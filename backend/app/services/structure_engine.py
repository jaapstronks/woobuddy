"""Structure engine — detect structurally significant regions in Dutch text.

The engine identifies three kinds of structured regions that give us
high-precision targets for Tier 2 redaction:

- **Email headers** (`Van:/Aan:/CC:/Bcc:/Onderwerp:/Verzonden:/Datum:`)
- **Signature blocks** (after `Met vriendelijke groet`, `Hoogachtend`, …)
- **Salutations** (`Geachte heer/mevrouw …`, `Beste …`, `L.S.`)

A Tier 2 `persoon` detection that falls inside an email header or a
signature block is almost never a false positive — the structure itself
is the evidence — so the pipeline auto-accepts it. A detection inside a
salutation is a strong "private citizen is being addressed" signal,
pre-filling `subject_role="burger"`.

This is pure rule-based pattern matching. No model calls, no wordlists
beyond what the caller already has. See `docs/todo/14-structuurherkenning.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.services.pdf_engine import ExtractionResult

StructureKind = Literal["email_header", "signature_block", "salutation"]


@dataclass(frozen=True)
class StructureSpan:
    """A single labeled structural region in the extracted text."""

    kind: StructureKind
    start_char: int
    end_char: int
    confidence: float
    evidence: str  # the trigger substring that opened this span


# ---------------------------------------------------------------------------
# Line utilities
# ---------------------------------------------------------------------------


def _iter_lines(text: str) -> list[tuple[str, int, int]]:
    """Return `(line_text, start_char, end_char)` for every line in `text`.

    Line endings are excluded from `line_text` but the offsets are relative
    to the original string so the spans we emit align with caller indexing.
    Empty lines are included (with `line_text == ""`) so the signature-block
    detector can count blank lines inside its window.
    """
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"^.*$", text, re.MULTILINE)]


# ---------------------------------------------------------------------------
# Email header detection
# ---------------------------------------------------------------------------

# Lines that *open* an email-header block. Dutch fields only — English
# headers (From:/To:/Subject:) are intentionally out of scope because Woo
# documents are Dutch and a line like "From: research and development"
# in body prose would fire far too often.
_EMAIL_HEADER_TRIGGER = re.compile(
    r"^\s*(van|aan|cc|bcc|onderwerp|verzonden|datum)\s*:",
    re.IGNORECASE,
)

# A "header-shaped" line — a capitalised word followed by a colon and
# some non-empty content. Used to extend a block past its opening trigger
# so `Van:` / `Aan:` / `Onderwerp:` can all grow the same span.
_HEADER_SHAPED_LINE = re.compile(r"^\s*[A-Z][A-Za-z]+\s*:\s*\S")

# Soft cap so a runaway "Name: value" table in the body text can't
# accidentally swallow half the document.
_MAX_HEADER_LINES = 15


def _detect_email_headers(
    lines: list[tuple[str, int, int]],
) -> list[StructureSpan]:
    """Find contiguous `Van:/Aan:/…` header blocks in a line-split text."""
    spans: list[StructureSpan] = []
    i = 0
    while i < len(lines):
        line, start, end = lines[i]
        trigger = _EMAIL_HEADER_TRIGGER.match(line)
        if trigger is None:
            i += 1
            continue

        block_start = start
        block_end = end
        evidence = trigger.group(0).strip()
        consumed = 1
        j = i + 1
        while j < len(lines) and consumed < _MAX_HEADER_LINES:
            next_line, _next_start, next_end = lines[j]
            # A blank line ends the block.
            if not next_line.strip():
                break
            # A non-header-shaped line ends the block.
            if not (
                _EMAIL_HEADER_TRIGGER.match(next_line)
                or _HEADER_SHAPED_LINE.match(next_line)
            ):
                break
            block_end = next_end
            consumed += 1
            j += 1

        spans.append(
            StructureSpan(
                kind="email_header",
                start_char=block_start,
                end_char=block_end,
                confidence=0.95,
                evidence=evidence,
            )
        )
        # Jump past the block. If the while loop above didn't advance
        # (rare: trigger alone), still step forward once to avoid a loop.
        i = j if j > i else i + 1

    return spans


# ---------------------------------------------------------------------------
# Signature block detection
# ---------------------------------------------------------------------------

# Dutch closings. Longer phrases come first because `re.match` takes the
# first matching alternative — without this ordering "groet" would win
# before "groeten" even on a "groeten" line, producing wrong evidence.
_SIGNATURE_TRIGGERS = re.compile(
    r"^\s*("
    r"met vriendelijke groeten|"
    r"met vriendelijke groet|"
    r"met hartelijke groet|"
    r"vriendelijke groeten|"
    r"vriendelijke groet|"
    r"hoogachtend|"
    r"groet,"
    r")",
    re.IGNORECASE,
)

# A disclaimer URL inside the signature tail marks the transition from
# "signer details" into the boilerplate email footer. The signature ends
# at that point.
_DISCLAIMER_URL = re.compile(
    r"https?://\S*\b(disclaimer|privacy|cookies|unsubscribe)\b",
    re.IGNORECASE,
)

# How many non-blank lines after the trigger we'll include. 6 covers the
# typical "Name / Function / Organization / Phone / Email / URL" tail.
_SIGNATURE_MAX_LINES = 6


def _detect_signature_blocks(
    lines: list[tuple[str, int, int]],
    salutation_line_indexes: set[int],
) -> list[StructureSpan]:
    """Find signature blocks opened by a Dutch closing phrase."""
    spans: list[StructureSpan] = []
    for i, (line, start, end) in enumerate(lines):
        trigger = _SIGNATURE_TRIGGERS.match(line)
        if trigger is None:
            continue

        block_start = start
        block_end = end
        evidence = trigger.group(0).strip()

        non_blank_taken = 0
        blank_run = 0
        j = i + 1
        while j < len(lines) and non_blank_taken < _SIGNATURE_MAX_LINES:
            next_line, _next_start, next_end = lines[j]
            if not next_line.strip():
                blank_run += 1
                if blank_run >= 2:
                    break
                j += 1
                continue
            # A new salutation opens the next message in an email thread.
            if j in salutation_line_indexes:
                break
            # Disclaimer URL — the footer starts here.
            if _DISCLAIMER_URL.search(next_line):
                break
            blank_run = 0
            block_end = next_end
            non_blank_taken += 1
            j += 1

        spans.append(
            StructureSpan(
                kind="signature_block",
                start_char=block_start,
                end_char=block_end,
                confidence=0.90,
                evidence=evidence,
            )
        )
    return spans


# ---------------------------------------------------------------------------
# Salutation detection
# ---------------------------------------------------------------------------

# Case-sensitive where it matters: `Beste` and "Geachte ... [A-Z]" expect a
# capitalised first-token-of-a-letter so they don't fire on sentence-internal
# uses like "beste vriend".
_SALUTATION_PATTERNS: list[re.Pattern[str]] = [
    # "Geachte heer", "Geachte mevrouw", "Geachte heer/mevrouw",
    # "Geachte heer en mevrouw" — case-insensitive is fine here because
    # "geachte" in lowercase is already rare outside a letter opening.
    re.compile(
        r"^\s*Geachte\s+(heer/mevrouw|heer\s+en\s+mevrouw|heer|mevrouw)\b",
        re.IGNORECASE,
    ),
    # "Beste <Name>" — case-sensitive capital B to avoid matching "beste"
    # in body prose ("dit is de beste optie").
    re.compile(r"^\s*Beste\s+\w+\b"),
    # "L.S." ("Lectori Salutem") — formal, always capitalised. We can't
    # use `\b` after a literal period (the period is non-word and a
    # following newline/EOL is also non-word, so the boundary fails),
    # so require the close to be followed by whitespace, punctuation, or
    # end-of-string.
    re.compile(r"^\s*L\.S\.(?=\s|[,;:!?]|$)"),
    # Fallback: "Geachte <Capitalised>" — a last-name opener without heer/mevrouw.
    re.compile(r"^\s*Geachte\s+[A-Z]"),
]


def _detect_salutations(
    lines: list[tuple[str, int, int]],
) -> tuple[list[StructureSpan], set[int]]:
    """Find one-line salutations. Returns spans plus the set of line
    indexes that contain a salutation so the signature detector can use
    them as a stop condition."""
    spans: list[StructureSpan] = []
    line_indexes: set[int] = set()
    for i, (line, start, end) in enumerate(lines):
        for pat in _SALUTATION_PATTERNS:
            m = pat.match(line)
            if m is None:
                continue
            spans.append(
                StructureSpan(
                    kind="salutation",
                    start_char=start,
                    end_char=end,
                    confidence=0.85,
                    evidence=m.group(0).strip(),
                )
            )
            line_indexes.add(i)
            break  # One salutation per line — don't double-emit.
    return spans, line_indexes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_structures(extraction: ExtractionResult) -> list[StructureSpan]:
    """Scan the extracted text for structurally significant spans.

    Returns the list of spans in document order. Kinds can overlap
    (e.g. a signature line inside a quoted email), and callers should
    intersect spans with Tier 2 detections to decide confidence boosts.
    """
    text = extraction.full_text
    if not text:
        return []

    lines = _iter_lines(text)

    # Salutations first so the signature detector can use them as a stop.
    salutations, salutation_indexes = _detect_salutations(lines)
    email_headers = _detect_email_headers(lines)
    signatures = _detect_signature_blocks(lines, salutation_indexes)

    spans: list[StructureSpan] = []
    spans.extend(email_headers)
    spans.extend(signatures)
    spans.extend(salutations)
    spans.sort(key=lambda s: (s.start_char, s.end_char))
    return spans


def find_enclosing_structure(
    structure_spans: list[StructureSpan],
    start_char: int,
    end_char: int,
) -> StructureSpan | None:
    """Return the structure span that fully contains `[start_char, end_char]`.

    If more than one span contains the range, email_header and
    signature_block take priority over salutation — the broader block
    carries stronger "auto-accept" semantics than a one-line salutation.
    """
    best: StructureSpan | None = None
    for span in structure_spans:
        if span.start_char <= start_char and span.end_char >= end_char:
            if best is None:
                best = span
                continue
            if best.kind == "salutation" and span.kind != "salutation":
                best = span
    return best
