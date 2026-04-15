"""HTTP tests for the public lead-capture endpoint (#45 — Brevo edition).

`backend/app/api/leads.py` is new, public, unauthenticated, and has rich
branching: consent check, email regex, and a Brevo response mapper that
translates 200/201/204/400-dup/401/429/5xx into different surfaces. That
is a lot of ship-blocking behavior for zero tests, which is what this
file fixes.

The Brevo upstream is faked with a tiny `_FakeAsyncClient` that records
calls and returns canned responses. We deliberately avoid adding `respx`
as a dev dependency for this — the surface area under test is small and
a 30-line fake keeps the dev install footprint unchanged.
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
# in-memory storage is process-global. Toggle the limiter off for leads
# tests and restore afterwards.


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
    """Records the single POST leads.py issues and returns a canned response.

    Configured via class attributes so tests can set them before issuing
    the request. `calls` accumulates across a single test; the
    `_reset_fake` fixture clears it between tests.
    """

    response: _FakeResponse = _FakeResponse(201)
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
        return _FakeAsyncClient.response


@pytest.fixture(autouse=True)
def _patch_brevo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replace httpx.AsyncClient *inside* leads.py with the fake.

    We patch the attribute on the `leads` module rather than on the
    global `httpx` package so unrelated tests (and any transitive httpx
    usage from ASGITransport) keep the real client. The dotted string
    form avoids a stray `from app.api import leads` import that mypy
    flags because `httpx` is not re-exported from the module.
    """
    _FakeAsyncClient.response = _FakeResponse(201)
    _FakeAsyncClient.raise_on_post = None
    _FakeAsyncClient.calls = []
    monkeypatch.setattr("app.api.leads.httpx.AsyncClient", _FakeAsyncClient)
    # Leads requires a configured API key to reach the upstream at all;
    # empty-key behavior is covered in its own dedicated test.
    monkeypatch.setattr(settings, "brevo_api_key", "test-key-xyz")
    monkeypatch.setattr(settings, "brevo_list_id", 4)
    yield


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_contact_returns_ok_and_posts_expected_payload(
    client: AsyncClient,
) -> None:
    _FakeAsyncClient.response = _FakeResponse(201)

    resp = await client.post(
        "/api/leads",
        json={
            "email": "Jaap@Example.COM",
            "name": "  Jaap Stronks  ",
            "organization": "Gemeente Utrecht",
            "message": "Interesse in de pilot.",
            "source": "landing",
            "consent": True,
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    # One upstream call, to the Brevo contacts endpoint.
    assert len(_FakeAsyncClient.calls) == 1
    call = _FakeAsyncClient.calls[0]
    assert call["url"] == "https://api.brevo.com/v3/contacts"

    payload = call["json"]
    # Email normalized: lowercased + trimmed.
    assert payload["email"] == "jaap@example.com"
    # listIds comes from settings.
    assert payload["listIds"] == [4]
    # updateEnabled makes resubmits idempotent — ships-blocking if dropped.
    assert payload["updateEnabled"] is True
    # Attributes mapped through _build_brevo_payload; FIRSTNAME is the
    # trimmed `name` field — no best-effort first/last split.
    attrs = payload["attributes"]
    assert attrs["SOURCE"] == "landing"
    assert attrs["FIRSTNAME"] == "Jaap Stronks"
    assert attrs["COMPANY"] == "Gemeente Utrecht"
    assert attrs["MESSAGE"] == "Interesse in de pilot."

    # API key threaded through as a header — never as a query param.
    headers = call["headers"]
    assert headers["api-key"] == "test-key-xyz"


@pytest.mark.asyncio
async def test_email_only_payload_omits_optional_attributes(
    client: AsyncClient,
) -> None:
    """Blank optional fields must collapse to missing keys, not empty strings."""
    _FakeAsyncClient.response = _FakeResponse(201)

    resp = await client.post(
        "/api/leads",
        json={
            "email": "a@b.nl",
            "name": "   ",  # all-whitespace → should be dropped
            "organization": "",
            "message": None,
            "source": "post-export",
            "consent": True,
        },
    )

    assert resp.status_code == 200
    attrs = _FakeAsyncClient.calls[0]["json"]["attributes"]
    assert "FIRSTNAME" not in attrs
    assert "COMPANY" not in attrs
    assert "MESSAGE" not in attrs
    assert attrs["SOURCE"] == "post-export"


@pytest.mark.asyncio
async def test_204_from_brevo_is_success(client: AsyncClient) -> None:
    """Brevo returns 204 when `updateEnabled: true` updates an existing
    contact. That is a normal success path, not an error."""
    _FakeAsyncClient.response = _FakeResponse(204)

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Client-side validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_consent_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": False},
    )
    assert resp.status_code == 400
    # Must not have reached Brevo.
    assert _FakeAsyncClient.calls == []


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
        json={"email": bad_email, "source": "landing", "consent": True},
    )
    assert resp.status_code == 400
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_oversized_email_400(client: AsyncClient) -> None:
    long_email = ("a" * 400) + "@example.nl"
    resp = await client.post(
        "/api/leads",
        json={"email": long_email, "source": "landing", "consent": True},
    )
    assert resp.status_code == 400
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_invalid_source_422(client: AsyncClient) -> None:
    """`source` is a Literal — Pydantic rejects anything else as 422."""
    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "guerilla-marketing", "consent": True},
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
    """Operator misconfig — the endpoint must fail loud and not reach
    the network. `_patch_brevo` already set a key; override it back to
    empty for this one test."""
    monkeypatch.setattr(settings, "brevo_api_key", "")

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 500
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_duplicate_parameter_is_silent_success(client: AsyncClient) -> None:
    """A 400 with code=duplicate_parameter must look the same as a fresh
    insert so the form cannot be used to probe list membership."""
    _FakeAsyncClient.response = _FakeResponse(
        400, {"code": "duplicate_parameter", "message": "Contact already exists"}
    )

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_generic_400_from_brevo_becomes_502(client: AsyncClient) -> None:
    """A 400 that isn't the duplicate sentinel is an unexpected shape
    from the upstream — map to 502, not 200."""
    _FakeAsyncClient.response = _FakeResponse(
        400, {"code": "invalid_parameter", "message": "something else"}
    )

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_code", [401, 403])
async def test_brevo_auth_error_returns_500(
    client: AsyncClient, auth_code: int
) -> None:
    """Revoked / misconfigured API key. The user sees a generic 500 and
    the server logs loudly — we explicitly do NOT surface 401/403 to the
    form, because that would let the page distinguish auth failures from
    other outages and leak account state."""
    _FakeAsyncClient.response = _FakeResponse(auth_code, {"code": "unauthorized"})

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_brevo_rate_limit_returns_503(client: AsyncClient) -> None:
    _FakeAsyncClient.response = _FakeResponse(429, {"code": "too_many_requests"})

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_brevo_5xx_returns_502(client: AsyncClient) -> None:
    _FakeAsyncClient.response = _FakeResponse(500, {"code": "internal_error"})

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_brevo_transport_error_returns_502(client: AsyncClient) -> None:
    """Network-level failure (DNS, timeout, connection refused) before
    we even get a response object."""
    _FakeAsyncClient.raise_on_post = httpx.ConnectError("boom")

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_brevo_non_json_error_body_still_502(client: AsyncClient) -> None:
    """Brevo occasionally returns HTML error pages. The JSON probe must
    swallow ValueError without crashing the handler."""
    _FakeAsyncClient.response = _FakeResponse(502, json_body=None)

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "consent": True},
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
    'a lead came in from source X' — no email, no name, no message. If a
    future edit sneaks any of those into a log line, this test catches it."""
    _FakeAsyncClient.response = _FakeResponse(201)

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
                "consent": True,
            },
        )
    assert resp.status_code == 200

    combined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_email not in combined
    assert secret_name not in combined
    assert secret_org not in combined
    assert secret_message not in combined
