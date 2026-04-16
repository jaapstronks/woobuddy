"""Text-span matching and bbox resolution.

Pure string-geometry helpers that map detected entity text back to
bounding box coordinates in extracted PDF text items. Separated from
``pdf_engine.py`` (which owns extraction and redaction) because these
functions have no dependency on PyMuPDF and are independently testable.
"""

import re

from app.services.pdf_engine import PageText, TextSpan
from app.services.pipeline_types import Bbox

# y0 tolerance for considering two text items to be on the same visual
# line. 3 PDF points is ~1 line-height of baseline jitter — wider than
# that and we're looking at the next line.
_SAME_LINE_TOL = 3.0


def _strip_ws(text: str) -> str:
    """Remove every whitespace character from ``text``.

    Used as a final fallback inside the multi-item merge so a search like
    "Kerkstraat 14" can match a run of single-character items that came
    through pdf.js without any intermediate space items. We compare the
    concatenated alphanumerics on both sides rather than trying to patch
    the space back in, because pdf.js drops zero-width and space-only
    items during extraction (`pdf-text-extractor.ts`) and there's no
    reliable way to reinsert them at the right position.
    """
    return re.sub(r"\s+", "", text)


def _word_boundary_match_index(haystack: str, needle: str) -> int:
    """Return the first index at which `needle` appears in `haystack` as a
    whole word (non-alphanumeric chars on both sides), or -1 for no match.

    This prevents "Vries" from matching inside "Vriesland" — the kind
    of false positive that causes the bbox of a person detection to
    snap onto an unrelated word.
    """
    if not needle:
        return -1
    n = len(needle)
    idx = 0
    while True:
        idx = haystack.find(needle, idx)
        if idx == -1:
            return -1
        left_ok = idx == 0 or not haystack[idx - 1].isalnum()
        right = idx + n
        right_ok = right == len(haystack) or not haystack[right].isalnum()
        if left_ok and right_ok:
            return idx
        idx += 1


def _is_word_boundary_match(haystack: str, needle: str) -> bool:
    """True iff `needle` appears in `haystack` as a whole word."""
    return _word_boundary_match_index(haystack, needle) != -1


def count_word_boundary_matches(
    haystack: str, needle: str, *, limit: int | None = None
) -> int:
    """Count word-boundary matches of `needle` in `haystack`.

    Case-insensitive. When `limit` is supplied, only matches starting
    strictly before that character offset are counted — this lets a
    caller figure out "how many occurrences of this text come before
    position X in the full document text" so the match at X can be
    mapped to a specific bbox. See `find_span_for_text` with
    `occurrence_index` below.
    """
    if not needle:
        return 0
    haystack_lower = haystack.lower()
    needle_lower = needle.lower()
    upper = len(haystack_lower) if limit is None else min(limit, len(haystack_lower))
    n = len(needle_lower)
    count = 0
    idx = 0
    while idx < upper:
        pos = haystack_lower.find(needle_lower, idx)
        if pos == -1 or pos >= upper:
            break
        left_ok = pos == 0 or not haystack_lower[pos - 1].isalnum()
        right = pos + n
        right_ok = right == len(haystack_lower) or not haystack_lower[right].isalnum()
        if left_ok and right_ok:
            count += 1
        idx = pos + 1
    return count


def _narrow_bbox_to_substring(span: "TextSpan", match_idx: int, match_len: int) -> Bbox:
    """Proportionally narrow a text span's bbox to the substring range
    `[match_idx, match_idx + match_len)`.

    pdf.js / PyMuPDF give us only the overall bbox of each text item, not
    per-glyph positions, so we can't get the exact pixel offset of a
    substring inside a longer item. We approximate by scaling linearly by
    character count — a variable-width font means this is off by a few
    pixels in practice, but that's far better than the alternative of
    snapping the WHOLE text item's bbox (which, for a sentence-length
    item, paints an entire paragraph line black when only a name should
    be redacted).

    If the substring covers the entire span we return the span's own
    bbox verbatim so existing tests stay stable.
    """
    total = len(span.text)
    # Degenerate case — no characters to scale against. Return the span's
    # own bbox so the caller gets a non-empty (if approximate) box.
    if total == 0:
        return Bbox(page=span.page, x0=span.x0, y0=span.y0, x1=span.x1, y1=span.y1)
    width = span.x1 - span.x0
    x0 = span.x0 + width * (match_idx / total)
    x1 = span.x0 + width * ((match_idx + match_len) / total)
    return Bbox(page=span.page, x0=x0, y0=span.y0, x1=x1, y1=span.y1)


def _try_merge_match_from_anchor(
    spans: list[TextSpan],
    i: int,
    search_lower: str,
    first_word: str,
    search_stripped: str,
) -> Bbox | None:
    """Try to assemble ``search_lower`` by walking same-line spans starting
    at ``spans[i]``. Returns a single bbox dict on success or ``None``.

    Three match strategies are tried after each item is appended:

    1. Word-boundary match on the space-joined merge (``with_space``).
       This is the common case — pdf.js / PyMuPDF return each token as
       its own item and the search text lines up exactly with "jan de
       vries" once Jan/de/Vries have been merged.
    2. Word-boundary match on the concatenated merge (``without_space``).
       Covers the no-space splits that sometimes come through for
       compound tokens like URLs.
    3. Equality on the whitespace-stripped merge (``stripped``). This is
       the fallback for PDFs where pdf.js returns each glyph as its own
       text item (typical of monospace fonts like Menlo). A 12-item
       stream of single characters can never satisfy strategies 1 or 2
       because the search contains spaces while the item stream does
       not, but the stripped forms match exactly. Without this path,
       long detections such as "NL83INGB0004752861", "Kerkstraat 14",
       and "Fatima El Amrani" come back from `detect_all` but resolve
       to zero bboxes, and the frontend silently drops them.

    The merge is bounded by accumulated stripped-character length rather
    than item count: we give up once the stripped stream has clearly
    overshot the search (``len(stripped) > len(search_stripped) + 4``) or
    once the same-line guard breaks. This replaces an earlier hard cap of
    12 items, which was too tight for per-glyph streams.
    """
    start = spans[i]
    start_lower = start.text.lower()
    if not (
        _is_word_boundary_match(start_lower, first_word)
        or search_lower.startswith(start_lower)
    ):
        return None

    merged_parts: list[str] = [start.text]
    x0, y0, x1, y1 = start.x0, start.y0, start.x1, start.y1
    stripped = _strip_ws(start.text.lower())

    # Safety cap on item count so a pathological PDF can't drag us through
    # an entire page from a single false-positive anchor. The length-based
    # early-abort below is the primary brake; this is belt-and-braces.
    max_items = max(60, len(search_stripped) * 2 + 8)

    j = i + 1
    while j < len(spans) and (j - i) <= max_items:
        nxt = spans[j]
        if abs(nxt.y0 - start.y0) > _SAME_LINE_TOL:
            return None
        merged_parts.append(nxt.text)
        x0 = min(x0, nxt.x0)
        x1 = max(x1, nxt.x1)
        y0 = min(y0, nxt.y0)
        y1 = max(y1, nxt.y1)
        stripped += _strip_ws(nxt.text.lower())

        with_space = " ".join(merged_parts).lower()
        without_space = "".join(merged_parts).lower()

        if (
            _is_word_boundary_match(with_space, search_lower)
            or _is_word_boundary_match(without_space, search_lower)
            or stripped == search_stripped
        ):
            return Bbox(page=start.page, x0=x0, y0=y0, x1=x1, y1=y1)

        if len(stripped) > len(search_stripped) + 4:
            return None
        j += 1

    return None


def _find_nth_occurrence(
    pages_to_check: list[PageText],
    search_lower: str,
    first_word: str,
    occurrence_index: int,
) -> list[Bbox]:
    """Return a single-bbox list for the Nth word-boundary match of
    `search_lower` across `pages_to_check`, in reading order.

    Walks every page span-by-span and, for each span, first checks
    whether the span itself is a single-item match; if not, tries to
    merge subsequent same-line spans starting from it. Single-item and
    merged matches are counted in the same walk so the Nth hit is
    picked correctly even when a page contains *both* kinds — e.g. the
    same name appears twice on a page, but pdf.js splits one occurrence
    across multiple text items ("Jaap" + "Stronks") while keeping the
    other as a single "Jaap Stronks" item. The earlier
    "single-item-only-if-any-exist-on-the-page" shortcut dropped the
    split occurrence entirely, which is how two copies of the same name
    ended up sharing one bbox at the wrong position.
    """
    search_stripped = _strip_ws(search_lower)
    seen = 0
    for page_text in pages_to_check:
        spans = page_text.spans
        for i, start in enumerate(spans):
            start_lower = start.text.lower()

            # --- single-item match at this span ---
            idx = _word_boundary_match_index(start_lower, search_lower)
            if idx != -1:
                if seen == occurrence_index:
                    return [_narrow_bbox_to_substring(start, idx, len(search_lower))]
                seen += 1
                # Don't also try to merge starting here — the whole
                # search text is already inside this one item, so any
                # merge match anchored here would just widen the bbox
                # onto unrelated neighbours.
                continue

            # --- multi-item same-line merge starting at this span ---
            matched_bbox = _try_merge_match_from_anchor(
                spans, i, search_lower, first_word, search_stripped
            )
            if matched_bbox is None:
                continue
            if seen == occurrence_index:
                return [matched_bbox]
            seen += 1

    return []


def find_span_for_text(
    pages: list[PageText],
    search_text: str,
    page_hint: int | None = None,
    occurrence_index: int | None = None,
) -> list[Bbox]:
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

    When `occurrence_index` is provided the function iterates all pages
    in reading order and returns a single-bbox list corresponding to
    the Nth (0-indexed) match it encounters, or `[]` if there aren't
    that many matches. This is how a NER detection at a specific
    character offset gets mapped to exactly one bbox instead of every
    occurrence of its text — otherwise a name like "A.B. Bakker" that
    appears twice in the document would attach both bboxes to a single
    detection, and the frontend's bbox→text resolver would happily
    render "A.B. Bakker A.B. Bakker" in the sidebar.
    """
    search_lower = search_text.lower().strip()
    if not search_lower:
        return []

    pages_to_check = (
        [pages[page_hint]] if page_hint is not None and 0 <= page_hint < len(pages) else pages
    )

    first_word = search_lower.split(" ", 1)[0] if " " in search_lower else search_lower
    search_stripped = _strip_ws(search_lower)

    if occurrence_index is not None:
        return _find_nth_occurrence(
            pages_to_check, search_lower, first_word, occurrence_index
        )

    results: list[Bbox] = []

    for page_text in pages_to_check:
        # 1) Single-item match — the common case. When the match is a
        #    strict substring of a longer text item (typical for PyMuPDF,
        #    where an entire sentence often comes back as one span) we
        #    narrow the bbox proportionally to the matched substring.
        #    Returning the full item's bbox used to cause the whole
        #    sentence to get redacted — see the Van der Berg regression
        #    that prompted this code path.
        for span in page_text.spans:
            span_lower = span.text.lower()
            idx = _word_boundary_match_index(span_lower, search_lower)
            if idx != -1:
                results.append(_narrow_bbox_to_substring(span, idx, len(search_lower)))

        # 2) Multi-item same-line merge, anchored at an item that
        #    plausibly starts the match.
        if not results:
            spans = page_text.spans
            for i in range(len(spans)):
                merged_bbox = _try_merge_match_from_anchor(
                    spans, i, search_lower, first_word, search_stripped
                )
                if merged_bbox is not None:
                    results.append(merged_bbox)
                    break  # one hit on this page is enough

        if results:
            break  # found on this page, stop

    return results
