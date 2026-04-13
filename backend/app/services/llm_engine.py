"""LLM engine — orchestrates the full detection pipeline.

Runs Tier 1 (regex) and Tier 2 (Deduce NER + local LLM verification).
Tier 3 (LLM content analysis) is temporarily disabled for fast mode;
when re-enabled it can be wired back into run_pipeline().

Tier 2 person detections are verified by a local LLM (via
`LLMProvider.classify_role`) to filter out the false positives that
Deduce — a Dutch medical de-identification library — routinely
produces on non-medical prose: institutions, locations, and fragments
tagged as `persoon`. The LLM's verdict also feeds the redact/keep
decision when the text really is a name.
"""

import asyncio
import re
from dataclasses import dataclass, field

from app.llm import get_llm_provider
from app.llm.provider import LLMProvider, RoleClassification
from app.logging_config import get_logger
from app.services.ner_engine import NERDetection, detect_all
from app.services.pdf_engine import ExtractionResult, find_span_for_text

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
    bounding_boxes: list[dict]
    reasoning: str
    source: str
    is_environmental: bool = False


@dataclass
class PipelineResult:
    """Result of the full detection pipeline."""

    detections: list[PipelineDetection] = field(default_factory=list)
    page_count: int = 0
    has_environmental_content: bool = False


def _context_around(full_text: str, start: int, end: int, window: int) -> str:
    """Return a slice of `full_text` roughly centred on [start, end] with
    up to `window` characters on each side. Used to give the LLM enough
    surrounding text to decide whether a detected string is actually a
    person — and in what capacity — without sending the whole document.
    """
    left = max(0, start - window)
    right = min(len(full_text), end + window)
    return full_text[left:right].strip()


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
    bboxes: list[dict],
    verdict: RoleClassification | None,
) -> PipelineDetection | None:
    """Map an LLM verdict onto a PipelineDetection.

    Returns None if the detection should be dropped entirely (the LLM
    says the text is not actually a person). On unclear verdicts we
    default to `pending` so a human can decide.
    """
    # LLM unavailable or failed → keep as pending with Deduce reasoning.
    if verdict is None:
        return PipelineDetection(
            entity_text=det.text,
            entity_type="persoon",
            tier="2",
            confidence=det.confidence,
            woo_article="5.1.2e",
            review_status="pending",
            bounding_boxes=bboxes,
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
        )

    # Citizens, civil servants, or anything else the model wants to
    # redact — queue for manual confirmation with the LLM's reasoning.
    return PipelineDetection(
        entity_text=det.text,
        entity_type="persoon",
        tier="2",
        confidence=verdict.confidence,
        woo_article="5.1.2e",
        review_status="pending",
        bounding_boxes=bboxes,
        reasoning=verdict.reason_nl or det.reasoning,
        source="llm",
    )


async def run_pipeline(
    extraction: ExtractionResult,
    public_official_names: list[str] | None = None,
    use_llm_verification: bool = True,
) -> PipelineResult:
    """Run the full three-tier detection pipeline on an extracted document.

    Args:
        extraction: Result from pdf_engine.extract_text().
        public_official_names: Names from the dossier's public officials
            list. These always short-circuit to "niet lakken" without
            calling the LLM.
        use_llm_verification: If True (default), Tier 2 `persoon`
            detections that are not on the public officials list are
            passed through the local LLM for false-positive filtering
            and role classification. Tests pass False to avoid
            depending on a running Ollama instance.
    """
    result = PipelineResult(page_count=extraction.page_count)
    official_names_lower = {n.lower() for n in (public_official_names or [])}

    logger.info(
        "pipeline.started",
        page_count=extraction.page_count,
        llm_enabled=use_llm_verification,
    )

    # Check for environmental content (Art. 5.1 lid 6-7 Woo)
    result.has_environmental_content = _check_environmental_content(extraction.full_text)

    # --- Tier 1 + Tier 2: run NER ---
    ner_detections = detect_all(extraction.full_text)
    logger.info("pipeline.ner_completed", detection_count=len(ner_detections))

    # Bucket detections. Tier 1 and non-person Tier 2 pass through
    # unchanged; person detections either match the officials list
    # (instant decision) or need LLM verification.
    persons_needing_llm: list[tuple[NERDetection, list[dict]]] = []

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
                )
            )
            continue

        if det.entity_type == "persoon":
            if det.text.lower() in official_names_lower:
                result.detections.append(
                    PipelineDetection(
                        entity_text=det.text,
                        entity_type="persoon",
                        tier="2",
                        confidence=0.90,
                        woo_article=None,
                        review_status="rejected",
                        bounding_boxes=bboxes,
                        reasoning=(
                            f"Persoonsnaam '{det.text}' gevonden in de lijst van publieke "
                            f"functionarissen. Niet lakken."
                        ),
                        source="deduce",
                    )
                )
                continue

            if use_llm_verification:
                persons_needing_llm.append((det, bboxes))
                continue

            # LLM disabled — fall back to the pre-LLM behaviour.
            result.detections.append(
                PipelineDetection(
                    entity_text=det.text,
                    entity_type="persoon",
                    tier="2",
                    confidence=det.confidence,
                    woo_article="5.1.2e",
                    review_status="pending",
                    bounding_boxes=bboxes,
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
            )
        )

    # --- Tier 2 LLM verification pass ---
    if persons_needing_llm:
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

    # --- Tier 3: skipped (LLM disabled for fast mode) ---
    logger.info(
        "pipeline.completed",
        detection_count=len(result.detections),
        tier3_skipped=True,
    )

    return result
