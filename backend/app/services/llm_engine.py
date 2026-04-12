"""LLM engine — orchestrates the full detection pipeline.

Currently runs Tier 1 (regex) and Tier 2 (Deduce NER) only. Tier 3 (LLM
content analysis) is temporarily disabled for fast mode; when re-enabled
it can be wired back into run_pipeline().
"""

import re
from dataclasses import dataclass, field

from app.logging_config import get_logger
from app.services.ner_engine import detect_all
from app.services.pdf_engine import ExtractionResult, find_span_for_text

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

    logger.info(
        "pipeline.started",
        page_count=extraction.page_count,
        llm_enabled=False,
    )

    # Check for environmental content (Art. 5.1 lid 6-7 Woo)
    result.has_environmental_content = _check_environmental_content(extraction.full_text)

    # --- Tier 1 + Tier 2: NER detection (no LLM calls) ---
    ner_detections = detect_all(extraction.full_text)
    logger.info("pipeline.ner_completed", detection_count=len(ner_detections))

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
            # Check public officials list
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
            else:
                # Skip LLM classification — default to pending for review
                result.detections.append(PipelineDetection(
                    entity_text=det.text,
                    entity_type="persoon",
                    tier="2",
                    confidence=det.confidence,
                    woo_article="5.1.2e",
                    review_status="pending",
                    bounding_boxes=bboxes,
                    reasoning=det.reasoning,
                    source="deduce",
                ))
        else:
            # Other Tier 2 entities (addresses, etc.)
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

    # --- Tier 3: skipped (LLM disabled for fast mode) ---
    logger.info(
        "pipeline.completed",
        detection_count=len(result.detections),
        tier3_skipped=True,
    )

    return result
