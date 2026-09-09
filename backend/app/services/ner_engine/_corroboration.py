"""Single-token persoon gate — drop bare names nothing else vouches for.

Deduce tags any capitalised token that happens to be on its first-name
or surname list as `persoon`, and the Meertens / CBS lists confirm it:
"Roos", "Storm", "Bloem", "Kunst", "Groen", "Post", "Bos" are all real
Dutch names *and* ordinary words that start sentences, headings and
table cells. In Woo documents those far outnumber genuine one-word
name mentions, so a bare token got the reviewer a card for every
capitalised flower, weather event or colour.

A single-token `persoon` hit survives only when the document itself
corroborates it:

- the same token also appears inside a multi-token persoon hit
  ("Jan Jansen" earlier → later bare "Jansen" is the same person);
- it was produced by an anchored rule (`title_rule` after "de heer",
  `initials_rule` after "G.J.", `anchor_rule` after a closing, a
  field label or an aanhef), or its token appears in one;
- a greeting / mail-header cue sits right before it on the same line
  ("Beste Roos,", "Hoi Storm", "Van: Jansen", "T.a.v. Bos").

Everything else is dropped. The trade-off is deliberate: a document
that names a citizen *only* by a bare surname, never with initials,
salutation or first name, loses that card — and the reviewer, who
reads the text anyway, adds it by hand. See `_tier2_filters` for the
same false-negative-over-false-positive stance on addresses and dates.
"""

from __future__ import annotations

import re

from app.logging_config import get_logger
from app.services.name_engine import NameLists

from ._types import NERDetection

logger = get_logger(__name__)

# Sources whose single-token output is already anchored by context.
_ANCHORED_SOURCES = frozenset({"title_rule", "initials_rule", "anchor_rule"})

# Greeting / header cues that vouch for a bare name on the same line.
# Anchored at the end of the look-behind window so the cue must sit
# directly before the span (allowing a colon/comma and whitespace).
_GREETING_CUE_WINDOW_CHARS = 40
_GREETING_CUE_PATTERN = re.compile(
    r"(?:"
    r"beste|geachte(?:\s+(?:heer|mevrouw|heer/mevrouw))?|"
    r"dag|hallo|hoi|hi|hey|"
    r"t\.a\.v\.|"
    r"van|aan|cc|bcc"
    r")\s*[:,]?\s*$",
    re.IGNORECASE,
)

# An initial ("W.", "A.M.") is not a name token for corroboration.
_INITIAL_TOKEN = re.compile(r"^(?:[A-Z]\.)+$")

# Salutation words Deduce keeps inside its span ("De heer Yilmaz").
# They anchor the name (self-evident) but are not name tokens.
_SALUTATION_WORDS = frozenset({"heer", "mevrouw", "meneer", "mijnheer", "dhr", "mevr", "mw"})


def _name_tokens(text: str, lists: NameLists) -> list[str]:
    """Normalised, corroboration-worthy tokens of a persoon span.

    Drops tussenvoegsels and initials so "A.M. van der Berg" yields
    only ``["berg"]``.
    """
    tokens: list[str] = []
    for raw in text.split():
        tok = raw.strip(".,;:()[]\"'")
        if not tok or _INITIAL_TOKEN.match(raw):
            continue
        lower = tok.lower()
        if lower in lists.tussenvoegsels or lower in _SALUTATION_WORDS:
            continue
        tokens.append(lower)
    return tokens


def _has_anchor_token(text: str) -> bool:
    """True when the span carries an initial or a salutation word."""
    for raw in text.split():
        if _INITIAL_TOKEN.match(raw):
            return True
        if raw.strip(".,;:()").lower() in _SALUTATION_WORDS:
            return True
    return False


def _is_self_evident(text: str, lists: NameLists) -> bool:
    """True when the span's own shape already vouches for it.

    Two or more name tokens ("Jan Jansen", "Mees Bos"), or an initial
    or salutation next to a surname ("M. van der Berg", "De heer
    Yilmaz") — the same structural evidence the initials and title
    rules rely on.
    """
    tokens = _name_tokens(text, lists)
    if len(tokens) >= 2:
        return True
    return bool(tokens) and _has_anchor_token(text)


def _has_greeting_cue(text: str, start_char: int) -> bool:
    window_start = max(0, start_char - _GREETING_CUE_WINDOW_CHARS)
    preceding = text[window_start:start_char]
    # Stay on the same line — a "Beste" three lines up says nothing.
    newline = preceding.rfind("\n")
    if newline != -1:
        preceding = preceding[newline + 1 :]
    return _GREETING_CUE_PATTERN.search(preceding) is not None


def suppress_uncorroborated_single_tokens(
    detections: list[NERDetection],
    text: str,
    lists: NameLists,
) -> list[NERDetection]:
    """Drop single-token `persoon` detections that nothing corroborates.

    Non-persoon detections and multi-token persoon spans pass through
    untouched.
    """
    corroborated: set[str] = set()
    for d in detections:
        if d.entity_type != "persoon":
            continue
        if _is_self_evident(d.text, lists) or d.source in _ANCHORED_SOURCES:
            corroborated.update(_name_tokens(d.text, lists))

    kept: list[NERDetection] = []
    for d in detections:
        if d.entity_type != "persoon":
            kept.append(d)
            continue
        if _is_self_evident(d.text, lists) or d.source in _ANCHORED_SOURCES:
            kept.append(d)
            continue
        tokens = _name_tokens(d.text, lists)
        if tokens and tokens[0] in corroborated:
            kept.append(d)
            continue
        if _has_greeting_cue(text, d.start_char):
            kept.append(d)
            continue
        logger.debug(
            "ner.persoon_dropped_uncorroborated_single_token",
            start=d.start_char,
            text_length=len(d.text),
        )
    return kept
