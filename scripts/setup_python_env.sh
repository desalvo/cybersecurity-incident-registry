#!/usr/bin/env bash
# Create an isolated Python virtual environment for the application.
# This keeps project pins such as pypdf==6.10.2 isolated from unrelated
# packages that may already be installed in a workstation or CI image.
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
VENV_DIR="${CIR_VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python not found." >&2
  exit 2
fi
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r requirements-dev.txt
"$VENV_DIR/bin/python" -m pip check
cat <<MSG

Virtual environment ready: $VENV_DIR
Activate it with:
  source "$VENV_DIR/bin/activate"

Or run commands directly with:
  "$VENV_DIR/bin/python" -m pytest -q
MSG
