#!/usr/bin/env bash
# Network-enabled SCA gate for CI/release builds.
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT="${CIR_SCA_OUTPUT:-SCA_PIP_AUDIT.json}"

if ! "$PYTHON_BIN" -c 'import pip_audit' >/dev/null 2>&1; then
  cat >&2 <<'EOF'
pip-audit is required for the network-enabled SCA gate.
Install it in the CI/release tooling environment (not the CIR runtime image), then rerun:
  python -m pip install pip-audit
The application runtime requirements are intentionally not changed by this helper.
EOF
  exit 2
fi

"$PYTHON_BIN" -m pip_audit \
  -r requirements.txt \
  --format json \
  --output "$OUTPUT" \
  --progress-spinner off

echo "SCA report written to $OUTPUT"
