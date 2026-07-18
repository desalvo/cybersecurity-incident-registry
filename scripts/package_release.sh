#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
OUT="${1:-$ROOT_DIR/../cybersecurity-incident-registry-${VERSION}.zip}"
BASE="cybersecurity-incident-registry-${VERSION}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
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
echo "$OUT"
