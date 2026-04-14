"""Tests for split/merge detection endpoints (#18).

Covers the reviewer-authored split/merge flows at the HTTP boundary.
Service-level behavior (bbox concatenation, FK cascades) is exercised
implicitly via the endpoint tests — there is no separate split/merge
service layer yet, so these are the authoritative tests for the feature.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.schemas import Detection, Document


async def _seed_document(seed_db) -> str:
    doc = Document(filename="test.pdf", page_count=1)
    seed_db.add(doc)
    await seed_db.commit()
    await seed_db.refresh(doc)
    return str(doc.id)


async def _seed_detection(
    seed_db,
    *,
    document_id: str,
    entity_type: str = "persoon",
    tier: str = "2",
    woo_article: str | None = "5.1.2e",
    bboxes: list[dict] | None = None,
    source: str = "deduce",
) -> Detection:
    detection = Detection(
        document_id=uuid.UUID(document_id),
        entity_type=entity_type,
        tier=tier,
        confidence=0.9,
        woo_article=woo_article,
        review_status="pending",
        bounding_boxes=bboxes or [{"page": 0, "x0": 10, "y0": 10, "x1": 100, "y1": 20}],
        reasoning="motivatie",
        source=source,
    )
    seed_db.add(detection)
    await seed_db.commit()
    await seed_db.refresh(detection)
    return detection


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_creates_two_detections_and_deletes_original(
    client: AsyncClient, seed_db
):
    doc_id = await _seed_document(seed_db)
    original = await _seed_detection(
        seed_db,
        document_id=doc_id,
        bboxes=[{"page": 0, "x0": 10, "y0": 10, "x1": 100, "y1": 20}],
    )
    original_id = str(original.id)

    resp = await client.post(
        f"/api/detections/{original_id}/split",
        json={
            "bboxes_a": [{"page": 0, "x0": 10, "y0": 10, "x1": 50, "y1": 20}],
            "bboxes_b": [{"page": 0, "x0": 50, "y0": 10, "x1": 100, "y1": 20}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2

    # Both halves inherit entity_type / tier / woo_article / motivation.
    for half in body:
        assert half["entity_type"] == "persoon"
        assert half["tier"] == "2"
        assert half["woo_article"] == "5.1.2e"
        assert half["reasoning"] == "motivatie"
        assert half["split_from"] == original_id
        assert half["review_status"] == "accepted"

    # Original is gone.
    result = await seed_db.execute(
        select(Detection).where(Detection.id == uuid.UUID(original_id))
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_split_products_are_deletable_via_manual_endpoint(
    client: AsyncClient, seed_db
):
    """Split/merge products are `source="manual"` so the regular delete
    endpoint (which refuses non-manual rows) can remove them — without
    this, an undo path would have no way to reverse the split."""
    doc_id = await _seed_document(seed_db)
    original = await _seed_detection(seed_db, document_id=doc_id, source="deduce")
    split_resp = await client.post(
        f"/api/detections/{original.id}/split",
        json={
            "bboxes_a": [{"page": 0, "x0": 10, "y0": 10, "x1": 50, "y1": 20}],
            "bboxes_b": [{"page": 0, "x0": 50, "y0": 10, "x1": 100, "y1": 20}],
        },
    )
    halves = split_resp.json()

    for half in halves:
        delete_resp = await client.delete(f"/api/detections/{half['id']}")
        assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_split_rejects_empty_bbox_sets(client: AsyncClient, seed_db):
    doc_id = await _seed_document(seed_db)
    original = await _seed_detection(seed_db, document_id=doc_id)

    resp = await client.post(
        f"/api/detections/{original.id}/split",
        json={
            "bboxes_a": [],
            "bboxes_b": [{"page": 0, "x0": 50, "y0": 10, "x1": 100, "y1": 20}],
        },
    )
    assert resp.status_code == 400

    # Original still present.
    result = await seed_db.execute(select(Detection).where(Detection.id == original.id))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_split_404_for_unknown_detection(client: AsyncClient):
    missing = uuid.uuid4()
    resp = await client.post(
        f"/api/detections/{missing}/split",
        json={
            "bboxes_a": [{"page": 0, "x0": 10, "y0": 10, "x1": 50, "y1": 20}],
            "bboxes_b": [{"page": 0, "x0": 50, "y0": 10, "x1": 100, "y1": 20}],
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_combines_bboxes_and_inherits_first_article(
    client: AsyncClient, seed_db
):
    doc_id = await _seed_document(seed_db)
    first = await _seed_detection(
        seed_db,
        document_id=doc_id,
        woo_article="5.1.2e",
        bboxes=[{"page": 0, "x0": 10, "y0": 10, "x1": 50, "y1": 20}],
    )
    second = await _seed_detection(
        seed_db,
        document_id=doc_id,
        woo_article="5.1.1c",
        bboxes=[{"page": 0, "x0": 60, "y0": 10, "x1": 100, "y1": 20}],
    )

    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(first.id), str(second.id)]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Article inherited from the first id in the list.
    assert body["woo_article"] == "5.1.2e"
    # Both source uuids recorded for audit.
    assert set(body["merged_from"]) == {str(first.id), str(second.id)}
    # Bboxes concatenated in list order.
    assert len(body["bounding_boxes"]) == 2
    assert body["bounding_boxes"][0]["x0"] == 10
    assert body["bounding_boxes"][1]["x0"] == 60

    # Originals are gone.
    remaining = await seed_db.execute(
        select(Detection).where(Detection.id.in_([first.id, second.id]))
    )
    assert remaining.scalars().all() == []


@pytest.mark.asyncio
async def test_merge_requires_two_ids(client: AsyncClient, seed_db):
    doc_id = await _seed_document(seed_db)
    lone = await _seed_detection(seed_db, document_id=doc_id)

    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(lone.id)]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_rejects_cross_document(client: AsyncClient, seed_db):
    doc_a = await _seed_document(seed_db)
    doc_b = await _seed_document(seed_db)
    det_a = await _seed_detection(seed_db, document_id=doc_a)
    det_b = await _seed_detection(seed_db, document_id=doc_b)

    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(det_a.id), str(det_b.id)]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_404_when_any_id_is_unknown(client: AsyncClient, seed_db):
    doc_id = await _seed_document(seed_db)
    real = await _seed_detection(seed_db, document_id=doc_id)
    missing = uuid.uuid4()

    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(real.id), str(missing)]},
    )
    assert resp.status_code == 404
