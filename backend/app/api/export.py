"""Export API — stream a redacted PDF back to the client.

The PDF is sent in the request body, redacted in memory, and streamed back.
Nothing is written to disk or persisted on the server.

Two operating modes (#50):

- **Inline-redactions mode** — multipart upload with the PDF + a JSON
  redaction list. No document_id, no DB lookup, no Detection rows. The
  anonymous landing-page flow uses this exclusively. See
  ``/api/export/redact-stream``.

- **DB-lookup mode** (legacy) — accepts a document_id in the path and
  reads accepted detections from Postgres. Used by the
  (still-deferred) authenticated save flow. See
  ``/api/documents/{id}/export/redact-stream``. Will be removed once
  authenticated save lands and replaces it with a different shape.
"""

import io
import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_document_or_404
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import Detection
from app.security import limiter, verify_proxy_secret
from app.services.pdf_accessibility import post_process_for_accessibility
from app.services.pdf_engine import PdfValidationError, apply_redactions

logger = get_logger(__name__)

router = APIRouter(tags=["export"])

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_REDACTIONS = 10_000  # ~50× the largest real Woo besluit we've seen
# PDFs always start with `%PDF-` followed by a version. Reject anything else
# before touching PyMuPDF so non-PDF payloads never reach fitz.open(): keeps
# error messages clean and prevents obscure exception text from being
# returned to clients.
_PDF_MAGIC = b"%PDF-"
# Hard ceiling on the user-supplied PDF title that ends up in XMP
# metadata. Long enough to fit any sensible Dutch besluit name, short
# enough that even an accidental paste of the document body gets cut off
# before it leaks into the metadata.
_MAX_TITLE_LEN = 200


def _build_redactions(detections: list[Detection]) -> list[dict[str, object]]:
    """Flatten a list of detections into per-bbox redaction records."""
    redactions: list[dict[str, object]] = []
    for det in detections:
        if not det.bounding_boxes:
            continue
        for bbox in det.bounding_boxes:
            redactions.append(
                {
                    "page": bbox.get("page", 0),
                    "x0": bbox.get("x0", 0),
                    "y0": bbox.get("y0", 0),
                    "x1": bbox.get("x1", 0),
                    "y1": bbox.get("y1", 0),
                    "woo_article": det.woo_article or "",
                }
            )
    return redactions


def _read_title_header(request: Request) -> str | None:
    """Pull the optional PDF title out of the `X-Export-Title` header.

    A header (rather than a query parameter) keeps the title out of
    access logs and out of any URL captured by the proxy. Empty / blank
    titles return None so we skip writing a blank `dc:title` to the XMP
    block.
    """
    raw = request.headers.get("x-export-title", "")
    title = raw.strip()
    if not title:
        return None
    return title[:_MAX_TITLE_LEN]


def _sanitize_export_filename(filename: str | None) -> str:
    """Produce a safe `gelakt_*.pdf` filename for the Content-Disposition
    header. Strips path separators and weird characters; falls back to
    `document.pdf` for missing / blank input."""
    base = (filename or "document.pdf").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    safe = "".join(c for c in base if c.isalnum() or c in "._- ")
    safe = safe.strip()
    if not safe:
        safe = "document.pdf"
    if not safe.lower().endswith(".pdf"):
        safe = f"{safe}.pdf"
    return safe[:200]


class _InlineRedaction(BaseModel):
    """One redaction rectangle as sent by the anonymous client.

    Mirrors the shape of `_build_redactions` output so both modes feed
    the redaction engine the same dict layout. `woo_article` is
    optional — if the reviewer didn't pick one, we redact the box but
    leave the legend slot blank.
    """

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    woo_article: str = ""


def _parse_inline_redactions(raw: str) -> list[dict[str, object]]:
    """Decode the JSON `redactions` form field into the same flat dict
    layout `_build_redactions` produces in DB-lookup mode."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Ongeldige redacties: verwacht JSON-array.",
        ) from exc
    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400,
            detail="Ongeldige redacties: verwacht JSON-array.",
        )
    if len(parsed) > MAX_REDACTIONS:
        raise HTTPException(
            status_code=413,
            detail=f"Te veel redacties (max {MAX_REDACTIONS}).",
        )
    try:
        validated = [_InlineRedaction(**item) for item in parsed]
    except (ValidationError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Ongeldige redacties: bbox-velden ontbreken of zijn fout.",
        ) from exc
    return [item.model_dump() for item in validated]


@router.post(
    "/api/documents/{document_id}/export/redact-stream",
    dependencies=[Depends(verify_proxy_secret)],
)
@limiter.limit("10/minute")
async def redact_stream(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Accept a PDF binary, apply accepted redactions in memory, stream back.

    The original PDF is never written to disk or stored. It exists only
    in memory during this request.

    SECURITY: Request body must NOT be logged.
    """
    doc = await get_document_or_404(document_id, db)

    pdf_bytes = await request.body()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Geen PDF-data ontvangen")
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF te groot (max 50 MB)")
    if not pdf_bytes.startswith(_PDF_MAGIC):
        raise HTTPException(
            status_code=400,
            detail="Ongeldig bestand: dit is geen PDF.",
        )

    # Metadata-only log: size in bytes is safe, the bytes themselves are not.
    logger.info(
        "export.requested",
        document_id=str(document_id),
        pdf_bytes=len(pdf_bytes),
    )

    det_result = await db.execute(
        select(Detection).where(
            Detection.document_id == document_id,
            Detection.review_status.in_(["accepted", "auto_accepted"]),
            Detection.bounding_boxes.is_not(None),
        )
    )
    detections = list(det_result.scalars().all())
    redactions = _build_redactions(detections)

    title = _read_title_header(request)

    try:
        redacted_bytes = apply_redactions(pdf_bytes, redactions) if redactions else pdf_bytes
        # Accessibility post-processing runs on every export — even when
        # there are no redactions we still want /Lang and XMP set so the
        # exported PDF behaves correctly in screen readers and DMSes.
        final_bytes = post_process_for_accessibility(
            redacted_bytes,
            redactions=redactions,
            title=title,
        )
    except PdfValidationError:
        # Raised when PyMuPDF refuses the stream (corrupt / not a PDF even
        # though it passed the magic-byte check). Never echo parser output:
        # it can contain fragments of the document on some fitz versions.
        logger.warning("export.invalid_pdf", document_id=str(document_id))
        raise HTTPException(
            status_code=400,
            detail="PDF kon niet worden verwerkt. Controleer het bestand.",
        ) from None

    logger.info(
        "export.generated",
        document_id=str(document_id),
        detection_count=len(detections),
        redaction_count=len(redactions),
        # Title strings are deliberately not logged — they can contain
        # zaaknummers, person names, or other privacy-sensitive context
        # that the reviewer typed into the export field. Only a boolean
        # signal that someone *did* set a title is safe.
        title_set=title is not None,
    )

    return StreamingResponse(
        io.BytesIO(final_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gelakt_{doc.filename}"'},
    )


# ---------------------------------------------------------------------------
# Inline-redactions mode (#50 — anonymous, no DB lookup)
# ---------------------------------------------------------------------------


@router.post(
    "/api/export/redact-stream",
    dependencies=[Depends(verify_proxy_secret)],
)
@limiter.limit("10/minute")
async def redact_stream_inline(
    request: Request,
    pdf: UploadFile = File(..., description="The original PDF bytes."),
    redactions: str = Form(..., description="JSON array of redaction rectangles."),
    filename: str | None = Form(None, description="Original filename for Content-Disposition."),
) -> StreamingResponse:
    """Inline-redactions counterpart to the legacy DB-lookup endpoint.

    Anonymous clients (#50) don't have a Document row to anchor on, so
    they send the PDF and redaction list in a single multipart request
    instead of relying on the server to look up detections. The PDF is
    redacted in memory and streamed back; nothing is written to disk
    or persisted, exactly as in DB-lookup mode.

    SECURITY: Request body must NOT be logged.
    """
    pdf_bytes = await pdf.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Geen PDF-data ontvangen")
    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF te groot (max 50 MB)")
    if not pdf_bytes.startswith(_PDF_MAGIC):
        raise HTTPException(
            status_code=400,
            detail="Ongeldig bestand: dit is geen PDF.",
        )

    redaction_list = _parse_inline_redactions(redactions)
    safe_filename = _sanitize_export_filename(filename)

    # Metadata-only log: bbox count + size in bytes are safe; the bytes
    # themselves and the filename string are not (the filename can carry
    # zaaknummers / personal names typed by the reviewer). filename only
    # leaves the server in the Content-Disposition response header that
    # *the same client* receives back — never logged.
    logger.info(
        "export.anonymous_requested",
        pdf_bytes=len(pdf_bytes),
        redaction_count=len(redaction_list),
    )

    title = _read_title_header(request)

    try:
        redacted_bytes = (
            apply_redactions(pdf_bytes, redaction_list) if redaction_list else pdf_bytes
        )
        # Accessibility post-processing runs on every export — even when
        # there are no redactions we still want /Lang and XMP set so the
        # exported PDF behaves correctly in screen readers and DMSes.
        final_bytes = post_process_for_accessibility(
            redacted_bytes,
            redactions=redaction_list,
            title=title,
        )
    except PdfValidationError:
        # Raised when PyMuPDF refuses the stream (corrupt / not a PDF
        # even though it passed the magic-byte check). Never echo the
        # parser output: it can contain fragments of the document on
        # some fitz versions.
        logger.warning("export.anonymous_invalid_pdf")
        raise HTTPException(
            status_code=400,
            detail="PDF kon niet worden verwerkt. Controleer het bestand.",
        ) from None

    logger.info(
        "export.anonymous_generated",
        redaction_count=len(redaction_list),
        title_set=title is not None,
    )

    return StreamingResponse(
        io.BytesIO(final_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gelakt_{safe_filename}"'},
    )
