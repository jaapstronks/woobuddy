"""Rate-limit buckets behind the reverse proxy.

In production every request reaches uvicorn from Caddy's container. These
tests run the real `limiter` behind uvicorn's `ProxyHeadersMiddleware`,
configured with the FORWARDED_ALLOW_IPS value from docker-compose.prod.yml,
and check that two visitors get two buckets while a visitor who is not the
proxy cannot choose its own key via X-Forwarded-For.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi import FastAPI, Request, Response
from slowapi.errors import RateLimitExceeded
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.security import limiter, rate_limit_exceeded_handler

COMPOSE_PROD = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
CADDY_IP = "172.18.0.4"  # a typical address in a compose network


def _forwarded_allow_ips() -> str:
    compose = yaml.safe_load(COMPOSE_PROD.read_text())
    for entry in compose["services"]["api"]["environment"]:
        key, _, value = entry.partition("=")
        if key == "FORWARDED_ALLOW_IPS":
            return value
    raise AssertionError("FORWARDED_ALLOW_IPS missing from the api service")


def _app() -> ProxyHeadersMiddleware:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

    @app.get("/probe")
    @limiter.limit("1/minute")
    async def probe(request: Request, response: Response) -> dict[str, str]:
        assert request.client is not None
        return {"client": request.client.host}

    return ProxyHeadersMiddleware(app, trusted_hosts=_forwarded_allow_ips())


# Built once: slowapi registers limits per route name, so a second build
# would stack a second 1/minute limit on the same key.
APP = _app()


@pytest.fixture(autouse=True)
def _fresh_limiter() -> Iterator[None]:
    original = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()
        limiter.enabled = original


def _client(peer: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=APP, client=(peer, 40000))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_client_host_is_the_visitor_behind_the_proxy() -> None:
    async with _client(CADDY_IP) as client:
        response = await client.get("/probe", headers={"X-Forwarded-For": "203.0.113.7"})
    assert response.json() == {"client": "203.0.113.7"}


async def test_two_visitors_get_two_buckets() -> None:
    async with _client(CADDY_IP) as client:
        first = await client.get("/probe", headers={"X-Forwarded-For": "203.0.113.7"})
        again = await client.get("/probe", headers={"X-Forwarded-For": "203.0.113.7"})
        other = await client.get("/probe", headers={"X-Forwarded-For": "198.51.100.23"})
    assert first.status_code == 200
    assert again.status_code == 429
    assert other.status_code == 200


async def test_untrusted_peer_cannot_pick_its_own_key() -> None:
    async with _client("203.0.113.7") as client:
        first = await client.get("/probe", headers={"X-Forwarded-For": "198.51.100.1"})
        spoofed = await client.get("/probe", headers={"X-Forwarded-For": "198.51.100.2"})
    assert first.json() == {"client": "203.0.113.7"}
    assert spoofed.status_code == 429
