import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Detection (response shape — used by the inline list in AnalyzeResponse)
# ---------------------------------------------------------------------------


class BoundingBoxResponse(BaseModel):
    page: int
    x0: float
    y0: float
    x1: float
    y1: float


SubjectRoleLiteral = Literal["burger", "ambtenaar", "publiek_functionaris", "geen_persoon"]


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
    # bar. Auto rows are `regex`/`deduce`/`rule`/`structure`/`custom_wordlist`/
    # `whitelist_gemeente`/`reference_list`; reviewer-authored rows are
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
    # into this one (null when this row is not a merge result).
    split_from: uuid.UUID | None = None
    merged_from: list[uuid.UUID] | None = None
    # #20 — character offsets in the server-joined full text. Returned
    # so the frontend can match detections to structure spans for
    # bulk-sweep affordances.
    start_char: int | None = None
    end_char: int | None = None


# ---------------------------------------------------------------------------
# Analyze (client-first: ephemeral text processing, anonymous-only)
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

    Mirrors the shape of `reference_names`: the frontend owns the list,
    so rather than ask the backend to load it from the database on
    every analyze call, it is threaded through the request.
    """

    term: str
    match_mode: CustomTermMatchModeLiteral = "exact"
    woo_article: str = "5.1.2e"


class AnalyzeRequest(BaseModel):
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
    # Freshly generated session UUID — never corresponds to a Postgres
    # row. The client uses it as a local key in IndexedDB / in-memory
    # state.
    document_id: uuid.UUID
    detection_count: int
    page_count: int
    status: str = "completed"
    structure_spans: list[StructureSpanResponse] = []
    # The full detection list inline. The client never fetches
    # detections separately — there is no Postgres row to fetch from.
    detections: list[DetectionResponse] = []


# ---------------------------------------------------------------------------
# Leads (#45 — email capture for public launch without auth)
# ---------------------------------------------------------------------------


LeadSourceLiteral = Literal["landing", "post-export"]


class LeadCreate(BaseModel):
    """Payload for the public contact form.

    Every submission fires a transactional email to the operator. The
    newsletter subscription is a separate opt-in: only when
    `newsletter_opt_in` is true do we also push the contact into the
    configured Brevo list.

    All optional fields are strings rather than nullable types because an
    HTML form sends `""` for empty inputs; the server coerces blanks to
    None before persisting.
    """

    email: str
    name: str | None = None
    organization: str | None = None
    message: str | None = None
    source: LeadSourceLiteral
    newsletter_opt_in: bool = False


class LeadResponse(BaseModel):
    """Deliberately opaque response.

    We return the same shape for a fresh insert and a duplicate submission
    so the form can't be used to probe whether an address is already on
    the list. No id, no timestamp — just `{ok: true}`.
    """

    ok: bool = True
