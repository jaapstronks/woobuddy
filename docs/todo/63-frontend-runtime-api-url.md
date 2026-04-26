# 63 — Frontend `PUBLIC_API_URL` at runtime, not build time

- **Priority:** P2 (v0.1.x follow-up to #43)
- **Size:** S (under a day)
- **Source:** v0.1.0 release retrospective 2026-04-26
- **Notion:** _not tracked yet_

## Why

`v0.1.0` ships multi-arch GHCR images (`ghcr.io/jaapstronks/woobuddy-frontend:v0.1.0`) but `PUBLIC_API_URL` is baked into the bundle at build time via SvelteKit's `$env/static/public`. The Dockerfile defaults it to `http://localhost:8000`, which is fine for dev but useless for self-hosters running on a custom hostname — they currently still have to rebuild the image from source. That undermines the "pin a specific version" promise of the GHCR images.

The fix is small and well-trodden: move `PUBLIC_API_URL` from `$env/static/public` (compile-time substitution) to `$env/dynamic/public` (read from `process.env` at request time on the adapter-node server). The browser bundle then receives the value through the dynamic-env mechanism instead of being string-literal'd at build time.

## Scope

- Migrate the two callers:
  - `frontend/src/lib/api/client.ts` — change `import { PUBLIC_API_URL } from '$env/static/public';` to `import { env } from '$env/dynamic/public';` and read `env.PUBLIC_API_URL`.
  - `frontend/src/lib/services/export-service.ts` — same.
- Update unit-test mocks (`frontend/src/lib/services/upload-flow.test.ts`, `network-isolation.test.ts`) to match the new import shape.
- Drop the `PUBLIC_API_URL` build-arg from `frontend/Dockerfile`. The image becomes hostname-agnostic.
- Update `docker-compose.yml` (dev) and `docker-compose.prod.yml` (hosted): set `PUBLIC_API_URL` under `environment:` instead of `build.args`. Keep the existing values (`http://localhost:8100` for dev, `https://woobuddy.nl` for prod).
- Document the env var in `deploy/README.md`'s "Upgrading between releases" section: self-hosters with a custom hostname set `PUBLIC_API_URL=https://<their-host>` (or leave empty for same-origin via reverse proxy).
- Audit other `$env/static/public` imports (`PUBLIC_SITE_MODE`, `PUBLIC_PLAUSIBLE_*`) for the same treatment if they should vary at runtime. `PUBLIC_SITE_MODE` is already dynamic in prod; double-check.

## Acceptance criteria

- A self-hoster runs:
  ```
  docker run -e PUBLIC_API_URL=https://example.org/api \
    -p 3000:3000 ghcr.io/jaapstronks/woobuddy-frontend:vX.Y.Z
  ```
  and the deployed app calls `https://example.org/api/*` — no rebuild required.
- Empty/unset `PUBLIC_API_URL` falls back to same-origin (relative paths), so self-hosters fronting both api+frontend behind one reverse proxy don't have to set anything.
- Dev `docker compose up` still works — frontend talks to `http://localhost:8100` for the API.
- Hosted prod (`woobuddy.nl`) still works — frontend talks to `https://woobuddy.nl/api/*`.
- Unit tests pass.

## Not in scope

- Migrating server-side env vars (`$env/static/private`) — those don't ship to the browser and don't have the same problem.
- Reworking how OAuth picker callbacks construct URLs — they already use runtime values.
- Documenting same-origin reverse-proxy patterns in detail (a one-liner pointer is enough; full deployment guides for nginx/Caddy/Traefik are out of scope).
