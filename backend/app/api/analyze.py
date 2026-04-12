"""Analyze API — ephemeral text processing for client-first architecture.

The client extracts text from PDFs in the browser (via pdf.js) and sends it
here for NER/LLM analysis. The server processes the text, returns detections,
and discards the text. No document content is stored in the database.

SECURITY: Request bodies on this endpoint must NEVER be logged. The
structured logger below only receives metadata (document id, detection
counts, page counts) — never the extracted text itself.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AnalyzeRequest, AnalyzeResponse
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import Detection, Document
from app.security import limiter, verify_proxy_secret
from app.services.llm_engine import run_pipeline
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
    data: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """Analyze client-extracted text and return detections.

    The text is processed ephemerally — it is never written to the database
    or to server logs. Only detection metadata (bbox, type, tier, article)
    is persisted.
    """
    result = await db.execute(select(Document).where(Document.id == data.document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")

    if doc.status not in ("uploaded", "review"):
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

        pipeline_result = await run_pipeline(
            extraction=extraction,
            public_official_names=[],
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
