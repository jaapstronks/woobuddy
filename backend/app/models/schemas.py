import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

DocumentStatus = Enum(
    "uploaded",
    "processing",
    "review",
    "approved",
    "exported",
    name="document_status",
    create_type=True,
)

DetectionTier = Enum("1", "2", "3", name="detection_tier", create_type=True)

ReviewStatus = Enum(
    "pending",
    "auto_accepted",
    "accepted",
    "rejected",
    "edited",
    "deferred",
    name="review_status",
    create_type=True,
)

PageReviewStatus = Enum(
    "unreviewed",
    "in_progress",
    "complete",
    "flagged",
    name="page_review_status",
    create_type=True,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(500))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(DocumentStatus, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    detections: Mapped[list["Detection"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Detection(Base):
    """A single detection record.

    SECURITY (client-first architecture): detection rows contain positions,
    types, tiers and decisions — never the actual extracted text. There is
    deliberately no `entity_text` column. The application-level SQLAlchemy
    event below enforces this as defense-in-depth.
    """

    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_detections_document_tier", "document_id", "tier"),
        Index("ix_detections_review_status", "review_status"),
        # Guard against future regressions: if a stray entity_text column ever
        # reappears, this is the second line of defense. See the event hook
        # below for the primary guard.
        CheckConstraint(
            "reasoning IS NULL OR length(reasoning) < 5000",
            name="ck_detections_reasoning_bounded",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(50))
    tier: Mapped[str] = mapped_column(DetectionTier)
    confidence: Mapped[float] = mapped_column(Float)
    woo_article: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_status: Mapped[str] = mapped_column(ReviewStatus, default="auto_accepted")
    # Tier 2 person-role classification (#15). Reviewer-assigned label used
    # to distinguish burgers (redact), ambtenaren (redact), and publiek
    # functionarissen (do NOT redact — the click rejects the detection and
    # records the role). Nullable: unset means "no classification yet" and
    # the UI shows the three chips. Persisting the role is fine because it
    # is a *label*, not document content — compatible with client-first.
    subject_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bounding_boxes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    # Boundary adjustment (#11): the very first time a reviewer adjusts a
    # detection's bbox, we snapshot the analyzer's original coordinates here
    # so the audit trail can always answer "how did the reviewer move this?".
    # Subsequent adjustments keep the same snapshot — it's the baseline, not
    # the previous value. Nullable because unadjusted detections don't need it.
    original_bounding_boxes: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="regex")  # regex, deduce, rule, …
    propagated_from: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detections.id", ondelete="SET NULL"), nullable=True
    )
    # Split and merge audit (#18). When a reviewer splits a detection into
    # two halves the resulting rows carry `split_from = original.id`; when
    # a reviewer merges N detections the resulting row carries
    # `merged_from = [original_ids...]`. Deliberately plain UUID / JSONB
    # columns with no FK: the split/merge endpoints delete the original(s)
    # as part of the operation, and we want the audit references to
    # survive that delete. A FK with `ON DELETE SET NULL` would NULL the
    # surviving rows' audit fields the moment the parent is gone, which
    # defeats the audit purpose; a FK with RESTRICT would block the very
    # deletion we need. Both fields are metadata only — no document text
    # — so they are compatible with the client-first architecture.
    split_from: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    merged_from: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # Character offsets in the server-joined full text, captured at analyze
    # time (#20). Nullable because reviewer-authored ("manual" / "search_redact")
    # detections have no position in the analyzed text. Persisted so the
    # frontend can match detections to structure spans (#14) for bulk
    # sweeps without having to call analyze again on every reload.
    # Metadata only — still compatible with client-first architecture.
    start_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_environmental: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    document: Mapped["Document"] = relationship(back_populates="detections")


class DocumentReferenceName(Base):
    """Per-document reference list of people who must NOT be redacted (#17).

    Stores the reviewer's "I know these people are publiek functionarissen
    (or otherwise exempt from redaction) in this specific document" list.
    Client-first compatible: the stored strings are reviewer-provided
    *labels*, not extracted document content — the user typed "Jan de
    Vries" in a panel, nothing was lifted out of the PDF.

    Matching against detections happens in the analyze pipeline via the
    `normalized_name` column (lowercased, diacritics stripped) so
    "De Vries" typed earlier matches "de vries" in the document. The
    reviewer-typed `display_name` is kept for the UI so the panel can
    render the original spelling.
    """

    __tablename__ = "document_reference_names"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "normalized_name",
            name="uq_document_reference_names_doc_normalized",
        ),
        Index("ix_document_reference_names_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    normalized_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    # `role_hint` is reserved for future extensions (#17 mentions
    # `ambtenaar`, `burger`). For v1 every entry is a publiek_functionaris
    # — the panel is literally labelled "Publiek functionarissen" — but
    # the column is there so we don't need a migration the day the panel
    # grows a dropdown.
    role_hint: Mapped[str] = mapped_column(String(30), default="publiek_functionaris")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentCustomTerm(Base):
    """Per-document custom wordlist (#21 — "eigen zoektermen").

    Stores reviewer-provided search terms that must be redacted throughout
    a specific document. Pairs with `DocumentReferenceName` (#17): both are
    per-document reviewer labels, both short-circuit the generic pipeline,
    but the two have opposite intent — reference names are opt-out ("do NOT
    redact these"), custom terms are opt-in ("DO redact these").

    Client-first compatible: the stored `term` was typed by the reviewer
    into a panel — it is a label, not content extracted from the PDF. The
    reviewer already made the decision to redact every occurrence, so the
    resulting detections go in at `review_status="accepted"`.
    """

    __tablename__ = "document_custom_terms"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "normalized_term",
            "match_mode",
            name="uq_document_custom_terms_doc_normalized_mode",
        ),
        Index("ix_document_custom_terms_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    term: Mapped[str] = mapped_column(String(200))
    # Lowercased + whitespace-collapsed. Diacritics are preserved — unlike
    # `normalize_reference_name`, which strips them. A reviewer typing a
    # brand name like "Café Zuid" expects a literal match, not "Cafe Zuid".
    normalized_term: Mapped[str] = mapped_column(String(200))
    # `exact` is the only implemented mode in v1. `prefix` and `whole_word`
    # are reserved in the schema so we don't need a migration the day the
    # panel grows a radio group.
    match_mode: Mapped[str] = mapped_column(String(20), default="exact")
    # Woo-artikel to tag the match with. Defaults to 5.1.2e (the most
    # common relative ground for personal data). The panel lets the
    # reviewer pick a different article per term for cases like KvK
    # numbers (5.1.2c) or bedrijfsgeheimen (5.1.2b).
    woo_article: Mapped[str] = mapped_column(String(20), default="5.1.2e")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PageReview(Base):
    """Per-page completeness tracking (#10).

    One row per (document, page) the reviewer has touched. Rows are created
    lazily — a missing row is equivalent to `unreviewed`, which keeps the
    table small for long documents whose reviewer only acts on a handful of
    pages. The unique constraint guarantees idempotent upserts.

    Client-first: this table stores status metadata only — no text, no
    detections, no content. The reviewer identifier is a free-text field
    because auth (#24) hasn't landed yet; once it does, this becomes a
    proper FK.
    """

    __tablename__ = "page_reviews"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_page_reviews_doc_page"),
        Index("ix_page_reviews_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(PageReviewStatus, default="unreviewed")
    reviewer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# Defense-in-depth: reject any attempt to set `entity_text` on a Detection
# instance. The column no longer exists, but an `__init__` call that still
# passes the keyword (legacy code, stray kwargs) would otherwise silently
# set a transient attribute and be a subtle way to re-introduce PII at rest
# if someone later reads `getattr(det, 'entity_text', None)` and persists it.
@event.listens_for(Detection, "init")
def _block_entity_text_on_init(
    target: Detection, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    if "entity_text" in kwargs:
        raise ValueError(
            "Detection records must never contain entity_text "
            "(client-first architecture). Store only metadata."
        )
