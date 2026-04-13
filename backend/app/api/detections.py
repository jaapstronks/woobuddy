"""Detection API routes — list and update detections."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_document_or_404
from app.api.schemas import (
    DetectionResponse,
    DetectionUpdate,
    ManualDetectionCreate,
)
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


@router.post(
    "/api/detections",
    response_model=DetectionResponse,
    status_code=201,
)
async def create_manual_detection(
    data: ManualDetectionCreate,
    db: AsyncSession = Depends(get_db),
) -> Detection:
    """Create a reviewer-authored redaction from a text selection.

    The client has selected text in the PDF text layer, resolved it to one
    or more bounding boxes in PDF coordinates, and sends only that position
    metadata here. The selected text itself stays in the browser — we never
    persist `entity_text`, in line with the client-first architecture.
    """
    await get_document_or_404(data.document_id, db)

    if not data.bounding_boxes:
        raise HTTPException(
            status_code=400,
            detail="Handmatige detectie vereist ten minste één bounding box.",
        )

    detection = Detection(
        document_id=data.document_id,
        entity_type=data.entity_type,
        tier=data.tier,
        confidence=1.0,  # Reviewer-authored: full confidence by definition.
        woo_article=data.woo_article,
        review_status="accepted",
        bounding_boxes=[bbox.model_dump() for bbox in data.bounding_boxes],
        reasoning=data.motivation_text,
        # "manual" for single text/area selections, "search_redact" for the
        # bulk-apply path in #09. Both are reviewer-authored and both are
        # deletable via `DELETE /api/detections/:id`.
        source=data.source,
    )
    detection.reviewed_at = datetime.now(UTC)
    db.add(detection)
    await db.commit()
    await db.refresh(detection)

    # Audit log: who/what/when, NEVER the selected text.
    logger.info(
        "detection.manual_created",
        detection_id=str(detection.id),
        document_id=str(detection.document_id),
        tier=detection.tier,
        entity_type=detection.entity_type,
        woo_article=detection.woo_article,
        bbox_count=len(data.bounding_boxes),
        source=detection.source,
    )
    return detection


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


@router.delete("/api/detections/{detection_id}", status_code=204)
async def delete_detection(
    detection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a reviewer-authored detection.

    Used by the frontend undo stack to reverse a manual text/area redaction.
    Auto detections (NER / regex) are NOT deletable — undoing their acceptance
    flips their `review_status` back instead, so the server-side detection set
    remains authoritative for everything the analyzers produced.
    """
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    detection = result.scalar_one_or_none()
    if not detection:
        raise HTTPException(status_code=404, detail="Detectie niet gevonden")

    if detection.source not in ("manual", "search_redact"):
        # 422 — the request is well-formed but the target is not eligible.
        # Both reviewer-authored sources are deletable; anything produced by
        # the analyzers (regex/deduce/llm) stays put so the undo stack for
        # an accept/reject only flips review_status.
        raise HTTPException(
            status_code=422,
            detail="Alleen handmatige detecties kunnen worden verwijderd.",
        )

    # Capture audit fields before the row is gone.
    document_id = detection.document_id
    tier = detection.tier
    entity_type = detection.entity_type

    await db.delete(detection)
    await db.commit()

    logger.info(
        "detection.deleted",
        detection_id=str(detection_id),
        document_id=str(document_id),
        tier=tier,
        entity_type=entity_type,
    )
    return Response(status_code=204)
