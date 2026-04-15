"""NER engine — Tier 1 regex patterns + Tier 2 Deduce NER.

Tier 1: Hard identifiers detected by regex with validation.
Tier 2: Contextual personal data detected by Deduce (Dutch NER).

Deduce is initialized once at module level (not per-request) because
it takes ~2s to load lookup tables.

The engine is split across a few files by concern:

- ``_types``        — ``NERDetection`` dataclass + ``_deduplicate`` helper
- ``_tier1``        — Tier 1 regex patterns + validators + ``detect_tier1``
- ``_deduce``       — lazy-init for Deduce + Meertens/CBS name lists
- ``_plausibility`` — ``_is_plausible_person_name`` + organization-noun filter
- ``_title_prefix`` — salutation-anchored non-CBS name rule (#48)
- ``_huisnummer``   — partial-anonymization huisnummer rule (#51)
- ``_tier2``        — ``detect_tier2`` pipeline + recent-date filter

Importers should continue using ``from app.services.ner_engine import ...``
— the public API is re-exported here.
"""

from __future__ import annotations

from app.logging_config import get_logger

from ._deduce import (
    _DEDUCE_TAG_MAP,
    _get_deduce,
    _get_name_lists,
    init_deduce,
    init_name_lists,
)
from ._huisnummer import _detect_adres_by_huisnummer
from ._plausibility import (
    _NON_NAME_STARTERS,
    _ORGANIZATION_KEYWORDS,
    _is_plausible_person_name,
)
from ._tier1 import (
    _is_plausible_birth_date,
    _parse_birth_date,
    _validate_bsn,
    _validate_btw,
    _validate_luhn,
    detect_tier1,
)
from ._tier2 import detect_tier2
from ._title_prefix import _detect_persoon_via_title_prefix
from ._types import NERDetection, _deduplicate

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
    "detect_all",
    "detect_tier1",
    "detect_tier2",
    "init_deduce",
    "init_name_lists",
    # Private names re-exported for tests (test_ner_engine.py pulls these
    # directly via ``from app.services.ner_engine import ...``).
    "_DEDUCE_TAG_MAP",
    "_NON_NAME_STARTERS",
    "_ORGANIZATION_KEYWORDS",
    "_deduplicate",
    "_detect_adres_by_huisnummer",
    "_detect_persoon_via_title_prefix",
    "_get_deduce",
    "_get_name_lists",
    "_is_plausible_birth_date",
    "_is_plausible_person_name",
    "_parse_birth_date",
    "_validate_bsn",
    "_validate_btw",
    "_validate_luhn",
]
