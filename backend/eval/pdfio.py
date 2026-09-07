"""PyMuPDF helpers shared by `ontlak.py` and `evaluate.py`.

Both scripts need the same two things: a way to tell a scanned page from a
page with a real text layer, and a way to turn a PDF into the payload the
frontend sends to `/api/analyze`. Keeping them here means the generator and
the evaluator can never drift on what counts as a scanned page — if they did,
the evaluator would score detections on pages the generator never filled.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - environment problem, not a code path
    sys.exit("PyMuPDF ontbreekt: pip install pymupdf")


def fullpage_image(page: Any) -> bool:
    """A scanned page: its text layer is OCR output, unusable for insertion.

    `ontlak.py` skips these because it cannot place a value convincingly on a
    page whose text layer reads `imaae002.pna`; `evaluate.py` skips them for
    the same reason — there is no trustworthy ground truth there, so any
    detection on such a page is neither a hit nor a false positive.
    """
    area = page.rect.get_area()
    return any(fitz.Rect(b["bbox"]).get_area() > 0.7 * area for b in page.get_image_info())


@dataclass
class Payload:
    """What the frontend would send after its own pdf.js extraction."""

    pages: list[dict[str, Any]] = field(default_factory=list)
    #: 1-based page numbers skipped because they are scans.
    scanned_pages: list[int] = field(default_factory=list)
    #: Total pages in the PDF, scanned ones included.
    page_count: int = 0


def pages_payload(path: Path, *, skip_scanned: bool = True) -> Payload:
    """Mimic what the frontend sends after pdf.js extraction.

    Page numbers stay 1-based and keep their original value even when earlier
    pages were skipped, so a bounding box coming back out of the pipeline can
    still be compared with a ground-truth bbox by page number.
    """
    payload = Payload()
    doc = fitz.open(path)
    try:
        payload.page_count = len(doc)
        for pno, page in enumerate(doc):
            if skip_scanned and fullpage_image(page):
                payload.scanned_pages.append(pno + 1)
                continue
            items: list[dict[str, Any]] = []
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        if not span["text"].strip():
                            continue
                        x0, y0, x1, y1 = span["bbox"]
                        items.append({"text": span["text"], "x0": x0, "y0": y0, "x1": x1, "y1": y1})
            payload.pages.append(
                {
                    "page_number": pno + 1,
                    "full_text": page.get_text(),
                    "text_items": items,
                    "rotation": page.rotation or 0,
                }
            )
    finally:
        doc.close()
    return payload
