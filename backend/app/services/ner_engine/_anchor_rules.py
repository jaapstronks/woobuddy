"""Structure-anchored name rule (#97) — names the wordlists cannot vouch for.

Meertens and CBS do not *find* names; they only filter what Deduce
hands over (`_tier2.score_person_candidate`). So a name Deduce does not
know — "Djaimy Pijpker", "Hadžić", "Kwabena Yıldırım", "Okonkwo" —
disappears even when the line it stands on says, in as many words, that
a person is coming. This module reads those anchors.

Four anchor families, all built on the same forward walk as the
salutation rule (#48, `_title_prefix`):

1. **Afsluiting** — a closing on its own line ("Hoogachtend,", "Met
   vriendelijke groet,"); the signer's name is the next non-empty line.
2. **Formulier- en headerlabels** — "Naam:", "Contactpersoon",
   "Behandeld door", "Van:"; the value follows on the same line.
3. **Aanhef** — "Geachte", "Beste", optionally + heer/mevrouw; the
   addressee follows on the same line.
4. **Display-naam vóór een e-mailadres** — the capitals directly before
   ``<voornaam@domein.nl>``.

Doctrine (#90, #96): an anchor is *evidence of a person*, not evidence
enough to redact unseen. Every hit here is emitted at 0.75 with
`source="anchor_rule"`, which reaches the reviewer as `pending`. Where
an anchor hit also sits inside an e-mail header or a signature block,
the structure rules in `pipeline_engine` decide what happens next —
that auto-accept is theirs, not this rule's.

Three guards keep the families from eating the document around them:

- the first token may not be a function title, role noun or section
  heading ("Behandeld door Team Ruimte" is a team, not a Ruimte);
- the span may not contain organisation or legal-form vocabulary
  ("Naam: Oosting Metalen Recycling B.V.");
- the closing family additionally requires the candidate line to be
  *entirely* name — "Met vriendelijke groet, / de Nationale ombudsman,"
  leaves a lowercase word over and is refused.
"""

from __future__ import annotations

import re

from app.services.name_engine import NameLists

from ._name_walk import walk_name
from ._org_context import contains_org_vocabulary
from ._plausibility import _is_plausible_person_name
from ._tier2_trim import is_role_or_section_word, trim_trailing_titles
from ._types import NERDetection

# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

#: A Dutch closing, alone on its line. Longest alternatives first so
#: "met vriendelijke groeten" wins over "groeten". Mirrors
#: `structure_engine._SIGNATURE_TRIGGERS`, but anchored at both ends:
#: here the line has to *be* the closing, because the name we are after
#: is the line below it.
_CLOSING_LINE = re.compile(
    r"^[ \t]*(?:"
    r"met\s+vriendelijke\s+groeten|met\s+vriendelijke\s+groet|"
    r"met\s+hartelijke\s+groet|met\s+de\s+meeste\s+hoogachting|"
    r"vriendelijke\s+groeten|vriendelijke\s+groet|hartelijke\s+groet|"
    r"hoogachtend|groeten|groet"
    r")[ \t]*[,.]?[ \t]*$",
    re.IGNORECASE,
)

#: Form and letterhead labels whose value is a person's name. Matched
#: anywhere on a line — a "Klant / Adviseur" table prints "Naam <value>"
#: mid-line — but only accepted when the label is capitalised or carries
#: a colon, which is what separates the label "Naam" from the noun
#: "naam" in running prose.
_FIELD_LABEL = re.compile(
    r"(?<![\w'])("
    r"achternaam|voornamen|voornaam|voorletters|initialen|contactpersoon|"
    r"behandeld\s+door|ingediend\s+door|opgesteld\s+door|ondertekend\s+door|"
    r"ondertekenaar|aanvrager|naam"
    r")[ \t]*(:)?",
    re.IGNORECASE,
)

#: E-mail header labels. Colon required — bare "Van" and "Aan" are a
#: tussenvoegsel and a preposition far more often than a header.
_MAIL_LABEL = re.compile(
    r"(?<![\w'])(?:van|aan|cc|bcc|t\.a\.v\.)[ \t]*:",
    re.IGNORECASE,
)

#: Salutation openers. "Geachte" and "Beste" are the two that routinely
#: stand in front of a bare surname; the heer/mevrouw variants that
#: `_title_prefix` already anchors on are absorbed here so the walk
#: starts after them.
_SALUTATION_ANCHOR = re.compile(
    r"(?<![\w'])(?:geachte|beste)"
    r"(?:[ \t]+(?:heer\s*/\s*mevrouw|heer\s+en\s+mevrouw|heer|mevrouw|mevr\.|dhr\.))?"
    r"(?=[\s,])",
    re.IGNORECASE,
)

#: The column headers of a Dutch e-form, printed as one row above the
#: row that holds the values ("Voorletters Tussenvoegsels Achternaam").
#: A label whose value is another label is a header row, not a filled
#: field, so the label family refuses a candidate built out of these.
_FORM_FIELD_WORDS = frozenset(
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


#: An e-mail address in angle brackets, the way mail clients print it
#: after a display name.
_BRACKETED_ADDRESS = re.compile(r"<[^<>@\s]+@[^<>\s]+>")

#: What may follow a name on a closing line and still leave the line
#: "entirely name": whitespace and sentence punctuation, nothing else.
_ONLY_PUNCT = re.compile(r"^[\s,.;:!?)\]}]*$")

#: Capitalised tokens a field label or salutation may claim. Two is the
#: canonical Dutch shape — given name plus family name, with particles
#: and initials free — and the cap is what stops "Naam: Djaimy Pijpker
#: Oosting Metalen Recycling B.V." from swallowing the company.
_MAX_INLINE_CAPITALS = 2

#: A closing line is bounded by the line itself, so it can afford a
#: longer name ("Shaniqua Terlouw-Van Rossem").
_MAX_LINE_CAPITALS = 4

_ANCHOR_CONFIDENCE = 0.75


# ---------------------------------------------------------------------------
# Shared candidate handling
# ---------------------------------------------------------------------------


def _lines(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of every line, newline excluded."""
    out: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        out.append((pos, pos + len(line)))
        pos += len(line) + 1
    return out


def _candidate(
    text: str,
    scan_start: int,
    scan_end: int,
    name_lists: NameLists,
    *,
    max_capitalized: int,
    require_full_line: bool = False,
) -> tuple[str, int, int] | None:
    """Walk a name from `scan_start` and vet it, or return None.

    `require_full_line` additionally demands that nothing but
    whitespace and punctuation is left between the end of the name and
    `scan_end`.
    """
    walk = walk_name(text, scan_start, scan_end, name_lists, max_capitalized=max_capitalized)
    if walk is None:
        return None
    # An initials-only run ("B.D.", "M.F.") is a person under an anchor:
    # the anchor supplies the noun the initials stand for.
    if walk.capitalized == 0 and not walk.has_initials:
        return None

    if require_full_line and not _ONLY_PUNCT.match(text[walk.end_char : scan_end]):
        return None

    span_start, span_end = walk.start_char, walk.end_char
    name_text = text[span_start:span_end]

    # The value of a label is a name or it is not a name at all: a role
    # noun in first position means the field holds a team, a function or
    # a heading. Refuse rather than trim — trimming would hand back the
    # word after it ("Team Ruimte" → "Ruimte").
    first_token = name_text.split()[0] if name_text.split() else ""
    if is_role_or_section_word(first_token):
        return None

    name_text, span_start, span_end = trim_trailing_titles(name_text, span_start, span_end)
    if not name_text:
        return None

    # A function title left standing after the trim means the trim ran
    # out of road, not that the span is a name: "De Staatssecretaris van
    # Financiën" loses its last word to the trailing-title pass and then
    # reads as a plausible three-token name. An anchor alone is not
    # enough evidence to redact a job title.
    if any(is_role_or_section_word(tok) for tok in name_text.split()):
        return None

    if contains_org_vocabulary(name_text) is not None:
        return None
    if not _is_plausible_person_name(name_text):
        return None

    return name_text, span_start, span_end


def _detection(name_text: str, start: int, end: int, reasoning: str) -> NERDetection:
    return NERDetection.tier2(
        text=name_text,
        entity_type="persoon",
        confidence=_ANCHOR_CONFIDENCE,
        start_char=start,
        end_char=end,
        reasoning=reasoning,
        source="anchor_rule",
    )


# ---------------------------------------------------------------------------
# The four families
# ---------------------------------------------------------------------------


def _closing_names(
    text: str, lines: list[tuple[int, int]], name_lists: NameLists
) -> list[NERDetection]:
    """1. `Hoogachtend,` / `Met vriendelijke groet,` → the next line."""
    out: list[NERDetection] = []
    for i, (start, end) in enumerate(lines):
        if _CLOSING_LINE.match(text[start:end]) is None:
            continue
        for next_start, next_end in lines[i + 1 : i + 4]:
            if not text[next_start:next_end].strip():
                continue
            found = _candidate(
                text,
                next_start,
                next_end,
                name_lists,
                max_capitalized=_MAX_LINE_CAPITALS,
                require_full_line=True,
            )
            if found is not None:
                out.append(
                    _detection(
                        *found,
                        reasoning=(
                            "Naam staat onder een briefafsluiting — de ondertekenaar van dit stuk."
                        ),
                    )
                )
            break  # Only the first non-empty line under the closing.
    return out


def _is_header_row(name_text: str) -> bool:
    """True when the "value" is made of field labels — a header row."""
    return any(tok.lower().strip(".,;:") in _FORM_FIELD_WORDS for tok in name_text.split())


def _label_names(
    text: str, lines: list[tuple[int, int]], name_lists: NameLists
) -> list[NERDetection]:
    """2. `Naam:` / `Contactpersoon` / `Van:` → the rest of the line."""
    out: list[NERDetection] = []
    for start, end in lines:
        line = text[start:end]

        for m in _FIELD_LABEL.finditer(line):
            label, colon = m.group(1), m.group(2)
            # "de naam van de aanvrager" is prose; "Naam" and "naam:"
            # are fields.
            if not (label[:1].isupper() or colon):
                continue
            found = _candidate(
                text,
                start + m.end(),
                end,
                name_lists,
                max_capitalized=_MAX_INLINE_CAPITALS,
            )
            if found is not None and not _is_header_row(found[0]):
                out.append(
                    _detection(
                        *found,
                        reasoning=(
                            f"Naam staat achter het label “{' '.join(label.split())}” — "
                            "een formulier- of briefhoofdveld voor een persoon."
                        ),
                    )
                )

        for m in _MAIL_LABEL.finditer(line):
            found = _candidate(
                text,
                start + m.end(),
                end,
                name_lists,
                max_capitalized=_MAX_INLINE_CAPITALS,
            )
            if found is not None:
                out.append(
                    _detection(
                        *found,
                        reasoning="Naam staat in een afzender- of geadresseerdenveld.",
                    )
                )
    return out


def _salutation_names(
    text: str, lines: list[tuple[int, int]], name_lists: NameLists
) -> list[NERDetection]:
    """3. `Geachte` / `Beste` (+ heer/mevrouw) → the rest of the line."""
    out: list[NERDetection] = []
    for start, end in lines:
        for m in _SALUTATION_ANCHOR.finditer(text[start:end]):
            found = _candidate(
                text,
                start + m.end(),
                end,
                name_lists,
                max_capitalized=_MAX_INLINE_CAPITALS,
            )
            if found is not None:
                out.append(
                    _detection(
                        *found,
                        reasoning=("Naam staat achter een aanhef — de geadresseerde van dit stuk."),
                    )
                )
    return out


def _mail_display_names(
    text: str, lines: list[tuple[int, int]], name_lists: NameLists
) -> list[NERDetection]:
    """4. The capitals directly before `<adres@domein>`."""
    out: list[NERDetection] = []
    for start, end in lines:
        line = text[start:end]
        for m in _BRACKETED_ADDRESS.finditer(line):
            before = line[: m.start()]
            # A mail client joins addressees with ";" or "," and opens
            # the line with "Van:" / "Aan:"; the display name reaches
            # back no further than the nearest of those.
            # Judge that whole segment, not just the token run the walk
            # takes: "provincie Drenthe <post@drenthe.nl>" opens with a
            # lowercase word the walk cannot start on, and reading only
            # what it *can* start on turns a desk mailbox into a person
            # called Drenthe.
            seg_start = (
                max(
                    before.rfind(";"),
                    before.rfind(","),
                    before.rfind(">"),
                    before.rfind(":"),
                )
                + 1
            )
            if contains_org_vocabulary(before[seg_start:]) is not None:
                continue
            # The display name is the *longest* token run that ends right
            # at the address, so walk from the leftmost boundary that
            # reaches it. Taking the first offset that merely survives
            # vetting would read "Provincie Drenthe <post@…>" as a person
            # called Drenthe once the organisation guard rejected the
            # whole span.
            offsets = [seg_start] + [
                seg_start + t.end() for t in re.finditer(r"\s+", before[seg_start:])
            ]
            scan_end = start + m.start()
            leftmost = next(
                (
                    off
                    for off in offsets
                    if (w := walk_name(text, start + off, scan_end, name_lists)) is not None
                    and _ONLY_PUNCT.match(text[w.end_char : scan_end])
                ),
                None,
            )
            if leftmost is None:
                continue
            found = _candidate(
                text,
                start + leftmost,
                scan_end,
                name_lists,
                max_capitalized=_MAX_LINE_CAPITALS,
                require_full_line=True,
            )
            if found is not None:
                out.append(
                    _detection(
                        *found,
                        reasoning=(
                            "Naam staat direct vóór een e-mailadres — de weergavenaam "
                            "die bij dat adres hoort."
                        ),
                    )
                )
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _drop_contained(detections: list[NERDetection]) -> list[NERDetection]:
    """Keep the outermost span when two anchors claim the same name."""
    if len(detections) < 2:
        return detections
    kept: list[NERDetection] = []
    for d in sorted(detections, key=lambda x: (x.start_char, -(x.end_char - x.start_char))):
        if any(k.start_char <= d.start_char and k.end_char >= d.end_char for k in kept):
            continue
        kept.append(d)
    return kept


def detect_persoon_via_anchors(text: str, name_lists: NameLists) -> list[NERDetection]:
    """Emit Tier 2 `persoon` detections from the four structure anchors.

    Caller is responsible for overlap-deduping against higher-confidence
    Deduce hits — see `detect_tier2`.
    """
    lines = _lines(text)
    hits: list[NERDetection] = []
    hits.extend(_closing_names(text, lines, name_lists))
    hits.extend(_label_names(text, lines, name_lists))
    hits.extend(_salutation_names(text, lines, name_lists))
    hits.extend(_mail_display_names(text, lines, name_lists))
    return _drop_contained(hits)
