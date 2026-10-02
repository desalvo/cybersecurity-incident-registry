#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STAMP="${AGID_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
BASE_RESULTS_DIR="$ROOT_DIR/compliance/agid"
OUT_DIR="${AGID_RESULTS_DIR:-$BASE_RESULTS_DIR/$STAMP}"

# Keep only the latest AGID compliance evidence in release packages.
# Set AGID_KEEP_PREVIOUS_RESULTS=1 only for local comparisons/debugging.
if [[ "${AGID_KEEP_PREVIOUS_RESULTS:-0}" != "1" && -z "${AGID_RESULTS_DIR:-}" ]]; then
  mkdir -p "$BASE_RESULTS_DIR"
  find "$BASE_RESULTS_DIR" -mindepth 1 -maxdepth 1 -type d ! -name "$STAMP" -exec rm -rf {} +
fi
mkdir -p "$OUT_DIR"

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

: > "$OUT_DIR/status.tsv"
OVERALL=0


prepare_python() {
  if [[ -n "${AGID_PYTHON:-}" ]]; then
    PYTHON_BIN="$AGID_PYTHON"
    return
  fi
  if [[ "${AGID_USE_CURRENT_ENV:-0}" == "1" ]]; then
    PYTHON_BIN="$(command -v python3 || command -v python)"
    return
  fi
  local venv_dir="${AGID_VENV_DIR:-$ROOT_DIR/.venv-agid}"
  if [[ ! -x "$venv_dir/bin/python" ]]; then
    "$(command -v python3 || command -v python)" -m venv "$venv_dir"
    "$venv_dir/bin/python" -m pip install --upgrade pip setuptools wheel
    "$venv_dir/bin/python" -m pip install -r requirements-dev.txt
  fi
  PYTHON_BIN="$venv_dir/bin/python"
}

prepare_python
export PYTHON_BIN
run_step pip_check timeout 120 "$PYTHON_BIN" -m pip check || OVERALL=1
run_step compileall timeout 120 "$PYTHON_BIN" -m compileall -q app tests || OVERALL=1
run_pytest_step pytest_all timeout "${AGID_PYTEST_TIMEOUT:-900}" bash scripts/run_pytest_offline_safe.sh || OVERALL=1
run_pytest_step pytest_agid_dynamic timeout "${AGID_PYTEST_DYNAMIC_TIMEOUT:-300}" "$PYTHON_BIN" -m pytest -q tests/test_agid_compliance_dynamic.py || OVERALL=1
run_step bandit_json timeout 120 "$PYTHON_BIN" -m bandit -r app -x '*/__pycache__/*' -f json --exit-zero -o "$OUT_DIR/bandit.json" || true
if ! "$PYTHON_BIN" scripts/check_bandit_threshold.py "$OUT_DIR/bandit.json" >"$OUT_DIR/bandit_threshold.log" 2>&1; then
  printf '%s\t%s\n' "bandit_threshold_high_medium" "1" >> "$OUT_DIR/status.tsv"
  OVERALL=1
else
  printf '%s\t%s\n' "bandit_threshold_high_medium" "0" >> "$OUT_DIR/status.tsv"
fi

if [[ "${AGID_OFFLINE:-0}" == "1" ]]; then
  export AGID_SKIP_PIP_AUDIT=1
  : "${AGID_PIP_AUDIT_STRICT:=0}"
fi
PIP_AUDIT_STRICT="${AGID_PIP_AUDIT_STRICT:-1}"
PIP_AUDIT_TIMEOUT="${AGID_PIP_AUDIT_TIMEOUT:-300}"
if [[ "${AGID_SKIP_PIP_AUDIT:-0}" == "1" ]]; then
  echo "pip-audit skipped by explicit AGID_SKIP_PIP_AUDIT=1; this run is not complete for Internet-connected CI." > "$OUT_DIR/pip-audit-note.txt"
  printf '%s\t%s\n' "pip_audit_explicitly_skipped" "${PIP_AUDIT_STRICT}" >> "$OUT_DIR/status.tsv"
  [[ "$PIP_AUDIT_STRICT" == "1" ]] && OVERALL=1
elif "$PYTHON_BIN" - <<'PY_CHECK' >/dev/null 2>&1
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec('pip_audit') else 1)
PY_CHECK
then
  if ! run_step pip_audit_json timeout "$PIP_AUDIT_TIMEOUT" "$PYTHON_BIN" -m pip_audit --progress-spinner off --timeout "${AGID_PIP_AUDIT_SOCKET_TIMEOUT:-10}" -r requirements.txt -r requirements-dev.txt -f json -o "$OUT_DIR/pip-audit.json"; then
    echo "pip-audit failed, found vulnerabilities, or could not reach the vulnerability service." > "$OUT_DIR/pip-audit-note.txt"
    [[ "$PIP_AUDIT_STRICT" == "1" ]] && OVERALL=1
  fi
else
  echo "pip-audit is not installed; install pip-audit or use the Docker AGID runner." > "$OUT_DIR/pip-audit-note.txt"
  printf '%s\t%s\n' "pip_audit_missing" "1" >> "$OUT_DIR/status.tsv"
  [[ "$PIP_AUDIT_STRICT" == "1" ]] && OVERALL=1
fi

"$PYTHON_BIN" scripts/summarize_agid_results.py "$OUT_DIR" "$OVERALL"
exit "$OVERALL"
