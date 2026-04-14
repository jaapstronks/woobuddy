"""LLM engine — orchestrates the full detection pipeline.

Runs Tier 1 (regex) and Tier 2 (Deduce NER + heuristic filters). Tier 3
is reserved and currently unused.

The LLM person-role classification pass is **dormant by default**. The
live pipeline is regex + Deduce + heuristics; there is no Ollama call on
the default code path. Set `settings.llm_tier2_enabled=True` to re-enable
the verification pass for experimentation. See `app/llm/README.md` for
why the code is kept in-tree.

When the LLM layer is dormant, Deduce `persoon` detections surface as
`review_status="pending"` and the reviewer decides. The rule-based
replacement for LLM role classification (public-official lists,
structure heuristics, function titles) lands in todos #36–#40.
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.llm.provider import LLMProvider, RoleClassification
from app.logging_config import get_logger
from app.services.custom_term_matcher import (
    CustomTermLike,
    TermMatch,
    match_custom_terms,
)
from app.services.name_engine import normalize_reference_name
from app.services.ner_engine import NERDetection, detect_all
from app.services.pdf_engine import ExtractionResult, find_span_for_text
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

# NOTE: `app.llm.provider` is import-safe when the layer is dormant — it only
# declares the abstract interface and dataclasses. The concrete Ollama
# implementation lives in `app.llm.ollama` and is imported lazily, inside the
# verification pass below, so a dormant pipeline never pulls in the HTTP client
# or triggers the provider factory's log line.

logger = get_logger(__name__)

# How much text to show the LLM around each detection. Enough for the
# model to see a salutation, functietitel, or surrounding sentence
# without pulling in the whole document.
_LLM_CONTEXT_WINDOW = 200

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


def _context_around(full_text: str, start: int, end: int, window: int) -> str:
    """Return a slice of `full_text` roughly centred on [start, end] with
    up to `window` characters on each side. Used to give the LLM enough
    surrounding text to decide whether a detected string is actually a
    person — and in what capacity — without sending the whole document.
    """
    left = max(0, start - window)
    right = min(len(full_text), end + window)
    return full_text[left:right].strip()


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


async def _classify_person(
    provider: LLMProvider,
    name: str,
    context: str,
) -> RoleClassification | None:
    """Call the LLM role classifier, returning None on any failure.

    The pipeline must not fail if the LLM is unreachable or returns
    junk — in that case we fall back to the original Deduce verdict
    (detection kept as `pending` for manual review).
    """
    try:
        return await provider.classify_role(
            person_name=name,
            surrounding_context=context,
        )
    except Exception:
        logger.warning("pipeline.llm_verification_failed", exc_info=True)
        return None


def _verdict_to_pipeline_detection(
    det: NERDetection,
    bboxes: list[dict[str, Any]],
    verdict: RoleClassification | None,
) -> PipelineDetection | None:
    """Map an LLM verdict onto a PipelineDetection.

    Returns None if the detection should be dropped entirely (the LLM
    says the text is not actually a person). On unclear verdicts we
    default to `pending` so a human can decide.
    """
    # LLM unavailable or failed → keep as pending with Deduce reasoning.
    if verdict is None:
        return _persoon_pending(
            det,
            bboxes,
            reasoning=det.reasoning,
            source="deduce",
        )

    # LLM says this is not a person at all — drop the detection.
    if verdict.role == "not_a_person":
        logger.info(
            "pipeline.llm_dropped_non_person",
            reason=verdict.reason_nl[:80] if verdict.reason_nl else "",
        )
        return None

    # LLM says the person is a public official acting in capacity —
    # suggest keeping visible (review_status='rejected' meaning
    # "suggestion rejected", not the person being rejected).
    if verdict.role == "public_official" and not verdict.should_redact:
        return PipelineDetection(
            entity_text=det.text,
            entity_type="persoon",
            tier="2",
            confidence=verdict.confidence,
            woo_article=None,
            review_status="rejected",
            bounding_boxes=bboxes,
            reasoning=(
                verdict.reason_nl or "Publiek functionaris in officiële hoedanigheid — niet lakken."
            ),
            source="llm",
            start_char=det.start_char,
            end_char=det.end_char,
        )

    # Citizens, civil servants, or anything else the model wants to
    # redact — queue for manual confirmation with the LLM's reasoning.
    return _persoon_pending(
        det,
        bboxes,
        reasoning=verdict.reason_nl or det.reasoning,
        source="llm",
        confidence=verdict.confidence,
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
    use_llm_verification: bool | None = None,
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
        use_llm_verification: If True, Tier 2 `persoon` detections that
            are not on the public officials list are passed through the
            local LLM for false-positive filtering and role
            classification. **Dormant by default** — when None, the
            value is read from `settings.llm_tier2_enabled`, which
            defaults to False. Callers that want deterministic behavior
            (tests) can pass an explicit True/False.
    """
    if use_llm_verification is None:
        use_llm_verification = settings.llm_tier2_enabled

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
        llm_enabled=use_llm_verification,
    )

    # Check for environmental content (Art. 5.1 lid 6-7 Woo)
    result.has_environmental_content = _check_environmental_content(extraction.full_text)

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

    # Bucket detections. Tier 1 and non-person Tier 2 pass through
    # unchanged; person detections either match the officials list
    # (instant decision) or need LLM verification.
    persons_needing_llm: list[tuple[NERDetection, list[dict[str, Any]]]] = []

    for det in ner_detections:
        bboxes = find_span_for_text(extraction.pages, det.text)

        if det.tier == "1":
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

            if use_llm_verification:
                persons_needing_llm.append((det, bboxes))
                continue

            # LLM disabled, no rule hit — fall back to Deduce-only pending.
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

    # --- Tier 2 LLM verification pass ---
    if persons_needing_llm:
        # Lazy import so the dormant path never touches `app.llm.ollama`
        # (and thus httpx/ollama client setup). Only runs when the flag
        # explicitly enables verification.
        from app.llm import get_llm_provider

        provider = get_llm_provider()
        verdicts = await asyncio.gather(
            *[
                _classify_person(
                    provider,
                    det.text,
                    _context_around(
                        extraction.full_text,
                        det.start_char,
                        det.end_char,
                        _LLM_CONTEXT_WINDOW,
                    ),
                )
                for det, _ in persons_needing_llm
            ]
        )

        dropped = 0
        for (det, bboxes), verdict in zip(persons_needing_llm, verdicts, strict=True):
            pipeline_det = _verdict_to_pipeline_detection(det, bboxes, verdict)
            if pipeline_det is None:
                dropped += 1
                continue
            result.detections.append(pipeline_det)

        logger.info(
            "pipeline.llm_verification_completed",
            verified=len(persons_needing_llm),
            dropped_as_non_person=dropped,
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

    # --- Tier 3: skipped (LLM disabled for fast mode) ---
    logger.info(
        "pipeline.completed",
        detection_count=len(result.detections),
        tier3_skipped=True,
    )

    return result
