import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

DossierStatus = Enum("open", "in_review", "completed", name="dossier_status", create_type=True)

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


class Dossier(Base):
    __tablename__ = "dossiers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500))
    request_number: Mapped[str] = mapped_column(String(100))
    organization: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(DossierStatus, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    public_officials: Mapped[list["PublicOfficial"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(500))
    minio_key_original: Mapped[str] = mapped_column(String(1000))
    minio_key_redacted: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(DocumentStatus, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dossier: Mapped["Dossier"] = relationship(back_populates="documents")
    detections: Mapped[list["Detection"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_detections_document_tier", "document_id", "tier"),
        Index("ix_detections_review_status", "review_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    entity_text: Mapped[str] = mapped_column(Text)
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

    document: Mapped["Document"] = relationship(back_populates="detections")
    motivation_text: Mapped["MotivationText | None"] = relationship(
        back_populates="detection", uselist=False
    )


class PublicOfficial(Base):
    __tablename__ = "public_officials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)

    dossier: Mapped["Dossier"] = relationship(back_populates="public_officials")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(200), default="system")
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MotivationText(Base):
    __tablename__ = "motivation_texts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    detection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detections.id", ondelete="CASCADE"), unique=True
    )
    text: Mapped[str] = mapped_column(Text)
    is_edited: Mapped[bool] = mapped_column(default=False)

    detection: Mapped["Detection"] = relationship(back_populates="motivation_text")
