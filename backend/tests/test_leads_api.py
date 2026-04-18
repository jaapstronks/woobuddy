"""HTTP tests for the public contact endpoint (#45 — Brevo edition).

`backend/app/api/leads.py` is public, unauthenticated, and fires two
Brevo calls in a specific order:

1. `/v3/smtp/email` — always, so the operator sees the message.
2. `/v3/contacts` — only when `newsletter_opt_in` is true.

These tests fake Brevo with a tiny `_FakeAsyncClient` that records
calls and returns canned responses — one per URL — so we can exercise
the happy path and the error mapping for each endpoint in isolation.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from types import TracebackType
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.config import settings
from app.security import limiter

# ---------------------------------------------------------------------------
# Rate limiter bypass
# ---------------------------------------------------------------------------
# `/api/leads` is decorated with `@limiter.limit("5/minute")`. Without a
# reset the full suite can cross the cap between tests because slowapi's
# in-memory storage is process-global.


@pytest.fixture(autouse=True)
def _disable_rate_limiter() -> Iterator[None]:
    original = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = original


# ---------------------------------------------------------------------------
# Brevo upstream fake
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal httpx.Response stand-in. Only what leads.py touches."""

    def __init__(self, status_code: int, json_body: Any = None) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def json(self) -> Any:
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body


class _FakeAsyncClient:
    """Records every POST and returns a canned response per URL.

    leads.py issues two distinct calls (smtp + contacts). Tests set
    per-URL responses via `responses[url] = _FakeResponse(...)`. A
    missing entry falls back to `default_response`.
    """

    default_response: _FakeResponse = _FakeResponse(201)
    responses: dict[str, _FakeResponse] = {}
    raise_on_post: httpx.HTTPError | None = None
    calls: list[dict[str, Any]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def post(
        self, url: str, *, json: Any = None, headers: Any = None
    ) -> _FakeResponse:
        _FakeAsyncClient.calls.append({"url": url, "json": json, "headers": headers})
        if _FakeAsyncClient.raise_on_post is not None:
            raise _FakeAsyncClient.raise_on_post
        return _FakeAsyncClient.responses.get(url, _FakeAsyncClient.default_response)


_SMTP_URL = "https://api.brevo.com/v3/smtp/email"
_CONTACTS_URL = "https://api.brevo.com/v3/contacts"


@pytest.fixture(autouse=True)
def _patch_brevo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _FakeAsyncClient.default_response = _FakeResponse(201)
    _FakeAsyncClient.responses = {}
    _FakeAsyncClient.raise_on_post = None
    _FakeAsyncClient.calls = []
    monkeypatch.setattr("app.api.leads.httpx.AsyncClient", _FakeAsyncClient)
    # The endpoint bails out on a missing key; set one so the happy
    # path can proceed. Empty-key behavior has a dedicated test below.
    monkeypatch.setattr(settings, "brevo_api_key", "test-key-xyz")
    monkeypatch.setattr(settings, "brevo_list_id", 4)
    monkeypatch.setattr(settings, "brevo_notification_email", "ops@example.nl")
    monkeypatch.setattr(settings, "brevo_sender_email", "noreply@example.nl")
    monkeypatch.setattr(settings, "brevo_sender_name", "WOO Buddy")
    yield


def _calls_to(url: str) -> list[dict[str, Any]]:
    return [c for c in _FakeAsyncClient.calls if c["url"] == url]


# ---------------------------------------------------------------------------
# Happy path — no newsletter opt-in (contact form only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_only_sends_email_and_skips_list(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/leads",
        json={
            "email": "Jaap@Example.COM",
            "name": "  Jaap Stronks  ",
            "organization": "Gemeente Utrecht",
            "message": "Interesse in de pilot.",
            "source": "landing",
            "newsletter_opt_in": False,
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    # Exactly one upstream call — the transactional email. No /v3/contacts.
    assert len(_FakeAsyncClient.calls) == 1
    smtp = _calls_to(_SMTP_URL)
    assert len(smtp) == 1
    assert _calls_to(_CONTACTS_URL) == []

    payload = smtp[0]["json"]
    assert payload["to"] == [{"email": "ops@example.nl"}]
    # Reply-To is the submitter's normalized address so the inbox
    # reply button Just Works.
    assert payload["replyTo"]["email"] == "jaap@example.com"
    assert payload["replyTo"]["name"] == "Jaap Stronks"
    assert payload["sender"] == {
        "email": "noreply@example.nl",
        "name": "WOO Buddy",
    }
    assert "Jaap Stronks" in payload["subject"]
    assert "Interesse in de pilot." in payload["htmlContent"]
    assert "Nee" in payload["htmlContent"]

    # API key goes through as a header, never as a query param.
    assert smtp[0]["headers"]["api-key"] == "test-key-xyz"


# ---------------------------------------------------------------------------
# Happy path — newsletter opt-in flips the second call on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_newsletter_opt_in_also_subscribes(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/leads",
        json={
            "email": "a@b.nl",
            "name": "Ada",
            "source": "landing",
            "newsletter_opt_in": True,
        },
    )

    assert resp.status_code == 200

    # Two calls, in order: smtp first, then contacts.
    assert [c["url"] for c in _FakeAsyncClient.calls] == [
        _SMTP_URL,
        _CONTACTS_URL,
    ]

    contacts_payload = _calls_to(_CONTACTS_URL)[0]["json"]
    assert contacts_payload["email"] == "a@b.nl"
    assert contacts_payload["listIds"] == [4]
    assert contacts_payload["updateEnabled"] is True
    attrs = contacts_payload["attributes"]
    assert attrs["SOURCE"] == "landing"
    assert attrs["FIRSTNAME"] == "Ada"


@pytest.mark.asyncio
async def test_email_only_payload_omits_optional_attributes(
    client: AsyncClient,
) -> None:
    """Blank optional fields must collapse to missing keys, not empty strings."""
    resp = await client.post(
        "/api/leads",
        json={
            "email": "a@b.nl",
            "name": "   ",
            "organization": "",
            "message": None,
            "source": "post-export",
            "newsletter_opt_in": True,
        },
    )

    assert resp.status_code == 200
    attrs = _calls_to(_CONTACTS_URL)[0]["json"]["attributes"]
    assert "FIRSTNAME" not in attrs
    assert "COMPANY" not in attrs
    assert "MESSAGE" not in attrs
    assert attrs["SOURCE"] == "post-export"


@pytest.mark.asyncio
async def test_newsletter_opt_in_defaults_to_false(client: AsyncClient) -> None:
    """Missing field in the body must NOT auto-subscribe the submitter."""
    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 200
    assert _calls_to(_CONTACTS_URL) == []


@pytest.mark.asyncio
async def test_204_from_brevo_list_is_success(client: AsyncClient) -> None:
    """Brevo returns 204 when `updateEnabled: true` updates an existing
    contact. That is a normal success path, not an error."""
    _FakeAsyncClient.responses = {_CONTACTS_URL: _FakeResponse(204)}

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "newsletter_opt_in": True},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Client-side validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_email",
    [
        "",
        "   ",
        "not-an-email",
        "missing-at-sign.nl",
        "two@@signs.nl",
        "no-dot@example",
        "spaces in@email.nl",
    ],
)
async def test_invalid_email_400(client: AsyncClient, bad_email: str) -> None:
    resp = await client.post(
        "/api/leads",
        json={"email": bad_email, "source": "landing"},
    )
    assert resp.status_code == 400
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_oversized_email_400(client: AsyncClient) -> None:
    long_email = ("a" * 400) + "@example.nl"
    resp = await client.post(
        "/api/leads",
        json={"email": long_email, "source": "landing"},
    )
    assert resp.status_code == 400
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_invalid_source_422(client: AsyncClient) -> None:
    """`source` is a Literal — Pydantic rejects anything else as 422."""
    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "guerilla-marketing"},
    )
    assert resp.status_code == 422
    assert _FakeAsyncClient.calls == []


# ---------------------------------------------------------------------------
# Brevo upstream error mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_returns_500_without_network_call(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "brevo_api_key", "")

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 500
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_duplicate_parameter_is_silent_success(client: AsyncClient) -> None:
    """A 400 with code=duplicate_parameter on the list call must look the
    same as a fresh insert so the form cannot be used to probe
    membership."""
    _FakeAsyncClient.responses = {
        _CONTACTS_URL: _FakeResponse(
            400, {"code": "duplicate_parameter", "message": "Contact already exists"}
        )
    }

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "newsletter_opt_in": True},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_generic_400_from_contacts_becomes_502(client: AsyncClient) -> None:
    _FakeAsyncClient.responses = {
        _CONTACTS_URL: _FakeResponse(
            400, {"code": "invalid_parameter", "message": "something else"}
        )
    }

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "newsletter_opt_in": True},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_code", [401, 403])
async def test_smtp_auth_error_returns_500(
    client: AsyncClient, auth_code: int
) -> None:
    """Revoked / misconfigured API key on the transactional endpoint.
    We explicitly do NOT surface 401/403 so the form can't distinguish
    auth failures from other outages and leak account state."""
    _FakeAsyncClient.responses = {
        _SMTP_URL: _FakeResponse(auth_code, {"code": "unauthorized"})
    }

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 500
    # Contacts call must not fire after the SMTP call failed.
    assert _calls_to(_CONTACTS_URL) == []


@pytest.mark.asyncio
async def test_smtp_rate_limit_returns_503(client: AsyncClient) -> None:
    _FakeAsyncClient.responses = {
        _SMTP_URL: _FakeResponse(429, {"code": "too_many_requests"})
    }

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_smtp_5xx_returns_502(client: AsyncClient) -> None:
    _FakeAsyncClient.responses = {
        _SMTP_URL: _FakeResponse(500, {"code": "internal_error"})
    }

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_smtp_transport_error_returns_502(client: AsyncClient) -> None:
    """Network-level failure (DNS, timeout, connection refused) before
    we even get a response object."""
    _FakeAsyncClient.raise_on_post = httpx.ConnectError("boom")

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_smtp_non_json_error_body_still_502(client: AsyncClient) -> None:
    """Brevo occasionally returns HTML error pages. The JSON probe must
    swallow ValueError without crashing the handler."""
    _FakeAsyncClient.responses = {_SMTP_URL: _FakeResponse(502, json_body=None)}

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Privacy: request content must never land in logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_and_name_never_appear_in_logs(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """CLAUDE.md invariant: the only fact the server records is
    'a lead came in from source X' — no email, no name, no message."""
    secret_email = "sentinel-9f8c2@example.nl"
    secret_name = "GeheimNaamSentinel"
    secret_org = "GeheimOrgSentinel"
    secret_message = "GeheimMessageSentinel"

    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            "/api/leads",
            json={
                "email": secret_email,
                "name": secret_name,
                "organization": secret_org,
                "message": secret_message,
                "source": "landing",
                "newsletter_opt_in": True,
            },
        )
    assert resp.status_code == 200

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_email not in combined
    assert secret_name not in combined
    assert secret_org not in combined
    assert secret_message not in combined
