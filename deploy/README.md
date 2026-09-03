# `deploy/` — Manual Hetzner deploy

How the hosted instance at <https://woobuddy.nl> is built and updated. Today this is **manual**: a developer runs a script from their laptop. There is no CI/CD pipeline yet (see [Should we automate this?](#should-we-automate-this)).

## What's running in production

- **Provider:** Hetzner Cloud, location `fsn1` (Falkenstein, DE)
- **Server:** `woobuddy-prod`, type `cx23`, Ubuntu 24.04 — ~€5/month gross
- **DNS:** `woobuddy.nl` and `www.woobuddy.nl` A-records via TransIP, 300s TTL
- **Reverse proxy / TLS:** Caddy 2 with automatic Let's Encrypt, `dynamic a` upstreams + active health checks so it load-balances across rolling replicas
- **Stack:** `docker-compose.prod.yml` — `caddy` + `frontend` (SvelteKit/node) + `api` (FastAPI) + `postgres:16-alpine`
- **Rolling updates:** [`docker rollout`](https://github.com/Wowu/docker-rollout) CLI plugin handles zero-downtime replacement of the `frontend` and `api` services (scales up new, waits for health, retires old)
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

Secrets are read from the project-root `.env`. Values referenced as `op://...` URIs are resolved by the 1Password CLI via `op run --env-file=.env -- …`:

| Variable | Used by | How to set |
|----------|---------|------------|
| `HCLOUD_TOKEN` | `provision.sh` | Hetzner Cloud API token — literal value in `.env`. |
| `TRANSIP_ACCESS_TOKEN` | `provision.sh` | TransIP JWT (24h validity) — literal value in `.env`, refresh with TransIP UI when expired. |
| `DBASE_PASSWORD` | `deploy.sh`, `docker-compose.prod.yml` | Postgres password baked into the prod compose file at boot. Literal value in `.env`. |
| `HETZNER_PRIVATE_KEY` | (referenced in script header but unused; the SSH key comes from `deploy/.deploy_key` on disk) | `op://...` reference — fine to leave alone. |
| `SCALEWAY_SECRET_KEY` | `deploy.sh`, `docker-compose.prod.yml` | Scaleway TEM secret key for the lead form. See "Lead-form mail" below. |
| `SCALEWAY_PROJECT_ID` | `deploy.sh`, `docker-compose.prod.yml` | Scaleway project the send is billed to — not a secret, but required. |
| `NOTIFICATION_EMAIL` | `deploy.sh`, `docker-compose.prod.yml` | Where lead notifications land. Not a secret. |
| `LISTMONK_API_USER` / `LISTMONK_API_TOKEN` | `deploy.sh`, `docker-compose.prod.yml` | Listmonk API user for the newsletter opt-in. See "Newsletter opt-in" below. |
| `LEADS_CONFIRM_SECRET` | `deploy.sh`, `docker-compose.prod.yml` | HMAC secret signing the confirmation link. |

`SCALEWAY_TEM_REGION`, `TEM_FROM_EMAIL`, `TEM_FROM_NAME`, `LISTMONK_URL`, `LISTMONK_LIST_UUID` and `PUBLIC_SITE_URL` are optional: `deploy.sh` falls back to the same defaults `docker-compose.prod.yml` carries. An empty `LISTMONK_LIST_UUID` — or an empty API user, token or confirm secret — is a valid choice: it turns the newsletter opt-in off and leaves the notification mail working.

### Lead-form mail (#72)

The contact form on the landing page is the only conversion path on woobuddy.nl, and it needs mail credentials in the running `api` container. It went to production without them once and returned a 500 on every submission for months, so this is now enforced in three places: `deploy.sh` refuses to run when a required key is unresolved, `install.sh` refuses to deploy when `/opt/woobuddy/.env` lacks one, and after the rollout `install.sh` asks the live API (`/api/health` → `lead_mail`) whether the config actually reached the process.

The credentials belong to the Scaleway IAM application **`woobuddy-leads`** (`982fc6f1-fe35-4222-93f1-4d99da9cdcef`) in the Bureau Bolster organization, with policy `woobuddy-leads-tem` granting `TransactionalEmailFullAccess` scoped to project `4304a571-309f-4113-91a2-13f55f5e8bf2` and nothing else. The sender is `hallo@woobuddy.nl` on the TEM sending domain `woobuddy.nl` (see [Sending domain](#sending-domain)).

Rotate the key with:

```bash
scw -p bolster iam api-key create \
  application-id=982fc6f1-fe35-4222-93f1-4d99da9cdcef \
  description="WOO Buddy lead form - Scaleway TEM (prod VPS)" \
  default-project-id=4304a571-309f-4113-91a2-13f55f5e8bf2
```

Put the returned `secret_key` in the project-root `.env` as `SCALEWAY_SECRET_KEY` (or in 1Password, vault Bolster, and reference it as `op://...`), re-run `deploy.sh`, then delete the old key with `scw -p bolster iam api-key delete <old-access-key>`.

### Sending domain

`woobuddy.nl` is a verified Scaleway TEM sending domain (id
`546b876b-e199-4fb5-a08e-7bb091e6b874`, project `4304a571-309f-4113-91a2-13f55f5e8bf2`).
Two DNS records at TransIP carry it:

- **DKIM** — `TXT 4304a571-309f-4113-91a2-13f55f5e8bf2._domainkey` with the key from
  `scw -p bolster tem domain get <id>`.
- **SPF** — the apex `TXT` gained `include:_spf.tem.scaleway.com` alongside the
  existing Brevo and ImprovMX includes.

Scaleway's dashboard also proposes an MX record pointing at
`blackhole.tem.scaleway.com`. **Do not add it.** `woobuddy.nl` receives mail through
ImprovMX forwarding, which is what makes `hallo@woobuddy.nl` a replyable address; the
existing MX already satisfies Scaleway's check. A blackhole MX would silently discard
every reply.

Re-check the domain after a DNS change with `scw -p bolster tem domain check <id>` and
confirm delivery with `scw -p bolster tem email list` after one real submission.

If `.env` contains only literal values you can run the scripts directly without `op run`. As soon as any value is an `op://` URI, prefix the command with `op run --env-file=.env --`.

### Newsletter opt-in (#76)

WOO Buddy runs the double opt-in itself: the backend mails the confirmation, and only
when the recipient clicks the signed link does the address reach Listmonk. That needs
four values, none of which `install.sh` gates on — leave any of them empty and the opt-in
checkbox degrades to a no-op while the contact form keeps working.

| Variable | What it is |
|----------|------------|
| `LISTMONK_API_USER` / `LISTMONK_API_TOKEN` | A Listmonk **API user**: Admin → Users → New → type *API*, with a role granting `lists:get` and `subscribers:get` / `subscribers:manage`. Nothing else. |
| `LEADS_CONFIRM_SECRET` | HMAC secret for the confirmation link. Any long random string (`openssl rand -base64 32`). Rotating it invalidates links still in flight — a 48-hour window at most. |
| `PUBLIC_SITE_URL` | Where the confirmation link points. The public frontend origin, not the API. |

`/api/health` reports `newsletter_opt_in: configured` once all four are present and a list
UUID is set. It is advisory only, unlike `lead_mail`.

**Why not Listmonk's own double opt-in.** Listmonk's opt-in mail, sender address and
public pages are instance-global, and `listmonk.dreamkit.eu` is shared with Dreamkit. A
WOO Buddy signup therefore received a mail headed "DREAMKIT UPDATES" from
`noreply@mail.dreamkit.eu`, announcing a list named "WOO Buddy — leads", and landed on a
Dreamkit confirmation page. Sending our own confirmation is the only way to control all
three. `preconfirm_subscriptions` on the write keeps Listmonk from sending a second mail
regardless of how the list's opt-in setting is configured later.

**List hygiene, as a working agreement.** The list is named "WOO Buddy updates", is of
type *private*, and its opt-in is set to *single* — the confirmation is ours now, so
Listmonk must not send one of its own. Campaigns from this list get the sender
`WOO Buddy <hallo@woobuddy.nl>` set per campaign, because the instance default is
Dreamkit's.

**Known remaining gap:** the unsubscribe page at the bottom of a Listmonk campaign is
still Dreamkit-branded. That page comes from Listmonk's own campaign footer and cannot be
themed per list; a WOO Buddy unsubscribe endpoint would be its own piece of work.

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
4. Writes `/opt/woobuddy/.env` with `DBASE_PASSWORD` plus the lead-form mail config (piped over stdin, so no secret lands in an ssh argv). Bails out if a required value is unresolved.
5. SSHes in and runs `/opt/woobuddy/deploy/install.sh`, which builds the new images, rolls `api` and `frontend` one replica at a time via `docker rollout`, and `caddy reload`s gracefully so any Caddyfile edits land without dropping connections. On a fresh box (no containers yet) it falls back to `docker compose up -d`.

### Migration discipline

Because `docker rollout` keeps the old replica serving traffic until the new one is healthy, old and new code run against the same Postgres simultaneously for a few seconds per deploy. Alembic migrations therefore need to be **backward-compatible across one release**: follow the expand/contract pattern (add columns/tables nullable first, backfill and flip constraints in a follow-up release, drop dead columns in a third). A release that renames or drops a column in a single migration will break whichever replica hasn't been rolled yet.

If you ever need a breaking migration, the safe workaround is one manual deploy: scale the rolling services down to 1 with `docker compose -f docker-compose.prod.yml up -d --no-deps --scale frontend=1 --scale api=1 api frontend` before running `deploy.sh` — that reintroduces the brief downtime window in exchange for not having to straddle two schemas.

Verify after:

```bash
curl -I https://woobuddy.nl/
curl -fsS https://woobuddy.nl/api/health
```

A first-Caddy-boot TLS cert can take ~30s. After that, the deploy is live.

## Upgrading between releases

Self-hosters who want to pin a specific version instead of tracking `main` should follow tagged releases. Each `vX.Y.Z` tag publishes images to GHCR (`ghcr.io/jaapstronks/woobuddy-api:vX.Y.Z`, `ghcr.io/jaapstronks/woobuddy-frontend:vX.Y.Z`) and a [GitHub Release](https://github.com/jaapstronks/woobuddy/releases) with the changelog. To upgrade from a checkout: `git fetch --tags && git checkout vX.Y.Z && docker compose -f docker-compose.prod.yml up -d --build`. To upgrade from prebuilt images: bump the `:vX.Y.Z` tag in your compose override and `docker compose pull && docker compose up -d`. Either way, **read the release notes before you upgrade** — minor versions follow the expand/contract migration rules above (backward-compatible across one release), but breaking schema changes are called out explicitly and may need a manual `alembic upgrade head` on a stopped service.

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

Scheduled off-VPS backups are open work.

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
