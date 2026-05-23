#!/usr/bin/env bash
# Build and run the manual Docker-based AGID compliance suite.
# Usage from project root:
#   ./compliance/agid/run_docker_agid_compliance.sh
# Optional:
#   AGID_RUN_ID=manual-YYYYMMDD ./compliance/agid/run_docker_agid_compliance.sh
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
IMAGE_NAME="${AGID_DOCKER_IMAGE:-cir-agid-compliance:manual}"
RUN_ID="${AGID_RUN_ID:-manual-docker-$(date -u +%Y%m%dT%H%M%SZ)}"

cd "$ROOT_DIR"

# Keep only the latest AGID evidence directory. Static runner/docs files remain.
find compliance/agid -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +

docker build ${AGID_DOCKER_BUILD_FLAGS:---pull} -f compliance/agid/Dockerfile -t "$IMAGE_NAME" .
docker run --rm \
  -e AGID_RUN_ID="$RUN_ID" \
  -e AGID_PIP_AUDIT_TIMEOUT="${AGID_PIP_AUDIT_TIMEOUT:-300}" \
  -e AGID_PIP_AUDIT_SOCKET_TIMEOUT="${AGID_PIP_AUDIT_SOCKET_TIMEOUT:-10}" \
  -v "$ROOT_DIR/compliance/agid:/results" \
  "$IMAGE_NAME"

cat <<MSG

AGID manual Docker compliance run completed.
Results directory: compliance/agid/${RUN_ID}/
Open compliance/agid/${RUN_ID}/SUMMARY.md for the human-readable report.
MSG
