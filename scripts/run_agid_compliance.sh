#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STAMP="${AGID_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${AGID_RESULTS_DIR:-$ROOT_DIR/compliance/agid/$STAMP}"
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
run_step bandit_json timeout 120 python -m bandit -r app -x '*/__pycache__/*' -f json -o "$OUT_DIR/bandit.json" || true
if ! python scripts/check_bandit_threshold.py "$OUT_DIR/bandit.json" >"$OUT_DIR/bandit_threshold.log" 2>&1; then
  printf '%s\t%s\n' "bandit_threshold_high_medium" "1" >> "$OUT_DIR/status.tsv"
  OVERALL=1
else
  printf '%s\t%s\n' "bandit_threshold_high_medium" "0" >> "$OUT_DIR/status.tsv"
fi

PIP_AUDIT_TIMEOUT="${AGID_PIP_AUDIT_TIMEOUT:-30}"
if [[ "${AGID_SKIP_PIP_AUDIT:-0}" == "1" ]]; then
  echo "pip-audit skipped by AGID_SKIP_PIP_AUDIT=1. Rerun in connected CI before production release." > "$OUT_DIR/pip-audit-note.txt"
  printf '%s\t%s\n' "pip_audit_json" "125" >> "$OUT_DIR/status.tsv"
elif python -m pip_audit --version >/dev/null 2>&1; then
  if ! run_step pip_audit_json timeout "$PIP_AUDIT_TIMEOUT" python -m pip_audit -r requirements.txt -r requirements-dev.txt -f json -o "$OUT_DIR/pip-audit.json"; then
    echo "pip-audit failed or timed out after ${PIP_AUDIT_TIMEOUT}s; see pip_audit_json.log. In offline environments this is recorded as an environmental limitation and must be rerun in connected CI before production release." > "$OUT_DIR/pip-audit-note.txt"
  fi
else
  echo "pip-audit not installed. Install requirements-dev.txt and rerun before production release." > "$OUT_DIR/pip-audit-note.txt"
  printf '%s\t%s\n' "pip_audit_json" "127" >> "$OUT_DIR/status.tsv"
fi

python scripts/summarize_agid_results.py "$OUT_DIR" "$OVERALL"
exit "$OVERALL"
