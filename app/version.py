"""Central application release metadata."""
from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

def _read_metadata_file(name: str, fallback: str) -> str:
    try:
        value = (_PROJECT_ROOT / name).read_text(encoding="utf-8").strip()
    except OSError:
        return fallback
    return value or fallback

DEFAULT_RELEASE_VERSION = _read_metadata_file("VERSION", "0.0.0")
DEFAULT_RELEASE_BUILD = _read_metadata_file("BUILD", "unknown")
APP_RELEASE_VERSION = os.getenv("APP_VERSION", DEFAULT_RELEASE_VERSION).strip() or DEFAULT_RELEASE_VERSION
APP_RELEASE_BUILD = os.getenv("APP_BUILD", DEFAULT_RELEASE_BUILD).strip() or DEFAULT_RELEASE_BUILD
