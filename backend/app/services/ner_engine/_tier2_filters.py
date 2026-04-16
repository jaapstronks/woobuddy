"""Validity filters for Tier 2 Deduce spans.

Extracted from `_tier2.py` so the post-heuristic filters (dropping
institutional addresses, event dates, too-recent years) can be tested
without spinning up the full Deduce pipeline.
"""

from __future__ import annotations

import datetime
import re

from ._types import ORGANIZATION_KEYWORDS

# Tier 2 `datum` filter: Deduce flags every date it finds as a possible
# geboortedatum, but in Woo documents plain dates are overwhelmingly event
# dates (meeting dates, letter dates, request dates). If the year is within
# the last few years the subject would be a toddler and almost never appears
# by name — so we drop it. Genuine recent birth dates with an explicit
# anchor word are still caught by the Tier 1 path above.
_RECENT_DATE_MIN_BIRTH_AGE_YEARS = 2
_DATE_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

# Event-date context markers. If any of these appears within
# ``_EVENT_DATE_WINDOW_CHARS`` characters before the date span, we treat
# the date as an administrative date (letter date, meeting date, decision
# date) rather than a personal geboortedatum and drop it from Tier 2.
# Genuine birth dates are still caught by the Tier 1 geboortedatum
# anchor path regardless of what the surrounding context says.
_EVENT_DATE_WINDOW_CHARS = 30
_EVENT_DATE_CONTEXT_PATTERN = re.compile(
    r"(?:"
    r"datum\s*[:\-]|"
    r"d\.?\s*d\.?|"
    r"dd\s*[:\-]|"
    r"verzonden(?:\s+op)?|"
    r"verstuurd(?:\s+op)?|"
    r"vastgesteld(?:\s+op)?|"
    r"besloten(?:\s+op)?|"
    r"ondertekend(?:\s+op)?|"
    r"vergadering(?:\s+van)?|"
    r"vergaderd(?:\s+op)?|"
    r"brief\s+van|"
    r"per\s+brief\s+van|"
    r"ingediend(?:\s+op)?|"
    r"ontvangen(?:\s+op)?"
    r")\s*$",
    re.IGNORECASE,
)


def is_recent_event_date(annotation_text: str, full_text: str, start_char: int) -> bool:
    """True if a Deduce-flagged `datum` span looks like an event date, not a birth date.

    Two signals:
    - year is within the last ``_RECENT_DATE_MIN_BIRTH_AGE_YEARS`` years;
    - the preceding ~30 chars end in an administrative anchor like
      "datum:", "d.d.", "vastgesteld", "vergadering van", …
    Either signal is enough to drop the date from Tier 2.
    """
    year_match = _DATE_YEAR_PATTERN.search(annotation_text)
    if year_match is not None:
        year = int(year_match.group(0))
        cutoff_year = datetime.date.today().year - _RECENT_DATE_MIN_BIRTH_AGE_YEARS
        if year >= cutoff_year:
            return True
    ctx_start = max(0, start_char - _EVENT_DATE_WINDOW_CHARS)
    preceding = full_text[ctx_start:start_char]
    return _EVENT_DATE_CONTEXT_PATTERN.search(preceding) is not None


# Address-context keywords specific to the `adres` branch. Deduce
# frequently emits institutional addresses as `adres`/`locatie` spans
# (Postbus-adressen, gemeentehuizen, ministerie-bezoekadressen). These
# are public and should not be redacted. A span that *contains* one of
# these keywords as a whole token, OR is preceded within ~30 chars by
# an institutional label, is dropped from Tier 2 adres results.
_ADRES_ORG_KEYWORDS = ORGANIZATION_KEYWORDS | {
    "postbus",
    "stadhuis",
    "rijksoverheid",
    "gemeentehuis",
    "provinciehuis",
    "raadhuis",
}
_ADRES_CONTEXT_WINDOW_CHARS = 30
_ADRES_CONTEXT_PATTERN = re.compile(
    r"(?:"
    r"postadres|bezoekadres|correspondentieadres|"
    r"postbus|gemeentehuis|stadhuis|raadhuis|"
    r"provinciehuis|ministerie|rijksoverheid|"
    r"gemeente|provincie"
    r")\s*[:\-]?\s*$",
    re.IGNORECASE,
)


def is_plausible_home_address(span_text: str, full_text: str, start_char: int) -> bool:
    """Reject adres spans that are clearly institutional/public.

    Mirrors the `persoon` plausibility filter: if the span text contains
    an organization keyword as a whole token, or if the preceding
    ~30 characters end in an institutional label, we treat the hit as a
    public address and drop it. The alternative would be to flip the
    default to `rejected`, but the whitelist engine already does that
    when the address is known — here we want to prevent the card from
    ever being surfaced.
    """
    stripped = span_text.strip()

    # Bare city/place names without a street are too vague to be
    # actionable: "Utrecht", "Rotterdam", "Eindhoven". A genuine home
    # address always contains a space (street + number, or city +
    # postcode). Single-word spans are overwhelmingly just Deduce
    # tagging a city name as `locatie`.
    if " " not in stripped:
        return False

    tokens = {t.lower().strip(".,;:()") for t in span_text.split()}
    if _ADRES_ORG_KEYWORDS & tokens:
        return False
    ctx_start = max(0, start_char - _ADRES_CONTEXT_WINDOW_CHARS)
    preceding = full_text[ctx_start:start_char]
    return not _ADRES_CONTEXT_PATTERN.search(preceding)
