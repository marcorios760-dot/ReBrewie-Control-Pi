#!/usr/bin/env bash
# Deploy the current checkout to an existing Raspberry Pi installation over SSH.
# Run this from your laptop/desktop, not from an SSH shell already on the Pi.
# If you are already on the Pi, use scripts/update_local_pi.sh instead.
# Deploy the current checkout to an existing Raspberry Pi installation.
#
# Required:
#   PI_HOST=192.168.1.50 scripts/deploy_to_pi.sh
# Optional:
#   PI_USER=pi APP_DIR=/opt/rebrewie-control-pi SERVICE_NAME=rebrewie-control-pi \
#   DEPLOY_RECIPES=1 DRY_RUN=1 scripts/deploy_to_pi.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rebrewie-control-pi}"
SERVICE_NAME="${SERVICE_NAME:-rebrewie-control-pi}"
PI_HOST="${PI_HOST:-${1:-}}"
PI_USER="${PI_USER:-}"
SSH_OPTS="${SSH_OPTS:-}"
DRY_RUN="${DRY_RUN:-0}"
DEPLOY_RECIPES="${DEPLOY_RECIPES:-0}"

if [[ -z "$PI_HOST" ]]; then
  cat >&2 <<'EOF'
Usage:
  PI_HOST=pi-ip-or-hostname [PI_USER=pi] scripts/deploy_to_pi.sh

Do not type angle brackets. Use PI_HOST=192.168.1.XXX, not PI_HOST=<192.168.1.XXX>.
Run this from another computer with SSH access to the Pi. If you are already
on the Pi, run: sudo scripts/update_local_pi.sh
  PI_HOST=<pi-ip-or-hostname> [PI_USER=pi] scripts/deploy_to_pi.sh

Examples:
  PI_HOST=192.168.1.50 PI_USER=pi scripts/deploy_to_pi.sh
  PI_HOST=rebrewie.local APP_DIR=/opt/rebrewie-control-pi scripts/deploy_to_pi.sh
  PI_HOST=192.168.1.50 DRY_RUN=1 scripts/deploy_to_pi.sh

The deploy preserves the Pi's .env, .venv, recipes/ and logs by default.
Set DEPLOY_RECIPES=1 only if you intentionally want to sync repo recipes too.
EOF
  exit 2
fi

if [[ "$PI_HOST" == *'<'* || "$PI_HOST" == *'>'* ]]; then
  cat >&2 <<EOF
Invalid PI_HOST: $PI_HOST
Do not include angle brackets. Example:
  PI_HOST=192.168.1.XXX PI_USER=pi scripts/deploy_to_pi.sh
EOF
  exit 2
fi

SSH_TARGET="$PI_HOST"
if [[ -n "$PI_USER" ]]; then
  SSH_TARGET="${PI_USER}@${PI_HOST}"
fi

RSYNC_COMMON=(
  --archive
  --compress
  --delete
  --exclude .git/
  --exclude .venv/
  --exclude __pycache__/
  --exclude '*.pyc'
  --exclude .env
  --exclude logs/
)

REMOTE_RSYNC_EXCLUDES=(
  --exclude .env
  --exclude .venv/
  --exclude logs/
)

if [[ "$DEPLOY_RECIPES" != "1" ]]; then
  RSYNC_COMMON+=(--exclude recipes/)
  REMOTE_RSYNC_EXCLUDES+=(--exclude recipes/)
fi

if [[ "$DRY_RUN" == "1" ]]; then
  RSYNC_COMMON+=(--dry-run --itemize-changes)
fi

run_ssh() {
  # shellcheck disable=SC2086 # SSH_OPTS is intentionally split like ssh itself.
  ssh $SSH_OPTS "$SSH_TARGET" "$@"
}

run_rsync() {
  local src="$1"
  local dest="$2"
  # shellcheck disable=SC2086 # SSH_OPTS is intentionally split like ssh itself.
  rsync "${RSYNC_COMMON[@]}" -e "ssh $SSH_OPTS" "$src" "$dest"
}

REMOTE_TMP="$(run_ssh 'mktemp -d /tmp/rebrewie-deploy.XXXXXX')"
cleanup() {
  run_ssh "rm -rf '$REMOTE_TMP'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "→ Syncing checkout to ${SSH_TARGET}:${REMOTE_TMP}"
run_rsync ./ "${SSH_TARGET}:${REMOTE_TMP}/"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "✓ Dry run complete; no files copied into ${APP_DIR} and service was not restarted."
  exit 0
fi

echo "→ Installing files into ${APP_DIR} (preserving .env, .venv, logs, and recipes by default)"
run_ssh "sudo mkdir -p '$APP_DIR' && sudo rsync -a --delete ${REMOTE_RSYNC_EXCLUDES[*]} '$REMOTE_TMP/' '$APP_DIR/'"

echo "→ Ensuring Python virtualenv exists and dependencies are installed"
run_ssh "cd '$APP_DIR' && if [ ! -x .venv/bin/python ]; then sudo python3 -m venv .venv; fi && sudo .venv/bin/python -m pip install -r requirements.txt"

echo "→ Restarting ${SERVICE_NAME} if systemd service exists"
run_ssh "if systemctl list-unit-files '${SERVICE_NAME}.service' >/dev/null 2>&1; then sudo systemctl restart '${SERVICE_NAME}'; sudo systemctl --no-pager --lines=20 status '${SERVICE_NAME}'; else echo 'Service ${SERVICE_NAME}.service not found; start manually with uvicorn or run install.sh first.'; fi"

echo "✓ Deploy complete"
