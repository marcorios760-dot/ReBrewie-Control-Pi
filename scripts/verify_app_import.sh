#!/usr/bin/env bash
# Verify that the FastAPI app can be imported and that key routes are registered.
#
# Network-restricted environments can set WHEELHOUSE to a directory populated by:
#   python -m pip download -r requirements.txt -d wheelhouse
# Then run:
#   WHEELHOUSE=/path/to/wheelhouse scripts/verify_app_import.sh
set -euo pipefail

VENV_DIR="${VENV_DIR:-/tmp/rebrewie-venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

rm -rf "$VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

if [[ "${UPGRADE_PIP:-0}" == "1" ]]; then
  if [[ -n "${WHEELHOUSE:-}" ]]; then
    "$VENV_DIR/bin/python" -m pip install \
      --no-index \
      --find-links "$WHEELHOUSE" \
      --upgrade pip \
      --quiet
  else
    "$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet
  fi
fi

if [[ -n "${WHEELHOUSE:-}" ]]; then
  "$VENV_DIR/bin/python" -m pip install \
    --no-index \
    --find-links "$WHEELHOUSE" \
    -r requirements.txt \
    --quiet
else
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt --quiet
fi

"$VENV_DIR/bin/python" - <<'PY'
from app.main import app

paths = {route.path for route in app.routes}
required = {
    "/api/status",
    "/api/recipes",
    "/api/discovery/devices",
    "/api/device/current",
    "/ws",
}
missing = sorted(required - paths)
if missing:
    raise SystemExit(f"Missing expected routes: {missing}")
print(f"app import ok; {len(paths)} routes registered")
PY
