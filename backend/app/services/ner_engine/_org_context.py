"""Organisation evidence around a detection — brief #96.

A Tier 1 hit is auto-accepted: it leaves the export without anyone
looking at it. The doctrine from #90 asks for positive evidence that
the value belongs to a *person* before that happens, and four value
types routinely fail that test in Woo documents — the desk mailbox a
decision names for questions, the website it links to, the switchboard
number in the letterhead, and the postcode of the sender's or
applicant's own address block. All four are organisation data that the
publisher deliberately left visible.

None of them is *rejected* here. Rejecting is a decision nobody sees;
these surface as ``pending`` with a Dutch reason that says why this is
not a person, and the reviewer settles it in one click.

The same vocabulary answers a Tier 2 question: a name that follows a
legal form ("Maatschap H.J. Kersten en C.H. Kersten-Ensing") is the
name a business trades under, so the signature-block rule must not
auto-accept it.
"""

from __future__ import annotations

import re

from ._types import LEGAL_FORM_ABBREVIATIONS, ORGANIZATION_KEYWORDS

# ---------------------------------------------------------------------------
# The window: the address block, not a character count
# ---------------------------------------------------------------------------

#: How far back the block may reach. A sender's address block is a run
#: of short lines, so lines are the honest unit here.
_BLOCK_MAX_LINES = 4
#: Hard cap so a single long paragraph line cannot drag half a page in.
_BLOCK_MAX_CHARS = 160

#: A finished sentence ends the block. Written so an abbreviation cannot
#: pass for one: the dot has to follow a lowercase letter or a digit, which
#: "B.V., P. de Keyserstraat 18" — the very context these rules read — does
#: not. `production_text()` strips blank lines out of browser text, so the
#: sentence, not the paragraph gap, is what reliably separates a letterhead
#: from the prose above it.
_SENTENCE_END = re.compile(r"[a-z0-9)][.!?][\"'’”)]?\s")


def block_before(full_text: str, start_char: int) -> str:
    """The address block the span sits in, up to the span itself.

    A raw character window is the wrong shape: a hundred characters of
    running prose a paragraph up ("… en de gemeente Emmen hiervan op de
    hoogte stellen.") would vouch for the postcode of a private citizen
    printed right underneath it. So walk back line by line, take at most
    ``_BLOCK_MAX_LINES`` of them, and cut whatever sits above the last
    sentence that finished before the span.

    This is the same move #95 and #104 made for the address labels: the
    line, not an arbitrary radius, is the unit a letterhead is written in.
    """
    head = full_text[:start_char]
    lines = head.split("\n")
    block = [lines[-1]]
    for line in reversed(lines[:-1]):
        if len(block) > _BLOCK_MAX_LINES or not line.strip():
            break
        block.append(line)
    window = "\n".join(reversed(block))[-_BLOCK_MAX_CHARS:]
    cut = 0
    for m in _SENTENCE_END.finditer(window):
        cut = m.end()
    return window[cut:]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Institution words beyond the shared list. `ORGANIZATION_KEYWORDS` was
#: written to spot an organisation *inside* a Deduce span; a letterhead
#: also names bodies that never show up as a person hit.
_EXTRA_ORG_WORDS = frozenset(
    {
        "waterschap",
        "hoogheemraadschap",
        "rijksdienst",
        "rijkswaterstaat",
        "rijksoverheid",
        "omgevingsdienst",
        "belastingdienst",
        "ombudsman",
        "politie",
        "brandweer",
        "veiligheidsregio",
        "gemeentehuis",
        "provinciehuis",
        "stadhuis",
        "raadhuis",
        "postbus",
        "postadres",
        "bezoekadres",
        "correspondentieadres",
        "kantoor",
        "bestuur",
        "secretariaat",
        "griffie",
        "rechtsvorm",
        "kvk",
        "handelsregister",
    }
)

#: Legal forms. The undotted abbreviations come from
#: `LEGAL_FORM_ABBREVIATIONS` so the person filter (#98) and this
#: letterhead reader agree on what one is; the dotted spellings and the
#: written-out forms are listed here because they are what the documents
#: print, and the boundary lookarounds below take care of the ones that
#: end in a dot.
_LEGAL_FORMS = LEGAL_FORM_ABBREVIATIONS | {
    "b.v.",
    "n.v.",
    "v.o.f.",
    "c.v.",
    "maatschap",
    "coöperatie",
    "cooperatie",
    "eenmanszaak",
    "handelsonderneming",
}


def _alternation(words: frozenset[str]) -> str:
    """Longest-first alternation so "b.v." wins over "bv"."""
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


# `\b` cannot close a token that ends in a dot, and cannot open one that
# follows a dot ("…B.V."), so both edges are spelled out as lookarounds.
_ORG_VOCABULARY = ORGANIZATION_KEYWORDS | _EXTRA_ORG_WORDS | _LEGAL_FORMS
_ORG_EVIDENCE = re.compile(
    r"(?<![\w.])(" + _alternation(_ORG_VOCABULARY) + r")(?!\w)",
    re.IGNORECASE,
)

#: A switchboard announces itself in words as often as in context. The
#: "Behandeld door"-label is the letterhead field a Dutch government
#: letter prints its handling team and general number in.
_SWITCHBOARD_PHRASE = re.compile(
    r"(?:algemee?ne?\s+telefoonnummer|algemeen\s+nummer|behandeld\s+door|"
    r"klant\s*contact\s*centrum|contactcentrum|klantcontact|centrale|receptie)",
    re.IGNORECASE,
)


#: A closed postcode line ends an address block. The sender's block
#: closes with "7800 RA Emmen", and what follows — "Aan", the addressee,
#: a citizen's own street — is a new block that the sender's Postbus must
#: not vouch for. Only the postcode rule reads this cut: a letterhead
#: prints its phone numbers *below* its postcode line, so the phone rule
#: still needs the lines above it.
_POSTCODE_LINE_END = re.compile(r"\b\d{4}\s?[A-Z]{2}\b[^\n]*\n")


def contains_org_vocabulary(text: str) -> str | None:
    """The organisation or legal-form word inside `text`, if any.

    Used by the anchor rules (#97) to refuse a candidate name that is
    really a body or a trading name — "Gemeente Emmen" after a closing,
    "Oosting Metalen Recycling B.V." after a `Naam:` label.
    """
    m = _ORG_EVIDENCE.search(text)
    return m.group(1) if m else None


def organisation_evidence(full_text: str, start_char: int) -> str | None:
    """The organisation word that vouches for the block, if any."""
    window = block_before(full_text, start_char)
    cut = 0
    for line_end in _POSTCODE_LINE_END.finditer(window):
        cut = line_end.end()
    m = _ORG_EVIDENCE.search(window[cut:])
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# E-mail — the desk mailbox
# ---------------------------------------------------------------------------

#: Local parts that belong to a desk. Matched at the *start* of the local
#: part so "woo-verzoek@" and "bezwaarenberoepWoo@" come along, but only
#: when what follows is not more letters — otherwise "postma.j@" reads as
#: "post". The terms in `_COMPOUND_MAILBOXES` are exempt from that check:
#: they routinely glue a word on ("bezwaarschriften@", "klachtenteam@").
_FUNCTIONAL_MAILBOXES = frozenset(
    {
        "post",
        "info",
        "woo",
        "wob",
        "foi",
        "vth",
        "jz",
        "avg",
        "privacy",
        "secretariaat",
        "receptie",
        "balie",
        "contact",
        "noreply",
        "no-reply",
        "communicatie",
        "griffie",
        "pers",
        "webmaster",
        "helpdesk",
        "servicedesk",
        "gemeente",
        "provincie",
        "omgevingsloket",
        "bezwaar",
        "klacht",
        "melding",
        "meldpunt",
        "subsidie",
        "vergunning",
        "handhaving",
        "aanvraag",
        "administratie",
        "inkoop",
        "sollicitatie",
        "vacature",
    }
)

#: Terms that routinely glue a word on: "bezwaarschriften@",
#: "klachtenteam@", "informatie@". Kept short on purpose — "pers" would
#: swallow "persoonlijk@" and "woo" would swallow "woonzaken@".
_COMPOUND_MAILBOXES = frozenset(
    {
        "bezwaar",
        "klacht",
        "melding",
        "subsidie",
        "vergunning",
        "handhaving",
        "aanvraag",
        "info",
    }
)


def functional_mailbox_prefix(address: str) -> str | None:
    """The desk term an e-mail address opens with, if it opens with one."""
    local = address.split("@", 1)[0].strip().lower()
    for term in sorted(_FUNCTIONAL_MAILBOXES, key=len, reverse=True):
        if not local.startswith(term):
            continue
        rest = local[len(term) :]
        if not rest or not rest[0].isalpha() or term in _COMPOUND_MAILBOXES:
            return term
    return None


# ---------------------------------------------------------------------------
# URL — a published page is not personal data
# ---------------------------------------------------------------------------

#: The exception: a URL that points at one person's profile page. Those
#: keep the Tier 1 default.
_PROFILE_URL = re.compile(
    r"(?:linkedin\.com/in/|facebook\.com/(?!pages/)|instagram\.com/|"
    r"(?:twitter|x)\.com/|mastodon[^/]*/@|/~[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)


def is_profile_url(url: str) -> bool:
    """True when the URL addresses a single person's own page."""
    return _PROFILE_URL.search(url) is not None


# ---------------------------------------------------------------------------
# Telefoon — the switchboard in the letterhead
# ---------------------------------------------------------------------------

#: A `06`-number is issued to a handset, not to a desk, so it keeps the
#: Tier 1 default whatever surrounds it.
_MOBILE = re.compile(r"^\s*(?:06|(?:\+|00)\s?31\s?\(?0?\)?\s?6)", re.IGNORECASE)


def _is_mobile(number: str) -> bool:
    return _MOBILE.match(number.replace("-", " ")) is not None


def _letterhead_phone_evidence(number: str, full_text: str, start_char: int) -> str | None:
    """Why this phone number reads as an organisation's own line."""
    if _is_mobile(number):
        return None
    window = block_before(full_text, start_char)
    phrase = _SWITCHBOARD_PHRASE.search(window)
    if phrase:
        return phrase.group(0)
    if "www." in window.lower():
        return "www."
    for word in window.split():
        if "@" in word and functional_mailbox_prefix(word) is not None:
            return word.strip("<>(),;")
    m = _ORG_EVIDENCE.search(window)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# The Tier 1 entry point
# ---------------------------------------------------------------------------


def organisation_context_reason(
    entity_type: str,
    text: str,
    full_text: str,
    start_char: int,
) -> str | None:
    """A Dutch reason why this Tier 1 hit is organisation data, or None.

    Returning a reason means "do not auto-redact this, ask the
    reviewer" — never "drop it". The wording says what the evidence was,
    so the reviewer can disagree with it in one click.
    """
    if entity_type == "email":
        term = functional_mailbox_prefix(text)
        if term is not None:
            return (
                f"Functioneel e-mailadres van een organisatie ({term}@) — "
                "hoort bij een balie of afdeling, niet bij een persoon."
            )
        return None

    if entity_type == "url":
        if is_profile_url(text):
            return None
        return "Gepubliceerde webpagina — een website is geen persoonsgegeven."

    if entity_type == "telefoon":
        evidence = _letterhead_phone_evidence(text, full_text, start_char)
        if evidence is not None:
            return (
                f"Telefoonnummer in het briefhoofd van een organisatie ({evidence}) — "
                "geen persoonlijk nummer."
            )
        return None

    if entity_type == "postcode":
        evidence = organisation_evidence(full_text, start_char)
        if evidence is not None:
            return (
                f"Postcode in het adresblok van een organisatie ({evidence}) — "
                "geen woonadres van een persoon."
            )
        return None

    return None


# ---------------------------------------------------------------------------
# Tier 2 — a name that follows a legal form
# ---------------------------------------------------------------------------

#: "Maatschap H.J. Kersten en C.H. Kersten-Ensing": everything between
#: the legal form and the span is initials, capitalised name parts, and
#: the connectors that join two partners. Anything else — a verb, a
#: lowercase word, a line break — ends the trading name. The line break
#: matters: "Delphy BV\nJan de Vries" is a company and the person who
#: signs for it, and that person keeps the signature-block default.
_LEGAL_FORM_LEAD = re.compile(
    r"(?<![\w.])(?P<form>(?i:" + _alternation(_LEGAL_FORMS) + r"))"
    r"(?:[ \t]+(?:en|&|\+|[A-ZÀ-Ÿ][\wÀ-ÿ'’-]*|(?:[A-Z]\.){1,4}))*"
    r"[ \t,-]*\Z"
)
_LEGAL_FORM_LEAD_WINDOW_CHARS = 80


def legal_form_lead(full_text: str, start_char: int) -> str | None:
    """The legal form this span trades under, if it directly follows one.

    A permit is addressed to "Maatschap H.J. Kersten en C.H.
    Kersten-Ensing"; the partners' names are the name of the business,
    which is why the publisher left them visible. The structure rules
    would otherwise read the block as a signature and auto-redact them.
    """
    ctx_start = max(0, start_char - _LEGAL_FORM_LEAD_WINDOW_CHARS)
    m = _LEGAL_FORM_LEAD.search(full_text[ctx_start:start_char])
    return m.group("form") if m else None
