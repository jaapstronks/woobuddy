"""NER engine — Tier 1 regex patterns + Tier 2 Deduce NER.

Tier 1: Hard identifiers detected by regex with validation.
Tier 2: Contextual personal data detected by Deduce (Dutch NER).

Deduce is initialized once at module level (not per-request) because
it takes ~2s to load lookup tables.

The engine is split across sub-modules by concern:

- ``_types``            — ``NERDetection`` dataclass + dedup helpers
- ``_tier1``            — Tier 1 regex patterns + validators
- ``_deduce``           — lazy-init for Deduce + Meertens/CBS name lists
- ``_plausibility``     — person-name heuristic filter
- ``_title_prefix``     — salutation-anchored non-CBS name rule
- ``_initials``         — initials + surname structural rule
- ``_straatnaam``       — Dutch street-suffix + house-number rule
- ``_huisnummer``       — partial-anonymization "huisnummer N" rule
- ``_label_anchored_id``— labelled reference-number rule
- ``_tier2``            — Tier 2 orchestrator (Deduce + all sub-rules)

Public API: import ``NERDetection``, ``detect_all``, ``detect_tier1``,
``detect_tier2``, ``init_deduce``, ``init_name_lists`` from this package.
Tests import private helpers directly from their sub-modules.
"""

from __future__ import annotations

from app.logging_config import get_logger

from ._deduce import init_deduce, init_name_lists
from ._tier1 import detect_tier1
from ._tier2 import detect_tier2
from ._types import NERDetection, NEREntityType, NERSource, NERTier

logger = get_logger(__name__)


def detect_all(text: str) -> list[NERDetection]:
    """Run both Tier 1 and Tier 2 detection.

    Tier 1 regex identifiers (postcode, telefoon, IBAN, …) take precedence
    over Tier 2 Deduce hits at the same char range. Deduce frequently
    re-tags a postcode as an "adres" span, producing two detections for
    the same text — one auto-redacted (Tier 1 black) and one pending
    (Tier 2 amber). The reviewer then rejects the Tier 2 card but the
    Tier 1 overlay stays dark, giving the misleading impression the
    rejection did not take. Dropping the Tier 2 duplicate here is the
    quietest fix — the Tier 1 detection is already authoritative and
    comes with a stronger review_status anyway.
    """
    tier1 = detect_tier1(text)
    tier2 = detect_tier2(text)

    # Build a set of char ranges occupied by Tier 1 detections. Equality is
    # fine for the dedupe: Deduce reports its `locatie` span for a postcode
    # using the exact same char offsets as the Tier 1 regex.
    tier1_ranges: set[tuple[int, int]] = {(d.start_char, d.end_char) for d in tier1}
    tier1_lower_texts = {d.text.lower() for d in tier1}

    deduped_tier2: list[NERDetection] = []
    for d in tier2:
        if (d.start_char, d.end_char) in tier1_ranges:
            logger.debug(
                "ner.tier2_dropped_duplicate_of_tier1",
                entity_type=d.entity_type,
                start_char=d.start_char,
                end_char=d.end_char,
            )
            continue
        if d.text.lower() in tier1_lower_texts:
            # Same text at a different char offset — still the same piece
            # of PII, just matched twice. Boost confidence and keep.
            d.confidence = min(d.confidence + 0.10, 1.0)
        deduped_tier2.append(d)

    return tier1 + deduped_tier2


__all__ = [
    "NERDetection",
    "NEREntityType",
    "NERSource",
    "NERTier",
    "detect_all",
    "detect_tier1",
    "detect_tier2",
    "init_deduce",
    "init_name_lists",
]
