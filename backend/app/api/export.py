"""Export API — stream a redacted PDF back to the client.

The PDF is sent in the request body, redacted in memory, and streamed back.
Nothing is written to disk or persisted on the server.
"""

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import Detection, Document
from app.security import limiter, verify_proxy_secret
from app.services.pdf_engine import PdfValidationError, apply_redactions

logger = get_logger(__name__)

router = APIRouter(tags=["export"])

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB
# PDFs always start with `%PDF-` followed by a version. Reject anything else
# before touching PyMuPDF so non-PDF payloads never reach fitz.open(): keeps
# error messages clean and prevents obscure exception text from being
# returned to clients.
_PDF_MAGIC = b"%PDF-"


def _build_redactions(detections: list[Detection]) -> list[dict]:
    """Flatten a list of detections into per-bbox redaction records."""
    redactions: list[dict] = []
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
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")

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

    if not detections:
        logger.info(
            "export.generated",
            document_id=str(document_id),
            detection_count=0,
            redaction_count=0,
        )
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="gelakt_{doc.filename}"'},
        )

    redactions = _build_redactions(detections)
    try:
        redacted_bytes = apply_redactions(pdf_bytes, redactions)
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
    )

    return StreamingResponse(
        io.BytesIO(redacted_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gelakt_{doc.filename}"'},
    )
