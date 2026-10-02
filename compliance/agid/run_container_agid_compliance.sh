#!/usr/bin/env bash
# Container entrypoint for a complete manual AGID compliance run.
# It executes all standard AGID tests plus Bandit and pip-audit, and writes
# the evidence to /results/<RUN_ID>/ by default.
set -Eeuo pipefail

ROOT_DIR="${AGID_PROJECT_DIR:-/project}"
PYTHON_BIN="${AGID_PYTHON:-/opt/agid-venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi
RESULTS_BASE="${AGID_RESULTS_BASE:-/results}"
RUN_ID="${AGID_RUN_ID:-manual-docker-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${AGID_RESULTS_DIR:-$RESULTS_BASE/$RUN_ID}"

cd "$ROOT_DIR"
mkdir -p "$OUT_DIR"
: > "$OUT_DIR/status.tsv"
OVERALL=0

run_step() {
  local name="$1"
  shift
  echo "==> $name"
  set +e
  "$@" >"$OUT_DIR/${name}.log" 2>&1
  local rc=$?
  set -e
  printf '%s\t%s\n' "$name" "$rc" >> "$OUT_DIR/status.tsv"
  return "$rc"
}


run_pytest_step() {
  local name="$1"
  shift
  PYTEST_VERSION="${PYTEST_VERSION:-agid}"   CIR_TEST_PASSWORD_HASH_METHOD="${CIR_TEST_PASSWORD_HASH_METHOD:-pbkdf2:sha256:1}"   PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-1}"   CIR_FORCE_PYTEST_PROCESS_EXIT="${CIR_FORCE_PYTEST_PROCESS_EXIT:-1}"   run_step "$name" "$@"
}

run_step pip_check timeout 120 "$PYTHON_BIN" -m pip check || OVERALL=1
run_step compileall timeout 120 "$PYTHON_BIN" -m compileall -q app tests || OVERALL=1
run_pytest_step pytest_all timeout "${AGID_PYTEST_TIMEOUT:-900}" bash scripts/run_pytest_offline_safe.sh || OVERALL=1
run_pytest_step pytest_agid_dynamic timeout "${AGID_PYTEST_DYNAMIC_TIMEOUT:-300}" "$PYTHON_BIN" -m pytest -q tests/test_agid_compliance_dynamic.py || OVERALL=1

run_step bandit_module_check timeout 60 "$PYTHON_BIN" -m bandit --version || OVERALL=1
if [[ "${AGID_OFFLINE:-0}" == "1" || "${AGID_SKIP_PIP_AUDIT:-0}" == "1" ]]; then
  printf '%s	%s
' "pip_audit_module_check_skipped_offline" "0" >> "$OUT_DIR/status.tsv"
else
  run_step pip_audit_module_check timeout 60 "$PYTHON_BIN" -m pip_audit --version || OVERALL=1
fi

run_step bandit_json timeout 180 "$PYTHON_BIN" -m bandit -r app -x '*/__pycache__/*' -f json --exit-zero -o "$OUT_DIR/bandit.json" || true
if ! "$PYTHON_BIN" scripts/check_bandit_threshold.py "$OUT_DIR/bandit.json" >"$OUT_DIR/bandit_threshold.log" 2>&1; then
  printf '%s\t%s\n' "bandit_threshold_high_medium" "1" >> "$OUT_DIR/status.tsv"
  OVERALL=1
else
  printf '%s\t%s\n' "bandit_threshold_high_medium" "0" >> "$OUT_DIR/status.tsv"
fi

if [[ "${AGID_OFFLINE:-0}" == "1" || "${AGID_SKIP_PIP_AUDIT:-0}" == "1" ]]; then
  echo "pip-audit skipped for explicit offline Docker run; rerun with network before production release." > "$OUT_DIR/pip-audit-note.txt"
  printf '%s\t%s\n' "pip_audit_offline_skipped" "0" >> "$OUT_DIR/status.tsv"
elif ! run_step pip_audit_json timeout "${AGID_PIP_AUDIT_TIMEOUT:-300}" "$PYTHON_BIN" -m pip_audit --progress-spinner off --timeout "${AGID_PIP_AUDIT_SOCKET_TIMEOUT:-10}" -r requirements.txt -r requirements-dev.txt -f json -o "$OUT_DIR/pip-audit.json"; then
  echo "pip-audit failed, found vulnerabilities, or could not reach the vulnerability service. This manual Docker run is not fully AGID-compliant until pip-audit passes." > "$OUT_DIR/pip-audit-note.txt"
  [[ "${AGID_PIP_AUDIT_STRICT:-1}" == "1" ]] && OVERALL=1
fi

"$PYTHON_BIN" scripts/summarize_agid_results.py "$OUT_DIR" "$OVERALL"
# Make files easy to edit/delete on bind-mounted directories.
chmod -R a+rwX "$OUT_DIR" || true
exit "$OVERALL"
