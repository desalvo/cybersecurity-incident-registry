#!/usr/bin/env python3
"""Compatibility wrapper for the Docker/offline pytest shell runner."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_pytest_offline_safe.sh"

if __name__ == "__main__":
    os.execvp("bash", ["bash", str(SCRIPT), *sys.argv[1:]])
