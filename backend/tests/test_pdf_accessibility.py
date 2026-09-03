"""Tests for `app.services.pdf_accessibility`.

These tests pin the accessibility contract enforced by todo #48 and
narrowed by #67: exported PDFs carry `/Lang (nl-NL)`, XMP metadata with
title / description / producer / dates, and an accessible Square
annotation on every redacted rectangle whose `/Contents` and `/Alt`
describe the Woo ground in Dutch and whose `/Rect` sits where the black
box does. PDF/A-2b is deliberately gone (#67), so there is nothing here
that depends on whether Ghostscript happens to be installed — the suite
means the same thing on every machine.

PyMuPDF is used as the fixture builder (already a project dep) — pikepdf
is the unit under test. Both libraries can read each other's output
losslessly.
"""

from __future__ import annotations

import io
from datetime import datetime

import fitz
import pikepdf
import pytest

from app.services.pdf_accessibility import (
    add_accessible_redaction_annots,
    add_language_tag,
    build_redaction_summary,
    describe_redaction,
    post_process_for_accessibility,
    write_xmp_metadata,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


# The fixture page is 300 wide × 200 high. Both numbers are asserted
# against directly in the /Rect tests below, so don't change them without
# recomputing the expected coordinates by hand.
_PAGE_WIDTH = 300.0
_PAGE_HEIGHT = 200.0


def _build_pdf(
    text: str = "Sentinel",
    with_outline: bool = False,
    rotate: int = 0,
) -> bytes:
    doc = fitz.open()
    p1 = doc.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
    p1.insert_text((50, 100), text, fontsize=12)
    p2 = doc.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
    p2.insert_text((50, 100), f"{text} 2", fontsize=12)
    if rotate:
        for page in doc:
            page.set_rotation(rotate)
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
# Annotation geometry — /Rect lives in user space, not viewer space
# ---------------------------------------------------------------------------


def _square_rect(pdf_bytes: bytes, page_num: int = 0) -> list[float]:
    """Return the /Rect of the single Square annotation on a page."""
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    try:
        annots = pdf.pages[page_num]["/Annots"]
        squares = [a for a in annots if str(a.get("/Subtype")) == "/Square"]
        assert len(squares) == 1
        return [float(v) for v in squares[0]["/Rect"]]
    finally:
        pdf.close()


class TestAnnotRectCoordinateSpace:
    """Until #67 the viewer-space box was written into /Rect verbatim, so
    every screen-reader annotation sat mirrored across the page's
    horizontal centre line. These tests pin the flip against a known page
    height rather than against whatever the code happens to compute."""

    # Viewer box: top edge 40pt from the top, bottom edge 60pt from the
    # top, on a 200pt-high page. In user space that is y 140..160.
    _BOX = {"page": 0, "x0": 50, "y0": 40, "x1": 150, "y1": 60, "woo_article": "5.1.2e"}

    def test_unrotated_page_flips_y_against_page_height(self):
        out = add_accessible_redaction_annots(_build_pdf(), [self._BOX])
        assert _square_rect(out) == [50.0, 140.0, 150.0, 160.0]

    def test_rect_is_not_the_raw_viewer_box(self):
        # Guard against a "fix" that computes the right numbers for the
        # wrong reason: the top-left-origin values must not survive.
        out = add_accessible_redaction_annots(_build_pdf(), [self._BOX])
        assert _square_rect(out) != [50.0, 40.0, 150.0, 60.0]

    @pytest.mark.parametrize("rotate", [0, 90, 180, 270])
    def test_matches_pymupdfs_own_inverse_transform(self, rotate: int):
        # Independent cross-check: PyMuPDF knows the viewer→user-space
        # transform for a page (it is what makes the black box land
        # correctly), so derive the expected /Rect from its inverse
        # transformation matrix instead of from our own arithmetic. If the
        # two ever disagree, the annotation and the ink have drifted apart.
        box = {"page": 0, "x0": 10, "y0": 20, "x1": 40, "y1": 60, "woo_article": "5.1.2e"}
        src = _build_pdf(rotate=rotate)
        out = add_accessible_redaction_annots(src, [box])

        doc = fitz.open(stream=src, filetype="pdf")
        try:
            page = doc[0]
            # PyMuPDF splits the transform in two: `transformation_matrix`
            # is only the y-flip against the box height and ignores
            # /Rotate entirely; `derotation_matrix` carries the quarter
            # turns. Viewer → user space is the composition of the two.
            viewer_to_user = page.derotation_matrix * (~page.transformation_matrix)
            corners = [
                fitz.Point(box["x0"], box["y0"]) * viewer_to_user,
                fitz.Point(box["x1"], box["y1"]) * viewer_to_user,
            ]
        finally:
            doc.close()
        expected = [
            min(c.x for c in corners),
            min(c.y for c in corners),
            max(c.x for c in corners),
            max(c.y for c in corners),
        ]
        assert _square_rect(out) == pytest.approx(expected, abs=0.01)

    @pytest.mark.parametrize(
        ("rotate", "expected"),
        [
            # /Rotate 90: the viewer's top-left is the page's bottom-left,
            # so the axes swap. Viewer (10,20)-(40,60) → user (20,10)-(60,40).
            (90, [20.0, 10.0, 60.0, 40.0]),
            # /Rotate 180: both axes mirror. urx=300, lly=0.
            (180, [260.0, 20.0, 290.0, 60.0]),
            # /Rotate 270: axes swap the other way. urx=300, ury=200.
            (270, [240.0, 160.0, 280.0, 190.0]),
            (0, [10.0, 140.0, 40.0, 180.0]),
        ],
    )
    def test_rotated_pages(self, rotate: int, expected: list[float]):
        # Scanner output routinely carries /Rotate. pdf.js and PyMuPDF both
        # hand us rotation-applied viewer coordinates; a PDF /Rect is
        # rotation-*un*applied, so each quarter turn needs its own mapping.
        box = {"page": 0, "x0": 10, "y0": 20, "x1": 40, "y1": 60, "woo_article": "5.1.2e"}
        out = add_accessible_redaction_annots(_build_pdf(rotate=rotate), [box])
        assert _square_rect(out) == expected


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
        )
        pdf = fitz.open(stream=out, filetype="pdf")
        toc = pdf.get_toc()
        pdf.close()
        titles = [entry[1] for entry in toc]
        assert "Hoofdstuk 1" in titles
        assert "Hoofdstuk 2" in titles


# ---------------------------------------------------------------------------
# /Lang survives the whole chain
# ---------------------------------------------------------------------------


class TestChainKeepsLanguageTag:
    """`/Lang` used to be set mid-chain and then wiped by the Ghostscript
    step that ran last (#67). It is the single highest-impact
    accessibility win here, so it gets asserted on the *final* bytes —
    the same thing `test_export_api` checks through the endpoint."""

    def test_lang_present_on_final_bytes_with_redactions(self):
        out = post_process_for_accessibility(
            _build_pdf(),
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
            title="Besluit Woo-verzoek 2026-0123",
        )
        pdf = pikepdf.open(io.BytesIO(out))
        try:
            assert str(pdf.Root["/Lang"]) == "nl-NL"
            with pdf.open_metadata() as meta:
                assert meta["dc:title"] == "Besluit Woo-verzoek 2026-0123"
        finally:
            pdf.close()

    def test_lang_present_on_final_bytes_without_redactions(self):
        out = post_process_for_accessibility(_build_pdf(), redactions=[])
        pdf = pikepdf.open(io.BytesIO(out))
        try:
            assert str(pdf.Root["/Lang"]) == "nl-NL"
        finally:
            pdf.close()
