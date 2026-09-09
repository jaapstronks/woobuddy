"""Public-official person whitelisting.

Context-gated: a person only matches when their municipality name
appears in the document, near the detection or in the letterhead. On
top of that the match must be *identified* — a surname alone is never
enough. The detection has to carry a given name or initials that agree
with the CSV's initials for that official; when it does not, the match
degrades to a hint that keeps the detection `pending` instead of
silently rejecting it.

The asymmetry is deliberate. A missed public official costs a reviewer
one click; a wrongly whitelisted private citizen leaves their name in a
published Woo document (#92).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence

from ._text import (
    _COMMON_SURNAMES,
    _HONORIFIC_TOKENS,
    _INITIAL_RE,
    _PAREN_RE,
    _normalize_phrase,
    _strip_bbox_markers,
)
from ._types import PersonWhitelistHit, WhitelistIndex

# A gemeente mentioned this many characters away from the detection (or
# closer) counts as the document's subject for that detection. Beyond it
# the mention is background noise — a list of neighbouring municipalities,
# a citation, a footer — and cannot carry a whitelist decision on its own.
_GEMEENTE_PROXIMITY_CHARS = 300

# A gemeente named inside this prefix of the document is the sender
# (letterhead / "Aan het college van ..."), which makes it the subject of
# the whole document rather than of one passage.
_LETTERHEAD_CHARS = 600

# Tussenvoegsels belong to the surname, not to the given name. They are
# skipped when looking for the given name in front of a matched surname,
# so "Isabelle van Westerman" yields "isabelle" and not "van".
_TUSSENVOEGSELS: frozenset[str] = frozenset(
    {
        "van",
        "de",
        "den",
        "der",
        "het",
        "'t",
        "ten",
        "ter",
        "te",
        "op",
        "aan",
        "bij",
        "in",
        "tot",
        "uit",
        "voor",
        "vande",
        "vander",
        "von",
        "zu",
        "la",
        "le",
        "du",
        "des",
        "di",
        "da",
        "dos",
        "el",
        "al",
    }
)


def _normalize_keeping_offsets(text: str) -> str:
    """Lowercase + strip diacritics without moving any character index.

    ``_normalize_phrase`` collapses whitespace and can change the string
    length, which makes its offsets useless for proximity work. This
    variant maps every input character to exactly one output character,
    so a match offset in the result is also an offset into ``text``.
    Characters whose NFKD form expands (``ﬁ``, ``½``) keep only their
    first base character — a rounding we accept because no municipality
    alias contains one.
    """
    out: list[str] = []
    for ch in text:
        if ch.isspace():
            out.append(" ")
            continue
        decomposed = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in decomposed if not unicodedata.combining(c))
        out.append(base[0].lower() if base else " ")
    return "".join(out)


def find_gemeente_mentions(full_text: str, index: WhitelistIndex) -> dict[str, tuple[int, ...]]:
    """Return every gemeente named in the text, with its character offsets.

    Called once per analyze request. The match is a word-boundary scan
    on an offset-preserving normalization of the full text; bbox markers
    like parentheses are stripped (in place) so "(gemeente Aalsmeer)"
    still fires. The offsets let ``match_person_whitelist`` ask whether
    the gemeente is near the detection or merely somewhere in the file.
    Returns an empty mapping when no municipality is mentioned — the
    public-officials whitelist then stays inert.
    """
    if not index.alias_patterns:
        return {}
    haystack = _normalize_keeping_offsets(_strip_bbox_markers(full_text))
    mentions: dict[str, list[int]] = {}
    for pattern, gm_code in index.alias_patterns:
        for m in pattern.finditer(haystack):
            mentions.setdefault(gm_code, []).append(m.start())
    return {gm: tuple(sorted(set(offsets))) for gm, offsets in mentions.items()}


def _gemeente_is_near(offsets: Sequence[int], start_char: int, end_char: int) -> bool:
    """True when a mention of this gemeente vouches for this span.

    Either the gemeente is named within ``_GEMEENTE_PROXIMITY_CHARS`` of
    the detection, or its first mention sits in the letterhead, which
    makes it the sender of the whole document.
    """
    if not offsets:
        return False
    if offsets[0] < _LETTERHEAD_CHARS:
        return True
    window_start = start_char - _GEMEENTE_PROXIMITY_CHARS
    window_end = end_char + _GEMEENTE_PROXIMITY_CHARS
    return any(window_start <= off <= window_end for off in offsets)


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


def _detection_name_tokens(text: str, index: WhitelistIndex) -> list[str]:
    """Split a detection string into normalized name tokens.

    Honorifics and initials are dropped from the front; what remains is
    the given name(s), tussenvoegsels and surname, in document order.
    A leading place name is stripped as well (#92): Deduce regularly
    runs a name into the preceding city — "Assen Berkant Vecht" — and
    without this the surname extraction lands on the city. The strip
    only fires while at least two name tokens survive, so a real
    "M.H. Assen" keeps its surname.
    """
    cleaned = _PAREN_RE.sub(" ", text or "")
    cleaned = _strip_bbox_markers(cleaned)
    honorific_bare = {h.strip(".") for h in _HONORIFIC_TOKENS}
    tokens: list[str] = []
    for tok in cleaned.split():
        norm = tok.lower().rstrip(".")
        if norm in honorific_bare:
            continue
        if _INITIAL_RE.match(tok):
            continue
        # Single-letter bare token ("R") — treat as initial fragment.
        if len(tok) == 1 and tok.isalpha():
            continue
        normalized = _normalize_phrase(tok)
        if normalized:
            tokens.append(normalized)

    while len(tokens) > 2 and tokens[0] in index.woonplaatsen:
        tokens = tokens[1:]
    return tokens


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


def _given_name_initial(det_tokens: Sequence[str], official_surname: str) -> str:
    """First letter of the given name in front of the matched surname.

    Returns ``""`` when the detection is a bare surname (optionally with
    tussenvoegsels), which is the case #92 is about: nothing in the text
    says *which* Groot or Westerman this is.
    """
    off_len = len(official_surname.split())
    lead = list(det_tokens[: len(det_tokens) - off_len])
    while lead and lead[-1] in _TUSSENVOEGSELS:
        lead.pop()
    if not lead:
        return ""
    return lead[0][:1]


def _initials_compatible(visible: str, official: str) -> bool:
    """True when two initial strings agree on their common prefix."""
    if not visible or not official:
        return False
    return official.startswith(visible[: len(official)]) or visible.startswith(
        official[: len(visible)]
    )


def _identity_verdict(
    given_initial: str,
    visible_initials: str,
    official_initials: str,
    is_common_surname: bool,
) -> tuple[str, str]:
    """Weigh the identity evidence for one candidate official.

    Returns ``(verdict, reason)`` where verdict is one of:

    - ``"confirmed"`` — a given name or initials pin this detection to
      this official; safe to default the card to "niet lakken".
    - ``"hint"``      — the surname fits but nothing identifies the
      person; the reviewer gets the lead, the detection stays pending.
    - ``"reject"``    — the evidence actively contradicts this official;
      try the next one.

    For a confirmation the reason names *which* evidence confirmed —
    ``"given_initial"`` or ``"initials"`` — so the card can say what it
    actually compared instead of claiming initials either way (#98).
    """
    if given_initial:
        if not official_initials:
            # CSV row carried a parenthesised first name, which the
            # loader drops — we cannot compare, so we do not claim.
            return "hint", "official_without_initials"
        if official_initials[0] != given_initial:
            return "reject", ""
        return "confirmed", "given_initial"

    if visible_initials and official_initials:
        if _initials_compatible(visible_initials, official_initials):
            return "confirmed", "initials"
        return "reject", ""

    # Bare surname. A common surname carries no information at all, so
    # it does not even earn a hint; an uncommon one does.
    if is_common_surname:
        return "reject", ""
    return "hint", "no_given_name"


def match_person_whitelist(
    detection_text: str,
    start_char: int,
    end_char: int,
    full_text: str,
    gemeente_mentions: Mapping[str, Sequence[int]],
    index: WhitelistIndex,
) -> PersonWhitelistHit | None:
    """Decide whether a Tier 2 persoon detection is a known public official.

    Returns a ``PersonWhitelistHit`` when the detection's surname maps to
    a raadslid / wethouder / burgemeester / Woo-contactpersoon of a
    municipality named in ``full_text``. ``hit.confirmed`` says how much
    the hit is worth: ``True`` means a given name or initials identified
    the person *and* the gemeente is named nearby, which is enough to
    default the card to "niet lakken". ``False`` means the surname fits
    but the identification does not — the caller must keep such a
    detection pending and merely show the lead (#92).

    A confirmed hit wins over a hint; when several officials share a
    surname the first confirmation returns, otherwise the first hint does.
    """
    if not gemeente_mentions:
        return None

    det_tokens = _detection_name_tokens(detection_text, index)
    if not det_tokens:
        return None
    surname = " ".join(det_tokens)

    visible_initials = _initials_near_span(full_text, start_char, end_char)
    weak_hit: PersonWhitelistHit | None = None

    for gm_code, offsets in gemeente_mentions.items():
        officials = index.officials_by_gm.get(gm_code, ())
        if not officials:
            continue
        near = _gemeente_is_near(offsets, start_char, end_char)

        for official in officials:
            if not _surname_matches(surname, official.surname_normalized):
                continue

            given_initial = _given_name_initial(det_tokens, official.surname_normalized)
            verdict, reason = _identity_verdict(
                given_initial,
                visible_initials,
                official.initials,
                official.surname_normalized in _COMMON_SURNAMES,
            )
            if verdict == "reject":
                continue
            if verdict == "confirmed" and not near:
                # Identified, but the gemeente is only named far away —
                # that is a lead, not a licence to un-redact.
                verdict, reason = "hint", "gemeente_far"

            municipality_name = next(
                (m.official_name for m in index.municipalities if m.gm_code == gm_code),
                gm_code,
            )
            hit = PersonWhitelistHit(
                official=official,
                municipality_name=municipality_name,
                used_initials=verdict == "confirmed" and reason == "initials",
                confirmed=verdict == "confirmed",
                hint_reason="" if verdict == "confirmed" else reason,
            )
            if hit.confirmed:
                return hit
            if weak_hit is None:
                weak_hit = hit

    return weak_hit
