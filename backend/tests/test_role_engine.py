"""Unit tests for `app.services.role_engine`.

These tests exercise the pure rule-based matcher without going through
Deduce — the detection span is supplied as explicit (start, end) offsets
in a fixed input string so the assertions stay deterministic regardless
of how Deduce tokenizes.

Covers the six canonical role-engine scenarios, plus a
pipeline-level smoke test that verifies the rule engine hooks into
`run_pipeline` correctly for the "Wethouder Jan de Vries" canonical
case.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.services.pdf_engine import ExtractionResult, PageText, TextSpan
from app.services.pipeline_engine import run_pipeline
from app.services.role_engine import (
    find_function_title_near,
    find_mandate_cue_before,
    load_function_title_lists,
)
from tests.text_shapes import production_text


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


# ---------------------------------------------------------------------------
# #94 — bestuursorganen and the mandate cue
# ---------------------------------------------------------------------------


@pytest.fixture(params=["pymupdf", "production"])
def shape(request: pytest.FixtureRequest) -> Callable[[str], str]:
    """Return a fixture reshaper for one of the two text shapes."""
    return production_text if request.param == "production" else lambda text: text


#: The closing of a Drenthe decision letter, with the redacted name
#: refilled above the college and the mandated signatory below it. Both
#: names sit inside the "Hoogachtend," signature block.
_GS_CLOSING = """\
Hoogachtend,

Stefanie Öztürk

Gedeputeerde Staten van Drenthe,
namens dezen,
W.J. van Elsacker,
teammanager Ruimte, Energie en Wonen
"""


class TestBestuursorganen:
    def test_gedeputeerde_staten_is_not_a_title(self, lists, shape):
        """The name above "Gedeputeerde Staten van Drenthe" is not a gedeputeerde."""
        text = shape(_GS_CLOSING)
        start, end = _span_of(text, "Stefanie Öztürk")
        assert find_function_title_near(text, start, end, lists) is None

    def test_singular_gedeputeerde_still_publiek(self, lists, shape):
        """ "gedeputeerde <Naam>" keeps its title — only the college is masked."""
        text = shape("Het besluit is genomen door gedeputeerde Y. Turenhout.")
        start, end = _span_of(text, "Y. Turenhout")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "publiek"
        assert match.title == "gedeputeerde"

    def test_provinciale_staten_is_not_a_title(self, lists, shape):
        text = shape("Provinciale Staten van Drenthe\nKarel Bosman\n")
        start, end = _span_of(text, "Karel Bosman")
        assert find_function_title_near(text, start, end, lists) is None

    def test_college_van_bw_is_not_a_title(self, lists, shape):
        text = shape("Namens het college van burgemeester en wethouders,\nSanne de Groot\n")
        start, end = _span_of(text, "Sanne de Groot")
        assert find_function_title_near(text, start, end, lists) is None

    def test_organ_glued_to_the_span_is_still_masked(self, lists, shape):
        """A refilled redaction box can run straight into the phrase.

        pdf.js hands us "Brian Vechtburgemeester en wethouders van
        Emmen" for a letter whose signature line was blacked out; the
        "wethouders" there is still the college's, not Brian's.
        """
        text = shape("Hoogachtend,\nBrian Vechtburgemeester en wethouders van Emmen,\n")
        start, end = _span_of(text, "Brian Vechtburgemeester")
        assert find_function_title_near(text, start, end, lists) is None

    def test_solitary_burgemeester_still_publiek(self, lists, shape):
        text = shape("De vergadering werd geleid door burgemeester Anne Klaassen.")
        start, end = _span_of(text, "Anne Klaassen")
        match = find_function_title_near(text, start, end, lists)
        assert match is not None
        assert match.list_name == "publiek"


class TestMandateCue:
    def test_namens_dezen_directly_before_the_name(self, shape):
        text = shape(_GS_CLOSING)
        start, _end = _span_of(text, "W.J. van Elsacker")
        assert find_mandate_cue_before(text, start) is True

    def test_namens_deze_singular(self, shape):
        text = shape(
            "Met vriendelijke groet,\nde Nationale ombudsman,\nnamens deze,\nHanneke van Essen\n"
        )
        start, _end = _span_of(text, "Hanneke van Essen")
        assert find_mandate_cue_before(text, start) is True

    def test_cue_reaches_across_a_function_title_line(self, shape):
        text = shape(
            "Hoogachtend,\nburgemeester en wethouders van Emmen,\nnamens dezen,\n"
            "teamleider Ruimtelijke ontwikkeling,\nmevrouw M.A.E. Holwarda\n"
        )
        start, _end = _span_of(text, "M.A.E. Holwarda")
        assert find_mandate_cue_before(text, start) is True

    def test_cue_does_not_reach_the_name_above_the_college(self, shape):
        """The addressee printed *before* the cue is not a mandated signatory."""
        text = shape(_GS_CLOSING)
        start, _end = _span_of(text, "Stefanie Öztürk")
        assert find_mandate_cue_before(text, start) is False

    def test_cue_does_not_reach_across_prose(self):
        text = (
            "Het besluit is namens dezen genomen. Voor de volledigheid melden wij "
            "dat de aanvraag door Jan de Vries is ingediend."
        )
        start, _end = _span_of(text, "Jan de Vries")
        assert find_mandate_cue_before(text, start) is False

    def test_cue_does_not_reach_across_a_blank_line(self):
        text = "namens dezen,\n\nJan de Vries\n"
        start, _end = _span_of(text, "Jan de Vries")
        assert find_mandate_cue_before(text, start) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("reshape", [lambda t: t, production_text], ids=["pymupdf", "production"])
async def test_pipeline_mandate_signatory_stays_pending(reshape):
    """#94: the "namens dezen" signatory must not be auto-accepted.

    Both names in the closing sit inside the "Hoogachtend," signature
    block, which used to auto-accept everything it enclosed. The
    mandated signatory now reaches the reviewer as a pending ambtenaar
    card instead, and the name above the college is no longer rejected
    as a publiek functionaris.
    """
    text = reshape(_GS_CLOSING)
    result = await run_pipeline(_make_extraction(text))

    by_text = {d.entity_text: d for d in result.detections if d.entity_type == "persoon"}
    assert "W.J. van Elsacker" in by_text, f"expected the signatory, got {list(by_text)}"

    signatory = by_text["W.J. van Elsacker"]
    assert signatory.review_status == "pending"
    assert signatory.subject_role == "ambtenaar"
    assert signatory.source == "rule"
    assert "namens dezen" in signatory.reasoning

    addressee = by_text.get("Stefanie Öztürk")
    assert addressee is not None, f"expected the refilled name, got {list(by_text)}"
    assert addressee.review_status != "rejected"
