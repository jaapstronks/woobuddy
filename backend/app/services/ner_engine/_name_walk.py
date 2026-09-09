"""Shared forward token walk for anchor-based person-name rules.

Both `_title_prefix` (#48, salutation + capitals) and `_anchor_rules`
(#97, closing / field label / salutation / mail display name) do the
same thing once they have found their anchor: step forward over the
tokens that follow it and decide how far the name reaches. The walk
itself — initials, single and multi-token tussenvoegsels, capitalized
tokens, and where to stop — lives here so there is one definition of
"what a Dutch name looks like from the left".

The walk is deliberately dumb: it reports what it consumed and where it
stopped, and leaves every judgment (is this plausible, does it have to
fill the whole line, may it be initials only) to the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.name_engine import NameLists

# A "name token" — a sequence of Unicode letters (plus apostrophe and
# hyphen) of length ≥ 2. The uppercase check is done in Python via
# ``str.isupper()`` on the first character, which correctly handles
# Turkish ("Yılmaz", "Öztürk"), Polish ("Łukasz"), Czech ("Čermák") and
# other extended-Latin alphabets that a fixed ASCII-range class misses.
_NAME_TOKEN = re.compile(r"[^\W\d_][\w'\-]+", re.UNICODE)

# An initial run: "W.", "A.M.", "G. J." (the walker tokenizes on
# whitespace, so the spaced variant arrives as two separate tokens).
_NAME_INITIAL = re.compile(r"(?:[A-Z]\.)+")

# Trailing sentence punctuation peeled off a token before it is
# classified. Initials keep their period — stripping it would turn them
# into bare capitals that no longer match `_NAME_INITIAL`. The
# non-period marks go first, so "B.D.," is still an initial run once
# the comma is gone and only then decides whether its period stays.
_NAME_TRAILING_PUNCT = ",.;:!?)]}"
_NAME_TRAILING_PUNCT_EXCEPT_PERIOD = ",;:!?)]}"


def is_cap_name_token(tok: str) -> bool:
    """Return True if `tok` is a capitalized name-like token."""
    if _NAME_TOKEN.fullmatch(tok) is None:
        return False
    return tok[:1].isupper()


def is_initial_token(tok: str) -> bool:
    """Return True if `tok` is an initial run ("W.", "A.M.")."""
    return _NAME_INITIAL.fullmatch(tok) is not None


def strip_trailing_punct(text: str) -> str:
    """Peel sentence punctuation off the end of `text`, keeping the
    period of a closing initial run ("J. Jansen," → "J. Jansen",
    "M.F.," → "M.F.")."""
    clean = text.rstrip(_NAME_TRAILING_PUNCT_EXCEPT_PERIOD)
    last = clean.rsplit(None, 1)[-1] if clean else ""
    if is_initial_token(last):
        return clean
    return clean.rstrip(_NAME_TRAILING_PUNCT)


@dataclass(frozen=True)
class NameWalk:
    """What a forward walk consumed, and what shape it had."""

    start_char: int
    end_char: int
    #: Number of capitalized name tokens consumed (tussenvoegsels and
    #: initials do not count).
    capitalized: int
    #: True when the walk consumed at least one initial run.
    has_initials: bool

    @property
    def is_initials_only(self) -> bool:
        return self.capitalized == 0 and self.has_initials


def _tokenize(text: str, start: int, end: int) -> list[tuple[str, int, int]]:
    """Whitespace-split `text[start:end]`, keeping absolute char offsets."""
    tokens: list[tuple[str, int, int]] = []
    for m in re.finditer(r"\S+", text[start:end]):
        raw = m.group(0)
        clean = strip_trailing_punct(raw)
        if not clean:
            continue
        tok_start = start + m.start()
        tokens.append((clean, tok_start, tok_start + len(clean)))
    return tokens


def walk_name(
    text: str,
    scan_start: int,
    scan_end: int,
    name_lists: NameLists,
    *,
    max_capitalized: int | None = None,
) -> NameWalk | None:
    """Consume a name-shaped token run from `scan_start`.

    Walks forward over initials, tussenvoegsels (single and multi-token)
    and capitalized tokens, stopping at the first token that is none of
    those — a lowercase word, a digit, a symbol — or once
    `max_capitalized` capitalized tokens have been taken.

    Returns ``None`` when nothing name-shaped starts at `scan_start`.
    The caller decides whether an initials-only run counts as a name.
    """
    tussen_single = name_lists.tussenvoegsels
    tussen_sequences = name_lists.tussenvoegsel_sequences
    max_seq_len = max((len(s) for s in tussen_sequences), default=0)

    tokens = _tokenize(text, scan_start, scan_end)
    if not tokens:
        return None

    span_start: int | None = None
    span_end: int | None = None
    capitalized = 0
    has_initials = False
    i = 0

    while i < len(tokens):
        tok, tok_start, tok_end = tokens[i]

        # Multi-token tussenvoegsel sequence ("van den", "de la", …).
        matched_seq = False
        if max_seq_len >= 2 and len(tokens) - i >= 2:
            for seq_len in range(min(max_seq_len, len(tokens) - i), 1, -1):
                window = tuple(tokens[i + k][0].lower() for k in range(seq_len))
                if window in tussen_sequences:
                    if span_start is None:
                        span_start = tok_start
                    span_end = tokens[i + seq_len - 1][2]
                    i += seq_len
                    matched_seq = True
                    break
        if matched_seq:
            continue

        # Initial: "W.", "A.M."
        if is_initial_token(tok):
            has_initials = True
            if span_start is None:
                span_start = tok_start
            span_end = tok_end
            i += 1
            continue

        # Single-token tussenvoegsel ("de", "van", "el", "di", …).
        if tok.lower() in tussen_single:
            if span_start is None:
                span_start = tok_start
            span_end = tok_end
            i += 1
            continue

        # Capitalized name token ("Khatib", "Yılmaz", "Kowalski").
        if is_cap_name_token(tok):
            if max_capitalized is not None and capitalized >= max_capitalized:
                break
            capitalized += 1
            if span_start is None:
                span_start = tok_start
            span_end = tok_end
            i += 1
            continue

        # Anything else (lowercase non-tussenvoegsel, digits, …): stop.
        break

    if span_start is None or span_end is None:
        return None
    return NameWalk(
        start_char=span_start,
        end_char=span_end,
        capitalized=capitalized,
        has_initials=has_initials,
    )
