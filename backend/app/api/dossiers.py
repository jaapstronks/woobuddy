import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import DossierCreate, DossierResponse, DossierStats, DossierWithStatsResponse
from app.db.session import get_db
from app.models.schemas import Detection, Dossier

router = APIRouter(prefix="/api/dossiers", tags=["dossiers"])


@router.post("", response_model=DossierResponse, status_code=201)
async def create_dossier(data: DossierCreate, db: AsyncSession = Depends(get_db)) -> Dossier:
    dossier = Dossier(**data.model_dump())
    db.add(dossier)
    await db.commit()
    await db.refresh(dossier)
    return dossier


@router.get("", response_model=list[DossierResponse])
async def list_dossiers(db: AsyncSession = Depends(get_db)) -> list[Dossier]:
    result = await db.execute(select(Dossier).order_by(Dossier.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{dossier_id}", response_model=DossierWithStatsResponse)
async def get_dossier(
    dossier_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DossierWithStatsResponse:
    result = await db.execute(
        select(Dossier).where(Dossier.id == dossier_id).options(selectinload(Dossier.documents))
    )
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")

    # Count documents
    doc_count = len(dossier.documents)

    # Gather detection stats across all documents in the dossier
    doc_ids = [d.id for d in dossier.documents]
    stats = DossierStats()
    if doc_ids:
        # By tier
        tier_result = await db.execute(
            select(Detection.tier, func.count())
            .where(Detection.document_id.in_(doc_ids))
            .group_by(Detection.tier)
        )
        stats.by_tier = {row[0]: row[1] for row in tier_result.all()}

        # By review status
        status_result = await db.execute(
            select(Detection.review_status, func.count())
            .where(Detection.document_id.in_(doc_ids))
            .group_by(Detection.review_status)
        )
        stats.by_status = {row[0]: row[1] for row in status_result.all()}
        stats.total = sum(stats.by_tier.values())

    return DossierWithStatsResponse(
        **DossierResponse.model_validate(dossier).model_dump(),
        document_count=doc_count,
        detection_counts=stats,
    )
