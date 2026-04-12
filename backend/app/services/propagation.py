"""Name propagation service.

When a reviewer confirms a name detection (e.g. "J. de Vries" is a citizen),
all other occurrences of that name across the dossier are automatically
accepted with the same decision. All propagated detections link back to the
source and can be reversed with a single action.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import Detection, Document

logger = logging.getLogger(__name__)


async def propagate_name_decision(
    source_detection_id: uuid.UUID,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """Propagate a name detection decision across all documents in the same dossier.

    Returns the IDs of all newly propagated detections.
    """
    # Load the source detection
    result = await db.execute(
        select(Detection).where(Detection.id == source_detection_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise ValueError(f"Detection {source_detection_id} not found")

    if source.entity_type != "persoon":
        raise ValueError("Only person name detections can be propagated")

    if source.review_status not in ("accepted", "rejected"):
        raise ValueError("Only reviewed detections can be propagated")

    # Find the dossier for this detection's document
    doc_result = await db.execute(
        select(Document).where(Document.id == source.document_id)
    )
    source_doc = doc_result.scalar_one_or_none()
    if not source_doc:
        raise ValueError("Source document not found")

    # Find all documents in the same dossier
    docs_result = await db.execute(
        select(Document.id).where(Document.dossier_id == source_doc.dossier_id)
    )
    doc_ids = [row[0] for row in docs_result.all()]

    # Find all matching name detections across the dossier that haven't been reviewed yet
    name_lower = source.entity_text.lower().strip()
    matching = await db.execute(
        select(Detection).where(
            Detection.document_id.in_(doc_ids),
            Detection.entity_type == "persoon",
            Detection.id != source.id,
            Detection.review_status.in_(["pending", "auto_accepted"]),
        )
    )

    propagated_ids: list[uuid.UUID] = []
    now = datetime.now(timezone.utc)

    for detection in matching.scalars().all():
        # Match by normalized name (case-insensitive)
        if detection.entity_text.lower().strip() != name_lower:
            continue

        detection.review_status = source.review_status
        detection.woo_article = source.woo_article
        detection.propagated_from = source.id
        detection.reviewed_at = now
        detection.reasoning = (
            f"Gepropageerd vanuit beslissing op '{source.entity_text}' "
            f"(detectie {source.id}). "
            f"Originele redenering: {source.reasoning or 'n.v.t.'}"
        )
        propagated_ids.append(detection.id)

    if propagated_ids:
        await db.commit()
        logger.info(
            "Propagated decision from detection %s to %d other detections",
            source_detection_id,
            len(propagated_ids),
        )

    return propagated_ids


async def undo_propagation(
    source_detection_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """Undo all propagated decisions from a source detection.

    Returns the number of detections that were reset.
    """
    result = await db.execute(
        update(Detection)
        .where(Detection.propagated_from == source_detection_id)
        .values(
            review_status="pending",
            propagated_from=None,
            reviewed_at=None,
            reasoning=None,
        )
        .returning(Detection.id)
    )
    count = len(result.all())
    await db.commit()

    if count:
        logger.info(
            "Undid propagation from detection %s, reset %d detections",
            source_detection_id,
            count,
        )

    return count
