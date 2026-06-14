#!/usr/bin/env bash
# Create local artifacts that can be uploaded/applied when direct git push is
# blocked by a corporate proxy or network policy.
set -euo pipefail

BRANCH="${1:-$(git branch --show-current)}"
DEFAULT_BASE="origin/Improved-V1"
if git rev-parse --verify --quiet "$DEFAULT_BASE" >/dev/null; then
  BASE="${BASE:-$DEFAULT_BASE}"
else
  BASE="${BASE:-$(git merge-base "$BRANCH" HEAD~1 2>/dev/null || git rev-list --max-parents=0 "$BRANCH") }"
  BASE="${BASE% }"
fi
OUT_DIR="${OUT_DIR:-/tmp/rebrewie-push-fallback}"

mkdir -p "$OUT_DIR"
git bundle create "$OUT_DIR/${BRANCH}.bundle" "$BRANCH"
git format-patch "$BASE..$BRANCH" --stdout > "$OUT_DIR/${BRANCH}.patch"

cat <<EOF
Created fallback artifacts:
  $OUT_DIR/${BRANCH}.bundle
  $OUT_DIR/${BRANCH}.patch

On a machine with GitHub access, either run:
  git clone $OUT_DIR/${BRANCH}.bundle ReBrewie-Control-Pi-Private-${BRANCH}
  cd ReBrewie-Control-Pi-Private-${BRANCH}
  git push origin ${BRANCH}:${BRANCH}

Or apply the patch to a checkout:
  git checkout -b ${BRANCH} ${BASE}
  git am $OUT_DIR/${BRANCH}.patch
  git push origin ${BRANCH}:${BRANCH}
EOF
