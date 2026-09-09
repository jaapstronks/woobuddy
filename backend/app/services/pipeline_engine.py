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

from app.logging_config import get_logger
from app.services.custom_term_matcher import CustomTermLike
from app.services.environmental_classifier import check_environmental_content
from app.services.name_engine import normalize_reference_name
from app.services.ner_engine import DEFAULT_WOO_ARTICLE, NERDetection, detect_all
from app.services.ner_engine._org_context import (
    legal_form_lead,
    organisation_context_reason,
)
from app.services.pdf_engine import ExtractionResult

# Re-export PipelineDetection/PipelineResult at the old import path so
# existing callers (tests, analyze.py) keep working after the types
# moved to pipeline_types.py.
from app.services.pipeline_custom_terms import apply_custom_terms
from app.services.pipeline_types import (
    Bbox,
    PipelineDetection,
    PipelineResult,
    PipelineReviewStatus,
    PipelineTier,
)
from app.services.role_engine import find_mandate_cue_after, find_mandate_cue_before
from app.services.span_resolver import resolve_occurrence_bboxes
from app.services.structure_engine import (
    StructureSpan,
    detect_structures,
    find_enclosing_structure,
    is_email_subject_line,
)
from app.services.title_match_rules import (
    mandate_cue_to_detection,
    match_function_title,
    title_match_to_detection,
)
from app.services.whitelist_engine import (
    PersonWhitelistHit,
    WhitelistIndex,
    find_gemeente_mentions,
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


def _pipeline_detection_from_ner(
    det: NERDetection,
    bboxes: list[Bbox],
    *,
    review_status: PipelineReviewStatus,
    source: str,
    reasoning: str,
    woo_article: str | None,
    entity_type: str | None = None,
    tier: PipelineTier | None = None,
    confidence: float | None = None,
    subject_role: str | None = None,
) -> PipelineDetection:
    """Build a PipelineDetection from a NERDetection with targeted overrides.

    All PipelineDetection construction in this module goes through here so
    that adding a field to the dataclass (e.g. the start_char/end_char
    backfill in #20) does not require touching every call site. Callers
    override only what differs from the originating NER hit — defaults for
    entity_type / tier / confidence come straight from ``det``.
    """
    return PipelineDetection(
        entity_text=det.text,
        entity_type=entity_type if entity_type is not None else det.entity_type,
        tier=tier if tier is not None else det.tier,
        confidence=confidence if confidence is not None else det.confidence,
        woo_article=woo_article,
        review_status=review_status,
        bounding_boxes=bboxes,
        reasoning=reasoning,
        source=source,
        subject_role=subject_role,
        start_char=det.start_char,
        end_char=det.end_char,
    )


def _persoon_pending(
    det: NERDetection,
    bboxes: list[Bbox],
    *,
    reasoning: str,
    source: str,
    confidence: float | None = None,
    subject_role: str | None = None,
) -> PipelineDetection:
    """Build a Tier 2 persoon detection in `pending` review state."""
    return _pipeline_detection_from_ner(
        det,
        bboxes,
        entity_type="persoon",
        tier="2",
        confidence=confidence,
        woo_article=DEFAULT_WOO_ARTICLE,
        review_status="pending",
        reasoning=reasoning,
        source=source,
        subject_role=subject_role,
    )


def _person_whitelist_to_detection(
    det: NERDetection,
    bboxes: list[Bbox],
    hit: PersonWhitelistHit,
) -> PipelineDetection:
    """Map a *confirmed* gemeente-official whitelist hit onto a detection.

    Same semantics as a publiek-functionaris title match: the detection
    is emitted at ``review_status="rejected"`` so the reviewer sees the
    card but the default is "niet lakken". The reasoning names the
    municipality so the reviewer can verify the call in one glance.
    Only ever called for ``hit.confirmed`` — an unconfirmed hit goes
    through ``_person_whitelist_hint_to_detection`` instead (#92).
    """
    reasoning = (
        f"{hit.official.functie} bij {hit.municipality_name} "
        f"({hit.official.display_name}) (initialen komen overeen) — "
        "gemeente wordt genoemd in het document."
    )
    return _pipeline_detection_from_ner(
        det,
        bboxes,
        entity_type="persoon",
        tier="2",
        confidence=min(det.confidence + 0.05, 0.95),
        woo_article=None,
        review_status="rejected",
        reasoning=reasoning,
        source="whitelist_gemeente",
        subject_role="publiek_functionaris",
    )


# Why an otherwise-fitting whitelist hit was not good enough to reject on.
_WHITELIST_HINT_REASON: dict[str, str] = {
    "no_given_name": "alleen de achternaam staat er, geen voornaam of initialen",
    "official_without_initials": "de lijst geeft geen initialen voor deze functionaris",
    "gemeente_far": "de gemeente wordt elders in het document genoemd, niet hier",
}


def _person_whitelist_hint_to_detection(
    det: NERDetection,
    bboxes: list[Bbox],
    hit: PersonWhitelistHit,
) -> PipelineDetection:
    """Surface an unconfirmed whitelist hit as a pending lead.

    The surname is on a municipal officials list, but nothing in the
    document says this is that person. Rejecting on that alone is how
    private citizens kept their names in published documents (#92), so
    the detection stays ``pending`` at its normal Woo article and the
    reviewer gets the lead and the reason it is only a lead.
    """
    missing = _WHITELIST_HINT_REASON.get(hit.hint_reason, "niet bevestigd")
    reasoning = (
        f"Mogelijk {hit.official.functie.lower()} bij {hit.municipality_name} "
        f"({hit.official.display_name}) — niet bevestigd: {missing}."
    )
    return _persoon_pending(
        det,
        bboxes,
        reasoning=reasoning,
        source="whitelist_gemeente_hint",
    )


def _ner_passthrough(
    det: NERDetection,
    bboxes: list[Bbox],
    *,
    tier: str,
    review_status: PipelineReviewStatus,
    woo_article_fallback: str | None = None,
) -> PipelineDetection:
    """Pass an NER hit through to a PipelineDetection with no rewrite.

    Used for Tier 1 regex hits (auto_accepted, no fallback article) and for
    the generic Tier 2 "no rule matched" tail (pending, fallback article
    5.1.2e).
    """
    return _pipeline_detection_from_ner(
        det,
        bboxes,
        tier=tier,  # type: ignore[arg-type]
        woo_article=det.woo_article or woo_article_fallback,
        review_status=review_status,
        reasoning=det.reasoning,
        source=det.source,
    )


def _address_whitelist_to_detection(
    det: NERDetection,
    bboxes: list[Bbox],
    reason: str,
) -> PipelineDetection:
    """Map an address-whitelist hit onto a PipelineDetection.

    The original Tier 1 regex (postcode, email, phone, url) or Tier 2
    Deduce ``adres`` would have auto-accepted this detection; the
    whitelist flips it to ``rejected`` so the reviewer sees it in the
    list but the default is to leave it visible.
    """
    return _pipeline_detection_from_ner(
        det,
        bboxes,
        woo_article=None,
        review_status="rejected",
        reasoning=reason,
        source="whitelist_gemeente",
    )


_STRUCTURE_REASON: dict[str, str] = {
    "email_header": "Naam in e-mailheader",
    "signature_block": "Naam in handtekeningblok",
    "salutation": "Naam in aanhef",
}


def _structure_to_pipeline_detection(
    det: NERDetection,
    bboxes: list[Bbox],
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
        return _pipeline_detection_from_ner(
            det,
            bboxes,
            entity_type="persoon",
            tier="2",
            confidence=min(det.confidence + 0.15, 0.95),
            woo_article=DEFAULT_WOO_ARTICLE,
            review_status="auto_accepted",
            reasoning=f"{reason_stem} — automatisch geaccepteerd op basis van context.",
            source="structure",
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
    gemeente_mentions: dict[str, tuple[int, ...]]
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
    gemeente_mentions = find_gemeente_mentions(extraction.full_text, whitelist_index)
    if gemeente_mentions:
        logger.info(
            "pipeline.whitelist_active_gemeenten",
            count=len(gemeente_mentions),
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
        gemeente_mentions=gemeente_mentions,
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
) -> list[Bbox]:
    """Resolve a NER detection to exactly one bbox via occurrence index."""
    return resolve_occurrence_bboxes(
        extraction.pages, extraction.full_text, det.text, det.start_char
    )


# =========================================================================
# Classification chains — one function per tier / entity-type
# =========================================================================


def _classify_tier1(
    det: NERDetection,
    bboxes: list[Bbox],
    ctx: _DocContext,
) -> PipelineDetection:
    """Classify a Tier 1 (regex) detection.

    Priority:
      1. Address whitelist → rejected
      2. KvK → pending (public handelsregister data)
      3. Organisation context → pending (#96)
      4. Default → auto_accepted
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
        return _pipeline_detection_from_ner(
            det,
            bboxes,
            tier="1",
            woo_article=det.woo_article,
            review_status="pending",
            reasoning=(
                "KvK-nummer gedetecteerd — openbaar handelsregistergegeven, standaard niet lakken."
            ),
            source=det.source,
        )

    # 3. Organisation context (#96): a desk mailbox, a published web
    # page, the switchboard in the letterhead, the postcode of the
    # sender's own address block. Auto-accepting these deletes public
    # information from the export without anyone looking at it, which
    # is exactly what #90 says a Tier 1 hit may not do without positive
    # evidence of a person. Pending, never rejected — the reader gets
    # the reason and decides.
    org_reason = organisation_context_reason(
        det.entity_type,
        det.text,
        ctx.extraction.full_text,
        det.start_char,
    )
    if org_reason is not None:
        return _pipeline_detection_from_ner(
            det,
            bboxes,
            tier="1",
            woo_article=det.woo_article,
            review_status="pending",
            reasoning=org_reason,
            source=det.source,
        )

    # 4. Default: auto-accept
    return _ner_passthrough(det, bboxes, tier="1", review_status="auto_accepted")


def _classify_persoon(
    det: NERDetection,
    bboxes: list[Bbox],
    ctx: _DocContext,
) -> PipelineDetection:
    """Classify a Tier 2 persoon detection.

    Priority chain (first match wins):
      1. Reference list → rejected (publiek_functionaris)
      2. Municipality officials whitelist → rejected
      3. Mandate cue ("namens dezen") → pending (ambtenaar)
      4. Legal-form lead ("Maatschap …") → pending (trading name)
      5. Publiek title match → rejected
      6. Structure enclosure → auto_accepted or pending
      7. Ambtenaar title match → pending (pre-filled role)
      8. Unconfirmed whitelist lead → pending
      9. Deduce fallback → pending
    """
    # 1. Reference list (#17) — strongest signal, encodes reviewer knowledge
    if (
        ctx.official_names_normalized
        and normalize_reference_name(det.text) in ctx.official_names_normalized
    ):
        return _pipeline_detection_from_ner(
            det,
            bboxes,
            entity_type="persoon",
            tier="2",
            confidence=0.95,
            woo_article=None,
            review_status="rejected",
            reasoning="Naam op publiek-functionarissenlijst van dit document.",
            source="reference_list",
            subject_role="publiek_functionaris",
        )

    # 2. Municipality officials whitelist — gated on a gemeente named
    # near the span *and* on a given name or initials that identify this
    # official. Only a confirmed hit may reject here; an unconfirmed one
    # is a lead and must not short-circuit the rules below, which can
    # still classify the detection better (mandate cue, title, structure).
    # It is picked up at the tail instead (#92).
    whitelist_hit = match_person_whitelist(
        det.text,
        det.start_char,
        det.end_char,
        ctx.extraction.full_text,
        ctx.gemeente_mentions,
        ctx.whitelist_index,
    )
    if whitelist_hit is not None and whitelist_hit.confirmed:
        return _person_whitelist_to_detection(det, bboxes, whitelist_hit)

    # 3. Mandate cue (#94, #111) — "Gedeputeerde Staten van Drenthe,
    # namens dezen, <naam>", or the rijksbrief order that prints the
    # signatory first and the mandating office after it. Either way the
    # name is the ambtenaar who signed on the body's behalf, so it beats
    # both the publiek-title rule below and the signature block's
    # auto-accept: never rejected, never auto-redacted.
    if find_mandate_cue_before(ctx.extraction.full_text, det.start_char):
        return mandate_cue_to_detection(det, bboxes)
    if find_mandate_cue_after(ctx.extraction.full_text, det.end_char):
        return mandate_cue_to_detection(det, bboxes, position="after")

    # 4. Legal-form lead (#96) — "Afschrift aan: Maatschap H.J. Kersten
    # en C.H. Kersten-Ensing". The partners' names *are* the name the
    # business trades under, which is why the publisher left them
    # visible; the signature-block rule below would auto-redact them.
    # Pending, not rejected: they are still names of natural persons and
    # the reviewer may well decide to redact them anyway.
    form = legal_form_lead(ctx.extraction.full_text, det.start_char)
    if form is not None:
        return _persoon_pending(
            det,
            bboxes,
            reasoning=(
                f"Naam volgt direct op een rechtsvorm ({form}) — vermoedelijk de "
                "tenaamstelling van een bedrijf, niet een privépersoon."
            ),
            source="rule",
        )

    # 5 + 7. Title match — computed once, split across publiek/ambtenaar
    title_match = match_function_title(
        ctx.extraction.full_text, det.text, det.start_char, det.end_char
    )

    # 5. Publiek title → rejected (beats structure: "Burgemeester X" in
    # a signature block must still be marked as not-to-redact)
    if title_match is not None and title_match.list_name == "publiek":
        rule_det = title_match_to_detection(det, bboxes, title_match)
        if rule_det is not None:
            return rule_det

    # 6. Structure enclosure (email header / signature block / salutation).
    # The `Onderwerp:` line is part of the header block but carries prose,
    # not a header value, so a hit there falls through to the rules below
    # and stays at most `pending` (#105).
    enclosing = find_enclosing_structure(ctx.structure_spans, det.start_char, det.end_char)
    if enclosing is not None and not (
        enclosing.kind == "email_header"
        and is_email_subject_line(ctx.extraction.full_text, det.start_char)
    ):
        return _structure_to_pipeline_detection(det, bboxes, enclosing)

    # 7. Ambtenaar title → pending with pre-filled role
    if title_match is not None:
        rule_det = title_match_to_detection(det, bboxes, title_match)
        if rule_det is not None:
            return rule_det

    # 8. Unconfirmed whitelist lead → pending, with the lead spelled out
    if whitelist_hit is not None:
        return _person_whitelist_hint_to_detection(det, bboxes, whitelist_hit)

    # 9. Deduce fallback → pending
    return _persoon_pending(det, bboxes, reasoning=det.reasoning, source="deduce")


def _classify_other_tier2(
    det: NERDetection,
    bboxes: list[Bbox],
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
        woo_article_fallback=DEFAULT_WOO_ARTICLE,
    )


def _classify_detection(
    det: NERDetection,
    bboxes: list[Bbox],
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
