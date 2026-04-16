"""Straatnaam + huisnummer rule — catch Dutch street spans Deduce misses.

Deduce (trained on medical records) routinely fails to emit `adres` /
`straat` annotations on ordinary Dutch letter / invoice prose like
"Havenstraat 194" or "Prinses Beatrixlaan 12a". The span is visually
obvious on the page and directly identifying, but without a CBS-style
wordlist there was no second path to rescue it — `_huisnummer.py` only
catches the partially-anonymized `huisnummer N` / `bewoner van nummer N`
shapes and leaves full street+number spans to Deduce.

This module adds a regex rule for the common Dutch shape:

    [optional tussenvoegsel] [Capitalized word(s)] <suffix> <number>

The suffix list is the closed set of Dutch straatnaam endings
(`-straat`, `-laan`, `-plein`, `-weg`, `-gracht`, `-kade`, …). Extending
it is a one-line change if a new suffix surfaces in the field.

Emits as Tier 2 `adres` at confidence 0.85, or 0.92 when a postcode hit
sits within `_POSTCODE_PROXIMITY_CHARS` characters of the span — the
screenshot-in-the-invoice case where the reviewer is *guaranteed* to
want the street card at the top of the list. The postcode check runs
via a local import of the Tier 1 pattern so this module remains a pure
Tier 2 helper without changing `detect_tier2`'s signature.

The institutional-address filter (`_is_plausible_home_address` in
`_tier2.py`) is reused by the caller so `Postbus 123`, `bezoekadres:
Stadhuisplein 1`, etc. are dropped the same way as Deduce's own
`adres` hits. A street at a gemeentehuis is public and should not be
redacted.
"""

from __future__ import annotations

import re

from app.services.name_engine import DUTCH_TUSSENVOEGSELS, build_tussenvoegsel_regex

from ._tier1 import _POSTCODE_PATTERN
from ._types import NERDetection

# Common Dutch straatnaam endings. Kept deliberately broad; adding a
# new suffix is cheap. Longer suffixes are listed first so the
# alternation prefers "plantsoen" over "hof" when both could match at
# the same position.
_STREET_SUFFIXES: tuple[str, ...] = (
    "plantsoen",
    "boulevard",
    "straat",
    "gracht",
    "singel",
    "kanaal",
    "dreef",
    "allee",
    "poort",
    "steeg",
    "markt",
    "plein",
    "laan",
    "kade",
    "park",
    "baan",
    "dijk",
    "ring",
    "hout",
    "veld",
    "burg",
    "wijk",
    "oord",
    "brug",
    "pad",
    "weg",
    "wal",
    "erf",
    "lei",
    "hof",
)

_SUFFIX_GROUP = "|".join(_STREET_SUFFIXES)

# A capitalized name-word. Allows Dutch diacritics, apostrophes, and
# hyphens so "Oranjeplein", "'s-Gravenhage-straat", and "Pré-park" all
# parse. Must start with an uppercase letter.
_CAP_WORD = r"[A-ZÄËÏÖÜÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛ][A-Za-zëéèïüöäáíóúàìòùâêîôû'’\-]*"

# Whitespace class used throughout the pattern: spaces and tabs only,
# NOT newlines. Street names, their prefix words, and the house number
# always sit on one line — if we allowed `\s` here, "Jaap Stronks\n
# Havenstraat 194" would match as a single span starting at "Jaap"
# because the cap-word prefix would greedily absorb the preceding line.
_HSP = r"[^\S\n]+"

# Optional leading tussenvoegsel run. Generated from the canonical
# Dutch particle list in `name_engine` so additions propagate
# automatically. Uses same-line whitespace (`_HSP`) so the match
# doesn't bleed across line breaks.
_TUSSEN_PREFIX = build_tussenvoegsel_regex(DUTCH_TUSSENVOEGSELS, separator=_HSP)

# Full street + number pattern:
#
# - Optional leading tussenvoegsel run.
# - 0–3 capitalized prefix words on the same line ("Prinses",
#   "Koningin Wilhelmina").
# - A required final capitalized word that ends in one of the street
#   suffixes. The suffix alternation is non-capturing and the cap-word
#   regex is non-greedy enough to let the suffix anchor the tail.
# - Same-line whitespace + a 1–4 digit house number with optional
#   toevoeging (`194`, `12a`, `3-5`, `1 bis`).
#
# The final word match requires at least one character before the
# suffix ("Park" alone does not match — there is no valid prefix that
# would let `[A-Z][\w]*park` anchor on just "Park" while still passing
# word-boundary checks).
_STRAATNAAM_PATTERN = re.compile(
    r"\b"
    rf"(?:{_TUSSEN_PREFIX})?"
    rf"(?:{_CAP_WORD}{_HSP}){{0,3}}"
    rf"{_CAP_WORD}(?:{_SUFFIX_GROUP})"
    rf"{_HSP}"
    # House number + optional toevoeging. The toevoeging MUST touch
    # the digits directly (no space) — otherwise " 194 is het" would
    # match "194 is" as `[digits][space][letters]`. Common toevoegsels
    # like "12a", "12bis", and "3-5" still work.
    r"(\d{1,4}(?:[a-zA-Z]{1,3}|-\d{1,3})?)"
    r"\b",
    re.UNICODE,
)

# How close a postcode must sit to the street span for the confidence
# boost to fire. 80 chars comfortably covers a line break between
# "Havenstraat 194" and "3024 TM Rotterdam" on any reasonable layout,
# without bleeding into the next paragraph.
_POSTCODE_PROXIMITY_CHARS = 80


def _detect_adres_by_straatnaam(text: str) -> list[NERDetection]:
    """Emit Tier 2 `adres` detections for Dutch street + number spans.

    Caller (`detect_tier2`) is responsible for applying the institutional
    filter (`_is_plausible_home_address`) and deduping against
    overlapping Deduce `adres` annotations.
    """
    detections: list[NERDetection] = []

    # Collect postcode positions once so the proximity check is O(N·P)
    # rather than rescanning the full text per street hit. Both lists
    # are small (a handful of entries per document at most).
    postcode_spans: list[tuple[int, int]] = [
        (m.start(), m.end()) for m in _POSTCODE_PATTERN.finditer(text)
    ]

    for m in _STRAATNAAM_PATTERN.finditer(text):
        span_start = m.start()
        span_end = m.end()
        span_text = m.group(0)

        # Proximity boost: if a postcode hit sits within the window on
        # either side, we're almost certainly looking at a full address
        # block (invoice letterhead, factuuradres, correspondentie).
        near_postcode = any(
            (pc_start >= span_end and pc_start - span_end <= _POSTCODE_PROXIMITY_CHARS)
            or (pc_end <= span_start and span_start - pc_end <= _POSTCODE_PROXIMITY_CHARS)
            for pc_start, pc_end in postcode_spans
        )
        confidence = 0.92 if near_postcode else 0.85

        reasoning = (
            "Straatnaam + huisnummer herkend, vlak bij een postcode — "
            "vrijwel zeker een volledig adres."
            if near_postcode
            else "Straatnaam + huisnummer herkend (Nederlandse straatsuffix)."
        )

        detections.append(
            NERDetection(
                text=span_text,
                entity_type="adres",
                tier="2",
                confidence=confidence,
                woo_article="5.1.2e",
                source="regex",
                start_char=span_start,
                end_char=span_end,
                reasoning=reasoning,
            )
        )

    return detections
