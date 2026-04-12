"""Detection API routes — trigger detection, list, update, propagate."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DetectionResponse, DetectionUpdate
from app.db.session import get_db
from app.models.schemas import Detection, Document, MotivationText, PublicOfficial
from app.services.llm_engine import run_pipeline
from app.services.motivation import generate_motivation_for_detection
from app.services.pdf_engine import extract_text
from app.services.propagation import propagate_name_decision, undo_propagation
from app.services.storage import storage

router = APIRouter(tags=["detections"])


@router.post("/api/documents/{document_id}/detect", status_code=202)
async def trigger_detection(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger the detection pipeline for a document."""
    # Load document
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")

    if doc.status not in ("uploaded", "review"):
        raise HTTPException(
            status_code=400,
            detail=f"Document heeft status '{doc.status}', detectie niet mogelijk",
        )

    # Update status to processing
    doc.status = "processing"
    await db.commit()

    try:
        # Download PDF from MinIO
        pdf_bytes = await storage.download(doc.minio_key_original)

        # Extract text
        extraction = extract_text(pdf_bytes)
        doc.page_count = extraction.page_count
        if extraction.document_date:
            doc.document_date = extraction.document_date

        # Get public officials list for this dossier
        officials_result = await db.execute(
            select(PublicOfficial.name).where(
                PublicOfficial.dossier_id == doc.dossier_id
            )
        )
        official_names = [row[0] for row in officials_result.all()]

        # Run pipeline
        pipeline_result = await run_pipeline(
            extraction=extraction,
            public_official_names=official_names,
        )

        # Clear existing detections for re-run
        existing = await db.execute(
            select(Detection).where(Detection.document_id == document_id)
        )
        for det in existing.scalars().all():
            await db.delete(det)

        # Store new detections
        detection_count = 0
        for pd in pipeline_result.detections:
            detection = Detection(
                document_id=document_id,
                entity_text=pd.entity_text,
                entity_type=pd.entity_type,
                tier=pd.tier,
                confidence=pd.confidence,
                woo_article=pd.woo_article,
                review_status=pd.review_status,
                bounding_boxes=pd.bounding_boxes,
                reasoning=pd.reasoning,
                source=pd.source,
            )
            db.add(detection)
            await db.flush()

            # Generate motivation text
            motivation_text = generate_motivation_for_detection(detection)
            if motivation_text:
                db.add(MotivationText(
                    detection_id=detection.id,
                    text=motivation_text,
                ))
            detection_count += 1

        doc.status = "review"
        await db.commit()

        return {
            "status": "completed",
            "document_id": str(document_id),
            "detection_count": detection_count,
            "page_count": extraction.page_count,
        }

    except Exception as e:
        doc.status = "uploaded"  # Reset on failure
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Detectie mislukt: {e}")


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
        detection.reviewed_at = datetime.now(timezone.utc)

    if data.woo_article is not None:
        detection.woo_article = data.woo_article

    if data.motivation_text is not None:
        # Update or create motivation text
        mot_result = await db.execute(
            select(MotivationText).where(MotivationText.detection_id == detection_id)
        )
        motivation = mot_result.scalar_one_or_none()
        if motivation:
            motivation.text = data.motivation_text
            motivation.is_edited = True
        else:
            db.add(MotivationText(
                detection_id=detection_id,
                text=data.motivation_text,
                is_edited=True,
            ))

    await db.commit()
    await db.refresh(detection)
    return detection


@router.post(
    "/api/documents/{document_id}/detections/batch",
    response_model=list[DetectionResponse],
)
async def batch_update_detections(
    document_id: uuid.UUID,
    updates: list[DetectionUpdate],
    detection_ids: list[uuid.UUID] = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[Detection]:
    """Batch update multiple detections."""
    if len(detection_ids) != len(updates):
        raise HTTPException(
            status_code=400,
            detail="Number of detection IDs must match number of updates",
        )

    result = await db.execute(
        select(Detection).where(
            Detection.id.in_(detection_ids),
            Detection.document_id == document_id,
        )
    )
    detections = {d.id: d for d in result.scalars().all()}

    updated: list[Detection] = []
    now = datetime.now(timezone.utc)

    for det_id, data in zip(detection_ids, updates):
        det = detections.get(det_id)
        if not det:
            continue
        if data.review_status:
            det.review_status = data.review_status
            det.reviewed_at = now
        if data.woo_article is not None:
            det.woo_article = data.woo_article
        updated.append(det)

    await db.commit()
    for det in updated:
        await db.refresh(det)
    return updated


@router.post("/api/detections/{detection_id}/propagate")
async def propagate_detection(
    detection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Propagate a name decision across the entire dossier."""
    try:
        propagated_ids = await propagate_name_decision(detection_id, db)
        return {
            "source_detection_id": str(detection_id),
            "propagated_count": len(propagated_ids),
            "propagated_ids": [str(pid) for pid in propagated_ids],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/detections/{detection_id}/undo-propagation")
async def undo_detection_propagation(
    detection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Undo all propagated decisions from a source detection."""
    count = await undo_propagation(detection_id, db)
    return {
        "source_detection_id": str(detection_id),
        "reset_count": count,
    }
