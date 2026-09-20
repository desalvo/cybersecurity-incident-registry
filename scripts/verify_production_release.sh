#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIGEST_FILE="$ROOT_DIR/PRODUCTION_IMAGE_DIGEST"
if [[ ! -s "$DIGEST_FILE" ]]; then
  echo "ERROR: PRODUCTION_IMAGE_DIGEST is missing or empty" >&2
  exit 1
fi
IMAGE="$(tr -d "[:space:]" < "$DIGEST_FILE")"
if [[ "$IMAGE" == PENDING_* ]]; then
  echo "ERROR: hotfix image has not been rebuilt/pinned yet: $IMAGE" >&2
  exit 1
fi
python3 "$ROOT_DIR/scripts/verify_release_candidate.py" --require-production-digest "$IMAGE"
echo "Production release metadata verification: PASS"
echo "Image: $IMAGE"
