"""NER engine — Tier 1 regex patterns + Tier 2 Deduce NER.

Tier 1: Hard identifiers detected by regex with validation.
Tier 2: Contextual personal data detected by Deduce (Dutch NER).

Deduce is initialized once at module level (not per-request) because
it takes ~2s to load lookup tables.
"""

import re
from dataclasses import dataclass

from app.logging_config import get_logger

logger = get_logger(__name__)


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


# ---------------------------------------------------------------------------
# Tier 1: Regex patterns with validation
# ---------------------------------------------------------------------------

# BSN: 9 digits, must pass 11-proef
_BSN_PATTERN = re.compile(r"\b(\d{9})\b")


def _validate_bsn(digits: str) -> bool:
    """Check the Dutch 11-proef for BSN numbers."""
    if len(digits) != 9 or digits[0] == "0":
        return False
    weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
    return total % 11 == 0 and total != 0


# IBAN: NL + 2 check digits + 4 letter bank code + 10 digits.
# Banks print IBANs in two forms: compact (NL91ABNA0417164300) or grouped
# with spaces for readability (NL68 RABO 0338 1615 89). We accept both —
# a single optional space between each group.
_IBAN_PATTERN = re.compile(
    r"\b(NL\d{2}\s?[A-Z]{4}(?:\s?\d{4}){2}\s?\d{2})\b",
    re.IGNORECASE,
)

# Phone: Dutch mobile and landline.
# Note on word boundaries: `\b` is a zero-width match between a word
# character (\w) and a non-word character. It does NOT fire between a
# space and a `+`, because both are non-word characters. So `\b\+31...`
# fails to match "op +31...". International patterns use explicit
# `(?<!\w)` / `(?!\w)` lookarounds instead.
_PHONE_PATTERNS = [
    re.compile(r"\b(0[1-9]\d{1,2}[-\s]?\d{6,7})\b"),  # landline: 020-1234567
    re.compile(r"\b(06[-\s]?\d{8})\b"),  # mobile: 06-12345678
    # International mobile: +31 6 12345678, +316-12345678, +31612345678
    re.compile(r"(?<!\w)(\+31[-\s]?6[-\s]?\d{8})(?!\w)"),
    # International landline with any grouping of spaces/dashes:
    # +3120 1234567, +31-20-1234567, +31 40 792 00 35, +31 20 123 4567
    re.compile(r"(?<!\w)(\+31[-\s]?\d{1,3}(?:[-\s]?\d{2,4}){2,4})(?!\w)"),
]

# URL: match http(s) URLs including hyphens and slashes. Tier 1 so the full
# URL gets a proper bbox even when Deduce's URL detection truncates at an
# embedded space (pdf.js occasionally splits long URLs across text items —
# the frontend now smart-joins them, but this regex is a backstop).
# We match greedy-to-whitespace and strip trailing sentence punctuation
# in code, rather than trying to encode that in a single regex.
_URL_PATTERN = re.compile(r"(?<!\w)(https?://[^\s<>\"'`]+)")
_URL_TRAILING_PUNCT = ".,;:!?)]}>"

# Email
_EMAIL_PATTERN = re.compile(
    r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"
)

# Postcode: 4 digits + optional space + 2 uppercase letters
_POSTCODE_PATTERN = re.compile(r"\b(\d{4}\s?[A-Z]{2})\b")

# License plate: Dutch formats (XX-999-X, 9-XXX-99, XX-99-XX, etc.)
_LICENSE_PLATE_PATTERNS = [
    re.compile(r"\b([A-Z]{2}-\d{3}-[A-Z])\b"),
    re.compile(r"\b(\d-[A-Z]{3}-\d{2})\b"),
    re.compile(r"\b([A-Z]{2}-\d{2}-[A-Z]{2})\b"),
    re.compile(r"\b(\d{2}-[A-Z]{2}-\d{2})\b"),
    re.compile(r"\b(\d{2}-[A-Z]{3}-\d)\b"),
    re.compile(r"\b([A-Z]-\d{3}-[A-Z]{2})\b"),
    re.compile(r"\b([A-Z]{3}-\d{2}-[A-Z])\b"),
    re.compile(r"\b(\d-[A-Z]{2}-\d{3})\b"),
    re.compile(r"\b([A-Z]{2}-\d{3}-[A-Z])\b"),
]

# Credit card: 13-19 digits with optional spaces/dashes, Luhn check
_CREDIT_CARD_PATTERN = re.compile(r"\b(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,7})\b")


def _validate_luhn(number: str) -> bool:
    """Luhn algorithm for credit card validation."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def detect_tier1(text: str) -> list[NERDetection]:
    """Detect Tier 1 hard identifiers using regex + validation."""
    detections: list[NERDetection] = []

    # BSN
    for m in _BSN_PATTERN.finditer(text):
        if _validate_bsn(m.group(1)):
            detections.append(NERDetection(
                text=m.group(1),
                entity_type="bsn",
                tier="1",
                confidence=0.98,
                woo_article="5.1.1e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning="BSN-nummer gedetecteerd (voldoet aan 11-proef).",
            ))

    # IBAN
    for m in _IBAN_PATTERN.finditer(text):
        detections.append(NERDetection(
            text=m.group(1),
            entity_type="iban",
            tier="1",
            confidence=0.97,
            woo_article="5.1.2e",
            source="regex",
            start_char=m.start(),
            end_char=m.end(),
            reasoning="IBAN-nummer gedetecteerd.",
        ))

    # Phone numbers
    for pattern in _PHONE_PATTERNS:
        for m in pattern.finditer(text):
            # Avoid matching things that are clearly not phone numbers
            matched = m.group(1)
            digits_only = re.sub(r"[\s\-+]", "", matched)
            if len(digits_only) < 10:
                continue
            detections.append(NERDetection(
                text=matched,
                entity_type="telefoon",
                tier="1",
                confidence=0.95,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning="Telefoonnummer gedetecteerd.",
            ))

    # Email
    for m in _EMAIL_PATTERN.finditer(text):
        detections.append(NERDetection(
            text=m.group(1),
            entity_type="email",
            tier="1",
            confidence=0.97,
            woo_article="5.1.2e",
            source="regex",
            start_char=m.start(),
            end_char=m.end(),
            reasoning="E-mailadres gedetecteerd.",
        ))

    # Postcode
    for m in _POSTCODE_PATTERN.finditer(text):
        detections.append(NERDetection(
            text=m.group(1),
            entity_type="postcode",
            tier="1",
            confidence=0.90,
            woo_article="5.1.2e",
            source="regex",
            start_char=m.start(),
            end_char=m.end(),
            reasoning="Postcode gedetecteerd.",
        ))

    # License plates
    for pattern in _LICENSE_PLATE_PATTERNS:
        for m in pattern.finditer(text):
            detections.append(NERDetection(
                text=m.group(1),
                entity_type="kenteken",
                tier="1",
                confidence=0.93,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning="Kenteken gedetecteerd.",
            ))

    # URL (http/https)
    for m in _URL_PATTERN.finditer(text):
        url = m.group(1)
        # Strip trailing sentence punctuation so "see https://example.com."
        # doesn't include the period. Do this in a loop to handle multiple.
        end_offset = 0
        while url and url[-1] in _URL_TRAILING_PUNCT:
            url = url[:-1]
            end_offset += 1
        if not url:
            continue
        detections.append(NERDetection(
            text=url,
            entity_type="url",
            tier="1",
            confidence=0.95,
            woo_article="5.1.2e",
            source="regex",
            start_char=m.start(1),
            end_char=m.end(1) - end_offset,
            reasoning="URL gedetecteerd.",
        ))

    # Credit card
    for m in _CREDIT_CARD_PATTERN.finditer(text):
        digits_only = re.sub(r"[\s\-]", "", m.group(1))
        if _validate_luhn(digits_only):
            detections.append(NERDetection(
                text=m.group(1),
                entity_type="creditcard",
                tier="1",
                confidence=0.95,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning="Creditcardnummer gedetecteerd (voldoet aan Luhn-check).",
            ))

    return _deduplicate(detections)


# ---------------------------------------------------------------------------
# Tier 2: Deduce NER
# ---------------------------------------------------------------------------

# Lazy-loaded Deduce instance (takes ~2s to initialize)
_deduce_instance = None


def _get_deduce():
    """Get or initialize the Deduce instance."""
    global _deduce_instance
    if _deduce_instance is None:
        from deduce import Deduce

        _deduce_instance = Deduce()
        logger.info("ner.deduce_loaded")
    return _deduce_instance


def init_deduce() -> None:
    """Pre-initialize Deduce (call during app startup)."""
    _get_deduce()


# Mapping from Deduce annotation tags to our entity types
_DEDUCE_TAG_MAP: dict[str, str] = {
    "naam": "persoon",
    "voornaam": "persoon",
    "achternaam": "persoon",
    "initiaal": "persoon",
    "persoon": "persoon",
    "patient": "persoon",
    "locatie": "adres",
    "adres": "adres",
    "straat": "adres",
    "huisnummer": "adres",
    "postcode": "postcode",
    "woonplaats": "adres",
    "instelling": "organisatie",
    "ziekenhuis": "organisatie",
    "datum": "datum",
    "leeftijd": "leeftijd",
    "telefoonnummer": "telefoon",
    "url": "url",
    "bsn": "bsn",
}


def detect_tier2(text: str) -> list[NERDetection]:
    """Detect Tier 2 contextual personal data using Deduce NER."""
    deduce = _get_deduce()
    doc = deduce.deidentify(text)
    detections: list[NERDetection] = []

    for annotation in doc.annotations:
        tag = annotation.tag.lower()
        entity_type = _DEDUCE_TAG_MAP.get(tag, tag)

        # Skip types already handled by Tier 1 regex
        if entity_type in ("bsn", "telefoon", "postcode", "url"):
            continue

        # Persons are the primary Tier 2 entity
        if entity_type == "persoon":
            confidence = 0.80
            woo_article = "5.1.2e"
            reasoning = (
                "Persoonsnaam gedetecteerd door NER. "
                "Classificatie nodig: burger, ambtenaar, of publiek functionaris."
            )
        elif entity_type == "adres":
            confidence = 0.75
            woo_article = "5.1.2e"
            reasoning = "Adres gedetecteerd — mogelijk woonadres."
        elif entity_type == "datum":
            confidence = 0.60
            woo_article = "5.1.2e"
            reasoning = "Datum gedetecteerd — mogelijk geboortedatum."
        elif entity_type == "organisatie":
            confidence = 0.50
            woo_article = ""
            reasoning = "Organisatienaam gedetecteerd — beoordeel of herleidbaar tot persoon."
        else:
            confidence = 0.60
            woo_article = "5.1.2e"
            reasoning = f"Entiteit gedetecteerd (type: {entity_type})."

        detections.append(NERDetection(
            text=annotation.text,
            entity_type=entity_type,
            tier="2",
            confidence=confidence,
            woo_article=woo_article,
            source="deduce",
            start_char=annotation.start_char,
            end_char=annotation.end_char,
            reasoning=reasoning,
        ))

    return _deduplicate(detections)


def detect_all(text: str) -> list[NERDetection]:
    """Run both Tier 1 and Tier 2 detection, with confidence boosting."""
    tier1 = detect_tier1(text)
    tier2 = detect_tier2(text)

    # Confidence boosting: if both Tier 1 and Tier 2 find the same text, boost
    tier1_texts = {d.text.lower() for d in tier1}
    for d in tier2:
        if d.text.lower() in tier1_texts:
            d.confidence = min(d.confidence + 0.10, 1.0)

    return tier1 + tier2


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
