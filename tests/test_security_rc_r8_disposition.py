from pathlib import Path
import json
import subprocess
import sys
import contextlib
from datetime import date
import importlib.util
import io
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def test_r8_policy_is_time_bounded_and_fail_closed():
    p = json.loads((ROOT / "tests/fixtures/historical_r8_risk_policy.json").read_text())
    assert p["release"] == (ROOT / "VERSION").read_text().strip()
    assert p["release_status"] == "review_required"
    assert p["reviewed_baseline"]["release"] == "0.9.0-1"
    assert p["reviewed_baseline"]["build"] == p["build"] == "20260902"
    assert p["reviewed_baseline"]["image"] == p["baseline_image"]
    assert p["valid_until"] == "2026-10-20"
    assert p["policy"]["python_high_critical_allowed"] is False
    assert p["policy"]["new_os_high_critical_allowed"] is False
    assert p["policy"]["fixed_version_available_allowed"] is False
    assert "CVE-2026-58016" in p["accepted_residual_vulnerabilities"]
    assert "CVE-2026-52490" in p["accepted_residual_vulnerabilities"]
    for cve in ("CVE-2026-76642", "CVE-2026-78408", "CVE-2026-78409", "CVE-2026-78410", "CVE-2026-16742"):
        assert cve in p["accepted_residual_vulnerabilities"]
    assert p["accepted_residual_vulnerabilities"]["CVE-2026-76642"]["packages"]
    for cve in ("CVE-2026-93990", "CVE-2026-88806", "CVE-2026-88807"):
        assert cve in p["accepted_residual_vulnerabilities"]
        assert p["accepted_residual_vulnerabilities"][cve]["review_before"] == "2026-10-20"


def _run(report, tmp_path):
    """Historical acceptance fixtures use the review date, never the CI clock.

    This replaces only the imported test module's clock. The production CLI
    retains the real date and is tested separately for expiration.
    """
    f = tmp_path / "report.json"
    f.write_text(json.dumps(report))
    evaluator_path = ROOT / 'scripts' / 'evaluate_trivy_gate.py'
    spec = importlib.util.spec_from_file_location('cir_r8_policy_under_test', evaluator_path)
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)

    class ReviewedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 1)

    args = [str(evaluator_path), str(f), '--policy', str(ROOT / 'tests/fixtures/historical_r8_risk_policy.json'), '--platform', 'linux/amd64']
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(evaluator, 'date', ReviewedDate), patch.object(sys, 'argv', args):
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = evaluator.main()
    return subprocess.CompletedProcess(args, result, stdout.getvalue(), stderr.getvalue())


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


def test_r8_gate_accepts_new_reviewed_util_linux_cve_in_scoped_package(tmp_path):
    report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[{"VulnerabilityID":"CVE-2026-76642","PkgName":"util-linux","Severity":"HIGH","InstalledVersion":"2.41.5-0+deb13u1","FixedVersion":""}]}]}
    r=_run(report,tmp_path)
    assert r.returncode == 0
    assert "PASS" in r.stdout


def test_r8_gate_rejects_reviewed_cve_outside_package_scope(tmp_path):
    report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[{"VulnerabilityID":"CVE-2026-76642","PkgName":"unexpected-package","Severity":"HIGH","InstalledVersion":"2.41.5-0+deb13u1","FixedVersion":""}]}]}
    r=_run(report,tmp_path)
    assert r.returncode == 1
    assert "unexpected package" in r.stderr


def test_r8_gate_rejects_unreviewed_util_linux_version(tmp_path):
    report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[{"VulnerabilityID":"CVE-2026-76642","PkgName":"util-linux","Severity":"HIGH","InstalledVersion":"2.41.6-1","FixedVersion":""}]}]}
    r=_run(report,tmp_path)
    assert r.returncode == 1
    assert "unreviewed installed version" in r.stderr


def test_r8_gate_accepts_reviewed_2026_10_01_findings(tmp_path):
    cases=(
        ("CVE-2026-93990","libexpat1","2.8.3-1~deb13u1"),
        ("CVE-2026-88806","libx11-6","2:1.8.12-1"),
        ("CVE-2026-88806","libx11-data","2:1.8.12-1"),
        ("CVE-2026-88807","libxrender1","1:0.9.12-1"),
    )
    for cve,pkg,version in cases:
        report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[{"VulnerabilityID":cve,"PkgName":pkg,"Severity":"HIGH","InstalledVersion":version,"FixedVersion":""}]}]}
        r=_run(report,tmp_path)
        assert r.returncode == 0, r.stderr
        assert "PASS" in r.stdout


def test_r8_gate_rejects_new_accepted_findings_when_patchable_or_out_of_scope(tmp_path):
    bad=(
        {"VulnerabilityID":"CVE-2026-93990","PkgName":"libexpat1","Severity":"HIGH","InstalledVersion":"2.8.4-1","FixedVersion":""},
        {"VulnerabilityID":"CVE-2026-88806","PkgName":"libx11-dev","Severity":"HIGH","InstalledVersion":"2:1.8.12-1","FixedVersion":""},
        {"VulnerabilityID":"CVE-2026-88807","PkgName":"libxrender1","Severity":"HIGH","InstalledVersion":"1:0.9.12-1","FixedVersion":"1:0.9.13-1"},
    )
    for vuln in bad:
        report={"Results":[{"Target":"debian","Type":"deb","Vulnerabilities":[vuln]}]}
        r=_run(report,tmp_path)
        assert r.returncode == 1
