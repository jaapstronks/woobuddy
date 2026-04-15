"""CSV loaders and index assembly for the whitelist engine.

Both CSVs (``gemeenten.csv`` and ``medewerkers_gemeenten.csv``) are
parsed here and compiled into a ``WhitelistIndex``. The loaders are
tolerant: missing files yield an empty index so the pipeline keeps
behaving as before the whitelist was added.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from app.logging_config import get_logger

from ._text import (
    _HONORIFIC_TOKENS,
    _INITIAL_LETTERS_RE,
    _INITIAL_RE,
    _PAREN_RE,
    _normalize_phrase,
)
from ._types import Municipality, PublicOfficial, WhitelistIndex

logger = get_logger(__name__)

# whitelist_engine/_loader.py → whitelist_engine/ → services/ → app/ → app/data
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_GEMEENTEN_FILE = _DATA_DIR / "gemeenten.csv"
_MEDEWERKERS_FILE = _DATA_DIR / "medewerkers_gemeenten.csv"


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
