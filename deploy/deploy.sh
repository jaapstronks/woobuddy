#!/usr/bin/env bash
# WOO Buddy — remote deploy: rsync the repo to the VPS and run install.sh.
#
# Runs under `op run --env-file=.env` so $HETZNER_PRIVATE_KEY and
# $DBASE_PASSWORD are resolved from 1Password.
#
# Steps:
#   1. Read VPS IP from deploy/.vps-ip (written by provision.sh).
#   2. Materialize the ed25519 private key to a tmp file with 0600 perms.
#   3. Poll until SSH is accepting connections on port 22.
#   4. rsync the repo to /opt/woobuddy on the VPS (excluding build artefacts).
#   5. Write /opt/woobuddy/.env with DBASE_PASSWORD plus the lead-form mail
#      config (the provisioning secrets stay off the box).
#   6. SSH in and run /opt/woobuddy/deploy/install.sh.
#
# Idempotent: re-running syncs incremental changes and re-converges the
# docker-compose state.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IP_FILE="${REPO_ROOT}/deploy/.vps-ip"
REMOTE_USER="root"
REMOTE_DIR="/opt/woobuddy"

if [[ ! -f "${IP_FILE}" ]]; then
	echo "ERROR: ${IP_FILE} missing — run deploy/provision.sh first." >&2
	exit 1
fi
VPS_IP="$(cat "${IP_FILE}")"
if [[ -z "${VPS_IP}" ]]; then
	echo "ERROR: ${IP_FILE} empty." >&2
	exit 1
fi

log() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# Deploy private key — lives at deploy/.deploy_key (gitignored, 0600). This
# is a throwaway ed25519 key generated once for this project. If it leaks,
# rotate by regenerating and re-running provision.sh.
# ---------------------------------------------------------------------------
KEY_FILE="${REPO_ROOT}/deploy/.deploy_key"
if [[ ! -f "${KEY_FILE}" ]]; then
	echo "ERROR: ${KEY_FILE} missing. Generate with:" >&2
	echo "  ssh-keygen -t ed25519 -f deploy/.deploy_key -N \"\"" >&2
	exit 1
fi
chmod 600 "${KEY_FILE}"

SSH_OPTS=(
	-i "${KEY_FILE}"
	-o IdentitiesOnly=yes
	-o IdentityAgent=none
	-o StrictHostKeyChecking=accept-new
	-o UserKnownHostsFile="${REPO_ROOT}/deploy/.known_hosts"
	-o ConnectTimeout=10
	-o BatchMode=yes
)

# ---------------------------------------------------------------------------
# SSH wrapper for rsync.
#
# rsync's `-e` takes a single string and re-splits it on whitespace, so we
# can't just pass `ssh ${SSH_OPTS[*]}` — REPO_ROOT contains a space ("Github
# NW"), which breaks the key path. The wrapper sidesteps that by keeping all
# options inside a script that rsync invokes as a single executable.
# ---------------------------------------------------------------------------
SSH_WRAPPER="$(mktemp -t woobuddy-ssh.XXXXXX)"
trap 'rm -f "${SSH_WRAPPER}"' EXIT
cat > "${SSH_WRAPPER}" <<WRAPPER
#!/usr/bin/env bash
exec ssh \\
  -i "${KEY_FILE}" \\
  -o IdentitiesOnly=yes \\
  -o IdentityAgent=none \\
  -o StrictHostKeyChecking=accept-new \\
  -o UserKnownHostsFile="${REPO_ROOT}/deploy/.known_hosts" \\
  -o ConnectTimeout=10 \\
  -o BatchMode=yes \\
  "\$@"
WRAPPER
chmod 700 "${SSH_WRAPPER}"

# ---------------------------------------------------------------------------
# Wait for SSH
# ---------------------------------------------------------------------------
log "Waiting for SSH on ${VPS_IP}:22"
for i in {1..60}; do
	if ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${VPS_IP}" true 2>/dev/null; then
		echo "  ssh ready"
		break
	fi
	if [[ ${i} -eq 60 ]]; then
		echo "ERROR: ssh never came up on ${VPS_IP}" >&2
		exit 1
	fi
	sleep 3
done

# ---------------------------------------------------------------------------
# rsync repo
# ---------------------------------------------------------------------------
log "Rsyncing repo to ${REMOTE_USER}@${VPS_IP}:${REMOTE_DIR}"
ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${VPS_IP}" "mkdir -p ${REMOTE_DIR}"

rsync -az --delete \
	-e "${SSH_WRAPPER}" \
	--exclude='.git/' \
	--exclude='node_modules/' \
	--exclude='.venv/' \
	--exclude='__pycache__/' \
	--exclude='*.pyc' \
	--exclude='.svelte-kit/' \
	--exclude='frontend/build/' \
	--exclude='backend/.venv/' \
	--exclude='backend/.pytest_cache/' \
	--exclude='backend/htmlcov/' \
	--exclude='deploy/.vps-ip' \
	--exclude='deploy/.known_hosts' \
	--exclude='.env' \
	--exclude='.env.local' \
	--exclude='.DS_Store' \
	--exclude='tmp/' \
	--exclude='docs/' \
	"${REPO_ROOT}/" "${REMOTE_USER}@${VPS_IP}:${REMOTE_DIR}/"

# ---------------------------------------------------------------------------
# Write prod .env on the VPS.
#
# Two groups: the Postgres password, and the lead-form mail config that
# docker-compose.prod.yml interpolates into the api service. The
# provisioning secrets (Hetzner, TransIP) stay off the box.
#
# #72: the mail keys used to be missing here entirely, so the api container
# booted with an empty Scaleway key and every contact-form submission
# returned a 500 that only the visitor ever saw. SCALEWAY_SECRET_KEY is
# therefore required, not optional — install.sh refuses to deploy without it.
# ---------------------------------------------------------------------------
log "Writing ${REMOTE_DIR}/.env (db password + lead-form mail config)"

require_var() {
	local name="$1"
	if [[ -z "${!name:-}" ]]; then
		echo "ERROR: ${name} not resolved — check the project-root .env (run under \`op run --env-file=.env --\` if it holds op:// references)." >&2
		exit 1
	fi
}

require_var DBASE_PASSWORD
require_var SCALEWAY_SECRET_KEY
require_var SCALEWAY_PROJECT_ID
require_var NOTIFICATION_EMAIL

# Defaults mirror docker-compose.prod.yml so a partially-filled .env still
# produces a working stack rather than a half-configured one.
SCALEWAY_TEM_REGION="${SCALEWAY_TEM_REGION:-fr-par}"
TEM_FROM_EMAIL="${TEM_FROM_EMAIL:-noreply@mail.dreamkit.eu}"
TEM_FROM_NAME="${TEM_FROM_NAME:-WOO Buddy}"
LISTMONK_URL="${LISTMONK_URL:-https://listmonk.dreamkit.eu}"
# Empty is a valid choice: it turns the newsletter opt-in off and leaves the
# notification mail working. The same goes for the three keys below (#76):
# without them the opt-in checkbox degrades to a no-op instead of failing.
LISTMONK_LIST_UUID="${LISTMONK_LIST_UUID:-}"
LISTMONK_API_USER="${LISTMONK_API_USER:-}"
LISTMONK_API_TOKEN="${LISTMONK_API_TOKEN:-}"
LEADS_CONFIRM_SECRET="${LEADS_CONFIRM_SECRET:-}"
PUBLIC_SITE_URL="${PUBLIC_SITE_URL:-https://woobuddy.nl}"

# Built locally and piped over stdin so no secret ever appears in an ssh
# argv (visible in `ps` on the remote box) or in this script's `set -x`.
REMOTE_ENV="$(
	printf 'DBASE_PASSWORD=%s\n' "${DBASE_PASSWORD}"
	printf 'SCALEWAY_SECRET_KEY=%s\n' "${SCALEWAY_SECRET_KEY}"
	printf 'SCALEWAY_PROJECT_ID=%s\n' "${SCALEWAY_PROJECT_ID}"
	printf 'SCALEWAY_TEM_REGION=%s\n' "${SCALEWAY_TEM_REGION}"
	printf 'TEM_FROM_EMAIL=%s\n' "${TEM_FROM_EMAIL}"
	printf 'TEM_FROM_NAME=%s\n' "${TEM_FROM_NAME}"
	printf 'NOTIFICATION_EMAIL=%s\n' "${NOTIFICATION_EMAIL}"
	printf 'LISTMONK_URL=%s\n' "${LISTMONK_URL}"
	printf 'LISTMONK_LIST_UUID=%s\n' "${LISTMONK_LIST_UUID}"
	printf 'LISTMONK_API_USER=%s\n' "${LISTMONK_API_USER}"
	printf 'LISTMONK_API_TOKEN=%s\n' "${LISTMONK_API_TOKEN}"
	printf 'LEADS_CONFIRM_SECRET=%s\n' "${LEADS_CONFIRM_SECRET}"
	printf 'PUBLIC_SITE_URL=%s\n' "${PUBLIC_SITE_URL}"
)"

printf '%s\n' "${REMOTE_ENV}" | ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${VPS_IP}" \
	"umask 077 && cat > ${REMOTE_DIR}/.env && chmod 600 ${REMOTE_DIR}/.env"

# ---------------------------------------------------------------------------
# Run installer
# ---------------------------------------------------------------------------
log "Running ${REMOTE_DIR}/deploy/install.sh"
ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${VPS_IP}" \
	"chmod +x ${REMOTE_DIR}/deploy/install.sh && ${REMOTE_DIR}/deploy/install.sh"

log "Deploy finished"
echo "Verify with: curl -I https://woobuddy.nl/"
