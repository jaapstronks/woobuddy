"""Cheap heuristic filter for Deduce ``persoon`` false positives.

Deduce was trained on medical records and over-tags institution names,
fragments, and common nouns as persons. This module provides the
pre-filter that runs before a detection is emitted, so the obvious
garbage never enters the review list in the first place.
"""

from __future__ import annotations

import re

# Institutions and generic-noun keywords that indicate a Deduce `persoon`
# hit is actually an organization, place, or common noun — not a person.
# Matched case-insensitively as whole words anywhere in the detection text.
# Source: real false positives observed on Dutch Woo documents (e.g.
# "Amsterdamse Hogeschool voor de Kunsten", "Instituut Beeld & Geluid",
# "Naturalis", "Rijksmuseum", "Kunsthal", "gemeente Amsterdam").
_ORGANIZATION_KEYWORDS = {
    # Education
    "hogeschool",
    "universiteit",
    "school",
    "academie",
    "faculteit",
    "college",
    "lyceum",
    "gymnasium",
    "mbo",
    "hbo",
    # Research / cultural institutions
    "instituut",
    "museum",
    "kunsthal",
    "bibliotheek",
    "archief",
    "theater",
    "concertgebouw",
    "orkest",
    # Government bodies ("college" already listed above)
    "gemeente",
    "provincie",
    "ministerie",
    "raad",
    "commissie",
    "directie",
    "afdeling",
    "departement",
    "bureau",
    "dienst",
    "kamer",
    "tweedekamer",
    "eerstekamer",
    "kabinet",
    "rechtbank",
    "hof",
    # Companies / legal forms
    "stichting",
    "vereniging",
    "fonds",
    "platform",
    "federatie",
    "unie",
    "coöperatie",
    "cooperatie",
    "maatschappij",
    "holding",
    "groep",
    # Health
    "ziekenhuis",
    "kliniek",
    "zorgcentrum",
    "ggd",
    "ggz",
    # Religious / misc
    "kerk",
    "moskee",
    "synagoge",
    "tempel",
    "parochie",
}

# Dutch articles and demonstratives that signal a Deduce hit is a
# generic noun phrase rather than a name. Matched case-insensitively
# on the first token.
#
# NOTE: common tussenvoegsels like "van", "ter", "ten", "der" are
# deliberately NOT in this set — real Dutch surnames start with them
# ("Van den Berg", "Ter Horst"). The "de"/"het"/"een" case is handled
# with a look-ahead: we only reject when no later token is capitalised,
# which distinguishes "de Vries" (a name) from "de gemeente" (not).
_NON_NAME_STARTERS = {
    "de",
    "het",
    "een",
    "dit",
    "dat",
    "deze",
    "die",
    "wat",
    "welk",
    "welke",
    "zijn",
    "haar",
    "hun",
    "onze",
    "jouw",
    "uw",
}


def _is_plausible_person_name(text: str) -> bool:
    """Cheap heuristic filter for Deduce `persoon` false positives.

    Runs before the detection is emitted, so organization names,
    fragments, and generic phrases never enter the review list in the
    first place. The goal is to drop the obvious garbage — marginal
    cases should still be kept and fall through to the LLM verifier.
    Returns True to keep the detection, False to drop it.
    """
    stripped = text.strip()
    if not stripped:
        return False

    # Length guard — real Dutch names cap out well under 50 chars even
    # for "Van den Berg-Van der Velde" style compounds.
    if len(stripped) > 50:
        return False
    if len(stripped) < 2:
        return False

    # Must contain at least one uppercase letter — names are capitalised.
    # Drops lowercase fragments like "partnerschappen met het rijks m".
    if not any(c.isupper() for c in stripped):
        return False

    original_tokens = stripped.split()
    lower_tokens = [t.lower() for t in original_tokens]
    if not original_tokens:
        return False

    # Reject if the first token is a Dutch article / demonstrative
    # AND no later token is capitalised. This distinguishes
    # "de Vries" (surname — later 'Vries' is capitalised, kept)
    # from "de gemeente" (generic phrase — nothing capitalised after
    # 'de', rejected).
    if lower_tokens[0] in _NON_NAME_STARTERS:
        later_capital = any(t[:1].isupper() for t in original_tokens[1:])
        if not later_capital:
            return False

    # Reject if any token is an organization keyword. This kills
    # "Amsterdamse Hogeschool", "Instituut Beeld", "gemeente Amsterdam",
    # "Stichting Woo Buddy", etc. The keyword has to appear as a whole
    # token — "Schoolstraat" does not trigger on "school".
    if _ORGANIZATION_KEYWORDS & set(lower_tokens):
        return False

    # Reject if the text contains a sentence-ending period followed
    # by a lowercase word — that's a multi-sentence fragment, not a
    # name. Example: "Kunsten. technologie in de context".
    #
    # The lookbehind `(?<=[a-z])` requires the period to follow a
    # lowercase letter, so initials like "A.M. van der Berg" are not
    # mistaken for sentence boundaries (the period there follows an
    # uppercase letter).
    if re.search(r"(?<=[a-z])\.\s+[a-z]", stripped):
        return False

    # Reject single-letter trailing fragments: "... het Rijks m".
    # A real name can end with an initial, but only if the initial is
    # written with a trailing period ("Jan de V."). A lone letter
    # without a period is almost always a pdf.js split artefact.
    last = original_tokens[-1]
    return not (len(original_tokens) >= 2 and len(last) == 1 and last.isalpha())
