"""Post-Deduce span-trimming helpers for Tier 2 person entities.

Deduce was trained on medical records and tends to greedily extend
person spans to absorb trailing job titles, section headings, and even
document-structure words ("geboortedatum"). The helpers here strip that
noise before the detection reaches the reviewer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Characters Deduce sometimes swallows into an entity span that we want
# to trim off before the detection reaches the reviewer: trailing commas
# and sentence punctuation, stray quotes, leading parentheses. Spaces
# are included so "  Jan Jansen " becomes "Jan Jansen".
_TRIM_CHARS = " \t\n\r,.;:!?\"'()[]"


def trim_span(annotation_text: str, start_char: int, end_char: int) -> tuple[str, int, int]:
    """Strip punctuation/whitespace from both ends of an entity span.

    Returns the (text, start, end) triple ready to be stored on the
    NERDetection. The caller is responsible for dropping empty results.
    """
    text = annotation_text
    start = start_char
    end = end_char
    while text and text[0] in _TRIM_CHARS:
        text = text[1:]
        start += 1
    while text and text[-1] in _TRIM_CHARS:
        text = text[:-1]
        end -= 1
    return text, start, end


# Where a Deduce person span was never one name to begin with. Deduce
# reaches across a sentence boundary ("Klacht ingediend door Jansen.
# Jansen stelt …" → one span "Jansen. Jansen") and across a line break,
# which in a Woo PDF can join two blocks forty points apart ("M.F." from
# a signature block glued to the "Van:" of a forwarded mail header, #93).
# Both halves are then judged as one name that nobody wrote.
#
# The period has to follow a *lowercase* letter: that is a finished
# sentence. After a capital it is an initial, and "A. Jans" must not be
# torn in two.
_SPAN_BREAK = re.compile(r"(?<=[a-z])\.[ \t]+|\n")

#: Abbreviated salutations and titles: the one place a lowercase letter,
#: a period and a space sit *inside* a name. "dhr. Jansen" is one span,
#: and the salutation is what the corroboration gate reads as the
#: evidence for the bare surname behind it — cut it off and the card is
#: lost, which is what the first cut of this split did.
_ABBREVIATED_PREFIXES: frozenset[str] = frozenset(
    {"dhr", "mevr", "mw", "mr", "mrs", "drs", "dr", "ir", "ing", "prof", "mgr", "jhr", "hr", "ds"}
)


def split_merged_span(text: str, start_char: int, end_char: int) -> list[tuple[str, int, int]]:
    """Cut a span at the boundaries Deduce should not have crossed.

    Returns one (text, start, end) triple per piece, offsets absolute,
    each still to be validated on its own — which is the point: a half
    that no wordlist and no anchor vouches for is dropped by the gates
    downstream instead of riding along on the other half's evidence.
    """
    pieces: list[tuple[str, int, int]] = []
    cursor = 0
    for m in _SPAN_BREAK.finditer(text):
        if m.group(0) != "\n":
            before = text[cursor : m.start()].rsplit(None, 1)
            if before and before[-1].lower() in _ABBREVIATED_PREFIXES:
                continue
        pieces.append((text[cursor : m.start()], start_char + cursor, start_char + m.start()))
        cursor = m.end()
    pieces.append((text[cursor:], start_char + cursor, end_char))
    return [(t, s, e) for t, s, e in pieces if t.strip()]


@dataclass(frozen=True)
class _TrailingTitleVocab:
    """Compiled trailing-title vocabulary for person-span trimming."""

    words: frozenset[str]
    phrases: tuple[str, ...]  # multi-word, sorted longest first


def _load_trailing_titles() -> _TrailingTitleVocab:
    """Build the trailing-title vocabulary from the role-engine data files."""
    data_dir = Path(__file__).resolve().parents[2] / "data"
    words: set[str] = set()
    phrases: list[str] = []

    for fname in ("functietitels_publiek.txt", "functietitels_ambtenaar.txt"):
        path = data_dir / fname
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            normalized = " ".join(line.lower().split())
            tokens = normalized.split()
            if len(tokens) > 1:
                phrases.append(normalized)
            else:
                words.add(normalized)

    # Generic role / section words not in the title lists but commonly
    # swallowed by Deduce into person spans.
    words |= {
        "voorzitter",
        "voorzitster",
        "secretaris",
        "penningmeester",
        "bestuurder",
        "rapporteur",
        "spreker",
        "betreft",
        "rondvraag",
        "toelichting",
        "bijlage",
        "advies",
        "casemanager",
        "coördinator",
        "hoofd",
        "manager",
        "medewerker",
        "sociaal",
        "domein",
        "zaken",
        "financiën",
        # Document-structure words Deduce absorbs after names
        "geboortedatum",
        "geboorteplaats",
        "woonplaats",
        "nationaliteit",
        "adres",
        "telefoonnummer",
        "emailadres",
    }

    return _TrailingTitleVocab(
        words=frozenset(words),
        phrases=tuple(sorted(phrases, key=len, reverse=True)),
    )


_trailing_title_vocab: _TrailingTitleVocab | None = None


def _get_trailing_titles() -> _TrailingTitleVocab:
    """Return the cached trailing-title vocabulary, loading on first use."""
    global _trailing_title_vocab  # noqa: PLW0603
    if _trailing_title_vocab is None:
        _trailing_title_vocab = _load_trailing_titles()
    return _trailing_title_vocab


# Leading non-name words to strip from person spans — section headings,
# greeting words, connectors, and Dutch administrative/legal role nouns
# Deduce absorbs into the span when they appear capitalized at the start
# of a sentence directly before a name ("Klaagster Jolanda Klaverstein").
_LEADING_STRIP_WORDS: frozenset[str] = frozenset(
    {
        # Section headings / greetings / connectors
        "rondvraag",
        "toelichting",
        "bijlage",
        "advies",
        # Document / agenda nouns that precede a capitalised word Deduce
        # then reads as a surname ("Motie Groen", "Agendapunt Post")
        "motie",
        "amendement",
        "agendapunt",
        "besluit",
        "voorstel",
        "memo",
        "notitie",
        "onderwerp",
        "betreft",
        "zaak",
        "dossier",
        "project",
        "programma",
        "team",
        "dag",
        "graag",
        "beste",
        "hallo",
        "hi",
        "collega",
        # Administrative roles (WOO / klacht / bezwaar context)
        "klaagster",
        "klager",
        "aanvrager",
        "aanvraagster",
        "verzoeker",
        "verzoekster",
        "bewoner",
        "bewoonster",
        "inspreker",
        "inspreekster",
        "betrokkene",
        "belanghebbende",
        "bezwaarmaker",
        "indiener",
        "melder",
        "meldster",
        # Legal-procedure roles (criminal/civil)
        "verdachte",
        "gedaagde",
        "eiser",
        "eiseres",
        "appellant",
        "gedupeerde",
        "slachtoffer",
        "benadeelde",
        "getuige",
    }
)


#: The column headers of a Dutch e-form, printed as one row above the
#: row that holds the values ("Voorletters Tussenvoegsels Achternaam").
#: A label whose value is another label is a header row, not a filled
#: field. Lives here rather than in `_anchor_rules` because the
#: salutation rule needs the same refusal: "Aanhef Mevr." followed on
#: the next line by "Straat en huisnummer" handed it "Straat" as a
#: surname (#98).
FORM_FIELD_WORDS: frozenset[str] = frozenset(
    {
        "naam",
        "namen",
        "achternaam",
        "voornaam",
        "voornamen",
        "voorletters",
        "initialen",
        "tussenvoegsel",
        "tussenvoegsels",
        "aanhef",
        "contactpersoon",
        "aanvrager",
        "ondertekenaar",
        "behandeld",
        "ingediend",
        "opgesteld",
        "ondertekend",
        "straat",
        "huisnummer",
        "toevoeging",
        "postcode",
        "plaats",
        "gegevens",
    }
)


def is_form_field_row(name_text: str) -> bool:
    """True when the "value" is made of field labels — a header row."""
    return any(tok.lower().strip(".,;:") in FORM_FIELD_WORDS for tok in name_text.split())


def is_role_or_section_word(token: str) -> bool:
    """True when `token` is a function title, role noun or section heading.

    The anchor rules (#97) use this to refuse a candidate whose *first*
    token is not a name at all — "Behandeld door Team Ruimte" must not
    yield "Ruimte", and "Hoogachtend, / De Staatssecretaris" must not
    yield a person. Trailing occurrences are handled by
    `trim_trailing_titles`, which truncates rather than refuses.
    """
    normalized = token.lower().strip(".,;:()")
    if not normalized:
        return False
    vocab = _get_trailing_titles()
    return normalized in vocab.words or normalized in _LEADING_STRIP_WORDS


def trim_trailing_titles(text: str, start_char: int, end_char: int) -> tuple[str, int, int]:
    """Strip trailing job titles and section headings from a person span.

    Deduce trained on medical records tends to greedily extend person
    spans to absorb the next capitalized word(s), yielding entities
    like ``"Marieke de Vries Beleidsmedewerker Sociaal Domein"`` or
    ``"S. van Dijk Betreft"``.

    Strategy:
      1. Try stripping multi-word title phrases from the end.
      2. Try stripping single known title words from the end.
      3. If end-stripping didn't help, scan for a known title word
         *inside* the span and truncate everything from that word onward
         (handles "A.B. Bakker Wethouder Ruimtelijke Ordening").
      4. Strip leading section heading words (Rondvraag, etc.).

    Only called for ``persoon`` entities — other types are unaffected.
    """
    vocab = _get_trailing_titles()

    original_text = text

    # Pass 1: strip known words/phrases from the end
    changed = True
    while changed:
        changed = False
        lower = text.lower().rstrip()

        # Multi-word phrases first (longest match)
        for phrase in vocab.phrases:
            if lower.endswith(phrase):
                before = text[: len(text) - len(phrase)].rstrip()
                if before:
                    removed_len = len(text) - len(before)
                    text = before
                    end_char -= removed_len
                    changed = True
                    break

        if changed:
            continue

        # Single trailing word
        tokens = text.rsplit(None, 1)
        if len(tokens) == 2:
            last_word = tokens[1].lower().rstrip(".,;:()")
            if last_word in vocab.words:
                before = tokens[0].rstrip()
                if before:
                    removed_len = len(text) - len(before)
                    text = before
                    end_char -= removed_len
                    changed = True

    # Pass 2: if end-stripping didn't change anything, scan for a known
    # title word inside the span and truncate from there. This catches
    # "A.B. Bakker Wethouder Ruimtelijke Ordening" where "Ordening" by
    # itself isn't a title word, but "Wethouder" is.
    if text == original_text:
        words = text.split()
        # Skip the first 2 words (minimum name) to avoid false cuts on
        # names that accidentally overlap a title word.
        for i in range(2, len(words)):
            if words[i].lower().rstrip(".,;:()") in vocab.words:
                before = " ".join(words[:i]).rstrip()
                if before:
                    removed_len = len(text) - len(before)
                    text = before
                    end_char -= removed_len
                break
            # Also check multi-word phrases starting at this position
            suffix_lower = " ".join(w.lower() for w in words[i:])
            for phrase in vocab.phrases:
                if suffix_lower.startswith(phrase):
                    before = " ".join(words[:i]).rstrip()
                    if before:
                        removed_len = len(text) - len(before)
                        text = before
                        end_char -= removed_len
                    break
            else:
                continue
            break

    # Pass 3: strip leading non-name words — section headings and
    # greeting words that Deduce absorbs into the span.
    # "Dag Yvonne" → "Yvonne", "Graag Dirkse" → "Dirkse",
    # "Rondvraag Raadslid X" → "Raadslid X"
    first_space = text.find(" ")
    if first_space > 0:
        first_word = text[:first_space].lower().strip(".,;:()")
        if first_word in _LEADING_STRIP_WORDS:
            after = text[first_space:].lstrip()
            start_char = end_char - len(after)
            text = after

    # Pass 3b: a function title *opening* the name. Pass 2 only looks
    # from the third token on, so "Voorzitter Jansen" and "Mevrouw
    # Wethouder Jansen" kept a bar that is wider than the name (#98).
    # The salutation is stepped over rather than dropped: it is what the
    # corroboration gate reads as evidence for a bare surname.
    text, start_char, end_char = _strip_leading_titles(text, start_char, end_char, vocab)

    # Pass 4: nothing but a function title left — "Wethouder",
    # "Voorzitter", or a salutation + title ("De heer Voorzitter",
    # "Mevrouw De Wethouder"). Deduce emits the latter because "Heer"
    # is a CBS surname and the name lists then wave it through; the
    # title-prefix rule emits the former when a salutation precedes a
    # role instead of a name. Return an empty span so the caller drops
    # the detection.
    if _is_only_title(text, vocab):
        return "", start_char, start_char

    return text, start_char, end_char


# Salutations that may open a Deduce person span. Matched at the start
# of the (already trimmed) span, case-insensitively.
_SALUTATION_PREFIX = re.compile(
    r"^(?:de\s+heer|de\s+heer/mevrouw|mevrouw|meneer|mijnheer|"
    r"dhr\.?|mevr\.?|mw\.?|heer)(?:\s+|$)",
    re.IGNORECASE,
)


def _strip_leading_titles(
    text: str,
    start_char: int,
    end_char: int,
    vocab: _TrailingTitleVocab,
) -> tuple[str, int, int]:
    """Cut a function title — and any salutation before it — off the front.

    "Voorzitter Jansen" → "Jansen", "Mevrouw Wethouder Jansen" →
    "Jansen". The card was right in both cases; the black bar was two
    words too wide, and a title is not personal data. The whole prefix
    goes so the span stays one contiguous run of characters, which is
    what the bbox resolver needs.

    The last token is never taken: a span that is *only* a title is
    pass 4's business and it has to see the span whole.
    """
    spans = [m.span() for m in re.finditer(r"\S+", text)]
    if len(spans) < 2:
        return text, start_char, end_char

    salutation = _SALUTATION_PREFIX.match(text)
    index = len(text[: salutation.end()].split()) if salutation else 0
    cut = index
    while cut < len(spans) - 1:
        token = text[spans[cut][0] : spans[cut][1]].lower().strip(".,;:()")
        if token not in vocab.words:
            break
        cut += 1
    if cut == index:
        return text, start_char, end_char
    # What remains has to stand on its own, and a bare surname does not:
    # the corroboration gate reads the salutation or the title in front
    # of it as the evidence that "Jansen" is a person. So "Voorzitter
    # Jansen" and "Mevrouw Wethouder Jansen" keep their prefix, wide bar
    # and all, rather than lose the card.
    if len(spans) - cut < 2:
        return text, start_char, end_char

    offset = spans[cut][0]
    return text[offset:], start_char + offset, end_char


def _is_only_title(text: str, vocab: _TrailingTitleVocab) -> bool:
    """True when `text` is (salutation +) (article +) a function title, nothing else."""
    rest = text.strip()
    m = _SALUTATION_PREFIX.match(rest)
    had_salutation = m is not None
    if m is not None:
        rest = rest[m.end() :].strip()
    # Optional article: "Mevrouw De Voorzitter" (pass 1 may already have
    # stripped the title, leaving "Mevrouw De").
    rest = re.sub(r"^(?:de|het)(?:\s+|$)", "", rest, flags=re.IGNORECASE).strip()
    if not rest:
        return had_salutation
    normalized = " ".join(rest.lower().split()).strip(".,;:()")
    return normalized in vocab.words or normalized in vocab.phrases
