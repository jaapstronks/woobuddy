"""Private text-normalization helpers and regex constants shared by the
loader, person-matching, and address-matching submodules of the whitelist
engine.
"""

from __future__ import annotations

import re
import unicodedata

# A small, deliberately curated set of very common Dutch surnames. When a
# detection's surname is in this set, the whitelist refuses to fire unless
# the document *also* shows initials that prefix-match the official's
# initials. The goal is to keep "Jan Jansen (private citizen)" from being
# accidentally un-redacted in a Utrecht document just because some
# "Mw. A. Jansen" happens to be on the Utrecht raadsleden list.
#
# The list is intentionally conservative (~80 entries): adding too many
# shrinks the whitelist's useful footprint. Source: Dutch census-style
# frequency tables for surnames; order does not matter.
_COMMON_SURNAMES_RAW: tuple[str, ...] = (
    "de jong",
    "jansen",
    "de vries",
    "van den berg",
    "van dijk",
    "bakker",
    "janssen",
    "visser",
    "smit",
    "meijer",
    "de boer",
    "mulder",
    "de groot",
    "bos",
    "vos",
    "peters",
    "hendriks",
    "van leeuwen",
    "dekker",
    "brouwer",
    "de wit",
    "dijkstra",
    "smits",
    "de graaf",
    "van der meer",
    "van der linden",
    "kok",
    "jacobs",
    "de haan",
    "vermeulen",
    "van den broek",
    "de bruijn",
    "de bruin",
    "van der velde",
    "willems",
    "prins",
    "huisman",
    "kuijpers",
    "van vliet",
    "van de ven",
    "timmermans",
    "groen",
    "de jonge",
    "schouten",
    "koster",
    "bosch",
    "van den heuvel",
    "van der veen",
    "blom",
    "wolters",
    "maas",
    "verhoeven",
    "van der wal",
    "koning",
    "van der laan",
    "bosma",
    "peeters",
    "martens",
    "hoekstra",
    "kuiper",
    "goedhart",
    "molenaar",
    "post",
    "kramer",
    "van beek",
    "scholten",
    "van den bosch",
    "bosman",
    "gerritsen",
    "hermans",
    "veenstra",
    "koopman",
    "van der horst",
    "verbeek",
    "bouwman",
    "de lange",
    "van dam",
    "van der meulen",
    "dijkman",
    "van der schaaf",
)
# Tuple is authored as a flat literal so duplicates surface in code review
# as repeated string lines. The dedupe check below catches anything that
# slips through: it raises at import time rather than silently shrinking
# the frozenset.
assert len(_COMMON_SURNAMES_RAW) == len({s.lower() for s in _COMMON_SURNAMES_RAW}), (
    "_COMMON_SURNAMES_RAW contains duplicate entries"
)
_COMMON_SURNAMES: frozenset[str] = frozenset(s.lower() for s in _COMMON_SURNAMES_RAW)

# Honorifics + sub-titles stripped from CSV names when parsing. Lowercased
# for comparison. Multi-word honorifics ("de heer", "de heer mr.") are
# handled by iterative prefix stripping in ``_parse_medewerker_name``.
_HONORIFIC_TOKENS: frozenset[str] = frozenset(
    {
        "dhr",
        "dhr.",
        "mw",
        "mw.",
        "mevr",
        "mevr.",
        "mevrouw",
        "meneer",
        "heer",
        "mr",
        "mr.",
        "drs",
        "drs.",
        "dr",
        "dr.",
        "prof",
        "prof.",
        "ir",
        "ir.",
        "ing",
        "ing.",
    }
)

# A token is an "initial" if it is a single uppercase letter optionally
# followed by more single-letter groups, each with a trailing period.
# Matches "A.", "A.B.", "W.M.J.", but not "Jan" or "Wm".
_INITIAL_RE = re.compile(r"^[A-Z](?:\.[A-Z])*\.$")

# Extract *just* the initial letters from an initial-ish token. "A.B." → "ab".
_INITIAL_LETTERS_RE = re.compile(r"[A-Z]")

# Parenthetical first names ("dhr. (Arjan) Lindeboom") — dropped during
# parsing; we do not try to match full first names.
_PAREN_RE = re.compile(r"\([^)]*\)")


def _nfkd_lower(text: str) -> str:
    """Lowercase + strip diacritics. Same normalization the name engine
    uses so matches survive 'Gülnur' ↔ 'gulnur', 'Adrián' ↔ 'adrian'.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _normalize_phrase(text: str) -> str:
    """Collapse whitespace + strip diacritics + lowercase — for the
    matching target of a multi-word name, address or alias.
    """
    return " ".join(_nfkd_lower(text).split()).strip()


def _strip_bbox_markers(text: str) -> str:
    """Remove characters that have no business being inside a name or
    address match. Parentheses, brackets, and most sentence punctuation
    are peeled off; hyphens and apostrophes stay because they appear in
    real names and street names ("'s-Hertogenbosch", "Martens-Schuitema").
    """
    return re.sub(r"[,;:!?()\[\]\"]", " ", text)
