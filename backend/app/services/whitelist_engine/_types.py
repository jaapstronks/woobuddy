"""Whitelist dataclasses. Kept dependency-free so both the loader and the
matching modules can import them without pulling in stdlib regex state."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class PersonWhitelistHit:
    """A successful public-official whitelist match."""

    official: PublicOfficial
    municipality_name: str  # "Gemeente Aalsmeer"
    used_initials: bool  # whether the initials-gate actually fired
