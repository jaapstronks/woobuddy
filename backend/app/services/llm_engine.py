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
as `review_status="pending"` and the reviewer decides. The file is still
named `llm_engine.py` for historical reasons; the module imported by
`app.api.analyze` is `run_pipeline`.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.logging_config import get_logger
from app.services.custom_term_matcher import (
    CustomTermLike,
    TermMatch,
    match_custom_terms,
)
from app.services.name_engine import normalize_reference_name
from app.services.ner_engine import NERDetection, detect_all
from app.services.pdf_engine import (
    ExtractionResult,
    count_word_boundary_matches,
    find_span_for_text,
)
from app.services.role_engine import (
    FunctionTitleMatch,
    find_function_title_near,
    get_function_title_lists,
)
from app.services.structure_engine import (
    StructureSpan,
    detect_structures,
    find_enclosing_structure,
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

# Environmental information keywords (Art. 5.1 lid 6-7 Woo)
# Environmental info has restricted redaction possibilities
_ENVIRONMENTAL_SIGNALS = [
    r"milieu",
    r"luchtkwaliteit",
    r"bodemverontreiniging",
    r"waterkwaliteit",
    r"geluidshinder",
    r"geluidsoverlast",
    r"emissie",
    r"uitstoot",
    r"fijnstof",
    r"stikstof",
    r"PFAS",
    r"asbest",
    r"afvalstoffen",
    r"afvalwater",
    r"grondwater",
    r"oppervlaktewater",
    r"lozingen",
    r"milieuvergunning",
    r"omgevingsvergunning",
    r"bestrijdingsmiddelen",
    r"biodiversiteit",
    r"natuurbescherming",
    r"Natura\s*2000",
    r"gezondheidsrisico",
    r"volksgezondheid",
    r"energieverbruik",
    r"CO2",
    r"klimaat",
    r"stralingsbescherming",
]

_ENVIRONMENTAL_PATTERN = re.compile("|".join(_ENVIRONMENTAL_SIGNALS), re.IGNORECASE)


def _check_environmental_content(text: str) -> bool:
    """Check if text contains environmental information (Art. 5.1 lid 6-7 Woo)."""
    return bool(_ENVIRONMENTAL_PATTERN.search(text))


@dataclass
class PipelineDetection:
    """A detection ready to be stored in the database."""

    entity_text: str
    entity_type: str
    tier: str
    confidence: float
    woo_article: str | None
    review_status: str  # auto_accepted, pending
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


def _match_function_title(
    full_text: str,
    span_text: str,
    start_char: int,
    end_char: int,
) -> FunctionTitleMatch | None:
    """Look for a function title near — or inside — a Tier 2 persoon span.

    The normal case is a title in the surrounding text ("Wethouder Jan
    de Vries"), which `role_engine.find_function_title_near` handles
    via the character window. But Deduce's person span sometimes
    swallows the title itself (annotation covers "Wethouder Jan de
    Vries" as one "persoon"), in which case the character window before
    the span is empty and the normal path finds nothing. As a fallback
    we scan the span text for a leading title — that's the apposition
    case but folded into the detection.

    Kept as a local helper so tests can monkey-patch it without
    reaching into the role_engine module.
    """
    lists = get_function_title_lists()
    match = find_function_title_near(full_text, start_char, end_char, lists)
    if match is not None:
        return match

    # Fallback: leading-title-in-span. We only accept a match at the
    # start of the span (so "Jan de Vries Wethouder" doesn't fire here —
    # that's an after-context case that already goes through the
    # character-window path). Same tie-breaking as before: publiek beats
    # ambtenaar if both happen to fit the prefix (extremely rare).
    stripped = (span_text or "").lstrip()
    best: FunctionTitleMatch | None = None
    for list_name, title, pattern in lists.iter_all():
        m = pattern.match(stripped)
        if m is None:
            continue
        # Require at least one token after the title inside the span,
        # otherwise the span is just the title with no name attached.
        remainder = stripped[m.end() :].strip()
        if not remainder:
            continue
        candidate = FunctionTitleMatch(
            title=title,
            list_name=list_name,
            position="before",
            tokens_between=0,
        )
        if best is None or (candidate.list_name == "publiek" and best.list_name == "ambtenaar"):
            best = candidate
    return best


def _title_match_to_detection(
    det: NERDetection,
    bboxes: list[dict[str, float]],
    match: FunctionTitleMatch,
) -> PipelineDetection | None:
    """Map a rule-engine hit onto a PipelineDetection.

    Publiek titles default to `review_status="rejected"` (the
    public-officials-do-not-redact rule). Ambtenaar titles stay
    `pending` but with a pre-filled role so the reviewer only confirms.
    """
    if match.list_name == "publiek":
        return PipelineDetection(
            entity_text=det.text,
            entity_type="persoon",
            tier="2",
            confidence=min(det.confidence + 0.05, 0.95),
            woo_article=None,
            review_status="rejected",
            bounding_boxes=bboxes,
            reasoning=(
                f"Publiek functionaris: voorafgegaan door '{match.title}' in de brontekst."
                if match.position == "before"
                else f"Publiek functionaris: gevolgd door '{match.title}' in de brontekst."
            ),
            source="rule",
            subject_role="publiek_functionaris",
            start_char=det.start_char,
            end_char=det.end_char,
        )

    # Ambtenaar — keep pending, pre-fill the role, reviewer confirms.
    return PipelineDetection(
        entity_text=det.text,
        entity_type="persoon",
        tier="2",
        confidence=det.confidence,
        woo_article="5.1.2e",
        review_status="pending",
        bounding_boxes=bboxes,
        reasoning=(
            f"Vermoedelijk ambtenaar in functie: voorafgegaan door '{match.title}'."
            if match.position == "before"
            else f"Vermoedelijk ambtenaar in functie: gevolgd door '{match.title}'."
        ),
        source="rule",
        subject_role="ambtenaar",
        start_char=det.start_char,
        end_char=det.end_char,
    )


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


def _custom_term_match_to_detection(
    match: TermMatch,
    bboxes: list[dict[str, Any]],
) -> PipelineDetection:
    """Map a custom-term occurrence onto a PipelineDetection.

    Custom terms are opt-in — the reviewer already made the decision by
    typing the term — so the resulting row goes in at
    `review_status="accepted"` rather than `pending`. The `source`
    tag is the discriminator the redaction log (#19) uses to show "why
    was this passage redacted?" without exposing the term itself as
    content.
    """
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


async def run_pipeline(
    extraction: ExtractionResult,
    public_official_names: list[str] | None = None,
    custom_terms: Sequence[CustomTermLike] | None = None,
) -> PipelineResult:
    """Run the detection pipeline on an extracted document.

    Args:
        extraction: Result from pdf_engine.extract_text().
        public_official_names: Names from the dossier's public officials
            list. These short-circuit to "niet lakken" without calling
            any classifier. Empty by default — the per-document
            reference list UI was stripped during simplification and
            will return as todo #40.
        custom_terms: Per-document custom wordlist (#21). Each term is
            matched with a case-insensitive substring scan; every hit
            becomes a `custom` detection at `review_status="accepted"`
            with `source="custom_wordlist"`. The reviewer already
            decided to redact these by typing them into the panel.
    """
    result = PipelineResult(page_count=extraction.page_count)
    # #17 — reference list matching. Normalize once (lowercase + NFKD
    # diacritic strip + collapsed whitespace) so "De Vries" typed in the
    # panel matches "de vries" or "De  Vries" in the document. The set is
    # empty when the frontend did not attach a reference list.
    official_names_normalized = {
        normalize_reference_name(n) for n in (public_official_names or []) if n
    }
    official_names_normalized.discard("")

    logger.info(
        "pipeline.started",
        page_count=extraction.page_count,
    )

    # Check for environmental content (Art. 5.1 lid 6-7 Woo)
    result.has_environmental_content = _check_environmental_content(extraction.full_text)

    # Whitelist — pre-compute once per document. The address whitelist is
    # global (postcodes and municipal contact details are public
    # everywhere), but the public-officials whitelist is gated on the
    # `active_gemeenten` set: a raadslid of Alblasserdam only short-
    # circuits when the document actually mentions gemeente Alblasserdam.
    whitelist_index: WhitelistIndex = get_whitelist_index()
    active_gemeenten = find_active_gemeenten(extraction.full_text, whitelist_index)
    if active_gemeenten:
        logger.info(
            "pipeline.whitelist_active_gemeenten",
            count=len(active_gemeenten),
        )

    # --- Structure pass (#14): scan the full text for email headers,
    # signature blocks, and salutations. The spans are also returned to
    # the frontend so #20 can render "sweep this block" affordances.
    structure_spans = detect_structures(extraction)
    result.structure_spans = structure_spans
    if structure_spans:
        logger.info(
            "pipeline.structures_detected",
            email_header=sum(1 for s in structure_spans if s.kind == "email_header"),
            signature_block=sum(1 for s in structure_spans if s.kind == "signature_block"),
            salutation=sum(1 for s in structure_spans if s.kind == "salutation"),
        )

    # --- Tier 1 + Tier 2: run NER ---
    ner_detections = detect_all(extraction.full_text)
    logger.info("pipeline.ner_completed", detection_count=len(ner_detections))

    for det in ner_detections:
        # Resolve this detection to exactly ONE bbox — the occurrence at
        # `det.start_char` in the combined full text. `find_span_for_text`
        # would otherwise return every bbox for every match of `det.text`
        # on the page, and the frontend bbox→text resolver would join
        # them all back into a single sidebar card ("A.B. Bakker A.B.
        # Bakker"). Counting word-boundary matches up to `start_char`
        # gives us the occurrence index of this specific hit.
        occurrence_idx = count_word_boundary_matches(
            extraction.full_text, det.text, limit=det.start_char
        )
        bboxes = find_span_for_text(extraction.pages, det.text, occurrence_index=occurrence_idx)
        if not bboxes:
            # Defensive fallback: if occurrence counting and span
            # matching disagree (different tokenisation between Deduce's
            # full-text view and pdf.js's text items), still return a
            # single bbox rather than re-emitting the multi-bbox bug.
            all_bboxes = find_span_for_text(extraction.pages, det.text)
            bboxes = all_bboxes[:1]

        if det.tier == "1":
            # Address whitelist (postcode / email / telefoon / url). A
            # hit flips the default to "niet lakken" with a municipality
            # reasoning string, but the detection still shows up in the
            # review list so the reviewer can override. The full-text
            # context is threaded through so the postbus-postcode rule
            # can inspect the characters before the span.
            addr_reason = match_address_whitelist(
                det.text,
                det.entity_type,
                whitelist_index,
                full_text=extraction.full_text,
                start_char=det.start_char,
            )
            if addr_reason is not None:
                result.detections.append(_address_whitelist_to_detection(det, bboxes, addr_reason))
                continue

            result.detections.append(
                PipelineDetection(
                    entity_text=det.text,
                    entity_type=det.entity_type,
                    tier="1",
                    confidence=det.confidence,
                    woo_article=det.woo_article,
                    review_status="auto_accepted",
                    bounding_boxes=bboxes,
                    reasoning=det.reasoning,
                    source=det.source,
                    start_char=det.start_char,
                    end_char=det.end_char,
                )
            )
            continue

        if det.entity_type == "persoon":
            # #17 — reference list is the strongest signal. It beats the
            # rule-based title matcher (#13) and the structure pass (#14)
            # because it encodes specific knowledge the reviewer already
            # has about this document ("the college van B&W of gemeente X
            # is Jan de Vries, Anna Jansen, …"). A match short-circuits
            # to `rejected` with `source="reference_list"`.
            if (
                official_names_normalized
                and normalize_reference_name(det.text) in official_names_normalized
            ):
                result.detections.append(
                    PipelineDetection(
                        entity_text=det.text,
                        entity_type="persoon",
                        tier="2",
                        confidence=0.95,
                        woo_article=None,
                        review_status="rejected",
                        bounding_boxes=bboxes,
                        reasoning=("Naam op publiek-functionarissenlijst van dit document."),
                        source="reference_list",
                        subject_role="publiek_functionaris",
                        start_char=det.start_char,
                        end_char=det.end_char,
                    )
                )
                continue

            # Gemeente-officials whitelist — context-gated on the
            # `active_gemeenten` set. Applied before the title-matcher so
            # a raadslid match wins over a generic "wethouder" window
            # match (the whitelist is more specific — it names the
            # person, not just the role). Common surnames additionally
            # require a visible-initials match; see whitelist_engine.
            whitelist_hit = match_person_whitelist(
                det.text,
                det.start_char,
                det.end_char,
                extraction.full_text,
                active_gemeenten,
                whitelist_index,
            )
            if whitelist_hit is not None:
                result.detections.append(_person_whitelist_to_detection(det, bboxes, whitelist_hit))
                continue

            # Rule-based role classifier (#13): scan a small window around
            # the detection for a Dutch function title. A publiek match
            # flips the default to "don't redact"; an ambtenaar match
            # pre-fills the role but keeps the detection pending so the
            # reviewer confirms. This is the main reason the pipeline no
            # longer needs an LLM for the common case.
            title_match = _match_function_title(
                extraction.full_text, det.text, det.start_char, det.end_char
            )

            # Publiek functionaris is the strongest signal we have — it
            # short-circuits everything else (including the structure
            # pass below). "Burgemeester X" inside a signature block
            # must still be marked as not-to-redact.
            if title_match is not None and title_match.list_name == "publiek":
                rule_det = _title_match_to_detection(det, bboxes, title_match)
                if rule_det is not None:
                    result.detections.append(rule_det)
                    continue

            # Structure pass (#14): a Tier 2 name enclosed by an email
            # header or signature block auto-accepts; a name inside a
            # salutation boosts confidence and pre-fills subject_role.
            enclosing = find_enclosing_structure(structure_spans, det.start_char, det.end_char)
            if enclosing is not None:
                result.detections.append(_structure_to_pipeline_detection(det, bboxes, enclosing))
                continue

            # Ambtenaar title — still worth emitting (pre-filled role,
            # pending status) even though no structure matched.
            if title_match is not None:
                rule_det = _title_match_to_detection(det, bboxes, title_match)
                if rule_det is not None:
                    result.detections.append(rule_det)
                    continue

            # No rule hit — fall back to Deduce-only pending.
            result.detections.append(
                _persoon_pending(
                    det,
                    bboxes,
                    reasoning=det.reasoning,
                    source="deduce",
                )
            )
            continue

        # Other Tier 2 entities (adres, datum, organisatie, …).
        # Address whitelist applies here too — a Deduce ``adres`` span
        # that resolves to a gemeente bezoekadres or the woonplaats of a
        # municipal address is public and should not be redacted.
        addr_reason = match_address_whitelist(
            det.text,
            det.entity_type,
            whitelist_index,
            full_text=extraction.full_text,
            start_char=det.start_char,
        )
        if addr_reason is not None:
            result.detections.append(_address_whitelist_to_detection(det, bboxes, addr_reason))
            continue

        result.detections.append(
            PipelineDetection(
                entity_text=det.text,
                entity_type=det.entity_type,
                tier="2",
                confidence=det.confidence,
                woo_article=det.woo_article or "5.1.2e",
                review_status="pending",
                bounding_boxes=bboxes,
                reasoning=det.reasoning,
                source=det.source,
                start_char=det.start_char,
                end_char=det.end_char,
            )
        )

    # --- Custom wordlist pass (#21) ---
    #
    # Runs AFTER the NER pass so we have the full detection list to
    # dedupe against. The spec is clear that when a custom-term match
    # overlaps a Tier 1 or Tier 2 detection, the custom term's Woo-
    # artikel wins (most specific reviewer intent) and the bbox is the
    # union — the reviewer's decision is at least as restrictive as the
    # pipeline's default. Non-overlapping matches simply become new
    # `custom` detections at `review_status="accepted"`.
    if custom_terms:
        term_matches = match_custom_terms(extraction.full_text, custom_terms)
        # Cache bbox lookups per term — every occurrence of the same
        # term resolves to the same bbox set through `find_span_for_text`,
        # so a single call suffices no matter how many matches the
        # matcher produced.
        bbox_cache: dict[str, list[dict[str, Any]]] = {}
        custom_added = 0
        custom_merged = 0
        for m in term_matches:
            cache_key = m.term.lower()
            if cache_key not in bbox_cache:
                bbox_cache[cache_key] = find_span_for_text(extraction.pages, m.term)
            term_bboxes = bbox_cache[cache_key]

            # Dedupe against existing detections with character offsets —
            # reviewer-authored rows (manual / search_redact) have no
            # offsets and are skipped here. An overlap is any
            # intersection on the half-open [start_char, end_char) range.
            overlap: PipelineDetection | None = None
            for existing in result.detections:
                if existing.start_char is None or existing.end_char is None:
                    continue
                if existing.start_char < m.end_char and m.start_char < existing.end_char:
                    overlap = existing
                    break

            if overlap is not None:
                # Mutate the existing row: the custom term's article
                # wins, the bboxes union, and the source/reasoning are
                # rewritten so the redaction log shows *why* this
                # passage was redacted from the reviewer's point of view.
                overlap.woo_article = m.woo_article
                seen = {
                    (b.get("page"), b.get("x0"), b.get("y0"), b.get("x1"), b.get("y1"))
                    for b in overlap.bounding_boxes
                }
                for bb in term_bboxes:
                    key = (bb.get("page"), bb.get("x0"), bb.get("y0"), bb.get("x1"), bb.get("y1"))
                    if key not in seen:
                        overlap.bounding_boxes.append(bb)
                        seen.add(key)
                overlap.source = "custom_wordlist"
                overlap.review_status = "accepted"
                overlap.reasoning = (
                    f"Zoekterm '{m.term}' uit documentspecifieke lijst "
                    f"(overschrijft eerdere detectie)."
                )
                custom_merged += 1
                continue

            result.detections.append(_custom_term_match_to_detection(m, term_bboxes))
            custom_added += 1

        logger.info(
            "pipeline.custom_terms_completed",
            terms=len(custom_terms),
            matches=len(term_matches),
            added=custom_added,
            merged=custom_merged,
        )

    logger.info(
        "pipeline.completed",
        detection_count=len(result.detections),
    )

    return result
