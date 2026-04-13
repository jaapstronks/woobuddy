"""PDF text extraction and redaction via PyMuPDF.

Extraction produces text spans with bounding box coordinates so detected
entities can be mapped back to visual positions in the PDF.

Redaction uses PyMuPDF's built-in redaction annotations and is irreversible —
always work on a copy.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

import fitz  # PyMuPDF

from app.logging_config import get_logger

logger = get_logger(__name__)


class PdfValidationError(ValueError):
    """Raised when PyMuPDF cannot parse the provided bytes as a PDF.

    The message is intentionally generic — callers should NOT echo the
    underlying fitz exception text to clients, because on some versions it
    can contain fragments of the document's raw stream.
    """


def _open_pdf_safe(pdf_bytes: bytes) -> "fitz.Document":
    """Open a PDF stream, converting fitz errors into `PdfValidationError`.

    Keeping this wrapper in one place means every call site routes invalid
    PDFs through the same clean error path — no fitz exception text ever
    reaches an HTTP response.
    """
    try:
        return fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as cause:  # pragma: no cover - defensive; fitz raises many types
        logger.warning("pdf.invalid_stream", size=len(pdf_bytes))
        raise PdfValidationError("Ongeldig PDF-bestand") from cause


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
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
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
    doc = _open_pdf_safe(pdf_bytes)
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
            if (
                len(groups) == 3
                and isinstance(groups[1], str)
                and groups[1].lower() in _DUTCH_MONTHS
            ):
                day = int(groups[0])
                month = _DUTCH_MONTHS[groups[1].lower()]
                year = int(groups[2])
            elif len(groups) == 3 and len(groups[0]) == 4:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            if 1900 < year < 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                return datetime(year, month, day)
        except (ValueError, IndexError):
            continue
    return None


def extraction_from_client_data(pages_data: list[dict]) -> ExtractionResult:
    """Build an ExtractionResult from client-provided text extraction data.

    The client extracts text via pdf.js and sends it as JSON. This function
    converts that into the same ExtractionResult the pipeline already expects,
    so run_pipeline() and detect_all() require zero changes.
    """
    result = ExtractionResult(page_count=len(pages_data))
    all_text_parts: list[str] = []
    earliest_date: datetime | None = None

    for page_data in pages_data:
        page_num = page_data.get("page_number", 0)
        full_text = page_data.get("full_text", "")
        spans = [
            TextSpan(
                text=item["text"],
                page=page_num,
                x0=item["x0"],
                y0=item["y0"],
                x1=item["x1"],
                y1=item["y1"],
            )
            for item in page_data.get("text_items", [])
        ]
        result.pages.append(PageText(page_number=page_num, full_text=full_text, spans=spans))
        all_text_parts.append(full_text)

        if earliest_date is None:
            found = _find_date_in_text(full_text)
            if found:
                earliest_date = found

    result.full_text = "\n\n".join(all_text_parts)
    result.document_date = earliest_date
    return result


# y0 tolerance for considering two text items to be on the same visual
# line. 3 PDF points is ~1 line-height of baseline jitter — wider than
# that and we're looking at the next line.
_SAME_LINE_TOL = 3.0


def _is_word_boundary_match(haystack: str, needle: str) -> bool:
    """True if `needle` appears in `haystack` with non-alphanumeric
    characters (or the string edges) on both sides.

    This prevents "Vries" from matching inside "Vriesland" — the kind
    of false positive that causes the bbox of a person detection to
    snap onto an unrelated word.
    """
    if not needle:
        return False
    n = len(needle)
    idx = 0
    while True:
        idx = haystack.find(needle, idx)
        if idx == -1:
            return False
        left_ok = idx == 0 or not haystack[idx - 1].isalnum()
        right = idx + n
        right_ok = right == len(haystack) or not haystack[right].isalnum()
        if left_ok and right_ok:
            return True
        idx += 1


def find_span_for_text(
    pages: list[PageText], search_text: str, page_hint: int | None = None
) -> list[dict]:
    """Find bounding boxes for a text string in the extracted text items.

    Matching rules (deliberately strict to avoid paragraph-sized bboxes
    when an entity matches loosely — see the Tier 2 false-positive bug
    where Deduce hits were snapping onto whole paragraphs):

    - **Word-boundary check**: "Vries" does not match inside "Vriesland".
    - **Single-line merges only**: when a match spans multiple text
      items, only items on the same visual line (y0 within
      `_SAME_LINE_TOL`) are combined. A bbox never spans multiple lines.
    - **Anchored merge start**: a merged match must begin inside the
      first item of the merge (either the first word of the search
      text lines up with a word boundary in that item, or the whole
      item is itself a prefix of the search text). This ensures the
      resulting bbox starts where the entity actually begins, rather
      than at some unrelated earlier item.
    """
    results: list[dict] = []
    search_lower = search_text.lower().strip()
    if not search_lower:
        return results

    pages_to_check = (
        [pages[page_hint]] if page_hint is not None and 0 <= page_hint < len(pages) else pages
    )

    first_word = search_lower.split(" ", 1)[0] if " " in search_lower else search_lower

    for page_text in pages_to_check:
        # 1) Single-item match — the common case.
        for span in page_text.spans:
            if _is_word_boundary_match(span.text.lower(), search_lower):
                results.append(
                    {
                        "page": span.page,
                        "x0": span.x0,
                        "y0": span.y0,
                        "x1": span.x1,
                        "y1": span.y1,
                    }
                )

        # 2) Multi-item same-line merge, anchored at an item that
        #    plausibly starts the match.
        if not results:
            spans = page_text.spans
            for i, start in enumerate(spans):
                start_lower = start.text.lower()

                # Only consider starting items that contribute the start
                # of the match. Two ways to qualify:
                #   (a) the first word of the search text appears at a
                #       word boundary inside this item ("...Jan" or
                #       "Jan" itself when search is "Jan de Vries");
                #   (b) the item's whole text is a prefix of the search
                #       text (covers no-space joins for split tokens).
                if not (
                    _is_word_boundary_match(start_lower, first_word)
                    or search_lower.startswith(start_lower)
                ):
                    continue

                merged_parts: list[str] = [start.text]
                x0, y0, x1, y1 = start.x0, start.y0, start.x1, start.y1

                for j in range(i + 1, min(i + 12, len(spans))):
                    nxt = spans[j]
                    # Same-line guard — never cross a line break.
                    if abs(nxt.y0 - start.y0) > _SAME_LINE_TOL:
                        break
                    merged_parts.append(nxt.text)
                    x0 = min(x0, nxt.x0)
                    x1 = max(x1, nxt.x1)
                    y0 = min(y0, nxt.y0)
                    y1 = max(y1, nxt.y1)

                    with_space = " ".join(merged_parts).lower()
                    without_space = "".join(merged_parts).lower()

                    if _is_word_boundary_match(with_space, search_lower) or _is_word_boundary_match(
                        without_space, search_lower
                    ):
                        results.append(
                            {
                                "page": start.page,
                                "x0": x0,
                                "y0": y0,
                                "x1": x1,
                                "y1": y1,
                            }
                        )
                        break

                if results:
                    break  # one hit on this page is enough

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
    doc = _open_pdf_safe(pdf_bytes)

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
    doc = _open_pdf_safe(pdf_bytes)
    count = len(doc)
    doc.close()
    return count
