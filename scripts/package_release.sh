#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
OUT="${1:-$ROOT_DIR/../cybersecurity-incident-registry-${VERSION}.zip}"
BASE="cybersecurity-incident-registry-${VERSION}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

REQUIRED_RELEASE_FILES=(
  "RELEASE_NOTES_0.9.0-1.md"
  "RELEASE_NOTES_0.9.0-1_en.md"
  "scripts/build_multiarch_image.sh"
  "MIGRATION_0.8.0_TO_0.9.0.md"
  "MIGRATION_0.8.0_TO_0.9.0_en.md"
  "RC_R7_FINAL_CONTAINER_MINIMIZATION.md"
  "SECURITY_DISPOSITION_R8.md"
  "TRIVY_RISK_ACCEPTANCE_R8.json"
  "scripts/run_trivy_production_gate.sh"
  "scripts/evaluate_trivy_gate.py"
  "PRODUCTION_RELEASE_0.9.0-1.md"
  "PRODUCTION_IMAGE_DIGEST"
  "scripts/verify_production_release.sh"
)
for relative in "${REQUIRED_RELEASE_FILES[@]}"; do
  if [[ ! -f "$ROOT_DIR/$relative" ]]; then
    echo "ERROR: required release file missing: $relative" >&2
    exit 1
  fi
done
mkdir -p "$TMP/$BASE"
rsync -a --delete \
  --exclude='.git/' --exclude='.env' --exclude='.venv/' --exclude='venv/' \
  --exclude='__pycache__/' --exclude='*.py[co]' --exclude='.pytest_cache/' \
  --exclude='.pytest_tmp/' --exclude='instance/*' --exclude='app/uploads/*' \
  --exclude='backups/' --exclude='generated/' --exclude='*.key' --exclude='*.crt' \
  "$ROOT_DIR/" "$TMP/$BASE/"
mkdir -p "$TMP/$BASE/instance" "$TMP/$BASE/app/uploads"
touch "$TMP/$BASE/instance/.gitkeep" "$TMP/$BASE/app/uploads/.gitkeep"
(cd "$TMP" && zip -qr "$OUT" "$BASE")
PACKAGE_LIST="$TMP/package-list.txt"
unzip -Z1 "$OUT" > "$PACKAGE_LIST"
for relative in "${REQUIRED_RELEASE_FILES[@]}"; do
  if ! grep -Fxq "$BASE/$relative" "$PACKAGE_LIST"; then
    echo "ERROR: packaged release is missing: $relative" >&2
    exit 1
  fi
done
CHECKSUM_FILE="${OUT}.sha256"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$(dirname "$OUT")" && sha256sum "$(basename "$OUT")") > "$CHECKSUM_FILE"
else
  python3 - "$OUT" "$CHECKSUM_FILE" <<'PY_CHECKSUM'
from pathlib import Path
import hashlib
import sys
src = Path(sys.argv[1])
out = Path(sys.argv[2])
digest = hashlib.sha256(src.read_bytes()).hexdigest()
out.write_text(f"{digest}  {src.name}\n", encoding="utf-8")
PY_CHECKSUM
fi
echo "$OUT"
echo "$CHECKSUM_FILE"
