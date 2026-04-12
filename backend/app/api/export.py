"""Export API routes — download redacted PDFs and motivation reports."""

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.schemas import Document, Dossier
from app.services.export_engine import (
    export_dossier_zip,
    format_motivation_report_text,
    generate_motivation_report,
)
from app.services.pdf_engine import apply_redactions
from app.services.storage import storage

router = APIRouter(tags=["export"])


@router.post("/api/documents/{document_id}/redact")
async def apply_document_redactions(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply accepted redactions to a document. This is irreversible."""
    from app.models.schemas import Detection

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")

    # Get accepted detections with bounding boxes
    det_result = await db.execute(
        select(Detection).where(
            Detection.document_id == document_id,
            Detection.review_status.in_(["accepted", "auto_accepted"]),
            Detection.bounding_boxes.is_not(None),
        )
    )
    detections = list(det_result.scalars().all())

    if not detections:
        raise HTTPException(status_code=400, detail="Geen geaccepteerde detecties om te lakken")

    # Download original
    pdf_bytes = await storage.download(doc.minio_key_original)

    # Build redaction list
    redactions: list[dict] = []
    for det in detections:
        if not det.bounding_boxes:
            continue
        for bbox in det.bounding_boxes:
            redactions.append({
                "page": bbox.get("page", 0),
                "x0": bbox.get("x0", 0),
                "y0": bbox.get("y0", 0),
                "x1": bbox.get("x1", 0),
                "y1": bbox.get("y1", 0),
                "woo_article": det.woo_article or "",
            })

    # Apply redactions (irreversible — on a copy)
    redacted_bytes = apply_redactions(pdf_bytes, redactions)

    # Upload redacted version
    redacted_key = doc.minio_key_original.replace("/", "/redacted/", 1)
    await storage.upload(redacted_key, redacted_bytes)

    doc.minio_key_redacted = redacted_key
    doc.status = "approved"
    await db.commit()

    return {
        "document_id": str(document_id),
        "redaction_count": len(redactions),
        "status": "approved",
    }


@router.get("/api/documents/{document_id}/redacted-pdf")
async def download_redacted_pdf(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download the redacted version of a document."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document niet gevonden")

    if not doc.minio_key_redacted:
        raise HTTPException(status_code=404, detail="Geen gelakte versie beschikbaar")

    data = await storage.download(doc.minio_key_redacted)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gelakt_{doc.filename}"'},
    )


@router.post("/api/dossiers/{dossier_id}/export")
async def export_dossier(
    dossier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Export a dossier as a ZIP with redacted PDFs and motivation report."""
    result = await db.execute(select(Dossier).where(Dossier.id == dossier_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")

    try:
        zip_bytes = await export_dossier_zip(dossier_id, db)

        # Store ZIP in MinIO
        zip_key = f"exports/{dossier_id}/export.zip"
        await storage.upload(zip_key, zip_bytes, content_type="application/zip")

        return {
            "dossier_id": str(dossier_id),
            "status": "completed",
            "download_url": f"/api/dossiers/{dossier_id}/export/download",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export mislukt: {e}")


@router.get("/api/dossiers/{dossier_id}/export/download")
async def download_export(
    dossier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download the exported ZIP for a dossier."""
    result = await db.execute(select(Dossier).where(Dossier.id == dossier_id))
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")

    zip_key = f"exports/{dossier_id}/export.zip"
    try:
        data = await storage.download(zip_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Export niet gevonden — voer eerst export uit")

    safe_name = dossier.title.replace(" ", "_")[:50]
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="woo_export_{safe_name}.zip"'},
    )


@router.get("/api/dossiers/{dossier_id}/motivation-report")
async def download_motivation_report(
    dossier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download the motivation report for a dossier as plain text."""
    try:
        report = await generate_motivation_report(dossier_id, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="Dossier niet gevonden")

    text = format_motivation_report_text(report)

    return StreamingResponse(
        io.BytesIO(text.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="motiveringsrapport.txt"'},
    )
