"""Analyze API — ephemeral text processing for client-first architecture.

The client extracts text from PDFs in the browser (via pdf.js) and sends it
here for rule-based NER analysis. The server processes the text, returns detections,
and discards the text. No document content is stored in the database.

SECURITY: Request bodies on this endpoint must NEVER be logged. The
structured logger below only receives metadata (document id, detection
counts, page counts) — never the extracted text itself.
"""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_document_or_404
from app.api.schemas import AnalyzeRequest, AnalyzeResponse, StructureSpanResponse
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import Detection
from app.security import limiter, verify_proxy_secret
from app.services.custom_term_matcher import CustomTermLike
from app.services.pipeline_engine import run_pipeline
from app.services.pdf_engine import extraction_from_client_data

logger = get_logger(__name__)

router = APIRouter(tags=["analyze"])


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
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """Analyze client-extracted text and return detections.

    The text is processed ephemerally — it is never written to the database
    or to server logs. Only detection metadata (bbox, type, tier, article)
    is persisted.
    """
    doc = await get_document_or_404(data.document_id, db)

    # `processing` is intentionally allowed as a re-entry point: an analyzer
    # run that was killed mid-flight (container restart, SIGKILL, hard timeout)
    # leaves the document stuck in `processing` forever because the revert-
    # to-`uploaded` happens in the Python `except` block. Refusing to retry
    # in that case traps the user with no recovery path short of a DB poke.
    # We accept the race risk of two concurrent analyzers on the same
    # document — the second commit overwrites the first's detections, which
    # is the same outcome as a sequential re-run.
    #
    # `approved` and `exported` are still blocked: re-analyzing a document
    # that has already been finalized would silently discard reviewed
    # decisions, which is not recoverable without an undo.
    if doc.status in ("approved", "exported"):
        raise HTTPException(
            status_code=400,
            detail=f"Document heeft status '{doc.status}', analyse niet mogelijk",
        )

    doc.status = "processing"
    await db.commit()
    logger.info(
        "analysis.requested",
        document_id=str(data.document_id),
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

        doc.page_count = extraction.page_count
        if extraction.document_date:
            doc.document_date = extraction.document_date

        # #17 — per-document reference list of names that must not be
        # redacted. The frontend sends the current list on every
        # analyze call; an empty list is the same as "no reference
        # list". The pipeline matches normalized spans against this
        # set and short-circuits to `rejected` with source
        # `reference_list`.
        #
        # #21 — per-document custom wordlist of terms that MUST be
        # redacted. Sent inline alongside `reference_names`; empty
        # means "no custom terms". The pipeline scans the full text
        # for every occurrence and emits `custom` detections at
        # `review_status="accepted"`.
        # CustomTermPayload satisfies the CustomTermLike Protocol structurally
        # (term/match_mode/woo_article are all present), but mypy treats
        # Protocol members as invariant, so the Literal["exact"] match_mode
        # field on the payload is not seen as a subtype of the Protocol's
        # `str`. Cast to widen the static type without changing runtime
        # behaviour.
        pipeline_result = await run_pipeline(
            extraction=extraction,
            public_official_names=data.reference_names,
            custom_terms=cast("list[CustomTermLike]", data.custom_terms),
        )

        # Clear existing detections
        existing = await db.execute(
            select(Detection).where(Detection.document_id == data.document_id)
        )
        for det in existing.scalars().all():
            await db.delete(det)

        # Store detections WITHOUT entity_text — the Detection model actively
        # rejects the kwarg (client-first architecture: no PII at rest).
        detection_count = 0
        for pd in pipeline_result.detections:
            detection = Detection(
                document_id=data.document_id,
                entity_type=pd.entity_type,
                tier=pd.tier,
                confidence=pd.confidence,
                woo_article=pd.woo_article,
                review_status=pd.review_status,
                bounding_boxes=pd.bounding_boxes,
                reasoning=pd.reasoning,
                source=pd.source,
                is_environmental=pd.is_environmental,
                subject_role=pd.subject_role,
                start_char=pd.start_char,
                end_char=pd.end_char,
            )
            db.add(detection)
            detection_count += 1

        doc.status = "review"
        await db.commit()

        logger.info(
            "analysis.completed",
            document_id=str(data.document_id),
            detection_count=detection_count,
            page_count=extraction.page_count,
            has_environmental_content=pipeline_result.has_environmental_content,
        )

        return AnalyzeResponse(
            document_id=data.document_id,
            detection_count=detection_count,
            page_count=extraction.page_count,
            structure_spans=[
                StructureSpanResponse(
                    kind=span.kind,
                    start_char=span.start_char,
                    end_char=span.end_char,
                    confidence=span.confidence,
                    evidence=span.evidence,
                )
                for span in pipeline_result.structure_spans
            ],
        )

    except HTTPException:
        raise
    except Exception:
        doc.status = "uploaded"
        await db.commit()
        # `.exception()` captures the traceback via structlog's
        # format_exc_info processor. Only the document id is logged — never
        # the incoming text.
        logger.exception(
            "analysis.failed",
            document_id=str(data.document_id),
        )
        raise HTTPException(
            status_code=500,
            detail="Analyse mislukt. Probeer het opnieuw.",
        ) from None
