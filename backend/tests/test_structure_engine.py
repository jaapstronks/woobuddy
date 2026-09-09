"""Unit tests for `app.services.structure_engine`.

The engine is pure text-in / spans-out — no Deduce, no pipeline. Tests
build `ExtractionResult` stubs directly so offsets are deterministic and
assertions can pin them down.

Every fixture below runs twice, through the `shape` fixture: once as written
(PyMuPDF-shaped, blank lines and all) and once reshaped into what the browser
actually sends. The engine cuts its blocks on line boundaries, and production
text has no blank lines to cut on — see `text_shapes.py` for why that
distinction cost us a page-wide signature block.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.services.pdf_engine import ExtractionResult, PageText, TextSpan
from app.services.pipeline_engine import run_pipeline
from app.services.structure_engine import (
    StructureSpan,
    detect_structures,
    find_enclosing_structure,
    is_email_subject_line,
)
from tests.text_shapes import production_text


@pytest.fixture(params=["pymupdf", "production"])
def shape(request: pytest.FixtureRequest) -> Callable[[str], str]:
    """Return a fixture reshaper for one of the two text shapes."""
    return production_text if request.param == "production" else lambda text: text


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
    def test_single_header_block(self, shape):
        text = shape(
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

    def test_email_thread_produces_multiple_headers_and_signatures(self, shape):
        """The todo requires that a threaded reply chain emits three
        `email_header` spans and two `signature_block` spans on the
        standard fixture. This test nails both."""
        text = shape(
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

    def test_case_insensitive_and_whitespace_tolerant(self, shape):
        text = shape("  VAN :   jan@example.nl\n  AAN :   piet@example.nl\n")
        spans = detect_structures(_make_extraction(text))
        assert any(s.kind == "email_header" for s in spans)

    def test_header_block_stops_at_non_header_line(self, shape):
        text = shape(
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
    def test_signature_includes_multi_line_tail(self, shape):
        text = shape(
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

    def test_hoogachtend_trigger(self, shape):
        text = shape("Hoogachtend,\n\nMr. A. Janssen\nAdvocaat\n")
        spans = detect_structures(_make_extraction(text))
        sigs = [s for s in spans if s.kind == "signature_block"]
        assert len(sigs) == 1
        assert sigs[0].evidence.lower() == "hoogachtend"

    def test_signature_stops_at_disclaimer_url(self, shape):
        text = shape(
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
    def test_geachte_heer_jansen(self, shape):
        text = shape("Geachte heer Jansen,\n\nBijgaand het besluit.\n")
        spans = detect_structures(_make_extraction(text))
        saluts = [s for s in spans if s.kind == "salutation"]
        assert len(saluts) == 1
        assert text[saluts[0].start_char : saluts[0].end_char].startswith("Geachte heer")

    def test_beste_name(self, shape):
        text = shape("Beste Jan,\n\nDank voor je bericht.\n")
        spans = detect_structures(_make_extraction(text))
        assert any(s.kind == "salutation" for s in spans)

    def test_ls_formal_opener(self, shape):
        text = shape("L.S.\n\nHierbij doe ik u toekomen het besluit.\n")
        spans = detect_structures(_make_extraction(text))
        assert any(s.kind == "salutation" for s in spans)

    def test_salutation_extent_is_trigger_line_only(self, shape):
        text = shape("Geachte mevrouw De Jong,\nBijgaand de reactie.\n")
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
    def test_plain_body_text_returns_empty_list(self, shape):
        text = shape(
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
    def test_detection_inside_signature(self, shape):
        text = shape("Met vriendelijke groet,\n\nJan de Vries\nWethouder\n")
        spans = detect_structures(_make_extraction(text))
        start = text.index("Jan de Vries")
        end = start + len("Jan de Vries")
        enclosing = find_enclosing_structure(spans, start, end)
        assert enclosing is not None
        assert enclosing.kind == "signature_block"

    def test_detection_outside_any_structure(self, shape):
        text = shape("Jan de Vries loopt over straat.\n")
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
# Subject-line recognition inside an email header (#105)
# ---------------------------------------------------------------------------


class TestIsEmailSubjectLine:
    """`Onderwerp:`/`Subject:` lines carry prose, so the pipeline must be
    able to single them out inside a header block it otherwise trusts."""

    def test_subject_line_is_recognised(self):
        text = "Van: Pieter Bakker\nOnderwerp: Aanmeldnotitie Emmen\n"
        assert is_email_subject_line(text, text.index("Aanmeldnotitie")) is True

    def test_english_subject_line_is_recognised(self):
        text = "Van: Pieter Bakker\nSubject: Aanmeldnotitie Emmen\n"
        assert is_email_subject_line(text, text.index("Aanmeldnotitie")) is True

    def test_other_header_fields_are_not_subject_lines(self):
        text = "Van: Pieter Bakker\nAan: Klaas Jansen\nCC: Marie de Wit\n"
        for name in ("Pieter", "Klaas", "Marie"):
            assert is_email_subject_line(text, text.index(name)) is False

    def test_last_line_without_trailing_newline(self):
        text = "Van: Pieter Bakker\nOnderwerp: Aanmeldnotitie Emmen"
        assert is_email_subject_line(text, text.index("Aanmeldnotitie")) is True

    def test_prose_mentioning_onderwerp_is_not_a_subject_line(self):
        text = "Het onderwerp van de vergadering was Jan de Vries.\n"
        assert is_email_subject_line(text, text.index("Jan")) is False


# ---------------------------------------------------------------------------
# Pipeline regression — persoon inside a signature block auto-accepts.
# ---------------------------------------------------------------------------


class TestPipelineStructureIntegration:
    @pytest.mark.asyncio
    async def test_name_in_signature_block_is_auto_accepted(self, shape):
        text = shape(
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

    @pytest.mark.asyncio
    async def test_name_on_subject_line_is_not_auto_accepted(self, shape):
        """#105 — the header block runs through `Onderwerp:`, but its value
        is prose. A name-shaped hit there must stay reviewable while the
        `Van:`/`Aan:` names keep their auto-accept."""
        text = shape(
            "Van: Pieter Bakker\n"
            "Aan: Klaas Jansen\n"
            "Onderwerp: Aanmeldnotitie Jan Willem Alexander\n"
            "\n"
            "Beste collega,\n"
        )
        extraction = _make_extraction(text)

        result = await run_pipeline(extraction)

        assert any(s.kind == "email_header" for s in result.structure_spans)
        persons = [d for d in result.detections if d.entity_type == "persoon"]

        subject_start = text.index("Onderwerp:")
        on_subject = [p for p in persons if p.start_char >= subject_start]
        assert on_subject, "Expected Deduce to detect a name on the subject line"
        for p in on_subject:
            assert p.review_status == "pending"

        # The addressing fields keep the auto-accept the block is for.
        header_names = [p for p in persons if p.start_char < subject_start]
        assert len(header_names) >= 2, "Expected the Van:/Aan: names to be detected"
        for p in header_names:
            assert p.review_status == "auto_accepted"
            assert "e-mailheader" in p.reasoning
