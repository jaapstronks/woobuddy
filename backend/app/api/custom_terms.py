"""Per-document custom wordlist API (#21 — "eigen zoektermen").

CRUD surface that mirrors the reference-names API (#17): both are
per-document reviewer labels, both short-circuit the generic detection
pipeline, both are opt-in by reviewer intent. They differ in direction
— reference names tell the pipeline *not* to redact, custom terms tell
the pipeline *to* redact — and deserve separate UI, but the HTTP shape
is deliberately identical.

Client-first note: the stored `term` is a reviewer-typed label, not PDF
content. The reviewer typed "Project Apollo" into a panel; nothing was
extracted. That is why persisting the string as plain text is
compatible with the client-first architecture even though it would
look like content at a glance.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_document_or_404
from app.api.schemas import CustomTermCreate, CustomTermResponse
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import DocumentCustomTerm
from app.security import verify_proxy_secret
from app.services.custom_term_matcher import normalize_term

logger = get_logger(__name__)

router = APIRouter(
    tags=["custom-terms"],
    dependencies=[Depends(verify_proxy_secret)],
)


@router.get(
    "/api/documents/{document_id}/custom-terms",
    response_model=list[CustomTermResponse],
)
async def list_custom_terms(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[DocumentCustomTerm]:
    """Return every custom term for a document, ordered by creation time."""
    await get_document_or_404(document_id, db)
    result = await db.execute(
        select(DocumentCustomTerm)
        .where(DocumentCustomTerm.document_id == document_id)
        .order_by(DocumentCustomTerm.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/api/documents/{document_id}/custom-terms",
    response_model=CustomTermResponse,
    status_code=201,
)
async def create_custom_term(
    document_id: uuid.UUID,
    data: CustomTermCreate,
    db: AsyncSession = Depends(get_db),
) -> DocumentCustomTerm:
    """Add one custom term to the document's wordlist.

    The server normalizes the term (lowercase + collapse whitespace,
    diacritics preserved) before writing, so "Project Apollo" and
    "project   apollo" hash to the same row. A duplicate returns 409
    Conflict — the composite unique index on
    (document_id, normalized_term, match_mode) catches it, and
    surfacing the conflict gives the UI a chance to explain.
    """
    await get_document_or_404(document_id, db)

    raw = (data.term or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Zoekterm mag niet leeg zijn.")
    if len(raw) > 200:
        raise HTTPException(
            status_code=400,
            detail="Zoekterm is te lang (maximaal 200 tekens).",
        )

    normalized = normalize_term(raw)
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="Zoekterm bevat geen bruikbare tekens.",
        )

    row = DocumentCustomTerm(
        document_id=document_id,
        term=raw,
        normalized_term=normalized,
        match_mode=data.match_mode,
        woo_article=data.woo_article,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Deze zoekterm staat al op de lijst voor dit document.",
        ) from None
    await db.refresh(row)

    logger.info(
        "custom_term.created",
        document_id=str(document_id),
        custom_term_id=str(row.id),
    )
    return row


@router.delete(
    "/api/documents/{document_id}/custom-terms/{term_id}",
    status_code=204,
)
async def delete_custom_term(
    document_id: uuid.UUID,
    term_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove one custom term. Idempotent — a missing row returns 204.

    Idempotency matters for the undo stack: if an undo retries a
    delete after a transient failure, the second call must not 404.
    """
    await get_document_or_404(document_id, db)
    result = await db.execute(
        select(DocumentCustomTerm).where(
            DocumentCustomTerm.id == term_id,
            DocumentCustomTerm.document_id == document_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return
    await db.delete(row)
    await db.commit()
    logger.info(
        "custom_term.deleted",
        document_id=str(document_id),
        custom_term_id=str(term_id),
    )
