# CLAUDE.md — WOO Buddy

## Project overview

WOO Buddy helps Dutch government employees redact privacy-sensitive information in Woo (Wet open overheid) documents. It uses a three-tier detection model where each tier has different detection methods, confidence levels, and UX patterns.

- **Tier 1** (hard identifiers): Regex + validation. Auto-redacted. Opt-out by reviewer.
- **Tier 2** (contextual personal data): Deduce NER + wordlists (Meertens voornamen, CBS achternamen) + structure heuristics (e-mailheaders, handtekeningblokken, aanhef) + a rule-based public-official filter. Suggested. One-click confirm/reject.
- **Tier 3** (content judgments): Reserved. **No LLM in the active pipeline.** Kept as a slot for future rule-based content signals (e.g. beleidsopvatting-verdacht zinnen). See `backend/app/llm/README.md` for the dormant revival path.

### No LLM in the live pipeline

As of April 2026 (see `docs/reference/woo-redactietool-analyse.md` and `docs/todo/done/35-deactivate-llm.md`), WOO Buddy runs without any LLM in the default code path. Detection is regex + Deduce + wordlists + structure heuristics. The Ollama provider in `backend/app/llm/` is kept in-tree but dormant — flip `settings.llm_tier2_enabled`/`llm_tier3_enabled` to revive it for experimentation.

Do not reintroduce LLM calls into the live pipeline without an explicit product decision to the contrary. Rule-based replacements for what the LLM used to do (person-role classification, false-positive filtering) live in todos #12–#17.

## Branding

- Always write "WOO Buddy" (WOO in caps, Buddy capitalized) in user-facing text
- Dutch UI language for the application itself
- English for code, comments, commit messages, and documentation

## Client-first architecture (CRITICAL)

**PDFs never leave the user's browser. The server never stores document content.**

This is the foundational architectural principle. Every feature must respect it:

- **Text extraction** happens client-side via pdf.js `getTextContent()`.
- **NER + rule-based analysis** is ephemeral: client sends extracted text → server processes → returns detections → discards text. No LLM is involved.
- **The database stores decisions, not content.** Detection records contain bbox coordinates, entity type, tier, article, review status. They do NOT contain `entity_text`.
- **Export is streaming:** PDF sent to server → PyMuPDF redacts in memory → redacted PDF streamed back → original never written to disk.
- **Server logs must never contain document text.** No logging request bodies on `/api/analyze` or `/api/export/redact`.

Full specification: `docs/todo/00-client-first-architecture.md`

## Architecture

Monorepo with two applications:

- `frontend/` — SvelteKit (Svelte 5 with runes), TypeScript strict, Tailwind CSS v4, Shoelace web components, pdf.js
- `backend/` — FastAPI, Python 3.12, async throughout

Infrastructure: PostgreSQL 16 (metadata only — no document content). No LLM in the live pipeline (dormant Ollama code kept in `backend/app/llm/` for future revival). No MinIO or persistent file storage for documents.

### Single-document flow (current shape)

The app is deliberately scoped to one document at a time while we nail the core UX:

- `/` — landing page (SSR, no Shoelace)
- `/try` — upload a single PDF; text is extracted client-side, the document is registered, detections are computed, and the user is routed to the review screen
- `/review/[docId]` — PDF viewer on the left, detection list on the right, export button in the toolbar; client-first throughout

There is **no dossier concept, no document list, no cross-document state**. A document stands on its own. The PDF lives in IndexedDB; the server stores only `Document` and `Detection` rows. Several backlog todos (organizations, document lifecycle, name propagation across documents, etc.) assume an older multi-document shape and will need rewriting when tackled.

## Frontend conventions

- **Svelte 5 runes mode** is enforced project-wide. Use `$state`, `$derived`, `$effect` — not legacy stores.
- **Shoelace web components** are actively used for interactive UI primitives (`sl-button`, `sl-input`, `sl-select`, `sl-alert`, `sl-dialog`, `sl-badge`, `sl-progress-bar`, `sl-tooltip`, `sl-checkbox`, `sl-textarea`, `sl-spinner`).
  - Import each component's JS module directly where used: `import '@shoelace-style/shoelace/dist/components/button/button.js';`
  - SSR is disabled for `/review/*` routes (`frontend/src/routes/review/+layout.ts`) — Shoelace requires browser APIs. The landing page at `/` stays SSR-compatible and does NOT use Shoelace.
  - Shoelace events in Svelte 5 use the `onsl-*` pattern: `<sl-button onsl-focus={(e) => handle(e)}>`.
  - Shoelace inputs don't support `bind:value`. Use `value={x}` + `onsl-input={(e) => { x = e.target.value; }}`.
  - Tailwind utilities don't penetrate Shadow DOM. Use Shoelace CSS custom properties or `::part()` for customization.
- **Svelte wrapper components** in `$lib/components/ui/` for layout patterns Shoelace doesn't cover: `Card.svelte`, `PageHeader.svelte`, `Alert.svelte`.
- **Tailwind v4** with `@theme` directive for design tokens — see `app.css`. Shoelace theme overrides also defined in `app.css` (`:root` block).
- Components are organized by feature: `landing/`, `shared/`, `review/`, `ui/`.
- API client lives in `$lib/api/client.ts` — all API calls go through it.

## Backend conventions

- **Async everywhere**: use `async def` for all route handlers and services.
- **Pydantic v2** for request/response validation.
- **SQLAlchemy v2** async with `asyncpg` driver.
- **No LLM in the live pipeline.** The LLM layer under `app/llm/` is dormant — kept as a parked revival path behind `settings.llm_tier2_enabled`/`llm_tier3_enabled` flags. See `app/llm/README.md`. Don't import from `app.llm.*` in new code unless you are explicitly working on the revival path; the default detection pipeline must not touch it.
- **Deduce** (Dutch NER) must be initialized once at startup (in FastAPI lifespan), not per-request (~2s load time).
- PDF redaction with PyMuPDF is **irreversible** and happens **in-memory only** during ephemeral export. Never write the original PDF to disk.

## Key design rules

- Tier 3 is reserved and has no active caller. Do not wire LLM analysis into it without a product decision.
- Five-year rule (Art. 5.3): warn when a relative ground is applied to documents older than 5 years.
- Public officials (college B&W, raadsleden, etc.) should NOT be redacted. Rule-based detection lives in todos #13 (functietitel + publiek-functionaris rule engine) and #17 (per-document reference list UI).

## Running locally

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Infrastructure only (no MinIO needed for documents)
docker compose up postgres
```

### Backend ports (important)

Two supported workflows, two different host ports:

- **Bare-metal uvicorn** (`uvicorn app.main:app --reload`) → `http://localhost:8000`
- **Docker Compose** (`docker compose up api`) → `http://localhost:8100` (the compose file names the backend service `api`, not `backend`, and maps host `8100` → container `8000`; see `docker-compose.yml`). To rebuild after editing backend code: `docker compose up -d --build api`.

`frontend/.env` sets `PUBLIC_API_URL` to whichever port matches your workflow. Both ports are allowed in the frontend CSP (`connect-src` in `svelte.config.js`) so either setup works without edits. If you change the mapping, update that list — a CSP-blocked `fetch()` surfaces to the user as a generic offline error and is easy to misdiagnose.

## Commands

- **Frontend type check**: `cd frontend && npm run check`
- **Backend lint**: `cd backend && source .venv/bin/activate && ruff check app/`
- **Backend format**: `cd backend && source .venv/bin/activate && ruff format app/`
- **Backend type check**: `cd backend && source .venv/bin/activate && mypy app/`
- **Backend tests**: `cd backend && source .venv/bin/activate && pytest`

## Todo backlog (`docs/todo/`)

The project backlog lives in `docs/todo/`. Read `docs/todo/README.md` for the full index with priorities, sizes, phases, and implementation order.

### How the backlog works

- Each todo is a numbered markdown file (e.g., `07-roles-permissions.md`) with priority, size, dependencies, scope, and acceptance criteria.
- Todos are grouped into phases (A through G). Work top-to-bottom within each phase.
- `docs/todo/00-client-first-architecture.md` is the foundational decision — every other todo must respect it.

### When implementing a todo

1. **Read the todo file first.** It has the scope, acceptance criteria, and dependencies.
2. **Check dependencies.** Don't start a todo if its `Depends on` items aren't done.
3. **Respect the client-first architecture.** If a feature seems to require server-side document storage, the design is wrong. Revisit #00.
4. **When done:** move the completed todo file to `docs/todo/done/` and update `docs/todo/README.md` to mark it (strikethrough or move to a "Completed" section). This prevents the backlog from going stale.

### Keeping the backlog current

- **After implementing:** move the file to `docs/todo/done/`, update the README index.
- **If scope changes during implementation:** update the todo file before moving it to done — the done file should reflect what was actually built, not just what was planned.
- **If a todo turns out to be unnecessary:** delete it and remove it from the README index with a note in the "Briefings Not Adopted" section.
- **If you discover new work during implementation:** create a new numbered todo file and add it to the README index in the right phase.
- **Never leave a todo file in `docs/todo/` that is fully implemented.** Stale todos are worse than no todos.

### Source briefings

The original feature briefings that generated the todos are in `docs/process/`. These are reference material — the todos are the actionable distillation. If a todo contradicts its source briefing, the todo wins (it reflects later analysis and the client-first decision).
