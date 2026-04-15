"""Page-completeness routes (#10).

A minimal per-page status tracker so a reviewer can mark individual pages
as `complete` / `in_progress` / `flagged`. Rows are created lazily — a
missing row means `unreviewed`, which keeps the table small for long
documents where only a handful of pages get manually touched.

Client-first: this endpoint stores status metadata only. No text, no
detections, no content. The reviewer identifier is free text for now
(auth lands in #24).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_document_or_404
from app.api.schemas import PageReviewResponse, PageReviewUpsert
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import PageReview
from app.security import verify_proxy_secret

logger = get_logger(__name__)

router = APIRouter(
    tags=["page-reviews"],
    dependencies=[Depends(verify_proxy_secret)],
)


@router.get(
    "/api/documents/{document_id}/page-reviews",
    response_model=list[PageReviewResponse],
)
async def list_page_reviews(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PageReview]:
    """Return every PageReview row for a document.

    Missing pages are `unreviewed` — the client assumes that for any page
    not returned here, so we don't need to materialize a row per page.
    """
    await get_document_or_404(document_id, db)
    result = await db.execute(
        select(PageReview)
        .where(PageReview.document_id == document_id)
        .order_by(PageReview.page_number)
    )
    return list(result.scalars().all())


@router.put(
    "/api/documents/{document_id}/page-reviews/{page_number}",
    response_model=PageReviewResponse,
)
async def upsert_page_review(
    document_id: uuid.UUID,
    page_number: int,
    data: PageReviewUpsert,
    db: AsyncSession = Depends(get_db),
) -> PageReview:
    """Set the status for a single page (idempotent upsert).

    The unique (document_id, page_number) constraint lets us use Postgres's
    `ON CONFLICT` clause so repeated writes from the client (e.g. toggling
    between complete and flagged) stay on a single row.
    """
    doc = await get_document_or_404(document_id, db)
    if page_number < 0 or page_number >= doc.page_count:
        raise HTTPException(
            status_code=400,
            detail="Paginanummer valt buiten dit document.",
        )

    stmt = (
        pg_insert(PageReview)
        .values(
            document_id=document_id,
            page_number=page_number,
            status=data.status,
            reviewer_id=data.reviewer_id,
        )
        .on_conflict_do_update(
            constraint="uq_page_reviews_doc_page",
            set_={
                "status": data.status,
                "reviewer_id": data.reviewer_id,
            },
        )
        .returning(PageReview)
    )
    result = await db.execute(stmt)
    await db.commit()
    row = result.scalar_one()
    # Refresh so server defaults (updated_at from onupdate/server_default)
    # are materialized on the returned instance.
    await db.refresh(row)
    logger.info(
        "page_review.upserted",
        document_id=str(document_id),
        page_number=page_number,
        status=data.status,
    )
    return row
