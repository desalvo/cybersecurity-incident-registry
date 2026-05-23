#!/usr/bin/env bash
# Manual AGID compliance runner without pip-audit. Use run_docker_agid_compliance.sh for the complete Internet-connected run including pip-audit.
# Execute from any directory inside the extracted project package.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

export AGID_RUN_ID="${AGID_RUN_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}"

if [[ ! -x scripts/run_agid_compliance.sh ]]; then
  chmod +x scripts/run_agid_compliance.sh
fi

if [[ "${AGID_CREATE_VENV:-1}" == "1" ]]; then
  VENV_DIR="${AGID_VENV_DIR:-.venv-agid}"
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install -r requirements-dev.txt
fi

./scripts/run_agid_compliance.sh

cat <<MSG

AGID local compliance run completed without pip-audit. For complete AGID evidence, run ./compliance/agid/run_docker_agid_compliance.sh on an Internet-connected Docker host.
Results directory: compliance/agid/${AGID_RUN_ID}/
Open compliance/agid/${AGID_RUN_ID}/SUMMARY.md for the human-readable report.
MSG
