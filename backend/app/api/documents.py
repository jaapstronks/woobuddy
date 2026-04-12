import io
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DocumentResponse
from app.db.session import get_db
from app.models.schemas import Document, Dossier
from app.services.storage import storage

router = APIRouter(tags=["documents"])

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


def _sanitize_filename(filename: str) -> str:
    """Strip path components and limit to safe characters."""
    # Take only the basename (no directory traversal)
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Replace unsafe characters with underscores
    name = re.sub(r"[^\w.\-]", "_", name)
    # Limit length (preserve extension)
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


@router.post(
    "/api/dossiers/{dossier_id}/documents",
    response_model=list[DocumentResponse],
    status_code=201,
)
async def upload_documents(
    dossier_id: uuid.UUID,
    files: list[UploadFile],
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    # Verify dossier exists
    result = await db.execute(select(Dossier).where(Dossier.id == dossier_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")

    documents: list[Document] = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Alleen PDF-bestanden toegestaan: {file.filename}",
            )

        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            max_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"Bestand te groot (max {max_mb} MB): {file.filename}",
            )

        safe_name = _sanitize_filename(file.filename)
        minio_key = f"{dossier_id}/{uuid.uuid4()}/{safe_name}"

        await storage.upload(minio_key, content, content_type="application/pdf")

        doc = Document(
            dossier_id=dossier_id,
            filename=safe_name,
            minio_key_original=minio_key,
        )
        db.add(doc)
        documents.append(doc)

    await db.commit()
    for doc in documents:
        await db.refresh(doc)

    return documents


@router.get("/api/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Document:
    return await _get_document_or_404(document_id, db)


@router.get("/api/documents/{document_id}/pdf")
async def stream_document_pdf(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    doc = await _get_document_or_404(document_id, db)

    data = await storage.download(doc.minio_key_original)

    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )
