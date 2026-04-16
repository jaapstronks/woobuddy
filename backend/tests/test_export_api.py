"""Contract tests for `POST /api/documents/:id/export/redact-stream`.

This endpoint streams a redacted PDF back to the client. The bytes live
only in memory for the duration of the request — the server writes
nothing to disk. The tests here pin the contract:

- Magic-byte and size validation happen before PyMuPDF is called, so
  non-PDF payloads get a clean 400 rather than a cryptic parser error.
- The request body (PDF bytes) must never be logged — only byte counts.
- An accepted detection results in the PDF content actually changing;
  with no accepted detections the original bytes come back untouched.
- Rejected / deferred / pending detections must NOT be redacted.
- 404 on an unknown document id.

We build a real minimal PDF at fixture time using fitz so one happy-path
test round-trips the full pipeline; the rest of the tests use that same
fixture byte string so no on-disk sample is needed.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

import fitz
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.schemas import Detection, Document
from app.security import limiter

# ---------------------------------------------------------------------------
# Rate limiter bypass — export is capped to 10/min which crosses easily when
# multiple tests fire in the same process.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_rate_limiter() -> Iterator[None]:
    original = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = original


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_minimal_pdf(text: str = "Sentinel content") -> bytes:
    """Build a valid single-page PDF in memory via PyMuPDF.

    Keeping this here (rather than shipping a fixture file) means the
    test suite doesn't need an on-disk binary and the "happy path"
    assertions can reference the exact text we inserted.
    """
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 100), text, fontsize=12)
    out = doc.tobytes()
    doc.close()
    return out


@pytest_asyncio.fixture
async def doc_with_pdf(seed_db) -> Document:
    doc = Document(filename="test.pdf", page_count=1, status="review")
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    return doc


@pytest.fixture
def sample_pdf() -> bytes:
    return _build_minimal_pdf()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_body_400(client: AsyncClient, doc_with_pdf: Document) -> None:
    resp = await client.post(
        f"/api/documents/{doc_with_pdf.id}/export/redact-stream",
        content=b"",
        headers={"Content-Type": "application/pdf"},
    )
    assert resp.status_code == 400
    assert "Geen PDF-data" in resp.text


@pytest.mark.asyncio
async def test_non_pdf_magic_is_rejected_before_fitz(
    client: AsyncClient, doc_with_pdf: Document
) -> None:
    """Reject non-PDF payloads at the magic-byte check — never hand them
    to PyMuPDF, whose error messages can include parser fragments of
    the input on some versions."""
    resp = await client.post(
        f"/api/documents/{doc_with_pdf.id}/export/redact-stream",
        content=b"<html>nope</html>",
        headers={"Content-Type": "application/pdf"},
    )
    assert resp.status_code == 400
    assert "geen PDF" in resp.text


@pytest.mark.asyncio
async def test_oversized_payload_returns_413(
    client: AsyncClient, doc_with_pdf: Document
) -> None:
    """>50 MB must 413 without loading PyMuPDF. We build the payload by
    prepending the PDF magic to junk so the size check fires before the
    magic check, matching the endpoint's check order."""
    body = b"%PDF-" + b"0" * (50 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/api/documents/{doc_with_pdf.id}/export/redact-stream",
        content=body,
        headers={"Content-Type": "application/pdf"},
    )
    assert resp.status_code == 413
    assert "50 MB" in resp.text


@pytest.mark.asyncio
async def test_unknown_document_returns_404(
    client: AsyncClient, sample_pdf: bytes
) -> None:
    bogus_id = uuid.uuid4()
    resp = await client.post(
        f"/api/documents/{bogus_id}/export/redact-stream",
        content=sample_pdf,
        headers={"Content-Type": "application/pdf"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_accepted_detections_returns_original(
    client: AsyncClient, doc_with_pdf: Document, sample_pdf: bytes
) -> None:
    """Short-circuit path: no accepted detections means nothing to redact
    and the endpoint streams the original bytes straight back."""
    resp = await client.post(
        f"/api/documents/{doc_with_pdf.id}/export/redact-stream",
        content=sample_pdf,
        headers={"Content-Type": "application/pdf"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content == sample_pdf

    disp = resp.headers["content-disposition"]
    assert f'filename="gelakt_{doc_with_pdf.filename}"' in disp


@pytest.mark.asyncio
async def test_accepted_detection_actually_redacts_content(
    client: AsyncClient, doc_with_pdf: Document, seed_db
) -> None:
    """End-to-end: a single accepted detection over the sentinel text
    must produce a PDF that no longer contains the original string."""
    sentinel = "GeheimTextInPDF"
    pdf_bytes = _build_minimal_pdf(sentinel)

    # Verify the sentinel is actually in the original — otherwise the
    # assertion below would pass for the wrong reason.
    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert sentinel in src_doc[0].get_text()
    src_doc.close()

    # Seed an accepted detection whose bbox covers the text. Exact
    # coordinates don't have to match the text layout perfectly — fitz
    # blacks out any rect we give it — but we use a box that clearly
    # overlaps the ink.
    det = Detection(
        document_id=doc_with_pdf.id,
        entity_type="persoon",
        tier="2",
        confidence=1.0,
        woo_article="5.1.2e",
        review_status="accepted",
        bounding_boxes=[
            {"page": 0, "x0": 40.0, "y0": 90.0, "x1": 260.0, "y1": 115.0}
        ],
        reasoning="test",
        source="manual",
    )
    seed_db.add(det)
    await seed_db.commit()

    resp = await client.post(
        f"/api/documents/{doc_with_pdf.id}/export/redact-stream",
        content=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
    )
    assert resp.status_code == 200
    # The redacted PDF is a different byte string than the input.
    assert resp.content != pdf_bytes
    # And — the authoritative check — the sentinel text is gone from the
    # rendered text layer. fitz's apply_redactions removes the glyphs, not
    # just the visual.
    out_doc = fitz.open(stream=resp.content, filetype="pdf")
    assert sentinel not in out_doc[0].get_text()
    out_doc.close()


@pytest.mark.asyncio
async def test_only_accepted_and_auto_accepted_are_redacted(
    client: AsyncClient, doc_with_pdf: Document, sample_pdf: bytes, seed_db
) -> None:
    """Pending / rejected / deferred / edited rows must NOT redact.
    The endpoint filters on review_status — if that filter ever changes
    silently, a reject would start blacking out text and we'd ship a
    privacy regression. This test guards the filter."""
    for status in ("pending", "rejected", "deferred", "edited"):
        det = Detection(
            document_id=doc_with_pdf.id,
            entity_type="persoon",
            tier="2",
            confidence=1.0,
            woo_article="5.1.2e",
            review_status=status,
            bounding_boxes=[
                {"page": 0, "x0": 0.0, "y0": 0.0, "x1": 300.0, "y1": 200.0}
            ],
            reasoning=f"status={status}",
            source="manual",
        )
        seed_db.add(det)
    await seed_db.commit()

    resp = await client.post(
        f"/api/documents/{doc_with_pdf.id}/export/redact-stream",
        content=sample_pdf,
        headers={"Content-Type": "application/pdf"},
    )
    assert resp.status_code == 200
    # Nothing eligible → bytes are returned unchanged.
    assert resp.content == sample_pdf


# ---------------------------------------------------------------------------
# Privacy invariant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_body_never_appears_in_logs(
    client: AsyncClient,
    doc_with_pdf: Document,
    sample_pdf: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Request body on /api/documents/:id/export/redact-stream must never
    be logged. Only byte counts are. We inject a sentinel ASCII marker
    inside a *valid* PDF so the magic check passes but any accidental
    logger.info(pdf_bytes) would pick up the marker."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "SentinelPDFBodyMarker9z1k", fontsize=12)
    body = doc.tobytes()
    doc.close()
    assert body[:5] == b"%PDF-"

    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            f"/api/documents/{doc_with_pdf.id}/export/redact-stream",
            content=body,
            headers={"Content-Type": "application/pdf"},
        )
    assert resp.status_code == 200

    combined = "\n".join(record.getMessage() for record in caplog.records)
    # The sentinel lives inside the PDF stream; if the body were logged,
    # the marker would appear. Byte-count metadata is fine.
    assert "SentinelPDFBodyMarker9z1k" not in combined
