"""Huisnummer / residence-cued "nummer N" rule (#51).

Woo documents routinely anonymize partially: the street is dropped
but "(huisnummer 22)" or "bewoner van nummer 26" stays in the prose.
When the street name is mentioned elsewhere in the document, those
bare numbers are directly identifying — exactly the contextual PII
Tier 2 `adres` is meant to cover. Deduce's built-in `huisnummer` tag
only fires when there is already a street token adjacent to the
number, so it misses these partially-anonymized cases entirely.

`huisnummer N` always fires — the literal word is effectively
unambiguous in Dutch government prose. The whole phrase is the span
so the redacted output reads "mevrouw T. Bakker (███)" instead of
leaking the category with "huisnummer ███".

`nummer N` is gated on a residence cue (`bewoner`, `woont`,
`woonachtig`) to keep `zaaknummer`, `dossiernummer`, `volgnummer`,
`artikelnummer`, etc. out of the review list. The emitted span
covers only "nummer N" so "bewoner van ███ heeft ingediend" still
conveys "a resident filed this" without naming the residence.
"""

from __future__ import annotations

import re

from ._types import NERDetection

_HUISNUMMER_PATTERN = re.compile(
    r"\bhuisnummer\s+\d{1,4}[a-zA-Z]?\b",
    re.IGNORECASE,
)

_RESIDENCE_NUMMER_PATTERN = re.compile(
    r"\b(?:bewoners?\s+(?:van\s+)?|woon(?:t|achtig)\s+op\s+)"
    r"(nummer\s+\d{1,4}[a-zA-Z]?)\b",
    re.IGNORECASE,
)


def _detect_adres_by_huisnummer(text: str) -> list[NERDetection]:
    """Emit Tier 2 `adres` detections for `huisnummer N` and
    residence-cued `nummer N` fragments that Deduce misses in
    partially-anonymized Woo prose.

    These are Tier 2 because the number alone is only identifying in
    context (when the street is mentioned elsewhere in the document).
    Review default is `pending` — reviewer confirms or rejects.
    """
    detections: list[NERDetection] = []

    for m in _HUISNUMMER_PATTERN.finditer(text):
        detections.append(
            NERDetection(
                text=m.group(0),
                entity_type="adres",
                tier="2",
                confidence=0.85,
                woo_article="5.1.2e",
                source="regex",
                start_char=m.start(),
                end_char=m.end(),
                reasoning=(
                    "Huisnummer in tekst — in combinatie met een straatnaam "
                    "elders in het document herleidbaar tot een woonadres."
                ),
            )
        )

    for m in _RESIDENCE_NUMMER_PATTERN.finditer(text):
        # Span covers only the `nummer N` group, not the preceding
        # "bewoner van" / "woont op". Leaving the cue in place keeps
        # the redacted sentence readable.
        inner_start = m.start(1)
        inner_end = m.end(1)
        detections.append(
            NERDetection(
                text=text[inner_start:inner_end],
                entity_type="adres",
                tier="2",
                confidence=0.80,
                woo_article="5.1.2e",
                source="regex",
                start_char=inner_start,
                end_char=inner_end,
                reasoning=(
                    "Huisnummer met bewonerscontext — mogelijk woonadres."
                ),
            )
        )

    return detections
