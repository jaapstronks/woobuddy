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
a flat PDF.

PDF/A-2b archival conformance is out of scope too, deliberately (#67,
decided 2026-09-02). It used to be attempted via a Ghostscript subprocess,
which (a) was never installed in the api image or in CI, so production
never produced PDF/A, and (b) rewrote the catalog on the machines that
*did* have it — stripping the `/Lang` tag that is the single biggest
accessibility win here. It also needed a tempfile, which contradicts the
export contract that document bytes never touch disk. Everything this
module does now happens in memory. Reviving PDF/A is allowed, but only
with a real archival requirement behind it and without a disk round-trip.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from datetime import datetime
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


def _pdf_rect_from_viewer_box(
    page: pikepdf.Page,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[float, float, float, float]:
    """Map a viewer-space box onto a PDF `/Rect` in user space.

    The redaction boxes travel through the app in *viewer* space: origin
    top-left, y growing downward, rotation already applied. That is what
    pdf.js hands the client and what `pdf_engine.apply_redactions`
    derotates for PyMuPDF (whose annotation API expects *unrotated* page
    coordinates). A PDF `/Rect`, however, is user space:
    origin bottom-left, y growing upward, rotation *not* applied. Writing
    the viewer values straight into `/Rect` mirrors every annotation
    vertically, which is what this codebase did until #67 — the black box
    landed correctly (PyMuPDF did the transform) while the screen-reader
    annotation describing it sat on the opposite side of the page.

    The four `/Rotate` cases are spelled out rather than folded into a
    matrix because each one is a corner correspondence that can be checked
    by hand: for `/Rotate 90` (page displayed a quarter turn clockwise)
    the viewer's top-left corner is the unrotated page's bottom-left, so
    the viewer's x axis runs along the page's y axis and vice versa.
    """
    # CropBox (pikepdf falls back to MediaBox when absent) rather than
    # MediaBox, because that is the box pdf.js builds its viewport from —
    # so it is the box the reviewer's coordinates are relative to.
    box = page.cropbox
    llx, lly = float(box[0]), float(box[1])
    urx, ury = float(box[2]), float(box[3])
    raw_rotate = page.obj.get("/Rotate")
    rotate = (int(raw_rotate) if raw_rotate is not None else 0) % 360

    if rotate == 90:
        return (llx + y0, lly + x0, llx + y1, lly + x1)
    if rotate == 180:
        return (urx - x1, lly + y0, urx - x0, lly + y1)
    if rotate == 270:
        return (urx - y1, ury - x1, urx - y0, ury - x0)
    # rotate == 0, and anything not a multiple of 90 (invalid per spec).
    return (llx + x0, ury - y1, llx + x1, ury - y0)


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
        skipped = 0
        for r in redactions:
            page_num = int(r.get("page", 0))
            if page_num < 0 or page_num >= page_count:
                # Same out-of-range case `apply_redactions` counts; log it
                # here too so a mismatch between the two passes is visible
                # instead of silent (#66/5).
                skipped += 1
                continue
            label = describe_redaction(r.get("woo_article"))
            page = pdf.pages[page_num]
            rect = _pdf_rect_from_viewer_box(
                page,
                float(r.get("x0", 0)),
                float(r.get("y0", 0)),
                float(r.get("x1", 0)),
                float(r.get("y1", 0)),
            )
            annot = pikepdf.Dictionary(
                Type=pikepdf.Name("/Annot"),
                Subtype=pikepdf.Name("/Square"),
                Rect=pikepdf.Array(list(rect)),
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

        if skipped:
            logger.warning(
                "export.annots_out_of_range",
                skipped=skipped,
                page_count=page_count,
            )

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
# Convenience: full post-processing chain
# ---------------------------------------------------------------------------


def post_process_for_accessibility(
    pdf_bytes: bytes,
    *,
    redactions: Iterable[dict[str, Any]] = (),
    title: str | None = None,
) -> bytes:
    """Run the full accessibility chain on a redacted PDF.

    Accessible annotations → /Lang → XMP, three pikepdf round-trips, all
    in memory. `/Lang` lands last of the two catalog writers on purpose:
    `write_xmp_metadata` only touches the metadata stream, so the tag it
    sets survives. This is CPU-bound work — callers on the event loop
    must hand it to a worker thread (see `api/export.py`).
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
    return out
