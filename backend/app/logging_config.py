"""Structured logging configuration for WOO Buddy.

Every log entry is rendered as a JSON object with a consistent shape:

    {
      "timestamp": "2026-04-13T10:12:34.567Z",
      "level": "info",
      "event": "document.registered",
      "request_id": "4e0c...",
      "user_id": "",
      "organization_id": "",
      ...extra fields...
    }

Request-scoped fields (`request_id`, `user_id`, `organization_id`) are bound
via :mod:`structlog.contextvars` by the request-id middleware, so every log
call made while handling a request automatically carries them without the
caller having to pass them explicitly.

CRITICAL: the logging pipeline deliberately does not process request bodies.
Routes that handle document content (`/api/analyze`, `/api/export/...`) must
never pass the raw text or PDF bytes to the logger. See `docs/todo/00-client-
first-architecture.md`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars
from structlog.types import EventDict, WrappedLogger


def _ensure_request_scope_fields(
    _logger: WrappedLogger, _method: str, event_dict: EventDict
) -> EventDict:
    """Guarantee request_id/user_id/organization_id are always present.

    The middleware binds these per request; this processor fills in empty
    strings for logs that fire outside of a request (startup, background
    tasks) so downstream consumers can rely on the fields existing.
    """
    event_dict.setdefault("request_id", "")
    event_dict.setdefault("user_id", "")
    event_dict.setdefault("organization_id", "")
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging to emit structured JSON.

    Should be called exactly once at process startup, before any logger is
    used. Safe to call multiple times (idempotent).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        _ensure_request_scope_fields,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, etc.) through structlog too,
    # so third-party libraries emit the same JSON format.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Uvicorn's access logger would log the raw HTTP request line, which is
    # fine, but we disable its default formatter so everything flows through
    # our JSON handler instead. We also silence the access log entirely —
    # request-scoped info is emitted explicitly by the middleware so we don't
    # double-log (and, critically, we never want uvicorn logging bodies).
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(noisy)
        lg.handlers = []
        lg.propagate = True
    # Silence the access log — we emit our own `http.request` events.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger. Thin wrapper for convenience.

    The return type is ``Any`` because structlog's BoundLogger is a runtime
    proxy and mypy cannot statically verify the logging method calls against
    it — typing it more precisely creates more friction than it removes.
    """
    return structlog.get_logger(name)
