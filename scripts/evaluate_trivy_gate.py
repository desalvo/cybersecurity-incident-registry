#!/usr/bin/env python3
"""Evaluate a Trivy JSON image scan against CIR's time-bounded residual-risk policy."""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import sys

HIGH_SEVERITIES = {"HIGH", "CRITICAL"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_vulns(report):
    for result in report.get("Results") or []:
        target = str(result.get("Target") or "")
        klass = str(result.get("Class") or "")
        typ = str(result.get("Type") or "")
        for vuln in result.get("Vulnerabilities") or []:
            yield target, klass, typ, vuln


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("report", type=Path)
    p.add_argument("--policy", type=Path, default=Path(__file__).resolve().parents[1] / "TRIVY_RISK_ACCEPTANCE_R8.json")
    p.add_argument("--platform", default="unknown")
    args = p.parse_args()

    policy = load(args.policy)
    report = load(args.report)
    allowed = policy["accepted_residual_vulnerabilities"]
    errors = []
    accepted = []

    valid_until = date.fromisoformat(policy["valid_until"])
    if date.today() > valid_until:
        errors.append(f"risk acceptance expired on {valid_until.isoformat()}")

    for target, klass, typ, vuln in iter_vulns(report):
        severity = str(vuln.get("Severity") or "").upper()
        if severity not in HIGH_SEVERITIES:
            continue
        vid = str(vuln.get("VulnerabilityID") or "")
        pkg = str(vuln.get("PkgName") or "")
        fixed = str(vuln.get("FixedVersion") or "").strip()
        is_python = typ == "python-pkg" or "python" in typ.lower() or "python" in target.lower()

        if is_python:
            errors.append(f"{args.platform}: Python {severity} finding is not allowed: {vid} in {pkg}")
            continue
        if fixed:
            errors.append(f"{args.platform}: {vid} in {pkg} is patchable (FixedVersion={fixed}); rebuild/update instead of accepting it")
            continue
        if vid not in allowed:
            errors.append(f"{args.platform}: new/unreviewed OS {severity} finding: {vid} in {pkg}")
            continue
        accepted.append((vid, pkg, severity))

    if errors:
        print(f"Trivy production gate: FAIL ({args.platform})", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        return 1

    unique = sorted({vid for vid, _, _ in accepted})
    print(f"Trivy production gate: PASS ({args.platform})")
    print(f"Accepted temporary residual OS CVEs present: {len(unique)}")
    print(f"Risk acceptance valid until: {valid_until.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
