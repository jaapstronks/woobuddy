"""Export engine — ZIP packaging and motivation report generation.

Produces:
1. A ZIP file containing all redacted PDFs for a dossier
2. A structured motivation report (as text, to be rendered as PDF by the frontend or a report tool)
"""

import io
import logging
import uuid
import zipfile
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import Detection, Document, Dossier, MotivationText
from app.services.pdf_engine import apply_redactions
from app.services.storage import storage

logger = logging.getLogger(__name__)


@dataclass
class MotivationEntry:
    """A single entry in the motivation report."""

    document_filename: str
    entity_text: str
    entity_type: str
    tier: str
    woo_article: str
    motivation_text: str


@dataclass
class MotivationReport:
    """Structured motivation report for a Woo decision."""

    dossier_title: str
    request_number: str
    organization: str
    entries: list[MotivationEntry] = field(default_factory=list)
    by_article: dict[str, list[MotivationEntry]] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)


async def generate_motivation_report(
    dossier_id: uuid.UUID,
    db: AsyncSession,
) -> MotivationReport:
    """Generate a structured motivation report for a dossier."""
    # Load dossier
    result = await db.execute(select(Dossier).where(Dossier.id == dossier_id))
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise ValueError(f"Dossier {dossier_id} not found")

    report = MotivationReport(
        dossier_title=dossier.title,
        request_number=dossier.request_number,
        organization=dossier.organization,
    )

    # Load all documents
    docs_result = await db.execute(
        select(Document).where(Document.dossier_id == dossier_id)
    )
    documents = {d.id: d for d in docs_result.scalars().all()}

    # Load all accepted/auto_accepted detections with motivation texts
    doc_ids = list(documents.keys())
    if not doc_ids:
        return report

    det_result = await db.execute(
        select(Detection, MotivationText)
        .outerjoin(MotivationText, MotivationText.detection_id == Detection.id)
        .where(
            Detection.document_id.in_(doc_ids),
            Detection.review_status.in_(["accepted", "auto_accepted"]),
            Detection.woo_article.is_not(None),
        )
        .order_by(Detection.document_id, Detection.tier)
    )

    tier_counts = {"1": 0, "2": 0, "3": 0}
    article_counts: dict[str, int] = {}

    for detection, motivation in det_result.all():
        doc = documents.get(detection.document_id)
        if not doc:
            continue

        article = detection.woo_article or ""
        entry = MotivationEntry(
            document_filename=doc.filename,
            entity_text=detection.entity_text[:200],
            entity_type=detection.entity_type,
            tier=detection.tier,
            woo_article=article,
            motivation_text=motivation.text if motivation else "",
        )

        report.entries.append(entry)

        if article not in report.by_article:
            report.by_article[article] = []
        report.by_article[article].append(entry)

        tier_counts[detection.tier] = tier_counts.get(detection.tier, 0) + 1
        article_counts[article] = article_counts.get(article, 0) + 1

    report.stats = {
        "total": len(report.entries),
        "tier_1": tier_counts.get("1", 0),
        "tier_2": tier_counts.get("2", 0),
        "tier_3": tier_counts.get("3", 0),
        **{f"art_{k}": v for k, v in article_counts.items()},
    }

    return report


def format_motivation_report_text(report: MotivationReport) -> str:
    """Format the motivation report as plain text."""
    lines: list[str] = []
    lines.append(f"MOTIVERINGSRAPPORT WOO-BESLUIT")
    lines.append(f"{'=' * 50}")
    lines.append(f"Dossier: {report.dossier_title}")
    lines.append(f"Kenmerk: {report.request_number}")
    lines.append(f"Organisatie: {report.organization}")
    lines.append("")

    # Stats
    lines.append("SAMENVATTING")
    lines.append(f"-" * 30)
    lines.append(f"Totaal gelakte passages: {report.stats.get('total', 0)}")
    lines.append(f"  Trap 1 (auto-gelakt): {report.stats.get('tier_1', 0)}")
    lines.append(f"  Trap 2 (bevestigd): {report.stats.get('tier_2', 0)}")
    lines.append(f"  Trap 3 (beoordeeld): {report.stats.get('tier_3', 0)}")
    lines.append("")

    # Per article
    lines.append("MOTIVERING PER WOO-ARTIKEL")
    lines.append(f"-" * 30)
    for article, entries in sorted(report.by_article.items()):
        lines.append(f"\nArtikel {article} ({len(entries)} passages)")
        lines.append(f"{'~' * 40}")

        # Use the first motivation text as representative
        if entries and entries[0].motivation_text:
            lines.append(f"\nMotivering: {entries[0].motivation_text}")

        lines.append(f"\nGelakte passages:")
        for entry in entries:
            lines.append(
                f"  - [{entry.document_filename}] "
                f"{entry.entity_type}: {entry.entity_text[:80]}"
            )

    return "\n".join(lines)


async def export_dossier_zip(
    dossier_id: uuid.UUID,
    db: AsyncSession,
) -> bytes:
    """Export a dossier as a ZIP containing redacted PDFs and motivation report."""
    # Load dossier and documents
    result = await db.execute(select(Dossier).where(Dossier.id == dossier_id))
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise ValueError(f"Dossier {dossier_id} not found")

    docs_result = await db.execute(
        select(Document).where(
            Document.dossier_id == dossier_id,
            Document.status.in_(["approved", "review"]),
        )
    )
    documents = list(docs_result.scalars().all())

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in documents:
            # Download original PDF
            pdf_bytes = await storage.download(doc.minio_key_original)

            # Get accepted redactions
            det_result = await db.execute(
                select(Detection).where(
                    Detection.document_id == doc.id,
                    Detection.review_status.in_(["accepted", "auto_accepted"]),
                    Detection.bounding_boxes.is_not(None),
                )
            )
            detections = list(det_result.scalars().all())

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

            # Apply redactions
            if redactions:
                redacted_bytes = apply_redactions(pdf_bytes, redactions)
            else:
                redacted_bytes = pdf_bytes

            # Add to ZIP
            zf.writestr(f"gelakt/{doc.filename}", redacted_bytes)

        # Generate and add motivation report
        report = await generate_motivation_report(dossier_id, db)
        report_text = format_motivation_report_text(report)
        zf.writestr("motiveringsrapport.txt", report_text)

    zip_buffer.seek(0)
    return zip_buffer.read()
