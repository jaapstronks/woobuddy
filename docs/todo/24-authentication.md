# 05 — Authentication (Better Auth)

- **Priority:** P0
- **Size:** L (3–7 days)
- **Source:** Auth & Billing briefing, "Authentication: Better Auth" section
- **Depends on:** Nothing (can run in parallel with Phase A)
- **Blocks:** #25, #26, #27, #28, #33

## Why

The app currently has no user model. `reviewed_by` fields are free-text strings, there are no sessions, and anyone with a URL can access any dossier. Real deployment requires authentication.

## Assessment of Briefing Recommendation

Better Auth is a solid choice. The reasoning is sound:
- Own database (no external auth service) — critical for government trust
- First-class SvelteKit + Svelte 5 support
- Organization plugin included (needed for #25)
- MIT licensed, actively maintained
- The alternatives (Auth.js, Lucia, Clerk) all have the drawbacks the briefing identifies

**Adopt as-is.** The briefing's architecture (SvelteKit handles auth, proxies to FastAPI with trusted headers) is clean and appropriate.

## Scope

### Server setup

- [ ] Install Better Auth: `pnpm add better-auth`
- [ ] Create `src/lib/server/auth.ts` with Better Auth config (PostgreSQL pool, email/password enabled)
- [ ] Run Better Auth migrations (`npx @better-auth/cli migrate`) — creates user, session, account, verification tables
- [ ] Ensure Alembic migrations coexist with Better Auth's tables

### SvelteKit integration

- [ ] Create `src/hooks.server.ts` — validate session on every request, populate `event.locals.user`
- [ ] Create `src/lib/auth-client.ts` — client-side auth store (runes-compatible)
- [ ] Protect `/app/*` routes — redirect to login if not authenticated

### Auth pages

- [ ] `/auth/login` — email/password login form
- [ ] `/auth/signup` — registration form
- [ ] `/auth/verify` — email verification page
- [ ] `/auth/forgot-password` — password reset request
- [ ] `/auth/reset-password` — password reset form

### SvelteKit → FastAPI proxy

- [ ] Create `+server.ts` route handlers under `/api/` that validate session and forward to FastAPI
- [ ] Add `X-User-Id` header on forwarded requests
- [ ] FastAPI middleware to validate and extract `X-User-Id` from trusted headers
- [ ] The proxy must handle streaming for the ephemeral `/api/export/redact` endpoint (PDF binary up + redacted PDF down)

### Quick Try flow update

- [ ] `/try` now requires login — redirect to signup if not authenticated
- [ ] PDF stays client-side throughout (File API in browser) — no server upload needed
- [ ] After auth redirect, the PDF is still in the browser's File API reference — resume processing from there

### Environment variables

- [ ] `BETTER_AUTH_SECRET` (generated via `openssl rand -base64 32`)
- [ ] `BETTER_AUTH_URL`
- [ ] SMTP config for email verification (use Nodemailer + any SMTP for dev)

## Acceptance Criteria

- New user can sign up, verify email, and log in
- Unauthenticated access to `/app/*` redirects to login
- FastAPI receives authenticated user ID on every proxied request
- `/try` flow works: open PDF in browser → forced login → resume (PDF stays client-side)

## Not in Scope

- Microsoft social login (see #33)
- 2FA / passkeys (see #33)
- Organization model (see #25)
