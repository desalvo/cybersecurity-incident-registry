#!/usr/bin/env python3
"""Evaluate a Trivy JSON image scan against CIR's time-bounded residual-risk policy."""
from __future__ import annotations
import argparse
from datetime import date
import json
import re
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

    try:
        policy = load(args.policy)
        report = load(args.report)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Trivy production gate: FAIL ({args.platform})", file=sys.stderr)
        print(f"- unable to load gate input: {exc}", file=sys.stderr)
        return 1

    errors = []
    accepted = []
    rules = policy.get("policy") or {}
    for key in ("python_high_critical_allowed", "new_os_high_critical_allowed", "fixed_version_available_allowed"):
        if rules.get(key) is not False:
            errors.append(f"policy must explicitly keep {key}=false")
    if rules.get("require_exact_allowlist_for_residual_os") is not True:
        errors.append("policy must require an exact residual-OS allowlist")
    if rules.get("enforce_package_scope_when_declared") is not True:
        errors.append("policy must enforce declared package scope")
    if rules.get("require_runtime_hardening_verification") is not True:
        errors.append("policy must require runtime hardening verification")

    allowed = policy.get("accepted_residual_vulnerabilities")
    if not isinstance(allowed, dict) or not allowed:
        errors.append("accepted_residual_vulnerabilities must be a non-empty object")
        allowed = {}

    try:
        valid_until = date.fromisoformat(str(policy.get("valid_until") or ""))
    except ValueError:
        errors.append("policy valid_until is missing or invalid")
        valid_until = date.min
    if date.today() > valid_until:
        errors.append(f"risk acceptance expired on {valid_until.isoformat()}")

    results = report.get("Results")
    if not isinstance(results, list) or not results:
        errors.append("Trivy report has no Results; refusing fail-open PASS")

    for target, klass, typ, vuln in iter_vulns(report):
        severity = str(vuln.get("Severity") or "").upper()
        if severity not in HIGH_SEVERITIES:
            continue
        vid = str(vuln.get("VulnerabilityID") or "").strip()
        pkg = str(vuln.get("PkgName") or "").strip()
        fixed = str(vuln.get("FixedVersion") or "").strip()
        if not vid or not pkg:
            errors.append(f"{args.platform}: malformed HIGH/CRITICAL finding without CVE/package identity")
            continue
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
        rule = allowed[vid]
        package_scope = rule.get("packages") or []
        if package_scope and pkg not in package_scope:
            errors.append(
                f"{args.platform}: {vid} appeared in unexpected package {pkg}; "
                f"accepted package scope is {','.join(package_scope)}"
            )
            continue
        version_pattern = str(rule.get("installed_version_regex") or "").strip()
        installed = str(vuln.get("InstalledVersion") or "").strip()
        if version_pattern and not re.fullmatch(version_pattern, installed):
            errors.append(
                f"{args.platform}: {vid} in {pkg} has unreviewed installed version {installed!r}; "
                f"expected /{version_pattern}/"
            )
            continue
        review_before = str(rule.get("review_before") or "").strip()
        if review_before and date.today() > date.fromisoformat(review_before):
            errors.append(f"{args.platform}: per-CVE review expired for {vid} on {review_before}")
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
