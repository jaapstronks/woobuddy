"""Unit tests for `app.services.structure_engine`.

The engine is pure text-in / spans-out — no Deduce, no pipeline. Tests
build `ExtractionResult` stubs directly so offsets are deterministic and
assertions can pin them down.
"""

from __future__ import annotations

import pytest

from app.services.pipeline_engine import run_pipeline
from app.services.pdf_engine import ExtractionResult, PageText, TextSpan
from app.services.structure_engine import (
    StructureSpan,
    detect_structures,
    find_enclosing_structure,
)


def _make_extraction(text: str) -> ExtractionResult:
    """Build a minimal ExtractionResult with one page of text.

    The single TextSpan is wide enough that `find_span_for_text` can map
    any detection bbox for the pipeline-level regression test further
    down; the structure engine itself only reads `full_text`.
    """
    spans = [TextSpan(text=text, page=0, x0=10, y0=10, x1=800, y1=1200)]
    return ExtractionResult(
        pages=[PageText(page_number=0, full_text=text, spans=spans)],
        page_count=1,
        full_text=text,
    )


def _kinds(spans: list[StructureSpan]) -> list[str]:
    return [s.kind for s in spans]


# ---------------------------------------------------------------------------
# Email header detection
# ---------------------------------------------------------------------------


class TestEmailHeaderDetection:
    def test_single_header_block(self):
        text = (
            "Van: jan@example.nl\n"
            "Aan: piet@example.nl\n"
            "Onderwerp: Woo-verzoek\n"
            "\n"
            "Beste Piet,\n"
            "\n"
            "Zie bijlage.\n"
        )
        spans = detect_structures(_make_extraction(text))
        headers = [s for s in spans if s.kind == "email_header"]
        assert len(headers) == 1
        # The block starts at the first Van: line and ends at the Onderwerp:
        # line (exclusive of the blank line that terminates it).
        block = headers[0]
        assert text[block.start_char : block.end_char].startswith("Van:")
        assert "Onderwerp: Woo-verzoek" in text[block.start_char : block.end_char]
        assert "Beste Piet" not in text[block.start_char : block.end_char]
        assert block.evidence.lower().startswith("van:")

    def test_email_thread_produces_multiple_headers_and_signatures(self):
        """The todo requires that a threaded reply chain emits three
        `email_header` spans and two `signature_block` spans on the
        standard fixture. This test nails both."""
        text = (
            "Van: piet@example.nl\n"
            "Aan: jan@example.nl\n"
            "Onderwerp: Re: Woo-verzoek\n"
            "\n"
            "Beste Jan,\n"
            "\n"
            "Dank voor je vraag.\n"
            "\n"
            "Met vriendelijke groet,\n"
            "\n"
            "Piet Janssen\n"
            "Afdeling Communicatie\n"
            "\n"
            "Van: jan@example.nl\n"
            "Aan: piet@example.nl\n"
            "Onderwerp: Woo-verzoek\n"
            "\n"
            "Hoi Piet,\n"
            "\n"
            "Zie bijlage.\n"
            "\n"
            "Met vriendelijke groet,\n"
            "\n"
            "Jan de Vries\n"
            "\n"
            "Van: noreply@example.nl\n"
            "Aan: jan@example.nl\n"
            "Onderwerp: Bevestiging\n"
            "\n"
            "Uw verzoek is ontvangen.\n"
        )
        spans = detect_structures(_make_extraction(text))
        kinds = _kinds(spans)
        assert kinds.count("email_header") == 3
        assert kinds.count("signature_block") == 2

    def test_case_insensitive_and_whitespace_tolerant(self):
        text = "  VAN :   jan@example.nl\n  AAN :   piet@example.nl\n"
        spans = detect_structures(_make_extraction(text))
        assert any(s.kind == "email_header" for s in spans)

    def test_header_block_stops_at_non_header_line(self):
        text = (
            "Van: jan@example.nl\n"
            "Aan: piet@example.nl\n"
            "Dit is gewoon tekst zonder dubbele punt.\n"
            "Onderwerp: later\n"
        )
        spans = detect_structures(_make_extraction(text))
        headers = [s for s in spans if s.kind == "email_header"]
        # The first block terminates at the prose line so Onderwerp is
        # not pulled into it. (Scanning then restarts and may emit a
        # second block from the stray Onderwerp: line, which is fine —
        # the assertion is specifically about the block-extent rule.)
        first_block_text = text[headers[0].start_char : headers[0].end_char]
        assert "Van:" in first_block_text
        assert "Aan:" in first_block_text
        assert "Onderwerp" not in first_block_text
        assert "zonder dubbele punt" not in first_block_text


# ---------------------------------------------------------------------------
# Signature block detection
# ---------------------------------------------------------------------------


class TestSignatureBlockDetection:
    def test_signature_includes_multi_line_tail(self):
        text = (
            "Het verzoek is in behandeling.\n"
            "\n"
            "Met vriendelijke groet,\n"
            "\n"
            "Jan de Vries\n"
            "Wethouder\n"
            "Gemeente Utrecht\n"
            "06-12345678\n"
            "jan@example.nl\n"
        )
        spans = detect_structures(_make_extraction(text))
        sigs = [s for s in spans if s.kind == "signature_block"]
        assert len(sigs) == 1
        body = text[sigs[0].start_char : sigs[0].end_char]
        assert "Met vriendelijke groet" in body
        assert "Jan de Vries" in body
        # 6-line cap: phone + email fit, anything further would be cut.
        assert "jan@example.nl" in body

    def test_hoogachtend_trigger(self):
        text = "Hoogachtend,\n\nMr. A. Janssen\nAdvocaat\n"
        spans = detect_structures(_make_extraction(text))
        sigs = [s for s in spans if s.kind == "signature_block"]
        assert len(sigs) == 1
        assert sigs[0].evidence.lower() == "hoogachtend"

    def test_signature_stops_at_disclaimer_url(self):
        text = (
            "Met vriendelijke groet,\n"
            "\n"
            "Jan de Vries\n"
            "https://example.nl/disclaimer\n"
            "Disclaimer text beyond this line.\n"
        )
        spans = detect_structures(_make_extraction(text))
        sigs = [s for s in spans if s.kind == "signature_block"]
        assert len(sigs) == 1
        body = text[sigs[0].start_char : sigs[0].end_char]
        assert "Jan de Vries" in body
        assert "disclaimer" not in body.lower()


# ---------------------------------------------------------------------------
# Salutation detection
# ---------------------------------------------------------------------------


class TestSalutationDetection:
    def test_geachte_heer_jansen(self):
        text = "Geachte heer Jansen,\n\nBijgaand het besluit.\n"
        spans = detect_structures(_make_extraction(text))
        saluts = [s for s in spans if s.kind == "salutation"]
        assert len(saluts) == 1
        assert text[saluts[0].start_char : saluts[0].end_char].startswith("Geachte heer")

    def test_beste_name(self):
        text = "Beste Jan,\n\nDank voor je bericht.\n"
        spans = detect_structures(_make_extraction(text))
        assert any(s.kind == "salutation" for s in spans)

    def test_ls_formal_opener(self):
        text = "L.S.\n\nHierbij doe ik u toekomen het besluit.\n"
        spans = detect_structures(_make_extraction(text))
        assert any(s.kind == "salutation" for s in spans)

    def test_salutation_extent_is_trigger_line_only(self):
        text = "Geachte mevrouw De Jong,\nBijgaand de reactie.\n"
        spans = detect_structures(_make_extraction(text))
        saluts = [s for s in spans if s.kind == "salutation"]
        assert len(saluts) == 1
        body = text[saluts[0].start_char : saluts[0].end_char]
        assert "Geachte mevrouw De Jong," in body
        assert "Bijgaand" not in body


# ---------------------------------------------------------------------------
# No-structure fixture
# ---------------------------------------------------------------------------


class TestNoStructure:
    def test_plain_body_text_returns_empty_list(self):
        text = (
            "Het college heeft besloten tot uitbreiding van de subsidieregeling. "
            "Het besluit wordt ter inzage gelegd bij de balie van het stadhuis.\n"
        )
        spans = detect_structures(_make_extraction(text))
        assert spans == []

    def test_empty_text(self):
        assert detect_structures(_make_extraction("")) == []


# ---------------------------------------------------------------------------
# find_enclosing_structure
# ---------------------------------------------------------------------------


class TestFindEnclosingStructure:
    def test_detection_inside_signature(self):
        text = "Met vriendelijke groet,\n\nJan de Vries\nWethouder\n"
        spans = detect_structures(_make_extraction(text))
        start = text.index("Jan de Vries")
        end = start + len("Jan de Vries")
        enclosing = find_enclosing_structure(spans, start, end)
        assert enclosing is not None
        assert enclosing.kind == "signature_block"

    def test_detection_outside_any_structure(self):
        text = "Jan de Vries loopt over straat.\n"
        spans = detect_structures(_make_extraction(text))
        start = text.index("Jan de Vries")
        end = start + len("Jan de Vries")
        assert find_enclosing_structure(spans, start, end) is None

    def test_email_header_preferred_over_salutation(self):
        # Build a synthetic span list where the same range is enclosed
        # by both an email_header and a salutation. The helper should
        # prefer the broader structural kind.
        salutation = StructureSpan(
            kind="salutation",
            start_char=0,
            end_char=40,
            confidence=0.85,
            evidence="Geachte heer",
        )
        header = StructureSpan(
            kind="email_header",
            start_char=0,
            end_char=80,
            confidence=0.95,
            evidence="Van:",
        )
        assert find_enclosing_structure([salutation, header], 5, 15) is header
        assert find_enclosing_structure([header, salutation], 5, 15) is header


# ---------------------------------------------------------------------------
# Pipeline regression — persoon inside a signature block auto-accepts.
# ---------------------------------------------------------------------------


class TestPipelineStructureIntegration:
    @pytest.mark.asyncio
    async def test_name_in_signature_block_is_auto_accepted(self):
        text = (
            "Geachte heer Jansen,\n"
            "\n"
            "Bijgaand het besluit op uw Woo-verzoek.\n"
            "\n"
            "Met vriendelijke groet,\n"
            "\n"
            "Karel Bakker\n"
            "Beleidsmedewerker\n"
        )
        extraction = _make_extraction(text)

        result = await run_pipeline(extraction)

        # The structure pass must have run and produced spans.
        assert any(s.kind == "signature_block" for s in result.structure_spans)
        assert any(s.kind == "salutation" for s in result.structure_spans)

        # The Tier 2 name inside the signature block auto-accepts with
        # the "Naam in handtekeningblok" reason. We don't assert on the
        # salutation name ("Jansen") because Deduce may or may not emit
        # a span for it depending on the version — the signature name
        # is the stable assertion.
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        karel = [p for p in persons if "Karel" in p.entity_text]
        assert karel, "Expected Deduce to detect the name inside the signature"
        assert any(p.review_status == "auto_accepted" for p in karel)
        assert any("handtekeningblok" in p.reasoning for p in karel)
