#!/usr/bin/env bash
# WOO Buddy — one-shot provisioning script.
#
# Runs under `op run --env-file=.env` so $HCLOUD_TOKEN and
# $TRANSIP_ACCESS_TOKEN are available as resolved secrets. Everything
# happens in one subprocess so the developer only has to tap Touch ID
# once for the whole flow.
#
# Steps:
#   1. Ensure SSH key `woobuddy-deploy` is uploaded to Hetzner.
#   2. Ensure server `woobuddy-prod` exists (cx22, fsn1, ubuntu-24.04).
#   3. Poll until the server has a public IPv4.
#   4. Write the IP to deploy/.vps-ip so later steps can read it.
#   5. Create/replace woobuddy.nl and www.woobuddy.nl A-records via
#      TransIP, pointing at the new IP.
#
# Idempotent: every step checks state first and skips if the desired
# state is already present.

set -euo pipefail

HCLOUD_API="https://api.hetzner.cloud/v1"
TRANSIP_API="https://api.transip.nl/v6"

SSH_KEY_NAME="woobuddy-deploy"
# Public key is read from deploy/.deploy_key.pub — the paired private key
# lives at deploy/.deploy_key (gitignored, 0600). Generate with:
#   ssh-keygen -t ed25519 -f deploy/.deploy_key -N ""
SSH_KEY_PUBLIC_FILE="$(cd "$(dirname "$0")" && pwd)/.deploy_key.pub"
if [[ ! -f "${SSH_KEY_PUBLIC_FILE}" ]]; then
	echo "ERROR: ${SSH_KEY_PUBLIC_FILE} missing. Generate with:" >&2
	echo "  ssh-keygen -t ed25519 -f deploy/.deploy_key -N \"\"" >&2
	exit 1
fi
SSH_KEY_PUBLIC="$(tr -d '\n' < "${SSH_KEY_PUBLIC_FILE}")"
SERVER_NAME="woobuddy-prod"
SERVER_TYPE="cx23"
SERVER_LOCATION="fsn1"
SERVER_IMAGE="ubuntu-24.04"
DOMAIN="woobuddy.nl"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IP_FILE="${REPO_ROOT}/deploy/.vps-ip"

log() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }
hcloud() { curl -sS -H "Authorization: Bearer ${HCLOUD_TOKEN}" -H "Content-Type: application/json" "$@"; }
transip() { curl -sS -H "Authorization: Bearer ${TRANSIP_ACCESS_TOKEN}" -H "Content-Type: application/json" "$@"; }

# ---------------------------------------------------------------------------
# 1. Upload SSH key (idempotent)
# ---------------------------------------------------------------------------
log "Ensuring SSH key '${SSH_KEY_NAME}' is uploaded to Hetzner"
existing_key_id=$(hcloud "${HCLOUD_API}/ssh_keys?name=${SSH_KEY_NAME}" \
	| python3 -c 'import sys,json; keys=json.load(sys.stdin).get("ssh_keys",[]); print(keys[0]["id"] if keys else "")')

if [[ -z "${existing_key_id}" ]]; then
	echo "  uploading new key..."
	create_resp=$(hcloud -X POST "${HCLOUD_API}/ssh_keys" \
		-d "{\"name\":\"${SSH_KEY_NAME}\",\"public_key\":\"${SSH_KEY_PUBLIC}\"}")
	ssh_key_id=$(echo "${create_resp}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["ssh_key"]["id"])')
	echo "  created ssh_key_id=${ssh_key_id}"
else
	ssh_key_id="${existing_key_id}"
	echo "  already present, ssh_key_id=${ssh_key_id}"
fi

# ---------------------------------------------------------------------------
# 2. Create server (idempotent by name)
# ---------------------------------------------------------------------------
log "Ensuring server '${SERVER_NAME}' exists (${SERVER_TYPE} / ${SERVER_LOCATION} / ${SERVER_IMAGE})"
existing_server=$(hcloud "${HCLOUD_API}/servers?name=${SERVER_NAME}" \
	| python3 -c 'import sys,json; s=json.load(sys.stdin).get("servers",[]); print(s[0]["id"] if s else "")')

if [[ -z "${existing_server}" ]]; then
	echo "  creating server (BILLABLE: €4.83/month gross recurring)..."
	create_body=$(python3 -c "
import json
print(json.dumps({
    'name': '${SERVER_NAME}',
    'server_type': '${SERVER_TYPE}',
    'location': '${SERVER_LOCATION}',
    'image': '${SERVER_IMAGE}',
    'ssh_keys': [${ssh_key_id}],
    'start_after_create': True,
    'labels': {'project': 'woobuddy', 'env': 'prod'},
}))
")
	create_resp=$(hcloud -X POST "${HCLOUD_API}/servers" -d "${create_body}")
	server_id=$(echo "${create_resp}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["server"]["id"])')
	echo "  created server_id=${server_id}"
else
	server_id="${existing_server}"
	echo "  already exists, server_id=${server_id}"
fi

# ---------------------------------------------------------------------------
# 3. Poll for IPv4
# ---------------------------------------------------------------------------
log "Waiting for public IPv4"
server_ip=""
for i in {1..60}; do
	server_ip=$(hcloud "${HCLOUD_API}/servers/${server_id}" \
		| python3 -c 'import sys,json; s=json.load(sys.stdin)["server"]; print(s["public_net"]["ipv4"]["ip"] or "")')
	if [[ -n "${server_ip}" ]]; then
		echo "  got ${server_ip}"
		break
	fi
	sleep 2
done

if [[ -z "${server_ip}" ]]; then
	echo "ERROR: server never got an IPv4 after 120s" >&2
	exit 1
fi

mkdir -p "$(dirname "${IP_FILE}")"
echo "${server_ip}" > "${IP_FILE}"
chmod 600 "${IP_FILE}"
echo "  wrote IP to ${IP_FILE}"

# ---------------------------------------------------------------------------
# 4. DNS via TransIP — replace A-records for @ and www
# ---------------------------------------------------------------------------
log "Updating DNS for ${DOMAIN} via TransIP"

# Fetch existing entries.
dns_before=$(transip "${TRANSIP_API}/domains/${DOMAIN}/dns")
echo "${dns_before}" > /tmp/transip_dns_before.json
echo "  current A-records for @ and www:"
python3 - <<'PY'
import json
d = json.load(open("/tmp/transip_dns_before.json"))
for e in d.get("dnsEntries", []):
    if e["type"] == "A" and e["name"] in ("@", "www"):
        print("    {:<4} A {:<20} (ttl {})".format(e["name"], e["content"], e["expire"]))
PY

# Delete any existing A record for @ or www. TransIP DELETE /dns takes the
# exact dnsEntry in the body.
for name in "@" "www"; do
	existing=$(python3 - "${name}" <<'PY'
import json, sys
wanted = sys.argv[1]
d = json.load(open("/tmp/transip_dns_before.json"))
for e in d.get("dnsEntries", []):
    if e["type"] == "A" and e["name"] == wanted:
        print(json.dumps(e))
        break
PY
	)
	if [[ -n "${existing}" ]]; then
		echo "  deleting old A record for '${name}'..."
		transip -X DELETE "${TRANSIP_API}/domains/${DOMAIN}/dns" \
			-d "{\"dnsEntry\":${existing}}"
	fi
done

# Create new A records pointing at the new IP.
for name in "@" "www"; do
	echo "  creating A record '${name}' -> ${server_ip}"
	transip -X POST "${TRANSIP_API}/domains/${DOMAIN}/dns" \
		-d "{\"dnsEntry\":{\"name\":\"${name}\",\"expire\":300,\"type\":\"A\",\"content\":\"${server_ip}\"}}"
done

log "Final DNS state"
transip "${TRANSIP_API}/domains/${DOMAIN}/dns" > /tmp/transip_dns_after.json
python3 - <<'PY'
import json
d = json.load(open("/tmp/transip_dns_after.json"))
for e in d.get("dnsEntries", []):
    if e["type"] == "A" and e["name"] in ("@", "www"):
        print("    {:<4} A {:<20} (ttl {})".format(e["name"], e["content"], e["expire"]))
PY

cat <<EOF

Provisioning complete.
  server_id  : ${server_id}
  public_ip  : ${server_ip}
  ssh_key_id : ${ssh_key_id}
  ip written : ${IP_FILE}

Next: rsync the repo to root@${server_ip}:/opt/woobuddy and run deploy/install.sh.
EOF
