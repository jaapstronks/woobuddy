"""LLM engine — orchestrates the full detection pipeline.

Combines Tier 1 (regex), Tier 2 (Deduce + LLM role classification),
and Tier 3 (LLM content analysis) into a single pipeline that processes
a document and produces detection results.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field

from app.llm import get_llm_provider
from app.llm.provider import ContentAnalysisResult, RoleClassification
from app.services.ner_engine import NERDetection, detect_all
from app.services.pdf_engine import ExtractionResult, PageText, find_span_for_text

logger = logging.getLogger(__name__)

# Tier 3 keyword signals — passages containing these are sent to the LLM
_TIER3_SIGNALS = [
    # Art. 5.2 — Personal policy opinions
    r"ik\s+adviseer",
    r"mijn\s+inschatting",
    r"het\s+lijkt\s+mij",
    r"ik\s+zou\s+voorstellen",
    r"naar\s+mijn\s+mening",
    r"ik\s+vind",
    r"ik\s+ben\s+van\s+mening",
    r"intern\s+beraad",
    r"beleidsadvies",
    r"conceptnota",
    # Art. 5.1.2f — Business data
    r"omzet",
    r"winst",
    r"offerte",
    r"aanbesteding",
    r"concurrentie",
    r"bedrijfsgeheim",
    # Art. 5.1.2d — Inspection / oversight
    r"handhaving",
    r"inspectie",
    r"toezicht",
    r"controleplan",
    # Art. 5.1.2i — Government functioning
    r"integriteitsonderzoek",
    r"functioneringsgesprek",
    # Art. 5.1.2c — Criminal investigation
    r"opsporingsonderzoek",
    r"verdachte",
    r"strafrechtelijk",
]

_TIER3_PATTERN = re.compile("|".join(_TIER3_SIGNALS), re.IGNORECASE)


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


@dataclass
class PipelineResult:
    """Result of the full detection pipeline."""

    detections: list[PipelineDetection] = field(default_factory=list)
    page_count: int = 0


def _get_context_window(full_text: str, start: int, end: int, window: int = 200) -> str:
    """Get surrounding context for a detection."""
    ctx_start = max(0, start - window)
    ctx_end = min(len(full_text), end + window)
    return full_text[ctx_start:ctx_end]


def _find_tier3_passages(pages: list[PageText]) -> list[tuple[str, int]]:
    """Find passages that should be sent to the LLM for Tier 3 analysis.

    Returns (passage_text, page_number) tuples.
    """
    passages: list[tuple[str, int]] = []
    for page in pages:
        # Split into paragraph-like chunks (by double newline or long gap)
        chunks = re.split(r"\n{2,}", page.full_text)
        if len(chunks) <= 1:
            # If no clear paragraphs, split by sentences
            chunks = re.split(r"(?<=[.!?])\s+", page.full_text)

        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 40:
                continue
            if _TIER3_PATTERN.search(chunk):
                passages.append((chunk, page.page_number))

    return passages


async def run_pipeline(
    extraction: ExtractionResult,
    public_official_names: list[str] | None = None,
) -> PipelineResult:
    """Run the full three-tier detection pipeline on an extracted document.

    Args:
        extraction: Result from pdf_engine.extract_text()
        public_official_names: Names from the dossier's public officials list
    """
    result = PipelineResult(page_count=extraction.page_count)
    official_names_lower = {n.lower() for n in (public_official_names or [])}
    llm = get_llm_provider()

    # --- Tier 1 + Tier 2: NER detection ---
    ner_detections = detect_all(extraction.full_text)

    for det in ner_detections:
        bboxes = find_span_for_text(extraction.pages, det.text)

        if det.tier == "1":
            result.detections.append(PipelineDetection(
                entity_text=det.text,
                entity_type=det.entity_type,
                tier="1",
                confidence=det.confidence,
                woo_article=det.woo_article,
                review_status="auto_accepted",
                bounding_boxes=bboxes,
                reasoning=det.reasoning,
                source=det.source,
            ))
        elif det.entity_type == "persoon":
            # Check public officials list first
            if det.text.lower() in official_names_lower:
                result.detections.append(PipelineDetection(
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
                ))
                continue

            # LLM role classification for names not on the officials list
            context = _get_context_window(
                extraction.full_text, det.start_char, det.end_char
            )
            try:
                classification: RoleClassification = await llm.classify_role(
                    person_name=det.text,
                    surrounding_context=context,
                )
                should_redact = classification.should_redact
                confidence = classification.confidence
                reasoning = classification.reason_nl
                review_status = "auto_accepted" if (
                    not should_redact and classification.role == "public_official"
                ) else "pending" if should_redact else "rejected"
                woo_article = "5.1.2e" if should_redact else None
            except Exception:
                logger.warning("LLM role classification failed for '%s', defaulting to pending", det.text)
                should_redact = True
                confidence = det.confidence
                reasoning = det.reasoning
                review_status = "pending"
                woo_article = "5.1.2e"

            result.detections.append(PipelineDetection(
                entity_text=det.text,
                entity_type="persoon",
                tier="2",
                confidence=confidence,
                woo_article=woo_article,
                review_status=review_status,
                bounding_boxes=bboxes,
                reasoning=reasoning,
                source="deduce+llm" if should_redact else "deduce+llm",
            ))
        else:
            # Other Tier 2 entities (addresses, dates, etc.)
            result.detections.append(PipelineDetection(
                entity_text=det.text,
                entity_type=det.entity_type,
                tier="2",
                confidence=det.confidence,
                woo_article=det.woo_article or "5.1.2e",
                review_status="pending",
                bounding_boxes=bboxes,
                reasoning=det.reasoning,
                source=det.source,
            ))

    # --- Tier 3: LLM content analysis ---
    tier3_passages = _find_tier3_passages(extraction.pages)

    for passage_text, page_number in tier3_passages:
        try:
            analysis: ContentAnalysisResult = await llm.analyze_content(
                passage=passage_text,
                surrounding_context=None,
            )
        except Exception:
            logger.warning("LLM content analysis failed for passage on page %d", page_number)
            continue

        if not analysis.annotations:
            continue

        bboxes = find_span_for_text(extraction.pages, passage_text[:80], page_hint=page_number)

        # Build reasoning from annotations
        reasoning_parts = [analysis.summary_nl] if analysis.summary_nl else []
        for ann in analysis.annotations:
            reasoning_parts.append(f"[{ann.woo_article}] {ann.label_nl}: {ann.analysis_nl}")

        # Add sentence classifications if present
        if analysis.sentence_classifications:
            reasoning_parts.append("\nFeit-mening classificatie:")
            for sc in analysis.sentence_classifications:
                reasoning_parts.append(
                    f"  - [{sc.classification}] {sc.sentence[:80]}... — {sc.explanation_nl}"
                )

        # Use the highest-likelihood annotation as primary
        primary = max(
            analysis.annotations,
            key=lambda a: {"high": 3, "medium": 2, "low": 1}.get(a.likelihood, 0),
        )

        result.detections.append(PipelineDetection(
            entity_text=passage_text[:500],  # Truncate very long passages
            entity_type="passage",
            tier="3",
            confidence={"high": 0.70, "medium": 0.55, "low": 0.40}.get(primary.likelihood, 0.50),
            woo_article=primary.woo_article,
            review_status="pending",
            bounding_boxes=bboxes,
            reasoning="\n".join(reasoning_parts),
            source="llm",
        ))

    return result
