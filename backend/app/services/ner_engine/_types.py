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

# Default Woo article for personal-data detections (Art. 5.1.2e —
# "bijzondere persoonsgegevens"). Used by both tiers unless overridden
# (e.g. BSN uses Art. 5.1.1e).
DEFAULT_WOO_ARTICLE = "5.1.2e"

# Institutions and generic-noun keywords that indicate a Deduce `persoon`
# hit is actually an organization, place, or common noun — not a person.
# Shared between the plausibility filter and the adres institutional filter.
ORGANIZATION_KEYWORDS: frozenset[str] = frozenset(
    {
        # Education
        "hogeschool",
        "universiteit",
        "school",
        "academie",
        "faculteit",
        "college",
        "lyceum",
        "gymnasium",
        "mbo",
        "hbo",
        # Research / cultural institutions
        "instituut",
        "museum",
        "kunsthal",
        "bibliotheek",
        "archief",
        "theater",
        "concertgebouw",
        "orkest",
        # Government bodies
        "gemeente",
        "provincie",
        "ministerie",
        "raad",
        "commissie",
        "directie",
        "afdeling",
        "departement",
        "bureau",
        "dienst",
        "kamer",
        "tweedekamer",
        "eerstekamer",
        "kabinet",
        "rechtbank",
        "hof",
        # Companies / legal forms
        "stichting",
        "vereniging",
        "fonds",
        "platform",
        "federatie",
        "unie",
        "coöperatie",
        "cooperatie",
        "maatschappij",
        "holding",
        "groep",
        # Health
        "ziekenhuis",
        "kliniek",
        "zorgcentrum",
        "ggd",
        "ggz",
        # Religious / misc
        "kerk",
        "moskee",
        "synagoge",
        "tempel",
        "parochie",
    }
)


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

    @classmethod
    def tier1(
        cls,
        text: str,
        entity_type: NEREntityType,
        confidence: float,
        start_char: int,
        end_char: int,
        reasoning: str,
        *,
        woo_article: str = DEFAULT_WOO_ARTICLE,
    ) -> NERDetection:
        """Create a Tier 1 (regex) detection with common defaults."""
        return cls(
            text=text,
            entity_type=entity_type,
            tier="1",
            confidence=confidence,
            woo_article=woo_article,
            source="regex",
            start_char=start_char,
            end_char=end_char,
            reasoning=reasoning,
        )

    @classmethod
    def tier2(
        cls,
        text: str,
        entity_type: NEREntityType,
        confidence: float,
        start_char: int,
        end_char: int,
        reasoning: str,
        *,
        source: NERSource = "deduce",
        woo_article: str = DEFAULT_WOO_ARTICLE,
    ) -> NERDetection:
        """Create a Tier 2 (contextual) detection with common defaults."""
        return cls(
            text=text,
            entity_type=entity_type,
            tier="2",
            confidence=confidence,
            woo_article=woo_article,
            source=source,
            start_char=start_char,
            end_char=end_char,
            reasoning=reasoning,
        )


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
