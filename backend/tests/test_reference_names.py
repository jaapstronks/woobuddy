"""Tests for the per-document reference-names feature (#17).

Covers two layers:

- Service-level: `normalize_reference_name` and the pipeline's
  reference-list match path. These are the same building blocks the CRUD
  layer uses, so any normalization regression caught here also protects
  the HTTP surface.
- HTTP-level: the /api/documents/{id}/reference-names CRUD routes. These
  verify end-to-end behavior (normalization, conflict handling, idempotent
  delete) without having to stand up the full analyze flow.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.schemas import Document
from app.services.pipeline_engine import run_pipeline
from app.services.name_engine import normalize_reference_name
from app.services.pdf_engine import ExtractionResult, PageText, TextSpan


def _make_extraction(text: str) -> ExtractionResult:
    spans = [TextSpan(text=text, page=0, x0=10, y0=10, x1=400, y1=25)]
    pages = [PageText(page_number=0, full_text=text, spans=spans)]
    return ExtractionResult(pages=pages, page_count=1, full_text=text)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


class TestNormalizeReferenceName:
    def test_lowercases(self):
        assert normalize_reference_name("Jan de Vries") == "jan de vries"

    def test_strips_diacritics(self):
        assert normalize_reference_name("Adrián García") == "adrian garcia"

    def test_keeps_tussenvoegsels(self):
        # Per the #17 spec: tussenvoegsels are kept. Strip them only in the
        # name-list scoring path (#12), not in the reference-list match.
        assert normalize_reference_name("De Vries") == "de vries"
        assert normalize_reference_name("Van den Berg") == "van den berg"

    def test_collapses_whitespace(self):
        assert normalize_reference_name("Jan  de   Vries") == "jan de vries"
        assert normalize_reference_name("  Jan de Vries  ") == "jan de vries"

    def test_empty_and_whitespace(self):
        assert normalize_reference_name("") == ""
        assert normalize_reference_name("   ") == ""

    def test_case_and_whitespace_both_ways(self):
        # The acceptance criterion: "Typing 'de Vries' and later seeing
        # 'De Vries' in a document produces a match." Normalization must
        # produce the same string for both inputs.
        assert normalize_reference_name("de Vries") == normalize_reference_name("De Vries")


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


class TestPipelineReferenceList:
    @pytest.mark.asyncio
    async def test_reference_list_flips_detection_to_rejected(self):
        """A `persoon` span whose normalized text is on the reference list
        must come back rejected with `source="reference_list"`."""
        extraction = _make_extraction(
            "Jan de Vries heeft twee brieven ondertekend namens de gemeente. "
            "Ook Jan de Vries was bij de vergadering."
        )

        result = await run_pipeline(
            extraction,
            public_official_names=["Jan de Vries"],
        )
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        jan = [p for p in persons if "Jan de Vries" in p.entity_text]
        assert len(jan) >= 1
        for p in jan:
            assert p.review_status == "rejected"
            assert p.source == "reference_list"
            assert p.subject_role == "publiek_functionaris"

    @pytest.mark.asyncio
    async def test_reference_list_case_insensitive(self):
        """'de Vries' typed in the panel must match 'De Vries' in the document.

        Uses a Dutch name so Deduce's name-list filter (#12) keeps the
        detection alive long enough to reach the reference-list match.
        Diacritic-insensitivity is covered separately in
        TestNormalizeReferenceName.test_strips_diacritics.
        """
        extraction = _make_extraction("De Vries heeft het voorstel namens de gemeente getekend.")
        result = await run_pipeline(
            extraction,
            public_official_names=["de Vries"],
        )
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        assert any(p.review_status == "rejected" and p.source == "reference_list" for p in persons)

    @pytest.mark.asyncio
    async def test_empty_reference_list_leaves_detection_pending(self):
        extraction = _make_extraction("Jan de Vries heeft een verzoek ingediend bij de gemeente.")
        result = await run_pipeline(
            extraction,
            public_official_names=[],
        )
        persons = [d for d in result.detections if d.entity_type == "persoon"]
        # At least one Jan-de-Vries detection should exist and NOT be flipped
        # by the reference list (it may still hit rule/structure paths).
        assert any("Jan de Vries" in p.entity_text for p in persons)
        assert not any(p.source == "reference_list" for p in persons)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reference_names_crud_roundtrip(client: AsyncClient, seed_db):
    """POST → GET → DELETE hitting the real routes."""
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    # POST
    create = await client.post(
        f"/api/documents/{doc_id}/reference-names",
        json={"display_name": "Jan de Vries"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["display_name"] == "Jan de Vries"
    assert body["normalized_name"] == "jan de vries"
    assert body["role_hint"] == "publiek_functionaris"
    created_id = body["id"]

    # GET (list)
    listing = await client.get(f"/api/documents/{doc_id}/reference-names")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["id"] == created_id

    # DELETE
    delete = await client.delete(f"/api/documents/{doc_id}/reference-names/{created_id}")
    assert delete.status_code == 204

    listing_after = await client.get(f"/api/documents/{doc_id}/reference-names")
    assert listing_after.json() == []


@pytest.mark.asyncio
async def test_reference_names_normalization_conflict(client: AsyncClient, seed_db):
    """Adding "De Vries" and then "de vries" must 409 — they normalize
    identically, so the composite unique index catches the duplicate."""
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    first = await client.post(
        f"/api/documents/{doc_id}/reference-names",
        json={"display_name": "De Vries"},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/documents/{doc_id}/reference-names",
        json={"display_name": "de vries"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_reference_names_rejects_empty(client: AsyncClient, seed_db):
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    blank = await client.post(
        f"/api/documents/{doc_id}/reference-names",
        json={"display_name": "   "},
    )
    assert blank.status_code == 400


@pytest.mark.asyncio
async def test_reference_names_delete_is_idempotent(client: AsyncClient, seed_db):
    """Delete on a missing row must 204, not 404. Needed for undo retries."""
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    missing = uuid.uuid4()
    resp = await client.delete(f"/api/documents/{doc_id}/reference-names/{missing}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_reference_names_404_for_unknown_document(client: AsyncClient):
    unknown = uuid.uuid4()
    resp = await client.get(f"/api/documents/{unknown}/reference-names")
    assert resp.status_code == 404
