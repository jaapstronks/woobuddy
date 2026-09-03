"""Listmonk admin-API client for the newsletter list (#76).

Listmonk is the system of record for the audience list — there is no
`leads` table, no dual write, no CSV export. This module is the only
place that talks to it.

**Why the admin API and not the public subscription endpoint.** The
public endpoint (`/api/public/subscription`) is simpler and needs no
credentials, but it leaves the double opt-in in Listmonk's hands. Our
Listmonk instance is shared with another brand, and its opt-in mail,
sender address and public pages are instance-global: a WOO Buddy signup
got a mail headed "DREAMKIT UPDATES" from `noreply@mail.dreamkit.eu`.
So WOO Buddy sends the confirmation itself and only reaches Listmonk
*after* the recipient clicked (see `lead_tokens`). Writing through the
admin API with `preconfirm_subscriptions` records that consent as
already confirmed, which also means Listmonk never sends a second mail
of its own — regardless of how the list's opt-in setting is configured
later. Relying on the list staying single-opt-in would let one admin
click reintroduce the exact bug this replaces.

Everything here degrades rather than raises when the integration is
unconfigured: a missing API token must never cost the operator the
notification mail, which is the part of the contact form that actually
matters.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class ListmonkError(Exception):
    """Listmonk was reachable but could not complete the request."""


class ListmonkNotConfiguredError(ListmonkError):
    """No API user, token or list configured — the integration is off."""


def is_configured() -> bool:
    """True when every piece the subscribe path needs is present."""
    return bool(
        settings.listmonk_url
        and settings.listmonk_api_user
        and settings.listmonk_api_token
        and settings.listmonk_list_uuid
    )


def _base_url() -> str:
    return settings.listmonk_url.rstrip("/")


def _headers() -> dict[str, str]:
    """Auth header for a Listmonk API user (Admin → Users → type API).

    Listmonk accepts `Authorization: token <user>:<token>` for API users.
    The token is a credential: it is never logged, and it never reaches a
    query string.
    """
    return {
        "Authorization": f"token {settings.listmonk_api_user}:{settings.listmonk_api_token}",
        "accept": "application/json",
        "content-type": "application/json",
    }


def _sql_quote(value: str) -> str:
    """Escape a value for Listmonk's SQL-fragment `query` parameter.

    `GET /api/subscribers?query=` takes a raw SQL boolean expression that
    Listmonk splices into its own WHERE clause. An address with a single
    quote in the local part is legal (`o'brien@example.nl`), so doubling
    quotes is not paranoia about attackers alone — it is the difference
    between a working lookup and a 500. Backslashes go too: Postgres
    reads them as escapes under `standard_conforming_strings = off`.
    """
    return value.replace("\\", "").replace("'", "''")


def _results_of(response: httpx.Response) -> list[dict[str, Any]]:
    """Pull `data.results` out of a Listmonk list response."""
    try:
        body = response.json()
    except ValueError as exc:
        raise ListmonkError("response was not JSON") from exc
    data = body.get("data") if isinstance(body, dict) else None
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise ListmonkError("response carried no results array")
    return [row for row in results if isinstance(row, dict)]


async def resolve_list_id(client: httpx.AsyncClient) -> int:
    """Translate the configured list UUID into Listmonk's numeric id.

    `POST /api/subscribers` takes integer list ids, while our config
    carries the UUID — the UUID is the stable identifier that survives a
    Listmonk restore, so it is the right thing to keep in `.env`. One
    extra GET per confirmation is cheap: confirmations are rare, and a
    process-level cache would go stale exactly when someone recreates the
    list, which is the moment a wrong answer hurts most.
    """
    response = await client.get(
        f"{_base_url()}/api/lists",
        headers=_headers(),
        params={"per_page": "all"},
    )
    if response.status_code in (401, 403):
        raise ListmonkError(f"list lookup rejected the API user ({response.status_code})")
    if response.status_code != 200:
        raise ListmonkError(f"list lookup returned {response.status_code}")

    wanted = settings.listmonk_list_uuid
    for row in _results_of(response):
        if row.get("uuid") == wanted and isinstance(row.get("id"), int):
            list_id: int = row["id"]
            return list_id
    raise ListmonkError("configured list uuid is not present on this Listmonk")


async def _find_subscriber_id(client: httpx.AsyncClient, email: str) -> int | None:
    """Look up an existing subscriber by address, or None."""
    response = await client.get(
        f"{_base_url()}/api/subscribers",
        headers=_headers(),
        params={"query": f"subscribers.email = '{_sql_quote(email)}'", "per_page": "1"},
    )
    if response.status_code != 200:
        raise ListmonkError(f"subscriber lookup returned {response.status_code}")
    for row in _results_of(response):
        if isinstance(row.get("id"), int):
            subscriber_id: int = row["id"]
            return subscriber_id
    return None


async def _add_existing_to_list(
    client: httpx.AsyncClient, subscriber_id: int, list_id: int
) -> None:
    """Add an address Listmonk already knows to our list, as confirmed.

    This is the path for someone who signed up before, or who is on
    another list on the same instance. `status: confirmed` records the
    consent we just collected ourselves; without it the row would sit
    unconfirmed and a double-opt-in list would refuse to mail it.
    """
    response = await client.put(
        f"{_base_url()}/api/subscribers/lists",
        headers=_headers(),
        json={
            "ids": [subscriber_id],
            "action": "add",
            "target_list_ids": [list_id],
            "status": "confirmed",
        },
    )
    if response.status_code not in (200, 201):
        raise ListmonkError(f"list add returned {response.status_code}")


async def subscribe_confirmed(client: httpx.AsyncClient, email: str, *, name: str = "") -> str:
    """Put a freshly confirmed address on the list. Returns what happened.

    `"created"` for a new subscriber, `"already_known"` when Listmonk
    already had the address and we only attached the list. Both are
    success from the visitor's point of view; the distinction exists for
    the log line.

    Raises `ListmonkNotConfiguredError` when the integration is off, and
    `ListmonkError` for anything Listmonk refused. Callers decide how
    loudly that matters — the confirmation page treats it as a soft
    failure, because the visitor did their part.
    """
    if not is_configured():
        raise ListmonkNotConfiguredError("listmonk api credentials or list uuid missing")

    list_id = await resolve_list_id(client)

    response = await client.post(
        f"{_base_url()}/api/subscribers",
        headers=_headers(),
        json={
            "email": email,
            "name": name or email,
            "status": "enabled",
            "lists": [list_id],
            # The consent was collected by our own confirmation mail, so
            # Listmonk must record it as confirmed and must not send an
            # opt-in mail of its own.
            "preconfirm_subscriptions": True,
        },
    )

    if response.status_code in (200, 201):
        return "created"

    if response.status_code == 409:
        # Listmonk already knows the address. Attach the list instead —
        # this is the returning-visitor path, not an error.
        subscriber_id = await _find_subscriber_id(client, email)
        if subscriber_id is None:
            raise ListmonkError("conflict on create but no subscriber found")
        await _add_existing_to_list(client, subscriber_id, list_id)
        return "already_known"

    if response.status_code in (401, 403):
        raise ListmonkError(f"subscribe rejected the API user ({response.status_code})")
    raise ListmonkError(f"subscribe returned {response.status_code}")


__all__ = [
    "ListmonkError",
    "ListmonkNotConfiguredError",
    "is_configured",
    "resolve_list_id",
    "subscribe_confirmed",
]
