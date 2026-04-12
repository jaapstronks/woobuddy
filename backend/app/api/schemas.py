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
    entity_type: str
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
    is_environmental: bool = False


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


class AnalyzeRequest(BaseModel):
    document_id: uuid.UUID
    pages: list[AnalyzePage]


class AnalyzeResponse(BaseModel):
    document_id: uuid.UUID
    detection_count: int
    page_count: int
    status: str = "completed"
