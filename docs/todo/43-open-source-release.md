# 43 — Open Source Release: cut v0.1.0 + publish images

- **Priority:** P1
- **Size:** S (half a day)
- **Source:** Distribution & pricing strategy 2026-04
- **Status:** Most of the original scope shipped before the public flip. What's left is the release-engineering tail.

## What's already done

The bulk of #43 landed during the public-flip prep:

- `LICENSE` (MIT), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `THIRD_PARTY_LICENSES.md`
- Dutch-first `README.md` with self-host quickstart, hosted-version link, contributing rules
- `.env.example` (NL-documented), `docker-compose.yml` (api + frontend + postgres, single `docker compose up`)
- Production self-host path: `docker-compose.prod.yml` + `deploy/README.md` (treated as the operator handbook in lieu of a separate `docs/SELF_HOSTING.md`)
- Repo flipped to public on GitHub (`jaapstronks/woobuddy`)
- Landing page links to the public repo (`Header`, `Footer`, `Trust`, `SelfHostIntro`)
- `.gitleaks.toml` configured

## Remaining scope

### Secrets/PII history audit

- [ ] Run `gitleaks detect --source . --log-opts="--all"` on the full history and confirm clean. The repo is already public, so a finding here is a "rotate + scrub" event, not a "delay launch" event — but we should know.

### Release process

- [ ] Tag `v0.1.0` on `main` once the audit is clean
- [ ] Add a release workflow in `.github/workflows/` that on tag push:
  - Builds and pushes `ghcr.io/jaapstronks/woobuddy-api` and `ghcr.io/jaapstronks/woobuddy-frontend`
  - Creates a GitHub Release with a changelog generated from conventional commits since the previous tag
- [ ] Document the upgrade path between minor versions in `deploy/README.md` (one paragraph: pull, `docker compose up --build`, watch for breaking-change notes in release notes)

## Acceptance Criteria

- `gitleaks` is clean against full history
- `v0.1.0` exists on GitHub with release notes
- `ghcr.io/jaapstronks/woobuddy-api:v0.1.0` and `...-frontend:v0.1.0` are pullable
- A self-hoster can pin a specific version instead of tracking `main`

## Not in Scope

- A formal governance model or maintainer team
- Hardening for hostile multi-tenant self-host
- A plugin system or extensibility API
- Translating the codebase to Dutch (UI is already Dutch; code stays English)
