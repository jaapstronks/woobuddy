"""Public lead capture (#45) — Brevo edition.

The GTM plan launches WOO Buddy without auth, so this endpoint is our
only way to convert interested visitors into a reachable audience. A
visitor submits `{email, source, consent}` (plus optional name /
organization / message) and we push the contact into Brevo list
`settings.brevo_list_id` (default 4 — the "Woobuddy" list). Brevo is the
system of record: there is no dual-write to Postgres, no CSV export, no
`leads` table in our database. A Brevo automation on that list handles
the welcome email.

Design notes:

* **Unauthenticated**. The `verify_proxy_secret` dependency is
  intentionally omitted — this is explicitly a public form.
* **Rate-limited** per IP via slowapi (in-memory bucket). Fine for
  launch; swap to a Redis-backed bucket if it gets abused.
* **Opaque success**. We return `{ok: true}` both for a fresh contact
  and for a duplicate that Brevo rejects, so the form cannot be used to
  probe list membership.
* **No request-body logging**. The only fact we record is "a lead was
  submitted from source X" — no email, no name, nothing that could link
  a log line to a person.
* **Client-first**. This endpoint touches zero document content. It
  lives under `/api/leads` next to the other API routes purely for
  deployment convenience.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.schemas import LeadCreate, LeadResponse
from app.config import settings
from app.logging_config import get_logger
from app.security import limiter

logger = get_logger(__name__)

router = APIRouter(tags=["leads"])

# Good-enough RFC 5322-ish email regex. Not comprehensive — we are a
# marketing signup form, not an MX validator. The real test is whether
# the operator can mail them afterwards.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Length caps mirror what Brevo will accept and what the form renders.
# Enforced here so a pathological payload never reaches the Brevo API.
_MAX_EMAIL_LEN = 320
_MAX_NAME_LEN = 200
_MAX_ORG_LEN = 200
_MAX_MESSAGE_LEN = 2000

_BREVO_CONTACTS_URL = "https://api.brevo.com/v3/contacts"
_BREVO_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _clean(value: str | None, *, max_len: int) -> str | None:
    """Trim whitespace, enforce max length, collapse blanks to None."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:max_len]


def _build_brevo_payload(data: LeadCreate) -> dict[str, Any]:
    """Shape our form fields into Brevo's `/v3/contacts` payload.

    Brevo attribute names are uppercase by convention. We use:
    * `FIRSTNAME` for the single `name` field (no best-effort split —
      splitting Dutch names is unreliable and we'd rather have one
      accurate field than two messy ones).
    * `COMPANY` (Brevo's built-in attribute) for the organization.
    * `MESSAGE` and `SOURCE` as custom attributes the Brevo account
      owner is expected to create in the dashboard. If they don't exist
      yet, Brevo silently ignores them — no error, the contact is still
      created. So the form works immediately and gets richer once the
      attributes are configured.
    """
    attributes: dict[str, Any] = {"SOURCE": data.source}
    name = _clean(data.name, max_len=_MAX_NAME_LEN)
    if name:
        attributes["FIRSTNAME"] = name
    organization = _clean(data.organization, max_len=_MAX_ORG_LEN)
    if organization:
        attributes["COMPANY"] = organization
    message = _clean(data.message, max_len=_MAX_MESSAGE_LEN)
    if message:
        attributes["MESSAGE"] = message

    return {
        "email": (data.email or "").strip().lower(),
        "listIds": [settings.brevo_list_id],
        # `updateEnabled: true` makes the call idempotent — re-submits
        # from the same address update attributes instead of 400-ing.
        # This is why we don't need separate "already on list" handling.
        "updateEnabled": True,
        "attributes": attributes,
    }


async def _submit_to_brevo(payload: dict[str, Any]) -> None:
    """Push one contact into Brevo. Raises HTTPException on failure.

    Success shapes from the Brevo API:
    * `201 Created` — fresh contact
    * `204 No Content` — existing contact updated (we set
      `updateEnabled: true` so this is a normal success path)

    Error shapes we handle explicitly:
    * `400` with `code == "duplicate_parameter"` — treat as success, for
      the same probe-resistance reason: the form cannot reveal whether
      an address was already on the list.
    * `401` / `403` — our API key is wrong/revoked. This is a
      server-config bug, not a client bug; log loudly and return a
      generic 500 so the form shows a retry.
    * `429` — Brevo is rate-limiting us. Surface as 503 so the user
      knows to try again shortly.
    * Anything else — 502, we couldn't reach the upstream.
    """
    if not settings.brevo_api_key:
        # Misconfiguration, not a user error. Don't expose details.
        logger.error("leads.brevo_api_key_missing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aanmelden is tijdelijk niet beschikbaar.",
        )

    headers = {
        "api-key": settings.brevo_api_key,
        "accept": "application/json",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_BREVO_TIMEOUT) as client:
            response = await client.post(
                _BREVO_CONTACTS_URL, json=payload, headers=headers
            )
    except httpx.HTTPError as exc:
        logger.error("leads.brevo_transport_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kon het aanmelden niet voltooien. Probeer het later opnieuw.",
        ) from exc

    if response.status_code in (200, 201, 204):
        return

    # Probe Brevo's JSON error envelope — it's usually
    # `{"code": "...", "message": "..."}`. We only use the `code` field
    # here; the human-readable message is not echoed back to the client
    # because it can leak details about our Brevo account.
    error_code: str | None = None
    try:
        body = response.json()
        if isinstance(body, dict):
            raw_code = body.get("code")
            if isinstance(raw_code, str):
                error_code = raw_code
    except ValueError:
        body = None

    if response.status_code == 400 and error_code == "duplicate_parameter":
        # Contact already exists and for some reason `updateEnabled`
        # didn't swallow it. Treat as a silent success.
        logger.info("leads.brevo_duplicate", source=payload.get("attributes", {}).get("SOURCE"))
        return

    if response.status_code in (401, 403):
        logger.error(
            "leads.brevo_auth_error",
            status_code=response.status_code,
            error_code=error_code,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aanmelden is tijdelijk niet beschikbaar.",
        )

    if response.status_code == 429:
        logger.warning("leads.brevo_rate_limited")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Even geduld — probeer het over een minuutje opnieuw.",
        )

    logger.error(
        "leads.brevo_unexpected_status",
        status_code=response.status_code,
        error_code=error_code,
    )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Kon het aanmelden niet voltooien. Probeer het later opnieuw.",
    )


@router.post("/api/leads", response_model=LeadResponse)
@limiter.limit("5/minute")
async def create_lead(
    request: Request,
    response: Response,
    data: LeadCreate,
) -> LeadResponse:
    """Push one contact into Brevo. Silent on duplicates."""
    if not data.consent:
        # Explicit consent is a GDPR requirement for a product-update
        # list. A form that forgets the checkbox should fail loud.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Toestemming is vereist om je e-mailadres op te slaan.",
        )

    email = (data.email or "").strip()
    if not email or len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig e-mailadres.",
        )

    payload = _build_brevo_payload(data)
    await _submit_to_brevo(payload)

    # Do NOT log email or field content — the only fact worth recording
    # is "a lead came in from source X".
    logger.info("leads.created", source=data.source)
    return LeadResponse(ok=True)
