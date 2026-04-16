"""Tests for pdf_engine.find_span_for_text — bbox resolution.

These exist because the old implementation happily merged up to 10
adjacent text items across lines and unioned their bboxes, producing
paragraph-sized redaction boxes for single-word Deduce hits. The
current rules (word boundaries, single-line merges, anchored starts)
all exist to prevent that class of bug.
"""

from app.services.pdf_engine import PageText, TextSpan
from app.services.span_resolver import count_word_boundary_matches, find_span_for_text


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

    def test_substring_match_narrows_bbox_proportionally(self):
        """When the name is embedded in a sentence-length span — which is
        how PyMuPDF commonly serves paragraph text — the bbox must be
        narrowed to (approximately) the name itself, not the whole span.
        Otherwise redacting a single name blacks out the full line."""
        sentence = "De heer Van der Berg heeft op 20 februari 2024 gesproken."
        page = _page([TextSpan(text=sentence, page=0, x0=0, y0=10, x1=1000, y1=20)])
        results = find_span_for_text([page], "Van der Berg")
        assert len(results) == 1
        bbox = results[0]
        # The name starts at character 8 and runs 12 chars. Expect the
        # bbox to live in roughly that range (0–1000 pixel scale with 57
        # total chars), which must be far inside the left half of the
        # sentence and must NOT equal the full-span bbox.
        total = len(sentence)
        expected_x0 = 1000 * (8 / total)
        expected_x1 = 1000 * (20 / total)
        assert abs(bbox["x0"] - expected_x0) < 0.01
        assert abs(bbox["x1"] - expected_x1) < 0.01
        # Sanity: bbox is smaller than the span.
        assert bbox["x1"] - bbox["x0"] < 1000
        # Y stays on the line.
        assert bbox["y0"] == 10
        assert bbox["y1"] == 20


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

    def test_per_glyph_merge_assembles_long_iban(self):
        """Regression: pdf.js returns each glyph as its own text item for
        monospace fonts (Menlo / Courier). An 18-character IBAN can never
        satisfy the space-joined match test because the search contains
        no spaces and the stream has none either — we fall back to
        comparing the whitespace-stripped forms. Before this fix the
        merge loop bailed out at 12 items and the detection came back
        with zero bboxes, so the frontend silently dropped it."""
        iban = "NL83INGB0004752861"
        char_w = 7.22
        spans = [
            TextSpan(
                text=c,
                page=0,
                x0=10 + i * char_w,
                y0=10,
                x1=10 + (i + 1) * char_w,
                y1=20,
            )
            for i, c in enumerate(iban)
        ]
        page = _page(spans)
        results = find_span_for_text([page], iban)
        assert len(results) == 1
        bbox = results[0]
        assert bbox["x0"] == 10
        assert abs(bbox["x1"] - (10 + len(iban) * char_w)) < 0.01

    def test_per_glyph_merge_assembles_multiword_address(self):
        """"Kerkstraat 14" in a per-glyph text stream. The space item is
        dropped by the extractor (pdf.js emits space-only items that get
        trimmed), so the joined glyph stream is "Kerkstraat14" but the
        search is "Kerkstraat 14". The whitespace-stripped equality path
        is what makes this resolvable."""
        glyphs = list("Kerkstraat14")  # space dropped by the extractor
        char_w = 7.22
        spans = [
            TextSpan(
                text=c,
                page=0,
                x0=10 + i * char_w,
                y0=10,
                x1=10 + (i + 1) * char_w,
                y1=20,
            )
            for i, c in enumerate(glyphs)
        ]
        page = _page(spans)
        results = find_span_for_text([page], "Kerkstraat 14")
        assert len(results) == 1
        assert results[0]["x0"] == 10

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


# ---------------------------------------------------------------------------
# Occurrence index — map a specific NER hit to a single bbox
# ---------------------------------------------------------------------------


class TestOccurrenceIndex:
    """The regression this fixes: a persoon detection at one char offset
    was attaching bboxes for every occurrence of that name, because
    `find_span_for_text` returned all of them. The sidebar card ended
    up rendering "A.B. Bakker A.B. Bakker" once the frontend bbox→text
    resolver joined the text across all bboxes."""

    def test_returns_only_nth_match_for_repeated_name(self):
        page = _page(
            [
                TextSpan(text="A.B. Bakker", page=0, x0=10, y0=10, x1=80, y1=20),
                TextSpan(text="bij", page=0, x0=82, y0=10, x1=100, y1=20),
                TextSpan(text="afwezigheid", page=0, x0=102, y0=10, x1=180, y1=20),
                TextSpan(text="A.B. Bakker", page=0, x0=10, y0=40, x1=80, y1=50),
            ]
        )
        first = find_span_for_text([page], "A.B. Bakker", occurrence_index=0)
        assert len(first) == 1
        assert first[0]["y0"] == 10

        second = find_span_for_text([page], "A.B. Bakker", occurrence_index=1)
        assert len(second) == 1
        assert second[0]["y0"] == 40

    def test_occurrence_index_out_of_range_returns_empty(self):
        page = _page(
            [TextSpan(text="A.B. Bakker", page=0, x0=10, y0=10, x1=80, y1=20)]
        )
        assert find_span_for_text([page], "A.B. Bakker", occurrence_index=3) == []

    def test_mixed_split_and_unsplit_occurrences_on_same_page(self):
        """Regression: a name appearing twice on one page where pdf.js
        splits the first occurrence across two text items ("Jaap" +
        "Stronks") but keeps the second as a single item. The earlier
        implementation skipped the multi-item merge pass whenever any
        single-item match existed on the page, so occurrence 0 got the
        second name's bbox and occurrence 1 got the same bbox via
        fallback. Both copies of the name then stacked onto the second
        position, leaving the first name un-highlighted.
        """
        page = _page(
            [
                TextSpan(text="Factuuradres", page=0, x0=50, y0=10, x1=120, y1=22),
                TextSpan(text="Jaap", page=0, x0=50, y0=30, x1=75, y1=42),
                TextSpan(text="Stronks", page=0, x0=78, y0=30, x1=122, y1=42),
                TextSpan(
                    text="Verzendadres 200233",
                    page=0,
                    x0=50,
                    y0=60,
                    x1=180,
                    y1=72,
                ),
                TextSpan(text="Jaap Stronks", page=0, x0=50, y0=80, x1=122, y1=92),
            ]
        )

        first = find_span_for_text([page], "Jaap Stronks", occurrence_index=0)
        assert len(first) == 1
        assert first[0]["y0"] == 30  # the split-span occurrence
        assert first[0]["x0"] == 50
        assert first[0]["x1"] == 122

        second = find_span_for_text([page], "Jaap Stronks", occurrence_index=1)
        assert len(second) == 1
        assert second[0]["y0"] == 80  # the single-span occurrence

    def test_count_word_boundary_matches_respects_limit(self):
        text = "A.B. Bakker en later nog eens A.B. Bakker in dezelfde zin."
        # Everything counted → 2.
        assert count_word_boundary_matches(text, "A.B. Bakker") == 2
        # Everything up to just before the second occurrence → 1.
        second_pos = text.rfind("A.B. Bakker")
        assert (
            count_word_boundary_matches(text, "A.B. Bakker", limit=second_pos) == 1
        )
        # Limit at the start → 0.
        assert count_word_boundary_matches(text, "A.B. Bakker", limit=0) == 0

    def test_count_word_boundary_matches_skips_substring_hits(self):
        """Substring-only matches must not bump the count — otherwise
        the occurrence index picks up a bbox that belongs to a
        different word and the sidebar card drifts off the name."""
        text = "Vriesland en Jan de Vries wandelden."
        # Only the standalone 'Vries' counts.
        assert count_word_boundary_matches(text, "Vries") == 1
