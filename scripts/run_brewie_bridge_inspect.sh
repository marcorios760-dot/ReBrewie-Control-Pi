#!/usr/bin/env bash
# Run the Brewie+ bridge inspection helper over SSH without scp/SFTP.
# This works on Brewie firmware where scp fails with:
#   sh: /usr/libexec/sftp-server: not found
set -euo pipefail

BREWIE_HOST="${BREWIE_HOST:-${1:-192.168.1.XXX}}"
BREWIE_USER="${BREWIE_USER:-root}"
SSH_OPTS="${SSH_OPTS:-}"
OUT_FILE="${OUT_FILE:-./brewie_bridge_inspect.txt}"
HELPER="contrib/brewie-machine/brewie_bridge_inspect.sh"

if [[ ! -f "$HELPER" ]]; then
  cat >&2 <<EOF
Missing local helper: $HELPER

Your Raspberry Pi project folder is older than the diagnostics instructions.
Copy/unzip the latest project folder onto the Pi or run the local updater from
an updated checkout, then retry:

  cd ~/rebrewie-control-pi
  BREWIE_HOST=192.168.1.XXX BREWIE_USER=root scripts/run_brewie_bridge_inspect.sh
EOF
  exit 2
fi

if [[ "$BREWIE_HOST" == *'<'* || "$BREWIE_HOST" == *'>'* ]]; then
  cat >&2 <<EOF
Invalid BREWIE_HOST: $BREWIE_HOST
Do not include angle brackets. Use BREWIE_HOST=192.168.1.XXX.
EOF
  exit 2
fi

echo "→ Streaming $HELPER to ${BREWIE_USER}@${BREWIE_HOST} and saving $OUT_FILE"
# shellcheck disable=SC2086 # SSH_OPTS intentionally follows ssh option syntax.
ssh $SSH_OPTS "${BREWIE_USER}@${BREWIE_HOST}" 'sh -s' < "$HELPER" > "$OUT_FILE"
echo "✓ Wrote $OUT_FILE"
