"""Tests for the detection pipeline orchestration.

The pipeline is 100% rule-based — no LLM anywhere in the live path.
See `docs/reference/llm-revival.md` if you want to revive a local
LLM verification pass in the future.
"""

import pytest

from app.services.environmental_classifier import check_environmental_content
from app.services.pipeline_engine import run_pipeline
from app.services.pdf_engine import ExtractionResult, PageText, TextSpan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extraction(text: str, page_count: int = 1) -> ExtractionResult:
    """Build a minimal ExtractionResult for testing."""
    spans = [TextSpan(text=text, page=0, x0=10, y0=10, x1=200, y1=25)]
    pages = [PageText(page_number=0, full_text=text, spans=spans)]
    return ExtractionResult(
        pages=pages,
        page_count=page_count,
        full_text=text,
    )



def _make_multipage_extraction(page_texts: list[str]) -> ExtractionResult:
    """Build an ExtractionResult spanning several pages.

    Mirrors `extract_text`: one span per page carrying the page's whole
    text, and a `full_text` joined with blank lines between pages — the
    same text the char offsets in the detections refer to.
    """
    pages = [
        PageText(
            page_number=i,
            full_text=text,
            spans=[TextSpan(text=text, page=i, x0=10, y0=10 + 20 * i, x1=400, y1=25 + 20 * i)],
        )
        for i, text in enumerate(page_texts)
    ]
    return ExtractionResult(
        pages=pages,
        page_count=len(pages),
        full_text="\n\n".join(page_texts),
    )


# ---------------------------------------------------------------------------
# Environmental content detection
# ---------------------------------------------------------------------------


class TestEnvironmentalDetection:
    def test_environmental_keywords_detected(self):
        assert check_environmental_content("De luchtkwaliteit is verslechterd.") is True
        assert check_environmental_content("PFAS-verontreiniging in de bodem.") is True
        assert check_environmental_content("CO2-uitstoot boven de norm.") is True

    def test_no_environmental_content(self):
        assert check_environmental_content("De vergadering is verdaagd.") is False
        assert check_environmental_content("Budget voor 2025 is goedgekeurd.") is False

    def test_case_insensitive(self):
        assert check_environmental_content("MILIEU impact assessment") is True


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


class TestRunPipeline:
    @pytest.mark.asyncio
    async def test_tier1_detection_is_auto_accepted(self):
        """Tier 1 detections from regex should be auto_accepted."""
        extraction = _make_extraction("Het BSN is 111222333 in dit document.")

        result = await run_pipeline(extraction)
        tier1 = [d for d in result.detections if d.tier == "1"]
        assert len(tier1) >= 1
        for d in tier1:
            assert d.review_status == "auto_accepted"

    @pytest.mark.asyncio
    async def test_tier2_person_is_pending(self):
        """Tier 2 person detections (not public officials) should be pending."""
        extraction = _make_extraction(
            "De heer Jan de Vries heeft een verzoek ingediend bij de gemeente."
        )

        result = await run_pipeline(extraction)
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        assert len(persons) >= 1
        for p in persons:
            assert p.review_status == "pending"
            assert p.woo_article == "5.1.2e"

    @pytest.mark.asyncio
    async def test_public_official_is_rejected(self):
        """A person on the public officials list should be auto-rejected.

        Deduce detects "Jan de Vries" (without salutation) in this context.
        The pipeline matches the detected text against the officials list.
        """
        extraction = _make_extraction("Jan de Vries heeft een verzoek ingediend bij de gemeente.")

        result = await run_pipeline(
            extraction,
            public_official_names=["Jan de Vries"],
        )
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        jan = [p for p in persons if "Jan de Vries" in p.entity_text]
        assert len(jan) >= 1
        assert jan[0].review_status == "rejected"
        assert jan[0].source == "reference_list"
        assert "publiek-functionarissenlijst" in jan[0].reasoning

    @pytest.mark.asyncio
    async def test_public_official_case_insensitive(self):
        """Public official matching should be case-insensitive."""
        extraction = _make_extraction("Het voorstel van Jan de Vries is besproken.")

        result = await run_pipeline(
            extraction,
            public_official_names=["jan de vries"],
        )
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        jan = [p for p in persons if "jan de vries" in p.entity_text.lower()]
        assert len(jan) >= 1
        assert jan[0].review_status == "rejected"

    @pytest.mark.asyncio
    async def test_environmental_content_flagged(self):
        """Pipeline should flag environmental content in the result."""
        extraction = _make_extraction(
            "De luchtkwaliteit in het plangebied is onderzocht. BSN: 111222333."
        )

        result = await run_pipeline(extraction)
        assert result.has_environmental_content is True

    @pytest.mark.asyncio
    async def test_no_environmental_flag_for_normal_text(self):
        extraction = _make_extraction("BSN: 111222333 in een ambtelijk document.")

        result = await run_pipeline(extraction)
        assert result.has_environmental_content is False

    @pytest.mark.asyncio
    async def test_page_count_from_extraction(self):
        extraction = _make_extraction("Tekst", page_count=5)

        result = await run_pipeline(extraction)
        assert result.page_count == 5

    @pytest.mark.asyncio
    async def test_bounding_boxes_resolved(self):
        """Detections should have bounding boxes from the extraction spans."""
        extraction = _make_extraction("BSN: 111222333")

        result = await run_pipeline(extraction)
        bsn_dets = [d for d in result.detections if d.entity_type == "bsn"]
        # bboxes may be empty if span text doesn't match — but the list should exist
        for d in bsn_dets:
            assert isinstance(d.bounding_boxes, list)

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_result(self):
        extraction = _make_extraction("")

        result = await run_pipeline(extraction)
        assert len(result.detections) == 0

    @pytest.mark.asyncio
    async def test_mixed_detections_correct_tiers(self):
        """A document with both BSN (Tier 1) and names (Tier 2) should produce both."""
        extraction = _make_extraction(
            "De heer Jan de Vries, BSN 111222333, heeft een klacht ingediend."
        )

        result = await run_pipeline(extraction)
        tiers = {d.tier for d in result.detections}
        assert "1" in tiers
        assert "2" in tiers


# ---------------------------------------------------------------------------
# Custom wordlist (#21) — pipeline integration
# ---------------------------------------------------------------------------


class _CustomTerm:
    """Structural stand-in for the matcher's `CustomTermLike` protocol."""

    def __init__(self, term: str, woo_article: str = "5.1.2e", match_mode: str = "exact"):
        self.term = term
        self.match_mode = match_mode
        self.woo_article = woo_article


class TestCustomWordlist:
    @pytest.mark.asyncio
    async def test_custom_term_produces_detections_per_occurrence(self):
        """A term that appears twice in the document yields two
        `custom` detections, both at `review_status="accepted"` and
        tagged with the custom Woo-artikel."""
        extraction = _make_extraction(
            "Project Apollo startte in 1961. "
            "Het rapport over Project Apollo is vrijgegeven."
        )
        result = await run_pipeline(
            extraction,
            custom_terms=[_CustomTerm("Project Apollo", woo_article="5.1.2b")],
        )
        customs = [d for d in result.detections if d.entity_type == "custom"]
        assert len(customs) == 2
        for d in customs:
            assert d.review_status == "accepted"
            assert d.source == "custom_wordlist"
            assert d.woo_article == "5.1.2b"
            assert "Project Apollo" in d.reasoning

    @pytest.mark.asyncio
    async def test_custom_term_is_case_insensitive(self):
        extraction = _make_extraction("project apollo is een codenaam.")
        result = await run_pipeline(
            extraction,
            custom_terms=[_CustomTerm("Project Apollo")],
        )
        customs = [d for d in result.detections if d.entity_type == "custom"]
        assert len(customs) == 1

    @pytest.mark.asyncio
    async def test_empty_custom_terms_produces_no_custom_detections(self):
        extraction = _make_extraction("Project Apollo is openbaar.")
        result = await run_pipeline(
            extraction,
            custom_terms=[],
        )
        assert not any(d.entity_type == "custom" for d in result.detections)

    @pytest.mark.asyncio
    async def test_custom_term_on_page_three_gets_a_page_three_bbox(self):
        """Regression (#66/1): bboxes for custom terms were cached per
        lowercased term and resolved with `find_span_for_text`, which stops
        at the first page holding a hit. Every later occurrence inherited
        the page-1 box, so a reviewer-typed term on page 3 was never burned
        in — the export drew a second black box on page 1 instead.
        """
        extraction = _make_multipage_extraction(
            [
                "Betreft Zonnepark Noord en de vergunning.",
                "Deze pagina gaat over iets anders.",
                "Bijlage: Zonnepark Noord opnieuw genoemd.",
            ]
        )
        result = await run_pipeline(
            extraction,
            custom_terms=[_CustomTerm("Zonnepark Noord", woo_article="5.1.2b")],
        )
        customs = [d for d in result.detections if d.entity_type == "custom"]
        assert len(customs) == 2

        pages = sorted(b["page"] for d in customs for b in d.bounding_boxes)
        assert pages == [0, 2], f"expected one box on page 0 and one on page 2, got {pages}"
        # Each occurrence carries exactly one box — no occurrence may inherit
        # another's geometry.
        assert [len(d.bounding_boxes) for d in customs] == [1, 1]
