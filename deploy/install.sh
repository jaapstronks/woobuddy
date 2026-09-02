#!/usr/bin/env bash
# WOO Buddy — first-boot installer + rolling-update runner for the
# Hetzner VPS.
#
# This script runs on the VPS as root (cloud-init or manual ssh). It:
#   1. Installs Docker Engine + compose plugin from the official repo.
#   2. Installs the `docker-rollout` CLI plugin for zero-downtime updates.
#   3. Expects the repo to already be at /opt/woobuddy (rsynced by the
#      developer) and .env to already contain DBASE_PASSWORD plus the
#      lead-form mail config. Refuses to deploy if either is missing.
#   4a. First deploy — `docker compose up -d` brings the whole stack up.
#   4b. Update deploy — builds new images, rolls `api` and `frontend`
#       one replica at a time behind Caddy, and gracefully reloads Caddy
#       in case the Caddyfile changed.
#   5. Waits for the health endpoint to go green.
#
# Idempotent: running it twice is safe. Package installs are skipped if
# already present, and the rollout dance is skipped on a fresh box.

set -euo pipefail

APP_DIR="/opt/woobuddy"
COMPOSE_FILE="docker-compose.prod.yml"

# docker-rollout release is pinned to a SHA rather than a tag so a
# compromised upstream tag can't silently change what runs here. Bump
# when reviewing a new upstream commit.
ROLLOUT_REPO="Wowu/docker-rollout"
ROLLOUT_SHA="a25ac4ce474e140d93625419ace38befa602d8c2"
ROLLOUT_DEST="/root/.docker/cli-plugins/docker-rollout"

log() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# 1. Docker Engine
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
	log "Installing Docker Engine"
	apt-get update
	apt-get install -y ca-certificates curl gnupg
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
		| gpg --dearmor -o /etc/apt/keyrings/docker.gpg
	chmod a+r /etc/apt/keyrings/docker.gpg
	# shellcheck disable=SC1091
	. /etc/os-release
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
		> /etc/apt/sources.list.d/docker.list
	apt-get update
	apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
	systemctl enable --now docker
else
	log "Docker already installed ($(docker --version))"
fi

# ---------------------------------------------------------------------------
# 2. docker-rollout plugin (for zero-downtime updates)
# ---------------------------------------------------------------------------
if [[ ! -x "${ROLLOUT_DEST}" ]]; then
	log "Installing docker-rollout plugin (${ROLLOUT_SHA:0:7})"
	install -m 0755 -d "$(dirname "${ROLLOUT_DEST}")"
	curl -fsSL "https://raw.githubusercontent.com/${ROLLOUT_REPO}/${ROLLOUT_SHA}/docker-rollout" \
		-o "${ROLLOUT_DEST}"
	chmod 0755 "${ROLLOUT_DEST}"
else
	log "docker-rollout already installed"
fi

# ---------------------------------------------------------------------------
# 3. App directory + .env sanity check
# ---------------------------------------------------------------------------
cd "${APP_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
	echo "ERROR: ${APP_DIR}/${COMPOSE_FILE} not found — rsync the repo first." >&2
	exit 1
fi

if [[ ! -f .env ]]; then
	echo "ERROR: ${APP_DIR}/.env not found — run deploy/deploy.sh, which writes it." >&2
	exit 1
fi

# Required keys must be present AND non-empty. #72: the mail config was
# absent here for months, so the api booted with an empty Scaleway key and
# the contact form 500'd on every submission — a failure only the visitor
# ever saw. A deploy that cannot send mail now fails here, loudly, instead.
#
# LISTMONK_LIST_UUID is deliberately not required: empty is a valid choice
# that disables the newsletter opt-in and leaves notification mail working.
missing=()
for key in DBASE_PASSWORD SCALEWAY_SECRET_KEY SCALEWAY_PROJECT_ID \
	TEM_FROM_EMAIL NOTIFICATION_EMAIL; do
	if ! grep -qE "^${key}=.+$" .env; then
		missing+=("${key}")
	fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
	echo "ERROR: ${APP_DIR}/.env is missing or has an empty value for: ${missing[*]}" >&2
	echo "       Fix the project-root .env on the developer machine and re-run deploy/deploy.sh." >&2
	exit 1
fi

# Lock down .env — compose reads it via root, no other user needs to.
chmod 600 .env

# ---------------------------------------------------------------------------
# 4. Build + start / update
# ---------------------------------------------------------------------------
log "Building images (first run pulls Python/Node/Postgres base images)"
docker compose -f "${COMPOSE_FILE}" build

# Detect first deploy vs update by checking whether the frontend service
# is currently running. On a fresh box we fall back to plain `docker
# compose up -d`; otherwise we roll `api` and `frontend` one at a time
# so Caddy keeps serving the old replica until the new one is healthy.
is_running() {
	local svc="$1"
	local count
	count=$(docker compose -f "${COMPOSE_FILE}" ps --status running --quiet "${svc}" | wc -l)
	[[ "${count}" -gt 0 ]]
}

if is_running frontend && is_running api; then
	log "Rolling stateless services (zero-downtime)"

	# Caddy + Postgres first. `--no-recreate` is load-bearing: without it,
	# compose walks `depends_on` and recreates api + frontend inline when
	# their compose config changed (e.g. a healthcheck tweak), killing
	# the old containers *before* `docker rollout` can scale up
	# replacements — exactly the downtime window we're trying to avoid.
	# The Caddyfile is bind-mounted and gets applied by the
	# `caddy reload` below; caddy image changes are rare and can be
	# handled by a targeted `--force-recreate caddy` on the (hopefully
	# never) day they happen.
	docker compose -f "${COMPOSE_FILE}" up -d --no-recreate caddy postgres

	# Roll api before frontend: the frontend only calls the api via Caddy
	# (same-origin), so draining frontend first would still leave old
	# frontend pods making calls against whichever api is up. Rolling
	# api first means by the time we touch the frontend, every frontend
	# replica — old and new — is talking to a fresh api.
	#
	# -t 180 overrides docker-rollout's 60s default: Deduce NER rebuilds
	# its Dutch-name lookup structures on first boot (~90s) before the
	# FastAPI lifespan finishes and /api/health starts returning 200.
	# The compose healthcheck already has `start_period: 90s`, but
	# docker-rollout polls `State.Health.Status` on its own clock and
	# would otherwise give up before Deduce is ready. 180s leaves room.
	# Frontend boots in seconds, but the same timeout is harmless — a
	# healthy container rolls instantly; the cap only bounds rollback.
	docker rollout -f "${COMPOSE_FILE}" -t 180 api
	docker rollout -f "${COMPOSE_FILE}" -t 180 frontend

	# Graceful Caddy reload in case the Caddyfile changed on disk. The
	# bind mount means new contents are already visible inside the
	# container; `caddy reload` tells the daemon to re-read them without
	# dropping connections.
	log "Reloading Caddy (graceful, no downtime)"
	docker compose -f "${COMPOSE_FILE}" exec -T caddy \
		caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
else
	log "Starting stack (first deploy)"
	docker compose -f "${COMPOSE_FILE}" up -d
fi

# ---------------------------------------------------------------------------
# 5. Wait for health
# ---------------------------------------------------------------------------
log "Waiting for api to become healthy (Deduce NER load takes ~2s)"
for i in {1..60}; do
	status=$(docker compose -f "${COMPOSE_FILE}" ps --format json api \
		| python3 -c 'import sys,json
raw=sys.stdin.read().strip()
if not raw:
    print(""); sys.exit()
# `compose ps --format json` emits one JSON object per line — take the first.
line=raw.splitlines()[0]
d=json.loads(line)
print(d.get("Health",""))' 2>/dev/null || echo "")
	if [[ "${status}" == "healthy" ]]; then
		log "API healthy"
		break
	fi
	sleep 2
done

# The .env check above proves the key reached the box; this proves it
# reached the *process*. Between the two sits the compose `environment:`
# block, which is exactly where #72 went wrong.
log "Verifying the api can send lead mail"
lead_mail=$(docker compose -f "${COMPOSE_FILE}" exec -T api python -c \
	"import httpx; print(httpx.get('http://localhost:8000/api/health').json().get('lead_mail',''))" \
	2>/dev/null | tr -d '\r' | tail -n 1)
if [[ "${lead_mail}" != "configured" ]]; then
	echo "ERROR: api reports lead_mail='${lead_mail}' — the mail config did not reach the container." >&2
	echo "       Check the \`environment:\` block for the api service in ${COMPOSE_FILE}." >&2
	exit 1
fi
echo "  lead_mail: configured"

log "Stack status"
docker compose -f "${COMPOSE_FILE}" ps

cat <<EOF

Done. The box should now be serving:
  https://woobuddy.nl         (frontend)
  https://woobuddy.nl/api/*   (api)
  https://www.woobuddy.nl     (redirect → apex)

First request may take ~30s while Caddy completes the Let's Encrypt
HTTP-01 challenge. Check Caddy logs if TLS doesn't come up:
  docker compose -f ${COMPOSE_FILE} logs -f caddy
EOF
