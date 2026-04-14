"""Detection API routes — list and update detections."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_document_or_404
from app.api.schemas import (
    DetectionResponse,
    DetectionUpdate,
    ManualDetectionCreate,
    MergeDetectionsRequest,
    SplitDetectionRequest,
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
    """Update a single detection (accept/reject/defer/edit/boundary-adjust)."""
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    detection = result.scalar_one_or_none()
    if not detection:
        raise HTTPException(status_code=404, detail="Detectie niet gevonden")

    # Boundary adjustment (#11). When the client sends a fresh bbox set we
    # snapshot the prior set into `original_bounding_boxes` the first time
    # (subsequent edits keep the analyzer's baseline, not the last value),
    # overwrite `bounding_boxes`, and flip `review_status` to "edited" unless
    # the same PATCH also sets an explicit status (e.g. undo/redo restoring
    # "accepted" alongside a bbox revert).
    bbox_adjusted = False
    prior_bounding_boxes: list[dict[str, Any]] | None = None
    if data.bounding_boxes is not None:
        if not data.bounding_boxes:
            raise HTTPException(
                status_code=400,
                detail="Grenscorrectie vereist ten minste één bounding box.",
            )
        prior_bounding_boxes = detection.bounding_boxes
        if detection.original_bounding_boxes is None:
            detection.original_bounding_boxes = prior_bounding_boxes
        new_bboxes: list[dict[str, Any]] = [bbox.model_dump() for bbox in data.bounding_boxes]
        detection.bounding_boxes = new_bboxes
        bbox_adjusted = True
        if data.review_status is None:
            detection.review_status = "edited"
            detection.reviewed_at = datetime.now(UTC)

    if data.review_status:
        detection.review_status = data.review_status
        detection.reviewed_at = datetime.now(UTC)

    if data.woo_article is not None:
        detection.woo_article = data.woo_article

    if data.subject_role is not None:
        # #15 — Tier 2 person-role classification. The chip click can arrive
        # together with a review_status flip (publiek_functionaris → rejected)
        # in a single PATCH; both fields are applied above.
        detection.subject_role = data.subject_role
    elif data.clear_subject_role:
        # Explicit clear path used by undo when the first chip click is being
        # reversed. `subject_role=None` alone means "don't touch"; the flag
        # disambiguates the two cases.
        detection.subject_role = None

    await db.commit()
    await db.refresh(detection)

    # Log the review action — status is metadata, not content. We never log
    # the redacted text itself (which is stored as "[redacted]" anyway).
    if data.review_status and not bbox_adjusted:
        logger.info(
            "detection.reviewed",
            detection_id=str(detection.id),
            document_id=str(detection.document_id),
            review_status=detection.review_status,
            tier=detection.tier,
            entity_type=detection.entity_type,
        )
    if bbox_adjusted:
        # Audit log: original and new bbox coordinates, no text content.
        # `prior` is the boxes that were on the row at the start of this
        # request (which, after undo/redo, may already be an edited set);
        # `original` is the analyzer's baseline for cross-edit comparison.
        logger.info(
            "detection.boundary_adjusted",
            detection_id=str(detection.id),
            document_id=str(detection.document_id),
            tier=detection.tier,
            entity_type=detection.entity_type,
            prior_bbox_count=len(prior_bounding_boxes or []),
            next_bbox_count=len(detection.bounding_boxes or []),
            prior_bboxes=prior_bounding_boxes,
            next_bboxes=detection.bounding_boxes,
            original_bboxes=detection.original_bounding_boxes,
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


# ---------------------------------------------------------------------------
# Split and merge (#18)
# ---------------------------------------------------------------------------


def _detection_from_original(
    *,
    original: Detection,
    bboxes: list[dict[str, Any]],
    split_from: uuid.UUID | None = None,
    merged_from: list[str] | None = None,
) -> Detection:
    """Create a new Detection row inheriting metadata from `original`.

    Used by both split and merge: the new row carries the original's
    entity_type / tier / woo_article / motivation so the sidebar does not
    lose its label, but becomes `source="manual"` so the regular delete
    endpoint can remove it — split/merge products are reviewer-authored by
    definition and should not be subject to the "auto detections are
    immutable" rule.
    """
    clone = Detection(
        document_id=original.document_id,
        entity_type=original.entity_type,
        tier=original.tier,
        # Split/merge products are reviewer-authored: full confidence.
        confidence=1.0,
        woo_article=original.woo_article,
        review_status="accepted",
        bounding_boxes=bboxes,
        reasoning=original.reasoning,
        source="manual",
        split_from=split_from,
        merged_from=merged_from,
    )
    clone.reviewed_at = datetime.now(UTC)
    return clone


@router.post(
    "/api/detections/{detection_id}/split",
    response_model=list[DetectionResponse],
    status_code=201,
)
async def split_detection(
    detection_id: uuid.UUID,
    data: SplitDetectionRequest,
    db: AsyncSession = Depends(get_db),
) -> list[Detection]:
    """Split a detection into two halves (#18).

    The client has resolved the split point against its local text layer
    and sends the two resulting bbox sets. We create two new detections,
    inherit metadata from the original (including motivation text), tag
    both with `split_from` for audit, and delete the original row.
    """
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Detectie niet gevonden")

    if not data.bboxes_a or not data.bboxes_b:
        raise HTTPException(
            status_code=400,
            detail="Splitsen vereist ten minste één bounding box per helft.",
        )

    original_id = original.id
    document_id = original.document_id
    tier = original.tier
    entity_type = original.entity_type

    left = _detection_from_original(
        original=original,
        bboxes=[bbox.model_dump() for bbox in data.bboxes_a],
        split_from=original_id,
    )
    right = _detection_from_original(
        original=original,
        bboxes=[bbox.model_dump() for bbox in data.bboxes_b],
        split_from=original_id,
    )

    db.add(left)
    db.add(right)
    await db.delete(original)
    await db.commit()
    await db.refresh(left)
    await db.refresh(right)

    # Audit log: uuids + bbox counts, never document text.
    logger.info(
        "detection.split",
        original_id=str(original_id),
        document_id=str(document_id),
        tier=tier,
        entity_type=entity_type,
        left_id=str(left.id),
        right_id=str(right.id),
        left_bbox_count=len(data.bboxes_a),
        right_bbox_count=len(data.bboxes_b),
    )

    return [left, right]


@router.post(
    "/api/detections/merge",
    response_model=DetectionResponse,
    status_code=201,
)
async def merge_detections(
    data: MergeDetectionsRequest,
    db: AsyncSession = Depends(get_db),
) -> Detection:
    """Merge two or more detections into one (#18).

    Bboxes are concatenated in the order of `detection_ids`. The new row
    inherits tier / entity_type / woo_article / motivation from the first
    detection in the list and carries all input uuids in `merged_from` for
    audit. The inputs are deleted.
    """
    if len(data.detection_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="Samenvoegen vereist minstens twee detecties.",
        )
    if len(set(data.detection_ids)) != len(data.detection_ids):
        raise HTTPException(
            status_code=400,
            detail="Duplicaat-ID's zijn niet toegestaan bij samenvoegen.",
        )

    result = await db.execute(select(Detection).where(Detection.id.in_(data.detection_ids)))
    originals_by_id = {det.id: det for det in result.scalars().all()}

    missing = [did for did in data.detection_ids if did not in originals_by_id]
    if missing:
        raise HTTPException(status_code=404, detail="Detectie niet gevonden")

    # Preserve the reviewer-specified order so the merge inherits the first
    # selected detection's metadata even if the DB returned them in a
    # different order.
    ordered = [originals_by_id[did] for did in data.detection_ids]
    primary = ordered[0]

    # All inputs must belong to the same document — otherwise "merge" has
    # no meaningful geometric interpretation and the resulting row would
    # be bound to whichever document id we picked first.
    document_ids = {det.document_id for det in ordered}
    if len(document_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="Samenvoegen over documenten heen wordt niet ondersteund.",
        )

    combined_bboxes: list[dict[str, Any]] = []
    for det in ordered:
        existing = det.bounding_boxes or []
        for bbox in existing:
            combined_bboxes.append(dict(bbox))

    if not combined_bboxes:
        raise HTTPException(
            status_code=400,
            detail="Samengevoegde detecties moeten ten minste één bounding box hebben.",
        )

    merged = _detection_from_original(
        original=primary,
        bboxes=combined_bboxes,
        merged_from=[str(did) for did in data.detection_ids],
    )

    db.add(merged)
    for det in ordered:
        await db.delete(det)
    await db.commit()
    await db.refresh(merged)

    logger.info(
        "detection.merged",
        merged_id=str(merged.id),
        document_id=str(primary.document_id),
        tier=primary.tier,
        entity_type=primary.entity_type,
        source_ids=[str(did) for did in data.detection_ids],
        bbox_count=len(combined_bboxes),
    )

    return merged
