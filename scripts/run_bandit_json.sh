#!/usr/bin/env bash
set -Eeuo pipefail
OUT_FILE="${1:?Usage: scripts/run_bandit_json.sh OUT_FILE}"
find app -type f -name '*.py' -not -path '*/__pycache__/*' -print0 \
  | xargs -0 python -m bandit -f json --exit-zero -o "$OUT_FILE"
