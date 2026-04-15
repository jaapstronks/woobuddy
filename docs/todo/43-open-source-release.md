# 43 — Open Source Release & Self-Host Path

- **Priority:** P1
- **Size:** M (1–3 days)
- **Source:** Distribution & pricing strategy 2026-04
- **Depends on:** Nothing strictly, but best done before #37 (billing) so the open-core model is in place before paid tiers exist
- **Blocks:** Self-host tier in #37

## Why

Open sourcing the core under MIT is the strategic centerpiece of WOO Buddy's distribution model. It does three things at once:

1. **Kills the procurement objection.** Government IT departments default to "we can't put data in the cloud." A self-hostable, MIT-licensed tool sidesteps that conversation entirely — they can run it in their own datacenter or private cloud.
2. **Builds trust by inspection.** A privacy-first claim ("uw documenten verlaten nooit uw browser") is much more credible when the source is public and auditable. Civil servants and their CISOs can verify it.
3. **Drives organic discovery.** A Dutch-language README on a public repo is the canonical search result for "open source woo redactie" — a zero-cost marketing channel that compounds.

The hosted tier (#37) sells team features, support, SSO, audit log, and SLA — *not* the core review loop. The free/self-host tier and the hosted Gratis tier are deliberately the same product; the team tier adds collaboration and operational comfort.

## Scope

### Repository preparation

- [ ] Move repo to a public GitHub organization (or flip the existing private repo to public when ready)
- [ ] Add `LICENSE` — MIT
- [ ] Add `CONTRIBUTING.md` — Dutch + English, explains the dev loop, code style, how to file issues, that the project is opinionated about client-first architecture
- [ ] Add `CODE_OF_CONDUCT.md` — Contributor Covenant
- [ ] Add `SECURITY.md` — disclosure policy, contact email, supported versions
- [ ] Audit the repo for accidentally committed secrets, customer data, or test fixtures that contain real PII (the generated fixtures from `d759e33` should be safe but verify)
- [ ] Audit `git log` for the same — rewrite history if necessary before going public
- [ ] Verify all dependencies have OSI-compatible licenses (Deduce, PyMuPDF, Shoelace, etc.)

### Self-host quickstart

- [ ] `docker-compose.yml` for self-hosters: `api` + `frontend` + `postgres`, no MinIO, no GPU. Should boot with a single `docker compose up`.
- [ ] `.env.example` with every variable documented in plain Dutch
- [ ] `README.md` (root) — Dutch-first, English second:
  - One-paragraph what-and-why
  - Quickstart: clone → docker compose up → open localhost
  - Link to hosted version for non-IT users
  - Link to architecture overview
  - Badge: license, build status, latest release
- [ ] `docs/SELF_HOSTING.md` — how to deploy to a customer's own VM, environment variables, backup, upgrade path, how to wire to existing SSO

### Release process

- [ ] Tag releases semver-style (`v0.1.0`, ...)
- [ ] GitHub Releases with changelog generated from conventional commits
- [ ] Publish a Docker image to GHCR (`ghcr.io/<org>/woobuddy-api`, `...-frontend`) on each tag
- [ ] Document the upgrade path between minor versions

### Marketing surface

- [ ] Update `frontend/src/lib/components/landing/OpenSource.svelte` to link to the public repo and the self-host docs
- [ ] Add a "Self-host" entry to the pricing table on the landing page (when pricing is added in #37)
- [ ] Mention the open-source nature in the `/privacy` page (#40) — it's a trust amplifier

## Acceptance Criteria

- Repository is public on GitHub with MIT license, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT
- A new self-hoster can clone the repo and run `docker compose up` to get a working instance
- Docker images are published to GHCR on tagged releases
- README is Dutch-first and includes the self-host quickstart
- No secrets or real PII in the repo or its history
- Landing page links to the public repo

## Not in Scope

- A formal governance model or maintainer team (we are the only maintainer for now)
- Hardening the self-host path for hostile multi-tenant scenarios (single-tenant per deploy is fine)
- A plugin system or extensibility API
- Translating the codebase or comments to Dutch (English is fine for code; UI strings are already Dutch)
