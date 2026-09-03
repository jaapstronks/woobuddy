"""Contract tests for `POST /api/export/redact-stream` (anonymous, inline).

The endpoint accepts a multipart upload with the PDF + a JSON list of
redaction rectangles + an optional filename. Redaction happens in
memory, the redacted PDF streams back, and nothing is persisted on the
server. The earlier DB-lookup mode (`/api/documents/{id}/export/...`)
was removed when the rest of the unused server-side review state went
— there is no longer a Document or Detection row to anchor an export
on.

The tests pin:

- Magic-byte and size validation happen before PyMuPDF is called, so
  non-PDF payloads get a clean 400 rather than a cryptic parser error.
- The request body (PDF bytes) and reviewer-supplied filename / title
  must never be logged — only metadata (counts, booleans).
- Empty redactions still post-process for accessibility, but leave
  the original content intact.
- `/Lang (nl-NL)` lands on the final bytes of *every* export, redacted
  or not. Until #67 the Ghostscript step ran last and stripped it on any
  machine that had `gs` installed, so the export suite meant something
  different on a dev laptop than in CI.
- The redaction + accessibility chain runs off the event loop (#67), so
  one 50 MB export cannot stall health checks for seconds.
- A redaction box that covers a known sentinel string actually
  removes it from the output.
- Bad redaction JSON returns a clean 400, never a 500.
- The response carries `Content-Disposition: attachment;
  filename="gelakt_<sanitized>.pdf"` and the sanitization actually
  strips path separators.
- Acceptance for #50: the full flow writes ZERO rows to documents and
  detections.

We build a real minimal PDF at fixture time using fitz so the happy-
path tests round-trip the full pipeline.
"""

from __future__ import annotations

import io
import json
import logging
import threading
from collections.abc import Iterator
from unittest.mock import patch

import fitz
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api import export as export_module
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


@pytest.fixture
def sample_pdf() -> bytes:
    return _build_minimal_pdf()


def _redaction(page: int = 0, *, woo_article: str = "5.1.2e") -> dict:
    return {
        "page": page,
        "x0": 50.0,
        "y0": 95.0,
        "x1": 200.0,
        "y1": 110.0,
        "woo_article": woo_article,
    }


# ---------------------------------------------------------------------------
# Acceptance + happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_persists_nothing(client: AsyncClient, sample_pdf: bytes, seed_db) -> None:
    """The acceptance criterion (#50): a redact-stream call streams a
    redacted PDF back and writes ZERO rows to the documents and
    detections tables."""
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, json.dumps([_redaction()])),
            "filename": (None, "test.pdf"),
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "gelakt_test.pdf" in resp.headers.get("content-disposition", "")

    out_doc = fitz.open(stream=resp.content, filetype="pdf")
    try:
        # Sentinel text was inside the redaction box — it must be gone.
        assert "Sentinel content" not in out_doc[0].get_text()
    finally:
        out_doc.close()

    # Acceptance: zero rows in either table.
    docs = (await seed_db.execute(select(Document))).scalars().all()
    detections = (await seed_db.execute(select(Detection))).scalars().all()
    assert len(docs) == 0
    assert len(detections) == 0


@pytest.mark.asyncio
async def test_empty_redactions_returns_unmodified(client: AsyncClient, sample_pdf: bytes) -> None:
    """With an empty redaction list the response is still a valid PDF
    (post-processed for accessibility) — but the original sentinel text
    must remain visible."""
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, "[]"),
        },
    )
    assert resp.status_code == 200
    out_doc = fitz.open(stream=resp.content, filetype="pdf")
    try:
        assert "Sentinel content" in out_doc[0].get_text()
    finally:
        out_doc.close()

    # /Lang nl-NL should still land on the catalog from the
    # accessibility post-processing pass — verifies that running it
    # against an unredacted PDF doesn't somehow no-op.
    import pikepdf

    pdf = pikepdf.open(io.BytesIO(resp.content))
    try:
        assert str(pdf.Root.get("/Lang")) == "nl-NL"
    finally:
        pdf.close()


@pytest.mark.asyncio
async def test_out_of_range_redaction_is_counted_not_swallowed(
    client: AsyncClient,
    sample_pdf: bytes,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression (#66/5): a box whose page index is past the end of the
    document used to be dropped with a bare `continue` — the export
    returned 200 and the reviewer had no way to know a black box was
    missing. The response now carries the counts and a warning is logged.
    """
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (
                None,
                json.dumps([_redaction(page=0), _redaction(page=7)]),
            ),
        },
    )
    assert resp.status_code == 200
    assert resp.headers["x-redactions-applied"] == "1"
    assert resp.headers["x-redactions-skipped"] == "1"

    logged = capsys.readouterr().out
    assert "export.redactions_out_of_range" in logged
    assert '"skipped": 1' in logged

    # The in-range box still did its job.
    out_doc = fitz.open(stream=resp.content, filetype="pdf")
    try:
        assert "Sentinel content" not in out_doc[0].get_text()
    finally:
        out_doc.close()


@pytest.mark.asyncio
async def test_all_boxes_in_range_reports_zero_skipped(
    client: AsyncClient, sample_pdf: bytes
) -> None:
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, json.dumps([_redaction(page=0)])),
        },
    )
    assert resp.status_code == 200
    assert resp.headers["x-redactions-applied"] == "1"
    assert resp.headers["x-redactions-skipped"] == "0"


@pytest.mark.asyncio
async def test_filename_sanitized(client: AsyncClient, sample_pdf: bytes) -> None:
    """A reviewer-supplied filename can carry path separators or weird
    characters — the Content-Disposition header must round-trip a clean
    `gelakt_*.pdf`."""
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("ignored.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, "[]"),
            "filename": (None, "../../etc/passwd"),
        },
    )
    assert resp.status_code == 200
    disposition = resp.headers.get("content-disposition", "")
    assert "gelakt_passwd.pdf" in disposition
    assert ".." not in disposition
    assert "/" not in disposition.split("filename=")[1]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_redactions_json_400(client: AsyncClient, sample_pdf: bytes) -> None:
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, "not-json"),
        },
    )
    assert resp.status_code == 400
    assert "Ongeldige redacties" in resp.text


@pytest.mark.asyncio
async def test_redactions_must_be_array_400(client: AsyncClient, sample_pdf: bytes) -> None:
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, '{"not": "array"}'),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_missing_bbox_field_400(client: AsyncClient, sample_pdf: bytes) -> None:
    bad = json.dumps([{"page": 0, "x0": 0, "x1": 10, "y0": 0}])  # no y1
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, bad),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_pdf_payload_400(client: AsyncClient) -> None:
    """Reject non-PDF payloads at the magic-byte check — never hand
    them to PyMuPDF, whose error messages can include parser
    fragments of the input on some versions."""
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("evil.txt", b"not a pdf", "application/pdf"),
            "redactions": (None, "[]"),
        },
    )
    assert resp.status_code == 400
    assert "geen pdf" in resp.text.lower()


@pytest.mark.asyncio
async def test_empty_pdf_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("empty.pdf", b"", "application/pdf"),
            "redactions": (None, "[]"),
        },
    )
    assert resp.status_code == 400
    assert "Geen PDF-data" in resp.text


@pytest.mark.asyncio
async def test_oversized_payload_returns_413(client: AsyncClient) -> None:
    """>50 MB must 413 without loading PyMuPDF. Pad PDF magic bytes
    with zeros so the size check fires before the magic check."""
    body = b"%PDF-" + b"0" * (50 * 1024 * 1024 + 1)
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("huge.pdf", body, "application/pdf"),
            "redactions": (None, "[]"),
        },
    )
    assert resp.status_code == 413
    assert "50 MB" in resp.text


# ---------------------------------------------------------------------------
# Privacy invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_bytes_never_appear_in_logs(
    client: AsyncClient,
    sample_pdf: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The happy-path log line must not echo the PDF content. The
    sentinel string we baked into the fixture is unique enough that
    finding it in any log record means a regression."""
    sentinel = "Sentinel content"
    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            "/api/export/redact-stream",
            files={
                "pdf": ("test.pdf", sample_pdf, "application/pdf"),
                "redactions": (None, json.dumps([_redaction()])),
            },
        )
    assert resp.status_code == 200
    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel not in combined


@pytest.mark.asyncio
async def test_title_header_lands_in_xmp_not_logs(
    client: AsyncClient,
    sample_pdf: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The user-supplied PDF title (X-Export-Title header) ends up in
    XMP metadata and must NOT appear in any log line. Reviewers may
    put zaaknummers, person names, or other privacy-sensitive context
    into that field — leaking it into structured logs would be a
    regression against the client-first architecture."""
    sentinel_title = "ExportTitleSentinel7e3a"
    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            "/api/export/redact-stream",
            files={
                "pdf": ("test.pdf", sample_pdf, "application/pdf"),
                "redactions": (None, "[]"),
            },
            headers={"X-Export-Title": sentinel_title},
        )
    assert resp.status_code == 200

    import pikepdf as _pikepdf

    pdf = _pikepdf.open(io.BytesIO(resp.content))
    try:
        with pdf.open_metadata() as meta:
            assert meta["dc:title"] == sentinel_title
    finally:
        pdf.close()

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel_title not in combined


@pytest.mark.asyncio
async def test_redacted_export_carries_language_tag(client: AsyncClient, sample_pdf: bytes) -> None:
    """`/Lang` must be on the final bytes of a *redacted* export too.

    The empty-redaction test above covers the cheap path; this one covers
    the path that actually goes through PyMuPDF and all three pikepdf
    round-trips, which is where #67's Ghostscript step used to sit and
    wipe the catalog."""
    resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", sample_pdf, "application/pdf"),
            "redactions": (None, json.dumps([_redaction()])),
        },
    )
    assert resp.status_code == 200, resp.text

    import pikepdf

    pdf = pikepdf.open(io.BytesIO(resp.content))
    try:
        assert str(pdf.Root.get("/Lang")) == "nl-NL"
    finally:
        pdf.close()


@pytest.mark.asyncio
async def test_chain_runs_off_the_event_loop(client: AsyncClient, sample_pdf: bytes) -> None:
    """Acceptance for #67: the handler does no CPU work on the event loop.

    PyMuPDF's redaction pass plus three pikepdf open→save round-trips can
    hold the loop for seconds on a real besluit, taking `/api/health` down
    with it. Rather than time it (flaky), assert where the work happens:
    the chain must be running on a worker thread, not the one the loop
    lives on."""
    loop_thread = threading.current_thread()
    seen: list[threading.Thread] = []
    real = export_module.post_process_for_accessibility

    def _spy(*args, **kwargs):
        seen.append(threading.current_thread())
        return real(*args, **kwargs)

    with patch.object(export_module, "post_process_for_accessibility", _spy):
        resp = await client.post(
            "/api/export/redact-stream",
            files={
                "pdf": ("test.pdf", sample_pdf, "application/pdf"),
                "redactions": (None, json.dumps([_redaction()])),
            },
        )
    assert resp.status_code == 200, resp.text
    assert len(seen) == 1
    assert seen[0] is not loop_thread
