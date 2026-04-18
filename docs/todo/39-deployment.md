# 39 — Deployment Setup

- **Priority:** P2
- **Size:** S (remaining work — initial setup is done)
- **Source:** Testing & Polish briefing, Section 5
- **Depends on:** #01 (done)
- **Blocks:** Nothing

## Status

The hosted instance at <https://woobuddy.nl> is **live**, served from a Hetzner cx23 in `fsn1` (Falkenstein, DE) via Caddy + docker-compose. Provision and deploy are scripted in [`deploy/`](../../deploy/) — see [`deploy/README.md`](../../deploy/README.md) for the operator documentation.

What's done:

- [x] Hosting platform chosen — Hetzner Cloud (EU, simple, ~€5/month). Not Railway/Fly because the cost story is "essentially zero" and we wanted full root on a single VPS, not a PaaS.
- [x] Two services running (`frontend`, `api`) plus `postgres:16-alpine`, all behind Caddy. No managed Postgres — overkill for current load and rules out an extra DPA.
- [x] No S3/MinIO. Confirmed: client-first means the only persistent state is Postgres metadata.
- [x] Hosting region documented as EU-only in the privacy policy.
- [x] Domain registered (`woobuddy.nl` via TransIP), DNS A-records managed by `provision.sh`.
- [x] TLS via Let's Encrypt, automatic via Caddy.
- [x] Production environment variables documented (see [`deploy/README.md`](../../deploy/README.md) and [`.env.example`](../../.env.example)) and stored in 1Password.
- [x] Manual deploy flow — `op run --env-file=.env -- ./deploy/deploy.sh`.

## Still open

- [ ] **Scheduled off-VPS Postgres backups.** Today there's only `pgdata` on the VPS volume. A weekly `pg_dump` to Hetzner Storage Box (or equivalent) is the next step. Document the restore procedure once it exists.
- [ ] **CI/CD: deploy on push to `main`.** Tests already run on every PR (`.github/workflows/test.yml`); the deploy step itself is still manual. See [`deploy/README.md`](../../deploy/README.md) → "Should we automate this?" for the recommendation (defer until either the team grows or we have a paying customer; require backups + smoke test + staging first).
- [ ] **Staging environment.** A second cx22 (~€4/month) running the latest `main` continuously, so we can shake out regressions before the prod cut. Cheap, but only worth setting up once auto-deploy lands.
- [ ] **Post-deploy smoke test.** A scripted check that `/`, `/try`, `/review/<known-doc>`, and `/api/health` all return 200 within 60s of a deploy. Required before auto-deploy is safe.

## Acceptance Criteria

- App is accessible at `woobuddy.nl` with HTTPS — **done**
- Deployments happen automatically on push to main — **deferred**, see open list
- Database is backed up on a schedule — **open**
- Hosting region is EU-only and documented in the privacy policy — **done**
- No PDF storage in cloud object storage — **done** (architecturally enforced by #00)
