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
    re.compile(r"\b(0[1-9]\d{1,2}[-\s]?\d{6,7})\b"),  # landline: 020-1234567 / 020 1234567
    # Grouped landline layouts that briefings, letterheads, and municipal
    # sites tend to use. Each alternation enforces a specific digit layout
    # so the total always sums to exactly 10 digits — keeps the regex tight
    # enough to avoid matching random numeric runs.
    re.compile(r"\b(0[1-9]\d[-\s]\d{3}[-\s]\d{2}[-\s]\d{2})\b"),  # 071 516 50 00 (3+3+2+2)
    re.compile(r"\b(0[1-9]\d[-\s]\d{3}[-\s]\d{4})\b"),  # 071 516 5000 (3+3+4)
    re.compile(r"\b(0[1-9]\d{2}[-\s]\d{2}[-\s]\d{2}[-\s]\d{2})\b"),  # 0412 12 34 56 (4+2+2+2)
    re.compile(r"\b(0[1-9]\d{2}[-\s]\d{3}[-\s]\d{3})\b"),  # 0412 123 456 (4+3+3)
    re.compile(r"\b(06[-\s]?\d{8})\b"),  # mobile: 06-12345678 / 06 12345678
    re.compile(r"\b(06[-\s]\d{4}[-\s]\d{4})\b"),  # 06 1234 5678 (mobile grouped)
    re.compile(r"\b(06[-\s]\d{2}[-\s]\d{2}[-\s]\d{2}[-\s]\d{2})\b"),  # 06 12 34 56 78
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
