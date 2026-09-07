"""Two shapes of the same page text, and why the tests need both.

The detection engines are pure text-in / spans-out, so a test can hand them a
string. Which string, though, is not a detail: for months every backend test
fed them PyMuPDF-shaped text — `page.get_text()` output, with a newline per
visual line and a blank line between paragraphs — while production sends what
pdf.js produced in the browser. Until #95 that browser text carried no
newlines at all, and ten rules in `ner_engine` plus the whole structure engine
silently reinterpreted "the same line" as "the last 40 to 60 characters". The
tests could not see it, because the tests were the one caller with newlines.

`production_text()` closes that gap. It reshapes a hand-written fixture into
what `joinTextItems()` in `frontend/src/lib/services/text-join.ts` would emit
for the same page:

* one `\n` per line boundary — pdf.js items that do not share a line;
* **no blank lines**, because a blank line has no text items to separate;
* single spaces, because the join emits exactly one space between items that
  share a line, never the runs of padding a PDF's own text layer can hold.

Keep both shapes in the suite. The PyMuPDF shape still reaches the engines via
the eval harness's `--extractor pymupdf` fallback, and a rule that only works
on blank-line-separated text is a rule that does not work.
"""

from __future__ import annotations


def production_text(text: str) -> str:
    """Reshape a fixture into the page text the browser would have sent."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)
