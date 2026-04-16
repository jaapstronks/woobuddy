"""Contract tests for the detections CRUD surface.

Covers:
- PATCH /api/detections/:id      — accept/reject/defer, boundary adjust,
                                   subject_role set + explicit clear.
- POST  /api/detections          — reviewer-authored manual detection.
- DELETE /api/detections/:id     — only reviewer-authored rows are
                                   deletable; auto rows return 422.
- POST /api/detections/:id/split — two-half split with bbox validation.
- POST /api/detections/merge     — 2+ ids, same document, no dupes.

These are the endpoints the frontend undo stack talks to, so the
contract is load-bearing: a silent shape change here translates to a
review-page regression that is hard to catch from the browser.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.schemas import Detection, Document

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def doc(seed_db) -> Document:
    d = Document(filename="test.pdf", page_count=1, status="review")
    seed_db.add(d)
    await seed_db.commit()
    await seed_db.refresh(d)
    return d


def _make_detection(
    *,
    document_id: uuid.UUID,
    source: str = "deduce",
    review_status: str = "pending",
    entity_type: str = "persoon",
    tier: str = "2",
    woo_article: str | None = "5.1.2e",
    bboxes: list[dict] | None = None,
) -> Detection:
    return Detection(
        document_id=document_id,
        entity_type=entity_type,
        tier=tier,
        confidence=0.8,
        woo_article=woo_article,
        review_status=review_status,
        bounding_boxes=bboxes
        or [{"page": 0, "x0": 10.0, "y0": 20.0, "x1": 100.0, "y1": 32.0}],
        reasoning="seeded for test",
        source=source,
    )


@pytest_asyncio.fixture
async def auto_detection(seed_db, doc: Document) -> Detection:
    det = _make_detection(document_id=doc.id, source="deduce")
    seed_db.add(det)
    await seed_db.commit()
    await seed_db.refresh(det)
    return det


@pytest_asyncio.fixture
async def manual_detection(seed_db, doc: Document) -> Detection:
    det = _make_detection(
        document_id=doc.id, source="manual", review_status="accepted"
    )
    seed_db.add(det)
    await seed_db.commit()
    await seed_db.refresh(det)
    return det


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_unknown_detection_returns_404(client: AsyncClient) -> None:
    bogus = uuid.uuid4()
    resp = await client.patch(
        f"/api/detections/{bogus}", json={"review_status": "accepted"}
    )
    assert resp.status_code == 404
    assert "Detectie niet gevonden" in resp.text


@pytest.mark.asyncio
async def test_patch_review_status_stamps_reviewed_at(
    client: AsyncClient, auto_detection: Detection, seed_db
) -> None:
    """Flipping review_status must record the reviewer-action timestamp.
    The redaction log uses this field — without it, a row shows up as
    "not yet reviewed" even after an accept."""
    assert auto_detection.reviewed_at is None

    resp = await client.patch(
        f"/api/detections/{auto_detection.id}",
        json={"review_status": "accepted"},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "accepted"

    await seed_db.refresh(auto_detection)
    assert auto_detection.review_status == "accepted"
    assert isinstance(auto_detection.reviewed_at, datetime)


@pytest.mark.asyncio
async def test_patch_bbox_flips_status_to_edited_and_snapshots_original(
    client: AsyncClient, auto_detection: Detection, seed_db
) -> None:
    """Boundary adjustment: the first bbox change must snapshot the
    analyzer's baseline into `original_bounding_boxes` AND flip the
    review_status to `edited` unless the reviewer also sent an
    explicit override."""
    new_boxes = [
        {"page": 0, "x0": 5.0, "y0": 15.0, "x1": 95.0, "y1": 28.0}
    ]

    resp = await client.patch(
        f"/api/detections/{auto_detection.id}",
        json={"bounding_boxes": new_boxes},
    )
    assert resp.status_code == 200

    await seed_db.refresh(auto_detection)
    assert auto_detection.review_status == "edited"
    # Original snapshot captured exactly once from the prior value.
    assert auto_detection.original_bounding_boxes is not None
    assert auto_detection.original_bounding_boxes[0]["x0"] == 10.0
    # Current bboxes overwritten with the new value.
    assert auto_detection.bounding_boxes[0]["x0"] == 5.0


@pytest.mark.asyncio
async def test_patch_bbox_with_explicit_status_respects_override(
    client: AsyncClient, auto_detection: Detection, seed_db
) -> None:
    """Undo/redo sends a bbox revert alongside a status revert. The
    server must not clobber the caller's status with `edited` in that
    case."""
    resp = await client.patch(
        f"/api/detections/{auto_detection.id}",
        json={
            "bounding_boxes": [
                {"page": 0, "x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0}
            ],
            "review_status": "accepted",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "accepted"


@pytest.mark.asyncio
async def test_patch_empty_bbox_array_400(
    client: AsyncClient, auto_detection: Detection
) -> None:
    """A PATCH that sends `bounding_boxes: []` is malformed — a detection
    with zero bboxes is unredactable. The endpoint must reject rather
    than silently persisting an unrenderable row."""
    resp = await client.patch(
        f"/api/detections/{auto_detection.id}",
        json={"bounding_boxes": []},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_subject_role_set_then_explicit_clear(
    client: AsyncClient, auto_detection: Detection, seed_db
) -> None:
    """`subject_role: null` alone means "don't touch" — that is what the
    client sends when the PATCH is only about something else. To actively
    clear the role (used by undo reverting a chip click) the client must
    send `clear_subject_role: true` alongside a null role."""
    # Set it.
    r1 = await client.patch(
        f"/api/detections/{auto_detection.id}",
        json={"subject_role": "burger"},
    )
    assert r1.status_code == 200
    assert r1.json()["subject_role"] == "burger"

    # null alone is a no-op — the role must remain `burger`.
    r2 = await client.patch(
        f"/api/detections/{auto_detection.id}",
        json={"subject_role": None, "woo_article": "5.1.2e"},
    )
    assert r2.status_code == 200
    assert r2.json()["subject_role"] == "burger"

    # Explicit clear.
    r3 = await client.patch(
        f"/api/detections/{auto_detection.id}",
        json={"subject_role": None, "clear_subject_role": True},
    )
    assert r3.status_code == 200
    assert r3.json()["subject_role"] is None


# ---------------------------------------------------------------------------
# POST /api/detections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_manual_detection_persists_metadata_not_text(
    client: AsyncClient, doc: Document, seed_db
) -> None:
    """Manual detection is reviewer-authored: full confidence, accepted
    by default, source=`manual`. Client-first: no entity_text column is
    accepted — the Detection model actively rejects it."""
    resp = await client.post(
        "/api/detections",
        json={
            "document_id": str(doc.id),
            "entity_type": "persoon",
            "tier": "2",
            "woo_article": "5.1.2e",
            "bounding_boxes": [
                {"page": 0, "x0": 10.0, "y0": 20.0, "x1": 110.0, "y1": 32.0}
            ],
            "motivation_text": "Handmatig geselecteerd",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "manual"
    assert body["review_status"] == "accepted"
    assert body["confidence"] == 1.0


@pytest.mark.asyncio
async def test_create_manual_detection_requires_bbox(
    client: AsyncClient, doc: Document
) -> None:
    resp = await client.post(
        "/api/detections",
        json={
            "document_id": str(doc.id),
            "entity_type": "persoon",
            "tier": "2",
            "bounding_boxes": [],
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_manual_detection_unknown_document_404(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/detections",
        json={
            "document_id": str(uuid.uuid4()),
            "entity_type": "persoon",
            "tier": "2",
            "bounding_boxes": [
                {"page": 0, "x0": 10.0, "y0": 20.0, "x1": 110.0, "y1": 32.0}
            ],
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_manual_detection_succeeds(
    client: AsyncClient, manual_detection: Detection
) -> None:
    resp = await client.delete(f"/api/detections/{manual_detection.id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_auto_detection_is_422(
    client: AsyncClient, auto_detection: Detection
) -> None:
    """Auto-detections (deduce/regex/rule/...) must NOT be deletable.
    The review loop flips their review_status; deleting would drop the
    analyzer's evidence of what it found."""
    resp = await client.delete(f"/api/detections/{auto_detection.id}")
    assert resp.status_code == 422
    assert "handmatig" in resp.text.lower()


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_requires_bboxes_on_both_halves(
    client: AsyncClient, auto_detection: Detection
) -> None:
    resp = await client.post(
        f"/api/detections/{auto_detection.id}/split",
        json={
            "bboxes_a": [
                {"page": 0, "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 32.0}
            ],
            "bboxes_b": [],
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_split_creates_two_manual_rows_and_removes_original(
    client: AsyncClient, auto_detection: Detection, seed_db
) -> None:
    """Split outputs inherit tier/entity_type/article/motivation but flip
    to source=manual so the regular DELETE endpoint can undo them."""
    original_id = auto_detection.id
    resp = await client.post(
        f"/api/detections/{original_id}/split",
        json={
            "bboxes_a": [
                {"page": 0, "x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 32.0}
            ],
            "bboxes_b": [
                {"page": 0, "x0": 50.0, "y0": 20.0, "x1": 100.0, "y1": 32.0}
            ],
        },
    )
    assert resp.status_code == 201
    rows = resp.json()
    assert len(rows) == 2
    for row in rows:
        assert row["source"] == "manual"
        assert row["split_from"] == str(original_id)
        assert row["entity_type"] == auto_detection.entity_type
        assert row["tier"] == auto_detection.tier

    # Original row is gone.
    gone = await client.get(f"/api/documents/{auto_detection.document_id}/detections")
    assert gone.status_code == 200
    remaining_ids = {r["id"] for r in gone.json()}
    assert str(original_id) not in remaining_ids


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_requires_at_least_two_ids(
    client: AsyncClient, auto_detection: Detection
) -> None:
    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(auto_detection.id)]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_rejects_duplicate_ids(
    client: AsyncClient, auto_detection: Detection
) -> None:
    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(auto_detection.id), str(auto_detection.id)]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_rejects_cross_document(
    client: AsyncClient, doc: Document, seed_db
) -> None:
    """Bboxes live in the coordinate space of a specific document; a
    merge across documents has no geometric meaning."""
    other_doc = Document(filename="other.pdf", page_count=1, status="review")
    seed_db.add(other_doc)
    await seed_db.commit()
    await seed_db.refresh(other_doc)

    a = _make_detection(document_id=doc.id)
    b = _make_detection(document_id=other_doc.id)
    seed_db.add_all([a, b])
    await seed_db.commit()
    await seed_db.refresh(a)
    await seed_db.refresh(b)

    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(a.id), str(b.id)]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_returns_single_row_with_concatenated_bboxes(
    client: AsyncClient, doc: Document, seed_db
) -> None:
    a = _make_detection(
        document_id=doc.id,
        bboxes=[{"page": 0, "x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0}],
    )
    b = _make_detection(
        document_id=doc.id,
        bboxes=[{"page": 0, "x0": 20.0, "y0": 0.0, "x1": 30.0, "y1": 10.0}],
    )
    seed_db.add_all([a, b])
    await seed_db.commit()
    await seed_db.refresh(a)
    await seed_db.refresh(b)

    resp = await client.post(
        "/api/detections/merge",
        json={"detection_ids": [str(a.id), str(b.id)]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "manual"
    assert len(body["bounding_boxes"]) == 2
    assert set(body["merged_from"]) == {str(a.id), str(b.id)}
