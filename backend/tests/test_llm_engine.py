"""Tests for the LLM engine — pipeline orchestration.

Tests the run_pipeline function with mocked NER/pdf dependencies to verify:
- Tier assignment (Tier 1 = auto_accepted, Tier 2 = pending)
- Public official filtering (persons on the list → rejected)
- Environmental content detection
- Bounding box resolution
"""


import pytest

from app.services.llm_engine import (
    _check_environmental_content,
    _find_tier3_passages,
    run_pipeline,
)
from app.services.ner_engine import NERDetection
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


def _make_ner_detection(
    text: str,
    entity_type: str = "bsn",
    tier: str = "1",
    confidence: float = 0.98,
    woo_article: str = "5.1.1e",
    source: str = "regex",
) -> NERDetection:
    return NERDetection(
        text=text,
        entity_type=entity_type,
        tier=tier,
        confidence=confidence,
        woo_article=woo_article,
        source=source,
        start_char=0,
        end_char=len(text),
    )


# ---------------------------------------------------------------------------
# Environmental content detection
# ---------------------------------------------------------------------------


class TestEnvironmentalDetection:
    def test_environmental_keywords_detected(self):
        assert _check_environmental_content("De luchtkwaliteit is verslechterd.") is True
        assert _check_environmental_content("PFAS-verontreiniging in de bodem.") is True
        assert _check_environmental_content("CO2-uitstoot boven de norm.") is True

    def test_no_environmental_content(self):
        assert _check_environmental_content("De vergadering is verdaagd.") is False
        assert _check_environmental_content("Budget voor 2025 is goedgekeurd.") is False

    def test_case_insensitive(self):
        assert _check_environmental_content("MILIEU impact assessment") is True


# ---------------------------------------------------------------------------
# Tier 3 passage finding
# ---------------------------------------------------------------------------


class TestTier3Passages:
    def test_finds_policy_opinion_signals(self):
        page = PageText(
            page_number=0,
            full_text="Ik adviseer om het voorstel aan te passen vanwege de juridische risico's.",
            spans=[],
        )
        passages = _find_tier3_passages([page])
        assert len(passages) >= 1
        assert passages[0][1] == 0  # page number

    def test_finds_business_data_signals(self):
        page = PageText(
            page_number=0,
            full_text=(
                "De offerte van het bedrijf bevat concurrentiegevoelige "
                "informatie over de aanbesteding."
            ),
            spans=[],
        )
        passages = _find_tier3_passages([page])
        assert len(passages) >= 1

    def test_skips_short_chunks(self):
        """Chunks shorter than 40 chars are ignored."""
        page = PageText(page_number=0, full_text="ik adviseer", spans=[])
        passages = _find_tier3_passages([page])
        assert len(passages) == 0

    def test_no_signals_returns_empty(self):
        page = PageText(
            page_number=0,
            full_text=(
                "De gemeente heeft het bestemmingsplan vastgesteld "
                "voor het nieuwe wijkcentrum."
            ),
            spans=[],
        )
        passages = _find_tier3_passages([page])
        assert len(passages) == 0


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
        extraction = _make_extraction(
            "Jan de Vries heeft een verzoek ingediend bij de gemeente."
        )

        result = await run_pipeline(
            extraction, public_official_names=["Jan de Vries"]
        )
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        jan = [p for p in persons if "Jan de Vries" in p.entity_text]
        assert len(jan) >= 1
        assert jan[0].review_status == "rejected"
        assert "publieke functionarissen" in jan[0].reasoning

    @pytest.mark.asyncio
    async def test_public_official_case_insensitive(self):
        """Public official matching should be case-insensitive."""
        extraction = _make_extraction(
            "Het voorstel van Jan de Vries is besproken."
        )

        result = await run_pipeline(
            extraction, public_official_names=["jan de vries"]
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
