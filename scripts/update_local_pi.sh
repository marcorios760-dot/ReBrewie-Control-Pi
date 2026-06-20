#!/usr/bin/env bash
# Update an existing Raspberry Pi installation from a local project checkout.
#
# Run this on the Pi from the unpacked/copied project directory:
#   sudo ./update.sh
# or:
#   sudo bash scripts/update_local_pi.sh
#
# Defaults preserve the Pi's .env, .venv, recipes/ and logs/ directories.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rebrewie-control-pi}"
SERVICE_NAME="${SERVICE_NAME:-rebrewie-control-pi}"
DEPLOY_RECIPES="${DEPLOY_RECIPES:-0}"
DRY_RUN="${DRY_RUN:-0}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Re-running with sudo …"
  exec sudo -E bash "$0" "$@"
fi

if [[ "$SOURCE_DIR" == "$APP_DIR" ]]; then
  echo "Source and destination are both $APP_DIR; nothing to copy."
else
  RSYNC_ARGS=(
    -a
    --delete
    --exclude '.git'
    --exclude '.venv'
    --exclude '__pycache__'
    --exclude '*.pyc'
    --exclude '.env'
    --exclude 'logs/'
  )

  if [[ "$DEPLOY_RECIPES" != "1" ]]; then
    RSYNC_ARGS+=(--exclude 'recipes/')
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    RSYNC_ARGS+=(--dry-run --itemize-changes)
  fi

  echo "→ Syncing $SOURCE_DIR/ to $APP_DIR/"
  mkdir -p "$APP_DIR"
  rsync "${RSYNC_ARGS[@]}" "$SOURCE_DIR/" "$APP_DIR/"
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "✓ Dry run complete; dependencies were not installed and service was not restarted."
  exit 0
fi

cd "$APP_DIR"

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "→ Created $APP_DIR/.env from .env.example"
fi

mkdir -p recipes

if [[ ! -x .venv/bin/python ]]; then
  echo "→ Creating Python virtualenv"
  python3 -m venv .venv
fi

echo "→ Installing/updating Python dependencies"
.venv/bin/python -m pip install -r requirements.txt

if systemctl list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1; then
  echo "→ Restarting ${SERVICE_NAME}"
  systemctl restart "$SERVICE_NAME"
  systemctl --no-pager --lines=20 status "$SERVICE_NAME"
else
  echo "⚠ ${SERVICE_NAME}.service not found; run ./install.sh once if this is a first install."
fi

echo "✓ Local Pi update complete"
