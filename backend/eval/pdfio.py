"""Page payloads for the eval harness: what the frontend would have sent.

Both `ontlak.py` and `evaluate.py` need to tell a scanned page from a page
with a real text layer, and `evaluate.py` needs to hand the pipeline exactly
the payload the browser would have produced. Keeping both here means the
generator and the evaluator can never drift on what counts as a scanned page —
if they did, the evaluator would score detections on pages the generator never
filled.

Two things in here are less obvious than they look.

**The text comes from pdf.js, not PyMuPDF.** Production text is
`getTextContent()` items in content-stream order, joined with '' when they
touch on the same line and with ' ' otherwise, with no newlines anywhere.
`page.get_text()` gives a different tokenisation *and* newlines, so a harness
built on it measures its own tokenizer. `pdfjs_extract.mjs` runs the real
library; `--extractor pymupdf` is a lower-fidelity fallback for machines
without node.

**Planted values are moved back into reading order.** `ontlak.py` writes its
fictional values with `insert_text(..., overlay=True)`, which appends to the
content stream — so in the order pdf.js reads, every planted value lands at
the *end* of its page, torn from the `Geachte` or `Behandeld door` that gave
it its meaning. Every context-dependent rule in the pipeline (greeting cue,
structure enclosure, title prefix, corroboration) would then be measured
against a document nobody will ever meet. `relocate_planted()` puts them back
where they are drawn. Only planted items move; every original item keeps its
production order.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - environment problem, not a code path
    sys.exit("PyMuPDF ontbreekt: pip install pymupdf")

_HERE = Path(__file__).resolve().parent
EXTRACTOR_SCRIPT = _HERE / "pdfjs_extract.mjs"

#: Mirrors `SAME_LINE_TOLERANCE` / `ADJACENT_X_TOLERANCE` in
#: `frontend/src/lib/services/pdf-text-extractor.ts`. Change one, change all
#: three (the .mjs has its own copy because it is the real join).
SAME_LINE_TOLERANCE = 2.0
ADJACENT_X_TOLERANCE = 1.5

#: How much of a text item has to sit inside a planted value's ground-truth
#: box before we call it part of that value.
PLANTED_OVERLAP_MIN = 0.5

#: A remaining item counts as "left of" the planted value on the same line
#: when its right edge does not reach past the value's left edge by more than
#: this. One point of slack for the rounding in the ground-truth bboxes.
LEFT_OF_SLACK = 1.0

Box = dict[str, float]


def fullpage_image(page: Any) -> bool:
    """A scanned page: its text layer is OCR output, unusable for insertion.

    `ontlak.py` skips these because it cannot place a value convincingly on a
    page whose text layer reads `imaae002.pna`; `evaluate.py` skips them for
    the same reason — there is no trustworthy ground truth there, so any
    detection on such a page is neither a hit nor a false positive.
    """
    area = page.rect.get_area()
    return any(fitz.Rect(b["bbox"]).get_area() > 0.7 * area for b in page.get_image_info())


def join_items(texts: list[str], boxes: list[Box]) -> str:
    """Build a page's `full_text` the way `extractText()` does.

    Items that touch on the same line are joined with nothing, everything else
    with a single space, and no newline is ever emitted. pdf.js splits long
    tokens (URLs, IBANs, phone numbers) across text items, so a blind `' '`
    join inserts phantom spaces that break both regexes and NER.

    `boxes` must be the *unrotated* (layout viewport) boxes: on a /Rotate 90
    page a line runs top-to-bottom in viewer space and every same-line test
    would fail.

    The Node twin lives in `pdfjs_extract.mjs`; `test_pdfjs_extract.py` pins
    the two together.
    """
    parts: list[str] = []
    for idx, text in enumerate(texts):
        if idx == 0:
            parts.append(text)
            continue
        box, prev = boxes[idx], boxes[idx - 1]
        same_line = abs(box["y0"] - prev["y0"]) < SAME_LINE_TOLERANCE
        touching = same_line and box["x0"] - prev["x1"] < ADJACENT_X_TOLERANCE
        parts.append(("" if touching else " ") + text)
    return "".join(parts)


@dataclass
class Payload:
    """What the frontend would send after its own pdf.js extraction."""

    pages: list[dict[str, Any]] = field(default_factory=list)
    #: 1-based page numbers skipped because they are scans.
    scanned_pages: list[int] = field(default_factory=list)
    #: Total pages in the PDF, scanned ones included.
    page_count: int = 0
    #: Which extractor produced the text: `pdfjs` or `pymupdf`.
    extractor: str = "pdfjs"
    #: How many text items were moved back into reading order. Should equal
    #: the number of planted values, give or take values pdf.js split across
    #: several items.
    relocated: int = 0


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def _area(b: Box) -> float:
    return max(0.0, b["x1"] - b["x0"]) * max(0.0, b["y1"] - b["y0"])


def _intersection(a: Box, b: Box) -> float:
    dx = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    dy = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
    return dx * dy if dx > 0 and dy > 0 else 0.0


def extract_pdfjs(path: Path) -> dict[str, Any]:
    """Run the real pdf.js over the PDF and return its page dicts.

    Fails loudly: a silent fall back to PyMuPDF here would quietly change what
    the harness measures, which is the exact bug this module exists to stop.
    """
    try:
        proc = subprocess.run(
            ["node", str(EXTRACTOR_SCRIPT), str(path)],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:  # pragma: no cover - environment problem
        sys.exit("node ontbreekt: installeer Node 22+, of draai met --extractor pymupdf")
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        tail = exc.stderr.decode("utf-8", "replace")[-2000:]
        sys.exit(f"pdfjs_extract.mjs faalde op {path.name}:\n{tail}")
    return json.loads(proc.stdout)


def extract_pymupdf(path: Path) -> dict[str, Any]:
    """Lower-fidelity fallback: PyMuPDF spans instead of pdf.js text items.

    Spans are coarser than pdf.js text items and already come out in reading
    order rather than content-stream order, so the join rule barely bites and
    nothing needs relocating. Close enough to eyeball a run on a machine
    without node; not close enough to compare against a pdf.js baseline.
    """
    pages: list[dict[str, Any]] = []
    doc = fitz.open(path)
    try:
        for pno, page in enumerate(doc):
            items: list[dict[str, Any]] = []
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        if not span["text"].strip():
                            continue
                        x0, y0, x1, y1 = span["bbox"]
                        items.append(
                            {"text": span["text"].strip(), "x0": x0, "y0": y0, "x1": x1, "y1": y1}
                        )
            boxes = [{k: it[k] for k in ("x0", "y0", "x1", "y1")} for it in items]
            pages.append(
                {
                    "page_number": pno + 1,
                    "full_text": join_items([it["text"] for it in items], boxes),
                    "text_items": items,
                    "layout_boxes": boxes,
                    "rotation": page.rotation or 0,
                }
            )
        return {"page_count": len(doc), "pages": pages}
    finally:
        doc.close()


# --------------------------------------------------------------------------
# Putting planted values back where they are drawn
# --------------------------------------------------------------------------


def relocate_planted(page: dict[str, Any], truth_boxes: list[Box]) -> int:
    """Move this page's planted items from the end of the stream into place.

    Returns how many items moved. `page` is edited in place: `text_items`,
    `layout_boxes` and `full_text` all come back consistent.

    Reading position is computed from the moved items' own *layout* boxes, not
    from the ground-truth box, so a rotated page works without translating
    between spaces. An item is inserted after the last remaining item that is
    either on an earlier line (smaller y, top-left origin) or on the same line
    and to its left.
    """
    items: list[dict[str, Any]] = page["text_items"]
    layout: list[Box] = page["layout_boxes"]
    if not items or not truth_boxes:
        return 0

    # Which item belongs to which planted value. Groups keep their internal
    # order, so a value pdf.js split over two items stays readable.
    groups: dict[int, list[int]] = {}
    claimed: set[int] = set()
    for idx, item in enumerate(items):
        box = {k: float(item[k]) for k in ("x0", "y0", "x1", "y1")}
        area = _area(box)
        if area <= 0:
            continue
        for ti, truth in enumerate(truth_boxes):
            if _intersection(box, truth) / area >= PLANTED_OVERLAP_MIN:
                groups.setdefault(ti, []).append(idx)
                claimed.add(idx)
                break
    if not claimed:
        return 0

    keep = [i for i in range(len(items)) if i not in claimed]

    # Insert the groups one at a time, back to front over the page, so that a
    # value which should follow another planted value on the same line still
    # finds it in `keep`. Sorting by reading position (line, then x) gives the
    # same answer whichever order the ground truth happens to list them in.
    def anchor(indices: list[int]) -> tuple[float, float]:
        return (
            min(layout[i]["y0"] for i in indices),
            min(layout[i]["x0"] for i in indices),
        )

    for _ti, indices in sorted(groups.items(), key=lambda kv: anchor(kv[1])):
        ay, ax = anchor(indices)
        pos = 0
        for slot, i in enumerate(keep, start=1):
            box = layout[i]
            earlier_line = box["y0"] < ay - SAME_LINE_TOLERANCE
            same_line = abs(box["y0"] - ay) <= SAME_LINE_TOLERANCE
            if earlier_line or (same_line and box["x1"] <= ax + LEFT_OF_SLACK):
                pos = slot
        keep[pos:pos] = indices

    page["text_items"] = [items[i] for i in keep]
    page["layout_boxes"] = [layout[i] for i in keep]
    page["full_text"] = join_items([items[i]["text"] for i in keep], [layout[i] for i in keep])
    return len(claimed)


# --------------------------------------------------------------------------


def pages_payload(
    path: Path,
    *,
    skip_scanned: bool = True,
    extractor: str = "pdfjs",
    planted: list[dict[str, Any]] | None = None,
) -> Payload:
    """Mimic what the frontend sends after pdf.js extraction.

    Page numbers stay 1-based and keep their original value even when earlier
    pages were skipped, so a bounding box coming back out of the pipeline can
    still be compared with a ground-truth bbox by page number.

    `planted` is the `detections` list from an `ontlak.py` ground-truth JSON.
    When given, the values it describes are moved out of the tail of the
    content stream and back into reading order — see the module docstring.
    """
    raw = extract_pdfjs(path) if extractor == "pdfjs" else extract_pymupdf(path)

    by_page: dict[int, list[Box]] = {}
    for item in planted or []:
        x0, y0, x1, y1 = (float(v) for v in item["bbox"])
        by_page.setdefault(int(item["page"]), []).append({"x0": x0, "y0": y0, "x1": x1, "y1": y1})

    payload = Payload(page_count=int(raw["page_count"]), extractor=extractor)
    doc = fitz.open(path)
    try:
        for page in raw["pages"]:
            pno = int(page["page_number"])
            if skip_scanned and fullpage_image(doc[pno - 1]):
                payload.scanned_pages.append(pno)
                continue
            payload.relocated += relocate_planted(page, by_page.get(pno, []))
            payload.pages.append(
                {
                    "page_number": pno,
                    "full_text": page["full_text"],
                    "text_items": page["text_items"],
                    "rotation": page["rotation"],
                }
            )
    finally:
        doc.close()
    return payload
