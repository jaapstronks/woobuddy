"""Validity filters for Tier 2 Deduce spans.

Extracted from `_tier2.py` so the post-heuristic filters (dropping
institutional addresses, event dates, uncorroborated street spans)
can be tested without spinning up the full Deduce pipeline.

Design rule for everything in this module: **prefer a false negative
over a false positive.** Reviewers read the whole document anyway; a
list full of "Uitvoering 7"-style cards costs more trust than a missed
edge case. Every filter below therefore asks "is there positive
evidence this is personal data?" rather than "can I prove it is not?".
"""

from __future__ import annotations

import datetime
import re

from ._tier1 import _POSTCODE_PATTERN, _is_plausible_postcode
from ._types import ORGANIZATION_KEYWORDS

# ---------------------------------------------------------------------------
# Tier 2 `datum`
# ---------------------------------------------------------------------------

# Deduce flags every date it finds as a possible geboortedatum, but in Woo
# documents plain dates are overwhelmingly event dates (meeting dates,
# letter dates, request dates). If the year is within the last few years
# the subject would be a toddler and almost never appears by name — so we
# drop it. Genuine recent birth dates with an explicit anchor word are
# still caught by the Tier 1 path.
_RECENT_DATE_MIN_BIRTH_AGE_YEARS = 2
_DATE_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

# Event-date context markers. If any of these appears within
# ``_EVENT_DATE_WINDOW_CHARS`` characters before the date span, we treat
# the date as an administrative date (letter date, meeting date, decision
# date) rather than a personal geboortedatum and drop it from Tier 2.
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


# A plain date is only worth a `datum` card when something nearby says
# it is a *birth* date. Tier 1 already handles the tight "geboortedatum:
# 3-5-1971" shape (20-char window); this wider window rescues table
# layouts ("Geboortedatum" column header a few cells earlier) and prose
# ("… is geboren te Utrecht op 3 mei 1971"). Without any cue the date is
# an event date and is dropped — the pre-#detection-review behaviour of
# flagging every pre-2024 date in a Woo document produced a card for
# nearly every paragraph.
_BIRTH_CUE_WINDOW_CHARS = 200
_BIRTH_CUE_PATTERN = re.compile(
    r"(?:geboortedatum|geboortedag|geboren|geb\.|geb:|\bdob\b|date\s+of\s+birth)",
    re.IGNORECASE,
)


def has_birth_cue(full_text: str, start_char: int) -> bool:
    """True when a birth-date cue word sits within ~200 chars before the span."""
    ctx_start = max(0, start_char - _BIRTH_CUE_WINDOW_CHARS)
    return _BIRTH_CUE_PATTERN.search(full_text[ctx_start:start_char]) is not None


# ---------------------------------------------------------------------------
# Tier 2 `adres`
# ---------------------------------------------------------------------------

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
# Two flavours of institutional context:
#
# - Labels that *only* introduce an organisation's address
#   ("Bezoekadres: Stadhuisplein 1, 3012 AR Rotterdam") may sit
#   anywhere earlier on the same line — the postcode+city span at the
#   end of that line is just as institutional as the street span.
# - Generic body words ("gemeente", "provincie", "ministerie") are
#   only evidence when they sit *directly* before the span
#   ("gemeente Kerkstraat 3"); "de gemeente schreef de bewoner van
#   Kerkstraat 3 aan" must not trip them.
#
# The address patterns anchor on ``\Z``, not ``$``. Their window ends
# exactly at the span, so ``$`` — which without ``re.MULTILINE`` also
# matches just before a trailing newline — would let a label on the
# *previous* line vouch for a span at the start of the next one. Same
# reason the whitespace before the anchor is horizontal only: ``\s*``
# swallows the line break.
_ADRES_CONTEXT_WINDOW_CHARS = 30
_ADRES_CONTEXT_PATTERN = re.compile(
    r"(?:"
    r"postadres|bezoekadres|correspondentieadres|"
    r"postbus|gemeentehuis|stadhuis|raadhuis|"
    r"provinciehuis|ministerie|rijksoverheid|"
    r"gemeente|provincie"
    r")[ \t]*[:\-]?[ \t]*\Z",
    re.IGNORECASE,
)
_ADRES_LABEL_LINE_WINDOW_CHARS = 60
_ADRES_LABEL_LINE_PATTERN = re.compile(
    r"\b(?:postadres|bezoekadres|correspondentieadres|postbus|"
    r"gemeentehuis|stadhuis|raadhuis|provinciehuis)\b[^\n]*\Z",
    re.IGNORECASE,
)


def has_institutional_address_label(full_text: str, start_char: int) -> bool:
    """True when an institutional address label precedes the span.

    Either a generic institution word directly before it, or an
    address label ("bezoekadres:", "Postbus 123,") earlier on the same
    line. Shared with the Tier 1 postcode whitelisting so the postcode
    of "Bezoekadres: Stadhuisplein 1, 3012 AR Rotterdam" is not
    auto-redacted either.
    """
    ctx_start = max(0, start_char - _ADRES_CONTEXT_WINDOW_CHARS)
    if _ADRES_CONTEXT_PATTERN.search(full_text[ctx_start:start_char]):
        return True
    line_start = max(0, start_char - _ADRES_LABEL_LINE_WINDOW_CHARS)
    return _ADRES_LABEL_LINE_PATTERN.search(full_text[line_start:start_char]) is not None


# Street suffixes that are (near-)unambiguous in Dutch: a capitalised
# word ending in one of these, followed by a number, is a street
# address in practically every document. "Kerkstraat 12" needs no
# further evidence.
STRONG_STREET_SUFFIXES: tuple[str, ...] = (
    "plantsoen",
    "boulevard",
    "straat",
    "gracht",
    "singel",
    "steeg",
    "dreef",
    "allee",
    "plein",
    "laan",
    "kade",
    "dijk",
    "weg",
)

# Suffixes that do occur in street names but far more often end an
# ordinary Dutch noun that happens to be followed by a number — the
# table-of-contents case: "Uitvoering 7", "Financiering 9", "Woningmarkt
# 14", "Tijdpad 18", "Loopbaan 4", "Bestuursakkoord 17", "Zonnepark 3".
# A span ending in one of these is only kept when a postcode sits
# nearby or an explicit residence cue precedes it.
WEAK_STREET_SUFFIXES: tuple[str, ...] = (
    "kanaal",
    "poort",
    "markt",
    "park",
    "baan",
    "ring",
    "hout",
    "veld",
    "burg",
    "wijk",
    "oord",
    "brug",
    "pad",
    "wal",
    "erf",
    "lei",
    "hof",
)

# Ordinary nouns that end in a *strong* suffix. Small on purpose: only
# words that show up capitalised + numbered in real documents.
_STRONG_SUFFIX_NOUN_STOPLIST: frozenset[str] = frozenset(
    {
        "onderweg",
        "terugweg",
        "uitweg",
        "omweg",
        "halverweg",
        "overweg",
        "tussenweg",
    }
)

_STRONG_STREET_WORD_RE = re.compile(
    r"\b([A-ZÄËÏÖÜÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛ][A-Za-zëéèïüöäáíóúàìòùâêîôû'’\-]*?"
    rf"(?:{'|'.join(STRONG_STREET_SUFFIXES)}))"
    r"[^\S\n]+\d{1,4}(?:[a-zA-Z]{1,3}|-\d{1,3})?\b",
)


def has_strong_street_shape(span_text: str) -> bool:
    """True when the span contains ``<Capitalised…strong-suffix> <number>``.

    "Havenstraat 194", "Prinses Beatrixlaan 12a", "Van der Helstplein
    3-5" → True. "Uitvoering 7", "Amsterdam 26", "Tekst 22",
    "Onderweg 3" → False.
    """
    for m in _STRONG_STREET_WORD_RE.finditer(span_text):
        if m.group(1).lower() not in _STRONG_SUFFIX_NOUN_STOPLIST:
            return True
    return False


# How far past an address span a postcode may sit and still count as
# corroboration. 80 chars comfortably covers a line break between
# "Loopbaan 14" and "5654 AB Eindhoven" on any reasonable layout
# without bleeding into the next paragraph.
POSTCODE_PROXIMITY_CHARS = 80


def has_postcode_nearby(full_text: str, start_char: int, end_char: int) -> bool:
    """True when a genuine Dutch postcode sits inside the span or ~80 chars after it.

    A Dutch address writes the postcode *after* the street, so only a
    postcode from the span onwards is evidence that the span is one.
    Looking backwards as well turned every capitalised word plus number
    within eighty characters of a delivery address into an address of
    its own: "5654 AB Eindhoven … Data 12" gave "Data 12" a 0.92 card on
    a production document.

    Only postcodes Tier 1 would accept count: "2019 EN 2020" is a year
    range, and Deduce's own postcode-shaped ``locatie`` span must not
    vouch for itself. A postcode on an institutional address line
    ("Bezoekadres: Raadhuisplein 2, 6711 DE Ede") belongs to the
    organisation, so it does not vouch for the "Zonnepark 3" in the
    Onderwerp line right under it either.
    """
    window_end = min(len(full_text), end_char + POSTCODE_PROXIMITY_CHARS)
    for m in _POSTCODE_PATTERN.finditer(full_text, start_char, window_end):
        if not _is_plausible_postcode(full_text, m):
            continue
        if has_institutional_address_label(full_text, m.start()):
            continue
        return True
    return False


# Residence cues that vouch for an otherwise ambiguous street span:
# "de bewoner van de Kerkbrink 3", "wonende Loopbaan 14", "gevestigd
# aan het Marktveld 2". Deliberately excludes generic location words
# ("locatie", "plaats") that planning documents use for everything.
# Anchored on ``\Z`` so a cue on the line above does not vouch for a
# span at the start of the next line — see the note above
# ``_ADRES_CONTEXT_WINDOW_CHARS``.
_ADDRESS_CUE_WINDOW_CHARS = 40
_ADDRESS_CUE_PATTERN = re.compile(
    r"(?:adres|wonende|woonachtig|gevestigd|gelegen|woont|woonde|wonen|"
    r"bewoners?|bewoonster|perceel|kadastraal)\b[^\n]{0,30}\Z",
    re.IGNORECASE,
)


def has_address_cue(full_text: str, start_char: int) -> bool:
    """True when a residence cue word precedes the span on the same line."""
    ctx_start = max(0, start_char - _ADDRESS_CUE_WINDOW_CHARS)
    return _ADDRESS_CUE_PATTERN.search(full_text[ctx_start:start_char]) is not None


_BARE_POSTCODE_SHAPE = re.compile(r"\d{4}\s?[A-Z]{2}")


def is_plausible_home_address(span_text: str, full_text: str, start_char: int) -> bool:
    """Decide whether an `adres` candidate deserves a review card.

    Applied to Deduce ``locatie``/``adres`` spans and to the regex
    straatnaam rule alike. The span survives only when **all** of:

    1. it is not institutional (org keyword inside, or an institutional
       label such as "bezoekadres:" / "Postbus" right before it);
    2. it contains a digit — a bare street or place name ("Den Haag",
       "Alphen aan den Rijn", "Prinses Beatrixlaan") is not a home
       address by itself and only produced noise;
    3. there is positive evidence it is a street address: a strong
       street suffix ("…straat 12"), a postcode inside or nearby, or a
       residence cue right before it.

    Deduce's own street pattern accepts any capitalised word ending in
    ``st``/``dam``/``park``/… followed by a number, which is how "Tekst
    22", "Amsterdam 26" and "Lijst 7" from a table of contents used to
    reach the reviewer. Rule 3 is what stops that.
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
    if has_institutional_address_label(full_text, start_char):
        return False

    if not any(ch.isdigit() for ch in stripped):
        return False

    # A bare postcode shape is never an adres card: a genuine one is
    # already a Tier 1 `postcode` hit, and an implausible one ("2019 EN"
    # from "BEGROTING 2019 EN 2020") must not be rescued by a real
    # postcode a line further down.
    if _BARE_POSTCODE_SHAPE.fullmatch(stripped):
        return False

    if has_strong_street_shape(stripped):
        return True
    end_char = start_char + len(span_text)
    if has_postcode_nearby(full_text, start_char, end_char):
        return True
    return has_address_cue(full_text, start_char)
