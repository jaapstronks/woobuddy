# `deploy/` — Manual Hetzner deploy

How the hosted instance at <https://woobuddy.nl> is built and updated. Today this is **manual**: a developer runs a script from their laptop. There is no CI/CD pipeline yet (see [Should we automate this?](#should-we-automate-this)).

## What's running in production

- **Provider:** Hetzner Cloud, location `fsn1` (Falkenstein, DE)
- **Server:** `woobuddy-prod`, type `cx23`, Ubuntu 24.04 — ~€5/month gross
- **DNS:** `woobuddy.nl` and `www.woobuddy.nl` A-records via TransIP, 300s TTL
- **Reverse proxy / TLS:** Caddy 2 with automatic Let's Encrypt
- **Stack:** `docker-compose.prod.yml` — `caddy` + `frontend` (SvelteKit/node) + `api` (FastAPI) + `postgres:16-alpine`
- **App home on the box:** `/opt/woobuddy`
- **Persistent volumes:** `pgdata` (Postgres), `caddy_data` (LE certs), `caddy_config`
- **No document storage:** PDFs never reach disk on the server. Only `Document` and `Detection` metadata rows live in Postgres.

## Files in this directory

| File | Purpose | Committed? |
|------|---------|------------|
| `provision.sh` | One-shot: create SSH key in Hetzner → create VPS → poll for IPv4 → write `.vps-ip` → create/replace TransIP A-records. | yes |
| `deploy.sh` | Every-change: rsync the repo to `/opt/woobuddy` → write minimal `.env` → run `install.sh` over SSH. | yes |
| `install.sh` | Runs *on the VPS*: install Docker if missing → `docker compose up -d --build` → wait for health. | yes |
| `Caddyfile` | Caddy config (apex → frontend, `/api/*` → api, www → 301 to apex). | yes |
| `.deploy_key` / `.deploy_key.pub` | ed25519 keypair used as the `root@vps` login key. Throwaway — rotate by regenerating and re-running `provision.sh`. | **no** (gitignored) |
| `.vps-ip` | The current public IPv4. Written by `provision.sh`, read by `deploy.sh`. | **no** (gitignored) |
| `.known_hosts` | SSH host-key pin for the VPS, written on first connect. | **no** (gitignored) |

## Secrets

Secrets are read from the project-root `.env`. Two of them are referenced as `op://...` URIs and resolved by the 1Password CLI via `op run --env-file=.env -- …`:

| Variable | Used by | How to set |
|----------|---------|------------|
| `HCLOUD_TOKEN` | `provision.sh` | Hetzner Cloud API token — literal value in `.env`. |
| `TRANSIP_ACCESS_TOKEN` | `provision.sh` | TransIP JWT (24h validity) — literal value in `.env`, refresh with TransIP UI when expired. |
| `DBASE_PASSWORD` | `deploy.sh`, `docker-compose.prod.yml` | Postgres password baked into the prod compose file at boot. Literal value in `.env`. |
| `HETZNER_PRIVATE_KEY` | (referenced in script header but unused; the SSH key comes from `deploy/.deploy_key` on disk) | `op://...` reference — fine to leave alone. |

If `.env` contains only literal values you can run the scripts directly without `op run`. As soon as any value is an `op://` URI, prefix the command with `op run --env-file=.env --`.

## Routine deploy (every change)

Pre-flight: you're on `main`, the working tree is clean, and the SHA you want to ship is `HEAD`.

```bash
cd "/path/to/woobuddy"

# Option A — secrets all literal in .env
set -a && . ./.env && set +a
./deploy/deploy.sh

# Option B — at least one secret is op:// (default)
op run --env-file=.env -- ./deploy/deploy.sh
```

`deploy.sh` is idempotent. It:

1. Reads the VPS IP from `deploy/.vps-ip`.
2. Polls SSH on port 22 until reachable.
3. Rsyncs the repo to `/opt/woobuddy` (excluding `node_modules`, `.venv`, `.git`, `docs/`, etc.).
4. Writes `/opt/woobuddy/.env` containing **only** `DBASE_PASSWORD`.
5. SSHes in and runs `/opt/woobuddy/deploy/install.sh`, which `docker compose up -d --build`s the stack and waits for `/api/health` to go green.

Verify after:

```bash
curl -I https://woobuddy.nl/
curl -fsS https://woobuddy.nl/api/health
```

A first-Caddy-boot TLS cert can take ~30s. After that, the deploy is live.

## First-time provisioning (almost never)

Only needed when standing up a new VPS or rotating the IP/host. Costs money — `provision.sh` creates a real cx23 server and updates real DNS records.

```bash
# Requires HCLOUD_TOKEN and TRANSIP_ACCESS_TOKEN resolvable in .env
op run --env-file=.env -- ./deploy/provision.sh
op run --env-file=.env -- ./deploy/deploy.sh
```

Idempotent: re-running `provision.sh` finds the existing SSH key and server by name and skips creation.

## Rolling back

There is no automated rollback. To go back to a known-good SHA:

```bash
git checkout <good-sha>
./deploy/deploy.sh   # (or with op run)
git checkout main
```

`pgdata` is *not* touched by a rollback. If a release ran an Alembic migration that the previous version doesn't understand, you'll need to roll back the migration manually before redeploying:

```bash
ssh -i deploy/.deploy_key root@$(cat deploy/.vps-ip) \
  "cd /opt/woobuddy && docker compose -f docker-compose.prod.yml exec api alembic downgrade -1"
```

## Operating the box

Quick SSH:

```bash
ssh -i deploy/.deploy_key -o UserKnownHostsFile=deploy/.known_hosts \
    root@$(cat deploy/.vps-ip)
```

On the box:

```bash
cd /opt/woobuddy
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f caddy
```

## Backups

Not yet automated. `pgdata` lives only on the VPS volume. Before doing anything risky, snapshot Postgres:

```bash
ssh -i deploy/.deploy_key root@$(cat deploy/.vps-ip) \
  "cd /opt/woobuddy && docker compose -f docker-compose.prod.yml exec -T postgres \
     pg_dump -U woobuddy woobuddy" \
  > "backup-$(date +%Y%m%d-%H%M).sql"
```

Scheduled off-VPS backups are open work — see [`docs/todo/39-deployment.md`](../docs/todo/39-deployment.md).

## Should we automate this?

The current flow works for two people shipping a few times a week. Auto-deploy on push-to-`main` would buy:

- **One less manual step** per merge (faster shipping, lower friction for OSS contributors).
- **A consistent trail** of who deployed what, when (GitHub Actions log).
- **Forced discipline:** every merge ships, so we have to keep `main` always-deployable. Today nothing enforces that.

It would also cost:

- **A non-trivial chunk of the secret-handling story.** Right now `DBASE_PASSWORD` and the SSH private key sit in 1Password and on Jaap's laptop. Moving them to GitHub Secrets means GitHub becomes a target with prod credentials. Mitigations exist (1Password GitHub Action, OIDC to a Hetzner-hosted runner) but they add moving parts.
- **Loss of the "look before you ship" pause.** Manual deploys catch obvious mistakes — a config you forgot to commit, a migration you didn't mean to run yet.
- **A staging environment, eventually.** Auto-deploy without staging means every regression is a prod regression.

Recommendation:

1. **Now:** keep manual deploy. It's two scripts and ~2 minutes per release.
2. **When the team grows past two, or when we add a Team-tier paying customer:** add a GitHub Actions workflow that (a) builds + tests on every PR (already done), (b) on push to `main`, SSHes into the VPS using a deploy key from GitHub Secrets, runs `git pull && deploy/install.sh`. Skip the rsync-from-laptop dance entirely.
3. **Before that:** a cheap intermediate is a Makefile target — `make deploy` — that wraps the `op run --env-file=.env -- ./deploy/deploy.sh` invocation so neither of us has to remember the exact command.

Either way, the prerequisites for safe auto-deploy are: scheduled Postgres backups, a staging VPS (cx22 is €4/month), and a smoke test that runs after deploy and pages on failure. Adding CI/CD before those is mostly cosmetic.
