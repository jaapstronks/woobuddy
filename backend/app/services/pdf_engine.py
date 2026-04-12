"""PDF text extraction and redaction via PyMuPDF.

Extraction produces text spans with bounding box coordinates so detected
entities can be mapped back to visual positions in the PDF.

Redaction uses PyMuPDF's built-in redaction annotations and is irreversible —
always work on a copy.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Common Dutch date patterns for the five-year rule
_DATE_PATTERNS = [
    # "15 maart 2024", "1 januari 2023"
    re.compile(
        r"\b(\d{1,2})\s+(januari|februari|maart|april|mei|juni|juli|augustus|"
        r"september|oktober|november|december)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    # "15-03-2024", "01/01/2023"
    re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b"),
    # "2024-03-15" (ISO)
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
]

_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}


@dataclass
class TextSpan:
    """A single text span extracted from a PDF page."""

    text: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    block_no: int = 0
    line_no: int = 0


@dataclass
class PageText:
    """All text from a single PDF page."""

    page_number: int
    full_text: str
    spans: list[TextSpan] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result of extracting text from an entire PDF."""

    pages: list[PageText] = field(default_factory=list)
    page_count: int = 0
    document_date: datetime | None = None
    full_text: str = ""


def extract_text(pdf_bytes: bytes) -> ExtractionResult:
    """Extract all text spans with bounding boxes from a PDF.

    Uses page.get_text("dict") for character-level position data.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result = ExtractionResult(page_count=len(doc))
    all_text_parts: list[str] = []
    earliest_date: datetime | None = None

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_dict = page.get_text("dict")
        page_spans: list[TextSpan] = []
        page_text_parts: list[str] = []

        for block_no, block in enumerate(page_dict.get("blocks", [])):
            if block.get("type") != 0:  # text block only
                continue
            for line_no, line in enumerate(block.get("lines", [])):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    page_spans.append(
                        TextSpan(
                            text=text,
                            page=page_idx,
                            x0=bbox[0],
                            y0=bbox[1],
                            x1=bbox[2],
                            y1=bbox[3],
                            block_no=block_no,
                            line_no=line_no,
                        )
                    )
                    page_text_parts.append(text)

        page_full_text = " ".join(page_text_parts)
        result.pages.append(
            PageText(
                page_number=page_idx,
                full_text=page_full_text,
                spans=page_spans,
            )
        )
        all_text_parts.append(page_full_text)

        # Try to find a document date on this page
        if earliest_date is None:
            found = _find_date_in_text(page_full_text)
            if found:
                earliest_date = found

    doc.close()
    result.full_text = "\n\n".join(all_text_parts)
    result.document_date = earliest_date
    return result


def _find_date_in_text(text: str) -> datetime | None:
    """Find the first plausible document date in text."""
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            groups = match.groups()
            if len(groups) == 3 and isinstance(groups[1], str) and groups[1].lower() in _DUTCH_MONTHS:
                day, month_str, year = int(groups[0]), _DUTCH_MONTHS[groups[1].lower()], int(groups[2])
            elif len(groups) == 3 and len(groups[0]) == 4:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            if 1900 < year < 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                return datetime(year, month, day)
        except (ValueError, IndexError):
            continue
    return None


def find_span_for_text(
    pages: list[PageText], search_text: str, page_hint: int | None = None
) -> list[dict]:
    """Find bounding boxes for a text string in the extracted spans.

    Returns a list of {"page": int, "x0": float, "y0": float, "x1": float, "y1": float}.
    Uses substring matching — the search text may span multiple spans.
    """
    results: list[dict] = []
    search_lower = search_text.lower().strip()
    if not search_lower:
        return results

    pages_to_check = (
        [pages[page_hint]] if page_hint is not None and 0 <= page_hint < len(pages) else pages
    )

    for page_text in pages_to_check:
        # First try exact span match
        for span in page_text.spans:
            if search_lower in span.text.lower():
                results.append({
                    "page": span.page,
                    "x0": span.x0,
                    "y0": span.y0,
                    "x1": span.x1,
                    "y1": span.y1,
                })

        # If no exact match, try merging adjacent spans
        if not results:
            for i, span in enumerate(page_text.spans):
                merged = span.text
                merged_bbox = [span.x0, span.y0, span.x1, span.y1]
                for j in range(i + 1, min(i + 10, len(page_text.spans))):
                    merged += " " + page_text.spans[j].text
                    merged_bbox[2] = max(merged_bbox[2], page_text.spans[j].x1)
                    merged_bbox[3] = max(merged_bbox[3], page_text.spans[j].y1)
                    if search_lower in merged.lower():
                        results.append({
                            "page": span.page,
                            "x0": merged_bbox[0],
                            "y0": merged_bbox[1],
                            "x1": merged_bbox[2],
                            "y1": merged_bbox[3],
                        })
                        break

        if results:
            break  # found on this page, stop

    return results


def apply_redactions(
    pdf_bytes: bytes,
    redactions: list[dict],
    redaction_color: tuple[float, float, float] = (0, 0, 0),
) -> bytes:
    """Apply redaction annotations to a PDF and return the modified bytes.

    Each item in `redactions` should have:
        page: int
        x0, y0, x1, y1: float (bounding box)
        woo_article: str (optional, shown as overlay text)

    This operation is IRREVERSIBLE. Always call on a copy, never the original.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for r in redactions:
        page_num = r["page"]
        if page_num < 0 or page_num >= len(doc):
            continue
        page = doc[page_num]
        rect = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        article_text = r.get("woo_article", "")

        page.add_redact_annot(
            rect,
            text=article_text,
            fontsize=6,
            fill=redaction_color,
            text_color=(1, 1, 1),  # white text on dark background
        )

    for page in doc:
        page.apply_redactions()

    result = doc.tobytes()
    doc.close()
    return result


def get_page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count
