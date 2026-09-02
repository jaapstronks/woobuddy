# 43 — Open Source Release: cut v0.1.0 + publish images

- **Priority:** P1
- **Size:** S (half a day)
- **Source:** Distribution & pricing strategy 2026-04
- **Status:** Done — v0.1.0 shipped 2026-04-26.
- **Notion:** [Ship #43 — release v0.1.0 (gitleaks audit, tag, GHCR images)](https://www.notion.so/34d11fb08c9e81889799cbdc060920cf)

## Outcome

`v0.1.0` is live on GitHub and on GHCR.

- Tag: [`v0.1.0`](https://github.com/jaapstronks/woobuddy/releases/tag/v0.1.0) on commit `19613ea`.
- Multi-arch images (linux/amd64 + linux/arm64), pullable anonymously: `ghcr.io/jaapstronks/woobuddy-api:v0.1.0`, `ghcr.io/jaapstronks/woobuddy-frontend:v0.1.0`. `:latest` points at the same digests.
- Release workflow (`.github/workflows/release.yml`) fires on every `v*` tag push: matrix-builds both images, picks up `:latest` for stable tags only, publishes a GitHub Release with auto-generated PR-title notes.
- Self-hosters can now pin a specific version. Upgrade flow documented in `deploy/README.md` ("Upgrading between releases").
- Validated via `v0.1.0-rc1` (caught the amd64-only manifest gap), then `v0.1.0-rc2` (multi-arch fix verified), then the real `v0.1.0` against the same `19613ea`.

Known limitations carried forward (not v0.1.0 blockers):

- `PUBLIC_API_URL` is baked into the frontend image at build time (`http://localhost:8000` default). Self-hosters with a custom hostname currently still rebuild from source. Moving to `$env/dynamic/public` is a v0.1.x follow-up.
- No SBOM publishing or signed images yet. cosign + SLSA provenance are a v0.2 follow-up if a paying Team or Enterprise customer asks for it.

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

- [x] Run `gitleaks detect --source . --log-opts="--all"` on the full history and confirm clean. The repo is already public, so a finding here is a "rotate + scrub" event, not a "delay launch" event — but we should know. _(Clean across all 40 commits, 2026-04-26.)_

### Release process

- [x] Tag `v0.1.0` on `main` once the rest of this list is merged _(tagged 2026-04-26 against `19613ea`; multi-arch images and Release published.)_
- [x] Add a release workflow in `.github/workflows/` that on tag push:
  - Builds and pushes `ghcr.io/jaapstronks/woobuddy-api` and `ghcr.io/jaapstronks/woobuddy-frontend`
  - Creates a GitHub Release with a changelog generated from conventional commits since the previous tag
- [x] Document the upgrade path between minor versions in `deploy/README.md` (one paragraph: pull, `docker compose up --build`, watch for breaking-change notes in release notes)

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
