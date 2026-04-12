import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DocumentRegister, DocumentResponse
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.schemas import Document
from app.security import verify_proxy_secret

logger = get_logger(__name__)

router = APIRouter(tags=["documents"], dependencies=[Depends(verify_proxy_secret)])


def _sanitize_filename(filename: str) -> str:
    """Strip path components and limit to safe characters."""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = re.sub(r"[^\w.\-]", "_", name)
    if len(name) > 200:
        stem, _, ext = name.rpartition(".")
        name = f"{stem[:200 - len(ext) - 1]}.{ext}" if ext else stem[:200]
    return name or "document.pdf"


async def _get_document_or_404(
    document_id: uuid.UUID, db: AsyncSession
) -> Document:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")
    return doc


def _is_five_year_warning(doc: Document) -> bool:
    """Check if document date is older than 5 years (Art. 5.3 Woo)."""
    if not doc.document_date:
        return False
    now = datetime.now(UTC)
    if doc.document_date.tzinfo is None:
        doc_date = doc.document_date.replace(tzinfo=UTC)
    else:
        doc_date = doc.document_date
    age_days = (now - doc_date).days
    return age_days > 5 * 365


def _doc_to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse.model_validate(doc, from_attributes=True).model_copy(
        update={"five_year_warning": _is_five_year_warning(doc)}
    )


@router.post(
    "/api/documents",
    response_model=DocumentResponse,
    status_code=201,
)
async def register_document(
    data: DocumentRegister,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Register a document without uploading the PDF (client-first architecture).

    The PDF stays in the user's browser. Only metadata is stored.
    """
    safe_name = _sanitize_filename(data.filename)
    doc = Document(
        filename=safe_name,
        page_count=data.page_count,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    logger.info(
        "document.registered",
        document_id=str(doc.id),
        page_count=doc.page_count,
    )
    return _doc_to_response(doc)


@router.get("/api/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DocumentResponse:
    doc = await _get_document_or_404(document_id, db)
    return _doc_to_response(doc)
