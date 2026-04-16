"""Detection pipeline — orchestrates the full detection pipeline.

Runs Tier 1 (regex) and Tier 2 (Deduce NER + heuristic filters). Tier 3
is reserved and currently unused.

The pipeline is 100% rule-based: regex + Deduce NER + wordlists +
structure heuristics. There is no LLM anywhere in the live path, and
the codebase does not ship an LLM provider. If you want to revive the
LLM-based Tier 2 verification pass (person-role classification), see
`docs/reference/llm-revival.md` — the focus is local-only (Ollama +
Google Gemma) so document text never leaves the operator's machine.

Deduce `persoon` detections that survive the rule-based filters surface
as `review_status="pending"` and the reviewer decides.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.logging_config import get_logger
from app.services.custom_term_matcher import CustomTermLike
from app.services.environmental_classifier import check_environmental_content
from app.services.name_engine import normalize_reference_name
from app.services.ner_engine import NERDetection, detect_all
from app.services.pdf_engine import ExtractionResult

# Re-export PipelineDetection/PipelineResult at the old import path so
# existing callers (tests, analyze.py) keep working after the types
# moved to pipeline_types.py.
from app.services.pipeline_custom_terms import apply_custom_terms
from app.services.pipeline_types import PipelineDetection, PipelineResult, PipelineReviewStatus
from app.services.span_resolver import count_word_boundary_matches, find_span_for_text
from app.services.structure_engine import (
    StructureSpan,
    detect_structures,
    find_enclosing_structure,
)
from app.services.title_match_rules import (
    match_function_title,
    title_match_to_detection,
)
from app.services.whitelist_engine import (
    PersonWhitelistHit,
    WhitelistIndex,
    find_active_gemeenten,
    get_whitelist_index,
    match_address_whitelist,
    match_person_whitelist,
)

logger = get_logger(__name__)


# `PipelineDetection` and `PipelineResult` live in pipeline_types.py —
# re-exported above so `from app.services.pipeline_engine import
# PipelineResult` keeps working.

__all__ = [
    "PipelineDetection",
    "PipelineResult",
    "run_pipeline",
]


def _persoon_pending(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    *,
    reasoning: str,
    source: str,
    confidence: float | None = None,
    subject_role: str | None = None,
) -> PipelineDetection:
    """Build a Tier 2 persoon detection in `pending` review state.

    All "queue this name for manual confirmation" code paths converge
    here so that adding a field (e.g. start_char) does not require
    touching three call sites that each repeat the same kwargs.
    """
    return PipelineDetection(
        entity_text=det.text,
        entity_type="persoon",
        tier="2",
        confidence=confidence if confidence is not None else det.confidence,
        woo_article="5.1.2e",
        review_status="pending",
        bounding_boxes=bboxes,
        reasoning=reasoning,
        source=source,
        subject_role=subject_role,
        start_char=det.start_char,
        end_char=det.end_char,
    )


def _person_whitelist_to_detection(
    det: NERDetection,
    bboxes: list[dict[str, float]],
    hit: PersonWhitelistHit,
) -> PipelineDetection:
    """Map a gemeente-official whitelist hit onto a PipelineDetection.

    Same semantics as a publiek-functionaris title match: the detection
    is emitted at ``review_status="rejected"`` so the reviewer sees the
    card but the default is "niet lakken". The reasoning names the
    municipality so the reviewer can verify the call in one glance.
    """
    initials_note = " (initialen komen overeen)" if hit.used_initials else ""
    reasoning = (
        f"{hit.official.functie} bij {hit.municipality_name} "
        f"({hit.official.display_name}){initials_note} — "
        "gemeente wordt genoemd in het document."
    )
    return PipelineDetection(
        entity_text=det.text,
        entity_type="persoon",
        tier="2",
        confidence=min(det.confidence + 0.05, 0.95),
        woo_article=None,
        review_status="rejected",
        bounding_boxes=bboxes,
        reasoning=reasoning,
        source="whitelist_gemeente",
        subject_role="publiek_functionaris",
        start_char=det.start_char,
        end_char=det.end_char,
    )


def _ner_passthrough(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    *,
    tier: str,
    review_status: PipelineReviewStatus,
    woo_article_fallback: str | None = None,
) -> PipelineDetection:
    """Pass an NER hit through to a PipelineDetection with no rewrite.

    Used for Tier 1 regex hits (auto_accepted, no fallback article) and for
    the generic Tier 2 "no rule matched" tail (pending, fallback article
    5.1.2e). Both code paths used to inline a 10-field constructor that
    drifted every time a new field was added — see the start_char /
    end_char backfill in #20.
    """
    return PipelineDetection(
        entity_text=det.text,
        entity_type=det.entity_type,
        tier=tier,
        confidence=det.confidence,
        woo_article=det.woo_article or woo_article_fallback,
        review_status=review_status,
        bounding_boxes=bboxes,
        reasoning=det.reasoning,
        source=det.source,
        start_char=det.start_char,
        end_char=det.end_char,
    )


def _address_whitelist_to_detection(
    det: NERDetection,
    bboxes: list[dict[str, float]],
    reason: str,
) -> PipelineDetection:
    """Map an address-whitelist hit onto a PipelineDetection.

    The original Tier 1 regex (postcode, email, phone, url) or Tier 2
    Deduce ``adres`` would have auto-accepted this detection; the
    whitelist flips it to ``rejected`` so the reviewer sees it in the
    list but the default is to leave it visible. Reviewers can still
    flip it back in one click if they disagree.
    """
    return PipelineDetection(
        entity_text=det.text,
        entity_type=det.entity_type,
        tier=det.tier,
        confidence=det.confidence,
        woo_article=None,
        review_status="rejected",
        bounding_boxes=bboxes,
        reasoning=reason,
        source="whitelist_gemeente",
        start_char=det.start_char,
        end_char=det.end_char,
    )


_STRUCTURE_REASON: dict[str, str] = {
    "email_header": "Naam in e-mailheader",
    "signature_block": "Naam in handtekeningblok",
    "salutation": "Naam in aanhef",
}


def _structure_to_pipeline_detection(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    structure: StructureSpan,
) -> PipelineDetection:
    """Map a Tier 2 persoon hit enclosed in a structure span onto a
    PipelineDetection with the right review semantics.

    Email-header and signature-block membership auto-accepts (the
    structural context is evidence enough). Salutation membership only
    boosts confidence and pre-fills `subject_role="burger"` — the person
    being addressed is almost always a private citizen.
    """
    reason_stem = _STRUCTURE_REASON[structure.kind]
    if structure.kind in ("email_header", "signature_block"):
        return PipelineDetection(
            entity_text=det.text,
            entity_type="persoon",
            tier="2",
            confidence=min(det.confidence + 0.15, 0.95),
            woo_article="5.1.2e",
            review_status="auto_accepted",
            bounding_boxes=bboxes,
            reasoning=f"{reason_stem} — automatisch geaccepteerd op basis van context.",
            source="structure",
            start_char=det.start_char,
            end_char=det.end_char,
        )

    # Salutation — private-citizen hint, stays pending so the reviewer
    # confirms but with the role pre-filled.
    return _persoon_pending(
        det,
        bboxes,
        reasoning=f"{reason_stem} — vermoedelijk burger.",
        source="structure",
        confidence=min(det.confidence + 0.10, 0.95),
        subject_role="burger",
    )


# =========================================================================
# Per-document context
# =========================================================================


@dataclass
class _DocContext:
    """Per-document state computed once at pipeline start.

    Holds the whitelist indices, structure spans, and reference-list
    names so that the per-detection classification functions don't need
    to thread a dozen arguments through every call.
    """

    extraction: ExtractionResult
    whitelist_index: WhitelistIndex
    active_gemeenten: set[str]
    structure_spans: list[StructureSpan]
    official_names_normalized: set[str]
    has_environmental_content: bool


def _build_doc_context(
    extraction: ExtractionResult,
    public_official_names: list[str] | None,
) -> _DocContext:
    """Compute all per-document state (whitelist, structures, env check)."""
    official_names = {normalize_reference_name(n) for n in (public_official_names or []) if n}
    official_names.discard("")

    whitelist_index = get_whitelist_index()
    active_gemeenten = find_active_gemeenten(extraction.full_text, whitelist_index)
    if active_gemeenten:
        logger.info(
            "pipeline.whitelist_active_gemeenten",
            count=len(active_gemeenten),
        )

    structure_spans = detect_structures(extraction)
    if structure_spans:
        logger.info(
            "pipeline.structures_detected",
            email_header=sum(1 for s in structure_spans if s.kind == "email_header"),
            signature_block=sum(1 for s in structure_spans if s.kind == "signature_block"),
            salutation=sum(1 for s in structure_spans if s.kind == "salutation"),
        )

    return _DocContext(
        extraction=extraction,
        whitelist_index=whitelist_index,
        active_gemeenten=active_gemeenten,
        structure_spans=structure_spans,
        official_names_normalized=official_names,
        has_environmental_content=check_environmental_content(extraction.full_text),
    )


# =========================================================================
# Bbox resolution
# =========================================================================


def _resolve_bboxes(
    extraction: ExtractionResult,
    det: NERDetection,
) -> list[dict[str, Any]]:
    """Resolve a NER detection to exactly one bbox via occurrence index.

    Counting word-boundary matches up to ``det.start_char`` gives us
    the occurrence index of this specific hit so ``find_span_for_text``
    returns one bbox, not one per occurrence of the same text.
    """
    occurrence_idx = count_word_boundary_matches(
        extraction.full_text, det.text, limit=det.start_char
    )
    bboxes = find_span_for_text(extraction.pages, det.text, occurrence_index=occurrence_idx)
    if not bboxes:
        # Defensive fallback: if occurrence counting and span matching
        # disagree (different tokenisation), still return a single bbox.
        all_bboxes = find_span_for_text(extraction.pages, det.text)
        bboxes = all_bboxes[:1]
    return bboxes


# =========================================================================
# Classification chains — one function per tier / entity-type
# =========================================================================


def _classify_tier1(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    ctx: _DocContext,
) -> PipelineDetection:
    """Classify a Tier 1 (regex) detection.

    Priority:
      1. Address whitelist → rejected
      2. KvK → pending (public handelsregister data)
      3. Default → auto_accepted
    """
    # 1. Address whitelist (postcode / email / telefoon / url)
    addr_reason = match_address_whitelist(
        det.text,
        det.entity_type,
        ctx.whitelist_index,
        full_text=ctx.extraction.full_text,
        start_char=det.start_char,
    )
    if addr_reason is not None:
        return _address_whitelist_to_detection(det, bboxes, addr_reason)

    # 2. KvK: public handelsregister data — surface for review
    if det.entity_type == "kvk":
        return PipelineDetection(
            entity_text=det.text,
            entity_type=det.entity_type,
            tier="1",
            confidence=det.confidence,
            woo_article=det.woo_article,
            review_status="pending",
            bounding_boxes=bboxes,
            reasoning=(
                "KvK-nummer gedetecteerd — openbaar handelsregistergegeven, standaard niet lakken."
            ),
            source=det.source,
            start_char=det.start_char,
            end_char=det.end_char,
        )

    # 3. Default: auto-accept
    return _ner_passthrough(det, bboxes, tier="1", review_status="auto_accepted")


def _classify_persoon(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    ctx: _DocContext,
) -> PipelineDetection:
    """Classify a Tier 2 persoon detection.

    Priority chain (first match wins):
      1. Reference list → rejected (publiek_functionaris)
      2. Municipality officials whitelist → rejected
      3. Publiek title match → rejected
      4. Structure enclosure → auto_accepted or pending
      5. Ambtenaar title match → pending (pre-filled role)
      6. Deduce fallback → pending
    """
    # 1. Reference list (#17) — strongest signal, encodes reviewer knowledge
    if (
        ctx.official_names_normalized
        and normalize_reference_name(det.text) in ctx.official_names_normalized
    ):
        return PipelineDetection(
            entity_text=det.text,
            entity_type="persoon",
            tier="2",
            confidence=0.95,
            woo_article=None,
            review_status="rejected",
            bounding_boxes=bboxes,
            reasoning="Naam op publiek-functionarissenlijst van dit document.",
            source="reference_list",
            subject_role="publiek_functionaris",
            start_char=det.start_char,
            end_char=det.end_char,
        )

    # 2. Municipality officials whitelist — context-gated on active gemeenten
    whitelist_hit = match_person_whitelist(
        det.text,
        det.start_char,
        det.end_char,
        ctx.extraction.full_text,
        ctx.active_gemeenten,
        ctx.whitelist_index,
    )
    if whitelist_hit is not None:
        return _person_whitelist_to_detection(det, bboxes, whitelist_hit)

    # 3 + 5. Title match — computed once, split across publiek/ambtenaar
    title_match = match_function_title(
        ctx.extraction.full_text, det.text, det.start_char, det.end_char
    )

    # 3. Publiek title → rejected (beats structure: "Burgemeester X" in
    # a signature block must still be marked as not-to-redact)
    if title_match is not None and title_match.list_name == "publiek":
        rule_det = title_match_to_detection(det, bboxes, title_match)
        if rule_det is not None:
            return rule_det

    # 4. Structure enclosure (email header / signature block / salutation)
    enclosing = find_enclosing_structure(ctx.structure_spans, det.start_char, det.end_char)
    if enclosing is not None:
        return _structure_to_pipeline_detection(det, bboxes, enclosing)

    # 5. Ambtenaar title → pending with pre-filled role
    if title_match is not None:
        rule_det = title_match_to_detection(det, bboxes, title_match)
        if rule_det is not None:
            return rule_det

    # 6. Deduce fallback → pending
    return _persoon_pending(det, bboxes, reasoning=det.reasoning, source="deduce")


def _classify_other_tier2(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    ctx: _DocContext,
) -> PipelineDetection:
    """Classify a non-persoon Tier 2 detection (adres, datum, organisatie, …).

    Priority:
      1. Address whitelist → rejected
      2. Default → pending
    """
    addr_reason = match_address_whitelist(
        det.text,
        det.entity_type,
        ctx.whitelist_index,
        full_text=ctx.extraction.full_text,
        start_char=det.start_char,
    )
    if addr_reason is not None:
        return _address_whitelist_to_detection(det, bboxes, addr_reason)

    return _ner_passthrough(
        det,
        bboxes,
        tier="2",
        review_status="pending",
        woo_article_fallback="5.1.2e",
    )


def _classify_detection(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    ctx: _DocContext,
) -> PipelineDetection:
    """Route a NER detection to the right classification chain."""
    if det.tier == "1":
        return _classify_tier1(det, bboxes, ctx)
    if det.entity_type == "persoon":
        return _classify_persoon(det, bboxes, ctx)
    return _classify_other_tier2(det, bboxes, ctx)


# =========================================================================
# Public API
# =========================================================================


async def run_pipeline(
    extraction: ExtractionResult,
    public_official_names: list[str] | None = None,
    custom_terms: Sequence[CustomTermLike] | None = None,
) -> PipelineResult:
    """Run the detection pipeline on an extracted document.

    The body is pure-CPU (regex, Deduce NER, dict lookups) and would
    otherwise block the FastAPI event loop for hundreds of milliseconds
    on large documents. We hand it off to a worker thread so concurrent
    requests can still make progress while NER is running.
    """
    return await asyncio.to_thread(
        _run_pipeline_sync,
        extraction,
        public_official_names,
        custom_terms,
    )


def _run_pipeline_sync(
    extraction: ExtractionResult,
    public_official_names: list[str] | None,
    custom_terms: Sequence[CustomTermLike] | None,
) -> PipelineResult:
    """Synchronous pipeline body — see ``run_pipeline`` for docs."""
    result = PipelineResult(page_count=extraction.page_count)
    ctx = _build_doc_context(extraction, public_official_names)

    logger.info("pipeline.started", page_count=extraction.page_count)
    result.has_environmental_content = ctx.has_environmental_content
    result.structure_spans = ctx.structure_spans

    # --- NER pass: Tier 1 regex + Tier 2 Deduce, then classify each ---
    ner_detections = detect_all(extraction.full_text)
    logger.info("pipeline.ner_completed", detection_count=len(ner_detections))

    for det in ner_detections:
        bboxes = _resolve_bboxes(extraction, det)
        result.detections.append(_classify_detection(det, bboxes, ctx))

    # --- Custom wordlist pass (#21) ---
    if custom_terms:
        apply_custom_terms(result, extraction, custom_terms)

    logger.info("pipeline.completed", detection_count=len(result.detections))
    return result
