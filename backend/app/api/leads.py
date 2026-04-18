"""Public contact form (#45 — Brevo edition).

The GTM plan launches WOO Buddy without auth, so this endpoint is our
only way for interested visitors to reach us. A visitor submits
`{email, source, newsletter_opt_in}` (plus optional name / organization
/ message). Two things can happen:

1. **Always**: a transactional email is sent through Brevo's
   `/v3/smtp/email` endpoint to `settings.brevo_notification_email`
   with the form contents and a `Reply-To` header pointing at the
   submitter. That is how the operator actually sees messages.
2. **Only if `newsletter_opt_in` is true**: the contact is also pushed
   into Brevo list `settings.brevo_list_id` via `/v3/contacts`.

Brevo is the system of record for the audience list; there is no
dual-write to Postgres, no CSV export, no `leads` table.

Design notes:

* **Unauthenticated**. This is explicitly a public form.
* **Rate-limited** per IP via slowapi (in-memory bucket).
* **Opaque success**. We return `{ok: true}` both for a fresh contact
  and for a duplicate that Brevo rejects, so the form cannot be used
  to probe list membership.
* **No request-body logging**. The only fact we record is "a lead was
  submitted from source X".
* **Client-first**. This endpoint touches zero document content.
"""

from __future__ import annotations

import html
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
# contact form, not an MX validator.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Length caps mirror what Brevo will accept and what the form renders.
_MAX_EMAIL_LEN = 320
_MAX_NAME_LEN = 200
_MAX_ORG_LEN = 200
_MAX_MESSAGE_LEN = 2000

_BREVO_CONTACTS_URL = "https://api.brevo.com/v3/contacts"
_BREVO_SMTP_URL = "https://api.brevo.com/v3/smtp/email"
_BREVO_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _clean(value: str | None, *, max_len: int) -> str | None:
    """Trim whitespace, enforce max length, collapse blanks to None."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:max_len]


def _brevo_headers() -> dict[str, str]:
    return {
        "api-key": settings.brevo_api_key,
        "accept": "application/json",
        "content-type": "application/json",
    }


def _build_contact_list_payload(
    email: str, data: LeadCreate
) -> dict[str, Any]:
    """Shape our form fields into Brevo's `/v3/contacts` payload.

    Only called when the submitter opts in to the newsletter. Brevo
    attribute names are uppercase by convention. Unknown attributes are
    silently ignored by Brevo, so MESSAGE/SOURCE will start populating
    once the account owner defines them in the dashboard.
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
        "email": email,
        "listIds": [settings.brevo_list_id],
        # Idempotent re-submits: update attributes instead of 400-ing.
        "updateEnabled": True,
        "attributes": attributes,
    }


def _build_smtp_payload(email: str, data: LeadCreate) -> dict[str, Any]:
    """Shape the form contents into Brevo's `/v3/smtp/email` payload.

    The operator receives a plain rendering of the submitted fields with
    a `Reply-To` header set to the submitter's address, so hitting reply
    in their inbox just works.
    """
    name = _clean(data.name, max_len=_MAX_NAME_LEN)
    organization = _clean(data.organization, max_len=_MAX_ORG_LEN)
    message = _clean(data.message, max_len=_MAX_MESSAGE_LEN)

    rows: list[tuple[str, str]] = [
        ("Bron", data.source),
        ("E-mail", email),
    ]
    if name:
        rows.append(("Naam", name))
    if organization:
        rows.append(("Organisatie", organization))
    rows.append(
        (
            "Nieuwsbrief",
            "Ja — ook aangemeld voor de lijst"
            if data.newsletter_opt_in
            else "Nee",
        )
    )

    rendered_rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'>{html.escape(label)}</td>"
        f"<td style='padding:4px 0'>{html.escape(value)}</td></tr>"
        for label, value in rows
    )
    rendered_message = (
        f"<p style='margin-top:16px;white-space:pre-wrap'>{html.escape(message)}</p>"
        if message
        else "<p style='margin-top:16px;color:#888'><em>Geen bericht ingevuld.</em></p>"
    )

    subject_hint = name or organization or email
    subject = f"WOO Buddy contactformulier — {subject_hint}"

    html_content = (
        "<div style='font-family:system-ui,sans-serif;font-size:14px;color:#111'>"
        f"<h2 style='margin:0 0 12px;font-size:18px'>Nieuw bericht via het contactformulier</h2>"
        f"<table style='border-collapse:collapse'>{rendered_rows}</table>"
        f"{rendered_message}"
        "</div>"
    )

    return {
        "sender": {
            "email": settings.brevo_sender_email,
            "name": settings.brevo_sender_name,
        },
        "to": [{"email": settings.brevo_notification_email}],
        "replyTo": {"email": email, **({"name": name} if name else {})},
        "subject": subject[:200],
        "htmlContent": html_content,
    }


async def _post_to_brevo(
    client: httpx.AsyncClient, url: str, payload: dict[str, Any]
) -> httpx.Response:
    """Thin wrapper — keeps the two Brevo calls symmetrical."""
    return await client.post(url, json=payload, headers=_brevo_headers())


def _raise_generic_gateway() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Kon het verzenden niet voltooien. Probeer het later opnieuw.",
    )


def _raise_generic_500() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Verzenden is tijdelijk niet beschikbaar.",
    )


def _error_code(response: httpx.Response) -> str | None:
    """Pull `code` out of Brevo's JSON error envelope, tolerantly."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        raw = body.get("code")
        if isinstance(raw, str):
            return raw
    return None


async def _send_contact_email(
    client: httpx.AsyncClient, email: str, data: LeadCreate
) -> None:
    """Fire the transactional email. Raises HTTPException on failure.

    Success shape:
    * `201 Created` with `{"messageId": "..."}`

    Error mapping mirrors `_add_to_list` — same user-facing surfaces so
    the form behaves identically whether the contacts or the SMTP call
    is the one that fails.
    """
    payload = _build_smtp_payload(email, data)
    try:
        response = await _post_to_brevo(client, _BREVO_SMTP_URL, payload)
    except httpx.HTTPError as exc:
        logger.error("leads.brevo_smtp_transport_error", error=str(exc))
        raise _raise_generic_gateway() from exc

    if response.status_code in (200, 201, 202):
        return

    code = _error_code(response)
    if response.status_code in (401, 403):
        logger.error(
            "leads.brevo_smtp_auth_error",
            status_code=response.status_code,
            error_code=code,
        )
        raise _raise_generic_500()
    if response.status_code == 429:
        logger.warning("leads.brevo_smtp_rate_limited")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Even geduld — probeer het over een minuutje opnieuw.",
        )
    logger.error(
        "leads.brevo_smtp_unexpected_status",
        status_code=response.status_code,
        error_code=code,
    )
    raise _raise_generic_gateway()


async def _add_to_list(
    client: httpx.AsyncClient, email: str, data: LeadCreate
) -> None:
    """Push one contact into the configured Brevo list.

    Success shapes:
    * `201 Created` — fresh contact
    * `204 No Content` — existing contact updated (we set
      `updateEnabled: true` so this is a normal success path)

    A `400 duplicate_parameter` response is treated as silent success
    for the same probe-resistance reason used across the file.
    """
    payload = _build_contact_list_payload(email, data)
    try:
        response = await _post_to_brevo(client, _BREVO_CONTACTS_URL, payload)
    except httpx.HTTPError as exc:
        logger.error("leads.brevo_contacts_transport_error", error=str(exc))
        raise _raise_generic_gateway() from exc

    if response.status_code in (200, 201, 204):
        return

    code = _error_code(response)
    if response.status_code == 400 and code == "duplicate_parameter":
        logger.info("leads.brevo_duplicate", source=data.source)
        return
    if response.status_code in (401, 403):
        logger.error(
            "leads.brevo_contacts_auth_error",
            status_code=response.status_code,
            error_code=code,
        )
        raise _raise_generic_500()
    if response.status_code == 429:
        logger.warning("leads.brevo_contacts_rate_limited")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Even geduld — probeer het over een minuutje opnieuw.",
        )
    logger.error(
        "leads.brevo_contacts_unexpected_status",
        status_code=response.status_code,
        error_code=code,
    )
    raise _raise_generic_gateway()


@router.post("/api/leads", response_model=LeadResponse)
@limiter.limit("5/minute")
async def create_lead(
    request: Request,
    response: Response,
    data: LeadCreate,
) -> LeadResponse:
    """Send the operator a transactional email; optionally subscribe."""
    email = (data.email or "").strip().lower()
    if not email or len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig e-mailadres.",
        )

    if not settings.brevo_api_key:
        # Misconfiguration, not a user error. Don't expose details.
        logger.error("leads.brevo_api_key_missing")
        raise _raise_generic_500()

    async with httpx.AsyncClient(timeout=_BREVO_TIMEOUT) as client:
        # Notification email comes first: it is the part the operator
        # cannot afford to miss. If subscribing to the list fails after
        # the email has already been sent the operator still knows a
        # lead came in — better than the reverse.
        await _send_contact_email(client, email, data)
        if data.newsletter_opt_in:
            await _add_to_list(client, email, data)

    # Do NOT log email or field content — the only fact worth recording
    # is "a lead came in from source X".
    logger.info(
        "leads.created",
        source=data.source,
        newsletter_opt_in=data.newsletter_opt_in,
    )
    return LeadResponse(ok=True)
