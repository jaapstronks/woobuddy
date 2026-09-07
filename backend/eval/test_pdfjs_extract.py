"""Pin the two halves of the harness's text extraction together.

`pdfjs_extract.mjs` is a hand transcription of `extractText()` in
`frontend/src/lib/services/pdf-text-extractor.ts`, and `pdfio.join_items()`
is a second transcription of the join rule inside it (Python needs its own
copy to rebuild `full_text` after relocating a planted value). Three copies of
one rule drift silently unless something asserts otherwise, so:

  * the join rule is checked against a hand-computed expectation on a PDF
    built here, item by item;
  * the Python join is checked against the Node one on the same page;
  * the relocation is checked to put an overlay-inserted value back where it
    is drawn, which is the whole reason `pdfio` exists.

Not part of the CI suite: `testpaths` is `tests/`, and `eval/` never ships.
Run it by hand from `backend/`:

    pytest eval/test_pdfjs_extract.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdfio import join_items, pages_payload  # noqa: E402

EXTRACTOR = Path(__file__).resolve().parent / "pdfjs_extract.mjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

FONT = "helv"
SIZE = 10.0


def _width(text: str) -> float:
    return fitz.get_text_length(text, fontname=FONT, fontsize=SIZE)


def _write(page: fitz.Page, x: float, y: float, text: str) -> float:
    """Draw one show-text operator; return the x where it ends."""
    page.insert_text((x, y), text, fontname=FONT, fontsize=SIZE)
    return x + _width(text)


def _extract(path: Path) -> dict:
    proc = subprocess.run(["node", str(EXTRACTOR), str(path)], capture_output=True, check=True)
    return json.loads(proc.stdout)


def test_join_rule_matches_the_frontend(tmp_path: Path) -> None:
    """Touching items join with nothing, everything else with one space.

    pdf.js hands the browser one text item per show-text operator, so an IBAN
    split over three operators must come back as one token: a phantom space
    there breaks both the Tier 1 regexes and Deduce.
    """
    doc = fitz.open()
    page = doc.new_page()
    # Three operators that abut exactly: one word to the reader, three items
    # to pdf.js.
    end = _write(page, 72.0, 100.0, "NL91")
    end = _write(page, end, 100.0, "ABNA")
    _write(page, end, 100.0, "0417")
    # A real gap on the same line, and a second line.
    _write(page, end + 40.0, 100.0, "Rekening")
    _write(page, 72.0, 130.0, "Geachte")
    pdf = tmp_path / "join.pdf"
    doc.save(pdf)
    doc.close()

    raw = _extract(pdf)
    assert raw["page_count"] == 1
    page_data = raw["pages"][0]
    assert page_data["page_number"] == 1
    assert page_data["rotation"] == 0
    # Hand-computed: no newline anywhere, and the IBAN survives whole.
    assert page_data["full_text"] == "NL91ABNA0417 Rekening Geachte"

    # And the Python twin agrees on the same items.
    assert (
        join_items(
            [i["text"] for i in page_data["text_items"]],
            page_data["layout_boxes"],
        )
        == page_data["full_text"]
    )


def test_planted_values_move_back_into_reading_order(tmp_path: Path) -> None:
    """`ontlak.py` appends; the reader reads. `pages_payload` reconciles them.

    `insert_text(..., overlay=True)` puts the planted value at the end of the
    content stream, which is the order pdf.js reports and therefore the order
    production would see. Left alone, every greeting cue and signature-block
    heuristic in the pipeline is scored against a document nobody will meet.
    """
    doc = fitz.open()
    page = doc.new_page()
    end = _write(page, 72.0, 100.0, "Geachte")
    _write(page, 72.0, 130.0, "Met vriendelijke groet")
    # The planted value: same line as "Geachte", but written last.
    value_x = end + _width(" ")
    _write(page, value_x, 100.0, "Jansen")
    pdf = tmp_path / "planted.pdf"
    doc.save(pdf)
    doc.close()

    without = pages_payload(pdf, planted=None)
    assert without.relocated == 0
    assert without.pages[0]["full_text"] == "Geachte Met vriendelijke groet Jansen"

    planted = [
        {
            "page": 1,
            "bbox": [value_x, 100.0 - SIZE, value_x + _width("Jansen"), 100.0 + SIZE * 0.25],
            "value": "Jansen",
        }
    ]
    with_truth = pages_payload(pdf, planted=planted)
    assert with_truth.relocated == 1
    assert with_truth.pages[0]["full_text"] == "Geachte Jansen Met vriendelijke groet"
    # The bboxes are untouched: only the order changed.
    assert {i["text"] for i in with_truth.pages[0]["text_items"]} == {
        i["text"] for i in without.pages[0]["text_items"]
    }
