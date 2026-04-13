"""Tests for the Tier 2 LLM verification pass in run_pipeline.

The LLM layer is **dormant by default** (pivot 2026-04 — see
`docs/todo/done/35-deactivate-llm.md` and `backend/app/llm/README.md`).
These tests exercise the parked revival path: they inject a fake
`LLMProvider` and call `run_pipeline(..., use_llm_verification=True)`
explicitly, so the dormant default never hides a regression in the
behavior we'd restore if an operator flipped the flag.

Tests run offline — no Ollama required. They verify the three branches
that matter for the review UX when the layer is active:

1. `not_a_person` → detection is dropped entirely.
2. `public_official` + `should_redact=False` → detection ends up
   `rejected` (i.e. "don't suggest redacting this").
3. `citizen`/`civil_servant` → detection stays `pending` with the
   LLM's reasoning surfaced to the reviewer.
4. LLM failures fall back to `pending` with the Deduce reasoning.
"""

from unittest.mock import patch

import pytest

from app.llm.provider import ContentAnalysisResult, LLMProvider, RoleClassification
from app.services.llm_engine import run_pipeline
from app.services.pdf_engine import ExtractionResult, PageText, TextSpan


class _FakeProvider(LLMProvider):
    """Fake LLM provider driven by a substring-matched verdict table.

    We match verdicts by substring (not equality) because Deduce's
    exact tokenization of person names is implementation-detail: it
    might return "Jan de Vries", "Klager Jan de Vries", or
    "Jan de Vries heeft" depending on context, and the tests should
    not have to care which.
    """

    def __init__(self, verdicts: dict[str, RoleClassification] | None = None) -> None:
        self.verdicts = verdicts or {}
        self.calls: list[tuple[str, str]] = []
        self.raise_on: set[str] = set()

    async def classify_role(
        self,
        person_name: str,
        surrounding_context: str,
        document_type: str | None = None,
    ) -> RoleClassification:
        self.calls.append((person_name, surrounding_context))
        for trigger in self.raise_on:
            if trigger in person_name:
                raise RuntimeError("simulated Ollama failure")
        for key, verdict in self.verdicts.items():
            if key in person_name:
                return verdict
        return RoleClassification(
            role="citizen",
            should_redact=True,
            confidence=0.7,
            reason_nl="Standaard burger — test fallback.",
        )

    async def analyze_content(
        self,
        passage: str,
        document_type: str | None = None,
        surrounding_context: str | None = None,
    ) -> ContentAnalysisResult:
        return ContentAnalysisResult()

    async def health_check(self) -> bool:
        return True


def _make_extraction(text: str) -> ExtractionResult:
    spans = [TextSpan(text=text, page=0, x0=10, y0=10, x1=400, y1=25)]
    pages = [PageText(page_number=0, full_text=text, spans=spans)]
    return ExtractionResult(pages=pages, page_count=1, full_text=text)


@pytest.mark.asyncio
async def test_llm_drops_non_person_detections():
    """If the LLM says the NER hit is not actually a person, the
    detection should be removed from the review list entirely."""
    extraction = _make_extraction("De heer Jan de Vries bezocht het nieuwe gebouw.")
    provider = _FakeProvider(
        verdicts={
            "Jan de Vries": RoleClassification(
                role="not_a_person",
                should_redact=False,
                confidence=0.9,
                reason_nl="Dit is geen persoonsnaam.",
            ),
        }
    )

    with patch("app.llm.get_llm_provider", return_value=provider):
        result = await run_pipeline(extraction, use_llm_verification=True)

    persons = [d for d in result.detections if d.entity_type == "persoon"]
    assert persons == [], "Detections classified as not_a_person must not appear in the result"
    assert len(provider.calls) >= 1, "LLM should have been called for the Deduce hit"


@pytest.mark.asyncio
async def test_llm_public_official_marked_rejected():
    """`public_official` with should_redact=False should surface as
    `rejected` (the suggestion is rejected — keep the name visible)."""
    extraction = _make_extraction("Burgemeester Jan de Vries opende de vergadering.")
    provider = _FakeProvider(
        verdicts={
            "Jan de Vries": RoleClassification(
                role="public_official",
                should_redact=False,
                confidence=0.95,
                reason_nl="Burgemeester in officiële hoedanigheid.",
            ),
        }
    )

    with patch("app.llm.get_llm_provider", return_value=provider):
        result = await run_pipeline(extraction, use_llm_verification=True)

    persons = [d for d in result.detections if d.entity_type == "persoon"]
    assert len(persons) >= 1
    jan = next(p for p in persons if "Jan de Vries" in p.entity_text)
    assert jan.review_status == "rejected"
    assert jan.source == "llm"
    assert "officiële" in jan.reasoning or "Burgemeester" in jan.reasoning


@pytest.mark.asyncio
async def test_llm_citizen_kept_pending_with_reasoning():
    """Citizens stay `pending` but with the LLM's reasoning instead
    of the generic Deduce string."""
    extraction = _make_extraction("Klager Jan de Vries diende een bezwaar in.")
    provider = _FakeProvider(
        verdicts={
            "Jan de Vries": RoleClassification(
                role="citizen",
                should_redact=True,
                confidence=0.88,
                reason_nl="Klager — privépersoon, moet gelakt worden.",
            ),
        }
    )

    with patch("app.llm.get_llm_provider", return_value=provider):
        result = await run_pipeline(extraction, use_llm_verification=True)

    persons = [d for d in result.detections if d.entity_type == "persoon"]
    jan = next(p for p in persons if "Jan de Vries" in p.entity_text)
    assert jan.review_status == "pending"
    assert jan.source == "llm"
    assert "privépersoon" in jan.reasoning or "Klager" in jan.reasoning


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_deduce_reasoning():
    """If the LLM raises, the detection must still appear — pending,
    with the original Deduce reasoning, so the user can still review
    it manually."""
    extraction = _make_extraction("Jan de Vries heeft een verzoek ingediend.")
    provider = _FakeProvider()
    provider.raise_on.add("Jan de Vries")

    with patch("app.llm.get_llm_provider", return_value=provider):
        result = await run_pipeline(extraction, use_llm_verification=True)

    persons = [d for d in result.detections if d.entity_type == "persoon"]
    assert len(persons) >= 1, "LLM failure must not make detections disappear"
    jan = next(p for p in persons if "Jan de Vries" in p.entity_text)
    assert jan.review_status == "pending"
    assert jan.source == "deduce"  # fallback path preserves source


@pytest.mark.asyncio
async def test_llm_not_called_when_disabled():
    """use_llm_verification=False should skip the LLM entirely."""
    extraction = _make_extraction("Jan de Vries heeft een verzoek ingediend.")
    provider = _FakeProvider()

    with patch("app.llm.get_llm_provider", return_value=provider):
        await run_pipeline(extraction, use_llm_verification=False)

    assert provider.calls == [], "LLM must not be called when use_llm_verification=False"


@pytest.mark.asyncio
async def test_public_officials_list_short_circuits_llm():
    """Names on the public officials list should skip the LLM call
    entirely — no point burning inference on a known answer."""
    extraction = _make_extraction("Jan de Vries heeft het besluit ondertekend.")
    provider = _FakeProvider()

    with patch("app.llm.get_llm_provider", return_value=provider):
        result = await run_pipeline(
            extraction,
            public_official_names=["Jan de Vries"],
            use_llm_verification=True,
        )

    # No LLM calls for Jan — he's on the list. Other detections might
    # still trigger the LLM though, so we check that Jan specifically
    # doesn't appear in provider.calls.
    called_names = {name for name, _ in provider.calls}
    assert "Jan de Vries" not in called_names

    persons = [d for d in result.detections if d.entity_type == "persoon"]
    jan = next(p for p in persons if "Jan de Vries" in p.entity_text)
    assert jan.review_status == "rejected"
    assert "publieke functionarissen" in jan.reasoning
