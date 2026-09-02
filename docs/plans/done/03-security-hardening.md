# 03 — Security Hardening ✅

- **Priority:** P0
- **Size:** M (1–3 days)
- **Source:** Testing & Polish briefing, Section 9
- **Depends on:** #00 (Client-first architecture — security model changes significantly)
- **Blocks:** Production deployment
- **Status:** Done (2026-04-13)

## What shipped

- `verifyPdfMagicBytes()` in `frontend/src/lib/services/pdf-text-extractor.ts` — rejects non-PDF uploads client-side before pdf.js runs. Wired into `/try`.
- `backend/app/security.py` — new module with:
  - `slowapi` limiter (default `100/minute`, `30/minute` on `/api/analyze`, `10/minute` on `/api/documents/{id}/export/redact-stream`), `429` responses with a Dutch message.
  - `SecurityHeadersMiddleware` — strict `Content-Security-Policy: default-src 'none'` on every API response plus `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`.
  - `verify_proxy_secret` dependency — compares the `x-woobuddy-proxy-secret` header against `settings.proxy_shared_secret` using `secrets.compare_digest`. A no-op while the env var is empty so local dev keeps working.
- `Detection.entity_text` column removed. A SQLAlchemy `init` event hook rejects any future attempt to set that kwarg, and a `CheckConstraint` bounds `reasoning` length. The API response schema and frontend type both made `entity_text` optional; the client already reconstructs it from local extraction via `bbox-text-resolver.ts`.
- `pdf_engine.PdfValidationError` wraps `fitz.open()`. `export.py` magic-byte checks the incoming stream and surfaces a clean `400` if PyMuPDF rejects it — no parser output reaches clients.
- `frontend/src/hooks.server.ts` — SvelteKit server hook sets a strict CSP on HTML responses and `handleFetch` attaches `x-woobuddy-proxy-secret` on SSR backend calls when `PRIVATE_API_PROXY_SECRET` is set (ready for the future SvelteKit proxy path).
- Analyze/export endpoints still do not log request bodies; only IDs, counts, and sizes are logged via structlog.

## Deferred (out of scope for this todo)

- PostgreSQL Row-Level Security — reevaluated with #25 (Organizations).
- Audit log append-only enforcement — there is no audit-log table yet.
- Sentry/GlitchTip body exclusion — no error reporter is wired up yet; revisit when it is.
- Browser → backend proxy secret enforcement — turns on when the frontend routes API calls through the SvelteKit server (lands with #24 Authentication). The backend dependency is already in place.

## Why

This tool processes privacy-sensitive government documents. Security isn't optional — a data leak is a career-ending event for the civil servant who used the tool.

## Scope

### File validation (client-side, since PDFs live in the browser)

- [ ] Verify files are actually PDFs by reading magic bytes (`%PDF-`) client-side before loading into pdf.js
- [ ] Reject non-PDF files even if the extension is `.pdf`
- [ ] Server-side: validate the PDF stream during ephemeral export (`fitz.open()` in try/catch) — but the original is never stored

### Content Security Policy

- [ ] Set strict CSP header: scripts only from application origin + cdn.jsdelivr.net (Shoelace)
- [ ] Block inline scripts

### Rate limiting

- [ ] Add `slowapi` or similar to FastAPI
- [ ] Key rates: 100 API calls/min per user, 5 file uploads/min per organization, 10 signups/hour per IP (once auth exists)

### Document isolation (prep for auth)

- [ ] Ensure every database query touching dossiers/documents/detections filters by ownership
- [ ] Add placeholder for `organization_id` scoping (actual enforcement in #25)
- [ ] Consider PostgreSQL Row-Level Security as defense-in-depth (evaluate, don't necessarily implement yet)

### Ephemeral processing security (client-first specific)

- [ ] The `/api/analyze` endpoint must NOT log request bodies (they contain extracted document text)
- [ ] The `/api/export/redact` endpoint must NOT write the PDF stream to disk — process entirely in memory
- [ ] Error handlers must NOT echo input text in error responses or stack traces
- [ ] Sentry/GlitchTip: exclude request body from error reports on analyze/export endpoints
- [ ] Detection records in PostgreSQL must never contain `entity_text` — enforce via schema constraint or application-level check

### Audit log integrity

- [ ] Ensure audit log table has no DELETE or UPDATE operations exposed via API
- [ ] Append-only enforcement at the application layer

### CSRF

- [ ] Verify SvelteKit's built-in CSRF protection is active for form actions
- [ ] For API proxy calls, ensure FastAPI only accepts requests from the SvelteKit proxy (shared secret header or internal network restriction)

## Acceptance Criteria

- Opening a `.pdf` file that is actually a JPEG is rejected client-side
- CSP header is present on all responses
- Rapid-fire API calls (>100/min) get rate-limited with a 429 response
- Audit log entries cannot be deleted via any API endpoint

## Not in Scope

- Full organization-scoped Row-Level Security (needs auth first)
- Penetration testing (future, pre-launch)
- End-to-end encryption of metadata (the metadata stored is non-sensitive by design)
