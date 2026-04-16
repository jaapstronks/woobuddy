"""Label-anchored identifier rule — klantnummer / factuurnummer / …

Dutch invoices, Woo correspondence, and decision letters routinely
identify a citizen via a labelled reference number:

    Klantnummer:    1.11368173
    Relatienummer:  987654
    Dossiernummer:  2024/12345
    Kenmerk:        OT-ID1382702-2025
    Factuurnummer:  901583844500
    Zaaknummer:     Z/24/0001

None of these are personal data on their own, but in combination with
a vendor name or document origin they resolve to exactly one natural
person — which is precisely the contextual identifier that Woo Art.
5.1.2e is written for. They were not detected at all before this
rule: neither Tier 1 regex nor Deduce NER emits them.

This module is the missing path. It matches a labelled number pattern
and emits a new `referentie` detection with a tiered confidence:

- **0.85** — directly identifying (klantnummer, relatienummer,
  debiteurennummer, polisnummer, patiëntnummer). These identify
  exactly one natural person once the vendor is known and should be
  surfaced at the top of the review list.
- **0.70** — frequently identifying (dossiernummer, kenmerk, ons
  kenmerk, uw kenmerk, referentienummer). Often tied to a single
  citizen but can also be a government-side case number; reviewer
  decides.
- **0.60** — administrative (factuurnummer, ordernummer,
  zaaknummer). The number is not itself personal data, but in
  combination with other fields in the same document it can be used
  to look up the customer record. Surfaced for review rather than
  suppressed.

The **span covers the number only**, not the label. That way the
redacted output reads "Klantnummer: ███" — the category stays
readable, only the identifier is blacked out. Mirrors the slicing
convention in `_huisnummer.py` for `bewoner van nummer N`.
"""

from __future__ import annotations

import re

from ._types import NERDetection

# Label → (confidence, reasoning) mapping. Labels are matched
# case-insensitively and treated as whole-token. Multi-word labels
# ("ons kenmerk", "uw kenmerk") are listed explicitly so the regex
# can anchor on them. Order does not matter for correctness but
# longer labels are listed first to help the alternation pick the
# most specific match.
_LABELS: dict[str, tuple[float, str]] = {
    # Directly identifying — one natural person per number.
    "klantnummer": (
        0.85,
        "Klantnummer — in combinatie met de leverancier direct "
        "herleidbaar tot een natuurlijk persoon.",
    ),
    "relatienummer": (
        0.85,
        "Relatienummer — in combinatie met de leverancier direct "
        "herleidbaar tot een natuurlijk persoon.",
    ),
    "debiteurennummer": (
        0.85,
        "Debiteurennummer — in combinatie met de leverancier direct "
        "herleidbaar tot een natuurlijk persoon.",
    ),
    "polisnummer": (
        0.85,
        "Polisnummer — in combinatie met de verzekeraar direct herleidbaar tot een verzekerde.",
    ),
    "patiëntnummer": (
        0.85,
        "Patiëntnummer — bijzonder persoonsgegeven in de gezondheidssector.",
    ),
    "patientnummer": (
        0.85,
        "Patiëntnummer — bijzonder persoonsgegeven in de gezondheidssector.",
    ),
    "lidnummer": (
        0.85,
        "Lidnummer — in combinatie met de vereniging/organisatie "
        "direct herleidbaar tot een natuurlijk persoon.",
    ),
    # Frequently identifying — often tied to a citizen, reviewer decides.
    "dossiernummer": (
        0.70,
        "Dossiernummer — mogelijk herleidbaar tot een natuurlijk persoon.",
    ),
    "referentienummer": (
        0.70,
        "Referentienummer — mogelijk herleidbaar tot een natuurlijk persoon.",
    ),
    "ons kenmerk": (
        0.70,
        "Kenmerk — mogelijk herleidbaar tot een natuurlijk persoon.",
    ),
    "uw kenmerk": (
        0.70,
        "Kenmerk — mogelijk herleidbaar tot een natuurlijk persoon.",
    ),
    "kenmerk": (
        0.70,
        "Kenmerk — mogelijk herleidbaar tot een natuurlijk persoon.",
    ),
    # Administrative — not personal data on their own, surfaced for review.
    "factuurnummer": (
        0.60,
        "Factuurnummer — administratief nummer, in combinatie met de leverancier herleidbaar.",
    ),
    "ordernummer": (
        0.60,
        "Ordernummer — administratief nummer, in combinatie met de leverancier herleidbaar.",
    ),
    "zaaknummer": (
        0.60,
        "Zaaknummer — administratief nummer, mogelijk een burger-zaak of een overheidszaak.",
    ),
}

# Labels sorted longest-first so "ons kenmerk" wins over "kenmerk"
# when the text contains the longer form. The regex alternation
# processes branches left-to-right and stops at the first match.
_SORTED_LABELS: list[str] = sorted(_LABELS.keys(), key=len, reverse=True)

# The label alternation. Each label is surrounded by word boundaries
# on the regex side; spaces inside multi-word labels are allowed to be
# any amount of whitespace.
_LABEL_ALT = "|".join(re.escape(label).replace(r"\ ", r"\s+") for label in _SORTED_LABELS)

# Full pattern:
#
# - Label (case-insensitive), followed by optional `:` / `-` and
#   whitespace.
# - A reference value in one of two shapes:
#   (a) Digit-led, with internal digits / dashes / dots / slashes /
#       spaces — so "1234 5678", "1.11368173", "2024/12345" all match.
#       Must start AND end with a digit so trailing prose is not
#       captured.
#   (b) Alphanumeric-led with internal letters / digits / dots /
#       dashes / slashes, no spaces. Captures "OT-ID1382702-2025",
#       "Z/24/0001". The ban on spaces inside (b) keeps
#       "Zaaknummer Z/24/0001 is in behandeling" from swallowing the
#       trailing prose.
#
# Group 1: the label text. Group 2: the reference value.
_LABEL_ANCHORED_ID_PATTERN = re.compile(
    rf"\b({_LABEL_ALT})\s*[:\-]?\s*"
    r"("
    r"\d[\d\- ./]{2,38}\d"  # (a) digit-led numeric run
    r"|"
    r"[A-Za-z0-9][A-Za-z0-9.\-/]{3,38}[A-Za-z0-9]"  # (b) alphanumeric, no spaces
    r")",
    re.IGNORECASE,
)

# The reference value must contain at least one digit. Letters-only
# matches like "Zie ons kenmerk bovenaan deze brief" are not
# identifiers.
_HAS_DIGIT = re.compile(r"\d")


def _detect_label_anchored_ids(text: str) -> list[NERDetection]:
    """Emit Tier 2 `referentie` detections for labelled identifiers.

    The span covers only the number, not the label — the redacted
    output reads "Klantnummer: ███" so the category stays readable.
    """
    detections: list[NERDetection] = []

    for m in _LABEL_ANCHORED_ID_PATTERN.finditer(text):
        label_text = m.group(1)
        # Normalize the label to look up the confidence/reasoning row.
        # `re.sub` collapses any internal whitespace to a single space
        # so "ons  kenmerk" matches "ons kenmerk" in the table.
        label_key = re.sub(r"\s+", " ", label_text.strip().lower())
        row = _LABELS.get(label_key)
        if row is None:
            continue
        confidence, reasoning = row

        number_start = m.start(2)
        number_end = m.end(2)
        number_text = text[number_start:number_end]

        # Strip any trailing whitespace / punctuation off the number
        # span — the regex class allows spaces for "123 456 789" but
        # a stray trailing space should not be part of the redaction.
        while number_text and number_text[-1] in " \t":
            number_text = number_text[:-1]
            number_end -= 1
        if not number_text:
            continue

        # Must contain at least one digit. Drops `kenmerk: zie bijlage`,
        # `zaaknummer wordt nog toegekend`, etc.
        if not _HAS_DIGIT.search(number_text):
            continue

        detections.append(
            NERDetection.tier2(
                text=number_text,
                entity_type="referentie",
                confidence=confidence,
                start_char=number_start,
                end_char=number_end,
                reasoning=reasoning,
                source="regex",
            )
        )

    return detections
