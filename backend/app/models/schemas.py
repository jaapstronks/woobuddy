import uuid
from datetime import datetime

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
    "uploaded", "processing", "review", "approved", "exported",
    name="document_status", create_type=True,
)

DetectionTier = Enum("1", "2", "3", name="detection_tier", create_type=True)

ReviewStatus = Enum(
    "pending", "auto_accepted", "accepted", "rejected", "edited", "deferred",
    name="review_status", create_type=True,
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
    bounding_boxes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="regex")  # regex, deduce, llm
    propagated_from: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detections.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_environmental: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    document: Mapped["Document"] = relationship(back_populates="detections")


# Defense-in-depth: reject any attempt to set `entity_text` on a Detection
# instance. The column no longer exists, but an `__init__` call that still
# passes the keyword (legacy code, stray kwargs) would otherwise silently
# set a transient attribute and be a subtle way to re-introduce PII at rest
# if someone later reads `getattr(det, 'entity_text', None)` and persists it.
@event.listens_for(Detection, "init")
def _block_entity_text_on_init(target: Detection, args: tuple, kwargs: dict) -> None:
    if "entity_text" in kwargs:
        raise ValueError(
            "Detection records must never contain entity_text "
            "(client-first architecture). Store only metadata."
        )
