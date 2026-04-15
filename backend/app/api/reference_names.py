"""Per-document reference names (#17).

A tiny CRUD surface that lets a reviewer maintain a list of names that
should NOT be redacted in a specific document — typically the members of
a college van B&W, a raad, or another public body whose names the
reviewer knows ahead of time. The analyze pipeline consumes this list on
every `/api/analyze` call and flips any matching Tier 2 `persoon`
detection to `review_status="rejected"` with `source="reference_list"`.

Client-first note: the stored `display_name` is a reviewer-provided
label, not PDF content — the user typed it in a panel, nothing was
extracted. That is why it is compatible with the client-first
architecture even though it's persisted as plain text.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_document_or_404
from app.api.schemas import ReferenceNameCreate, ReferenceNameResponse
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import DocumentReferenceName
from app.security import verify_proxy_secret
from app.services.name_engine import normalize_reference_name

logger = get_logger(__name__)

router = APIRouter(
    tags=["reference-names"],
    dependencies=[Depends(verify_proxy_secret)],
)


@router.get(
    "/api/documents/{document_id}/reference-names",
    response_model=list[ReferenceNameResponse],
)
async def list_reference_names(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[DocumentReferenceName]:
    """Return every reference name for a document, ordered by creation time."""
    await get_document_or_404(document_id, db)
    result = await db.execute(
        select(DocumentReferenceName)
        .where(DocumentReferenceName.document_id == document_id)
        .order_by(DocumentReferenceName.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/api/documents/{document_id}/reference-names",
    response_model=ReferenceNameResponse,
    status_code=201,
)
async def create_reference_name(
    document_id: uuid.UUID,
    data: ReferenceNameCreate,
    db: AsyncSession = Depends(get_db),
) -> DocumentReferenceName:
    """Add one reference name.

    The server normalizes the display name — lowercase + strip
    diacritics + collapse whitespace, keeping tussenvoegsels — before
    writing. Re-adding the same name (even with a different casing or
    diacritics) returns 409 Conflict rather than silently creating a
    duplicate: the composite unique index on (document_id, normalized_name)
    catches it, and surfacing the conflict gives the UI a chance to
    explain.
    """
    await get_document_or_404(document_id, db)

    display = (data.display_name or "").strip()
    if not display:
        raise HTTPException(status_code=400, detail="Naam mag niet leeg zijn.")
    if len(display) > 200:
        raise HTTPException(status_code=400, detail="Naam is te lang (maximaal 200 tekens).")

    normalized = normalize_reference_name(display)
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="Naam bevat geen bruikbare tekens.",
        )

    row = DocumentReferenceName(
        document_id=document_id,
        display_name=display,
        normalized_name=normalized,
        role_hint=data.role_hint,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Deze naam staat al op de lijst voor dit document.",
        ) from None
    await db.refresh(row)

    logger.info(
        "reference_name.created",
        document_id=str(document_id),
        reference_name_id=str(row.id),
    )
    return row


@router.delete(
    "/api/documents/{document_id}/reference-names/{name_id}",
    status_code=204,
)
async def delete_reference_name(
    document_id: uuid.UUID,
    name_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove one reference name.

    Returns 204 even when the row is already gone — idempotent delete is
    friendlier for an undo/redo flow where the client may retry after a
    transient failure.
    """
    await get_document_or_404(document_id, db)
    result = await db.execute(
        select(DocumentReferenceName).where(
            DocumentReferenceName.id == name_id,
            DocumentReferenceName.document_id == document_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return
    await db.delete(row)
    await db.commit()
    logger.info(
        "reference_name.deleted",
        document_id=str(document_id),
        reference_name_id=str(name_id),
    )
