"""What a Tier 2 `persoon` span is *not* — brief #98.

Four rules propose person names (Deduce, the initials rule, the
title-prefix rule, the anchor rules) and all four are fooled by the
same handful of shapes: a list marker read as an initial plus a
surname, a street name that ends like one, an author in a reference
list, a place name absorbed into the span. Each rule could grow its own
guard, but then the guard has to be written four times and a fifth rule
starts without it. So the shapes live here, once, and the gate runs
over the merged detection list in `detect_tier2`.

Stance, unchanged from `_tier2_filters`: **prefer a false negative over
a false positive.** Every predicate below therefore asks for a second
signal before it drops anything — a list marker has to open its line
*and* be followed by lowercase prose *and* not be a name the wordlists
know; a street has to carry a house number; a place has to sit behind
something that is not a name at all.
"""

from __future__ import annotations

import csv
import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from app.logging_config import get_logger
from app.services.name_engine import NameLists, normalize_name_token

from ._tier2_filters import has_strong_street_shape
from ._types import NERDetection

logger = get_logger(__name__)

_GEMEENTEN_CSV = Path(__file__).resolve().parents[2] / "data" / "gemeenten.csv"


# ---------------------------------------------------------------------------
# The place index
# ---------------------------------------------------------------------------

#: Provinces. `gemeenten.csv` lists municipalities and the towns inside
#: them, never the province they sit in, and "Kop van Drenthe" is read
#: as a surname without them.
_PROVINCES: frozenset[str] = frozenset(
    {
        "drenthe",
        "flevoland",
        "friesland",
        "fryslan",
        "gelderland",
        "groningen",
        "limburg",
        "noord-brabant",
        "noord-holland",
        "overijssel",
        "utrecht",
        "zeeland",
        "zuid-holland",
    }
)


@lru_cache(maxsize=1)
def place_names() -> frozenset[str]:
    """Dutch place names: every town in `gemeenten.csv`, plus the provinces.

    The `Bevat plaatsen` column is the useful one — it names the ~2.500
    towns and villages inside the municipalities, which is the level at
    which a document writes "te Nieuw-Dordrecht". Normalised the same
    way as the name lists so "Fryslân" and "fryslan" are one entry.
    """
    names: set[str] = set(_PROVINCES)
    if not _GEMEENTEN_CSV.exists():
        logger.warning("ner.place_index_missing", path=str(_GEMEENTEN_CSV))
        return frozenset(names)
    with _GEMEENTEN_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";", quotechar='"'):
            short = (row.get("Afkorting") or "").strip()
            if len(short) > 2:
                names.add(normalize_name_token(short))
            for town in (row.get("Bevat plaatsen") or "").split(","):
                town = town.strip()
                if len(town) > 2:
                    names.add(normalize_name_token(town))
    logger.info("ner.place_index_loaded", places=len(names))
    return frozenset(names)


def _is_place(phrase: str) -> bool:
    return normalize_name_token(phrase.strip(".,;:()[]\"'")) in place_names()


#: Nouns that name a farm or estate rather than a family. "Hof" is not
#: here — it already sits in `ORGANIZATION_KEYWORDS`, which the
#: plausibility filter reads.
_PLACE_NOUNS: frozenset[str] = frozenset({"hoeve", "boerderij"})


# ---------------------------------------------------------------------------
# The shapes
# ---------------------------------------------------------------------------

#: One initial and one word, nothing else: "A. Gemengd", "I. VOORSCHRIFTEN".
#: A real signature carries more ("M.A.E. Holwarda", "W.J. van Elsacker"),
#: so the tight shape is itself part of the evidence.
_ENUMERATION_SPAN = re.compile(r"^([A-Z])\.[ \t]+(\S+)$")

#: The span opens its line, optionally behind a page number printed on
#: the same line ("3 I. VOORSCHRIFTEN").
_LINE_LEAD = re.compile(r"(?:^|\n)[ \t]*(?:\d{1,3}[ \t]+)?\Z")

#: What follows a list marker: running prose or a count, never the comma
#: that follows a signed name ("A. Jans, teamleider"). The optional
#: bracket covers "D. Elastomeren (rubber, siliconen)".
_CONTINUES_IN_PROSE = re.compile(r"^[ \t]\(?[a-zà-ÿ\d]")


def is_enumeration_marker(
    span_text: str,
    full_text: str,
    start_char: int,
    end_char: int,
    lists: NameLists,
) -> bool:
    """True when the span is a list marker, not an initial plus a surname.

    Three signals have to agree, because each one alone has a real name
    behind it somewhere: the span opens a line (a signature usually
    does too), it is either shouted or followed by lowercase prose ("A.
    Gemengd kunststof"; a signed name is followed by a comma and a job
    title), and the word is in neither the Meertens nor the CBS list
    ("P. Bakker heeft …" survives on the last one alone).
    """
    m = _ENUMERATION_SPAN.match(span_text.strip())
    if m is None:
        return False
    word = m.group(2)
    if _LINE_LEAD.search(full_text[:start_char]) is None:
        return False
    shouted = len(word) > 1 and word.isupper()
    if not shouted and _CONTINUES_IN_PROSE.match(full_text[end_char : end_char + 3]) is None:
        return False
    normalized = normalize_name_token(word)
    return normalized not in lists.first_names and normalized not in lists.last_names


#: How far past the span a house number may sit. Enough for " 194a".
_HOUSE_NUMBER_WINDOW = 8


def is_street_address(span_text: str, full_text: str, end_char: int) -> bool:
    """True when the span is a street name carrying a house number.

    "P. de Keyserstraat" reads as initial + tussenvoegsel + surname to
    every rule here, and the eight cards it produced were all the same
    address. The house number is what settles it: `Van der Laan` in
    prose has none, `P. de Keyserstraat 18` does — and the address rule
    picks the line up anyway.
    """
    tail = full_text[end_char : end_char + _HOUSE_NUMBER_WINDOW]
    return has_strong_street_shape(span_text + tail)


#: A year in brackets or behind a comma, closing the citation: "…, 2012."
#: or "… (2012)". Mirrors the `bibliography_author` triage rule. Written
#: tightly on purpose: a letter date ("Assen, 11 mei 2023") puts a day
#: and a month between the comma and the year, and a job title after a
#: signature has no year at all.
_CITATION_YEAR = re.compile(r",[ \t]*(?:19|20)\d\d[.,]|\((?:19|20)\d\d\)")

#: How far past the span the year may sit. A citation lists more than one
#: author — "J.W.H.P. Verhagen en M. Verbruggen, 2012." — so the year
#: closing the entry is not always the next thing after the first name.
_CITATION_WINDOW = 40


def is_bibliography_author(full_text: str, end_char: int) -> bool:
    """True when a publication year follows the span, citation-style.

    A reference list is a wall of real names — "Tol, A.J., J.W.H.P.
    Verhagen en M. Verbruggen, 2012. Leidraad …" — and every one of them
    is an author, not a data subject. The year is the only thing that
    separates the shape from a signature, and it has to close the
    citation: "A. Jans, teamleider" carries no year, and a letter date
    ("Assen, 11 mei 2023") does not follow the name.
    """
    window = full_text[end_char : end_char + _CITATION_WINDOW]
    return _CITATION_YEAR.search(window) is not None


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s]+", text.strip()) if t]


_INITIAL_TOKEN = re.compile(r"^(?:[A-Z]\.)+$")


def _opens_with_name_evidence(tokens: list[str], lists: NameLists) -> bool:
    """True when the span's first token is itself a reason to read a name.

    An initial ("P. Emmen"), a tussenvoegsel ("Van Dijk Assen") or a
    Meertens given name ("Piet Emmen") all say the capitals that follow
    are a name. A bare capitalised word that no first-name list knows
    ("Buitengebied", "Vaarverbinding", "Kop") says nothing.
    """
    if not tokens:
        return False
    first = tokens[0]
    if _INITIAL_TOKEN.match(first):
        return True
    normalized = normalize_name_token(first)
    return normalized in lists.tussenvoegsels or normalized in lists.first_names


def _trailing_place_length(tokens: list[str]) -> int:
    """How many trailing tokens form a place name, longest match first.

    "Ter Apel" and "Nieuw-Dordrecht" both have to come out whole, so the
    trailing one to three tokens are tried as a phrase before a single
    token is.
    """
    for size in range(min(3, len(tokens)), 0, -1):
        if _is_place(" ".join(tokens[-size:])):
            return size
    return 0


def ends_in_place_name(span_text: str, lists: NameLists) -> bool:
    """True when the span is <something that is not a name> + <place>.

    "Buitengebied Emmen", "Vaarverbinding Erica – Ter Apel": a
    bestemmingsplan and a waterway, read as surnames because the
    capitals line up. Two guards, because two hundred of the 2.474 town
    names in the index are also surnames:

    - the *first* token may not be name evidence, so "Piet Emmen", "P.
      Emmen" and "Van Dijk Assen" are left alone;
    - a tussenvoegsel directly before the place makes it a surname —
      "Shaniqua de Oosterwijk" is a person and Oosterwijk is a village
      in Vijfheerenlanden. That guard costs "Kop van Drenthe", which
      stays a card; a signed name is worth more than a region.
    """
    tokens = _tokens(span_text)
    if len(tokens) < 2 or _opens_with_name_evidence(tokens, lists):
        return False
    size = _trailing_place_length(tokens)
    if not 0 < size < len(tokens):
        return False
    return normalize_name_token(tokens[-(size + 1)]) not in lists.tussenvoegsels


def ends_in_place_noun(span_text: str, lists: NameLists) -> bool:
    """True when the span ends in a farm noun that is not a surname here.

    "Willem Alexander Hoeve" is an estate; "Van der Hoeve" is a family.
    The tussenvoegsel is the difference, and it is the whole rule.
    """
    tokens = _tokens(span_text)
    if len(tokens) < 2:
        return False
    if normalize_name_token(tokens[-1].strip(".,;:()")) not in _PLACE_NOUNS:
        return False
    return normalize_name_token(tokens[-2]) not in lists.tussenvoegsels


def trim_trailing_place(text: str, start_char: int, end_char: int) -> tuple[str, int, int]:
    """Strip a trailing "te <Plaats>" from a person span.

    "de heer Kersten te Nieuw-Dordrecht" is one person and one village,
    and the black bar has to stop after the person. `te` is a
    tussenvoegsel, which is why the forward walk swallowed the village
    in the first place.
    """
    spans = [m.span() for m in re.finditer(r"\S+", text)]
    tokens = [text[s:e] for s, e in spans]
    size = _trailing_place_length(tokens)
    if size == 0 or size + 1 >= len(tokens):
        return text, start_char, end_char
    te_index = len(tokens) - size - 1
    if normalize_name_token(tokens[te_index]) != "te":
        return text, start_char, end_char
    trimmed = text[: spans[te_index][0]].rstrip()
    if not trimmed:
        return text, start_char, end_char
    return trimmed, start_char, start_char + len(trimmed)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def _not_a_person_reason(
    det: NERDetection,
    full_text: str,
    lists: NameLists,
) -> str | None:
    """The shape that disqualifies this span, if any. For the debug log."""
    if is_enumeration_marker(det.text, full_text, det.start_char, det.end_char, lists):
        return "enumeration_marker"
    if is_street_address(det.text, full_text, det.end_char):
        return "street_address"
    if is_bibliography_author(full_text, det.end_char):
        return "bibliography_author"
    if ends_in_place_name(det.text, lists):
        return "place_name"
    if ends_in_place_noun(det.text, lists):
        return "place_noun"
    return None


def drop_non_person_spans(
    detections: list[NERDetection],
    full_text: str,
    lists: NameLists,
) -> list[NERDetection]:
    """Trim and filter `persoon` detections that are not people (#98).

    Runs over the merged list so a shape is caught whichever rule
    proposed it — six of the eight "P. de Keyserstraat" cards came from
    the initials rule, two from the title rule. Non-persoon detections
    pass through untouched.
    """
    kept: list[NERDetection] = []
    for det in detections:
        if det.entity_type != "persoon":
            kept.append(det)
            continue
        text, start, end = trim_trailing_place(det.text, det.start_char, det.end_char)
        if text != det.text:
            det = replace(det, text=text, start_char=start, end_char=end)
        reason = _not_a_person_reason(det, full_text, lists)
        if reason is None:
            kept.append(det)
            continue
        logger.debug(
            "ner.persoon_dropped_by_shape",
            reason=reason,
            source=det.source,
            start=det.start_char,
        )
    return kept
