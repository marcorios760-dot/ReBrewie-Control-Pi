#!/usr/bin/env bash
# Configure an installed Raspberry Pi service to use the stock Brewie TCP bridge.
#
# Example:
#   sudo BREWIE_HOST=192.168.1.132 scripts/configure_brewie_tcp.sh
#   sudo scripts/configure_brewie_tcp.sh 192.168.1.132 9000
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rebrewie-control-pi}"
SERVICE_NAME="${SERVICE_NAME:-rebrewie-control-pi}"
BREWIE_HOST="${1:-${BREWIE_HOST:-192.168.1.132}}"
BREWIE_PORT="${2:-${BREWIE_PORT:-9000}}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"

if [[ $EUID -ne 0 ]]; then
  echo "Re-running with sudo …"
  exec sudo -E bash "$0" "$@"
fi

if [[ -z "$BREWIE_HOST" || "$BREWIE_HOST" == *'<'* || "$BREWIE_HOST" == *'>'* ]]; then
  echo "ERROR: Use a plain IP address, for example: 192.168.1.132" >&2
  exit 2
fi

if [[ ! "$BREWIE_PORT" =~ ^[0-9]+$ ]]; then
  echo "ERROR: BREWIE_PORT must be a number, for example: 9000" >&2
  exit 2
fi

mkdir -p "$(dirname "$ENV_FILE")"
if [[ -f "$ENV_FILE" ]]; then
  backup="$ENV_FILE.bak.$(date +%Y%m%d%H%M%S)"
  cp "$ENV_FILE" "$backup"
  echo "→ Backed up $ENV_FILE to $backup"
elif [[ -f "$APP_DIR/.env.example" ]]; then
  cp "$APP_DIR/.env.example" "$ENV_FILE"
  echo "→ Created $ENV_FILE from $APP_DIR/.env.example"
else
  touch "$ENV_FILE"
  echo "→ Created $ENV_FILE"
fi

set_env_value() {
  key="$1"
  value="$2"
  if grep -Eq "^[[:space:]]*#?[[:space:]]*${key}=" "$ENV_FILE"; then
    sed -i -E "s|^[[:space:]]*#?[[:space:]]*${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

set_env_value BREWIE_TRANSPORT tcp
set_env_value BREWIE_HOST "$BREWIE_HOST"
set_env_value BREWIE_PORT "$BREWIE_PORT"

# Leave BREWIE_HTTP_BASE in place for future HTTP experiments, but it is ignored
# while BREWIE_TRANSPORT=tcp.

echo "→ Active Brewie TCP configuration in $ENV_FILE:"
grep -E '^(BREWIE_TRANSPORT|BREWIE_HOST|BREWIE_PORT)=' "$ENV_FILE"

if systemctl list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1; then
  echo "→ Restarting ${SERVICE_NAME}"
  systemctl restart "$SERVICE_NAME"
  systemctl --no-pager --lines=20 status "$SERVICE_NAME" || true
else
  echo "⚠ ${SERVICE_NAME}.service not found; update $ENV_FILE is complete but no service was restarted."
fi

pi_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
if [[ -n "${pi_ip:-}" ]]; then
  echo ""
  echo "Open these from your browser:"
  echo "  http://${pi_ip}:8080/api/status"
  echo "  http://${pi_ip}:8080/api/log?n=200"
fi
