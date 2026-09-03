"""HTTP tests for `POST /api/leads/confirm` and the Listmonk client (#76).

This is the half of the double opt-in where consent turns into a list
membership, so the cases worth pinning down are the refusals: a stale
link, a forged one, and a Listmonk that is unreachable or unconfigured.
None of them may raise — the confirmation page renders a sentence per
`status`, so the endpoint always answers 200 with a verdict.

Listmonk is faked at the HTTP level rather than mocked at the function
level, so the tests also assert the *shape* of what we send it: the
`preconfirm_subscriptions` flag is the thing standing between a
confirmed subscriber and Listmonk sending an opt-in mail of its own,
which is the bug #76 exists to remove.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import TracebackType
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.config import settings
from app.security import limiter
from app.services.lead_tokens import make_token

_LISTMONK_BASE = "https://listmonk.test"
_LISTS_URL = f"{_LISTMONK_BASE}/api/lists"
_SUBSCRIBERS_URL = f"{_LISTMONK_BASE}/api/subscribers"
_SUBSCRIBER_LISTS_URL = f"{_LISTMONK_BASE}/api/subscribers/lists"
_LIST_UUID = "list-uuid-abc"
_LIST_ID = 7
_SECRET = "confirm-secret"


@pytest.fixture(autouse=True)
def _disable_rate_limiter() -> Iterator[None]:
    original = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = original


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any = None) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def json(self) -> Any:
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body


_LISTS_OK = _FakeResponse(200, {"data": {"results": [{"id": _LIST_ID, "uuid": _LIST_UUID}]}})


class _FakeAsyncClient:
    """Fakes Listmonk over HTTP, recording every call for inspection."""

    get_responses: dict[str, _FakeResponse] = {}
    post_responses: dict[str, _FakeResponse] = {}
    put_responses: dict[str, _FakeResponse] = {}
    raise_on_request: httpx.HTTPError | None = None
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

    def _record(self, method: str, url: str, **kwargs: Any) -> None:
        _FakeAsyncClient.calls.append({"method": method, "url": url, **kwargs})

    async def get(self, url: str, *, headers: Any = None, params: Any = None) -> _FakeResponse:
        self._record("GET", url, headers=headers, params=params)
        if _FakeAsyncClient.raise_on_request is not None:
            raise _FakeAsyncClient.raise_on_request
        return _FakeAsyncClient.get_responses.get(url, _FakeResponse(404))

    async def post(self, url: str, *, json: Any = None, headers: Any = None) -> _FakeResponse:
        self._record("POST", url, json=json, headers=headers)
        if _FakeAsyncClient.raise_on_request is not None:
            raise _FakeAsyncClient.raise_on_request
        return _FakeAsyncClient.post_responses.get(url, _FakeResponse(404))

    async def put(self, url: str, *, json: Any = None, headers: Any = None) -> _FakeResponse:
        self._record("PUT", url, json=json, headers=headers)
        if _FakeAsyncClient.raise_on_request is not None:
            raise _FakeAsyncClient.raise_on_request
        return _FakeAsyncClient.put_responses.get(url, _FakeResponse(404))


@pytest.fixture(autouse=True)
def _patch_listmonk(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _FakeAsyncClient.get_responses = {_LISTS_URL: _LISTS_OK}
    _FakeAsyncClient.post_responses = {_SUBSCRIBERS_URL: _FakeResponse(200, {"data": {}})}
    _FakeAsyncClient.put_responses = {}
    _FakeAsyncClient.raise_on_request = None
    _FakeAsyncClient.calls = []
    monkeypatch.setattr("app.api.leads.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(settings, "listmonk_url", _LISTMONK_BASE)
    monkeypatch.setattr(settings, "listmonk_list_uuid", _LIST_UUID)
    monkeypatch.setattr(settings, "listmonk_api_user", "woobuddy-api")
    monkeypatch.setattr(settings, "listmonk_api_token", "listmonk-token")
    monkeypatch.setattr(settings, "leads_confirm_secret", _SECRET)
    yield


def _calls(method: str, url: str) -> list[dict[str, Any]]:
    return [c for c in _FakeAsyncClient.calls if c["method"] == method and c["url"] == url]


def _token(email: str = "a@b.nl", **kwargs: Any) -> str:
    return make_token(email, secret=_SECRET, **kwargs)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_token_subscribes_and_reports_confirmed(
    client: AsyncClient,
) -> None:
    resp = await client.post("/api/leads/confirm", json={"token": _token()})

    assert resp.status_code == 200
    assert resp.json() == {"status": "confirmed"}

    posted = _calls("POST", _SUBSCRIBERS_URL)
    assert len(posted) == 1
    payload = posted[0]["json"]
    assert payload["email"] == "a@b.nl"
    assert payload["lists"] == [_LIST_ID]
    assert payload["status"] == "enabled"
    # Without this flag Listmonk sends its own (Dreamkit-branded) opt-in
    # mail — the exact bug #76 removes.
    assert payload["preconfirm_subscriptions"] is True


@pytest.mark.asyncio
async def test_api_credentials_travel_in_the_auth_header(client: AsyncClient) -> None:
    """Never in a query string: it would land in Listmonk's access log."""
    await client.post("/api/leads/confirm", json={"token": _token()})

    headers = _calls("POST", _SUBSCRIBERS_URL)[0]["headers"]
    assert headers["Authorization"] == "token woobuddy-api:listmonk-token"
    params = _calls("GET", _LISTS_URL)[0]["params"]
    assert "listmonk-token" not in str(params)


@pytest.mark.asyncio
async def test_list_uuid_is_resolved_to_the_numeric_id(client: AsyncClient) -> None:
    """`.env` carries the UUID (stable across restores); Listmonk's
    subscribe endpoint wants the integer id."""
    _FakeAsyncClient.get_responses = {
        _LISTS_URL: _FakeResponse(
            200,
            {
                "data": {
                    "results": [
                        {"id": 3, "uuid": "some-other-list"},
                        {"id": _LIST_ID, "uuid": _LIST_UUID},
                    ]
                }
            },
        )
    }

    resp = await client.post("/api/leads/confirm", json={"token": _token()})

    assert resp.json() == {"status": "confirmed"}
    assert _calls("POST", _SUBSCRIBERS_URL)[0]["json"]["lists"] == [_LIST_ID]


# ---------------------------------------------------------------------------
# Already-known address (the returning visitor)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_attaches_the_list_to_the_existing_subscriber(
    client: AsyncClient,
) -> None:
    _FakeAsyncClient.post_responses = {
        _SUBSCRIBERS_URL: _FakeResponse(409, {"message": "e-mail already exists"})
    }
    _FakeAsyncClient.get_responses = {
        _LISTS_URL: _LISTS_OK,
        _SUBSCRIBERS_URL: _FakeResponse(200, {"data": {"results": [{"id": 42}]}}),
    }
    _FakeAsyncClient.put_responses = {_SUBSCRIBER_LISTS_URL: _FakeResponse(200, {"data": True})}

    resp = await client.post("/api/leads/confirm", json={"token": _token()})

    # Same verdict as a fresh subscribe — the visitor did the same thing.
    assert resp.json() == {"status": "confirmed"}

    put = _calls("PUT", _SUBSCRIBER_LISTS_URL)[0]["json"]
    assert put == {
        "ids": [42],
        "action": "add",
        "target_list_ids": [_LIST_ID],
        "status": "confirmed",
    }


@pytest.mark.asyncio
async def test_quotes_in_an_address_do_not_break_the_lookup(
    client: AsyncClient,
) -> None:
    """Listmonk's `query` param is a raw SQL fragment. `o'brien@x.nl` is a
    legal address, so the quote has to be escaped rather than passed on."""
    _FakeAsyncClient.post_responses = {_SUBSCRIBERS_URL: _FakeResponse(409, {})}
    _FakeAsyncClient.get_responses = {
        _LISTS_URL: _LISTS_OK,
        _SUBSCRIBERS_URL: _FakeResponse(200, {"data": {"results": [{"id": 42}]}}),
    }
    _FakeAsyncClient.put_responses = {_SUBSCRIBER_LISTS_URL: _FakeResponse(200)}

    await client.post(
        "/api/leads/confirm",
        json={"token": _token("o'brien@example.nl")},
    )

    query = _calls("GET", _SUBSCRIBERS_URL)[0]["params"]["query"]
    assert query == "subscribers.email = 'o''brien@example.nl'"


# ---------------------------------------------------------------------------
# Token refusals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_token_reports_expired_and_touches_nothing(
    client: AsyncClient,
) -> None:
    stale = make_token("a@b.nl", secret=_SECRET, ttl_seconds=1, now=0)

    resp = await client.post("/api/leads/confirm", json={"token": stale})

    assert resp.status_code == 200
    assert resp.json() == {"status": "expired"}
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_token_signed_with_another_secret_reports_invalid(
    client: AsyncClient,
) -> None:
    forged = make_token("victim@example.nl", secret="not-our-secret")

    resp = await client.post("/api/leads/confirm", json={"token": forged})

    assert resp.json() == {"status": "invalid"}
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["", "   ", "garbage", "a.b", "a.\u00e9", "\u00e9.b"])
async def test_malformed_tokens_report_invalid(client: AsyncClient, token: str) -> None:
    resp = await client.post("/api/leads/confirm", json={"token": token})
    assert resp.json() == {"status": "invalid"}


@pytest.mark.asyncio
async def test_missing_token_field_is_a_422(client: AsyncClient) -> None:
    resp = await client.post("/api/leads/confirm", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Listmonk refusals — never a 5xx at the visitor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unconfigured_listmonk_reports_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "listmonk_api_token", "")

    resp = await client.post("/api/leads/confirm", json={"token": _token()})

    assert resp.status_code == 200
    assert resp.json() == {"status": "unavailable"}


@pytest.mark.asyncio
async def test_rejected_api_user_reports_unavailable(client: AsyncClient) -> None:
    _FakeAsyncClient.get_responses = {_LISTS_URL: _FakeResponse(401, {"message": "nope"})}

    resp = await client.post("/api/leads/confirm", json={"token": _token()})

    assert resp.status_code == 200
    assert resp.json() == {"status": "unavailable"}


@pytest.mark.asyncio
async def test_unknown_list_uuid_reports_unavailable(client: AsyncClient) -> None:
    """A restored Listmonk with a recreated list must not fail silently
    into a wrong list — it fails visibly into `unavailable`."""
    _FakeAsyncClient.get_responses = {
        _LISTS_URL: _FakeResponse(200, {"data": {"results": [{"id": 3, "uuid": "other"}]}})
    }

    resp = await client.post("/api/leads/confirm", json={"token": _token()})

    assert resp.json() == {"status": "unavailable"}
    assert _calls("POST", _SUBSCRIBERS_URL) == []


@pytest.mark.asyncio
async def test_transport_failure_reports_unavailable(client: AsyncClient) -> None:
    _FakeAsyncClient.raise_on_request = httpx.ConnectError("listmonk down")

    resp = await client.post("/api/leads/confirm", json={"token": _token()})

    assert resp.status_code == 200
    assert resp.json() == {"status": "unavailable"}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_confirmed_address_never_reaches_the_logs(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same rule as the submit path: record that it happened, not who."""
    await client.post(
        "/api/leads/confirm",
        json={"token": _token("sentinel-4b21@example.nl")},
    )

    out = capsys.readouterr().out
    assert "leads.confirmed" in out
    assert "sentinel-4b21@example.nl" not in out
