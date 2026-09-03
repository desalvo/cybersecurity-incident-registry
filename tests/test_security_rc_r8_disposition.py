from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_r8_policy_is_time_bounded_and_fail_closed():
    p = json.loads((ROOT / "TRIVY_RISK_ACCEPTANCE_R8.json").read_text())
    assert p["release"] == "0.9.0-1"
    assert p["valid_until"] == "2026-10-03"
    assert p["policy"]["python_high_critical_allowed"] is False
    assert p["policy"]["new_os_high_critical_allowed"] is False
    assert p["policy"]["fixed_version_available_allowed"] is False
    assert "CVE-2026-58016" in p["accepted_residual_vulnerabilities"]
    assert "CVE-2026-52490" in p["accepted_residual_vulnerabilities"]


def _run(report, tmp_path):
    f = tmp_path / "report.json"
    f.write_text(json.dumps(report))
    return subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_trivy_gate.py"), str(f), "--platform", "linux/amd64"], text=True, capture_output=True)


def test_r8_gate_rejects_python_high(tmp_path):
    report={"Results":[{"Target":"Python","Type":"python-pkg","Vulnerabilities":[{"VulnerabilityID":"CVE-X","PkgName":"x","Severity":"HIGH","FixedVersion":""}]}]}
    r=_run(report,tmp_path)
    assert r.returncode == 1
    assert "Python HIGH finding is not allowed" in r.stderr


def test_r8_gate_rejects_new_os_high(tmp_path):
    report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[{"VulnerabilityID":"CVE-2099-9999","PkgName":"x","Severity":"HIGH","FixedVersion":""}]}]}
    r=_run(report,tmp_path)
    assert r.returncode == 1
    assert "new/unreviewed" in r.stderr


def test_r8_gate_rejects_now_patchable_accepted_cve(tmp_path):
    report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[{"VulnerabilityID":"CVE-2026-58016","PkgName":"libglib2.0-0t64","Severity":"CRITICAL","FixedVersion":"9.9"}]}]}
    r=_run(report,tmp_path)
    assert r.returncode == 1
    assert "patchable" in r.stderr


def test_r8_gate_accepts_reviewed_unfixed_os_cve(tmp_path):
    report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[{"VulnerabilityID":"CVE-2026-58016","PkgName":"libglib2.0-0t64","Severity":"CRITICAL","FixedVersion":""}]}]}
    r=_run(report,tmp_path)
    assert r.returncode == 0
    assert "PASS" in r.stdout
