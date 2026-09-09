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

The forward token walk itself lives in `_name_walk`; `_anchor_rules`
(#97) uses the same walk from a wider set of anchors.
"""

from __future__ import annotations

import re

from app.services.name_engine import NameLists

from ._name_walk import walk_name
from ._plausibility import _is_plausible_person_name
from ._tier2_trim import is_form_field_row, trim_trailing_titles
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
    detections: list[NERDetection] = []

    for anchor in _TITLE_ANCHOR_PATTERN.finditer(text):
        scan_start = anchor.end()
        scan_end = min(len(text), scan_start + _TITLE_SCAN_WINDOW_CHARS)

        walk = walk_name(text, scan_start, scan_end, name_lists)
        if walk is None or walk.capitalized == 0:
            continue

        span_start, span_end = walk.start_char, walk.end_char
        name_text = text[span_start:span_end]

        # Strip function titles the walk absorbed ("mevrouw Wethouder
        # Jansen" → "Jansen") and drop the span when nothing but a title
        # remains ("mevrouw Wethouder", "de heer Voorzitter").
        name_text, span_start, span_end = trim_trailing_titles(name_text, span_start, span_end)
        if not name_text:
            continue

        # Sanity filter — reuses the Deduce heuristic so organisation-
        # keyword false positives are dropped here too.
        if not _is_plausible_person_name(name_text):
            continue

        # A form prints its salutation as a field of its own, so the
        # capitals under "Aanhef Mevr." are the *next* label, not the
        # name: "Straat en huisnummer" gave a `Straat` card (#98). The
        # anchor rules refuse a value made of field labels for the same
        # reason.
        if is_form_field_row(name_text):
            continue

        detections.append(
            NERDetection.tier2(
                text=name_text,
                entity_type="persoon",
                confidence=0.75,
                start_char=span_start,
                end_char=span_end,
                reasoning="Naam herkend via titel + hoofdlettersequentie (niet in CBS-lijst).",
                source="title_rule",
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
