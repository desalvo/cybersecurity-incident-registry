#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${1:-${CIR_PRODUCTION_IMAGE:-}}"
PLATFORMS="${CIR_TRIVY_PLATFORMS:-linux/amd64,linux/arm64}"
POLICY="${CIR_TRIVY_POLICY:-$ROOT_DIR/TRIVY_RISK_ACCEPTANCE_R8.json}"
OUT_DIR="${CIR_TRIVY_OUTPUT_DIR:-$ROOT_DIR/generated/trivy-r8}"

if [[ -z "$IMAGE" ]]; then
  echo "Usage: $(basename "$0") IMAGE" >&2
  echo "or set CIR_PRODUCTION_IMAGE." >&2
  exit 2
fi
command -v trivy >/dev/null 2>&1 || { echo "ERROR: trivy not found in PATH" >&2; exit 1; }
[[ -f "$POLICY" ]] || { echo "ERROR: policy not found: $POLICY" >&2; exit 1; }
mkdir -p "$OUT_DIR"
python3 "$ROOT_DIR/scripts/verify_security_gate_context.py"

# Collect both architecture reports even if the first policy evaluation fails.
# Never promote unless every scan and every policy evaluation succeeds.
IFS=',' read -r -a platform_array <<< "$PLATFORMS"
failures=0
for platform in "${platform_array[@]}"; do
  safe="${platform//\//-}"
  report="$OUT_DIR/${safe}.json"
  echo "Scanning $IMAGE for $platform"
  if ! trivy image --scanners vuln --severity HIGH,CRITICAL --format json --platform "$platform" --output "$report" "$IMAGE"; then
    echo "ERROR: Trivy scan failed for $platform" >&2
    failures=$((failures + 1))
    continue
  fi
  if ! python3 "$ROOT_DIR/scripts/evaluate_trivy_gate.py" "$report" --policy "$POLICY" --platform "$platform"; then
    echo "ERROR: Trivy policy rejected $platform" >&2
    failures=$((failures + 1))
  fi
done
if (( failures > 0 )); then
  echo "ERROR: production gate rejected $failures architecture scan(s); no promotion authorized" >&2
  exit 1
fi
echo "Trivy production gate completed for: $PLATFORMS"
