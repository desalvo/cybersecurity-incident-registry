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

: > "$OUT_DIR/status.tsv"
OVERALL=0

run_step pip_check timeout 120 python -m pip check || OVERALL=1
run_step compileall timeout 120 python -m compileall -q app tests || OVERALL=1
run_step pytest_all timeout 180 python -m pytest -q || OVERALL=1
run_step pytest_agid_dynamic timeout 180 python -m pytest -q tests/test_agid_compliance_dynamic.py || OVERALL=1
run_step bandit_json timeout 120 python -m bandit -r app -x '*/__pycache__/*' -f json --exit-zero -o "$OUT_DIR/bandit.json" || true
if ! python scripts/check_bandit_threshold.py "$OUT_DIR/bandit.json" >"$OUT_DIR/bandit_threshold.log" 2>&1; then
  printf '%s\t%s\n' "bandit_threshold_high_medium" "1" >> "$OUT_DIR/status.tsv"
  OVERALL=1
else
  printf '%s\t%s\n' "bandit_threshold_high_medium" "0" >> "$OUT_DIR/status.tsv"
fi

PIP_AUDIT_STRICT="${AGID_PIP_AUDIT_STRICT:-1}"
PIP_AUDIT_TIMEOUT="${AGID_PIP_AUDIT_TIMEOUT:-300}"
if [[ "${AGID_SKIP_PIP_AUDIT:-0}" == "1" ]]; then
  echo "pip-audit skipped by explicit AGID_SKIP_PIP_AUDIT=1; this run is not complete for Internet-connected CI." > "$OUT_DIR/pip-audit-note.txt"
  printf '%s\t%s\n' "pip_audit_explicitly_skipped" "1" >> "$OUT_DIR/status.tsv"
  [[ "$PIP_AUDIT_STRICT" == "1" ]] && OVERALL=1
elif python - <<'PY_CHECK' >/dev/null 2>&1
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec('pip_audit') else 1)
PY_CHECK
then
  if ! run_step pip_audit_json timeout "$PIP_AUDIT_TIMEOUT" python -m pip_audit --progress-spinner off --timeout "${AGID_PIP_AUDIT_SOCKET_TIMEOUT:-10}" -r requirements.txt -r requirements-dev.txt -f json -o "$OUT_DIR/pip-audit.json"; then
    echo "pip-audit failed, found vulnerabilities, or could not reach the vulnerability service." > "$OUT_DIR/pip-audit-note.txt"
    [[ "$PIP_AUDIT_STRICT" == "1" ]] && OVERALL=1
  fi
else
  echo "pip-audit is not installed; install pip-audit or use the Docker AGID runner." > "$OUT_DIR/pip-audit-note.txt"
  printf '%s\t%s\n' "pip_audit_missing" "1" >> "$OUT_DIR/status.tsv"
  [[ "$PIP_AUDIT_STRICT" == "1" ]] && OVERALL=1
fi

python scripts/summarize_agid_results.py "$OUT_DIR" "$OVERALL"
exit "$OVERALL"
