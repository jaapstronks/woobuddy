"""Public officials API routes — manage the reference list of names
that should NOT be redacted for a given dossier/organization."""

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PublicOfficialResponse
from app.db.session import get_db
from app.models.schemas import Dossier, PublicOfficial

router = APIRouter(tags=["officials"])


@router.post(
    "/api/dossiers/{dossier_id}/officials",
    response_model=list[PublicOfficialResponse],
    status_code=201,
)
async def upload_officials(
    dossier_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> list[PublicOfficial]:
    """Upload a CSV of public officials for a dossier.

    CSV format: name,role (header row expected).
    Example:
        name,role
        P.M. de Vries,Wethouder
        J. Bakker,Gemeentesecretaris
    """
    # Verify dossier exists
    result = await db.execute(select(Dossier).where(Dossier.id == dossier_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Alleen CSV-bestanden toegestaan")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # Handle BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    officials: list[PublicOfficial] = []

    for row in reader:
        name = row.get("name", row.get("naam", "")).strip()
        role = row.get("role", row.get("rol", row.get("functie", ""))).strip()

        if not name:
            continue

        official = PublicOfficial(
            dossier_id=dossier_id,
            name=name,
            role=role or None,
        )
        db.add(official)
        officials.append(official)

    await db.commit()
    for o in officials:
        await db.refresh(o)

    return officials


@router.get(
    "/api/dossiers/{dossier_id}/officials",
    response_model=list[PublicOfficialResponse],
)
async def list_officials(
    dossier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PublicOfficial]:
    """Get the public officials reference list for a dossier."""
    result = await db.execute(
        select(PublicOfficial)
        .where(PublicOfficial.dossier_id == dossier_id)
        .order_by(PublicOfficial.name)
    )
    return list(result.scalars().all())


@router.delete("/api/dossiers/{dossier_id}/officials/{official_id}", status_code=204)
async def delete_official(
    dossier_id: uuid.UUID,
    official_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a name from the public officials list."""
    result = await db.execute(
        select(PublicOfficial).where(
            PublicOfficial.id == official_id,
            PublicOfficial.dossier_id == dossier_id,
        )
    )
    official = result.scalar_one_or_none()
    if not official:
        raise HTTPException(status_code=404, detail="Functionaris niet gevonden")

    await db.delete(official)
    await db.commit()
