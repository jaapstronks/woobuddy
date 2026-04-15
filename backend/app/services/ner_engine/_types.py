"""NERDetection dataclass + the small deduplication helper shared by
the Tier 1 and Tier 2 passes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NERDetection:
    """A single NER detection result."""

    text: str
    entity_type: str  # persoon, bsn, iban, telefoon, email, adres, postcode, kenteken
    tier: str  # "1" or "2"
    confidence: float
    woo_article: str
    source: str  # "regex" or "deduce"
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
