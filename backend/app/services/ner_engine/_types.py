"""NERDetection dataclass + the small deduplication helper shared by
the Tier 1 and Tier 2 passes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NEREntityType = Literal[
    "persoon",
    "bsn",
    "iban",
    "telefoon",
    "email",
    "adres",
    "postcode",
    "kenteken",
    "creditcard",
    "geboortedatum",
    "kvk",
    "btw",
    "datum",
    "organisatie",
    "referentie",
    "url",
]

NERTier = Literal["1", "2"]

NERSource = Literal["regex", "deduce", "rule", "initials_rule", "title_rule"]


@dataclass
class NERDetection:
    """A single NER detection result."""

    text: str
    entity_type: NEREntityType
    tier: NERTier
    confidence: float
    woo_article: str
    source: NERSource
    start_char: int  # character offset in the full text
    end_char: int
    reasoning: str = ""


def _deduplicate(detections: list[NERDetection]) -> list[NERDetection]:
    """Remove duplicate detections (same text at same position)."""
    seen: set[tuple[str, int, int]] = set()
    result: list[NERDetection] = []
    for d in detections:
        key = (d.text.lower(), d.start_char, d.end_char)
        if key not in seen:
            seen.add(key)
            result.append(d)
    return result


def _merge_without_overlap(
    detections: list[NERDetection],
    new_hits: list[NERDetection],
    entity_type: str,
    log_tag: str,
) -> None:
    """Append ``new_hits`` to ``detections``, skipping any that overlap
    existing detections of ``entity_type``.

    Newly added hits are tracked in the range set so two overlapping
    ``new_hits`` don't both slip through.

    Parameters
    ----------
    detections:
        The accumulation list (mutated in place).
    new_hits:
        Candidate detections to merge.
    entity_type:
        Only existing detections of this type are considered for the
        overlap check.
    log_tag:
        Structured-log event name emitted for each dropped hit (e.g.
        ``"ner.straatnaam_dropped_overlap"``).
    """
    from app.logging_config import get_logger

    logger = get_logger(__name__)
    ranges = [(d.start_char, d.end_char) for d in detections if d.entity_type == entity_type]
    for hit in new_hits:
        overlaps = any(hit.start_char < end and hit.end_char > start for start, end in ranges)
        if overlaps:
            logger.debug(log_tag, start=hit.start_char, end=hit.end_char)
            continue
        detections.append(hit)
        ranges.append((hit.start_char, hit.end_char))
