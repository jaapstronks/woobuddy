"""Unit tests for `app.services.role_engine`.

These tests exercise the pure rule-based matcher without going through
Deduce — the detection span is supplied as explicit (start, end) offsets
in a fixed input string so the assertions stay deterministic regardless
of how Deduce tokenizes.

Covers the six scenarios listed in
`docs/todo/done/13-functietitel-publiek-functionaris.md`, plus a
pipeline-level smoke test that verifies the rule engine hooks into
`run_pipeline` correctly for the "Wethouder Jan de Vries" canonical
case.
"""

from __future__ import annotations

import pytest

from app.services.pipeline_engine import run_pipeline
from app.services.pdf_engine import ExtractionResult, PageText, TextSpan
from app.services.role_engine import (
    find_function_title_near,
    load_function_title_lists,
)


@pytest.fixture(scope="module")
def lists():
    return load_function_title_lists()


def _span_of(text: str, needle: str) -> tuple[int, int]:
    """Return (start, end) of the first occurrence of `needle` in `text`."""
    start = text.index(needle)
    return start, start + len(needle)


class TestFindFunctionTitleNear:
    def test_publiek_title_before_capitalized(self, lists):
        text = "Wethouder Jan de Vries heeft het besluit ondertekend."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "publiek"
        assert match.title == "wethouder"
        assert match.position == "before"

    def test_publiek_title_before_lowercase(self, lists):
        text = "namens wethouder Jan de Vries is het besluit genomen."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "publiek"
        assert match.title == "wethouder"

    def test_ambtenaar_title_before(self, lists):
        text = "Het stuk is opgesteld door beleidsmedewerker Jan de Vries."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "ambtenaar"
        assert match.title == "beleidsmedewerker"

    def test_publiek_title_after_apposition(self, lists):
        text = "Jan de Vries, wethouder van Utrecht, opent de vergadering."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "publiek"
        assert match.position == "after"

    def test_distant_title_rejected(self, lists):
        """'Jan de Vries zei dat de wethouder gebeld had' — the wethouder
        refers to someone else. Three tokens between the span and the
        title is past our threshold, so no match should fire."""
        text = "Jan de Vries zei dat de wethouder gebeld had."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is None

    def test_no_title_in_window(self, lists):
        text = "Jan de Vries heeft een brief geschreven over het project."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is None

    def test_publiek_beats_ambtenaar_at_same_position(self, lists):
        """Per the todo: when both a publiek and an ambtenaar title
        match in the before-context within proximity, publiek wins
        regardless of which is closer. This implements the
        public-officials-do-not-redact rule even if a civil-servant
        title happens to be closer to the name in the text."""
        text = "De wethouder en projectleider Jan de Vries zijn aanwezig."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "publiek"
        assert match.title == "wethouder"

    def test_multiword_publiek_title(self, lists):
        text = "Commissaris van de Koning Jan de Vries bezocht de regio."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "publiek"
        assert match.title == "commissaris van de koning"

    def test_whole_word_matching(self, lists):
        """'wethouderschap' must NOT match 'wethouder' as a prefix."""
        text = "Het wethouderschap van Jan de Vries duurt vier jaar."
        start, end = _span_of(text, "Jan de Vries")
        match = find_function_title_near(text, start, end, lists)
        assert match is None


# ---------------------------------------------------------------------------
# Pipeline smoke test — verifies the rule engine hooks into run_pipeline.
# ---------------------------------------------------------------------------


def _make_extraction(text: str) -> ExtractionResult:
    spans = [TextSpan(text=text, page=0, x0=10, y0=10, x1=500, y1=25)]
    pages = [PageText(page_number=0, full_text=text, spans=spans)]
    return ExtractionResult(pages=pages, page_count=1, full_text=text)


@pytest.mark.asyncio
async def test_pipeline_publiek_functionaris_rule_fires():
    """Canonical acceptance case from the todo: a document containing
    'Wethouder Jan de Vries' should produce a Tier 2 persoon detection
    with review_status='rejected', subject_role='publiek_functionaris',
    source='rule', and a reasoning string naming the matched title."""
    text = "Wethouder Jan de Vries ondertekent het besluit namens de gemeente."
    extraction = _make_extraction(text)

    result = await run_pipeline(extraction)

    persons = [d for d in result.detections if d.entity_type == "persoon"]
    assert persons, "expected Deduce to detect a persoon in the input"
    rule_hits = [p for p in persons if p.source == "rule"]
    assert rule_hits, "rule engine should have fired on 'Wethouder Jan de Vries'"
    hit = rule_hits[0]
    assert hit.review_status == "rejected"
    assert hit.subject_role == "publiek_functionaris"
    assert "wethouder" in hit.reasoning.lower()
