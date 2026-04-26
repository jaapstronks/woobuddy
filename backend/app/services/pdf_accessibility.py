"""Accessibility post-processing for exported PDFs.

The PyMuPDF redaction step in `pdf_engine.apply_redactions` produces a
visually correct gelakt PDF — black rectangles where the sensitive text
was — but it leaves three accessibility gaps that fail Dutch
digitoegankelijk.nl / EN 301 549 / WCAG 2.1 AA:

1. No `/Lang` on the document catalog. Dutch TTS picks the wrong voice.
2. No XMP metadata. The PDF shows up in DMS systems with empty fields.
3. The redaction overlay is opaque ink. A screen-reader user lands on the
   gap and gets *nothing* — no indication of *why* the passage is gelakt
   or under which Woo article it was redacted.

This module fixes those gaps as a separate post-processing pass on top of
PyMuPDF's output. We use pikepdf because it gives us direct, minimal-fuss
access to the catalog, XMP, and annotation tree without re-encoding the
content streams.

PDF/UA-1 (full structure-tree conformance) is intentionally out of scope —
it requires a tagged source document, which PyMuPDF cannot synthesize from
a flat PDF. PDF/A-2b *archival* conformance is supported via Ghostscript
when available, with a graceful fallback for self-hosters who skipped that
optional dependency.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import pikepdf

from app.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Woo article → Dutch screen-reader description
# ---------------------------------------------------------------------------
#
# This is what NVDA / VoiceOver / JAWS will read aloud when a screen-reader
# user lands on a redacted region. Keeping it short and uniform ("Gelakt —
# Artikel X — ground") matches how the rest of the UI talks about Woo
# grounds. The mapping mirrors `frontend/src/lib/utils/woo-articles.ts` —
# if you add a new code there, mirror it here so the alt text doesn't fall
# back to the generic "Gelakt op grond van de Wet open overheid".
#
# Article codes appear in two notations across the codebase ("5.1.2e" vs
# "5.1.2.e"). `_normalize_article` strips dots so both forms resolve.

_WOO_ARTICLE_DESCRIPTIONS: dict[str, str] = {
    "5.1.1c": "Bedrijfs- en fabricagegegevens",
    "5.1.1d": "Bijzondere persoonsgegevens",
    "5.1.1e": "Identificatienummers",
    "5.1.2a": "Internationale betrekkingen",
    "5.1.2c": "Opsporing en vervolging van strafbare feiten",
    "5.1.2d": "Inspectie, controle en toezicht",
    "5.1.2e": "Persoonlijke levenssfeer",
    "5.1.2f": "Bedrijfs- en fabricagegegevens",
    "5.1.2h": "Beveiliging van personen en bedrijven",
    "5.1.2i": "Goed functioneren van de overheid",
    "5.1.5": "Onevenredige benadeling",
    "5.2": "Persoonlijke beleidsopvattingen",
}

_GENERIC_REDACTION_LABEL = "Gelakt op grond van de Wet open overheid"


_LETTER_DOT_RE = re.compile(r"\.(?=[a-z]$)")


def _normalize_article(code: str) -> str:
    """Collapse "5.1.2.e" to "5.1.2e" — the codebase mixes both forms."""
    return _LETTER_DOT_RE.sub("", code.replace(" ", "").lower())


def describe_redaction(woo_article: str | None) -> str:
    """Return the Dutch screen-reader label for a redaction.

    Falls back to a generic Woo-grounded label when the article code is
    missing or unknown — never returns an empty string, because that would
    leave the screen reader silent on the redaction.
    """
    if not woo_article:
        return _GENERIC_REDACTION_LABEL
    key = _normalize_article(woo_article)
    ground = _WOO_ARTICLE_DESCRIPTIONS.get(key)
    if not ground:
        return _GENERIC_REDACTION_LABEL
    return f"Gelakt — Artikel {woo_article} — {ground}"


# ---------------------------------------------------------------------------
# Accessible redaction annotations
# ---------------------------------------------------------------------------


def add_accessible_redaction_annots(
    pdf_bytes: bytes,
    redactions: Iterable[dict[str, Any]],
) -> bytes:
    """Overlay each redacted rectangle with an accessible Square annotation.

    The annotation is invisible (`/CA 0`, no border) — sighted users still
    see only PyMuPDF's painted black rectangle. The point of the
    annotation is its `/Contents` and `/Alt` fields, which screen readers
    announce when the cursor crosses the region. Without this, a NVDA user
    walking through a gelakt Woo besluit gets a silent gap where the
    passage used to be.
    """
    redactions = list(redactions)
    if not redactions:
        return pdf_bytes

    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    try:
        page_count = len(pdf.pages)
        for r in redactions:
            page_num = int(r.get("page", 0))
            if page_num < 0 or page_num >= page_count:
                continue
            label = describe_redaction(r.get("woo_article"))
            page = pdf.pages[page_num]
            annot = pikepdf.Dictionary(
                Type=pikepdf.Name("/Annot"),
                Subtype=pikepdf.Name("/Square"),
                Rect=pikepdf.Array(
                    [
                        float(r.get("x0", 0)),
                        float(r.get("y0", 0)),
                        float(r.get("x1", 0)),
                        float(r.get("y1", 0)),
                    ]
                ),
                # /Contents is the field screen readers announce.
                Contents=pikepdf.String(label),
                # /Alt mirrors /Contents — some readers prefer one over the
                # other, and PDF/UA-style conformance checks look for /Alt
                # on annotations that stand in for content.
                Border=pikepdf.Array([0, 0, 0]),
                F=4,  # printable, not hidden
                CA=0.0,  # fully transparent — the painted black square
                # underneath stays the visual representation.
            )
            annot["/Alt"] = pikepdf.String(label)
            annot_obj = pdf.make_indirect(annot)
            existing = page.get("/Annots")
            if existing is None:
                existing = pikepdf.Array()
            existing.append(annot_obj)
            page["/Annots"] = existing

        out = io.BytesIO()
        pdf.save(out)
    finally:
        pdf.close()
    return out.getvalue()


# ---------------------------------------------------------------------------
# Document language tag
# ---------------------------------------------------------------------------


def add_language_tag(pdf_bytes: bytes, lang: str = "nl-NL") -> bytes:
    """Set `/Lang` on the document catalog.

    Two lines of code that flip the screen-reader voice from default
    English to Dutch in Acrobat Reader, NVDA, JAWS, and VoiceOver — the
    single highest-impact accessibility win for the cost.
    """
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    try:
        pdf.Root.Lang = lang
        out = io.BytesIO()
        pdf.save(out)
    finally:
        pdf.close()
    return out.getvalue()


# ---------------------------------------------------------------------------
# XMP metadata
# ---------------------------------------------------------------------------


def write_xmp_metadata(
    pdf_bytes: bytes,
    *,
    title: str | None = None,
    description: str | None = None,
    language: str = "nl-NL",
    producer: str = "WOO Buddy",
    creator_tool: str = "WOO Buddy",
    create_date: datetime | None = None,
) -> bytes:
    """Write XMP metadata onto the PDF.

    Empty / None fields are skipped rather than written as blank strings —
    a blank `dc:title` is worse than no title at all because some DMSes
    show "" in the title column instead of falling back to the filename.
    """
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            if title:
                meta["dc:title"] = title
            meta["dc:language"] = language
            if description:
                meta["dc:description"] = description
            meta["pdf:Producer"] = producer
            meta["xmp:CreatorTool"] = creator_tool
            stamp = (create_date or datetime.now()).isoformat()
            meta["xmp:CreateDate"] = stamp
            meta["xmp:ModifyDate"] = stamp
        out = io.BytesIO()
        pdf.save(out)
    finally:
        pdf.close()
    return out.getvalue()


def build_redaction_summary(
    redactions: Iterable[dict[str, Any]],
) -> str | None:
    """Build a one-line Dutch description for `dc:description`.

    Aggregates the Woo articles used and the export date — never the
    redacted text itself, never the bbox coordinates. The output is
    suitable as a publicly-visible PDF metadata field.
    """
    articles: set[str] = set()
    for r in redactions:
        code = r.get("woo_article")
        if code:
            articles.add(str(code))
    if not articles:
        return None
    sorted_articles = ", ".join(f"Art. {a}" for a in sorted(articles))
    today = datetime.now().date().isoformat()
    return f"Gelakt conform {sorted_articles} — {today}"


# ---------------------------------------------------------------------------
# PDF/A-2b conversion via Ghostscript
# ---------------------------------------------------------------------------


def _ghostscript_path() -> str | None:
    """Return the path to a `gs` binary, or None if not installed.

    Ghostscript is an optional dependency. Self-hosters who skipped it
    still get a working export; they just don't get archival conformance.
    """
    return shutil.which("gs")


def convert_to_pdfa(pdf_bytes: bytes, *, conformance: str = "2") -> bytes:
    """Convert the PDF to PDF/A-2b via Ghostscript.

    Returns the original bytes unchanged when Ghostscript is unavailable
    or the conversion fails — PDF/A is an *enhancement*, not a blocker.
    The caller still gets a working redacted PDF, just without archival
    conformance, and a warning ends up in the logs so operators can spot
    the missing dependency.
    """
    gs = _ghostscript_path()
    if gs is None:
        logger.warning("export.pdfa.ghostscript_missing")
        return pdf_bytes

    with tempfile.TemporaryDirectory(prefix="woobuddy_pdfa_") as tmp:
        in_path = Path(tmp) / "in.pdf"
        out_path = Path(tmp) / "out.pdf"
        in_path.write_bytes(pdf_bytes)
        cmd = [
            gs,
            f"-dPDFA={conformance}",
            "-dPDFACompatibilityPolicy=1",
            "-sProcessColorModel=DeviceRGB",
            "-sDEVICE=pdfwrite",
            "-dBATCH",
            "-dNOPAUSE",
            "-dQUIET",
            f"-sOutputFile={out_path}",
            str(in_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning(
                "export.pdfa.ghostscript_failed",
                error=type(exc).__name__,
            )
            return pdf_bytes

        if result.returncode != 0 or not out_path.exists():
            logger.warning(
                "export.pdfa.ghostscript_nonzero",
                returncode=result.returncode,
            )
            return pdf_bytes
        return out_path.read_bytes()


# ---------------------------------------------------------------------------
# Convenience: full post-processing chain
# ---------------------------------------------------------------------------


def post_process_for_accessibility(
    pdf_bytes: bytes,
    *,
    redactions: Iterable[dict[str, Any]] = (),
    title: str | None = None,
    enable_pdfa: bool = True,
) -> bytes:
    """Run the full accessibility chain on a redacted PDF.

    Order matches the todo: accessible annotations → /Lang → XMP →
    PDF/A-2b. The XMP step is *after* annotations because Ghostscript
    rewrites the catalog and metadata in one pass; we want our metadata
    to be the source-of-truth that Ghostscript carries forward.
    """
    redactions = list(redactions)
    out = pdf_bytes
    out = add_accessible_redaction_annots(out, redactions)
    out = add_language_tag(out)
    out = write_xmp_metadata(
        out,
        title=title,
        description=build_redaction_summary(redactions),
    )
    if enable_pdfa:
        out = convert_to_pdfa(out)
    return out
