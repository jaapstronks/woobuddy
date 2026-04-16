"""Custom-term matching pass for the detection pipeline.

Extracted from ``pipeline_engine`` to keep the orchestrator focused on
NER classification. This module handles matching user-supplied terms
against the document text, resolving bboxes, and merging overlapping
hits with existing NER detections (#21).
"""

from collections.abc import Sequence

from app.logging_config import get_logger
from app.services.custom_term_matcher import (
    CustomTermLike,
    TermMatch,
    match_custom_terms,
)
from app.services.pdf_engine import ExtractionResult
from app.services.pipeline_types import Bbox, PipelineDetection, PipelineResult
from app.services.span_resolver import find_span_for_text

logger = get_logger(__name__)


def _custom_term_match_to_detection(
    match: TermMatch,
    bboxes: list[Bbox],
) -> PipelineDetection:
    """Map a custom-term occurrence onto a PipelineDetection."""
    return PipelineDetection(
        entity_text=match.term,
        entity_type="custom",
        tier="2",
        confidence=0.99,
        woo_article=match.woo_article,
        review_status="accepted",
        bounding_boxes=bboxes,
        reasoning=f"Zoekterm '{match.term}' uit documentspecifieke lijst.",
        source="custom_wordlist",
        start_char=match.start_char,
        end_char=match.end_char,
    )


def _find_overlapping_detection(
    detections: list[PipelineDetection],
    start_char: int,
    end_char: int,
) -> PipelineDetection | None:
    """Return the first existing detection that overlaps [start, end)."""
    for existing in detections:
        if existing.start_char is None or existing.end_char is None:
            continue
        if existing.start_char < end_char and start_char < existing.end_char:
            return existing
    return None


def _merge_custom_into_existing(
    existing: PipelineDetection,
    match: TermMatch,
    term_bboxes: list[Bbox],
) -> None:
    """Mutate an existing detection: the custom term's article wins."""
    existing.woo_article = match.woo_article
    seen = {
        (b["page"], b["x0"], b["y0"], b["x1"], b["y1"])
        for b in existing.bounding_boxes
    }
    for bb in term_bboxes:
        key = (bb["page"], bb["x0"], bb["y0"], bb["x1"], bb["y1"])
        if key not in seen:
            existing.bounding_boxes.append(bb)
            seen.add(key)
    existing.source = "custom_wordlist"
    existing.review_status = "accepted"
    existing.reasoning = (
        f"Zoekterm '{match.term}' uit documentspecifieke lijst (overschrijft eerdere detectie)."
    )


def apply_custom_terms(
    result: PipelineResult,
    extraction: ExtractionResult,
    custom_terms: Sequence[CustomTermLike],
) -> None:
    """Apply custom-term matches (#21), merging overlaps with NER hits."""
    term_matches = match_custom_terms(extraction.full_text, custom_terms)
    bbox_cache: dict[str, list[Bbox]] = {}
    custom_added = 0
    custom_merged = 0

    for m in term_matches:
        cache_key = m.term.lower()
        if cache_key not in bbox_cache:
            bbox_cache[cache_key] = find_span_for_text(extraction.pages, m.term)
        term_bboxes = bbox_cache[cache_key]

        overlap = _find_overlapping_detection(result.detections, m.start_char, m.end_char)
        if overlap is not None:
            _merge_custom_into_existing(overlap, m, term_bboxes)
            custom_merged += 1
        else:
            result.detections.append(_custom_term_match_to_detection(m, term_bboxes))
            custom_added += 1

    logger.info(
        "pipeline.custom_terms_completed",
        terms=len(custom_terms),
        matches=len(term_matches),
        added=custom_added,
        merged=custom_merged,
    )
