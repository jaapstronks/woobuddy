"""Straatnaam + huisnummer rule — catch Dutch street spans Deduce misses.

Deduce (trained on medical records) routinely fails to emit `adres` /
`straat` annotations on ordinary Dutch letter / invoice prose like
"Havenstraat 194" or "Prinses Beatrixlaan 12a". The span is visually
obvious on the page and directly identifying, but without a CBS-style
wordlist there was no second path to rescue it — `_huisnummer.py` only
catches the partially-anonymized `huisnummer N` / `bewoner van nummer N`
shapes and leaves full street+number spans to Deduce.

This module adds a regex rule for the common Dutch shape:

    [optional capitalised tussenvoegsel] [Capitalised word(s)] <suffix> <number>

The suffix list is the union of the *strong* street endings
(`-straat`, `-laan`, `-plein`, `-weg`, `-gracht`, `-kade`, …) and the
*weak* ones (`-park`, `-markt`, `-baan`, `-ring`, `-oord`, …) from
`_tier2_filters`. The regex generates candidates for both; the caller
runs every candidate through `is_plausible_home_address`, which keeps
strong-suffix spans on their own merits and weak-suffix spans only when
a postcode or residence cue corroborates them. That split is what keeps
"Uitvoering 7", "Bestuursakkoord 17" and "Loopbaan 4" from a table of
contents out of the review list while "Loopbaan 14, 5654 AB Eindhoven"
still gets its card.

Confidence tiers:

- **0.92** — a postcode sits within `POSTCODE_PROXIMITY_CHARS` of the
  span: the invoice-letterhead case where the reviewer is *guaranteed*
  to want the card at the top of the list.
- **0.85** — strong suffix, no postcode ("Havenstraat 194 is het
  bezoekadres").
- **0.80** — weak suffix, kept only because a residence cue precedes it.

The institutional-address filter is applied by the caller so `Postbus
123`, `bezoekadres: Stadhuisplein 1`, etc. are dropped the same way as
Deduce's own `adres` hits. A street at a gemeentehuis is public and
should not be redacted.
"""

from __future__ import annotations

import re

from ._tier2_filters import (
    POSTCODE_PROXIMITY_CHARS,
    STRONG_STREET_SUFFIXES,
    WEAK_STREET_SUFFIXES,
    has_postcode_nearby,
    has_strong_street_shape,
)
from ._types import NERDetection

# Longer suffixes first so the alternation prefers "plantsoen" over
# "hof" when both could match at the same position.
_ALL_SUFFIXES: tuple[str, ...] = tuple(
    sorted(STRONG_STREET_SUFFIXES + WEAK_STREET_SUFFIXES, key=len, reverse=True)
)
_SUFFIX_GROUP = "|".join(_ALL_SUFFIXES)

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

# Capitalised prefix words that are never part of a street name but sit
# right in front of one in prose and letter layouts: prepositions at
# sentence start ("Aan de Kerkstraat 3 is …"), address labels
# ("Adres Kerkstraat 3"), and connectors. Excluding them keeps the
# emitted span (and therefore the redaction box) on the address itself.
_PREFIX_STOPWORDS = (
    "Aan",
    "Op",
    "In",
    "Te",
    "Bij",
    "Voor",
    "Naar",
    "Door",
    "Met",
    "Van",  # handled by the tussenvoegsel prefix below
    "Zie",
    "Het",
    "Een",
    "En",
    "Of",
    "Adres",
    "Woonadres",
    "Postadres",
    "Bezoekadres",
    "Correspondentieadres",
    "Afzender",
    "Locatie",
    "Wonende",
    "Gevestigd",
    "Gelegen",
)
_PREFIX_WORD = rf"(?!(?:{'|'.join(_PREFIX_STOPWORDS)})\b){_CAP_WORD}"

# Optional leading tussenvoegsel run. Street names carry the particle
# capitalised ("Van der Helstplein", "De Ruyterkade"), so — unlike the
# person-name rules — the first letter is *required* to be uppercase.
# A lowercase "aan de" / "in de" before a street is sentence prose,
# not part of the name, and must stay out of the span.
_TUSSEN_PREFIX = (
    r"(?:"
    rf"Van(?:{_HSP}(?:de|den|der|het|'t|’t))?|"
    r"De|Den|Der|Ten|Ter"
    r")"
    rf"{_HSP}"
)

# Full street + number pattern:
#
# - Optional leading capitalised tussenvoegsel run.
# - 0–3 capitalised prefix words on the same line ("Prinses",
#   "Koningin Wilhelmina"), excluding prepositions and labels.
# - A required final capitalised word that ends in one of the street
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
    rf"(?:{_PREFIX_WORD}{_HSP}){{0,3}}"
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

# Re-exported for callers/tests that reason about the proximity window.
_POSTCODE_PROXIMITY_CHARS = POSTCODE_PROXIMITY_CHARS


def _detect_adres_by_straatnaam(text: str) -> list[NERDetection]:
    """Emit Tier 2 `adres` candidates for Dutch street + number spans.

    Caller (`detect_tier2`) is responsible for applying
    `is_plausible_home_address` (institutional filter + strong/weak
    suffix gating) and deduping against overlapping Deduce `adres`
    annotations. Weak-suffix candidates returned here are therefore
    *not* detections yet — most of them are dropped by the caller.
    """
    detections: list[NERDetection] = []

    for m in _STRAATNAAM_PATTERN.finditer(text):
        span_start = m.start()
        span_end = m.end()
        span_text = m.group(0)

        near_postcode = has_postcode_nearby(text, span_start, span_end)
        strong = has_strong_street_shape(span_text)

        if near_postcode:
            confidence = 0.92
            reasoning = (
                "Straatnaam + huisnummer herkend, vlak bij een postcode — "
                "vrijwel zeker een volledig adres."
            )
        elif strong:
            confidence = 0.85
            reasoning = "Straatnaam + huisnummer herkend (Nederlandse straatsuffix)."
        else:
            confidence = 0.80
            reasoning = (
                "Straatnaam + huisnummer herkend op basis van de woonaanduiding ervoor "
                "(suffix alleen is niet eenduidig)."
            )

        detections.append(
            NERDetection.tier2(
                text=span_text,
                entity_type="adres",
                confidence=confidence,
                start_char=span_start,
                end_char=span_end,
                reasoning=reasoning,
                source="regex",
            )
        )

    return detections
