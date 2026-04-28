# CLAUDE.md — WOO Buddy

## Project ownership

WOO Buddy is a **personal side project** by Jaap Stronks and Jeroen Hammer. It is **not** a CIIIC project, even though Jaap works at CIIIC day-to-day. Don't attribute ownership, hosting, billing, or OAuth app registrations to CIIIC in any artifact (code, docs, todos, Notion, domain config, app registrations). "The team" / "us" in internal notes means Jaap + Jeroen. The hosted tier at woobuddy.nl is operated by them personally.

## Project overview

WOO Buddy helps Dutch government employees redact privacy-sensitive information in Woo (Wet open overheid) documents. It uses a three-tier detection model where each tier has different detection methods, confidence levels, and UX patterns.

- **Tier 1** (hard identifiers): Regex + validation. Auto-redacted. Opt-out by reviewer.
- **Tier 2** (contextual personal data): Deduce NER + wordlists (Meertens voornamen, CBS achternamen) + structure heuristics (e-mailheaders, handtekeningblokken, aanhef) + a rule-based public-official filter. Suggested. One-click confirm/reject.
- **Tier 3** (content judgments): Reserved. **No LLM anywhere in the codebase.** Kept as a slot for future rule-based content signals (e.g. beleidsopvatting-verdacht zinnen).

### No LLM in the codebase

As of April 2026 (see `docs/reference/woo-redactietool-analyse.md` and `docs/todo/done/35-deactivate-llm.md`), WOO Buddy runs without any LLM. Detection is regex + Deduce + wordlists + structure heuristics. The Ollama provider code and all LLM settings have been removed — there is no dormant revival path in-tree.

Do not reintroduce LLM calls without an explicit product decision to the contrary. If one is ever made, the revival must be **local-only** (Ollama + Google Gemma, or equivalent) and opt-in; read `docs/reference/llm-revival.md` before you start. The trust story ("uw PDF verlaat nooit uw browser") and the cost model of the generous free tier both depend on there being no LLM on the default path.

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

Infrastructure: PostgreSQL 16 (metadata only — no document content). No LLM anywhere in the codebase. No MinIO or persistent file storage for documents.

### Single-document flow (current shape)

The app is deliberately scoped to one document at a time while we nail the core UX:

- `/` — landing page (SSR, no Shoelace). The PDF drop zone is embedded in the hero; uploading triggers client-side text extraction, document registration, detection compute, and routes to the review screen. `/#try` is the in-page anchor; the standalone `/try` route is a permanent 308 redirect to `/#try` for old share links.
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
- **No LLM in the codebase.** The detection pipeline is rule-based end to end. There is no `app/llm/` package, no `anthropic`/`openai`/`ollama` dependency, no `llm_*` settings. If you believe you need an LLM for something, read `docs/reference/llm-revival.md` first — the default path must remain LLM-free.
- **Deduce** (Dutch NER) must be initialized once at startup (in FastAPI lifespan), not per-request (~2s load time).
- PDF redaction with PyMuPDF is **irreversible** and happens **in-memory only** during ephemeral export. Never write the original PDF to disk.

## Distribution & pricing strategy

WOO Buddy is **open core with a generous free tier**. Hosting cost is essentially zero (no LLM, no document storage), so the free tier is deliberately the marketing engine — not a teaser. When designing features, respect the following:

- **Self-host is a first-class tier**, not an afterthought. The codebase is MIT-licensed and runnable via `docker compose up` against a single Postgres. Government IT departments with strict data-sovereignty requirements can run it themselves without talking to us. See `docs/todo/43-open-source-release.md`.
- **The hosted Gratis tier has no signup wall on the landing-page upload flow and no document cap.** Anonymous reviewers can analyze and export full PDFs without an account. The trust unlock is "uw PDF verlaat nooit uw browser" — do not undermine it with watermarks, preview-only modes, document caps, or forced login on the trial flow. (Earlier drafts of `32-authentication.md` and `37-mollie-billing.md` proposed those gates and were explicitly reversed.)
- **Billing gates team features, not the review loop.** The Team tier (~€79–€99/month per organization) sells multi-user, shared custom wordlists, audit log, SSO, NL-hosted DPA, and priority support. The Enterprise tier sells SLA, ISO27001/NEN7510 paperwork, and dedicated instances. Pricing is per-org flat — never per-document.
- **Anonymous `/api/analyze` requests must not persist anything to PostgreSQL.** No `Document` row, no `Detection` rows. Detection metadata is computed in memory and returned. Persistence kicks in only when the user logs in and explicitly chooses to save.
- **Don't introduce LLM/GPU dependencies into the default code path.** They would break the cost model that makes the generous free tier viable. If a future product decision revives a local LLM verification step, it must be opt-in per operator and local-only — see `docs/reference/llm-revival.md`.

When you build a new feature, ask: "Does this gate something on the trial path?" If yes, the design is wrong — gate it on team features instead.

## Key design rules

- Tier 3 is reserved and has no active caller. Do not wire LLM analysis into it without a product decision.
- Five-year rule (Art. 5.3): warn when a relative ground is applied to documents older than 5 years.
- Public officials (college B&W, raadsleden, etc.) should NOT be redacted. Rule-based detection lives in todos #13 (functietitel + publiek-functionaris rule engine) and #17 (per-document reference list UI).
- Public-official detection is rule-based (#13). Titles are matched against `backend/app/data/functietitels_publiek.txt` — edit the list, not the code, to extend coverage.

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

## Branching, commits, and pull requests

This repo uses a **PR-only workflow**. The `main` branch is protected — direct pushes are blocked by a GitHub ruleset. Every change goes through a feature branch and a pull request.

### Protection rules in effect on `main`

- No direct pushes (PR required, 0 approvals, but the workflow gates the merge).
- No force pushes, no branch deletion, **linear history only** (no merge commits).
- Required status checks: `Frontend tests` and `Backend tests` must be green and the branch must be up to date with `main`.
- All review threads must be resolved before merging.
- Squash-and-merge is the **only** enabled merge style (configured at repo level). Merged feature branches are auto-deleted.
- The repo owner has an emergency bypass on their admin role. **This is for genuine hotfixes only — Claude must never use it autonomously, even when asked to "just push to main".** If a user asks Claude to bypass, Claude explains the rule, asks for explicit confirmation, and prefers opening a PR.

### Branch naming

- `kebab-case`, prefixed by type: `feat/`, `fix/`, `refactor/`, `docs/`, `chore/`, `test/`, `perf/`.
- Examples: `feat/page-completeness-review`, `fix/csp-blocked-fetch`, `docs/branch-protection-and-pr-rules`.
- One branch = one logical change. Don't pile unrelated work onto a branch because it's already open.

### Commit message rules (Conventional Commits)

Every commit message has the form:

```
<type>(<scope>): <subject>

<body — optional, wrapped at ~72 cols, explains *why*>
```

- **type**: `feat` (new feature), `fix` (bug fix), `refactor` (no behavior change), `docs`, `chore` (tooling/build), `test`, `perf`, `style`.
- **scope**: optional, lowercase, names the affected area: `review`, `pdf-viewer`, `backend`, `ci`, `auth`, etc.
- **subject**: imperative mood ("add", not "added" or "adds"), no trailing period, ≤ 72 chars.
- **body** (when present): explains *why* the change is needed and what trade-offs were made. Never restate the diff.
- One logical change per commit. Don't bundle unrelated work.
- Banned: `wip`, `fix`, `stuff`, `update`, `address feedback`, `pr review`, etc. as standalone messages.

Good: `feat(review): jump-to-next-detection keyboard shortcut`
Good: `fix(pdf-viewer): clamp area-select bbox to page bounds when dragging past edge`
Bad: `Updated PdfViewer.svelte`
Bad: `wip`

### Pull request rules

- **Title**: same format as a commit subject (Conventional Commit, ≤ 72 chars). The PR title becomes the squash-merge commit on `main`, so it must be self-explanatory.
- **Description**: use this template:

  ```
  ## Summary
  - one or two bullets on what changes

  ## Why
  - what problem this solves / what user value it adds

  ## Test plan
  - [ ] specific manual or automated checks the reviewer should run
  ```

- **Size**: aim for under ~400 lines changed. Bigger PRs should usually be split.
- **CI must be green** before merging. Both `Frontend tests` and `Backend tests` are required.
- **All review threads resolved** before merging.
- **Rebase, don't merge.** If `main` has moved, `git fetch origin && git rebase origin/main` on the feature branch — never merge `main` into the feature branch (linear history will reject it).

### How Claude should work under these rules

When asked to commit and push:

1. Confirm there's a clean branching plan. Never commit to `main`. If currently on `main`, create a feature branch first (`git checkout -b <type>/<slug>`).
2. Write commits that follow the Conventional Commit format above. If the work spans unrelated changes, split them into separate commits.
3. Push the branch with `-u`, then open a PR via `gh pr create` using the template above.
4. Report the PR URL.
5. **Do not merge automatically.** The user merges. (Auto-merge is enabled, so `gh pr merge --auto --squash` is fine if the user explicitly asks.)
6. If a user asks Claude to push directly to `main` or use the admin bypass, Claude explains the rule first and asks for explicit confirmation before doing anything destructive. Default answer: "let's open a PR instead".

### When a rule gets violated

Whether it's Claude, Jaap, Jeroen, or a future contributor — when a rule above gets bent, default to a short, specific coaching reply rather than a rule citation:

- Explain **why** the rule exists in one sentence, not just that it was broken.
- Show what a fix looks like based on the actual diff/branch in front of you — a concrete rewrite beats a link.
- Offer to do the fix (amend the message, rebase, split the PR), then stop. One explanation, one example, one offer.

## Hero demo video

The landing page Hero (`frontend/src/lib/components/landing/Hero.svelte`) plays `frontend/static/woobuddy-demo.mp4`. When replacing the clip, record a raw MP4 and compress it with this recipe before committing — the raw ScreenFlow/QuickTime export is typically 5–10× bigger than needed and will inflate the bundle:

```bash
ffmpeg -y -i <raw-input>.mp4 \
  -vcodec libx264 -crf 30 -preset slow \
  -movflags +faststart -an \
  frontend/static/woobuddy-demo.mp4
```

- `-crf 30 -preset slow` hits ~500–700 KB for typical screencast content (large flat areas compress well). Drop to `-crf 28` if quality looks soft.
- `-movflags +faststart` puts the moov atom at the front so the video starts playing before it's fully downloaded.
- `-an` strips audio — the Hero video is muted and autoplayed.
- Overwrite the existing `woobuddy-demo.mp4` and delete the raw source; Hero already points at `/woobuddy-demo.mp4` so no code changes are needed.

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
