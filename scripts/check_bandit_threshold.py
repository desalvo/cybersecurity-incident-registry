#!/usr/bin/env python3
"""Fail only when Bandit reports HIGH or MEDIUM severity findings."""
from __future__ import annotations
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
metrics = data.get("metrics", {}).get("_totals", {})
high = int(metrics.get("SEVERITY.HIGH", 0))
medium = int(metrics.get("SEVERITY.MEDIUM", 0))
low = int(metrics.get("SEVERITY.LOW", 0))
print(f"Bandit severity counts: HIGH={high}, MEDIUM={medium}, LOW={low}")
if high or medium:
    raise SystemExit(1)
