"""Role engine — rule-based public-official / civil-servant classifier.

This is the rule-based replacement for the dormant LLM person-role
verification pass. The idea: when a Tier 2 `persoon` detection is
preceded (or apposed) by a Dutch function title from one of two
hand-curated lists, we can classify the person's role without any model.

- Publiek functionaris (`functietitels_publiek.txt`) → the detection is
  defaulted to `review_status="rejected"` (don't redact). These are
  titles like "wethouder", "burgemeester", "minister" where the bearer
  is acting in an official capacity and the CLAUDE.md rule says not to
  redact.
- Ambtenaar (`functietitels_ambtenaar.txt`) → stays `pending` but with a
  pre-filled reason so the reviewer's click is a confirmation, not a
  classification from scratch.

Two things keep the title lists from over-reading a signature block:

- Bestuursorgaan phrases (`bestuursorganen.txt`) are masked out of the
  context before any title is matched. "Gedeputeerde Staten van
  Drenthe" is a college, not the title of the name printed next to it,
  while "gedeputeerde Y. Turenhout" still is.
- The mandate cue "namens dezen," marks the name printed next to it
  as the ambtenaar who signed on the body's behalf. The cue can sit on
  either side of that name: before it in a Drenthe-style closing, after
  it in a rijksbrief that prints the signatory first — see
  `find_mandate_cue_before` and `find_mandate_cue_after`.

The rule engine intentionally only looks at a small window
around each detection — it is not a parser, and cannot reason about
who "the wethouder" refers to in a subordinate clause. Reviewers still
have the final say via the Tier 2 card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.logging_config import get_logger

logger = get_logger(__name__)


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_PUBLIEK_FILE = _DATA_DIR / "functietitels_publiek.txt"
_AMBTENAAR_FILE = _DATA_DIR / "functietitels_ambtenaar.txt"
_BESTUURSORGANEN_FILE = _DATA_DIR / "bestuursorganen.txt"


# Match window around each detection, in characters. 40 chars is enough
# to catch "De heer wethouder Jan de Vries" or "Jan de Vries, wethouder
# van Utrecht", but short enough that unrelated titles further up the
# sentence don't bleed in.
DEFAULT_WINDOW_CHARS = 40

# Maximum number of tokens between the matched title and the detection
# span before the match is considered "too loose" and ignored. Keeps
# "Jan de Vries zei dat de wethouder gebeld had" (3 tokens between) from
# firing incorrectly: the wethouder there refers to a different person.
_MAX_TOKENS_BETWEEN = 2

# List-context window: when a plural title ("raadsleden",
# "fractievoorzitters", "wethouders") is followed by a comma-separated
# list of names, we need to look further back than the standard window
# to reach the title from the 2nd/3rd/4th name in the list. This window
# is only used when the intervening text parses cleanly as a list
# (names + optional honorific prefixes + commas + "en"), so unrelated
# titles further up the paragraph cannot bleed in.
_LIST_CONTEXT_WINDOW_CHARS = 240

# Padding around the scanned region when bestuursorgaan phrases are
# masked. A phrase that straddles the edge of the window must still be
# recognized as a whole, and the longest phrase in the file ("college
# van burgemeester en wethouders") is 38 characters.
_ORGAN_MASK_PAD_CHARS = 64

# Every non-whitespace character of a bestuursorgaan phrase becomes this
# one. Whitespace is left alone so the masked text keeps the same length
# *and* the same token boundaries: character offsets and the
# `tokens_between` distances computed around the span do not shift.
_MASK_CHAR = "#"
_NON_SPACE = re.compile(r"\S")

# Mandate cue: "Gedeputeerde Staten van Drenthe, namens dezen, <naam>".
# The name after this cue is the civil servant who signed on the body's
# behalf — never the body's own office holder.
_MANDATE_CUE_PATTERN = re.compile(r"\bnamens\s+dezen?\b", re.IGNORECASE)

# How far back from the span the cue may sit. The signature block puts
# the function title on its own line between cue and name ("namens
# dezen, teamleider Ruimtelijke ontwikkeling, mevrouw M.A.E. Holwarda"),
# so the window has to clear a title line plus an honorific.
_MANDATE_WINDOW_CHARS = 120

# ... but not an arbitrary amount of prose: the text between the cue and
# the name must stay within a signature block's worth of tokens.
_MANDATE_MAX_TOKENS_BETWEEN = 6

# The same cue, read forward. A rijksbrief prints the signatory first
# and the mandating office after it, so the text between name and cue is
# an office designation on its own line ("De Staatssecretaris van
# Financiën – Herstel en Toeslagen") rather than a title plus honorific.
# Such a designation is longer than the six tokens the backward scan
# allows, and the em dash in it counts as a token of its own.
_MANDATE_AFTER_MAX_TOKENS_BETWEEN = 10

# A blank line ends the signature block, so a cue on the other side of
# one does not reach the name.
_BLANK_LINE = re.compile(r"\n[^\S\n]*\n")

# Text between the list-introducing title and the span must consist of
# list-separator tokens only: honorific prefixes (dhr./mw./mr./drs./
# prof./dr./mevrouw/meneer/familie), initials (A./A.B./F.A.), surname
# particles, proper-noun tokens, comma/semicolon/slash separators, and
# the coordinator "en". Any other token — a verb, a connector like
# "zei", a whole sentence — breaks the list and the scan stops.
_LIST_INTERIOR_PATTERN = re.compile(
    r"^(?:"
    r"\s+|"  # plain whitespace between tokens
    r",\s*|;\s*|/\s*|en\s+|"  # separators
    r"[○•▪▸–—\-]\s*|"  # bullet / list markers from PDF rendering
    r"dhr\.?|mw\.?|mr\.?|drs\.?|prof\.?|dr\.?|"  # honorifics
    r"mevr\.?|mevrouw|meneer|familie|de\s+heer|"
    r"[A-Z]\.(?:\s*[A-Z]\.)*|"  # initials "A." / "A.B." / "F.A."
    r"(?:van|ter|ten|der|den|de|da|du|del|la|le|bin|al|el|in\s+’t|op\s+den)|"
    r"\([^)]{0,23}\)|"  # parenthesized content: party affiliations like (VVD), (D66)
    # Proper-noun token: case-sensitive initial uppercase required even
    # though the overall pattern is IGNORECASE. Without (?-i:...) the
    # initial [A-Z] matches lowercase too, letting any prose through.
    r"(?-i:[A-ZÄÖÜÁÀÉÈÍÎÏÓÔÚÛÇŞİĞ])[\wÄÖÜäöüáàéèíîïóôúûçşığ’’-]{1,30}"
    r")+\s*$",
    re.IGNORECASE | re.UNICODE,
)


ListName = Literal["publiek", "ambtenaar"]
Position = Literal["before", "after"]


@dataclass(frozen=True)
class FunctionTitleLists:
    """Compiled function-title lists ready for matching.

    `publiek` and `ambtenaar` are ordered lists of normalized title
    strings (lowercase, whitespace-collapsed). `patterns` holds the
    pre-compiled case-insensitive regexes for each title, keyed by
    `(list_name, title)` so we can iterate them quickly.

    `bestuursorganen` holds the body phrases from
    `bestuursorganen.txt` with their compiled patterns in
    `organ_patterns` (same order). They are not titles and never
    produce a match; they are masked out of the context first so the
    titles inside them cannot fire.
    """

    publiek: tuple[str, ...]
    ambtenaar: tuple[str, ...]
    patterns: dict[tuple[ListName, str], re.Pattern[str]]
    bestuursorganen: tuple[str, ...] = ()
    organ_patterns: tuple[re.Pattern[str], ...] = ()

    def iter_all(self) -> list[tuple[ListName, str, re.Pattern[str]]]:
        """Yield every (list, title, pattern) triple. Longest titles
        first so multi-word titles like "commissaris van de koning" get
        a shot before a hypothetical single-word prefix match.
        """
        items: list[tuple[ListName, str, re.Pattern[str]]] = []
        for t in self.publiek:
            items.append(("publiek", t, self.patterns[("publiek", t)]))
        for t in self.ambtenaar:
            items.append(("ambtenaar", t, self.patterns[("ambtenaar", t)]))
        items.sort(key=lambda triple: -len(triple[1].split()))
        return items


@dataclass(frozen=True)
class FunctionTitleMatch:
    """A single function-title hit near a detection span."""

    title: str  # the title as stored in the list (normalized)
    list_name: ListName  # "publiek" or "ambtenaar"
    position: Position  # "before" or "after" the detection span
    tokens_between: int  # tokens between title and span, 0 if adjacent


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _load_title_file(path: Path) -> tuple[str, ...]:
    """Load a one-title-per-line file, ignoring comments and blank lines.

    Whitespace inside a title is collapsed to single spaces. Missing
    files return an empty tuple and log a warning — the pipeline keeps
    working with just whichever list was available.
    """
    if not path.exists():
        logger.warning("role_engine.source_missing", path=str(path))
        return ()

    titles: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            normalized = " ".join(line.lower().split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                titles.append(normalized)
    return tuple(titles)


def _compile_title_pattern(title: str) -> re.Pattern[str]:
    """Compile a case-insensitive whole-word regex for `title`.

    Spaces in multi-word titles become `\\s+` so arbitrary runs of
    whitespace (including newlines from pdf.js output) still match.
    Hyphens and ampersands are kept literal via `re.escape`.
    """
    parts = [re.escape(p) for p in title.split()]
    body = r"\s+".join(parts)
    return re.compile(rf"\b{body}\b", re.IGNORECASE)


def _compile_organ_pattern(phrase: str) -> re.Pattern[str]:
    """Compile a bestuursorgaan phrase for masking.

    Same as `_compile_title_pattern` except the *leading* word boundary
    is dropped. A redaction box sitting right before the phrase leaves
    the extracted text with the two glued together — "Brian
    Vechtburgemeester en wethouders van Emmen" is what pdf.js hands us
    for a letter whose signature line was blacked out. With a leading
    `\\b` the phrase would not be recognized there and its "wethouders"
    would be read as the name's title, which is the exact bug this file
    exists to prevent. Masking one token too many only costs a
    publiek-functionaris rejection, and a name that reaches the reviewer
    is the safe side of that trade.
    """
    parts = [re.escape(p) for p in phrase.split()]
    body = r"\s+".join(parts)
    return re.compile(rf"{body}\b", re.IGNORECASE)


def load_function_title_lists() -> FunctionTitleLists:
    """Load both function-title files once and return compiled patterns.

    Call from `main.lifespan` and cache on `app.state.function_title_lists`.
    The I/O is trivial (few dozen titles total) so callers that forget
    can also call this lazily without any measurable cost.
    """
    publiek = _load_title_file(_PUBLIEK_FILE)
    ambtenaar = _load_title_file(_AMBTENAAR_FILE)
    bestuursorganen = _load_title_file(_BESTUURSORGANEN_FILE)

    patterns: dict[tuple[ListName, str], re.Pattern[str]] = {}
    for title in publiek:
        patterns[("publiek", title)] = _compile_title_pattern(title)
    for title in ambtenaar:
        patterns[("ambtenaar", title)] = _compile_title_pattern(title)

    # Longest phrase first, so "college van burgemeester en wethouders"
    # is masked as a whole before the shorter "burgemeester en
    # wethouders" gets to nibble at its tail.
    organ_patterns = tuple(
        _compile_organ_pattern(phrase) for phrase in sorted(bestuursorganen, key=lambda p: -len(p))
    )

    logger.info(
        "role_engine.lists_loaded",
        publiek=len(publiek),
        ambtenaar=len(ambtenaar),
        bestuursorganen=len(bestuursorganen),
    )
    return FunctionTitleLists(
        publiek=publiek,
        ambtenaar=ambtenaar,
        patterns=patterns,
        bestuursorganen=bestuursorganen,
        organ_patterns=organ_patterns,
    )


# Module-level cache so callers (tests, lazy paths) don't have to thread
# `app.state` around. Mirrors the pattern used in `name_engine`.
_cached_lists: FunctionTitleLists | None = None


def get_function_title_lists() -> FunctionTitleLists:
    """Return the cached function-title lists, loading on first use."""
    global _cached_lists
    if _cached_lists is None:
        _cached_lists = load_function_title_lists()
    return _cached_lists


def init_function_title_lists() -> FunctionTitleLists:
    """Pre-load the lists at app startup (called from FastAPI lifespan)."""
    return get_function_title_lists()


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def mask_organ_phrases(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    """Blank out bestuursorgaan phrases, keeping length and whitespace.

    "Hoogachtend, Gedeputeerde Staten van Drenthe, namens dezen," becomes
    "Hoogachtend, ############ ###### van Drenthe, namens dezen,". The
    replacement is the same length and touches no whitespace, so a caller
    can slice the masked text with the *original* character offsets and
    still count the same number of tokens between a title and a span.
    """
    if not patterns:
        return text
    masked = text
    for pattern in patterns:
        masked = pattern.sub(lambda m: _NON_SPACE.sub(_MASK_CHAR, m.group(0)), masked)
    return masked


def _count_tokens(text: str) -> int:
    """Count whitespace-separated tokens in `text`.

    Punctuation like a comma between a name and its apposed title
    ("Jan, wethouder") collapses to zero tokens, which is what we want:
    the title is immediately adjacent.
    """
    return len(text.split())


def find_mandate_cue_before(
    full_text: str,
    span_start: int,
    window: int = _MANDATE_WINDOW_CHARS,
) -> bool:
    """Is this span the name of someone signing *in mandaat*?

    Dutch government letters close with the body that took the decision,
    then "namens dezen," (or "namens deze,"), then the civil servant who
    actually signed:

        Gedeputeerde Staten van Drenthe,
        namens dezen,
        W.J. van Elsacker,
        teammanager a.i. Ruimte, Energie en Wonen

    That name is an ambtenaar, and whether an ambtenaar's name is
    redacted is a judgement call — so it must reach the reviewer as a
    suggestion rather than be swallowed by the signature block's
    auto-accept. The cue may sit a title line away from the name
    ("namens dezen, teamleider Ruimtelijke ontwikkeling, mevrouw
    M.A.E. Holwarda"), but not across a blank line and not across more
    than a signature block's worth of tokens.
    """
    if span_start <= 0 or span_start > len(full_text):
        return False

    before = full_text[max(0, span_start - window) : span_start]
    last: re.Match[str] | None = None
    for m in _MANDATE_CUE_PATTERN.finditer(before):
        last = m
    if last is None:
        return False

    interior = before[last.end() :]
    if _BLANK_LINE.search(interior):
        return False
    return _count_tokens(interior.replace(",", " ")) <= _MANDATE_MAX_TOKENS_BETWEEN


def _names_an_office(text: str, lists: FunctionTitleLists) -> bool:
    """Does `text` designate an office rather than carry prose?

    Empty counts: the cue can follow the name directly. Otherwise the
    text has to name a bestuursorgaan ("Gedeputeerde Staten van
    Drenthe") or hold a function title from either list ("De
    Staatssecretaris van Financiën"). Ten tokens of ordinary sentence
    ("... ingediend en vervolgens beoordeeld. Het besluit is") do
    neither, which is the point: without this the forward scan would
    reach a cue anywhere in the same paragraph.
    """
    if not text.strip():
        return True
    if mask_organ_phrases(text, lists.organ_patterns) != text:
        return True
    return any(pattern.search(text) is not None for _, _, pattern in lists.iter_all())


def find_mandate_cue_after(
    full_text: str,
    span_end: int,
    lists: FunctionTitleLists | None = None,
    window: int = _MANDATE_WINDOW_CHARS,
) -> bool:
    """Is this span the name of someone signing *in mandaat*, cue after?

    The mirror of `find_mandate_cue_before`. A rijksbrief closes the
    other way round: the signatory's name first, then the office that
    holds the authority, then the cue, then the signatory's own
    function.

        Hoogachtend,
        Shaniqua Terlouw-Van Rossem
        De Staatssecretaris van Financiën – Herstel en Toeslagen
        namens deze,
        Afdelingshoofd Openbaarmaking en Transparantie

    Read forward from the name, the first thing the title scan meets is
    "Staatssecretaris" — a publiek title, two tokens away — and the name
    would be rejected as a public official's. The cue says otherwise:
    everything between the name and it is the *mandating* office, and
    the signatory is the ambtenaar below. Same guards as the backward
    scan: not across a blank line, and not across more than an office
    designation's worth of tokens. On top of that the text between name
    and cue must actually *name* an office — a bestuursorgaan phrase or
    a function title. Reading forward there is no honorific or comma to
    bound the scan the way the backward one is bounded, so without that
    requirement a "namens deze" anywhere in the paragraph below a name
    would claim it.
    """
    if span_end < 0 or span_end >= len(full_text):
        return False

    after = full_text[span_end : span_end + window]
    first = _MANDATE_CUE_PATTERN.search(after)
    if first is None:
        return False

    interior = after[: first.start()]
    if _BLANK_LINE.search(interior):
        return False
    if _count_tokens(interior.replace(",", " ")) > _MANDATE_AFTER_MAX_TOKENS_BETWEEN:
        return False
    return _names_an_office(interior, lists if lists is not None else get_function_title_lists())


def _is_better(candidate: FunctionTitleMatch, current: FunctionTitleMatch | None) -> bool:
    """Tie-break between two candidate matches.

    Order:
    1. Before-context beats after-context (titles normally precede names).
    2. At the same position, `publiek` beats `ambtenaar` (the
       public-officials-do-not-redact rule is stronger than the
       civil-servant pre-fill).
    3. Otherwise prefer the match closer (fewer tokens_between) to the span.
    """
    if current is None:
        return True
    if candidate.position != current.position:
        return candidate.position == "before"
    if candidate.list_name != current.list_name:
        return candidate.list_name == "publiek"
    return candidate.tokens_between < current.tokens_between


def find_function_title_near(
    full_text: str,
    span_start: int,
    span_end: int,
    lists: FunctionTitleLists,
    window: int = DEFAULT_WINDOW_CHARS,
) -> FunctionTitleMatch | None:
    """Scan a window around [span_start, span_end] for a function title.

    Looks at up to `window` characters before `span_start` and after
    `span_end` (not including the span itself). Every title in both
    lists is tried; the best match is returned per the tie-breaking
    rules in `_is_better`. Returns None if nothing fires within the
    proximity threshold.

    The matcher is case-insensitive and whole-word, so "wethouder" and
    "Wethouder" both fire but "wethouderschap" does not.

    Bestuursorgaan phrases are masked out of the context first, so the
    "gedeputeerde" in "Gedeputeerde Staten van Drenthe" cannot be read
    as the title of the name printed beside it. Masking keeps offsets
    and token distances intact, so everything below still slices the
    text with the caller's original character positions.
    """
    if span_start < 0 or span_end <= span_start or span_end > len(full_text):
        return None

    # One masked copy of everything the scans below can reach, padded so
    # a phrase straddling a window edge is still matched as a whole.
    region_start = max(0, span_start - _LIST_CONTEXT_WINDOW_CHARS - _ORGAN_MASK_PAD_CHARS)
    region_end = min(len(full_text), span_end + window + _ORGAN_MASK_PAD_CHARS)
    region = mask_organ_phrases(full_text[region_start:region_end], lists.organ_patterns)

    def masked(start: int, end: int) -> str:
        """Slice the masked region using absolute offsets into `full_text`."""
        return region[start - region_start : end - region_start]

    before_start = max(0, span_start - window)
    before_text = masked(before_start, span_start)
    after_end = min(len(full_text), span_end + window)
    after_text = masked(span_end, after_end)

    # Wider slice used only for list-context matching (see below). We
    # compute it once instead of per-title because it is only consulted
    # when the narrow window produced no hit.
    list_start = max(0, span_start - _LIST_CONTEXT_WINDOW_CHARS)
    list_before_text = masked(list_start, span_start)

    best: FunctionTitleMatch | None = None

    for list_name, title, pattern in lists.iter_all():
        # Before-context: prefer the rightmost match (closest to the span).
        last_before: re.Match[str] | None = None
        for m in pattern.finditer(before_text):
            last_before = m
        if last_before is not None:
            between = before_text[last_before.end() :]
            tokens_between = _count_tokens(between)
            if tokens_between <= _MAX_TOKENS_BETWEEN:
                candidate = FunctionTitleMatch(
                    title=title,
                    list_name=list_name,
                    position="before",
                    tokens_between=tokens_between,
                )
                if _is_better(candidate, best):
                    best = candidate

        # List-context before: look further back and accept only when
        # the intervening text parses as a comma/en-separated list of
        # names (honorifics + initials + proper-noun tokens + separators).
        # This is what lets "fractievoorzitters dhr. R. van Gelderen,
        # mw. L. Rozendaal, dhr. M. Dirkse en mw. S. Abdelkader" apply
        # the title to all four names instead of only the first.
        list_before_hit: re.Match[str] | None = None
        for m in pattern.finditer(list_before_text):
            list_before_hit = m
        # Skip if the wider scan hit the same match as the narrow one
        # AND the narrow path actually accepted it (produced a candidate
        # within the token limit). If the narrow path found the title
        # but rejected it (too many tokens between), the list-context
        # path should still try — its interior-pattern check is more
        # permissive and handles bullet-separated lists.
        narrow_offset = len(list_before_text) - len(before_text)
        narrow_tokens_between = (
            _count_tokens(before_text[last_before.end() :])
            if last_before is not None
            else _MAX_TOKENS_BETWEEN + 1
        )
        same_as_narrow = (
            last_before is not None
            and narrow_tokens_between <= _MAX_TOKENS_BETWEEN
            and list_before_hit is not None
            and list_before_hit.start() == last_before.start() + narrow_offset
        )
        if list_before_hit is not None and not same_as_narrow:
            interior = list_before_text[list_before_hit.end() :]
            # Strip a leading colon + whitespace: titles like
            # "Fractievoorzitters:" are followed by a colon before the
            # name list. We strip it here rather than accepting colons
            # anywhere in the interior (which would let the list bleed
            # through section boundaries like "Inspreker: mevrouw ...").
            interior = interior.lstrip(": ")
            if interior and _LIST_INTERIOR_PATTERN.match(interior):
                candidate = FunctionTitleMatch(
                    title=title,
                    list_name=list_name,
                    position="before",
                    tokens_between=_count_tokens(interior),
                )
                if _is_better(candidate, best):
                    best = candidate

        # After-context: prefer the leftmost match (closest to the span).
        first_after = pattern.search(after_text)
        if first_after is not None:
            between = after_text[: first_after.start()]
            tokens_between = _count_tokens(between)
            if tokens_between <= _MAX_TOKENS_BETWEEN:
                candidate = FunctionTitleMatch(
                    title=title,
                    list_name=list_name,
                    position="after",
                    tokens_between=tokens_between,
                )
                if _is_better(candidate, best):
                    best = candidate

    return best
