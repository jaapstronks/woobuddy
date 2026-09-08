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
from app.services.span_resolver import resolve_occurrence_bboxes

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
    """Return the existing detection that overlaps [start, end), if any.

    A custom term can straddle both a Tier 1 identifier and a Tier 2
    span (a postcode inside an address, say), and only one of them gets
    the term's Woo article. This used to be "the first one in the list",
    which happened to mean Tier 1 because `detect_all` returned Tier 1
    hits before Tier 2 ones. That list is sorted by offset now (#103),
    so state the preference instead of inheriting it: the harder tier
    wins, then the earlier span.
    """
    candidates = [
        d
        for d in detections
        if d.start_char is not None
        and d.end_char is not None
        and d.start_char < end_char
        and start_char < d.end_char
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda d: (d.tier, d.start_char, d.end_char))


def _merge_custom_into_existing(
    existing: PipelineDetection,
    match: TermMatch,
    term_bboxes: list[Bbox],
) -> None:
    """Mutate an existing detection: the custom term's article wins."""
    existing.woo_article = match.woo_article
    seen = {(b["page"], b["x0"], b["y0"], b["x1"], b["y1"]) for b in existing.bounding_boxes}
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
    custom_added = 0
    custom_merged = 0

    for m in term_matches:
        # Resolve *this* occurrence, not "the term". Caching one bbox list
        # per lowercased term made every occurrence inherit the first hit's
        # box — always on the first page that contained the term — so a
        # reviewer-typed term on page 3 got a page-1 box and exported
        # unredacted (#66/1).
        term_bboxes = resolve_occurrence_bboxes(
            extraction.pages, extraction.full_text, m.term, m.start_char
        )

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
