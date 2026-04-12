# CLAUDE.md — WOO Buddy

## Project overview

WOO Buddy helps Dutch government employees redact privacy-sensitive information in Woo (Wet open overheid) documents. It uses a three-tier detection model where each tier has different detection methods, confidence levels, and UX patterns.

- **Tier 1** (hard identifiers): Regex + validation. Auto-redacted. Opt-out by reviewer.
- **Tier 2** (contextual personal data): Deduce NER + role classification. Suggested. One-click confirm/reject.
- **Tier 3** (content judgments): LLM analysis. Annotated with decision support. Human decides.

## Branding

- Always write "WOO Buddy" (WOO in caps, Buddy capitalized) in user-facing text
- Dutch UI language for the application itself
- English for code, comments, commit messages, and documentation

## Architecture

Monorepo with two applications:

- `frontend/` — SvelteKit (Svelte 5 with runes), TypeScript strict, Tailwind CSS v4, Shoelace web components, pdf.js
- `backend/` — FastAPI, Python 3.12, async throughout

Infrastructure: PostgreSQL 16 (metadata), MinIO (PDF storage), Ollama + Gemma 4 (local LLM).

## Frontend conventions

- **Svelte 5 runes mode** is enforced project-wide. Use `$state`, `$derived`, `$effect` — not legacy stores.
- **Shoelace web components** must be imported dynamically or in `onMount()` (no SSR for customElements).
- Shoelace events in Svelte 5 use the `onsl-*` pattern: `<sl-button onsl-focus={(e) => handle(e)}>`.
- For the review page, consider `export const ssr = false;` due to heavy browser-only dependencies (pdf.js, Shoelace).
- **Tailwind v4** with `@theme` directive for design tokens — see `app.css`.
- Components are organized by feature: `landing/`, `shared/`, `review/`, `dossier/`, `export/`.
- API client lives in `$lib/api/client.ts` — all API calls go through it.

## Backend conventions

- **Async everywhere**: use `async def` for all route handlers and services.
- **Pydantic v2** for request/response validation.
- **SQLAlchemy v2** async with `asyncpg` driver.
- The LLM layer is abstracted behind an `LLMProvider` interface in `app/llm/provider.py`. Providers (Ollama, Anthropic) are swappable via `LLM_PROVIDER` env var.
- **Deduce** (Dutch NER) must be initialized once at startup (in FastAPI lifespan), not per-request (~2s load time).
- PDF redaction with PyMuPDF is **irreversible** — always work on a copy. Originals stay in MinIO permanently.

## Key design rules

- Tier 3 must NOT show confidence percentages — use qualitative labels instead.
- Name propagation must be undoable: propagated decisions link back to source and are reversible with one action.
- Five-year rule (Art. 5.3): warn when a relative ground is applied to documents older than 5 years.
- Public officials (college B&W, raadsleden, etc.) should NOT be redacted — maintained via a per-dossier CSV reference list.

## Running locally

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Infrastructure only
docker compose up postgres minio
```

## Commands

- **Frontend type check**: `cd frontend && npm run check`
- **Backend lint**: `cd backend && source .venv/bin/activate && ruff check app/`
- **Backend format**: `cd backend && source .venv/bin/activate && ruff format app/`
- **Backend type check**: `cd backend && source .venv/bin/activate && mypy app/`
- **Backend tests**: `cd backend && source .venv/bin/activate && pytest`
