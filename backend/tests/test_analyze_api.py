"""Contract tests for `POST /api/analyze` (anonymous-only since #50).

The route is the heart of the client-first architecture: it accepts
ephemerally-extracted text from the browser, runs the rule-based
detection pipeline, returns the full detection list inline with
server-generated UUIDs, and persists nothing. The invariants
enforced here are small but unforgiving:

- Document text (`full_text` or `text_items`) must never hit the logs.
- Anonymous flow writes ZERO rows to `documents` and `detections`.
- The detection list comes back inline, so the client never has to
  follow up with a GET.
- Pipeline failure returns 500 without leaving state behind.

We stub `run_pipeline` so this file exercises the API contract, not the
detection engine itself (that has its own pytest module). The stub is a
plain async function on the `app.api.analyze` namespace — no respx /
freeze guns needed.
"""

from __future__ import annotations

import json as _json
import logging
from collections.abc import Iterator
from typing import Any

import fitz as _fitz
import pytest
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
        return PipelineResult(
            detections=list(_StubPipeline.result.detections),
            page_count=extraction.page_count,
            has_environmental_content=_StubPipeline.result.has_environmental_content,
            structure_spans=list(_StubPipeline.result.structure_spans),
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


def _payload(*, text: str = "Hallo wereld") -> dict[str, Any]:
    return {
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


# ---------------------------------------------------------------------------
# Acceptance: zero rows persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_persists_nothing(client: AsyncClient, seed_db) -> None:
    """The acceptance criterion (#50): an analyze call writes zero rows
    to `documents` and zero rows to `detections`. The pipeline still
    runs; the detections come back inline in the response."""
    _StubPipeline.result = PipelineResult(
        detections=[_pipeline_detection()],
        page_count=1,
    )

    resp = await client.post("/api/analyze", json=_payload())
    assert resp.status_code == 200, resp.text

    body = resp.json()
    # Server generated a fresh session document id — non-empty UUID,
    # never corresponds to a Postgres row.
    assert body["document_id"]
    assert body["detection_count"] == 1
    assert body["page_count"] == 1
    assert len(body["detections"]) == 1

    detection = body["detections"][0]
    assert detection["entity_type"] == "persoon"
    assert detection["tier"] == "2"
    assert detection["source"] == "deduce"
    assert detection["bounding_boxes"][0]["page"] == 0
    # Server-generated id; client uses it as a local key.
    assert detection["id"]
    assert detection["document_id"] == body["document_id"]

    # The acceptance check: zero rows in either table.
    docs = (await seed_db.execute(select(Document))).scalars().all()
    detections = (await seed_db.execute(select(Detection))).scalars().all()
    assert len(docs) == 0
    assert len(detections) == 0


@pytest.mark.asyncio
async def test_response_includes_structure_spans(client: AsyncClient) -> None:
    """Structure spans (#14) ride along with the response — the
    frontend uses them for bulk-sweep affordances (#20) and Tier 2
    card context (#15)."""
    from app.services.structure_engine import StructureSpan

    _StubPipeline.result = PipelineResult(
        page_count=1,
        structure_spans=[
            StructureSpan(
                kind="signature_block",
                start_char=10,
                end_char=42,
                confidence=0.9,
                evidence="Met vriendelijke groet,",
            )
        ],
    )

    resp = await client.post("/api/analyze", json=_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["structure_spans"]) == 1
    assert body["structure_spans"][0]["kind"] == "signature_block"


@pytest.mark.asyncio
async def test_pipeline_failure_returns_500_without_persisting(
    client: AsyncClient, seed_db
) -> None:
    """When the pipeline raises the response is a 500 with a generic
    Dutch error — and crucially still no DB writes."""
    _StubPipeline.raise_with = RuntimeError("boom")

    resp = await client.post("/api/analyze", json=_payload())
    assert resp.status_code == 500
    assert "Analyse mislukt" in resp.text

    docs = (await seed_db.execute(select(Document))).scalars().all()
    detections = (await seed_db.execute(select(Detection))).scalars().all()
    assert len(docs) == 0
    assert len(detections) == 0


# ---------------------------------------------------------------------------
# Privacy invariant: document text must not appear in logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_text_never_appears_in_logs(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CLAUDE.md invariant: request bodies on /api/analyze must NEVER be
    logged. If a future edit adds text fragments to a structured log
    call, this sentinel catches it — regardless of log level."""
    secret = "SentinelZinDieNietInLogsMag7f9e"
    _StubPipeline.result = PipelineResult(page_count=1)

    with caplog.at_level(logging.DEBUG):
        resp = await client.post("/api/analyze", json=_payload(text=secret))
    assert resp.status_code == 200

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in combined


@pytest.mark.asyncio
async def test_full_text_never_appears_in_logs_on_failure(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failure path logs `analysis.failed` with a traceback. Verify
    the traceback doesn't serialize the request body either."""
    secret = "SentinelFailPadTextGe3h1a"
    _StubPipeline.raise_with = RuntimeError("explode but don't leak")

    with caplog.at_level(logging.DEBUG):
        resp = await client.post("/api/analyze", json=_payload(text=secret))
    assert resp.status_code == 500

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in combined


# ---------------------------------------------------------------------------
# End-to-end acceptance — analyze + export, zero rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_then_export_produces_zero_rows(
    client: AsyncClient, seed_db
) -> None:
    """The Phase D acceptance test for #50: a reviewer's full flow —
    analyze, then export with the returned detections as redactions —
    must leave both `documents` and `detections` tables empty.
    Combined here so the trust-claim invariant is verifiable in one
    spot."""
    _StubPipeline.result = PipelineResult(
        detections=[_pipeline_detection()],
        page_count=1,
    )

    analyze_resp = await client.post("/api/analyze", json=_payload())
    assert analyze_resp.status_code == 200
    body = analyze_resp.json()
    assert body["detection_count"] == 1
    assert len(body["detections"]) == 1

    # Build a real minimal PDF and feed it to the export endpoint along
    # with the analyze response's detections re-shaped as redactions.
    pdf_doc = _fitz.open()
    pdf_doc.new_page(width=300, height=200).insert_text((50, 100), "Hi", fontsize=12)
    pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    redactions = [
        {
            "page": bbox["page"],
            "x0": bbox["x0"],
            "y0": bbox["y0"],
            "x1": bbox["x1"],
            "y1": bbox["y1"],
            "woo_article": body["detections"][0]["woo_article"] or "",
        }
        for bbox in body["detections"][0]["bounding_boxes"]
    ]
    export_resp = await client.post(
        "/api/export/redact-stream",
        files={
            "pdf": ("test.pdf", pdf_bytes, "application/pdf"),
            "redactions": (None, _json.dumps(redactions)),
        },
    )
    assert export_resp.status_code == 200, export_resp.text

    # Acceptance: both tables empty after the full flow.
    docs = (await seed_db.execute(select(Document))).scalars().all()
    detections = (await seed_db.execute(select(Detection))).scalars().all()
    assert len(docs) == 0
    assert len(detections) == 0
