"""Public-official person whitelisting.

Context-gated: a person only matches when their municipality name
appears somewhere in the document's full text. Common Dutch surnames
additionally require the detection's visible initials to prefix-match
the official's — otherwise a private citizen whose name happens to
collide with a raadslid in an unrelated document would be un-redacted
by accident.
"""

from __future__ import annotations

import re

from ._text import (
    _COMMON_SURNAMES,
    _HONORIFIC_TOKENS,
    _INITIAL_RE,
    _PAREN_RE,
    _normalize_phrase,
    _strip_bbox_markers,
)
from ._types import PersonWhitelistHit, WhitelistIndex


def find_active_gemeenten(full_text: str, index: WhitelistIndex) -> set[str]:
    """Return the set of gm_codes whose name aliases appear in the text.

    Called once per analyze request. The match is a word-boundary
    substring scan on the NFKD-lowered full text; bbox markers like
    parentheses are stripped so "(gemeente Aalsmeer)" still fires.
    Returns an empty set when no municipality is mentioned — the
    public-officials whitelist then stays inert.
    """
    if not index.alias_patterns:
        return set()
    haystack = _normalize_phrase(_strip_bbox_markers(full_text))
    active: set[str] = set()
    for pattern, gm_code in index.alias_patterns:
        if gm_code in active:
            continue
        if pattern.search(haystack):
            active.add(gm_code)
    return active


def _initials_near_span(full_text: str, start_char: int, end_char: int, window: int = 30) -> str:
    """Return any initial-letter prefix present in a window around the span.

    Looks up to ``window`` chars before ``start_char`` (and inside the
    span itself, in case the detection swallowed "H.H. Erdogan" as one
    Deduce span). Returns a compact letters-only string, e.g. "hh", or
    an empty string if no initials are near.
    """
    if start_char < 0 or end_char > len(full_text) or end_char <= start_char:
        return ""
    before_start = max(0, start_char - window)
    before_text = full_text[before_start:start_char]
    span_text = full_text[start_char:end_char]

    # Prefer the *rightmost* run of initials before the span — e.g.
    # "Dhr. H.H. Erdogan" should yield "hh", not the empty prefix that
    # a naive leftmost search of "Dhr." produces.
    initials_letters = ""
    for haystack in (span_text, before_text):
        for m in re.finditer(r"(?:[A-Z]\.){1,4}", haystack):
            initials_letters = "".join(re.findall(r"[A-Z]", m.group(0))).lower()
    return initials_letters


def _detection_surname(text: str) -> str:
    """Isolate the surname portion of a detection string.

    Strips honorifics and initials from the front; normalizes what's
    left. Keeps tussenvoegsels attached ("de heer Van den Oever" →
    "van den oever"). Returns ``""`` when nothing name-like remains.
    """
    cleaned = _PAREN_RE.sub(" ", text or "")
    cleaned = _strip_bbox_markers(cleaned)
    tokens = cleaned.split()
    surname_tokens: list[str] = []
    honorific_bare = {h.strip(".") for h in _HONORIFIC_TOKENS}
    for tok in tokens:
        norm = tok.lower().rstrip(".")
        if norm in honorific_bare:
            continue
        if _INITIAL_RE.match(tok):
            continue
        # Single-letter bare token ("R") — treat as initial fragment.
        if len(tok) == 1 and tok.isalpha():
            continue
        surname_tokens.append(tok)
    return _normalize_phrase(" ".join(surname_tokens))


def _surname_matches(detection_surname: str, official_surname: str) -> bool:
    """True when the detection's surname portion covers the official's.

    Accepts either an exact match or the official's surname appearing as
    a whole-word suffix of the detection (so "de heer van den oever" and
    "van den oever" both match the official "van den oever"). The
    reverse direction (detection shorter than official) is not accepted
    — "oever" alone should not match "van den oever".
    """
    if not detection_surname or not official_surname:
        return False
    if detection_surname == official_surname:
        return True
    det_tokens = detection_surname.split()
    off_tokens = official_surname.split()
    if len(off_tokens) > len(det_tokens):
        return False
    return det_tokens[-len(off_tokens) :] == off_tokens


def match_person_whitelist(
    detection_text: str,
    start_char: int,
    end_char: int,
    full_text: str,
    active_gemeenten: set[str],
    index: WhitelistIndex,
) -> PersonWhitelistHit | None:
    """Decide whether a Tier 2 persoon detection is a known public official.

    Returns a ``PersonWhitelistHit`` when the detection's surname maps
    to a raadslid / wethouder / burgemeester / Woo-contactpersoon of a
    municipality mentioned in ``full_text`` (the ``active_gemeenten``
    set). Common surnames additionally require the detection's visible
    initials to prefix-match the official's — see ``_COMMON_SURNAMES``.
    """
    if not active_gemeenten:
        return None

    surname = _detection_surname(detection_text)
    if not surname:
        return None

    visible_initials = _initials_near_span(full_text, start_char, end_char)
    is_common = surname in _COMMON_SURNAMES

    for gm_code in active_gemeenten:
        officials = index.officials_by_gm.get(gm_code, ())
        for official in officials:
            if not _surname_matches(surname, official.surname_normalized):
                continue

            # Initials gate — common surnames are only whitelisted when
            # the visible initials prefix-match the official's.
            used_initials = False
            if is_common:
                if not visible_initials or not official.initials:
                    continue
                official_prefix = official.initials[: len(visible_initials)]
                visible_prefix = visible_initials[: len(official.initials)]
                if not official.initials.startswith(
                    visible_prefix
                ) and not visible_initials.startswith(official_prefix):
                    continue
                used_initials = True
            elif visible_initials and official.initials:
                # For uncommon surnames we still reject a hard mismatch
                # on explicit initials: "M. Erdogan" should not be
                # whitelisted against "H.H. Erdogan" just because their
                # surnames agree.
                first_visible = visible_initials[:1]
                first_official = official.initials[:1]
                if first_visible and first_official and first_visible != first_official:
                    continue
                used_initials = True

            municipality_name = next(
                (m.official_name for m in index.municipalities if m.gm_code == gm_code),
                gm_code,
            )
            return PersonWhitelistHit(
                official=official,
                municipality_name=municipality_name,
                used_initials=used_initials,
            )

    return None
