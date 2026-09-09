"""Wordlist-driven name finder (#97) — Meertens ∧ CBS without Deduce.

The name lists are used as a *filter* everywhere else in Tier 2: Deduce
proposes a span, `score_person_candidate` checks whether any token is a
known Dutch given name or surname, and the span survives or does not.
The lists never propose anything themselves, so a plain
"Voornaam Achternaam" that Deduce walks past is lost even though both
halves are on a list we ship.

This rule closes that gap with the narrowest possible shape: a
capitalised token whose normalisation is in the Meertens
voornamenbank, optional tussenvoegsels, and a capitalised token whose
normalisation is in the CBS achternamenlijst. Both halves must hit —
one list alone ("Groen", "Bos", "Post") is the false-positive machine
that `_corroboration` exists to shut down.

Confidence is 0.80: the same two-list evidence a Deduce hit gets 0.95
for, minus the corroboration of a NER model having seen a name there.
"""

from __future__ import annotations

import re

from app.services.name_engine import NameLists, _normalize

from ._name_walk import is_cap_name_token
from ._org_context import contains_org_vocabulary
from ._plausibility import _is_plausible_person_name
from ._tier2_trim import is_role_or_section_word
from ._types import NERDetection

#: A word token: Unicode letters plus apostrophe and hyphen. The
#: capital check happens in Python (`str.isupper()` on the first
#: character) because Python's `re` has no Unicode uppercase class, so a
#: character class here would silently exclude "Öztürk" or accept
#: lowercase prose.
_WORD = re.compile(r"[^\W\d_][\w'\-]*", re.UNICODE)


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(text)]


def _same_line(text: str, left_end: int, right_start: int) -> bool:
    """True when only intra-line whitespace separates two tokens."""
    between = text[left_end:right_start]
    return between.strip() == "" and "\n" not in between


def _neighbour_is_org(
    text: str, tokens: list[tuple[str, int, int]], first_index: int, last_index: int
) -> bool:
    """True when the token on either side of the pair is organisation
    vocabulary, on the same line."""
    if first_index > 0:
        prev_tok, _prev_start, prev_end = tokens[first_index - 1]
        if (
            _same_line(text, prev_end, tokens[first_index][1])
            and contains_org_vocabulary(prev_tok) is not None
        ):
            return True
    if last_index + 1 < len(tokens):
        next_tok, next_start, _next_end = tokens[last_index + 1]
        if (
            _same_line(text, tokens[last_index][2], next_start)
            and contains_org_vocabulary(next_tok) is not None
        ):
            return True
    return False


def detect_persoon_via_wordlists(text: str, name_lists: NameLists) -> list[NERDetection]:
    """Emit Tier 2 `persoon` detections for Meertens + CBS token pairs.

    Caller is responsible for overlap-deduping against higher-confidence
    Deduce hits — see `detect_tier2`.
    """
    if not name_lists.first_names or not name_lists.last_names:
        return []

    tussen_single = name_lists.tussenvoegsels
    tussen_sequences = name_lists.tussenvoegsel_sequences
    max_seq_len = max((len(s) for s in tussen_sequences), default=0)

    tokens = _tokens(text)
    detections: list[NERDetection] = []

    for i, (first, first_start, first_end) in enumerate(tokens):
        if not is_cap_name_token(first):
            continue
        if _normalize(first) not in name_lists.first_names:
            continue

        # Step over a tussenvoegsel run ("de", "van der", "el"), longest
        # sequence first so "van der Meer" does not stop at "van".
        j = i + 1
        prev_end = first_end
        while j < len(tokens):
            matched = 0
            for seq_len in range(min(max_seq_len, len(tokens) - j), 1, -1):
                window = tuple(tokens[j + k][0].lower() for k in range(seq_len))
                if window in tussen_sequences and all(
                    _same_line(text, tokens[j + k - 1][2], tokens[j + k][1])
                    for k in range(1, seq_len)
                ):
                    matched = seq_len
                    break
            if not matched and tokens[j][0].lower() in tussen_single:
                matched = 1
            if not matched or not _same_line(text, prev_end, tokens[j][1]):
                break
            prev_end = tokens[j + matched - 1][2]
            j += matched

        if j >= len(tokens) or j == i:
            continue
        last, last_start, last_end = tokens[j]
        if not _same_line(text, prev_end, last_start):
            continue
        if not is_cap_name_token(last):
            continue
        if _normalize(last) not in name_lists.last_names:
            continue

        span_text = text[first_start:last_end]
        if is_role_or_section_word(first) or is_role_or_section_word(last):
            continue
        if contains_org_vocabulary(span_text) is not None:
            continue
        # A pair the surrounding line frames as a trading name — "De Jan
        # Bakker Stichting", "Stichting Jan Bakker", "Jan Bakker Holding
        # B.V.". The Deduce path gets the same protection at pipeline
        # level from `legal_form_lead` (#96); this rule proposes spans
        # Deduce never saw, so it has to look for itself.
        if _neighbour_is_org(text, tokens, i, j):
            continue
        if not _is_plausible_person_name(span_text):
            continue

        detections.append(
            NERDetection.tier2(
                text=span_text,
                entity_type="persoon",
                confidence=0.80,
                start_char=first_start,
                end_char=last_end,
                reasoning=(
                    "Persoonsnaam herkend: voornaam op lijst van het "
                    "Meertens Instituut (Nederlandse Voornamenbank), "
                    "achternaam op CBS-achternamenlijst."
                ),
                source="wordlist_rule",
            )
        )
    return detections
