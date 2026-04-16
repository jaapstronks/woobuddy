"""Shared dataclasses for the detection pipeline.

`PipelineDetection` and `PipelineResult` live here (rather than in
`pipeline_engine.py`) so helper modules that build pipeline detections —
notably `title_match_rules` — can construct them without importing
`pipeline_engine` and causing a circular import.

`pipeline_engine` still re-exports both names for backwards compat with
tests that import them from the old location.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.structure_engine import StructureSpan

PipelineReviewStatus = Literal[
    "auto_accepted", "pending", "accepted", "rejected", "edited",
]


@dataclass
class PipelineDetection:
    """A detection ready to be stored in the database."""

    entity_text: str
    entity_type: str
    tier: str
    confidence: float
    woo_article: str | None
    review_status: PipelineReviewStatus
    bounding_boxes: list[dict[str, Any]]
    reasoning: str
    source: str
    is_environmental: bool = False
    # Role classification produced by the rule engine (#13), if any.
    # Not persisted to the Detection table today — reserved for the Tier 2
    # card UX in #15 — but callers (and tests) can read it to verify that
    # the rule engine fired on a given detection.
    subject_role: str | None = None
    # Character offsets in the server-joined full text. Carried through
    # from the originating NERDetection so `analyze.py` can persist them
    # on the Detection row (#20 — bulk sweeps match detections against
    # structure spans on the frontend by comparing these offsets with
    # the spans' own `start_char`/`end_char`).
    start_char: int | None = None
    end_char: int | None = None


@dataclass
class PipelineResult:
    """Result of the full detection pipeline."""

    detections: list[PipelineDetection] = field(default_factory=list)
    page_count: int = 0
    has_environmental_content: bool = False
    # Structural regions (email headers, signature blocks, salutations)
    # found by `structure_engine.detect_structures`. Attached for #20
    # bulk sweeps and returned via AnalyzeResponse so the frontend can
    # render "lak dit blok" affordances on top of the PDF.
    structure_spans: list[StructureSpan] = field(default_factory=list)
