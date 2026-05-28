#!/usr/bin/env bash
# Execute the full AGID compliance suite from inside the container.
# Results are written under /results/<RUN_ID> when /results is mounted.
set -Eeuo pipefail

PROJECT_DIR="${AGID_PROJECT_DIR:-/project}"
if [[ ! -f "$PROJECT_DIR/requirements.txt" || ! -x "$PROJECT_DIR/scripts/run_agid_compliance.sh" ]]; then
  PROJECT_DIR="/opt/project"
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Project directory not found: $PROJECT_DIR" >&2
  exit 2
fi

RUN_ID="${AGID_RUN_ID:-docker-$(date -u +%Y%m%dT%H%M%SZ)}"
RESULTS_ROOT="${AGID_RESULTS_ROOT:-/results}"
if [[ -d "$RESULTS_ROOT" && -w "$RESULTS_ROOT" ]]; then
  export AGID_RESULTS_DIR="$RESULTS_ROOT/$RUN_ID"
else
  export AGID_RESULTS_DIR="$PROJECT_DIR/compliance/agid/$RUN_ID"
fi
export AGID_RUN_ID="$RUN_ID"
export AGID_PIP_AUDIT_STRICT="${AGID_PIP_AUDIT_STRICT:-1}"
export AGID_SKIP_PIP_AUDIT="${AGID_SKIP_PIP_AUDIT:-0}"
export AGID_USE_LOCAL_DNS="${AGID_USE_LOCAL_DNS:-0}"
export AGID_CREATE_VENV=0

mkdir -p "$AGID_RESULTS_DIR"
cd "$PROJECT_DIR"
chmod +x scripts/run_agid_compliance.sh scripts/*.sh compliance/agid/*.sh 2>/dev/null || true

python -m pip check >"$AGID_RESULTS_DIR/container_pip_check.log" 2>&1 || true
./scripts/run_agid_compliance.sh
RC=$?

cat >"$AGID_RESULTS_DIR/CONTAINER_RUN.md" <<MSG
# AGID compliance container run

- Run ID: $RUN_ID
- Project directory: $PROJECT_DIR
- Results directory: $AGID_RESULTS_DIR
- Exit code: $RC
- pip-audit strict: ${AGID_PIP_AUDIT_STRICT}
- pip-audit skipped: ${AGID_SKIP_PIP_AUDIT}

The main report is SUMMARY.md in this directory.
MSG

exit "$RC"
