#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh  –  ReBrewie Control Pi installer
#
# Run from the extracted project directory: *run "sudo bash" first to run as root if initial attempt fails
#   chmod +x install.sh && ./install.sh  
#
# The script must be run as root (or it re-launches itself with sudo).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rebrewie-control-pi}"
SERVICE_NAME="rebrewie-control-pi"

if [[ $EUID -ne 0 ]]; then
  echo "Re-running with sudo …"
  exec sudo -H bash "$0" "$@"
fi

echo "═══════════════════════════════════════════"
echo "  ReBrewie Control Pi – Installer"
echo "═══════════════════════════════════════════"

# ── System packages ──────────────────────────────────────────────────────────
echo "[1/6] Installing system packages …"
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip rsync

# ── Copy application files ───────────────────────────────────────────────────
echo "[2/6] Copying files to $APP_DIR …"
mkdir -p "$APP_DIR"
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.env' \
  ./ "$APP_DIR/"

# ── Python virtualenv ────────────────────────────────────────────────────────
echo "[3/6] Creating Python virtualenv …"
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

echo "      Verifying application import …"
.venv/bin/python - <<'PY'
from app.main import app

required = {"/api/status", "/api/recipes", "/api/discovery/devices", "/api/device/current", "/ws"}
paths = {route.path for route in app.routes}
missing = sorted(required - paths)
if missing:
    raise SystemExit(f"Missing expected routes: {missing}")
print(f"      App import OK ({len(paths)} routes registered)")
PY

# ── First-run .env ───────────────────────────────────────────────────────────
echo "[4/6] Configuring environment …"
if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "      .env created from .env.example – edit it to set your transport."
else
  echo "      .env already exists – skipping."
fi

# ── Recipes directory ────────────────────────────────────────────────────────
mkdir -p "$APP_DIR/recipes"

# ── systemd service ──────────────────────────────────────────────────────────
echo "[5/6] Installing systemd service …"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
cp "$APP_DIR/systemd/${SERVICE_NAME}.service" "$SERVICE_FILE"

# Patch paths in the service file
UVICORN="$APP_DIR/.venv/bin/uvicorn"
sed -i "s|WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|"         "$SERVICE_FILE"
sed -i "s|EnvironmentFile=.*|EnvironmentFile=${APP_DIR}/.env|"      "$SERVICE_FILE"
sed -i "s|ExecStart=.*|ExecStart=${UVICORN} app.main:app --host 0.0.0.0 --port 8080|" "$SERVICE_FILE"

# Use current user if not 'pi'
CURRENT_USER="${SUDO_USER:-pi}"
sed -i "s|User=pi|User=${CURRENT_USER}|" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable  "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 1
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "ERROR: $SERVICE_NAME did not stay running. Recent logs:" >&2
  journalctl -u "$SERVICE_NAME" --no-pager -n 50 >&2 || true
  exit 1
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo "[6/6] Done!"
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo ""
echo "  ✓ Service: $SERVICE_NAME (systemctl status $SERVICE_NAME)"
echo "  ✓ Open:    http://${PI_IP:-localhost}:8080"
echo ""
echo "  Edit $APP_DIR/.env to configure:"
echo "    BREWIE_TRANSPORT=tcp  (or serial / http / mock)"
echo "    BREWIE_HOST=<your-brewie-ip>"
echo "  Then: sudo systemctl restart $SERVICE_NAME"
echo ""
echo "  ⚠  Keep this service on your local LAN only."
echo "     Do NOT port-forward port 8080 to the internet."
