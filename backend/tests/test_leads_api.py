"""HTTP tests for the public contact endpoint (Scaleway TEM).

`backend/app/api/leads.py` is public, unauthenticated, and fires up to
two upstream calls in a specific order, both to Scaleway TEM `/emails`:

1. The operator notification — always, so a message is never lost.
2. The newsletter confirmation to the *submitter* — only when
   `newsletter_opt_in` is true and the opt-in is fully configured.

Nothing reaches Listmonk from this endpoint any more (#76): the address
only gets to the list once the recipient clicks the signed link, which
`test_leads_confirm.py` covers.

The upstream is faked with a tiny `_FakeAsyncClient` that records calls
and returns canned responses. Because both sends go to the same URL,
tests that need the two calls to differ push a queue of responses for
that URL rather than a single one.
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
from app.services.lead_tokens import read_token

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
# Upstream fake (Scaleway TEM + Listmonk)
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

    Tests set per-URL responses via `responses[url] = _FakeResponse(...)`,
    or a per-call sequence via `response_queues[url] = [...]` when the
    same URL is hit twice and the two answers must differ. A missing
    entry falls back to `default_response`.
    """

    default_response: _FakeResponse = _FakeResponse(200)
    responses: dict[str, _FakeResponse] = {}
    response_queues: dict[str, list[_FakeResponse]] = {}
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

    async def post(self, url: str, *, json: Any = None, headers: Any = None) -> _FakeResponse:
        _FakeAsyncClient.calls.append({"url": url, "json": json, "headers": headers})
        if _FakeAsyncClient.raise_on_post is not None:
            raise _FakeAsyncClient.raise_on_post
        queue = _FakeAsyncClient.response_queues.get(url)
        if queue:
            return queue.pop(0)
        return _FakeAsyncClient.responses.get(url, _FakeAsyncClient.default_response)


_TEM_REGION = "fr-par"
_TEM_URL = f"https://api.scaleway.com/transactional-email/v1alpha1/regions/{_TEM_REGION}/emails"
_LISTMONK_BASE = "https://listmonk.dreamkit.eu"
_LIST_UUID = "test-uuid-abc"


@pytest.fixture(autouse=True)
def _patch_upstreams(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _FakeAsyncClient.default_response = _FakeResponse(200)
    _FakeAsyncClient.responses = {}
    _FakeAsyncClient.response_queues = {}
    _FakeAsyncClient.raise_on_post = None
    _FakeAsyncClient.calls = []
    monkeypatch.setattr("app.api.leads.httpx.AsyncClient", _FakeAsyncClient)
    # The endpoint bails out on a missing secret key; set one so the happy
    # path can proceed. Empty-key behavior has a dedicated test below.
    monkeypatch.setattr(settings, "scaleway_secret_key", "test-key-xyz")
    monkeypatch.setattr(settings, "scaleway_project_id", "proj-123")
    monkeypatch.setattr(settings, "scaleway_tem_region", _TEM_REGION)
    monkeypatch.setattr(settings, "tem_from_email", "hallo@example.nl")
    monkeypatch.setattr(settings, "tem_from_name", "WOO Buddy")
    monkeypatch.setattr(settings, "notification_email", "ops@example.nl")
    monkeypatch.setattr(settings, "listmonk_url", _LISTMONK_BASE)
    monkeypatch.setattr(settings, "listmonk_list_uuid", _LIST_UUID)
    # Opt-in needs both halves configured; individual tests unset one to
    # exercise the degradation path.
    monkeypatch.setattr(settings, "listmonk_api_user", "woobuddy-api")
    monkeypatch.setattr(settings, "listmonk_api_token", "listmonk-token")
    monkeypatch.setattr(settings, "leads_confirm_secret", "confirm-secret")
    monkeypatch.setattr(settings, "public_site_url", "https://woobuddy.test")
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

    # Exactly one upstream call — the operator notification. No opt-in mail.
    assert len(_FakeAsyncClient.calls) == 1
    tem = _calls_to(_TEM_URL)
    assert len(tem) == 1

    payload = tem[0]["json"]
    assert payload["to"] == [{"email": "ops@example.nl"}]
    assert payload["from"] == {"email": "hallo@example.nl", "name": "WOO Buddy"}
    assert payload["project_id"] == "proj-123"
    # Reply-To is the submitter's normalized address (with name) so the
    # inbox reply button Just Works.
    assert payload["additional_headers"] == [
        {"key": "Reply-To", "value": '"Jaap Stronks" <jaap@example.com>'}
    ]
    assert "Jaap Stronks" in payload["subject"]
    assert "Interesse in de pilot." in payload["html"]
    assert "Interesse in de pilot." in payload["text"]
    assert "Nee" in payload["html"]

    # Secret key goes through as the X-Auth-Token header, never a query param.
    assert tem[0]["headers"]["X-Auth-Token"] == "test-key-xyz"


# ---------------------------------------------------------------------------
# Happy path — newsletter opt-in mails the submitter a confirmation link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_newsletter_opt_in_mails_a_confirmation_to_the_submitter(
    client: AsyncClient,
) -> None:
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

    # Two sends, both through TEM: the operator notification first, then
    # the confirmation to the submitter.
    tem = _calls_to(_TEM_URL)
    assert len(tem) == 2
    assert tem[0]["json"]["to"] == [{"email": "ops@example.nl"}]

    confirmation = tem[1]["json"]
    assert confirmation["to"] == [{"email": "a@b.nl"}]
    assert confirmation["subject"] == ("Bevestig je e-mailadres voor updates over WOO Buddy")
    assert confirmation["from"] == {"email": "hallo@example.nl", "name": "WOO Buddy"}


@pytest.mark.asyncio
async def test_confirmation_link_points_at_the_site_with_a_token(
    client: AsyncClient,
) -> None:
    """The button must land on woobuddy.nl, not on the API or on Listmonk."""
    await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "newsletter_opt_in": True},
    )

    body = _calls_to(_TEM_URL)[1]["json"]
    assert "https://woobuddy.test/nieuwsbrief/bevestigen?t=" in body["text"]
    assert "https://woobuddy.test/nieuwsbrief/bevestigen?t=" in body["html"]

    # The token round-trips back to the submitted address (#76).
    token = body["text"].split("bevestigen?t=", 1)[1].split()[0]
    assert read_token(token, secret="confirm-secret") == "a@b.nl"


@pytest.mark.asyncio
async def test_confirmation_mail_mentions_no_other_brand_or_list_name(
    client: AsyncClient,
) -> None:
    """The whole point of #76 — the mail this replaced said "DREAMKIT
    UPDATES" and named a list called "WOO Buddy — leads"."""
    await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "newsletter_opt_in": True},
    )

    body = _calls_to(_TEM_URL)[1]["json"]
    for part in (body["html"], body["text"], body["subject"]):
        lowered = part.lower()
        assert "dreamkit" not in lowered
        assert "listmonk" not in lowered
        assert "leads" not in lowered


@pytest.mark.asyncio
async def test_newsletter_opt_in_defaults_to_false(client: AsyncClient) -> None:
    """Missing field in the body must NOT mail the submitter anything."""
    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 200
    assert len(_calls_to(_TEM_URL)) == 1


@pytest.mark.asyncio
async def test_nothing_reaches_listmonk_from_the_form(client: AsyncClient) -> None:
    """Consent is not consent until the link is clicked: the submit path
    must not touch the list at all."""
    await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "newsletter_opt_in": True},
    )

    assert all(_LISTMONK_BASE not in c["url"] for c in _FakeAsyncClient.calls)


# ---------------------------------------------------------------------------
# Opt-in degradation — an unconfigured integration never costs the operator
# the notification mail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unset",
    ["leads_confirm_secret", "listmonk_api_token", "listmonk_api_user", "listmonk_list_uuid"],
)
async def test_opt_in_is_skipped_when_unconfigured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    unset: str,
) -> None:
    monkeypatch.setattr(settings, unset, "")

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing", "newsletter_opt_in": True},
    )

    # The message still got delivered; only the opt-in was dropped.
    assert resp.status_code == 200
    assert len(_calls_to(_TEM_URL)) == 1
    # structlog renders to stdout, so the warning shows up in capsys.
    assert "leads.opt_in_skipped" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_failed_confirmation_send_does_not_fail_the_submission(
    client: AsyncClient,
) -> None:
    """The operator's notification is already out by then. A visitor
    should not see an error for a checkbox they ticked in passing."""
    _FakeAsyncClient.response_queues = {
        _TEM_URL: [_FakeResponse(200), _FakeResponse(500, {"message": "boom"})]
    }

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
# Upstream error mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_secret_key_returns_500_without_network_call(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "scaleway_secret_key", "")

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 500
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_code", [401, 403])
async def test_tem_auth_error_returns_500(client: AsyncClient, auth_code: int) -> None:
    """Revoked / misconfigured secret key on the transactional endpoint.
    We explicitly do NOT surface 401/403 so the form can't distinguish
    auth failures from other outages and leak account state."""
    _FakeAsyncClient.responses = {_TEM_URL: _FakeResponse(auth_code, {"message": "unauthorized"})}

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 500
    # Only the notification was attempted; nothing follows a failed send.
    assert len(_calls_to(_TEM_URL)) == 1


@pytest.mark.asyncio
async def test_tem_rate_limit_returns_503(client: AsyncClient) -> None:
    _FakeAsyncClient.responses = {_TEM_URL: _FakeResponse(429, {"message": "too_many_requests"})}

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_tem_5xx_returns_502(client: AsyncClient) -> None:
    _FakeAsyncClient.responses = {_TEM_URL: _FakeResponse(500, {"message": "internal_error"})}

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_tem_transport_error_returns_502(client: AsyncClient) -> None:
    """Network-level failure (DNS, timeout, connection refused) before
    we even get a response object."""
    _FakeAsyncClient.raise_on_post = httpx.ConnectError("boom")

    resp = await client.post(
        "/api/leads",
        json={"email": "a@b.nl", "source": "landing"},
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_tem_non_json_error_body_still_502(client: AsyncClient) -> None:
    """A non-JSON error body must not crash the handler (the code never
    parses the body — any non-2xx maps deterministically)."""
    _FakeAsyncClient.responses = {_TEM_URL: _FakeResponse(502, json_body=None)}

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


# ---------------------------------------------------------------------------
# Header injection (#72)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crlf_in_name_cannot_inject_a_mail_header(
    client: AsyncClient,
) -> None:
    """A newline in `name` must not reach Subject or Reply-To.

    `name` is interpolated into both headers. Without a filter, a
    submitter could terminate the header and append their own — a Bcc
    that quietly copies every lead somewhere else, say.
    """
    resp = await client.post(
        "/api/leads",
        json={
            "email": "attacker@example.nl",
            "name": "Ada\r\nBcc: exfil@evil.example\r\nX-Injected: 1",
            "source": "landing",
            "newsletter_opt_in": False,
        },
    )

    assert resp.status_code == 200, resp.text
    payload = _calls_to(_TEM_URL)[0]["json"]

    reply_to = payload["additional_headers"][0]["value"]
    subject = payload["subject"]

    for field in (reply_to, subject):
        assert "\r" not in field
        assert "\n" not in field
    # The words survive (we neutralize rather than truncate), but they sit
    # on one line inside the quoted display name, so they are no longer
    # headers — just text.
    assert reply_to == '"Ada Bcc: exfil@evil.example X-Injected: 1" <attacker@example.nl>'
    assert "Bcc: exfil@evil.example" in subject
    # Exactly one quoted display name — an unescaped quote in `name` would
    # otherwise let the submitter close it early.
    assert reply_to.count('"') == 2


@pytest.mark.asyncio
async def test_quotes_in_name_do_not_break_the_reply_to_display_name(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/leads",
        json={
            "email": "a@b.nl",
            "name": 'Ada" <root@evil.example> "',
            "source": "landing",
            "newsletter_opt_in": False,
        },
    )

    assert resp.status_code == 200, resp.text
    reply_to = _calls_to(_TEM_URL)[0]["json"]["additional_headers"][0]["value"]
    assert reply_to.count('"') == 2
    assert reply_to.endswith("<a@b.nl>")
    assert "root@evil.example" not in reply_to.split("<")[-1]


@pytest.mark.asyncio
async def test_crlf_in_organization_is_stripped_from_the_subject(
    client: AsyncClient,
) -> None:
    """`organization` reaches the Subject when no name is given."""
    resp = await client.post(
        "/api/leads",
        json={
            "email": "a@b.nl",
            "organization": "Gemeente\nSubject: hijacked",
            "source": "landing",
            "newsletter_opt_in": False,
        },
    )

    assert resp.status_code == 200, resp.text
    subject = _calls_to(_TEM_URL)[0]["json"]["subject"]
    assert "\n" not in subject
    assert "\r" not in subject


@pytest.mark.asyncio
async def test_newlines_in_message_are_preserved(client: AsyncClient) -> None:
    """The body is not a header: a multi-line message must stay multi-line.

    Guards the header filter against over-reach — `message` is escaped and
    rendered `pre-wrap`, so its newlines carry meaning.
    """
    resp = await client.post(
        "/api/leads",
        json={
            "email": "a@b.nl",
            "message": "Regel een.\nRegel twee.",
            "source": "landing",
            "newsletter_opt_in": False,
        },
    )

    assert resp.status_code == 200, resp.text
    payload = _calls_to(_TEM_URL)[0]["json"]
    assert "Regel een.\nRegel twee." in payload["text"]
