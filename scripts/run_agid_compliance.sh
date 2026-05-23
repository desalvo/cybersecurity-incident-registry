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

run_step pip_check python -m pip check || OVERALL=1
run_step compileall python -m compileall -q app tests || OVERALL=1
run_step pytest_all python -m pytest -q || OVERALL=1
run_step pytest_agid_dynamic python -m pytest -q tests/test_agid_compliance_dynamic.py || OVERALL=1
run_step bandit_json scripts/run_bandit_json.sh "$OUT_DIR/bandit.json" || true
if ! python scripts/check_bandit_threshold.py "$OUT_DIR/bandit.json" >"$OUT_DIR/bandit_threshold.log" 2>&1; then
  printf '%s\t%s\n' "bandit_threshold_high_medium" "1" >> "$OUT_DIR/status.tsv"
  OVERALL=1
else
  printf '%s\t%s\n' "bandit_threshold_high_medium" "0" >> "$OUT_DIR/status.tsv"
fi

run_step pip_audit_module_check python -m pip_audit --version || OVERALL=1
if ! run_step pip_audit_json python -m pip_audit --progress-spinner off --timeout "${AGID_PIP_AUDIT_SOCKET_TIMEOUT:-10}" -r requirements.txt -r requirements-dev.txt -f json -o "$OUT_DIR/pip-audit.json"; then
  echo "pip-audit failed, found vulnerabilities, or could not reach the vulnerability service. The AGID compliance run is not release-ready until pip-audit passes." > "$OUT_DIR/pip-audit-note.txt"
  OVERALL=1
fi
python scripts/summarize_agid_results.py "$OUT_DIR" "$OVERALL"
exit "$OVERALL"
