"""Per-document custom-term matcher (#21 — "eigen zoektermen").

A reviewer can maintain a per-document list of strings that must be
redacted wherever they occur — a bedrijfsnaam, a straatnaam, the
codename of an intern project. The list is persisted in
`document_custom_terms` and passed into the analyze pipeline on every
call; this module is the building block that scans the document text
for every occurrence and produces character-offset matches the pipeline
then maps onto bboxes and `Detection` rows.

Design notes
------------

- **Exact substring, case-insensitive.** `normalize_term` lowercases and
  collapses whitespace but preserves diacritics — a reviewer typing
  "Café Zuid" expects a literal match, not "Cafe Zuid". (Contrast with
  `normalize_reference_name` in `name_engine.py`, which strips
  diacritics to match Deduce's span text.)
- **No word-boundary constraint in v1.** The spec is explicit that a
  term which is a substring of a longer word must still match in exact
  mode — reviewers aren't engineers and they shouldn't need to reason
  about `\\b`. `prefix` and `whole_word` modes are reserved in the
  schema but deliberately not implemented here.
- **Non-overlapping matches for a single term.** Once an occurrence is
  found at index `i`, the scan advances past `i + len(term)` so the
  same run of characters never produces two matches for the same term.
- **Regex-free scanning.** The normalized terms come straight from
  reviewer input; feeding them into `re.compile` would either require
  escaping every call (easy to miss) or open the door to ReDoS. A plain
  `str.find` loop on the lowercased haystack is faster for the <50
  terms the UI allows and has no surprises.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_term(raw: str) -> str:
    """Normalize a reviewer-typed term for matching.

    Lowercased and whitespace-collapsed; diacritics are preserved. An
    empty-after-strip input returns an empty string, which the caller
    should treat as "drop this term" (the CRUD layer rejects empties at
    the API boundary, but the matcher stays defensive).
    """
    if not raw:
        return ""
    collapsed = _WHITESPACE_RE.sub(" ", raw).strip()
    return collapsed.lower()


class CustomTermLike(Protocol):
    """Structural interface the matcher expects.

    Accepts both the ORM row (`DocumentCustomTerm`) and the API
    payload (`CustomTermPayload`) without either needing to import the
    other. Whatever carries `term`, `match_mode`, and `woo_article`
    fits — the matcher computes its own normalized form.
    """

    term: str
    match_mode: str
    woo_article: str


@dataclass(frozen=True)
class TermMatch:
    """A single occurrence of a custom term in the analyzed text."""

    term: str
    """The original, reviewer-typed term (for the detection reasoning)."""

    match_mode: str
    woo_article: str
    start_char: int
    """Character offset into the full text where the match begins."""

    end_char: int
    """Exclusive end offset — `end_char - start_char == len(normalized)`."""


def match_custom_terms(text: str, terms: Sequence[CustomTermLike]) -> list[TermMatch]:
    """Return every occurrence of every custom term in `text`.

    Results are returned in the order they are discovered — per term,
    in order of appearance. Duplicate or overlapping hits for
    *different* terms are preserved; de-duplication against Tier 1 and
    Tier 2 detections happens in the pipeline caller, which has access
    to the full detection list.

    `exact` is the only implemented mode; any other value is silently
    skipped so that reserving `prefix`/`whole_word` in the schema is
    forward-compatible (older backends won't crash on newer rows).
    """
    if not text or not terms:
        return []

    haystack = text.lower()
    results: list[TermMatch] = []

    for term in terms:
        if term.match_mode != "exact":
            # Reserved modes — not implemented in v1. A future backend
            # will grow a branch here; an older backend that encounters
            # a row in a newer mode simply ignores it rather than
            # erroring out on import of the list.
            continue

        needle = normalize_term(term.term)
        if not needle:
            continue

        needle_len = len(needle)
        idx = 0
        while True:
            found = haystack.find(needle, idx)
            if found == -1:
                break
            results.append(
                TermMatch(
                    term=term.term,
                    match_mode=term.match_mode,
                    woo_article=term.woo_article,
                    start_char=found,
                    end_char=found + needle_len,
                )
            )
            # Non-overlapping advance: the next search starts after the
            # end of this match. A reviewer-typed term "aa" in "aaaa"
            # produces two matches, not three — overlapping hits would
            # double-count the middle character and confuse the undo
            # stack.
            idx = found + needle_len

    return results


__all__ = ["TermMatch", "CustomTermLike", "normalize_term", "match_custom_terms"]
