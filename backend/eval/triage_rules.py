"""The pattern catalogue: what a detection error most likely *is*.

A report tells you that 53 hard false positives happened and that 22 planted
values were missed. It does not tell you they are eleven problems, not 75, and
it does not tell you which brief in `docs/plans/` each one belongs to. Doing
that by hand costs a reading session per run, which is exactly the tax that
stops an evaluation loop from being run.

So: one small predicate per known failure shape, each carrying the brief it
belongs to. A rule is five lines. Adding one when three unclassified items
share a cause is part of the same PR that acts on them — see the
`detectie-eval` skill.

These are *hypotheses*, not verdicts. `triage.py` prints examples with every
count so a wrong guess is visible immediately, and an item that matches no
rule lands in `unclassified` rather than being forced into the nearest bucket.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parents[1] / "app/data"


# --------------------------------------------------------------------------
# The item under triage
# --------------------------------------------------------------------------


@dataclass
class TriageItem:
    """One report row, flattened so a rule never has to know where it came from."""

    kind: str  # fp | fn
    doc: str
    page: int | None
    text: str  # entity_text (fp) or planted value (fn)
    entity_type: str = ""  # pipeline type (fp)
    truth_type: str = ""  # planted type (fn)
    source: str = ""
    review_status: str = ""
    reasoning: str = ""
    context: str = ""
    slot_context: str = ""
    outcome: str = ""  # missed | partial | rejected (fn)
    uncovered: str = ""
    in_wordlist: bool | None = None
    lenient: bool = False
    severity: str = ""  # hard | soft (fp)
    #: Facts about the whole document, precomputed by `triage.py`: how often
    #: each normalised text occurs, and which texts came back without a bbox.
    doc_facts: dict[str, Any] = field(default_factory=dict)

    @property
    def before(self) -> str:
        """The part of the context that precedes the span, or all of it."""
        idx = self.context.find(self.text)
        return self.context[:idx] if idx > 0 else self.context

    @property
    def after(self) -> str:
        idx = self.context.find(self.text)
        return self.context[idx + len(self.text) :] if idx >= 0 else ""


@dataclass(frozen=True)
class TriageRule:
    name: str
    applies_to: str  # fp | fn
    check: Callable[[TriageItem], bool]
    brief: str
    note: str = ""


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

ORG_KEYWORDS = (
    "provincie",
    "gemeente",
    "waterschap",
    "ministerie",
    "rijkswaterstaat",
    "omgevingsdienst",
    "rud ",
    "ggd",
    "politie",
    "brandweer",
    "veiligheidsregio",
    "ombudsman",
    "stichting",
    "vereniging",
    "college",
    "gedeputeerde",
    "provinciale staten",
    "raad",
    "bureau",
    "kantoor",
    "advocaten",
)

LEGAL_FORMS = ("b.v.", "n.v.", "v.o.f.", " bv", " nv", "gmbh", " ltd", "vof")

STREET_SUFFIXES = (
    "straat",
    "weg",
    "laan",
    "plein",
    "kade",
    "dijk",
    "gracht",
    "singel",
    "steeg",
    "dreef",
    "allee",
    "boulevard",
    "plantsoen",
)

#: Local parts that belong to a desk, not a person. `bezwaar*` and friends are
#: prefixes, so `bezwaarschriften@` matches too.
FUNCTIONAL_LOCAL_PREFIXES = (
    "post",
    "info",
    "woo",
    "wob",
    "vth",
    "jz",
    "avg",
    "bezwaar",
    "secretariaat",
    "receptie",
    "contact",
    "noreply",
    "no-reply",
    "communicatie",
    "griffie",
    "pers",
    "klacht",
    "meldpunt",
    "subsidie",
    "vergunning",
    "handhaving",
    "webmaster",
    "helpdesk",
    "servicedesk",
    "balie",
    "gemeente",
    "provincie",
    "omgevingsloket",
)

_FALLBACK_PLACES = frozenset(
    {
        "assen",
        "emmen",
        "norg",
        "meppel",
        "hoogeveen",
        "coevorden",
        "roden",
        "gieten",
        "beilen",
        "zuidlaren",
        "stadskanaal",
        "den haag",
        "groningen",
    }
)


@lru_cache(maxsize=1)
def place_names() -> frozenset[str]:
    """Dutch place names, from the gemeente index when it is readable.

    `gemeenten.csv` carries both the gemeente name and the places inside it,
    which is a far better list than anything worth hand-maintaining here. It
    is a data file, not an API, so a parse failure falls back rather than
    taking the whole triage down with it.
    """
    path = _DATA / "gemeenten.csv"
    if not path.is_file():
        return _FALLBACK_PLACES
    names: set[str] = set(_FALLBACK_PLACES)
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                short = (row.get("Afkorting") or "").strip().lower()
                if short:
                    names.add(short)
                for town in (row.get("Bevat plaatsen") or "").split(","):
                    town = town.strip().lower()
                    if len(town) > 2:
                        names.add(town)
    except (OSError, csv.Error):  # pragma: no cover - data problem, not logic
        return _FALLBACK_PLACES
    return frozenset(names)


# --------------------------------------------------------------------------
# Small predicates shared by several rules
# --------------------------------------------------------------------------


def _has(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def _window_before(item: TriageItem, chars: int) -> str:
    return item.before[-chars:].lower()


def _is_person(item: TriageItem) -> bool:
    return item.entity_type == "persoon"


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", text.strip()) if t]


_ENUMERATION = re.compile(r"^[A-Z]\.\s?\S+$")
_YEAR_AFTER = re.compile(r"^[^A-Za-z]{0,3}(?:,\s*(?:19|20)\d\d[.,]|\((?:19|20)\d\d\))")
_MANDATE = re.compile(r"namens\s+deze[nz]?,?\s*$", re.IGNORECASE)
_REFERENCE_LABEL = re.compile(r"(ons\s+kenmerk|uw\s+kenmerk|kenmerk|zaaknummer|zaaknr)\W*$", re.I)
_CLOSING = re.compile(r"^\s*(hoogachtend|met\s+vriendelijke\s+groet|met\s+vriendelijk|groet)", re.I)
_ANCHOR_LABEL = re.compile(
    r"(naam|achternaam|voornaam|contactpersoon|behandeld\s+door|behandelaar|van|aan|t\.a\.v\.)"
    r"\s*[:.]?\s*$",
    re.IGNORECASE,
)
_INSTITUTIONAL = re.compile(r"(postbus|bezoekadres|postadres|correspondentieadres)", re.IGNORECASE)
_OBJECT_CUE = re.compile(
    r"(locatie|inrichting|perceel|kadastraal|gelegen\s+aan|ter\s+plaatse\s+van|"
    r"woo-?verzoek|wob-?verzoek|onderwerp|betreft|zijnde|p/a)",
    re.IGNORECASE,
)
_BIRTHDATE_CUE = re.compile(r"(geboren|geboortedatum|geb\.)", re.IGNORECASE)
#: `2010 DO/…` in a permit table looks exactly like a postcode to the regex.
_YEAR_AS_POSTCODE = re.compile(r"^(19|20)\d\d\s?[A-Z]{2}$")

#: Causes found by running the triage over a real report and reading what fell
#: through. They have no brief yet: the first session to act on one decides
#: where it belongs and replaces this marker.
UNASSIGNED = "(nog te bepalen)"
_GOVERNING_BODY = re.compile(
    r"(gedeputeerde|provinciale\s+staten|burgemeester\s+en\s+wethouders|college|"
    r"dagelijks\s+bestuur|algemeen\s+bestuur)",
    re.IGNORECASE,
)


def _functional_mailbox(text: str) -> bool:
    local = text.split("@")[0].strip().lower()
    local = re.sub(r"[^a-z0-9.\-_]", "", local)
    return any(local.startswith(p) for p in FUNCTIONAL_LOCAL_PREFIXES)


def _street_like(text: str) -> bool:
    tokens = _tokens(text)
    if not tokens:
        return False
    last = tokens[-1].lower().rstrip(".,")
    # A house number trailing the street ("Maasdijk 191") still reads as a
    # street to the person detector, so look one token further back.
    if last.isdigit() and len(tokens) > 1:
        last = tokens[-2].lower().rstrip(".,")
    return any(last.endswith(s) for s in STREET_SUFFIXES) and len(last) > max(
        len(s) for s in STREET_SUFFIXES if last.endswith(s)
    )


def _contains_place(text: str) -> bool:
    if re.search(r"\ste\s+[A-Z]", text):
        return True
    return any(tok.lower().strip(".,") in place_names() for tok in _tokens(text)[1:])


# --------------------------------------------------------------------------
# The catalogue
# --------------------------------------------------------------------------

FP_RULES: tuple[TriageRule, ...] = (
    TriageRule(
        "functional_mailbox",
        "fp",
        lambda i: i.entity_type == "email" and _functional_mailbox(i.text),
        "#96",
        "A desk address, not a person: post@, info@, woo@, bezwaar…@",
    ),
    TriageRule(
        "url_public_site",
        "fp",
        lambda i: i.entity_type == "url",
        "#96",
        "A published website is not personal data",
    ),
    TriageRule(
        "phone_in_letterhead",
        "fp",
        lambda i: (
            i.entity_type == "telefoon"
            and (
                _has(_window_before(i, 80), ORG_KEYWORDS)
                or re.search(
                    r"(postbus|www\.|\bt\b\s*:?\s*$|telefoon)", _window_before(i, 80), re.I
                )
                is not None
                or _functional_mailbox(
                    _window_before(i, 80).split()[-1] if i.before.split() else ""
                )
            )
        ),
        "#96",
        "The organisation's own switchboard, printed on every page",
    ),
    TriageRule(
        "org_postcode",
        "fp",
        lambda i: (
            i.entity_type in {"postcode", "adres"}
            and (
                _has(_window_before(i, 60), ORG_KEYWORDS)
                or _has(_window_before(i, 60), LEGAL_FORMS)
                or "postbus" in _window_before(i, 60)
            )
        ),
        "#96",
        "The sender's own address block",
    ),
    TriageRule(
        "enumeration_letter",
        "fp",
        lambda i: (
            _is_person(i)
            and _ENUMERATION.match(i.text.strip()) is not None
            and (
                i.text.strip().split(".")[-1].strip().isupper()
                or re.match(r"^\s*[a-z0-9]", i.after) is not None
            )
        ),
        "#98",
        "A list marker read as initial + surname: 'a. Verzoek', 'b. Besluit'",
    ),
    TriageRule(
        "street_as_person",
        "fp",
        lambda i: _is_person(i) and _street_like(i.text),
        "#98",
        "A street name ends like a surname",
    ),
    TriageRule(
        "legal_form_in_span",
        "fp",
        lambda i: _is_person(i) and _has(i.text, LEGAL_FORMS),
        "#98",
        "A company, not a person",
    ),
    TriageRule(
        "bibliography_author",
        "fp",
        lambda i: _is_person(i) and _YEAR_AFTER.match(i.after[:40]) is not None,
        "#98",
        "An author in a reference list; the year gives it away",
    ),
    TriageRule(
        "title_scan_over_punct",
        "fp",
        lambda i: (
            _is_person(i)
            and i.source.startswith("rule")
            and re.search(r"[.,]\s+$", i.before[-6:]) is not None
        ),
        "#98",
        "A title match ran past a sentence boundary",
    ),
    TriageRule(
        "place_in_person_span",
        "fp",
        lambda i: _is_person(i) and _contains_place(i.text),
        "#98",
        "A place name swallowed into a person span",
    ),
    TriageRule(
        "signature_block_overreach",
        "fp",
        lambda i: (
            _is_person(i)
            and i.source.startswith("structure")
            and i.review_status == "auto_accepted"
            and (
                any(c.isdigit() for c in i.text)
                or "-" in i.text
                or _street_like(i.text)
                or _has(i.text, ORG_KEYWORDS)
            )
        ),
        "#95",
        "The signature-block heuristic took the whole block",
    ),
    TriageRule(
        "merged_over_line",
        "fp",
        lambda i: (
            i.entity_type in {"persoon", "adres"}
            and len(_tokens(i.text)) >= 3
            and (
                re.search(r"\d{4}\s?[A-Z]{2}", i.text) is not None
                or any(tok.lower().strip(".,") in place_names() for tok in _tokens(i.text)[1:])
            )
        ),
        "#95",
        "One span ran across a line break and merged two fields",
    ),
    TriageRule(
        "object_address",
        "fp",
        lambda i: (
            i.entity_type in {"adres", "postcode"}
            and (
                _OBJECT_CUE.search(_window_before(i, 60)) is not None
                or _has(_window_before(i, 60), LEGAL_FORMS)
            )
        ),
        "#99",
        "The address of the thing the permit is about, not of a person",
    ),
    TriageRule(
        "government_reference",
        "fp",
        lambda i: (
            i.entity_type == "referentie"
            and (
                _REFERENCE_LABEL.search(i.before) is not None or len(re.sub(r"\D", "", i.text)) < 4
            )
        ),
        "#99",
        "A case number the organisation itself printed",
    ),
    TriageRule(
        "mandate_signatory",
        "fp",
        lambda i: _is_person(i) and _MANDATE.search(_window_before(i, 30)) is not None,
        "#99",
        "Signed 'namens dezen' — a policy question, not a detector bug",
    ),
    TriageRule(
        "date_in_prose",
        "fp",
        lambda i: i.entity_type == "datum" and _BIRTHDATE_CUE.search(_window_before(i, 40)) is None,
        UNASSIGNED,
        "A date in running prose. Only a birth date is personal data",
    ),
    TriageRule(
        "year_as_postcode",
        "fp",
        lambda i: (
            i.entity_type == "postcode" and _YEAR_AS_POSTCODE.match(i.text.strip()) is not None
        ),
        UNASSIGNED,
        "'2010 DO' in a permit table matches the postcode regex",
    ),
    TriageRule(
        "repeated_address",
        "fp",
        lambda i: (
            i.entity_type == "adres"
            and i.doc_facts.get("text_counts", {}).get(i.text.lower(), 0) >= 5
        ),
        "#99",
        "The same address on every page: boilerplate, most likely the sender's",
    ),
)


FN_RULES: tuple[TriageRule, ...] = (
    TriageRule(
        "whitelist_surname_only",
        "fn",
        lambda i: i.outcome == "rejected" and "whitelist_gemeente" in i.source,
        "#92",
        "A civil-servant whitelist suppressed a private person with the same name",
    ),
    TriageRule(
        "governing_body_as_title",
        "fn",
        lambda i: (
            i.outcome == "rejected"
            and i.source.startswith("rule")
            and _GOVERNING_BODY.search(i.reasoning) is not None
        ),
        "#94",
        "The public-official rule fired on a body, not on this person",
    ),
    TriageRule(
        "no_bbox",
        "fn",
        lambda i: any(
            t and (t in i.text or i.text in t) for t in i.doc_facts.get("no_bbox_texts", ())
        ),
        "#93",
        "Found, but with no bounding box, so nothing is drawn",
    ),
    TriageRule(
        "anchor_closing",
        "fn",
        lambda i: (
            i.outcome == "missed"
            and (
                _CLOSING.match(i.slot_context) is not None or _CLOSING.search(i.context) is not None
            )
        ),
        "#97",
        "The name under a sign-off has no cue in front of it",
    ),
    TriageRule(
        "anchor_label",
        "fn",
        lambda i: i.outcome == "missed" and _ANCHOR_LABEL.search(i.before) is not None,
        "#97",
        "A labelled field ('Naam:', 'Behandeld door') is not used as an anchor",
    ),
    TriageRule(
        "display_name_before_email",
        "fn",
        lambda i: (
            i.truth_type == "email_met_naam"
            and i.outcome in {"missed", "partial"}
            and bool(re.search(r"[A-Za-z]{2,}", i.uncovered))
        ),
        "#97",
        "'Naam <adres@…>' — the address is found, the display name is not",
    ),
    TriageRule(
        "bare_initials",
        "fn",
        lambda i: i.truth_type == "initialen" and i.outcome == "missed",
        "#97",
        "'R.K.' on its own carries no corroboration",
    ),
    TriageRule(
        "bare_surname_after_greeting",
        "fn",
        lambda i: (
            i.truth_type == "achternaam"
            and i.outcome in {"missed", "partial"}
            and re.search(r"geachte", i.context, re.IGNORECASE) is not None
        ),
        "#97",
        "'Geachte <achternaam>' should be a strong cue (see #90's corroboration)",
    ),
    TriageRule(
        "institutional_label_window",
        "fn",
        lambda i: (
            i.truth_type in {"adres", "postcode", "postcode_plaats"}
            and i.outcome == "missed"
            and _INSTITUTIONAL.search(_window_before(i, 60)) is not None
        ),
        "#95",
        "A private address sitting under an institutional label",
    ),
    TriageRule(
        "off_wordlist_name",
        "fn",
        lambda i: i.outcome == "missed" and i.in_wordlist is False,
        "#97",
        "A name outside Meertens/CBS, with nothing else to go on",
    ),
    TriageRule(
        "tussenvoegsel_only_gap",
        "fn",
        lambda i: i.lenient and i.outcome == "partial",
        "#97",
        "Sanity row: should be 0, leniency promotes these to found",
    ),
    TriageRule(
        "place_only_gap",
        "fn",
        lambda i: i.lenient and i.truth_type == "postcode_plaats" and i.outcome == "partial",
        "#97",
        "Sanity row: should be 0",
    ),
)

ALL_RULES: tuple[TriageRule, ...] = FP_RULES + FN_RULES


def classify(item: TriageItem) -> list[TriageRule]:
    """Every rule that fires on this item, most specific first by catalogue order.

    Returning all of them rather than the first is deliberate: an item that
    matches `street_as_person` *and* `merged_over_line` is telling you
    something a single label would hide.
    """
    rules = FP_RULES if item.kind == "fp" else FN_RULES
    out: list[TriageRule] = []
    for rule in rules:
        try:
            if rule.check(item):
                out.append(rule)
        except Exception:  # pragma: no cover - a bad rule must not kill triage
            continue
    return out
