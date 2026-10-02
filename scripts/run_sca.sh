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

set +e
"$PYTHON_BIN" -m pip_audit \
  -r requirements.txt \
  --format json \
  --output "$OUTPUT" \
  --progress-spinner off
audit_rc=$?
set -e

if [[ -f "$OUTPUT" ]]; then
  echo "SCA report written to $OUTPUT"
fi

if (( audit_rc != 0 )); then
  echo "SCA gate: FAIL" >&2
  if [[ -f "$OUTPUT" ]]; then
    "$PYTHON_BIN" - "$OUTPUT" >&2 <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    report = json.load(handle)

found = False
for dep in report.get("dependencies", []):
    vulns = dep.get("vulns") or []
    if not vulns:
        continue
    found = True
    for vuln in vulns:
        fixes = ", ".join(vuln.get("fix_versions") or []) or "<none>"
        print(f"- {dep.get('name','?')} {dep.get('version','?')}: {vuln.get('id','?')}; fix versions: {fixes}")
if not found:
    print("- pip-audit returned non-zero but no vulnerability entries were found in the JSON report.")
PY
  fi
  exit "$audit_rc"
fi

echo "SCA gate: PASS"
