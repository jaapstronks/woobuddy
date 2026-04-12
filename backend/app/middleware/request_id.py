"""Request-id middleware.

Generates a UUID per incoming HTTP request, binds it into structlog's
contextvars so every log emitted during the request automatically carries
`request_id`, and returns it on the response as `X-Request-ID` so the
client (and any upstream proxy) can correlate logs.

Auth is not wired up yet, so `user_id` and `organization_id` are bound as
empty strings for now. When auth lands, populate them from the session.

CRITICAL: this middleware must NEVER read the request body, and must never
log it. It only inspects headers and method/path metadata.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger("http")

# Endpoints that handle sensitive document content. We intentionally log
# request *metadata* for these (method, path, status, duration) but never
# the body — and this tuple exists so callers and auditors can trivially
# confirm the list of protected paths.
SENSITIVE_PATH_PREFIXES: tuple[str, ...] = (
    "/api/analyze",
    "/api/documents",  # covers /api/documents/{id}/export/redact-stream
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Honour an inbound X-Request-ID if the client sent one (useful for
        # tracing through a reverse proxy), otherwise mint a new UUID.
        incoming = request.headers.get("x-request-id")
        request_id = incoming or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            # Auth is not implemented yet — placeholders so the fields exist
            # in every log entry and future me doesn't have to add them later.
            user_id="",
            organization_id="",
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Unhandled exception — log with request metadata only (no body)
            # and re-raise so FastAPI's error handling kicks in.
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log.error(
                "http.request.unhandled_exception",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                exc_info=True,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        # Access log — metadata only. Never include body.
        log.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
