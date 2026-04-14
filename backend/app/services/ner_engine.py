"""NER engine — Tier 1 regex patterns + Tier 2 Deduce NER.

Tier 1: Hard identifiers detected by regex with validation.
Tier 2: Contextual personal data detected by Deduce (Dutch NER).

Deduce is initialized once at module level (not per-request) because
it takes ~2s to load lookup tables.
"""

import datetime
import re
from dataclasses import dataclass
from typing import Any

from app.logging_config import get_logger
from app.services.name_engine import (
    NameLists,
    load_name_lists,
    score_person_candidate,
)

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
_EMAIL_PATTERN = re.compile(r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b")

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

# KvK: 8 consecutive digits. Standalone 8-digit sequences are too ambiguous
# (could be invoice numbers, order references, anything), so we require a
# context anchor — `KvK`, `KVK`, or `Kamer van Koophandel` — within 20
# characters before the number.
_KVK_ANCHOR_PATTERN = re.compile(r"(?:kvk|kamer\s+van\s+koophandel)", re.IGNORECASE)
_KVK_NUMBER_PATTERN = re.compile(r"\b(\d{8})\b")
_KVK_WINDOW_CHARS = 20

# BTW-nummer (Dutch VAT): NL + 9 digits + B + 2 digits, with optional spaces.
# Historically the 9-digit body equalled the holder's BSN and therefore
# passed the 11-proef. Since Jan 2020 the Belastingdienst issues random
# 9-digit bodies that no longer validate — this detector will miss those.
# Kept as-is per todo #16; a later pass may add a format-only fallback.
_BTW_PATTERN = re.compile(
    r"\b(NL\s?(\d{9})\s?B\s?(\d{2}))\b",
    re.IGNORECASE,
)

# Geboortedatum: a date immediately preceded by one of a handful of
# Dutch/English anchor phrases. Plain dates (no anchor) stay Tier 2 because
# the false-positive rate is too high.
_GEBOORTEDATUM_ANCHOR_PATTERN = re.compile(
    r"(?:geboortedatum|geboren\s+op|geb\.|geb:|DOB|date\s+of\s+birth)",
    re.IGNORECASE,
)
_GEBOORTEDATUM_WINDOW_CHARS = 20

# Dutch month names (and a few English ones that show up in bilingual
# templates). Order matters in the alternation: longer forms first so
# "januari" is preferred over "jan" when both would match.
_DUTCH_MONTH_NAMES: dict[str, int] = {
    "januari": 1,
    "jan": 1,
    "februari": 2,
    "feb": 2,
    "maart": 3,
    "mrt": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "mei": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "augustus": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "oktober": 10,
    "okt": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_DUTCH_MONTH_NAMES.keys(), key=len, reverse=True))
_DATE_PATTERN = re.compile(
    r"(?P<numeric>\d{1,2}[-/]\d{1,2}[-/]\d{4})"
    r"|(?P<word>\d{1,2}\s+(?:" + _MONTH_ALT + r")\s+\d{4})",
    re.IGNORECASE,
)
_DATE_NUMERIC_PARTS = re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})")
_DATE_WORD_PARTS = re.compile(
    r"(\d{1,2})\s+(" + _MONTH_ALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _validate_btw(digits: str) -> bool:
    """Apply BSN-style 11-proef to the 9-digit body of a BTW-nummer.

    Todo #16 explicitly asks for BSN-rigor validation. See note on
    `_BTW_PATTERN` about the 2020 format change.
    """
    return _validate_bsn(digits)


def _parse_birth_date(raw: str) -> datetime.date | None:
    """Parse a date string (numeric or word form) into a `datetime.date`.

    Returns None for impossible dates (e.g. 31 feb, month > 12).
    """
    numeric = _DATE_NUMERIC_PARTS.fullmatch(raw)
    if numeric:
        day, month, year = int(numeric.group(1)), int(numeric.group(2)), int(numeric.group(3))
    else:
        word = _DATE_WORD_PARTS.fullmatch(raw)
        if not word:
            return None
        day = int(word.group(1))
        resolved_month = _DUTCH_MONTH_NAMES.get(word.group(2).lower())
        if resolved_month is None:
            return None
        month = resolved_month
        year = int(word.group(3))
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _is_plausible_birth_date(date: datetime.date) -> bool:
    """A geboortedatum must be in the past and within ~120 years."""
    today = datetime.date.today()
    if date > today:
        return False
    return (today.year - date.year) <= 120


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
            detections.append(
                NERDetection(
                    text=m.group(1),
                    entity_type="bsn",
                    tier="1",
                    confidence=0.98,
                    woo_article="5.1.1e",
                    source="regex",
                    start_char=m.start(),
                    end_char=m.end(),
                    reasoning="BSN-nummer gedetecteerd (voldoet aan 11-proef).",
                )
            )

    # IBAN
    for m in _IBAN_PATTERN.finditer(text):
        detections.append(
            NERDetection(
                text=m.group(1),
                entity_type="iban",
                tier="1",
                confidence=0.97,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning="IBAN-nummer gedetecteerd.",
            )
        )

    # Phone numbers
    for pattern in _PHONE_PATTERNS:
        for m in pattern.finditer(text):
            # Avoid matching things that are clearly not phone numbers
            matched = m.group(1)
            digits_only = re.sub(r"[\s\-+]", "", matched)
            if len(digits_only) < 10:
                continue
            detections.append(
                NERDetection(
                    text=matched,
                    entity_type="telefoon",
                    tier="1",
                    confidence=0.95,
                    woo_article="5.1.2e",
                    source="regex",
                    start_char=m.start(),
                    end_char=m.end(),
                    reasoning="Telefoonnummer gedetecteerd.",
                )
            )

    # Email
    for m in _EMAIL_PATTERN.finditer(text):
        detections.append(
            NERDetection(
                text=m.group(1),
                entity_type="email",
                tier="1",
                confidence=0.97,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning="E-mailadres gedetecteerd.",
            )
        )

    # Postcode
    for m in _POSTCODE_PATTERN.finditer(text):
        detections.append(
            NERDetection(
                text=m.group(1),
                entity_type="postcode",
                tier="1",
                confidence=0.90,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning="Postcode gedetecteerd.",
            )
        )

    # License plates
    for pattern in _LICENSE_PLATE_PATTERNS:
        for m in pattern.finditer(text):
            detections.append(
                NERDetection(
                    text=m.group(1),
                    entity_type="kenteken",
                    tier="1",
                    confidence=0.93,
                    woo_article="5.1.2e",
                    source="regex",
                    start_char=m.start(),
                    end_char=m.end(),
                    reasoning="Kenteken gedetecteerd.",
                )
            )

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
        detections.append(
            NERDetection(
                text=url,
                entity_type="url",
                tier="1",
                confidence=0.95,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(1),
                end_char=m.end(1) - end_offset,
                reasoning="URL gedetecteerd.",
            )
        )

    # KvK: 8-digit number anchored by `KvK` / `Kamer van Koophandel` within
    # 20 chars of the digits. Scanning from the anchor forward keeps the
    # algorithm bounded and avoids flagging random invoice numbers.
    for anchor in _KVK_ANCHOR_PATTERN.finditer(text):
        window_end = min(len(text), anchor.end() + _KVK_WINDOW_CHARS + 8)
        window = text[anchor.end() : window_end]
        num = _KVK_NUMBER_PATTERN.search(window)
        if not num:
            continue
        # Require the digits to start within the 20-char anchor window.
        if num.start() > _KVK_WINDOW_CHARS:
            continue
        start = anchor.end() + num.start(1)
        end = anchor.end() + num.end(1)
        detections.append(
            NERDetection(
                text=num.group(1),
                entity_type="kvk",
                tier="1",
                confidence=0.90,
                woo_article="5.1.2e",
                source="regex",
                start_char=start,
                end_char=end,
                reasoning="KvK-nummer gedetecteerd (contextanker binnen 20 tekens).",
            )
        )

    # BTW-nummer
    for m in _BTW_PATTERN.finditer(text):
        if not _validate_btw(m.group(2)):
            continue
        detections.append(
            NERDetection(
                text=m.group(1),
                entity_type="btw",
                tier="1",
                confidence=0.95,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(1),
                end_char=m.end(1),
                reasoning="BTW-nummer gedetecteerd (format + 11-proef).",
            )
        )

    # Geboortedatum (context-anchored only)
    for anchor in _GEBOORTEDATUM_ANCHOR_PATTERN.finditer(text):
        window_start = anchor.end()
        window_end = min(len(text), window_start + _GEBOORTEDATUM_WINDOW_CHARS + 20)
        window = text[window_start:window_end]
        date_match = _DATE_PATTERN.search(window)
        if not date_match:
            continue
        if date_match.start() > _GEBOORTEDATUM_WINDOW_CHARS:
            continue
        raw = date_match.group(0)
        parsed = _parse_birth_date(raw)
        if parsed is None or not _is_plausible_birth_date(parsed):
            continue
        start = window_start + date_match.start()
        end = window_start + date_match.end()
        detections.append(
            NERDetection(
                text=raw,
                entity_type="geboortedatum",
                tier="1",
                confidence=0.95,
                woo_article="5.1.2e",
                source="regex",
                start_char=start,
                end_char=end,
                reasoning="Geboortedatum gedetecteerd (contextanker + geldige datum).",
            )
        )

    # Credit card
    for m in _CREDIT_CARD_PATTERN.finditer(text):
        digits_only = re.sub(r"[\s\-]", "", m.group(1))
        if _validate_luhn(digits_only):
            detections.append(
                NERDetection(
                    text=m.group(1),
                    entity_type="creditcard",
                    tier="1",
                    confidence=0.95,
                    woo_article="5.1.2e",
                    source="regex",
                    start_char=m.start(),
                    end_char=m.end(),
                    reasoning="Creditcardnummer gedetecteerd (voldoet aan Luhn-check).",
                )
            )

    return _deduplicate(detections)


# ---------------------------------------------------------------------------
# Tier 2: Deduce NER
# ---------------------------------------------------------------------------

# Lazy-loaded Deduce instance (takes ~2s to initialize)
_deduce_instance = None

# Lazy-loaded name lists (Meertens voornamen + CBS achternamen + tussenvoegsels).
# Populated once at startup via `init_name_lists()`, or lazily on first use.
_name_lists: NameLists | None = None


def _get_deduce() -> Any:
    """Get or initialize the Deduce instance.

    Return type is `Any` because the upstream `deduce` package ships
    without type stubs — typing it as a concrete class would just push
    the `import-untyped` warning around without buying anything.
    """
    global _deduce_instance
    if _deduce_instance is None:
        from deduce import Deduce

        _deduce_instance = Deduce()
        logger.info("ner.deduce_loaded")
    return _deduce_instance


def init_deduce() -> None:
    """Pre-initialize Deduce (call during app startup)."""
    _get_deduce()


def init_name_lists() -> NameLists:
    """Pre-initialize the Meertens + CBS name lists (call during app startup)."""
    global _name_lists
    if _name_lists is None:
        _name_lists = load_name_lists()
    return _name_lists


def _get_name_lists() -> NameLists:
    """Return the cached name lists, loading them on first use."""
    global _name_lists
    if _name_lists is None:
        _name_lists = load_name_lists()
    return _name_lists


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


# Institutions and generic-noun keywords that indicate a Deduce `persoon`
# hit is actually an organization, place, or common noun — not a person.
# Matched case-insensitively as whole words anywhere in the detection text.
# Source: real false positives observed on Dutch Woo documents (e.g.
# "Amsterdamse Hogeschool voor de Kunsten", "Instituut Beeld & Geluid",
# "Naturalis", "Rijksmuseum", "Kunsthal", "gemeente Amsterdam").
_ORGANIZATION_KEYWORDS = {
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
    # Government bodies ("college" already listed above)
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

# Dutch articles and demonstratives that signal a Deduce hit is a
# generic noun phrase rather than a name. Matched case-insensitively
# on the first token.
#
# NOTE: common tussenvoegsels like "van", "ter", "ten", "der" are
# deliberately NOT in this set — real Dutch surnames start with them
# ("Van den Berg", "Ter Horst"). The "de"/"het"/"een" case is handled
# with a look-ahead: we only reject when no later token is capitalised,
# which distinguishes "de Vries" (a name) from "de gemeente" (not).
_NON_NAME_STARTERS = {
    "de",
    "het",
    "een",
    "dit",
    "dat",
    "deze",
    "die",
    "wat",
    "welk",
    "welke",
    "zijn",
    "haar",
    "hun",
    "onze",
    "jouw",
    "uw",
}


def _is_plausible_person_name(text: str) -> bool:
    """Cheap heuristic filter for Deduce `persoon` false positives.

    Runs before the detection is emitted, so organization names,
    fragments, and generic phrases never enter the review list in the
    first place. The goal is to drop the obvious garbage — marginal
    cases should still be kept and fall through to the LLM verifier.
    Returns True to keep the detection, False to drop it.
    """
    stripped = text.strip()
    if not stripped:
        return False

    # Length guard — real Dutch names cap out well under 50 chars even
    # for "Van den Berg-Van der Velde" style compounds.
    if len(stripped) > 50:
        return False
    if len(stripped) < 2:
        return False

    # Must contain at least one uppercase letter — names are capitalised.
    # Drops lowercase fragments like "partnerschappen met het rijks m".
    if not any(c.isupper() for c in stripped):
        return False

    original_tokens = stripped.split()
    lower_tokens = [t.lower() for t in original_tokens]
    if not original_tokens:
        return False

    # Reject if the first token is a Dutch article / demonstrative
    # AND no later token is capitalised. This distinguishes
    # "de Vries" (surname — later 'Vries' is capitalised, kept)
    # from "de gemeente" (generic phrase — nothing capitalised after
    # 'de', rejected).
    if lower_tokens[0] in _NON_NAME_STARTERS:
        later_capital = any(t[:1].isupper() for t in original_tokens[1:])
        if not later_capital:
            return False

    # Reject if any token is an organization keyword. This kills
    # "Amsterdamse Hogeschool", "Instituut Beeld", "gemeente Amsterdam",
    # "Stichting Woo Buddy", etc. The keyword has to appear as a whole
    # token — "Schoolstraat" does not trigger on "school".
    if _ORGANIZATION_KEYWORDS & set(lower_tokens):
        return False

    # Reject if the text contains a sentence-ending period followed
    # by a lowercase word — that's a multi-sentence fragment, not a
    # name. Example: "Kunsten. technologie in de context".
    #
    # The lookbehind `(?<=[a-z])` requires the period to follow a
    # lowercase letter, so initials like "A.M. van der Berg" are not
    # mistaken for sentence boundaries (the period there follows an
    # uppercase letter).
    if re.search(r"(?<=[a-z])\.\s+[a-z]", stripped):
        return False

    # Reject single-letter trailing fragments: "... het Rijks m".
    # A real name can end with an initial, but only if the initial is
    # written with a trailing period ("Jan de V."). A lone letter
    # without a period is almost always a pdf.js split artefact.
    last = original_tokens[-1]
    return not (len(original_tokens) >= 2 and len(last) == 1 and last.isalpha())


def detect_tier2(text: str) -> list[NERDetection]:
    """Detect Tier 2 contextual personal data using Deduce NER."""
    deduce = _get_deduce()
    doc = deduce.deidentify(text)
    name_lists = _get_name_lists()
    detections: list[NERDetection] = []

    for annotation in doc.annotations:
        tag = annotation.tag.lower()
        entity_type = _DEDUCE_TAG_MAP.get(tag, tag)

        # Skip types already handled by Tier 1 regex
        if entity_type in ("bsn", "telefoon", "postcode", "url"):
            continue

        # Cheap heuristic pre-filter for `persoon` false positives.
        # Deduce was trained on medical records and over-tags
        # institution names, fragments, and common nouns as persons.
        # We drop the obvious garbage here before it ever enters the
        # review list.
        if entity_type == "persoon" and not _is_plausible_person_name(annotation.text):
            logger.debug(
                "ner.persoon_dropped_by_heuristic",
                text_length=len(annotation.text),
            )
            continue

        # Persons are the primary Tier 2 entity
        if entity_type == "persoon":
            # Name-list scoring: after the structural heuristic passes,
            # raise the bar by requiring at least one token to match
            # Meertens (first name) or CBS (surname). When the lists
            # are empty (e.g. tests with missing fixtures) we fall back
            # to the heuristic-only verdict to keep the pipeline working.
            confidence = 0.80
            woo_article = "5.1.2e"
            reasoning = (
                "Persoonsnaam gedetecteerd door NER. "
                "Classificatie nodig: burger, ambtenaar, of publiek functionaris."
            )
            if name_lists.first_names or name_lists.last_names:
                score = score_person_candidate(annotation.text, name_lists)
                if not score.is_plausible:
                    logger.debug(
                        "ner.persoon_dropped_by_name_lists",
                        text_length=len(annotation.text),
                    )
                    continue
                # Boost confidence for positive list hits. +0.10 for a
                # known first name, +0.05 extra if a known surname
                # also appears. Cap at 0.95 so manual review still
                # sees a sliver of uncertainty.
                if score.has_known_first_name:
                    confidence = min(confidence + 0.10, 0.95)
                if score.has_known_last_name:
                    confidence = min(confidence + 0.05, 0.95)
                # Attribution string — exact wording matters because
                # `Tier2Card.svelte` pattern-matches "Meertens Instituut"
                # to render the link back to the NVB.
                if score.has_known_first_name and score.has_known_last_name:
                    reasoning = (
                        "Persoonsnaam herkend: voornaam op lijst van het "
                        "Meertens Instituut (Nederlandse Voornamenbank), "
                        "achternaam op CBS-achternamenlijst."
                    )
                elif score.has_known_first_name:
                    reasoning = (
                        "Voornaam herkend in Nederlandse Voornamenbank (Meertens Instituut)."
                    )
                else:
                    reasoning = "Achternaam herkend op CBS-achternamenlijst."
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

        detections.append(
            NERDetection(
                text=annotation.text,
                entity_type=entity_type,
                tier="2",
                confidence=confidence,
                woo_article=woo_article,
                source="deduce",
                start_char=annotation.start_char,
                end_char=annotation.end_char,
                reasoning=reasoning,
            )
        )

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
