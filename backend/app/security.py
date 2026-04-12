"""Security primitives: rate limiting, CSP headers, proxy-secret verification.

Centralizing these here keeps `main.py` readable and lets tests override the
limiter or disable it.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

# `get_remote_address` keys on the direct client IP. When the app is behind
# a reverse proxy, the proxy should strip untrusted `X-Forwarded-For` headers
# — we intentionally do NOT trust client-supplied headers for rate limiting.
#
# Default limit applies to every route; individual endpoints can tighten it
# via `@limiter.limit("...")`.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    headers_enabled=True,
    strategy="fixed-window",
)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> Response:
    """Return a 429 without echoing any request body content."""
    return Response(
        content='{"detail":"Te veel verzoeken. Probeer het later opnieuw."}',
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        media_type="application/json",
        headers={"Retry-After": "60"},
    )


# ---------------------------------------------------------------------------
# Security headers (CSP, etc.)
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach conservative security headers to every response.

    The frontend (SvelteKit) sets its own CSP for the HTML shell. The API
    responses get a locked-down CSP that forbids rendering as a document at
    all — the API never serves HTML.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            # API responses are JSON only; block everything else.
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        return response


# ---------------------------------------------------------------------------
# Proxy shared-secret verification
# ---------------------------------------------------------------------------

_PROXY_HEADER = "x-woobuddy-proxy-secret"


async def verify_proxy_secret(request: Request) -> None:
    """Reject API calls that did not come from the SvelteKit proxy.

    The SvelteKit server-side fetch hook attaches the shared secret header;
    browsers cannot forge it because they cannot set custom headers cross-
    origin without CORS pre-flight (which the backend does not permit from
    arbitrary origins).

    When `proxy_shared_secret` is empty (local dev without SvelteKit proxy
    in the loop), verification is skipped and a warning is logged once.
    """
    expected = settings.proxy_shared_secret
    if not expected:
        return

    received = request.headers.get(_PROXY_HEADER, "")
    if not secrets.compare_digest(received, expected):
        # Do NOT echo the received value — treat it as potential credential.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Onbevoegd",
        )


__all__ = [
    "SecurityHeadersMiddleware",
    "limiter",
    "rate_limit_exceeded_handler",
    "verify_proxy_secret",
]
