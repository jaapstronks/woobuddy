"""Tests for pdf_engine.find_span_for_text — bbox resolution.

These exist because the old implementation happily merged up to 10
adjacent text items across lines and unioned their bboxes, producing
paragraph-sized redaction boxes for single-word Deduce hits. The
current rules (word boundaries, single-line merges, anchored starts)
all exist to prevent that class of bug.
"""

from app.services.pdf_engine import PageText, TextSpan, find_span_for_text


def _page(spans: list[TextSpan]) -> PageText:
    full_text = " ".join(s.text for s in spans)
    return PageText(page_number=0, full_text=full_text, spans=spans)


# ---------------------------------------------------------------------------
# Single-item match with word-boundary check
# ---------------------------------------------------------------------------


class TestSingleItemMatch:
    def test_exact_span_returns_its_bbox(self):
        page = _page([TextSpan(text="Jan de Vries", page=0, x0=10, y0=10, x1=100, y1=20)])
        results = find_span_for_text([page], "Jan de Vries")
        assert len(results) == 1
        assert results[0] == {
            "page": 0,
            "x0": 10,
            "y0": 10,
            "x1": 100,
            "y1": 20,
        }

    def test_word_boundary_prevents_substring_false_positive(self):
        """'Vries' should NOT match inside 'Vriesland'. Before the
        boundary check, this would have bbox'd the town name as if
        it were a person."""
        page = _page([TextSpan(text="Vriesland", page=0, x0=10, y0=10, x1=80, y1=20)])
        results = find_span_for_text([page], "Vries")
        assert results == []

    def test_word_boundary_allows_punctuation_boundaries(self):
        """Punctuation on either side should still count as a boundary."""
        page = _page([TextSpan(text="(Jan de Vries).", page=0, x0=10, y0=10, x1=120, y1=20)])
        results = find_span_for_text([page], "Jan de Vries")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Multi-item merge — same line only, anchored start
# ---------------------------------------------------------------------------


class TestMultiItemMerge:
    def test_single_line_merge_finds_split_name(self):
        """pdf.js splits 'Jan de Vries' into three items. They're on
        the same line, so the merge should produce one tight bbox."""
        page = _page(
            [
                TextSpan(text="Jan", page=0, x0=10, y0=10, x1=30, y1=20),
                TextSpan(text="de", page=0, x0=32, y0=10, x1=42, y1=20),
                TextSpan(text="Vries", page=0, x0=44, y0=10, x1=80, y1=20),
            ]
        )
        results = find_span_for_text([page], "Jan de Vries")
        assert len(results) == 1
        bbox = results[0]
        assert bbox["x0"] == 10
        assert bbox["x1"] == 80
        # Same-line: y range stays tight.
        assert bbox["y0"] == 10
        assert bbox["y1"] == 20

    def test_merge_never_crosses_line_break(self):
        """This is the paragraph-box regression. Old code would merge
        across lines because it only cared about string containment."""
        page = _page(
            [
                TextSpan(text="de", page=0, x0=10, y0=10, x1=20, y1=20),
                # Next 'line' of the PDF — y0 is well below the first line.
                TextSpan(text="Amsterdamse", page=0, x0=10, y0=40, x1=80, y1=50),
                TextSpan(text="Hogeschool", page=0, x0=82, y0=40, x1=150, y1=50),
            ]
        )
        # The whole phrase does not appear on a single line, so we must
        # not produce a bbox that spans lines.
        results = find_span_for_text([page], "de Amsterdamse Hogeschool")
        assert results == []

    def test_merge_anchored_at_start_span(self):
        """The first span of the merge must contain the start of the
        match. Otherwise the bbox gets anchored at an unrelated earlier
        span and drifts leftward."""
        page = _page(
            [
                TextSpan(text="Onderwerp:", page=0, x0=10, y0=10, x1=70, y1=20),
                TextSpan(text="Jan", page=0, x0=72, y0=10, x1=92, y1=20),
                TextSpan(text="de", page=0, x0=94, y0=10, x1=104, y1=20),
                TextSpan(text="Vries", page=0, x0=106, y0=10, x1=140, y1=20),
            ]
        )
        results = find_span_for_text([page], "Jan de Vries")
        assert len(results) == 1
        bbox = results[0]
        # bbox must start at the 'Jan' item (x0=72), not at 'Onderwerp:'.
        assert bbox["x0"] == 72
        assert bbox["x1"] == 140

    def test_no_space_merge_for_split_url(self):
        """URLs get split without spaces by the PDF renderer. The
        merge must accept no-space concatenation for this case."""
        page = _page(
            [
                TextSpan(text="https://example.com/", page=0, x0=10, y0=10, x1=100, y1=20),
                TextSpan(text="long-path", page=0, x0=101, y0=10, x1=160, y1=20),
            ]
        )
        results = find_span_for_text([page], "https://example.com/long-path")
        assert len(results) == 1
        assert results[0]["x0"] == 10
        assert results[0]["x1"] == 160

    def test_returns_empty_when_text_not_found(self):
        page = _page([TextSpan(text="something else", page=0, x0=10, y0=10, x1=80, y1=20)])
        results = find_span_for_text([page], "Jan de Vries")
        assert results == []

    def test_empty_search_text_returns_empty(self):
        page = _page([TextSpan(text="Jan", page=0, x0=10, y0=10, x1=30, y1=20)])
        assert find_span_for_text([page], "") == []
        assert find_span_for_text([page], "   ") == []
