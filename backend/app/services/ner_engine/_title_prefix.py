"""Title-prefix rule (#48) — catch names whose surname is NOT in CBS.

Deduce + the CBS achternamenlijst handle "W. de Groot" well, but they
silently miss common non-Dutch surnames ("El Khatib", "Bekir Yılmaz",
"Agnieszka Kowalski") because those tokens are absent from CBS. The
fix is a second rule path: when a Dutch salutation / family anchor
immediately precedes one or more capitalized tokens, treat the
sequence as a person name regardless of the CBS lookup.

Anchors are *salutations*, not function titles. The publiek-
functionaris filter (#13) still runs on the full pipeline, so
"burgemeester Rutte" continues to be suppressed — this rule
intentionally does not fire on functietitels. Confidence is lower
(0.75 vs 0.90 on a CBS hit) because the false-positive potential is
higher.
"""

from __future__ import annotations

import re

from app.services.name_engine import NameLists

from ._plausibility import _is_plausible_person_name
from ._types import NERDetection

# Salutation / family anchors. Case-insensitive whole-word match, with a
# required trailing whitespace so we don't match inside bigger words.
# Listed longest first so "de familie" wins over "familie" when both
# would apply. `(?<![\w'])` anchors the left edge without requiring a
# word character boundary (which would fail after punctuation).
_TITLE_ANCHOR_PATTERN = re.compile(
    r"(?<![\w'])"
    r"(?:"
    r"de\s+familie|de\s+heer|"
    r"dhr\.|mevr\.|mw\.|mr\.|drs\.|prof\.|dr\.|"
    r"mevrouw|meneer|familie"
    r")"
    r"(?=\s)",
    re.IGNORECASE,
)

# Characters after a title that we step over before scanning for name
# tokens. Generous enough to cover "dhr., " or "mevr.\n" spacing.
_TITLE_SCAN_WINDOW_CHARS = 80

# A "name token" — a sequence of Unicode letters (plus apostrophe and
# hyphen) of length ≥ 2. The uppercase check is done in Python via
# ``str.isupper()`` on the first character, which correctly handles
# Turkish ("Yılmaz", "Öztürk"), Polish ("Łukasz"), Czech ("Čermák") and
# other extended-Latin alphabets that a fixed ASCII-range class misses.
# The upstream `_is_plausible_person_name` still vets the span.
_NAME_TOKEN = re.compile(r"[^\W\d_][\w'\-]+", re.UNICODE)


def _is_cap_name_token(tok: str) -> bool:
    """Return True if `tok` is a capitalized name-like token."""
    m = _NAME_TOKEN.fullmatch(tok)
    if m is None:
        return False
    return tok[:1].isupper()

# A "name token" in general: either an initial ("W.", "A.M."), a
# lowercase-led tussenvoegsel candidate, or a capitalized token.
# Tokenization is whitespace-delimited; the caller strips trailing
# sentence punctuation for everything except initials (where the
# trailing period is load-bearing).
_NAME_INITIAL = re.compile(r"(?:[A-Z]\.)+")
_NAME_TRAILING_PUNCT = ",.;:!?)]}"


def _detect_persoon_via_title_prefix(
    text: str,
    name_lists: NameLists,
) -> list[NERDetection]:
    """Emit Tier 2 `persoon` detections via the salutation + capitals rule.

    For each salutation anchor in `text`, walk forward past optional
    initials and tussenvoegsels, then consume capitalized tokens. The
    emitted span covers the name portion only — the anchor itself is
    excluded (same slicing convention as the CBS / Deduce hits).

    The result is a list of `NERDetection` with:
    - `entity_type="persoon"`, `tier="2"`
    - `confidence=0.75`
    - `source="title_rule"`
    - `reasoning="Naam herkend via titel + hoofdlettersequentie (niet in CBS-lijst)."`

    Caller is responsible for overlap-deduping against higher-confidence
    Deduce hits — see `detect_tier2`.
    """
    tussen_single = name_lists.tussenvoegsels
    tussen_sequences = name_lists.tussenvoegsel_sequences
    max_seq_len = max((len(s) for s in tussen_sequences), default=0)

    detections: list[NERDetection] = []

    for anchor in _TITLE_ANCHOR_PATTERN.finditer(text):
        scan_start = anchor.end()
        scan_end = min(len(text), scan_start + _TITLE_SCAN_WINDOW_CHARS)
        window = text[scan_start:scan_end]

        # Tokenize by whitespace, keeping absolute char offsets.
        # Initials ("W.") keep their trailing period — stripping it
        # would turn them into bare capitals that no longer match the
        # initial pattern. Every other trailing sentence punctuation
        # mark is peeled off so "Khatib," / "Kowalski." still parse.
        tokens: list[tuple[str, int, int]] = []
        for m in re.finditer(r"\S+", window):
            raw = m.group(0)
            raw_clean = raw if _NAME_INITIAL.fullmatch(raw) else raw.rstrip(_NAME_TRAILING_PUNCT)
            if not raw_clean:
                continue
            tokens.append(
                (
                    raw_clean,
                    scan_start + m.start(),
                    scan_start + m.start() + len(raw_clean),
                )
            )

        if not tokens:
            continue

        span_start: int | None = None
        span_end: int | None = None
        has_capitalized = False
        i = 0

        while i < len(tokens):
            tok, tok_start, tok_end = tokens[i]

            # Multi-token tussenvoegsel sequence ("van den", "de la", …).
            matched_seq = False
            if max_seq_len >= 2 and len(tokens) - i >= 2:
                for seq_len in range(min(max_seq_len, len(tokens) - i), 1, -1):
                    window_tup = tuple(tokens[i + k][0].lower() for k in range(seq_len))
                    if window_tup in tussen_sequences:
                        if span_start is None:
                            span_start = tok_start
                        span_end = tokens[i + seq_len - 1][2]
                        i += seq_len
                        matched_seq = True
                        break
            if matched_seq:
                continue

            # Initial: "W.", "A."
            if _NAME_INITIAL.fullmatch(tok):
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
            if _is_cap_name_token(tok):
                has_capitalized = True
                if span_start is None:
                    span_start = tok_start
                span_end = tok_end
                i += 1
                continue

            # Anything else (lowercase non-tussenvoegsel, digits, …): stop.
            break

        if not has_capitalized or span_start is None or span_end is None:
            continue

        name_text = text[span_start:span_end]

        # Sanity filter — reuses the Deduce heuristic so "de heer
        # Voorzitter" / organisation-keyword false positives are dropped
        # here too.
        if not _is_plausible_person_name(name_text):
            continue

        detections.append(
            NERDetection(
                text=name_text,
                entity_type="persoon",
                tier="2",
                confidence=0.75,
                woo_article="5.1.2e",
                source="title_rule",
                start_char=span_start,
                end_char=span_end,
                reasoning=("Naam herkend via titel + hoofdlettersequentie (niet in CBS-lijst)."),
            )
        )

    # Drop any detection whose span is fully contained within another
    # title-rule detection. Stacked anchors ("dhr. dr. Prof. Henk de
    # Vries") would otherwise emit "Prof. Henk de Vries" AND "Henk de
    # Vries" — keep the outermost span so the reviewer sees one card.
    if len(detections) > 1:
        kept: list[NERDetection] = []
        for d in sorted(
            detections,
            key=lambda x: (x.start_char, -(x.end_char - x.start_char)),
        ):
            if any(k.start_char <= d.start_char and k.end_char >= d.end_char for k in kept):
                continue
            kept.append(d)
        detections = kept

    return detections
