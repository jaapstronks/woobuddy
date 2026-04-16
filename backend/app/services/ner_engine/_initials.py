"""Initials-rule — catch `G.J. Stronks`-style persoon spans.

Deduce detects the span, but the name-list gate in `_tier2.py` drops
it when the Meertens voornamenlijst has no entry for the initials
("g.j") AND the surname is absent from the CBS top-N achternamenlijst.
Long-tail Dutch surnames (`Stronks`, `Kuipers`, `Veenstra`, `Bongers`)
routinely fail the CBS check, so a full signed-off persoonsnaam like
"G.J. Stronks" disappears without leaving a trail.

The salutation-anchored `_title_prefix` rule (#48) does not rescue
these cases: it requires a preceding "de heer" / "Dr." / "Mevrouw"
anchor, which rarely appears on letterheads, invoice headers, or
signature blocks where initials-style names are the norm.

This module is the missing path: detect `[Initials] [Surname]` on
structure alone. The shape is highly specific in Dutch prose — one
or more single-letter tokens with trailing periods, optionally
followed by a lowercase tussenvoegsel run, then one or two
capitalized surname tokens. Confidence is 0.85 (slightly below a
CBS-hit Deduce span, well above the 0.75 title-prefix rule) because
the pattern itself is the evidence; no wordlist lookup is required.

Caller (`detect_tier2`) is responsible for deduping against existing
`persoon` hits so a Deduce + CBS win is never demoted.
"""

from __future__ import annotations

import re

from ._plausibility import _is_plausible_person_name
from ._types import NERDetection

# One or more initials, each a single capital letter followed by a
# period. Accepts adjacent ("G.J.") and space-separated ("G. J.")
# variants — both are seen in practice on Dutch letters.
_INITIALS = r"(?:[A-Z]\.\s*){1,4}"

# Optional tussenvoegsel run between initials and surname. Allows
# both lowercase ("M. de Vries") and capitalized ("M. De Vries",
# "M. El Khatib") since Dutch convention capitalizes the tussen when
# the given name is omitted. Multi-token sequences are written
# explicitly so "van der" / "de la" match as one unit. Non-Dutch
# particles ("el", "al", "da", "di", "von") are included because the
# rule has to handle Dutch-government correspondence with international
# residents (mirrors `name_engine._TUSSENVOEGSELS_RAW`).
_TUSSEN = (
    r"(?:"
    # Dutch multi-token sequences first so the longest match wins.
    r"[Vv]an\s+(?:[Dd]en\s+|[Dd]er\s+|[Dd]e\s+|'t\s+|[Hh]et\s+)?|"
    r"[Dd]e\s+(?:[Ll]a\s+|[Ll]os\s+|[Ll]as\s+)?|"
    r"[Vv]on\s+(?:[Dd]er\s+|[Dd]en\s+)?|"
    r"[Oo]p\s+(?:[Dd]en\s+|[Dd]e\s+)?|"
    r"[Aa]an\s+(?:[Dd]en\s+|[Dd]e\s+)?|"
    r"[Ii]n\s+(?:[Dd]en\s+|[Dd]e\s+|'t\s+)?|"
    r"[Uu]it\s+(?:[Dd]en\s+|[Dd]e\s+)?|"
    # Single-token Dutch particles.
    r"[Dd]er\s+|[Dd]en\s+|[Hh]et\s+|'t\s+|"
    r"[Tt]en\s+|[Tt]er\s+|[Tt]e\s+|"
    # Non-Dutch particles routinely seen in Woo correspondence.
    r"[Ee]l\s+|[Aa]l\s+|[Aa]bu\s+|[Aa]bd\s+|[Bb]en\s+|[Bb]in\s+|[Ii]bn\s+|"
    r"[Dd]a\s+|[Dd]o\s+|[Dd]os\s+|[Dd]as\s+|[Dd]i\s+|[Dd]el\s+|[Dd]ella\s+|[Dd]al\s+|[Ll]o\s+|[Ll]a\s+|"
    r"[Vv]om\s+|[Zz]u\s+"
    r")"
)

# Legal-form and title abbreviations that look like initials but are
# not personal names. If the initials portion normalizes to any of
# these we skip the span entirely. Keeping the set small and concrete
# — the rule should err on the side of keeping ambiguous spans so the
# reviewer can make the call.
_LEGAL_FORM_ABBREVIATIONS = {
    "NV",
    "BV",
    "VOF",
    "CV",
    "VZW",
    "SA",
    "SL",
    "LLC",
    "LTD",
    "GMBH",
    "AG",
    "PLC",
    # Academic / professional abbreviations that also pattern-match
    # `[A-Z]\.[A-Z]\.` and tend to precede a capitalized word.
    "BSC",
    "MSC",
    "PHD",
    "MD",
    "LLM",
    "MBA",
}

# Capitalized surname token. Allows Dutch diacritics, apostrophes,
# hyphens, and a trailing hyphenated double surname like
# "Kuipers-Jansen". Minimum three characters total so short
# abbreviation fragments like "Sc" (from `M.Sc.`) or "Dr" do not get
# accepted as surnames. The CBS wordlist already has a 3-char
# minimum so this does not exclude any real Dutch family name.
_SURNAME_WORD = (
    r"[A-ZÄËÏÖÜÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛ]"
    r"[A-Za-zëéèïüöäáíóúàìòùâêîôû'’]{2,}"
    r"(?:-[A-ZÄËÏÖÜÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛ][A-Za-zëéèïüöäáíóúàìòùâêîôû'’]+)?"
)

_INITIALS_PATTERN = re.compile(
    r"(?<![\w.])"  # left anchor: not mid-word, not mid-initial run
    rf"({_INITIALS})"
    rf"(?:{_TUSSEN})?"
    rf"({_SURNAME_WORD})"
    r"\b",
    re.UNICODE,
)


def _detect_persoon_via_initials(text: str) -> list[NERDetection]:
    """Emit Tier 2 `persoon` detections for `[Initials] [Surname]` spans.

    Caller is responsible for overlap-deduping against higher-confidence
    Deduce `persoon` hits — see `detect_tier2`.
    """
    detections: list[NERDetection] = []

    for m in _INITIALS_PATTERN.finditer(text):
        start = m.start()
        end = m.end()

        # If the "surname" is immediately followed by `.<letter>`, it is
        # actually another initial or an abbreviation fragment ("M.Sc.
        # Johnson", "M.A. Jones"). Drop the match — the real name, if
        # any, will be picked up by a subsequent iteration at a later
        # offset.
        if end + 1 < len(text) and text[end] == "." and text[end + 1].isalpha():
            continue

        span_text = text[start:end].strip()

        # Drop legal-form / academic abbreviations masquerading as
        # initials ("N.V. Nederlandse Spoorwegen", "B.V. Kuipers
        # Holding", "M.Sc. Johnson"). The initials capture group is
        # everything up to the tussen / surname; strip periods and
        # whitespace before comparing.
        initials_raw = m.group(1)
        initials_norm = re.sub(r"[\s.]", "", initials_raw).upper()
        if initials_norm in _LEGAL_FORM_ABBREVIATIONS:
            continue

        # Reuse the organization / fragment filter. This drops cases
        # where the surname token is actually an org keyword
        # ("G.J. Stichting" is not a person).
        if not _is_plausible_person_name(span_text):
            continue

        detections.append(
            NERDetection(
                text=span_text,
                entity_type="persoon",
                tier="2",
                confidence=0.85,
                woo_article="5.1.2e",
                source="initials_rule",
                start_char=start,
                end_char=start + len(span_text),
                reasoning=(
                    "Naam herkend via initialen + achternaampatroon "
                    "(niet in CBS-lijst, maar structuur is eenduidig)."
                ),
            )
        )

    return detections
