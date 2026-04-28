"""Analyze API — ephemeral text processing for client-first architecture.

The client extracts text from PDFs in the browser (via pdf.js) and sends it
here for rule-based NER analysis. The server processes the text, returns
detections, and discards the text. **Nothing is persisted** — no `Document`
row, no `Detection` row, no status mutation. The server returns a
session-scoped UUID and a fully-populated detection list inline; the
client manages its own state in IndexedDB from there (see
`session-state-store` and `detections.svelte.ts`).

This is the only mode (#50). The earlier save-mode (where the client
sent a `document_id` and the server persisted) has no caller after the
frontend went local-only and was removed; the future authenticated save
flow (50b) will land in a different shape and is tracked in the
backlog.

SECURITY: Request bodies on this endpoint must NEVER be logged. The
structured logger below only receives metadata (detection counts, page
counts) — never the extracted text itself.
"""

import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BoundingBoxResponse,
    DetectionResponse,
    StructureSpanResponse,
)
from app.logging_config import get_logger
from app.security import limiter, verify_proxy_secret
from app.services.custom_term_matcher import CustomTermLike
from app.services.pdf_engine import extraction_from_client_data
from app.services.pipeline_engine import run_pipeline
from app.services.pipeline_types import PipelineDetection

logger = get_logger(__name__)

router = APIRouter(tags=["analyze"])


def _pipeline_detection_to_response(
    pd: PipelineDetection, *, document_id: uuid.UUID
) -> DetectionResponse:
    """Materialize a pipeline detection as a response DTO with a fresh UUID.

    The id is freshly generated and only valid within the current
    response — the client uses it as a local key in its in-browser
    state. There is no Detection row to persist into.
    """
    return DetectionResponse(
        id=uuid.uuid4(),
        document_id=document_id,
        entity_type=pd.entity_type,
        tier=pd.tier,
        confidence=pd.confidence,
        woo_article=pd.woo_article,
        review_status=pd.review_status,
        bounding_boxes=[BoundingBoxResponse(**bbox) for bbox in pd.bounding_boxes],
        original_bounding_boxes=None,
        reasoning=pd.reasoning,
        source=pd.source,
        propagated_from=None,
        reviewer_id=None,
        reviewed_at=None,
        is_environmental=pd.is_environmental,
        subject_role=pd.subject_role,
        split_from=None,
        merged_from=None,
        start_char=pd.start_char,
        end_char=pd.end_char,
    )


@router.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    dependencies=[Depends(verify_proxy_secret)],
)
@limiter.limit("30/minute")
async def analyze_document(
    request: Request,
    response: Response,
    data: AnalyzeRequest,
) -> AnalyzeResponse:
    """Analyze client-extracted text and return detections inline.

    The text is processed ephemerally — never written to the database
    or to server logs. Detections come back with server-generated
    UUIDs that the client treats as local keys.
    """
    logger.info(
        "analysis.requested",
        page_count=len(data.pages),
    )

    try:
        pages_data = [
            {
                "page_number": p.page_number,
                "full_text": p.full_text,
                "text_items": [
                    {"text": ti.text, "x0": ti.x0, "y0": ti.y0, "x1": ti.x1, "y1": ti.y1}
                    for ti in p.text_items
                ],
            }
            for p in data.pages
        ]
        extraction = extraction_from_client_data(pages_data)

        # #17 — per-document reference list of names that must not be
        # redacted. The frontend sends the current list on every
        # analyze call; an empty list is the same as "no reference
        # list".
        #
        # #21 — per-document custom wordlist of terms that MUST be
        # redacted. Sent inline alongside `reference_names`; empty
        # means "no custom terms".
        #
        # CustomTermPayload satisfies the CustomTermLike Protocol
        # structurally (term/match_mode/woo_article are all present),
        # but mypy treats Protocol members as invariant, so the
        # `Literal["exact"]` match_mode field on the payload is not
        # seen as a subtype of the Protocol's `str`. Cast to widen
        # the static type without changing runtime behaviour.
        pipeline_result = await run_pipeline(
            extraction=extraction,
            public_official_names=data.reference_names,
            custom_terms=cast("list[CustomTermLike]", data.custom_terms),
        )

        structure_spans = [
            StructureSpanResponse(
                kind=span.kind,
                start_char=span.start_char,
                end_char=span.end_char,
                confidence=span.confidence,
                evidence=span.evidence,
            )
            for span in pipeline_result.structure_spans
        ]

        # The session document id is freshly generated per request. It
        # is self-consistent within this response (every detection
        # carries the same value) but never corresponds to a Postgres
        # row — the client treats it as an opaque local key.
        session_doc_id = uuid.uuid4()
        response_detections = [
            _pipeline_detection_to_response(pd, document_id=session_doc_id)
            for pd in pipeline_result.detections
        ]

        logger.info(
            "analysis.completed",
            detection_count=len(response_detections),
            page_count=extraction.page_count,
            has_environmental_content=pipeline_result.has_environmental_content,
        )

        return AnalyzeResponse(
            document_id=session_doc_id,
            detection_count=len(response_detections),
            page_count=extraction.page_count,
            detections=response_detections,
            structure_spans=structure_spans,
        )

    except HTTPException:
        raise
    except Exception:
        # `.exception()` captures the traceback via structlog's
        # format_exc_info processor. Only metadata is logged — never
        # the incoming text.
        logger.exception("analysis.failed")
        raise HTTPException(
            status_code=500,
            detail="Analyse mislukt. Probeer het opnieuw.",
        ) from None
