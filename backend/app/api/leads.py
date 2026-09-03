"""Public contact form and the newsletter double opt-in.

WOO Buddy launches without auth, so this endpoint is the only way for
interested visitors to reach us. A visitor submits
`{email, source, newsletter_opt_in}` (plus optional name / organization
/ message). Two things can happen:

1. **Always**: a transactional email is sent through Scaleway TEM's
   `/emails` API to `settings.notification_email` with the form contents
   and a `Reply-To` header pointing at the submitter. That is how the
   operator actually sees messages.
2. **Only if `newsletter_opt_in` is true**: a confirmation mail goes to
   the *submitter*, carrying a signed link back to the site. Nothing
   reaches the mailing list until that link is clicked — which happens
   at `POST /api/leads/confirm`.

**Why WOO Buddy runs its own double opt-in** (#76): Listmonk's opt-in
mail, sender address and public pages are instance-global, and the
instance is shared with another brand, so a signup here used to receive
a mail headed "DREAMKIT UPDATES" from `noreply@mail.dreamkit.eu`
announcing a list called "WOO Buddy — leads". That reads as a sales
list from a stranger, which is the opposite of what the landing page
promises. Sending the confirmation ourselves is the only way to control
the sender, the copy and the page behind the button.

Listmonk is still the system of record for the audience list; there is
no dual-write to Postgres, no CSV export, no `leads` table. The
confirmation link is stateless (see `app/services/lead_tokens.py`), so
an address in flight lives in exactly one place: the recipient's inbox.

Design notes:

* **Unauthenticated**. This is explicitly a public form.
* **Rate-limited** per IP via slowapi (in-memory bucket).
* **Opaque success**. We return `{ok: true}` whether or not the opt-in
  path did anything, so the form cannot be used to probe list membership
  or to find out whether the integration is configured.
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

from app.api.schemas import LeadConfirm, LeadConfirmResponse, LeadCreate, LeadResponse
from app.config import settings
from app.logging_config import get_logger
from app.security import limiter
from app.services import listmonk
from app.services.lead_mail import build_confirmation_payload
from app.services.lead_tokens import (
    ExpiredTokenError,
    InvalidTokenError,
    make_token,
    read_token,
)

logger = get_logger(__name__)

router = APIRouter(tags=["leads"])

# Good-enough RFC 5322-ish email regex. Not comprehensive — we are a
# contact form, not an MX validator.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Length caps mirror what the providers accept and what the form renders.
_MAX_EMAIL_LEN = 320
_MAX_NAME_LEN = 200
_MAX_ORG_LEN = 200
_MAX_MESSAGE_LEN = 2000

_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


# Anything that ends up in a mail header (Subject, Reply-To) must not carry
# control characters. A bare CR/LF in `name` or `organization` would let a
# submitter terminate our header and append their own — a Bcc, say — to the
# notification mail. Double quotes and backslashes go too: the display name
# in Reply-To is wrapped in quotes, so an unescaped one breaks the address
# out of its quoted string.
_HEADER_UNSAFE_RE = re.compile(r'[\x00-\x1f\x7f"\\]+')


def _clean(value: str | None, *, max_len: int, header_safe: bool = False) -> str | None:
    """Trim whitespace, enforce max length, collapse blanks to None.

    With `header_safe=True` every control character, double quote and
    backslash collapses to a single space first, so the result is safe to
    interpolate into a mail header. Truncation happens last, so the cap
    still holds after substitution.
    """
    if value is None:
        return None
    stripped = value.strip()
    if header_safe:
        stripped = _HEADER_UNSAFE_RE.sub(" ", stripped).strip()
    if not stripped:
        return None
    return stripped[:max_len]


def _tem_url() -> str:
    return (
        "https://api.scaleway.com/transactional-email/v1alpha1/regions/"
        f"{settings.scaleway_tem_region}/emails"
    )


def _tem_headers() -> dict[str, str]:
    return {
        "X-Auth-Token": settings.scaleway_secret_key,
        "accept": "application/json",
        "content-type": "application/json",
    }


def _build_tem_payload(email: str, data: LeadCreate) -> dict[str, Any]:
    """Shape the form contents into Scaleway TEM's `/emails` payload.

    The operator receives a plain rendering of the submitted fields with
    a `Reply-To` header set to the submitter's address, so hitting reply
    in their inbox just works.
    """
    # `name` and `organization` reach the Subject and Reply-To headers, so
    # they are cleaned header-safe. `message` only ever lands in the body,
    # HTML-escaped and rendered `pre-wrap`, so its newlines stay meaningful.
    name = _clean(data.name, max_len=_MAX_NAME_LEN, header_safe=True)
    organization = _clean(data.organization, max_len=_MAX_ORG_LEN, header_safe=True)
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
            "Ja — ook aangemeld voor de lijst" if data.newsletter_opt_in else "Nee",
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

    # Plain-text alternative — Scaleway TEM wants both parts, and it keeps
    # the message readable in text-only clients.
    text_lines = [f"{label}: {value}" for label, value in rows]
    if message:
        text_lines.append("")
        text_lines.append(message)
    text_content = "Nieuw bericht via het contactformulier\n\n" + "\n".join(text_lines)

    # Reply-To carries the submitter so the inbox reply button Just Works.
    reply_to = f'"{name}" <{email}>' if name else email

    return {
        "from": {
            "email": settings.tem_from_email,
            "name": settings.tem_from_name,
        },
        "to": [{"email": settings.notification_email}],
        "subject": subject[:200],
        "html": html_content,
        "text": text_content,
        "project_id": settings.scaleway_project_id,
        "additional_headers": [{"key": "Reply-To", "value": reply_to}],
    }


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


def _raise_rate_limited() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Even geduld — probeer het over een minuutje opnieuw.",
    )


async def _send_contact_email(client: httpx.AsyncClient, email: str, data: LeadCreate) -> None:
    """Fire the transactional email via Scaleway TEM. Raises on failure.

    Success shape: `200 OK` with `{"emails": [...]}`.

    Error mapping keeps the same user-facing surfaces as the list call so
    the form behaves identically whichever upstream is the one that fails:
    401/403 (bad/revoked key) -> generic 500, 429 -> 503, anything else
    -> 502.
    """
    payload = _build_tem_payload(email, data)
    try:
        response = await client.post(_tem_url(), json=payload, headers=_tem_headers())
    except httpx.HTTPError as exc:
        logger.error("leads.tem_transport_error", error=str(exc))
        raise _raise_generic_gateway() from exc

    if response.status_code in (200, 201, 202):
        return

    if response.status_code in (401, 403):
        logger.error("leads.tem_auth_error", status_code=response.status_code)
        raise _raise_generic_500()
    if response.status_code == 429:
        logger.warning("leads.tem_rate_limited")
        raise _raise_rate_limited()
    logger.error("leads.tem_unexpected_status", status_code=response.status_code)
    raise _raise_generic_gateway()


def opt_in_available() -> bool:
    """True when a confirmation mail can actually be sent and honoured.

    Both halves have to be present: a secret to sign the link with, and
    Listmonk credentials to act on it afterwards. Mailing someone a link
    that will fail when they click it is worse than quietly skipping the
    opt-in, so this gate covers the whole round trip rather than just the
    send.
    """
    return bool(settings.leads_confirm_secret) and listmonk.is_configured()


async def _send_confirmation_email(client: httpx.AsyncClient, email: str) -> bool:
    """Mail the submitter a signed confirmation link. Returns whether it went.

    Deliberately non-fatal in every failure mode. The operator's
    notification has already been sent by the time this runs, so the form
    submission succeeded in the way that matters; losing the newsletter
    opt-in is a smaller harm than showing the visitor an error for a
    checkbox they ticked in passing.
    """
    try:
        token = make_token(email, secret=settings.leads_confirm_secret)
    except ValueError:
        logger.warning("leads.opt_in_skipped", reason="no_confirm_secret")
        return False

    try:
        response = await client.post(
            _tem_url(),
            json=build_confirmation_payload(email, token),
            headers=_tem_headers(),
        )
    except httpx.HTTPError as exc:
        logger.error("leads.confirmation_transport_error", error=str(exc))
        return False

    if response.status_code in (200, 201, 202):
        return True

    logger.error("leads.confirmation_send_failed", status_code=response.status_code)
    return False


@router.post("/api/leads", response_model=LeadResponse)
@limiter.limit("5/minute")
async def create_lead(
    request: Request,
    response: Response,
    data: LeadCreate,
) -> LeadResponse:
    """Mail the operator; optionally start the newsletter double opt-in."""
    email = (data.email or "").strip().lower()
    if not email or len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig e-mailadres.",
        )

    if not settings.scaleway_secret_key:
        # Misconfiguration, not a user error. Don't expose details.
        logger.error("leads.scaleway_secret_key_missing")
        raise _raise_generic_500()

    confirmation_sent = False
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        # Notification email comes first: it is the part the operator
        # cannot afford to miss. If the confirmation mail fails after the
        # notification has gone out, the operator still knows a lead came
        # in — better than the reverse.
        await _send_contact_email(client, email, data)
        if data.newsletter_opt_in and opt_in_available():
            confirmation_sent = await _send_confirmation_email(client, email)
        elif data.newsletter_opt_in:
            logger.warning("leads.opt_in_skipped", reason="listmonk_not_configured")

    # Do NOT log email or field content — the only fact worth recording
    # is "a lead came in from source X".
    logger.info(
        "leads.created",
        source=data.source,
        newsletter_opt_in=data.newsletter_opt_in,
        confirmation_sent=confirmation_sent,
    )
    return LeadResponse(ok=True)


@router.post("/api/leads/confirm", response_model=LeadConfirmResponse)
@limiter.limit("20/minute")
async def confirm_lead(
    request: Request,
    response: Response,
    data: LeadConfirm,
) -> LeadConfirmResponse:
    """Redeem a confirmation token and put the address on the list.

    Always 200 — the caller is the SvelteKit confirmation page, which
    renders a different sentence per `status` rather than an HTTP error.
    A bad token is an ordinary outcome here (a stale link, a mail client
    that mangled the URL), not an exceptional one.

    `already_known` is not distinguished from `confirmed` in the
    response: only the token holder ever gets here, but there is no
    reason to tell them anything beyond "it worked".
    """
    token = (data.token or "").strip()

    try:
        email = read_token(token, secret=settings.leads_confirm_secret)
    except ExpiredTokenError:
        logger.info("leads.confirm_expired")
        return LeadConfirmResponse(status="expired")
    except InvalidTokenError:
        # Covers a tampered link and an unconfigured secret alike; the
        # visitor can do nothing about either, so they see one message.
        logger.info("leads.confirm_invalid")
        return LeadConfirmResponse(status="invalid")

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            outcome = await listmonk.subscribe_confirmed(client, email)
        except listmonk.ListmonkNotConfiguredError:
            logger.error("leads.confirm_listmonk_unconfigured")
            return LeadConfirmResponse(status="unavailable")
        except (listmonk.ListmonkError, httpx.HTTPError) as exc:
            logger.error("leads.confirm_listmonk_failed", error=str(exc))
            return LeadConfirmResponse(status="unavailable")

    # `outcome` says whether Listmonk created the subscriber or already
    # had them; neither is worth an address in the log line.
    logger.info("leads.confirmed", outcome=outcome)
    return LeadConfirmResponse(status="confirmed")
