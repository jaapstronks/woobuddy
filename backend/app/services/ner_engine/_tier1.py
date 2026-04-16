"""Tier 1 — hard identifiers detected by regex + validation.

Runs on the raw document text and emits high-confidence detections
(BSN, IBAN, phone, email, postcode, kenteken, URL, KvK, BTW-nummer,
anchored geboortedatum, creditcard). All rules here are self-contained
— no Deduce, no name lists, no CSV data.
"""

from __future__ import annotations

import datetime
import re

from ._types import NERDetection, _deduplicate

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
# with spaces for readability (NL68 RABO 0338 1615 89). We accept both,
# and tolerate up to 3 whitespace chars between groups so IBANs that
# wrap across a line (extractor inserts " " + "\n") or a page boundary
# ("\n\n") still match. Mod-97 validation below keeps precision high.
_IBAN_PATTERN = re.compile(
    r"\b(NL\d{2}\s{0,3}[A-Z]{4}(?:\s{0,3}\d{4}){2}\s{0,3}\d{2})\b",
    re.IGNORECASE,
)

# Phone: Dutch mobile and landline.
# Note on word boundaries: `\b` is a zero-width match between a word
# character (\w) and a non-word character. It does NOT fire between a
# space and a `+`, because both are non-word characters. So `\b\+31...`
# fails to match "op +31...". International patterns use explicit
# `(?<!\w)` / `(?!\w)` lookarounds instead.
# Separator shorthand used in phone patterns below. Dutch phone numbers
# appear with dashes, spaces, dots, and combinations thereof:
#   06-12345678  /  06 12 34 56 78  /  06.12.34.56.78  /  0512 - 893 472
# `_P` matches one or more separator characters (dash, dot, space in any
# mix), which handles "06 12", "06-12", "06.12", and "06 - 12" alike.
# Digit-count constraints in each pattern keep the match tight.
_P = r"[\s.\-]+"  # phone separator: one or more of space/dot/dash

_PHONE_PATTERNS = [
    re.compile(r"\b(0[1-9]\d{1,2}[\s.\-]?\d{6,7})\b"),  # landline: 020-1234567 / 020 1234567
    # Grouped landline layouts that briefings, letterheads, and municipal
    # sites tend to use. Each alternation enforces a specific digit layout
    # so the total always sums to exactly 10 digits — keeps the regex tight
    # enough to avoid matching random numeric runs.
    re.compile(  # 3+3+2+2: 071 516 50 00
        r"\b(0[1-9]\d" + _P + r"\d{3}" + _P + r"\d{2}" + _P + r"\d{2})\b"
    ),
    re.compile(  # 3+3+4: 071 516 5000
        r"\b(0[1-9]\d" + _P + r"\d{3}" + _P + r"\d{4})\b"
    ),
    re.compile(  # 4+2+2+2: 0412 12 34 56
        r"\b(0[1-9]\d{2}" + _P + r"\d{2}" + _P + r"\d{2}" + _P + r"\d{2})\b"
    ),
    re.compile(  # 4+3+3: 0412 123 456
        r"\b(0[1-9]\d{2}" + _P + r"\d{3}" + _P + r"\d{3})\b"
    ),
    re.compile(r"\b(06[\s.\-]?\d{8})\b"),  # mobile compact
    re.compile(  # mobile grouped: 06 1234 5678
        r"\b(06" + _P + r"\d{4}" + _P + r"\d{4})\b"
    ),
    re.compile(  # mobile spaced: 06 12 34 56 78
        r"\b(06" + _P + r"\d{2}" + _P + r"\d{2}" + _P + r"\d{2}" + _P + r"\d{2})\b"
    ),
    # International mobile: +31 6 12345678, +316-12345678, +31612345678
    re.compile(r"(?<!\w)(\+31[-\s]?6[-\s]?\d{8})(?!\w)"),
    # International mobile with (0): +31(0)6 12345678, +31(0)6 33 92 14 78
    re.compile(r"(?<!\w)(\+31\(0\)6[\s.\-]?(?:[\s.\-]?\d{2}){4})(?!\w)"),
    re.compile(r"(?<!\w)(\+31\(0\)6[\s.\-]?\d{8})(?!\w)"),
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

# License plate: Dutch sidecodes (1 through 14). Each pattern covers
# one sidecode verbatim. Sidecode 4 (XX-99-XX) is the most common shape
# on modern plates; older sidecodes still appear on vintage vehicles.
# See https://nl.wikipedia.org/wiki/Nederlands_kenteken for the full list.
_LICENSE_PLATE_PATTERNS = [
    re.compile(r"\b([A-Z]{2}-\d{2}-\d{2})\b"),  # 1:  XX-99-99
    re.compile(r"\b(\d{2}-\d{2}-[A-Z]{2})\b"),  # 2:  99-99-XX
    re.compile(r"\b(\d{2}-[A-Z]{2}-\d{2})\b"),  # 3:  99-XX-99
    re.compile(r"\b([A-Z]{2}-\d{2}-[A-Z]{2})\b"),  # 4:  XX-99-XX
    re.compile(r"\b(\d{2}-[A-Z]{2}-[A-Z]{2})\b"),  # 5:  99-XX-XX
    re.compile(r"\b([A-Z]{2}-[A-Z]{2}-\d{2})\b"),  # 6:  XX-XX-99
    re.compile(r"\b(\d{2}-[A-Z]{3}-\d)\b"),  # 7:  99-XXX-9
    re.compile(r"\b(\d-[A-Z]{3}-\d{2})\b"),  # 8:  9-XXX-99
    re.compile(r"\b([A-Z]{2}-\d{3}-[A-Z])\b"),  # 9:  XX-999-X
    re.compile(r"\b([A-Z]-\d{3}-[A-Z]{2})\b"),  # 10: X-999-XX
    re.compile(r"\b([A-Z]{3}-\d{2}-[A-Z])\b"),  # 11: XXX-99-X
    re.compile(r"\b([A-Z]-\d{2}-[A-Z]{3})\b"),  # 12: X-99-XXX
    re.compile(r"\b(\d{3}-[A-Z]-[A-Z]{2})\b"),  # 13: 999-X-XX
    re.compile(r"\b(\d-[A-Z]{2}-\d{3})\b"),  # 14: 9-XX-999
    re.compile(r"\b([A-Z]{2}-\d{3}-[A-Z]{2})\b"),  # 15: XX-999-XX (diplomatic / special)
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


def _detect_bsn(text: str) -> list[NERDetection]:
    """Detect BSN numbers (9 digits, 11-proef validated)."""
    return [
        NERDetection.tier1(
            text=m.group(1), entity_type="bsn", confidence=0.98,
            start_char=m.start(), end_char=m.end(),
            reasoning="BSN-nummer gedetecteerd (voldoet aan 11-proef).",
            woo_article="5.1.1e",
        )
        for m in _BSN_PATTERN.finditer(text)
        if _validate_bsn(m.group(1))
    ]


def _validate_iban_mod97(iban: str) -> bool:
    """ISO 13616 mod-97 checksum. Strips whitespace before checking."""
    compact = "".join(iban.split()).upper()
    rearranged = compact[4:] + compact[:4]
    try:
        numeric = "".join(
            str(ord(c) - 55) if "A" <= c <= "Z" else c for c in rearranged
        )
        return int(numeric) % 97 == 1
    except ValueError:
        return False


def _detect_iban(text: str) -> list[NERDetection]:
    """Detect IBAN numbers (regex + mod-97 checksum)."""
    return [
        NERDetection.tier1(
            text=m.group(1), entity_type="iban", confidence=0.97,
            start_char=m.start(), end_char=m.end(),
            reasoning="IBAN-nummer gedetecteerd.",
        )
        for m in _IBAN_PATTERN.finditer(text)
        if _validate_iban_mod97(m.group(1))
    ]


def _detect_telefoon(text: str) -> list[NERDetection]:
    """Detect Dutch phone numbers (mobile + landline, national + international)."""
    detections: list[NERDetection] = []
    for pattern in _PHONE_PATTERNS:
        for m in pattern.finditer(text):
            matched = m.group(1)
            digits_only = re.sub(r"[\s\-+.()/]", "", matched)
            if len(digits_only) < 10:
                continue
            detections.append(
                NERDetection.tier1(
                    text=matched, entity_type="telefoon", confidence=0.95,
                    start_char=m.start(), end_char=m.end(),
                    reasoning="Telefoonnummer gedetecteerd.",
                )
            )
    return detections


def _detect_email(text: str) -> list[NERDetection]:
    """Detect email addresses."""
    return [
        NERDetection.tier1(
            text=m.group(1), entity_type="email", confidence=0.97,
            start_char=m.start(), end_char=m.end(),
            reasoning="E-mailadres gedetecteerd.",
        )
        for m in _EMAIL_PATTERN.finditer(text)
    ]


def _detect_postcode(text: str) -> list[NERDetection]:
    """Detect Dutch postcodes (4 digits + 2 uppercase letters)."""
    return [
        NERDetection.tier1(
            text=m.group(1), entity_type="postcode", confidence=0.90,
            start_char=m.start(), end_char=m.end(),
            reasoning="Postcode gedetecteerd.",
        )
        for m in _POSTCODE_PATTERN.finditer(text)
    ]


def _detect_kenteken(text: str) -> list[NERDetection]:
    """Detect Dutch license plates (sidecodes 1–15)."""
    detections: list[NERDetection] = []
    for pattern in _LICENSE_PLATE_PATTERNS:
        for m in pattern.finditer(text):
            detections.append(
                NERDetection.tier1(
                    text=m.group(1), entity_type="kenteken", confidence=0.93,
                    start_char=m.start(), end_char=m.end(),
                    reasoning="Kenteken gedetecteerd.",
                )
            )
    return detections


def _detect_url(text: str) -> list[NERDetection]:
    """Detect http/https URLs."""
    detections: list[NERDetection] = []
    for m in _URL_PATTERN.finditer(text):
        url = m.group(1)
        end_offset = 0
        while url and url[-1] in _URL_TRAILING_PUNCT:
            url = url[:-1]
            end_offset += 1
        if not url:
            continue
        detections.append(
            NERDetection.tier1(
                text=url, entity_type="url", confidence=0.95,
                start_char=m.start(1), end_char=m.end(1) - end_offset,
                reasoning="URL gedetecteerd.",
            )
        )
    return detections


_KVK_REASONING = "KvK-nummer gedetecteerd — openbaar handelsregistergegeven, standaard niet lakken."


def _detect_kvk(text: str) -> list[NERDetection]:
    """Detect KvK numbers (8-digit, context-anchored)."""
    kvk_anchors = list(_KVK_ANCHOR_PATTERN.finditer(text))
    if not kvk_anchors:
        return []

    detections: list[NERDetection] = []
    kvk_found: set[int] = set()

    # Pass 1: tight forward window (20 chars after anchor)
    for anchor in kvk_anchors:
        window_end = min(len(text), anchor.end() + _KVK_WINDOW_CHARS + 8)
        window = text[anchor.end() : window_end]
        num = _KVK_NUMBER_PATTERN.search(window)
        if not num or num.start() > _KVK_WINDOW_CHARS:
            continue
        start = anchor.end() + num.start(1)
        end = anchor.end() + num.end(1)
        kvk_found.add(start)
        detections.append(
            NERDetection.tier1(
                text=num.group(1), entity_type="kvk", confidence=0.90,
                start_char=start, end_char=end, reasoning=_KVK_REASONING,
            )
        )

    # Pass 2: table-context (200 chars, tabular data heuristic)
    for num in _KVK_NUMBER_PATTERN.finditer(text):
        num_start = num.start(1)
        if num_start in kvk_found:
            continue
        for anchor in kvk_anchors:
            dist = num_start - anchor.end()
            if dist < 0 or dist > 200:
                continue
            between = text[anchor.end() : num_start]
            if not re.search(r"[A-Za-z]{2,}", between):
                continue
            if re.search(r"\.\s+[A-Z]", between):
                continue
            kvk_found.add(num_start)
            detections.append(
                NERDetection.tier1(
                    text=num.group(1), entity_type="kvk", confidence=0.85,
                    start_char=num_start, end_char=num.end(1),
                    reasoning=_KVK_REASONING,
                )
            )
            break

    return detections


def _detect_btw(text: str) -> list[NERDetection]:
    """Detect BTW-nummers (Dutch VAT, BSN-style 11-proef on the body)."""
    return [
        NERDetection.tier1(
            text=m.group(1), entity_type="btw", confidence=0.95,
            start_char=m.start(1), end_char=m.end(1),
            reasoning="BTW-nummer gedetecteerd (format + 11-proef).",
        )
        for m in _BTW_PATTERN.finditer(text)
        if _validate_btw(m.group(2))
    ]


def _detect_geboortedatum(text: str) -> list[NERDetection]:
    """Detect context-anchored birth dates."""
    detections: list[NERDetection] = []
    for anchor in _GEBOORTEDATUM_ANCHOR_PATTERN.finditer(text):
        window_start = anchor.end()
        window_end = min(len(text), window_start + _GEBOORTEDATUM_WINDOW_CHARS + 20)
        window = text[window_start:window_end]
        date_match = _DATE_PATTERN.search(window)
        if not date_match or date_match.start() > _GEBOORTEDATUM_WINDOW_CHARS:
            continue
        raw = date_match.group(0)
        parsed = _parse_birth_date(raw)
        if parsed is None or not _is_plausible_birth_date(parsed):
            continue
        start = window_start + date_match.start()
        end = window_start + date_match.end()
        detections.append(
            NERDetection.tier1(
                text=raw, entity_type="geboortedatum", confidence=0.95,
                start_char=start, end_char=end,
                reasoning="Geboortedatum gedetecteerd (contextanker + geldige datum).",
            )
        )
    return detections


def _detect_creditcard(text: str) -> list[NERDetection]:
    """Detect credit card numbers (Luhn-validated)."""
    return [
        NERDetection.tier1(
            text=m.group(1), entity_type="creditcard", confidence=0.95,
            start_char=m.start(), end_char=m.end(),
            reasoning="Creditcardnummer gedetecteerd (voldoet aan Luhn-check).",
        )
        for m in _CREDIT_CARD_PATTERN.finditer(text)
        if _validate_luhn(re.sub(r"[\s\-]", "", m.group(1)))
    ]


def detect_tier1(text: str) -> list[NERDetection]:
    """Detect Tier 1 hard identifiers using regex + validation."""
    detections: list[NERDetection] = []
    detections.extend(_detect_bsn(text))
    detections.extend(_detect_iban(text))
    detections.extend(_detect_telefoon(text))
    detections.extend(_detect_email(text))
    detections.extend(_detect_postcode(text))
    detections.extend(_detect_kenteken(text))
    detections.extend(_detect_url(text))
    detections.extend(_detect_kvk(text))
    detections.extend(_detect_btw(text))
    detections.extend(_detect_geboortedatum(text))
    detections.extend(_detect_creditcard(text))
    return _deduplicate(detections)
