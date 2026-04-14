"""HTTP round-trip tests for the per-document custom wordlist (#21).

Service-level matcher behavior is covered in
`test_custom_term_matcher.py`; pipeline-level integration lives in
`test_llm_engine.py`. This file only exercises the CRUD endpoints —
the same shape as `test_reference_names.py` for feature #17.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.schemas import Document


@pytest.mark.asyncio
async def test_custom_terms_crud_roundtrip(client: AsyncClient, seed_db):
    """POST → GET → DELETE hitting the real routes."""
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    create = await client.post(
        f"/api/documents/{doc_id}/custom-terms",
        json={"term": "Project Apollo", "woo_article": "5.1.2b"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["term"] == "Project Apollo"
    assert body["normalized_term"] == "project apollo"
    assert body["match_mode"] == "exact"
    assert body["woo_article"] == "5.1.2b"
    created_id = body["id"]

    listing = await client.get(f"/api/documents/{doc_id}/custom-terms")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["id"] == created_id

    delete = await client.delete(
        f"/api/documents/{doc_id}/custom-terms/{created_id}"
    )
    assert delete.status_code == 204

    listing_after = await client.get(f"/api/documents/{doc_id}/custom-terms")
    assert listing_after.json() == []


@pytest.mark.asyncio
async def test_custom_terms_normalization_conflict(client: AsyncClient, seed_db):
    """Adding "Project Apollo" and then "project   apollo" must 409 —
    they normalize identically, so the composite unique index catches
    the duplicate."""
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    first = await client.post(
        f"/api/documents/{doc_id}/custom-terms",
        json={"term": "Project Apollo"},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/documents/{doc_id}/custom-terms",
        json={"term": "project   apollo"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_custom_terms_rejects_empty(client: AsyncClient, seed_db):
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    blank = await client.post(
        f"/api/documents/{doc_id}/custom-terms",
        json={"term": "   "},
    )
    assert blank.status_code == 400


@pytest.mark.asyncio
async def test_custom_terms_delete_is_idempotent(client: AsyncClient, seed_db):
    """Delete on a missing row must 204, not 404 — undo retries depend on it."""
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    doc_id = str(doc.id)

    missing = uuid.uuid4()
    resp = await client.delete(f"/api/documents/{doc_id}/custom-terms/{missing}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_custom_terms_404_for_unknown_document(client: AsyncClient):
    unknown = uuid.uuid4()
    resp = await client.get(f"/api/documents/{unknown}/custom-terms")
    assert resp.status_code == 404
