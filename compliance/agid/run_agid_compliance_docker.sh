#!/usr/bin/env bash
# Build and run the AGID compliance container from the extracted project root.
# Results are written in the current directory by default.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

IMAGE_NAME="${AGID_DOCKER_IMAGE:-cybersecurity-incident-registry-agid:latest}"
RESULTS_DIR="${AGID_DOCKER_RESULTS_DIR:-$PWD}"
RUN_ID="${AGID_RUN_ID:-docker-$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$RESULTS_DIR"

docker build ${AGID_DOCKER_BUILD_FLAGS:---pull} -f compliance/agid/Dockerfile -t "$IMAGE_NAME" .
docker run --rm \
  -e "AGID_RUN_ID=$RUN_ID" \
  -e "AGID_PIP_AUDIT_STRICT=${AGID_PIP_AUDIT_STRICT:-1}" \
  -e "AGID_SKIP_PIP_AUDIT=${AGID_SKIP_PIP_AUDIT:-0}" \
  -e "AGID_USE_LOCAL_DNS=${AGID_USE_LOCAL_DNS:-0}" \
  -v "$PWD:/project" \
  -v "$RESULTS_DIR:/results" \
  "$IMAGE_NAME"

cat <<MSG

AGID compliance container completed.
Results saved in: $RESULTS_DIR/$RUN_ID
MSG
