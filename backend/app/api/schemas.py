import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class DocumentRegister(BaseModel):
    filename: str
    page_count: int = 0


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    page_count: int
    document_date: datetime | None
    status: Literal["uploaded", "processing", "review", "approved", "exported"]
    created_at: datetime
    five_year_warning: bool = False


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class BoundingBoxResponse(BaseModel):
    page: int
    x0: float
    y0: float
    x1: float
    y1: float


SubjectRoleLiteral = Literal["burger", "ambtenaar", "publiek_functionaris"]


class DetectionUpdate(BaseModel):
    review_status: (
        Literal["pending", "auto_accepted", "accepted", "rejected", "edited", "deferred"] | None
    ) = None
    woo_article: str | None = None
    motivation_text: str | None = None
    # Boundary adjustment (#11) — when present, replaces the detection's
    # bounding boxes and (if not already done) snapshots the previous set
    # into `original_bounding_boxes` for audit. Server also flips
    # `review_status` to "edited" unless the client sent an explicit
    # override in the same call.
    bounding_boxes: list[BoundingBoxResponse] | None = None
    # #15 — Tier 2 person-role classification. `None` here means the client
    # did not touch the field in this PATCH; to explicitly clear an already
    # set role (used by undo after the very first chip click), send
    # `clear_subject_role: true` alongside a `None` role.
    subject_role: SubjectRoleLiteral | None = None
    clear_subject_role: bool = False


class ManualDetectionCreate(BaseModel):
    """Payload to create a reviewer-authored ("manual") detection.

    Client-first: the `entity_text` of the selection stays in the browser —
    only position metadata, tier, article and entity type are persisted.
    """

    document_id: uuid.UUID
    entity_type: str
    tier: Literal["1", "2", "3"] = "2"
    woo_article: str | None = None
    bounding_boxes: list[BoundingBoxResponse]
    motivation_text: str | None = None
    # #09 — search-and-redact tags its bulk-created detections with a
    # distinct source so audit logs can distinguish them from single
    # text-selection redactions. Everything else still defaults to "manual".
    source: Literal["manual", "search_redact"] = "manual"


class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    entity_type: str
    tier: Literal["1", "2", "3"]
    confidence: float
    woo_article: str | None
    review_status: Literal["pending", "auto_accepted", "accepted", "rejected", "edited", "deferred"]
    bounding_boxes: list[BoundingBoxResponse] | None
    original_bounding_boxes: list[BoundingBoxResponse] | None = None
    reasoning: str | None
    # #19 — pipeline label, surfaced in the redaction log table and filter
    # bar. Auto rows are `regex`/`deduce`/`llm`; reviewer-authored rows are
    # `manual` or `search_redact`.
    source: str = "regex"
    propagated_from: uuid.UUID | None
    reviewer_id: str | None
    reviewed_at: datetime | None
    is_environmental: bool = False
    # #15 — reviewer-assigned person-role classification for Tier 2 persoon
    # and equivalent detections. Null until classified.
    subject_role: SubjectRoleLiteral | None = None
    # #18 — split/merge audit. `split_from` points at the detection that was
    # split to produce this row (null when this row is not the result of a
    # split). `merged_from` is a list of detection UUIDs that were merged
    # into this one (null when this row is not a merge result). Metadata
    # only — no document text — so compatible with client-first.
    split_from: uuid.UUID | None = None
    merged_from: list[uuid.UUID] | None = None
    # #20 — character offsets in the server-joined full text. Returned
    # so the frontend can match detections to structure spans for
    # bulk-sweep affordances. Null for reviewer-authored rows (manual /
    # search_redact) that have no position in the analyzed text.
    start_char: int | None = None
    end_char: int | None = None


class SplitDetectionRequest(BaseModel):
    """Payload to split a detection into two (#18).

    The client resolves the split point against its local text layer, then
    sends the two resulting bbox sets. Both halves become independent
    detections — they inherit the original's tier / entity_type / woo_article
    / motivation, but their source is flipped to "manual" so the regular
    delete endpoint can remove them (the original is deleted server-side as
    part of this operation).
    """

    bboxes_a: list[BoundingBoxResponse]
    bboxes_b: list[BoundingBoxResponse]


class MergeDetectionsRequest(BaseModel):
    """Payload to merge two or more detections into one (#18).

    The server concatenates the input detections' bboxes in the order of
    `detection_ids` and produces a new "manual"-source detection that
    inherits tier / entity_type / woo_article / motivation from the first
    id in the list. The inputs are deleted; their uuids are preserved in
    `merged_from` for audit.
    """

    detection_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# Analyze (client-first: ephemeral text processing)
# ---------------------------------------------------------------------------


class AnalyzeTextItem(BaseModel):
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


class AnalyzePage(BaseModel):
    page_number: int
    full_text: str
    text_items: list[AnalyzeTextItem]


CustomTermMatchModeLiteral = Literal["exact"]


class CustomTermPayload(BaseModel):
    """Inline term payload sent from the frontend with an analyze request.

    Mirrors the shape of `reference_names`: the frontend already owns the
    list, so rather than force the backend to load it from the database
    on every analyze call, it is threaded through the request.
    """

    term: str
    match_mode: CustomTermMatchModeLiteral = "exact"
    woo_article: str = "5.1.2e"


class AnalyzeRequest(BaseModel):
    document_id: uuid.UUID
    pages: list[AnalyzePage]
    # #17 — per-document reference list of people that must NOT be
    # redacted. Optional: the frontend sends the current list on every
    # analyze call; when omitted the server behaves as if the list is
    # empty. Values are reviewer-provided display names — the server
    # normalizes them before matching.
    reference_names: list[str] = []
    # #21 — per-document custom wordlist of terms that MUST be redacted.
    # Opposite intent to `reference_names`: these produce extra
    # detections with `review_status="accepted"` because the reviewer
    # already made the decision by typing the term. Empty by default.
    custom_terms: list[CustomTermPayload] = []


class StructureSpanResponse(BaseModel):
    """A structural region (email header / signature block / salutation)
    found by `structure_engine.detect_structures`. Returned ephemerally
    with the analysis response so the frontend can render bulk-sweep
    affordances in #20 — not persisted."""

    kind: Literal["email_header", "signature_block", "salutation"]
    start_char: int
    end_char: int
    confidence: float
    evidence: str


class AnalyzeResponse(BaseModel):
    document_id: uuid.UUID
    detection_count: int
    page_count: int
    status: str = "completed"
    structure_spans: list[StructureSpanResponse] = []


# ---------------------------------------------------------------------------
# Page reviews (#10 — page completeness)
# ---------------------------------------------------------------------------


PageReviewStatusLiteral = Literal["unreviewed", "in_progress", "complete", "flagged"]


class PageReviewUpsert(BaseModel):
    status: PageReviewStatusLiteral
    reviewer_id: str | None = None


class PageReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    status: PageReviewStatusLiteral
    reviewer_id: str | None
    updated_at: datetime


# ---------------------------------------------------------------------------
# Reference names (#17 — per-document "niet lakken" list)
# ---------------------------------------------------------------------------


ReferenceRoleHintLiteral = Literal["publiek_functionaris", "ambtenaar", "burger"]


class ReferenceNameCreate(BaseModel):
    display_name: str
    role_hint: ReferenceRoleHintLiteral = "publiek_functionaris"


class ReferenceNameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    display_name: str
    normalized_name: str
    role_hint: ReferenceRoleHintLiteral
    created_at: datetime


# ---------------------------------------------------------------------------
# Custom terms (#21 — per-document "eigen zoektermen")
# ---------------------------------------------------------------------------


class CustomTermCreate(BaseModel):
    term: str
    match_mode: CustomTermMatchModeLiteral = "exact"
    woo_article: str = "5.1.2e"


class CustomTermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    term: str
    normalized_term: str
    match_mode: CustomTermMatchModeLiteral
    woo_article: str
    created_at: datetime
