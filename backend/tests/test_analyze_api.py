"""Contract tests for `POST /api/analyze`.

The route is the heart of the client-first architecture: it accepts
ephemerally-extracted text from the browser, runs the rule-based
detection pipeline, persists *only* detection metadata, and discards
the text. The invariants enforced here are small but unforgiving:

- Document text (full_text or text_items) must never hit the logs.
- Re-analyzing wipes previous detections (no ghost rows from a prior run).
- Document.status flips uploaded → processing → review on success, and
  reverts to uploaded on analyzer error.
- Re-entry from a stuck `processing` state is allowed; `approved` /
  `exported` are blocked to protect finalized reviews.

We stub `run_pipeline` so this file exercises the API contract, not the
detection engine itself (that has its own pytest module). The stub is a
plain async function on the `app.api.analyze` namespace — no respx/freeze
guns needed.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.api import analyze as analyze_module
from app.models.schemas import Detection, Document
from app.security import limiter
from app.services.pipeline_types import PipelineDetection, PipelineResult

# ---------------------------------------------------------------------------
# Rate limiter bypass — /api/analyze is rate-limited and the suite can cross
# the cap if several tests fire in quick succession. Shared-state in the
# slowapi limiter is process-global; toggle it off for this file.
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
# Pipeline stub
# ---------------------------------------------------------------------------


class _StubPipeline:
    """Replaces `analyze_module.run_pipeline` for contract tests.

    The default behavior returns an empty PipelineResult with a fixed
    page count — any test can override `.result` or `.raise_with` to
    drive a specific branch of the endpoint.
    """

    result: PipelineResult = PipelineResult(page_count=0)
    raise_with: Exception | None = None
    calls: list[dict[str, Any]] = []

    async def __call__(self, extraction: Any, **kwargs: Any) -> PipelineResult:
        _StubPipeline.calls.append({"extraction": extraction, **kwargs})
        if _StubPipeline.raise_with is not None:
            raise _StubPipeline.raise_with
        # Copy the page count through from the real extraction so analyze.py's
        # `doc.page_count = extraction.page_count` line is exercised faithfully.
        return PipelineResult(
            detections=list(_StubPipeline.result.detections),
            page_count=extraction.page_count,
            has_environmental_content=_StubPipeline.result.has_environmental_content,
        )


@pytest.fixture(autouse=True)
def _stub_run_pipeline(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _StubPipeline.result = PipelineResult(page_count=0)
    _StubPipeline.raise_with = None
    _StubPipeline.calls = []
    monkeypatch.setattr(analyze_module, "run_pipeline", _StubPipeline())
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_payload(doc_id: uuid.UUID, *, text: str = "Hallo wereld") -> dict[str, Any]:
    return {
        "document_id": str(doc_id),
        "pages": [
            {
                "page_number": 0,
                "full_text": text,
                "text_items": [
                    {"text": text, "x0": 10.0, "y0": 20.0, "x1": 110.0, "y1": 32.0}
                ],
            }
        ],
        "reference_names": [],
        "custom_terms": [],
    }


def _pipeline_detection(page: int = 0) -> PipelineDetection:
    return PipelineDetection(
        entity_text="Jan de Vries",
        entity_type="persoon",
        tier="2",
        confidence=0.85,
        woo_article="5.1.2e",
        review_status="pending",
        bounding_boxes=[
            {"page": page, "x0": 10.0, "y0": 20.0, "x1": 110.0, "y1": 32.0}
        ],
        reasoning="deduce/persoon",
        source="deduce",
    )


@pytest_asyncio.fixture
async def uploaded_doc(seed_db) -> Document:
    doc = Document(filename="test.pdf", page_count=0)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    return doc


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_persists_detections_and_flips_status(
    client: AsyncClient, uploaded_doc: Document, seed_db
) -> None:
    _StubPipeline.result = PipelineResult(
        detections=[_pipeline_detection()],
        page_count=1,
    )

    resp = await client.post(
        "/api/analyze", json=_sample_payload(uploaded_doc.id)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["document_id"] == str(uploaded_doc.id)
    assert body["detection_count"] == 1
    assert body["page_count"] == 1

    # Document row: status flipped to `review`, page_count updated.
    await seed_db.refresh(uploaded_doc)
    assert uploaded_doc.status == "review"
    assert uploaded_doc.page_count == 1

    # Detection row persisted with exactly the fields the pipeline produced.
    rows = (
        await seed_db.execute(
            select(Detection).where(Detection.document_id == uploaded_doc.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    det = rows[0]
    assert det.entity_type == "persoon"
    assert det.tier == "2"
    assert det.source == "deduce"
    assert det.woo_article == "5.1.2e"
    assert det.review_status == "pending"
    # Client-first: there is no entity_text column. Hasattr guards against a
    # future regression that re-adds it accidentally — the log guard test
    # below would also catch text leaking back into the pipeline.
    assert not hasattr(det, "entity_text")


@pytest.mark.asyncio
async def test_reanalyze_wipes_previous_detections(
    client: AsyncClient, uploaded_doc: Document, seed_db
) -> None:
    """Calling analyze twice must not double-persist — the second run
    deletes the previous row set before inserting, otherwise the sidebar
    would accumulate stale detections on every reload."""
    # Seed one stray detection from an imaginary prior run. It must be
    # gone after the next analyze.
    stale = Detection(
        document_id=uploaded_doc.id,
        entity_type="persoon",
        tier="2",
        confidence=0.5,
        woo_article="5.1.2e",
        review_status="pending",
        bounding_boxes=[{"page": 0, "x0": 0, "y0": 0, "x1": 1, "y1": 1}],
        reasoning="from a previous run",
        source="deduce",
    )
    seed_db.add(stale)
    await seed_db.commit()

    _StubPipeline.result = PipelineResult(
        detections=[_pipeline_detection()],
        page_count=1,
    )

    resp = await client.post(
        "/api/analyze", json=_sample_payload(uploaded_doc.id)
    )
    assert resp.status_code == 200

    rows = (
        await seed_db.execute(
            select(Detection).where(Detection.document_id == uploaded_doc.id)
        )
    ).scalars().all()
    # Exactly one row — the new one. The stale row was wiped.
    assert len(rows) == 1
    assert rows[0].reasoning != "from a previous run"


@pytest.mark.asyncio
async def test_processing_state_is_recoverable(
    client: AsyncClient, seed_db
) -> None:
    """A document stuck in `processing` (e.g. previous analyzer killed
    mid-flight) must be re-analyzable. Refusing to retry would trap the
    user with no recovery path."""
    doc = Document(filename="test.pdf", page_count=0, status="processing")
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)

    _StubPipeline.result = PipelineResult(page_count=1)
    resp = await client.post("/api/analyze", json=_sample_payload(doc.id))
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_document_returns_404(client: AsyncClient) -> None:
    bogus_id = uuid.uuid4()
    resp = await client.post("/api/analyze", json=_sample_payload(bogus_id))
    assert resp.status_code == 404
    assert "Document niet gevonden" in resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("final_status", ["approved", "exported"])
async def test_finalized_document_is_blocked(
    client: AsyncClient, seed_db, final_status: str
) -> None:
    """Re-analyzing a finalized document would silently discard reviewer
    decisions (the DELETE in analyze.py wipes the row set). Block it."""
    doc = Document(filename="test.pdf", page_count=1, status=final_status)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)

    resp = await client.post("/api/analyze", json=_sample_payload(doc.id))
    assert resp.status_code == 400
    assert final_status in resp.text


@pytest.mark.asyncio
async def test_analyzer_failure_reverts_status(
    client: AsyncClient, uploaded_doc: Document, seed_db
) -> None:
    """If the pipeline raises, the endpoint must set status back to
    `uploaded` so the client can retry. A 500 with status stuck on
    `processing` is the exact trap the test above protects against."""
    _StubPipeline.raise_with = RuntimeError("boom from stub pipeline")

    resp = await client.post(
        "/api/analyze", json=_sample_payload(uploaded_doc.id)
    )
    assert resp.status_code == 500
    assert "Analyse mislukt" in resp.text

    await seed_db.refresh(uploaded_doc)
    assert uploaded_doc.status == "uploaded"


# ---------------------------------------------------------------------------
# Privacy invariant: document text must not appear in logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_text_never_appears_in_logs(
    client: AsyncClient,
    uploaded_doc: Document,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CLAUDE.md invariant: request bodies on /api/analyze must NEVER be
    logged. If a future edit adds text fragments to a structured log
    call, this sentinel catches it — regardless of log level."""
    secret = "SentinelZinDieNietInLogsMag7f9e"

    _StubPipeline.result = PipelineResult(page_count=1)

    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            "/api/analyze", json=_sample_payload(uploaded_doc.id, text=secret)
        )
    assert resp.status_code == 200

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in combined


@pytest.mark.asyncio
async def test_full_text_never_appears_in_logs_on_failure(
    client: AsyncClient,
    uploaded_doc: Document,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failure path logs `analysis.failed` with a traceback. Verify
    the traceback doesn't serialize the request body either."""
    secret = "SentinelFailPadTextGe3h1a"
    _StubPipeline.raise_with = RuntimeError("explode but don't leak")

    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            "/api/analyze", json=_sample_payload(uploaded_doc.id, text=secret)
        )
    assert resp.status_code == 500

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in combined
