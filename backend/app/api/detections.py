"""Detection API routes — list and update detections."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DetectionResponse, DetectionUpdate
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import Detection
from app.security import verify_proxy_secret

logger = get_logger(__name__)

router = APIRouter(
    tags=["detections"],
    dependencies=[Depends(verify_proxy_secret)],
)


@router.get(
    "/api/documents/{document_id}/detections",
    response_model=list[DetectionResponse],
)
async def list_detections(
    document_id: uuid.UUID,
    tier: str | None = Query(None, description="Filter by tier (1, 2, 3)"),
    db: AsyncSession = Depends(get_db),
) -> list[Detection]:
    """List all detections for a document, optionally filtered by tier."""
    query = select(Detection).where(Detection.document_id == document_id)
    if tier:
        query = query.where(Detection.tier == tier)
    query = query.order_by(Detection.tier, Detection.confidence.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.patch("/api/detections/{detection_id}", response_model=DetectionResponse)
async def update_detection(
    detection_id: uuid.UUID,
    data: DetectionUpdate,
    db: AsyncSession = Depends(get_db),
) -> Detection:
    """Update a single detection (accept/reject/defer/edit)."""
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    detection = result.scalar_one_or_none()
    if not detection:
        raise HTTPException(status_code=404, detail="Detectie niet gevonden")

    if data.review_status:
        detection.review_status = data.review_status
        detection.reviewed_at = datetime.now(UTC)

    if data.woo_article is not None:
        detection.woo_article = data.woo_article

    await db.commit()
    await db.refresh(detection)

    # Log the review action — status is metadata, not content. We never log
    # the redacted text itself (which is stored as "[redacted]" anyway).
    if data.review_status:
        logger.info(
            "detection.reviewed",
            detection_id=str(detection.id),
            document_id=str(detection.document_id),
            review_status=detection.review_status,
            tier=detection.tier,
            entity_type=detection.entity_type,
        )
    return detection
