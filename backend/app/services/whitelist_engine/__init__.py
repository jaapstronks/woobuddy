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
   surnames the match additionally requires the detection's visible
   initials to prefix-match the CSV's initials — otherwise a raadslid
   whose name happens to collide with a private citizen in an unrelated
   document would be un-redacted by accident.

Both CSVs are loaded once at app startup via ``init_whitelist_index``
and cached in the module (``get_whitelist_index``) so tests and lazy
paths work without threading ``app.state`` through every call site. The
files will go stale — new raadsleden are elected, municipalities merge
— so the process for refreshing them is "replace the CSV and restart
the backend." That cadence is explicit and intentional; there is no
auto-update path.

This package is split across a few files by concern:

- ``_text``      — normalization helpers + regex constants + common-surnames set
- ``_types``     — immutable dataclasses (``WhitelistIndex``, ``PublicOfficial``, etc.)
- ``_loader``    — CSV parsing and cached index assembly
- ``_persons``   — context-gated public-official matching
- ``_addresses`` — global address / contact whitelisting + postbus rule

Importers should continue using ``from app.services.whitelist_engine import ...``
— the public API is re-exported here.
"""

from __future__ import annotations

from ._addresses import is_postbus_context_postcode, match_address_whitelist
from ._loader import (
    get_whitelist_index,
    init_whitelist_index,
    load_whitelist_index,
    reset_cache,
)
from ._persons import find_active_gemeenten, match_person_whitelist
from ._types import (
    Municipality,
    PersonWhitelistHit,
    PublicOfficial,
    WhitelistIndex,
)

__all__ = [
    "Municipality",
    "PersonWhitelistHit",
    "PublicOfficial",
    "WhitelistIndex",
    "find_active_gemeenten",
    "get_whitelist_index",
    "init_whitelist_index",
    "is_postbus_context_postcode",
    "load_whitelist_index",
    "match_address_whitelist",
    "match_person_whitelist",
    "reset_cache",
]
