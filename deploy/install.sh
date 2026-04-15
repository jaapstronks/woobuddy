#!/usr/bin/env bash
# WOO Buddy — first-boot installer for a fresh Ubuntu 24.04 Hetzner VPS.
#
# This script runs on the VPS as root (cloud-init or manual ssh). It:
#   1. Installs Docker Engine + compose plugin from the official repo.
#   2. Creates /opt/woobuddy as the app home.
#   3. Expects the repo to already be at /opt/woobuddy (rsynced by the
#      developer) and .env to already contain DBASE_PASSWORD.
#   4. Brings the stack up with docker-compose.prod.yml.
#   5. Waits for the health endpoint to go green.
#
# Idempotent: running it twice is safe. Package installs are skipped if
# already present, and `docker compose up -d` reconciles to the declared
# state.

set -euo pipefail

APP_DIR="/opt/woobuddy"
COMPOSE_FILE="docker-compose.prod.yml"

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
# 2. App directory + .env sanity check
# ---------------------------------------------------------------------------
cd "${APP_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
	echo "ERROR: ${APP_DIR}/${COMPOSE_FILE} not found — rsync the repo first." >&2
	exit 1
fi

if [[ ! -f .env ]] || ! grep -q '^DBASE_PASSWORD=' .env; then
	echo "ERROR: ${APP_DIR}/.env must exist and contain DBASE_PASSWORD." >&2
	exit 1
fi

# Lock down .env — compose reads it via root, no other user needs to.
chmod 600 .env

# ---------------------------------------------------------------------------
# 3. Build + start
# ---------------------------------------------------------------------------
log "Building images (first run pulls Python/Node/Postgres base images)"
docker compose -f "${COMPOSE_FILE}" build

log "Starting stack"
docker compose -f "${COMPOSE_FILE}" up -d

# ---------------------------------------------------------------------------
# 4. Wait for health
# ---------------------------------------------------------------------------
log "Waiting for api to become healthy (Deduce NER load takes ~2s)"
for i in {1..60}; do
	status=$(docker compose -f "${COMPOSE_FILE}" ps --format json api \
		| python3 -c 'import sys,json; d=json.loads(sys.stdin.read() or "{}"); print(d.get("Health","") if isinstance(d,dict) else d[0].get("Health",""))' 2>/dev/null || echo "")
	if [[ "${status}" == "healthy" ]]; then
		log "API healthy"
		break
	fi
	sleep 2
done

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
