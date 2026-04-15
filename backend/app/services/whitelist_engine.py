"""Whitelist engine — suppress false positives on public municipal data.

Two CSV sources (committed under ``backend/app/data/``):

- ``gemeenten.csv`` — all 342+ Dutch municipalities with their Bezoekadres,
  Postadres and Woo-Adres records, general phone, general e-mail and
  public website. Addresses of a municipality are *public* information
  and should never be redacted no matter which document they appear in.
- ``medewerkers_gemeenten.csv`` — per-municipality list of raadsleden,
  burgemeesters, wethouders, Woo-contactpersonen and related public
  roles. These people are public officials in the bearer-of-office sense
  and, per CLAUDE.md, should not be redacted *when the document is about
  their municipality*.

The engine exposes three whitelisting decisions:

1. **Address whitelisting** (global, no context gating). Postcodes,
   street+number, general municipal phone numbers, info@-emails and
   municipal websites match everywhere — a postcode is still a postcode
   whether or not the document mentions its city. Applied to all
   ``postcode``, ``adres``, ``telefoon``, ``email`` and ``url``
   detections before they reach the review list.

2. **Postbus-context postcode suppression** (local context). A postcode
   immediately preceded by ``Postbus <nummer>`` is a PO-box address and
   therefore organisational, never personal. Only applied to ``postcode``
   detections and only when the caller passes the surrounding document
   text so the engine can inspect the window before the span.

3. **Public-official whitelisting** (context gated). A person matches
   only if their municipality name appears somewhere in the same
   document's full text (``find_active_gemeenten``). For common Dutch
   surnames (``_COMMON_SURNAMES``) the match additionally requires the
   detection's visible initials to prefix-match the CSV's initials —
   otherwise a raadslid whose name happens to collide with a private
   citizen in an unrelated document would be un-redacted by accident.

Both CSVs are loaded once at app startup via ``init_whitelist_index``
and cached in the module (``get_whitelist_index``) so tests and lazy
paths work without threading ``app.state`` through every call site. The
files will go stale — new raadsleden are elected, municipalities merge
— so the process for refreshing them is "replace the CSV and restart
the backend." That cadence is explicit and intentional; there is no
auto-update path.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_GEMEENTEN_FILE = _DATA_DIR / "gemeenten.csv"
_MEDEWERKERS_FILE = _DATA_DIR / "medewerkers_gemeenten.csv"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# A small, deliberately curated set of very common Dutch surnames. When a
# detection's surname is in this set, the whitelist refuses to fire unless
# the document *also* shows initials that prefix-match the official's
# initials. The goal is to keep "Jan Jansen (private citizen)" from being
# accidentally un-redacted in a Utrecht document just because some
# "Mw. A. Jansen" happens to be on the Utrecht raadsleden list.
#
# The list is intentionally conservative (~80 entries): adding too many
# shrinks the whitelist's useful footprint. Source: Dutch census-style
# frequency tables for surnames; order does not matter.
_COMMON_SURNAMES: frozenset[str] = frozenset(
    _s.lower()
    for _s in (
        "de jong",
        "jansen",
        "de vries",
        "van den berg",
        "van dijk",
        "bakker",
        "janssen",
        "visser",
        "smit",
        "meijer",
        "de boer",
        "mulder",
        "de groot",
        "bos",
        "vos",
        "peters",
        "hendriks",
        "van leeuwen",
        "dekker",
        "brouwer",
        "de wit",
        "dijkstra",
        "smits",
        "de graaf",
        "van der meer",
        "van der linden",
        "kok",
        "jacobs",
        "de haan",
        "vermeulen",
        "van den broek",
        "de bruijn",
        "de bruin",
        "van der velde",
        "willems",
        "prins",
        "huisman",
        "peeters",
        "kuijpers",
        "van vliet",
        "van de ven",
        "timmermans",
        "groen",
        "de jonge",
        "schouten",
        "koster",
        "bosch",
        "van den heuvel",
        "van der veen",
        "blom",
        "wolters",
        "maas",
        "verhoeven",
        "van der wal",
        "koning",
        "van der laan",
        "bosma",
        "peeters",
        "martens",
        "hoekstra",
        "kuiper",
        "goedhart",
        "molenaar",
        "vos",
        "post",
        "kramer",
        "van beek",
        "scholten",
        "van den bosch",
        "bosman",
        "gerritsen",
        "hermans",
        "veenstra",
        "koopman",
        "van der horst",
        "verbeek",
        "bouwman",
        "de lange",
        "van dam",
        "van der meulen",
        "dijkman",
        "van der schaaf",
    )
)

# Honorifics + sub-titles stripped from CSV names when parsing. Lowercased
# for comparison. Multi-word honorifics ("de heer", "de heer mr.") are
# handled by iterative prefix stripping in ``_parse_medewerker_name``.
_HONORIFIC_TOKENS: frozenset[str] = frozenset(
    {
        "dhr",
        "dhr.",
        "mw",
        "mw.",
        "mevr",
        "mevr.",
        "mevrouw",
        "meneer",
        "heer",
        "mr",
        "mr.",
        "drs",
        "drs.",
        "dr",
        "dr.",
        "prof",
        "prof.",
        "ir",
        "ir.",
        "ing",
        "ing.",
    }
)

# A token is an "initial" if it is a single uppercase letter optionally
# followed by more single-letter groups, each with a trailing period.
# Matches "A.", "A.B.", "W.M.J.", but not "Jan" or "Wm".
_INITIAL_RE = re.compile(r"^[A-Z](?:\.[A-Z])*\.$")

# Extract *just* the initial letters from an initial-ish token. "A.B." → "ab".
_INITIAL_LETTERS_RE = re.compile(r"[A-Z]")

# Parenthetical first names ("dhr. (Arjan) Lindeboom") — dropped during
# parsing; we do not try to match full first names.
_PAREN_RE = re.compile(r"\([^)]*\)")


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _nfkd_lower(text: str) -> str:
    """Lowercase + strip diacritics. Same normalization the name engine
    uses so matches survive 'Gülnur' ↔ 'gulnur', 'Adrián' ↔ 'adrian'.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _normalize_phrase(text: str) -> str:
    """Collapse whitespace + strip diacritics + lowercase — for the
    matching target of a multi-word name, address or alias.
    """
    return " ".join(_nfkd_lower(text).split()).strip()


def _strip_bbox_markers(text: str) -> str:
    """Remove characters that have no business being inside a name or
    address match. Parentheses, brackets, and most sentence punctuation
    are peeled off; hyphens and apostrophes stay because they appear in
    real names and street names ("'s-Hertogenbosch", "Martens-Schuitema").
    """
    return re.sub(r"[,;:!?()\[\]\"]", " ", text)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublicOfficial:
    """A named public office-holder tied to a single municipality."""

    gm_code: str  # e.g. "gm1680" — the OWMS/TOOi gemeente identifier
    surname_normalized: str  # includes tussenvoegsels, e.g. "van den oever"
    initials: str  # normalized initial letters, e.g. "hh", "mgw"
    functie: str  # raw functie string, e.g. "Raadslid"
    display_name: str  # original CSV name, kept for logging/UI


@dataclass(frozen=True)
class Municipality:
    """A municipality with its aliases and public contact data."""

    gm_code: str
    official_name: str  # "Gemeente 's-Hertogenbosch"
    short_name: str  # "'s-Hertogenbosch"
    aliases: tuple[str, ...]  # normalized, lowercase, diacritic-stripped


@dataclass(frozen=True)
class WhitelistIndex:
    """Everything the whitelist engine needs for a single analyze call.

    Built once at app startup. Instances are immutable; the CSVs are
    expected to be refreshed out-of-band by replacing the files and
    restarting the backend.
    """

    # Municipality lookups.
    municipalities: tuple[Municipality, ...]
    alias_patterns: tuple[tuple[re.Pattern[str], str], ...]  # (pattern, gm_code)

    # Per-gm_code official lists (tuple so the dataclass stays hashable-ish
    # and tests can compare them directly).
    officials_by_gm: dict[str, tuple[PublicOfficial, ...]] = field(default_factory=dict)

    # Global address whitelists (not context-gated — all municipal
    # contact data is public). All entries are normalized via
    # ``_normalize_phrase``.
    postcodes: frozenset[str] = frozenset()
    addresses: frozenset[str] = frozenset()  # "raadhuisplein 1"
    woonplaatsen: frozenset[str] = frozenset()
    emails: frozenset[str] = frozenset()
    phones: frozenset[str] = frozenset()  # normalized digits-only
    websites: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _parse_addressen_field(raw: str) -> list[dict[str, str]]:
    """Parse the packed ``Adressen`` column from ``gemeenten.csv``.

    The source format is a semicolon-separated list of address records,
    each record being a comma-separated list of ``key: value`` pairs:

        adresType: Bezoekadres, openbareRuimte: Spiekersteeg, ...;
        adresType: Postadres, postbus: 93, postcode: 9460 AB, ...

    A handful of values contain literal commas (e.g. attention lines).
    We accept that as tolerable noise — the downstream consumers only
    care about ``postcode``, ``openbareRuimte``, ``huisnummer`` and
    ``woonplaats``, none of which embed commas in real data.
    """
    records: list[dict[str, str]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        record: dict[str, str] = {}
        for pair in chunk.split(","):
            if ":" not in pair:
                continue
            key, _, value = pair.partition(":")
            record[key.strip()] = value.strip()
        if record:
            records.append(record)
    return records


def _first_value(field_value: str) -> str:
    """Pull the first value from a ``value, label: algemeen`` field.

    Phones, e-mails and websites in ``gemeenten.csv`` are stored as
    comma-separated tuples. Real usage only cares about the value; the
    label metadata is not whitelisted.
    """
    return field_value.split(",", 1)[0].strip()


def _expand_municipality_aliases(official: str, afkorting: str) -> tuple[str, ...]:
    """Build the ordered alias set used to recognise a gemeente in text.

    The strongest alias is ``"gemeente X"`` — unambiguous and always
    matched. The bare ``X`` form is also added when long enough to stay
    low-collision. Shorter names ("Bergen", "Vaals") are deliberately
    skipped for bare matching to reduce false positives; the
    ``"gemeente X"`` form still catches them.
    """
    aliases: list[str] = []
    seen: set[str] = set()

    def add(alias: str) -> None:
        norm = _normalize_phrase(alias)
        if norm and norm not in seen:
            seen.add(norm)
            aliases.append(norm)

    if official:
        add(official)
        if official.lower().startswith("gemeente "):
            add(official[len("gemeente ") :])
        else:
            add(f"Gemeente {official}")

    if afkorting:
        afk_clean = re.sub(r"\s*\([^)]*\)", "", afkorting).strip()
        add(f"Gemeente {afk_clean}")
        # Bare afkorting only if distinctive (>= 5 chars, no spaces makes
        # it a single-token name). "Bergen" and "Utrecht" both qualify;
        # "Vaals", "Epe", "Ede" stay behind the "gemeente " guard.
        if len(afk_clean) >= 5:
            add(afk_clean)

    return tuple(aliases)


def _compile_alias_patterns(
    municipalities: tuple[Municipality, ...],
) -> tuple[tuple[re.Pattern[str], str], ...]:
    """Pre-compile word-boundary regexes for every alias.

    Patterns are compiled against an NFKD-normalized, lowercase document
    view, which is what ``find_active_gemeenten`` feeds in. Using `\\b`
    is safe against ASCII apostrophes and hyphens — the two cases that
    matter for "'s-hertogenbosch" etc. are handled by stripping bbox
    markers on the document side before matching.
    """
    compiled: list[tuple[re.Pattern[str], str]] = []
    for muni in municipalities:
        for alias in muni.aliases:
            # Escape so punctuation like the apostrophe in 's-hertogenbosch
            # is literal. `\b` anchors guard against substring false hits
            # (e.g. "ede" inside "moede").
            pattern = re.compile(rf"\b{re.escape(alias)}\b")
            compiled.append((pattern, muni.gm_code))
    return tuple(compiled)


def _load_gemeenten_csv(
    path: Path,
) -> tuple[
    tuple[Municipality, ...],
    frozenset[str],  # postcodes
    frozenset[str],  # addresses
    frozenset[str],  # woonplaatsen
    frozenset[str],  # emails
    frozenset[str],  # phones
    frozenset[str],  # websites
]:
    """Parse ``gemeenten.csv`` into municipalities + address whitelists."""
    if not path.exists():
        logger.warning("whitelist_engine.gemeenten_missing", path=str(path))
        return ((), frozenset(), frozenset(), frozenset(), frozenset(), frozenset(), frozenset())

    municipalities: list[Municipality] = []
    postcodes: set[str] = set()
    addresses: set[str] = set()
    woonplaatsen: set[str] = set()
    emails: set[str] = set()
    phones: set[str] = set()
    websites: set[str] = set()

    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";", quotechar='"')
        for row in reader:
            official = (row.get("Officiële naam") or "").strip()
            afkorting = (row.get("Afkorting") or "").strip()
            gm_uri = (row.get("TOOi URI") or "").strip()
            gm_code = gm_uri.rsplit("/", 1)[-1] if gm_uri else official.lower()

            aliases = _expand_municipality_aliases(official, afkorting)
            if not aliases:
                continue

            if afkorting:
                short = afkorting
            elif official.lower().startswith("gemeente "):
                short = official[len("Gemeente ") :]
            else:
                short = official
            municipalities.append(
                Municipality(
                    gm_code=gm_code,
                    official_name=official,
                    short_name=short,
                    aliases=aliases,
                )
            )

            # Addresses — parse the packed field. The header in the
            # source CSV is the full parenthesised column name, we look
            # it up via a pre-built key fragment to avoid a ~200-char
            # string literal here.
            addressen_raw = ""
            for key, value in row.items():
                if key and key.startswith("Adressen ("):
                    addressen_raw = value or ""
                    break
            for record in _parse_addressen_field(addressen_raw):
                pc = record.get("postcode", "").replace(" ", "").upper()
                if re.fullmatch(r"\d{4}[A-Z]{2}", pc):
                    postcodes.add(pc)
                street = record.get("openbareRuimte", "").strip()
                huisnr = record.get("huisnummer", "").strip()
                if street and huisnr:
                    addresses.add(_normalize_phrase(f"{street} {huisnr}"))
                if street:
                    addresses.add(_normalize_phrase(street))
                plaats = record.get("woonplaats", "").strip()
                if plaats:
                    woonplaatsen.add(_normalize_phrase(plaats))

            # Phones — keep digits only so "(0297) 38 75 75" and
            # "+31 297 387575" both normalize to "0297387575".
            phone_raw = row.get("Telefoonnummers ", "") or ""
            for part in phone_raw.split(";"):
                value = _first_value(part)
                digits = re.sub(r"\D+", "", value)
                if len(digits) >= 7:
                    phones.add(digits)

            # Emails — split on semicolons for multi-label entries.
            email_raw = row.get("E-mail adressen", "") or ""
            for part in email_raw.split(";"):
                value = _first_value(part).lower()
                if "@" in value:
                    emails.add(value)

            # Websites — the landing domain is enough; exact URL match
            # would be too brittle.
            site_raw = row.get("Internetpagina's", "") or ""
            for part in site_raw.split(";"):
                value = _first_value(part).lower().rstrip("/")
                if value.startswith(("http://", "https://")):
                    websites.add(value)

    return (
        tuple(municipalities),
        frozenset(postcodes),
        frozenset(addresses),
        frozenset(woonplaatsen),
        frozenset(emails),
        frozenset(phones),
        frozenset(websites),
    )


def _looks_like_person_row(naam: str) -> bool:
    """Accept only rows whose ``Naam`` looks like an actual person.

    ``medewerkers_gemeenten.csv`` mixes real names ("Dhr. H.H. Erdogan")
    with department labels ("Juridische zaken", "Klantencontactcentrum").
    We accept a row when it contains either a honorific or an initial
    pattern — the two features that are almost always present on a real
    person row and almost never on a functional label. Rows we skip
    simply fall through to the normal detection path, which is safe.
    """
    stripped = naam.strip()
    if not stripped:
        return False
    tokens = stripped.split()
    bare_honorifics = {h.strip(".") for h in _HONORIFIC_TOKENS}
    has_honorific = any(tok.lower().strip(".") in bare_honorifics for tok in tokens)
    has_initial = any(_INITIAL_RE.match(tok) for tok in tokens)
    return has_honorific or has_initial


def _parse_medewerker_name(naam: str) -> tuple[str, str] | None:
    """Split a CSV name into ``(surname_normalized, initial_letters)``.

    Returns None for rows that don't look like persons. The surname
    keeps any tussenvoegsels ("van den Oever" → "van den oever"). The
    initials are compacted to their letters only ("K.J." → "kj").
    """
    if not _looks_like_person_row(naam):
        return None

    # Drop parenthetical first names — we only match on initials anyway.
    cleaned = _PAREN_RE.sub(" ", naam).strip()
    tokens = cleaned.split()

    initial_letters: list[str] = []
    surname_tokens: list[str] = []
    seen_non_honorific = False
    for tok in tokens:
        norm_tok = tok.lower().rstrip(".")
        if not seen_non_honorific and norm_tok in {h.strip(".") for h in _HONORIFIC_TOKENS}:
            continue
        seen_non_honorific = True
        if _INITIAL_RE.match(tok):
            initial_letters.extend(m.group(0) for m in _INITIAL_LETTERS_RE.finditer(tok))
            continue
        # Stray sub-titles ("ing.", "mr.") after the honorific — skip.
        if norm_tok in {h.strip(".") for h in _HONORIFIC_TOKENS}:
            continue
        surname_tokens.append(tok)

    if not surname_tokens:
        return None

    surname_normalized = _normalize_phrase(" ".join(surname_tokens))
    if not surname_normalized:
        return None

    initials_joined = "".join(initial_letters).lower()
    return surname_normalized, initials_joined


def _load_medewerkers_csv(
    path: Path,
    known_gm_codes: set[str],
    official_names_to_gm: dict[str, str],
) -> dict[str, tuple[PublicOfficial, ...]]:
    """Parse ``medewerkers_gemeenten.csv`` into a per-gm officials index.

    Rows whose ``Resource identifier v5.0 organisatie`` cannot be mapped
    to a municipality loaded from ``gemeenten.csv`` are skipped with a
    debug log — they are almost always provincie- or waterschap- rows
    which we don't whitelist here.
    """
    if not path.exists():
        logger.warning("whitelist_engine.medewerkers_missing", path=str(path))
        return {}

    by_gm: dict[str, list[PublicOfficial]] = {}
    skipped_rows = 0

    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";", quotechar='"')
        for row in reader:
            organisatie = (row.get("Organisatie (onderdeel)") or "").strip()
            naam = (row.get("Naam") or "").strip()
            functie = (row.get("Functie") or "").strip()
            gm_uri = (row.get("Resource identifier v5.0 organisatie") or "").strip()

            gm_code = gm_uri.rsplit("/", 1)[-1] if gm_uri else ""
            if gm_code not in known_gm_codes:
                # Fall back to name lookup — some v4 URIs are not v5.
                gm_code = official_names_to_gm.get(_normalize_phrase(organisatie), "")
            if not gm_code:
                skipped_rows += 1
                continue

            parsed = _parse_medewerker_name(naam)
            if parsed is None:
                skipped_rows += 1
                continue
            surname_normalized, initials = parsed

            by_gm.setdefault(gm_code, []).append(
                PublicOfficial(
                    gm_code=gm_code,
                    surname_normalized=surname_normalized,
                    initials=initials,
                    functie=functie,
                    display_name=naam,
                )
            )

    logger.info(
        "whitelist_engine.medewerkers_loaded",
        officials=sum(len(v) for v in by_gm.values()),
        municipalities=len(by_gm),
        skipped=skipped_rows,
    )
    return {gm: tuple(v) for gm, v in by_gm.items()}


def load_whitelist_index() -> WhitelistIndex:
    """Load both CSVs and compile the whitelist index.

    Missing files are tolerated — the engine returns an empty index and
    ``match_*`` helpers return ``None``/``False``, so the pipeline keeps
    behaving as before the whitelist was added.
    """
    (
        municipalities,
        postcodes,
        addresses,
        woonplaatsen,
        emails,
        phones,
        websites,
    ) = _load_gemeenten_csv(_GEMEENTEN_FILE)

    known_codes = {m.gm_code for m in municipalities}
    official_names_to_gm = {_normalize_phrase(m.official_name): m.gm_code for m in municipalities}
    officials_by_gm = _load_medewerkers_csv(_MEDEWERKERS_FILE, known_codes, official_names_to_gm)

    alias_patterns = _compile_alias_patterns(municipalities)

    logger.info(
        "whitelist_engine.index_loaded",
        municipalities=len(municipalities),
        officials=sum(len(v) for v in officials_by_gm.values()),
        postcodes=len(postcodes),
        addresses=len(addresses),
        emails=len(emails),
        phones=len(phones),
    )

    return WhitelistIndex(
        municipalities=municipalities,
        alias_patterns=alias_patterns,
        officials_by_gm=officials_by_gm,
        postcodes=postcodes,
        addresses=addresses,
        woonplaatsen=woonplaatsen,
        emails=emails,
        phones=phones,
        websites=websites,
    )


# Module-level cache so callers (tests, lazy paths) don't have to thread
# `app.state` around. Mirrors ``role_engine._cached_lists``.
_cached_index: WhitelistIndex | None = None


def get_whitelist_index() -> WhitelistIndex:
    """Return the cached index, loading on first use."""
    global _cached_index
    if _cached_index is None:
        _cached_index = load_whitelist_index()
    return _cached_index


def init_whitelist_index() -> WhitelistIndex:
    """Pre-load the index at app startup (called from FastAPI lifespan)."""
    return get_whitelist_index()


def reset_cache() -> None:
    """Drop the cached index — for tests that want to reload."""
    global _cached_index
    _cached_index = None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def find_active_gemeenten(full_text: str, index: WhitelistIndex) -> set[str]:
    """Return the set of gm_codes whose name aliases appear in the text.

    Called once per analyze request. The match is a word-boundary
    substring scan on the NFKD-lowered full text; bbox markers like
    parentheses are stripped so "(gemeente Aalsmeer)" still fires.
    Returns an empty set when no municipality is mentioned — the
    public-officials whitelist then stays inert.
    """
    if not index.alias_patterns:
        return set()
    haystack = _normalize_phrase(_strip_bbox_markers(full_text))
    active: set[str] = set()
    for pattern, gm_code in index.alias_patterns:
        if gm_code in active:
            continue
        if pattern.search(haystack):
            active.add(gm_code)
    return active


@dataclass(frozen=True)
class PersonWhitelistHit:
    """A successful public-official whitelist match."""

    official: PublicOfficial
    municipality_name: str  # "Gemeente Aalsmeer"
    used_initials: bool  # whether the initials-gate actually fired


def _initials_near_span(full_text: str, start_char: int, end_char: int, window: int = 30) -> str:
    """Return any initial-letter prefix present in a window around the span.

    Looks up to ``window`` chars before ``start_char`` (and inside the
    span itself, in case the detection swallowed "H.H. Erdogan" as one
    Deduce span). Returns a compact letters-only string, e.g. "hh", or
    an empty string if no initials are near.
    """
    if start_char < 0 or end_char > len(full_text) or end_char <= start_char:
        return ""
    before_start = max(0, start_char - window)
    before_text = full_text[before_start:start_char]
    span_text = full_text[start_char:end_char]

    # Prefer the *rightmost* run of initials before the span — e.g.
    # "Dhr. H.H. Erdogan" should yield "hh", not the empty prefix that
    # a naive leftmost search of "Dhr." produces.
    initials_letters = ""
    for haystack in (span_text, before_text):
        for m in re.finditer(r"(?:[A-Z]\.){1,4}", haystack):
            initials_letters = "".join(re.findall(r"[A-Z]", m.group(0))).lower()
    return initials_letters


def _detection_surname(text: str) -> str:
    """Isolate the surname portion of a detection string.

    Strips honorifics and initials from the front; normalizes what's
    left. Keeps tussenvoegsels attached ("de heer Van den Oever" →
    "van den oever"). Returns ``""`` when nothing name-like remains.
    """
    cleaned = _PAREN_RE.sub(" ", text or "")
    cleaned = _strip_bbox_markers(cleaned)
    tokens = cleaned.split()
    surname_tokens: list[str] = []
    honorific_bare = {h.strip(".") for h in _HONORIFIC_TOKENS}
    for tok in tokens:
        norm = tok.lower().rstrip(".")
        if norm in honorific_bare:
            continue
        if _INITIAL_RE.match(tok):
            continue
        # Single-letter bare token ("R") — treat as initial fragment.
        if len(tok) == 1 and tok.isalpha():
            continue
        surname_tokens.append(tok)
    return _normalize_phrase(" ".join(surname_tokens))


def _surname_matches(detection_surname: str, official_surname: str) -> bool:
    """True when the detection's surname portion covers the official's.

    Accepts either an exact match or the official's surname appearing as
    a whole-word suffix of the detection (so "de heer van den oever" and
    "van den oever" both match the official "van den oever"). The
    reverse direction (detection shorter than official) is not accepted
    — "oever" alone should not match "van den oever".
    """
    if not detection_surname or not official_surname:
        return False
    if detection_surname == official_surname:
        return True
    det_tokens = detection_surname.split()
    off_tokens = official_surname.split()
    if len(off_tokens) > len(det_tokens):
        return False
    return det_tokens[-len(off_tokens) :] == off_tokens


def match_person_whitelist(
    detection_text: str,
    start_char: int,
    end_char: int,
    full_text: str,
    active_gemeenten: set[str],
    index: WhitelistIndex,
) -> PersonWhitelistHit | None:
    """Decide whether a Tier 2 persoon detection is a known public official.

    Returns a ``PersonWhitelistHit`` when the detection's surname maps
    to a raadslid / wethouder / burgemeester / Woo-contactpersoon of a
    municipality mentioned in ``full_text`` (the ``active_gemeenten``
    set). Common surnames additionally require the detection's visible
    initials to prefix-match the official's — see ``_COMMON_SURNAMES``.
    """
    if not active_gemeenten:
        return None

    surname = _detection_surname(detection_text)
    if not surname:
        return None

    visible_initials = _initials_near_span(full_text, start_char, end_char)
    is_common = surname in _COMMON_SURNAMES

    for gm_code in active_gemeenten:
        officials = index.officials_by_gm.get(gm_code, ())
        for official in officials:
            if not _surname_matches(surname, official.surname_normalized):
                continue

            # Initials gate — common surnames are only whitelisted when
            # the visible initials prefix-match the official's.
            used_initials = False
            if is_common:
                if not visible_initials or not official.initials:
                    continue
                official_prefix = official.initials[: len(visible_initials)]
                visible_prefix = visible_initials[: len(official.initials)]
                if not official.initials.startswith(
                    visible_prefix
                ) and not visible_initials.startswith(official_prefix):
                    continue
                used_initials = True
            elif visible_initials and official.initials:
                # For uncommon surnames we still reject a hard mismatch
                # on explicit initials: "M. Erdogan" should not be
                # whitelisted against "H.H. Erdogan" just because their
                # surnames agree.
                first_visible = visible_initials[:1]
                first_official = official.initials[:1]
                if first_visible and first_official and first_visible != first_official:
                    continue
                used_initials = True

            municipality_name = next(
                (m.official_name for m in index.municipalities if m.gm_code == gm_code),
                gm_code,
            )
            return PersonWhitelistHit(
                official=official,
                municipality_name=municipality_name,
                used_initials=used_initials,
            )

    return None


# "Postbus <nummer>" immediately preceding a postcode indicates an
# organisational PO-box address — structurally never a person's home
# address. We suppress such postcodes from Tier 1 auto-redact even
# though the bare regex in ``ner_engine`` flags them. The window is
# deliberately tight (30 chars) so an unrelated "Postbus" earlier in
# the same sentence cannot leak into a real residential postcode
# later on the line. The anchor ``\Z`` forces the match to butt up
# against the end of the look-behind window, i.e. directly against
# the postcode span.
_POSTBUS_PREFIX_RE = re.compile(r"(?i)\bpostbus\s+\d{1,6}[\s,.;:\-]*\Z")


def is_postbus_context_postcode(
    full_text: str,
    start_char: int,
    window: int = 30,
) -> bool:
    """True when the postcode at ``start_char`` is immediately preceded
    by a ``Postbus <nummer>`` construction within ``window`` characters.

    Used to suppress Tier 1 postcode auto-redaction when the postcode is
    part of an organisational PO-box address. See the module docstring
    for the rationale.
    """
    if not full_text or start_char <= 0:
        return False
    before = full_text[max(0, start_char - window) : start_char]
    return _POSTBUS_PREFIX_RE.search(before) is not None


def match_address_whitelist(
    detection_text: str,
    entity_type: str,
    index: WhitelistIndex,
    full_text: str | None = None,
    start_char: int | None = None,
) -> str | None:
    """Return a Dutch reason string when the detection matches a municipal
    public-address/contact value, or ``None`` when nothing matches.

    The value-based checks (postcode, street, info-email, general phone,
    municipal website) are not context-gated — these values are public
    everywhere regardless of the surrounding document. The *postbus*
    check is context-gated: callers that want it must pass ``full_text``
    and ``start_char`` so the engine can inspect the characters before
    the span. Omitting them preserves the pre-postbus-rule behaviour.
    """
    if not detection_text:
        return None

    text = detection_text.strip()

    if entity_type == "postcode":
        normalized = text.replace(" ", "").upper()
        if normalized in index.postcodes:
            return "Postcode van een gemeentelijk adres — openbare informatie."
        if (
            full_text is not None
            and start_char is not None
            and is_postbus_context_postcode(full_text, start_char)
        ):
            return "Postcode hoort bij een postbusadres — geen persoonlijk adres."
        return None

    if entity_type == "email":
        if text.lower() in index.emails:
            return "Algemeen e-mailadres van een gemeente — openbare informatie."
        return None

    if entity_type == "telefoon":
        digits = re.sub(r"\D+", "", text)
        if digits and digits in index.phones:
            return "Algemeen telefoonnummer van een gemeente — openbare informatie."
        return None

    if entity_type == "url":
        lower = text.lower().rstrip("/")
        if lower in index.websites:
            return "Officiële website van een gemeente — openbare informatie."
        # Also accept a prefix match so a deep link under gemeente.nl
        # still whitelists.
        for site in index.websites:
            if lower.startswith(site):
                return "Pagina op een officiële gemeentelijke website — openbare informatie."
        return None

    if entity_type == "adres":
        normalized = _normalize_phrase(_strip_bbox_markers(text))
        if normalized in index.addresses:
            return "Bezoekadres/Woo-adres van een gemeente — openbare informatie."
        # Street-only match (no huisnummer) — still public.
        if normalized in index.woonplaatsen:
            return "Woonplaats van een gemeentelijk adres — openbare informatie."
        return None

    return None
