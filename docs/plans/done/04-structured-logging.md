# 04 — Structured Logging ✅

- **Priority:** P1
- **Size:** S (< 1 day)
- **Source:** Testing & Polish briefing, Section 8
- **Depends on:** Nothing
- **Status:** Done (backend). Frontend error-tracking deferred — see below.

## What shipped

### Backend (FastAPI)

- **`structlog` 25.5** added to `backend/pyproject.toml` and configured in `backend/app/logging_config.py`:
  - JSON renderer, ISO-8601 UTC timestamps under the `timestamp` key, log level, event, and a `format_exc_info` processor for clean tracebacks.
  - `merge_contextvars` processor pulls per-request fields (`request_id`, `user_id`, `organization_id`) from `structlog.contextvars` so every log emitted inside a request automatically carries them — no manual plumbing.
  - A `_ensure_request_scope_fields` processor guarantees those three fields are always present (empty string when outside a request, e.g. startup/background), so log consumers can rely on schema stability.
  - Stdlib `logging` is routed through the same `ProcessorFormatter` so uvicorn/sqlalchemy/etc. emit the same JSON.
  - `uvicorn.access` is disabled — we emit our own `http.request` events from the middleware so there is no double-logging and no risk of uvicorn logging things we don't control.
- **Request-id middleware** at `backend/app/middleware/request_id.py`:
  - Generates a UUIDv4 per request (honours an inbound `X-Request-ID` header if present, for proxy tracing).
  - Binds `request_id`, and placeholder `user_id="" / organization_id=""` fields (auth not wired yet) via `structlog.contextvars.bind_contextvars`.
  - Emits `http.request` at INFO on completion with method, path, status, and duration — **metadata only, never the body**.
  - On unhandled exceptions inside the request, emits `http.request.unhandled_exception` at ERROR with the traceback, then re-raises so FastAPI's error handling runs.
  - Sets `X-Request-ID` on the response so the frontend can correlate.
  - Middleware order in `main.py` is documented: Starlette prepends, so `RequestIdMiddleware` is added **last** to be the **outermost** wrapper (runs first on each request, binds contextvars before anything else).
- **Event logs wired throughout the app:**
  - INFO — `document.registered`, `analysis.requested`, `analysis.completed`, `detection.reviewed`, `export.requested`, `export.generated`, `pipeline.started`, `pipeline.ner_completed`, `pipeline.completed`, `llm.provider_selected`, `llm.status`, `ner.deduce_initialized`, `ner.deduce_loaded`, `db.tables_ensured`, `http.request`.
  - WARNING — `llm.unreachable_at_startup`, `ner.deduce_init_failed`, `llm.role_classification.no_tool_call`, `llm.content_analysis.no_tool_call`, `pdf.invalid_stream`.
  - ERROR (via `.exception()`) — `analysis.failed`, `llm.health_probe_raised`, `http.request.unhandled_exception`.
- **Client-first guarantee verified:**
  - The `/api/analyze` route logs only `document_id`, `page_count`, `detection_count`, and `has_environmental_content` — never the extracted text.
  - The `/api/documents/{id}/export/redact-stream` route logs only `document_id`, `pdf_bytes` (size in bytes), `detection_count`, and `redaction_count` — never the PDF bytes themselves.
  - The request-id middleware never reads the body.
  - `uvicorn.access` is fully disabled, removing the default access log that can echo the request line.
- Smoke-tested by calling `configure_logging()` and firing a few log calls; every line is a well-formed JSON object with consistent fields, including the request-scope fields.
- `ruff check` passes on all touched files (pre-existing `E501` warnings in `llm/prompts.py`, `llm/ollama.py`, and `llm/anthropic.py` were not introduced by this change and are out of scope). `mypy app/logging_config.py app/middleware/request_id.py` is clean.
- All 34 non-broken backend tests pass (`tests/test_llm_engine.py` is broken on `main` for unrelated reasons — imports removed `_find_tier3_passages`).

### Frontend (SvelteKit) — deferred

Not implemented in this pass. The todo asked to *evaluate* Sentry vs GlitchTip; that's a product/hosting decision (SaaS vs self-hosted, cost, and especially data-residency for Dutch government users) that shouldn't be made without explicit input. A follow-up todo should cover:

- Vendor decision (Sentry SaaS, Sentry self-hosted, GlitchTip, or bare-bones `window.onerror` → backend endpoint).
- Client-side error capture for unhandled exceptions and failed API calls.
- Source-map upload pipeline.

The frontend already surfaces failed API calls to the user via `$lib/api/client.ts`; what's missing is *reporting* them to an operator dashboard.

## Files touched

- `backend/pyproject.toml` — added `structlog>=24.4.0`
- `backend/app/logging_config.py` — new
- `backend/app/middleware/__init__.py` — new (empty package marker)
- `backend/app/middleware/request_id.py` — new
- `backend/app/main.py` — call `configure_logging()`, install `RequestIdMiddleware`, replace logger, use event-style log keys
- `backend/app/api/analyze.py` — structlog, `analysis.requested` / `analysis.completed` / `analysis.failed`
- `backend/app/api/documents.py` — structlog, `document.registered`
- `backend/app/api/detections.py` — structlog, `detection.reviewed`
- `backend/app/api/export.py` — structlog, `export.requested`, `export.generated`
- `backend/app/services/llm_engine.py` — structlog, `pipeline.*`
- `backend/app/services/ner_engine.py` — structlog
- `backend/app/services/pdf_engine.py` — structlog
- `backend/app/llm/__init__.py` — structlog, `llm.provider_selected`
- `backend/app/llm/ollama.py` — structlog, event-style warnings
- `backend/app/llm/anthropic.py` — structlog, event-style warnings
- `backend/app/security.py` — structlog

## Not in Scope (unchanged)

- Production alerting rules (set up when deploying)
- Log aggregation service setup (depends on hosting choice)
