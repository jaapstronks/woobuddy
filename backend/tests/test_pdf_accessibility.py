"""Tests for `app.services.pdf_accessibility`.

These tests pin the accessibility contract enforced by todo #48:
exported PDFs carry `/Lang (nl-NL)`, XMP metadata with title /
description / producer / dates, and an accessible Square annotation on
every redacted rectangle whose `/Contents` and `/Alt` describe the Woo
ground in Dutch. They also pin the graceful-degradation contract for
PDF/A: when Ghostscript is missing, conversion silently returns the
input unchanged with a warning log.

PyMuPDF is used as the fixture builder (already a project dep) — pikepdf
is the unit under test. Both libraries can read each other's output
losslessly.
"""

from __future__ import annotations

import io
from datetime import datetime
from unittest.mock import patch

import fitz
import pikepdf
import pytest

from app.services.pdf_accessibility import (
    add_accessible_redaction_annots,
    add_language_tag,
    build_redaction_summary,
    convert_to_pdfa,
    describe_redaction,
    post_process_for_accessibility,
    write_xmp_metadata,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_pdf(text: str = "Sentinel", with_outline: bool = False) -> bytes:
    doc = fitz.open()
    p1 = doc.new_page(width=300, height=200)
    p1.insert_text((50, 100), text, fontsize=12)
    p2 = doc.new_page(width=300, height=200)
    p2.insert_text((50, 100), f"{text} 2", fontsize=12)
    if with_outline:
        # Two-level outline so a regression that flattens it would show
        # up. PyMuPDF's set_toc takes [[level, title, page], ...].
        doc.set_toc(
            [
                [1, "Hoofdstuk 1", 1],
                [2, "Inleiding", 1],
                [1, "Hoofdstuk 2", 2],
            ]
        )
    out = doc.tobytes()
    doc.close()
    return out


@pytest.fixture
def pdf_bytes() -> bytes:
    return _build_pdf()


# ---------------------------------------------------------------------------
# describe_redaction
# ---------------------------------------------------------------------------


class TestDescribeRedaction:
    def test_known_article_returns_dutch_label(self):
        # 5.1.2e is the most-used article — pin it explicitly so a future
        # rename of the description doesn't silently drift.
        assert describe_redaction("5.1.2e") == (
            "Gelakt — Artikel 5.1.2e — Persoonlijke levenssfeer"
        )

    def test_dotted_form_resolves(self):
        # The codebase mixes "5.1.2e" and "5.1.2.e" — both must resolve
        # to the same Dutch ground.
        assert "Persoonlijke levenssfeer" in describe_redaction("5.1.2.e")

    def test_unknown_code_falls_back_to_generic(self):
        # An unknown article must NEVER produce an empty alt text — that
        # would leave a screen reader silent on the redaction.
        assert describe_redaction("9.9.9z") == ("Gelakt op grond van de Wet open overheid")

    def test_none_falls_back_to_generic(self):
        assert describe_redaction(None) == ("Gelakt op grond van de Wet open overheid")


# ---------------------------------------------------------------------------
# add_language_tag
# ---------------------------------------------------------------------------


class TestAddLanguageTag:
    def test_lang_set_on_catalog(self, pdf_bytes: bytes):
        out = add_language_tag(pdf_bytes)
        pdf = pikepdf.open(io.BytesIO(out))
        try:
            assert str(pdf.Root["/Lang"]) == "nl-NL"
        finally:
            pdf.close()

    def test_lang_overrides_existing(self, pdf_bytes: bytes):
        # Re-tagging an already-tagged PDF (e.g. a re-export) must
        # overwrite the previous language tag, not append.
        first = add_language_tag(pdf_bytes, lang="en-US")
        second = add_language_tag(first, lang="nl-NL")
        pdf = pikepdf.open(io.BytesIO(second))
        try:
            assert str(pdf.Root["/Lang"]) == "nl-NL"
        finally:
            pdf.close()


# ---------------------------------------------------------------------------
# write_xmp_metadata
# ---------------------------------------------------------------------------


class TestWriteXmpMetadata:
    def test_writes_all_supplied_fields(self, pdf_bytes: bytes):
        out = write_xmp_metadata(
            pdf_bytes,
            title="Besluit Woo-verzoek 2026-0123",
            description="Gelakt conform Art. 5.1.2e — 2026-04-25",
            create_date=datetime(2026, 4, 25, 12, 0, 0),
        )
        pdf = pikepdf.open(io.BytesIO(out))
        try:
            with pdf.open_metadata() as meta:
                assert meta["dc:title"] == "Besluit Woo-verzoek 2026-0123"
                assert meta["dc:language"] == "nl-NL"
                assert "5.1.2e" in meta["dc:description"]
                assert meta["pdf:Producer"] == "WOO Buddy"
                assert "WOO Buddy" in meta["xmp:CreatorTool"]
                assert "2026-04-25" in meta["xmp:CreateDate"]
        finally:
            pdf.close()

    def test_empty_title_is_skipped(self, pdf_bytes: bytes):
        # A blank title in the XMP block is worse than a missing one —
        # some DMSes show "" instead of falling back to the filename. The
        # service must skip rather than write empty.
        out = write_xmp_metadata(pdf_bytes, title=None)
        pdf = pikepdf.open(io.BytesIO(out))
        try:
            with pdf.open_metadata() as meta:
                assert meta.get("dc:title") in (None, "")
        finally:
            pdf.close()


# ---------------------------------------------------------------------------
# build_redaction_summary
# ---------------------------------------------------------------------------


class TestBuildRedactionSummary:
    def test_empty_redactions_returns_none(self):
        # Don't fabricate a description for a no-redaction export — the
        # caller skips writing dc:description in that case.
        assert build_redaction_summary([]) is None

    def test_aggregates_distinct_articles(self):
        out = build_redaction_summary(
            [
                {"woo_article": "5.1.2e"},
                {"woo_article": "5.1.2e"},
                {"woo_article": "5.1.1e"},
            ]
        )
        assert out is not None
        # Distinct articles, sorted, single-line, ASCII-friendly.
        assert "Art. 5.1.1e" in out
        assert "Art. 5.1.2e" in out
        # Date stamp is present (any ISO-looking yyyy-mm-dd suffices).
        assert datetime.now().date().isoformat() in out


# ---------------------------------------------------------------------------
# add_accessible_redaction_annots
# ---------------------------------------------------------------------------


class TestAccessibleAnnots:
    def test_no_redactions_returns_input_unchanged(self, pdf_bytes: bytes):
        # Cheap path: no redactions → byte-identity. Avoids re-encoding
        # the PDF for nothing.
        assert add_accessible_redaction_annots(pdf_bytes, []) == pdf_bytes

    def test_annotation_carries_dutch_label(self, pdf_bytes: bytes):
        out = add_accessible_redaction_annots(
            pdf_bytes,
            [
                {
                    "page": 0,
                    "x0": 50,
                    "y0": 100,
                    "x1": 150,
                    "y1": 120,
                    "woo_article": "5.1.2e",
                }
            ],
        )
        pdf = pikepdf.open(io.BytesIO(out))
        try:
            annots = pdf.pages[0].get("/Annots")
            assert annots is not None
            # Find the Square annotation we added.
            squares = [a for a in annots if str(a.get("/Subtype")) == "/Square"]
            assert len(squares) == 1
            sq = squares[0]
            label = "Gelakt — Artikel 5.1.2e — Persoonlijke levenssfeer"
            assert str(sq["/Contents"]) == label
            assert str(sq["/Alt"]) == label
        finally:
            pdf.close()

    def test_out_of_range_page_is_skipped(self, pdf_bytes: bytes):
        # Defensive: a redaction record with a page index past the end
        # of the document must be dropped rather than throw — the
        # frontend can produce these during multi-document edge cases.
        out = add_accessible_redaction_annots(
            pdf_bytes,
            [
                {
                    "page": 99,
                    "x0": 10,
                    "y0": 10,
                    "x1": 20,
                    "y1": 20,
                    "woo_article": "5.1.2e",
                }
            ],
        )
        pdf = pikepdf.open(io.BytesIO(out))
        try:
            for page in pdf.pages:
                annots = page.get("/Annots")
                if annots is None:
                    continue
                # No Square annotations were added — the input had none
                # and the out-of-range record was skipped.
                assert not any(str(a.get("/Subtype")) == "/Square" for a in annots)
        finally:
            pdf.close()


# ---------------------------------------------------------------------------
# convert_to_pdfa — graceful degradation
# ---------------------------------------------------------------------------


class TestConvertToPdfa:
    def test_returns_input_when_ghostscript_missing(
        self, pdf_bytes: bytes, capsys: pytest.CaptureFixture[str]
    ):
        # Self-host case: gs is not on PATH. Export must still succeed
        # and emit a warning so operators can spot the missing dep.
        # structlog writes to stdout via PrintLoggerFactory, so we read
        # captured stdout rather than the stdlib `caplog` records.
        with patch(
            "app.services.pdf_accessibility._ghostscript_path",
            return_value=None,
        ):
            out = convert_to_pdfa(pdf_bytes)
        assert out == pdf_bytes
        captured = capsys.readouterr()
        assert "ghostscript_missing" in captured.out


# ---------------------------------------------------------------------------
# Outline preservation through the full chain
# ---------------------------------------------------------------------------


class TestOutlinePreservation:
    def test_post_processing_keeps_bookmarks(self):
        # Regression guard: if a future change to the post-processing
        # chain accidentally drops the outline, screen-reader users lose
        # navigation in long besluiten.
        src = _build_pdf(with_outline=True)
        out = post_process_for_accessibility(
            src,
            redactions=[
                {
                    "page": 0,
                    "x0": 50,
                    "y0": 100,
                    "x1": 150,
                    "y1": 120,
                    "woo_article": "5.1.2e",
                }
            ],
            title="Test",
            # gs may not be installed in CI — exercising the chain end-
            # to-end without it is the realistic path for self-hosters.
            enable_pdfa=False,
        )
        pdf = fitz.open(stream=out, filetype="pdf")
        toc = pdf.get_toc()
        pdf.close()
        titles = [entry[1] for entry in toc]
        assert "Hoofdstuk 1" in titles
        assert "Hoofdstuk 2" in titles
