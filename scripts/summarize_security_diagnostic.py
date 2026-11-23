#!/usr/bin/env python3
"""Summarize a non-publishing Trivy diagnostic and available Debian evidence."""
import argparse
import json
from pathlib import Path


def summarize(evidence: Path):
    reports = sorted(evidence.glob("linux-*.json"))
    result = {"schema": 1, "reports": [], "debian_evidence": {}, "limitations": [
        "No FixedVersion in Trivy is not evidence that a fix is unavailable.",
        "apt-cache Candidate is a repository candidate, not proof that a CVE is fixed.",
        "Installed reverse dependencies do not prove vulnerable code is unreachable.",
        "No vulnerability is automatically accepted or suppressed.",
    ]}
    for path in reports:
        data = json.loads(path.read_text(encoding="utf-8"))
        findings = [v for section in data.get("Results", [])
                    for v in section.get("Vulnerabilities", []) or []
                    if v.get("Severity") in ("HIGH", "CRITICAL")]
        result["reports"].append({"file": path.name, "high": sum(v.get("Severity") == "HIGH" for v in findings),
                                  "critical": sum(v.get("Severity") == "CRITICAL" for v in findings),
                                  "unique_cves": len({v.get("VulnerabilityID") for v in findings}),
                                  "fixed_version_reported": sum(bool(v.get("FixedVersion")) for v in findings),
                                  "packages": sorted({v.get("PkgName", "") for v in findings})})
    for name in ("debian-installed.tsv", "debian-policy.txt", "debian-priority-packages.txt", "debian-apt-update.log"):
        p = evidence / name
        result["debian_evidence"][name] = {"present": p.is_file(), "bytes": p.stat().st_size if p.is_file() else 0}
    required = ("debian-installed.tsv", "debian-policy.txt", "debian-priority-packages.txt", "debian-apt-update.log")
    result["debian_evidence_complete"] = all(result["debian_evidence"][name]["present"] and result["debian_evidence"][name]["bytes"] > 0 for name in required)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(summarize(args.evidence_dir), indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
