import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Dossier
# ---------------------------------------------------------------------------


class DossierCreate(BaseModel):
    title: str
    request_number: str
    organization: str


class DossierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    request_number: str
    organization: str
    status: Literal["open", "in_review", "completed"]
    created_at: datetime
    updated_at: datetime


class DossierStats(BaseModel):
    total: int = 0
    by_tier: dict[str, int] = {}
    by_status: dict[str, int] = {}


class DossierWithStatsResponse(DossierResponse):
    document_count: int = 0
    detection_counts: DossierStats = DossierStats()


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_id: uuid.UUID
    filename: str
    page_count: int
    document_date: datetime | None
    status: Literal["uploaded", "processing", "review", "approved", "exported"]
    created_at: datetime


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class DetectionUpdate(BaseModel):
    review_status: Literal[
        "pending", "auto_accepted", "accepted", "rejected", "edited", "deferred"
    ] | None = None
    woo_article: str | None = None
    motivation_text: str | None = None


class BoundingBoxResponse(BaseModel):
    page: int
    x0: float
    y0: float
    x1: float
    y1: float


class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    entity_text: str
    entity_type: Literal[
        "persoon", "bsn", "telefoonnummer", "email", "adres", "iban",
        "gezondheid", "datum", "postcode", "kenteken", "creditcard",
        "paspoort", "rijbewijs",
    ]
    tier: Literal["1", "2", "3"]
    confidence: float
    woo_article: str | None
    review_status: Literal[
        "pending", "auto_accepted", "accepted", "rejected", "edited", "deferred"
    ]
    bounding_boxes: list[BoundingBoxResponse] | None
    reasoning: str | None
    propagated_from: uuid.UUID | None
    reviewer_id: str | None
    reviewed_at: datetime | None


# ---------------------------------------------------------------------------
# Public official
# ---------------------------------------------------------------------------


class PublicOfficialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dossier_id: uuid.UUID
    name: str
    role: str | None
