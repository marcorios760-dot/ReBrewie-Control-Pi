#!/usr/bin/env bash
# Convenience wrapper for updating an existing local Raspberry Pi installation.
# Prefer this when you are already SSH'd into the Pi and have copied/unzipped the
# updated project directory there.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_UPDATER="$SCRIPT_DIR/scripts/update_local_pi.sh"

if [[ ! -f "$LOCAL_UPDATER" ]]; then
  cat >&2 <<EOF
Could not find scripts/update_local_pi.sh next to this wrapper.

This usually means you are running an older project copy that does not include
new deployment helpers yet. Copy or unzip the latest project folder onto the Pi,
then run:

  cd ~/rebrewie-control-pi
  sudo ./update.sh

If this is the first install, run:

  sudo ./install.sh
EOF
  exit 2
fi

exec bash "$LOCAL_UPDATER" "$@"
