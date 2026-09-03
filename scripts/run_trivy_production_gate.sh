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

IFS=',' read -r -a platform_array <<< "$PLATFORMS"
for platform in "${platform_array[@]}"; do
  safe="${platform//\//-}"
  report="$OUT_DIR/${safe}.json"
  echo "Scanning $IMAGE for $platform"
  trivy image --scanners vuln --severity HIGH,CRITICAL --format json --platform "$platform" --output "$report" "$IMAGE"
  python3 "$ROOT_DIR/scripts/evaluate_trivy_gate.py" "$report" --policy "$POLICY" --platform "$platform"
done

echo "Trivy production gate completed for: $PLATFORMS"
