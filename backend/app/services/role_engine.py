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

See `docs/todo/done/13-functietitel-publiek-functionaris.md` for the full
design. The rule engine intentionally only looks at a small window
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


ListName = Literal["publiek", "ambtenaar"]
Position = Literal["before", "after"]


@dataclass(frozen=True)
class FunctionTitleLists:
    """Compiled function-title lists ready for matching.

    `publiek` and `ambtenaar` are ordered lists of normalized title
    strings (lowercase, whitespace-collapsed). `patterns` holds the
    pre-compiled case-insensitive regexes for each title, keyed by
    `(list_name, title)` so we can iterate them quickly.
    """

    publiek: tuple[str, ...]
    ambtenaar: tuple[str, ...]
    patterns: dict[tuple[ListName, str], re.Pattern[str]]

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


def load_function_title_lists() -> FunctionTitleLists:
    """Load both function-title files once and return compiled patterns.

    Call from `main.lifespan` and cache on `app.state.function_title_lists`.
    The I/O is trivial (few dozen titles total) so callers that forget
    can also call this lazily without any measurable cost.
    """
    publiek = _load_title_file(_PUBLIEK_FILE)
    ambtenaar = _load_title_file(_AMBTENAAR_FILE)

    patterns: dict[tuple[ListName, str], re.Pattern[str]] = {}
    for title in publiek:
        patterns[("publiek", title)] = _compile_title_pattern(title)
    for title in ambtenaar:
        patterns[("ambtenaar", title)] = _compile_title_pattern(title)

    logger.info(
        "role_engine.lists_loaded",
        publiek=len(publiek),
        ambtenaar=len(ambtenaar),
    )
    return FunctionTitleLists(publiek=publiek, ambtenaar=ambtenaar, patterns=patterns)


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


def _count_tokens(text: str) -> int:
    """Count whitespace-separated tokens in `text`.

    Punctuation like a comma between a name and its apposed title
    ("Jan, wethouder") collapses to zero tokens, which is what we want:
    the title is immediately adjacent.
    """
    return len(text.split())


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
    """
    if span_start < 0 or span_end <= span_start or span_end > len(full_text):
        return None

    before_start = max(0, span_start - window)
    before_text = full_text[before_start:span_start]
    after_end = min(len(full_text), span_end + window)
    after_text = full_text[span_end:after_end]

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
