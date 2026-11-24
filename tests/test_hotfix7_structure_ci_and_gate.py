from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile
import contextlib
from datetime import date
import importlib.util
import io
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "scripts" / "evaluate_trivy_gate.py"
POLICY = ROOT / "tests/fixtures/historical_r8_risk_policy.json"


def _run_gate(report: dict, policy: dict | None = None) -> subprocess.CompletedProcess[str]:
    """Exercise historical policy fixtures at their review date, in tests only.

    The production evaluator retains the real clock and has no override flag.
    A separate test below invokes its actual CLI with today's date.
    """
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        report_path = td / "report.json"
        policy_path = td / "policy.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        policy_path.write_text(json.dumps(policy or json.loads(POLICY.read_text(encoding="utf-8"))), encoding="utf-8")
        spec = importlib.util.spec_from_file_location('cir_policy_under_test', EVALUATOR)
        evaluator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluator)
        class ReviewedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 1)
        args = [str(EVALUATOR), str(report_path), '--policy', str(policy_path), '--platform', 'linux/amd64']
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(evaluator, 'date', ReviewedDate), patch.object(sys, 'argv', args):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = evaluator.main()
        return subprocess.CompletedProcess(args, result, stdout.getvalue(), stderr.getvalue())


def test_production_evaluator_uses_real_clock_and_rejects_expired_repository_policy():
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / 'report.json'
        report.write_text(json.dumps(_report([_vuln('CVE-2026-76642', 'util-linux')])), encoding='utf-8')
        result = subprocess.run([sys.executable, str(EVALUATOR), str(report), '--policy', str(POLICY)],
                                cwd=ROOT, text=True, capture_output=True)
    policy = json.loads(POLICY.read_text(encoding='utf-8'))
    if date.today() > date.fromisoformat(policy['valid_until']):
        assert result.returncode != 0
        assert 'risk acceptance expired' in result.stderr
    else:
        assert result.returncode == 0, result.stderr


def _report(vulnerabilities: list[dict], *, typ: str = "debian") -> dict:
    return {
        "ArtifactName": "example.invalid/cir@sha256:" + "a" * 64,
        "Results": [{"Target": "Debian 13", "Class": "os-pkgs", "Type": typ, "Vulnerabilities": vulnerabilities}],
    }


def _vuln(cve: str, pkg: str, *, installed: str = "2.41.5-0+deb13u1", fixed: str = "", severity: str = "HIGH") -> dict:
    return {"VulnerabilityID": cve, "PkgName": pkg, "InstalledVersion": installed, "FixedVersion": fixed, "Severity": severity}


def test_hotfix7_document_layout_and_sbom_location() -> None:
    assert sorted(p.name for p in ROOT.glob("*.md")) == ["README.md", "README_en.md"]
    required = {
        "DEVELOPMENT_HISTORY.md", "SECURITY.md", "RELEASE.md", "DEPLOYMENT.md",
        "ADMIN_ALFRESCO.md", "MIGRATION.md", "TESTING_AND_PRODUCTION.md",
    }
    assert required <= {p.name for p in (ROOT / "docs").glob("*.md")}
    assert not list(ROOT.glob("SBOM*.json"))
    assert {"SBOM_ROUND6.cdx.json", "SBOM_ROUND17.cdx.json", "SBOM_ROUND18.cdx.json"} <= {p.name for p in (ROOT / "sbom").glob("*.json")}
    assert (ROOT / "tests/fixtures/historical_r8_risk_policy.json").is_file()


def test_markdown_relative_links_resolve() -> None:
    broken: list[str] = []
    files = [ROOT / "README.md", ROOT / "README_en.md", *sorted((ROOT / "docs").glob("*.md"))]
    link_re = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for md in files:
        for target in link_re.findall(md.read_text(encoding="utf-8")):
            target = target.strip().split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split(" ", 1)[0].strip("<>")
            if not (md.parent / target).resolve().exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert not broken, "broken relative Markdown links: " + "; ".join(broken)


def test_github_actions_is_fail_closed_and_promotes_only_after_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci-release.yml").read_text(encoding="utf-8")
    for needle in (
        "python -m pip check", "python -m pytest -q", "./scripts/run_postgres_tests.sh",
        "scripts/verify_release_candidate.py", "./scripts/run_sca.sh", "linux/amd64,linux/arm64",
        'candidate_tag="ci-${GITHUB_SHA}"', "final_tag=latest", 'final_tag="$GITHUB_REF_NAME"',
        "run_trivy_production_gate.sh", "imagetools create", "DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN",
    ):
        assert needle in workflow
    gate = workflow.index("Run CIR Trivy production gate on exact candidate digest")
    promote = workflow.index("Promote approved digest to final Docker tag")
    assert gate < promote
    assert "continue-on-error: true" not in workflow
    assert "--ignore-unfixed" not in workflow


def test_hotfix7_new_cves_are_exactly_scoped_and_temporary() -> None:
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    assert p["valid_until"] == "2026-10-20"
    expected = {"CVE-2026-76642", "CVE-2026-78408", "CVE-2026-78409", "CVE-2026-78410", "CVE-2026-16742"}
    accepted = p["accepted_residual_vulnerabilities"]
    assert expected <= set(accepted)
    util_packages = {"bsdutils", "libblkid1", "liblastlog2-2", "libmount1", "libsmartcols1", "libuuid1", "login", "mount", "util-linux"}
    for cve in expected - {"CVE-2026-16742"}:
        assert set(accepted[cve]["packages"]) == util_packages
        assert accepted[cve]["review_before"] == "2026-10-20"
        assert accepted[cve]["installed_version_regex"].startswith("^2\\.41\\.5-0\\+deb13u1")
    assert accepted["CVE-2026-16742"]["packages"] == ["libsystemd0", "libudev1"]
    assert accepted["CVE-2026-16742"]["review_before"] == "2026-10-20"


def test_trivy_gate_accepts_exact_hotfix7_disposition() -> None:
    r = _run_gate(_report([_vuln("CVE-2026-76642", "util-linux")]))
    assert r.returncode == 0, r.stderr


def test_trivy_gate_rejects_new_cve_wrong_package_fixed_version_and_python() -> None:
    cases = [
        _report([_vuln("CVE-2099-99999", "util-linux")]),
        _report([_vuln("CVE-2026-76642", "unexpected-pkg")]),
        _report([_vuln("CVE-2026-76642", "util-linux", fixed="2.41.6")]),
        _report([_vuln("CVE-2099-12345", "flask", installed="3.1.3")], typ="python-pkg"),
    ]
    for report in cases:
        r = _run_gate(report)
        assert r.returncode != 0, (r.stdout, r.stderr)


def test_trivy_gate_rejects_expired_acceptance_and_empty_scan() -> None:
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    p["valid_until"] = "2000-01-01"
    r = _run_gate(_report([_vuln("CVE-2026-76642", "util-linux")]), p)
    assert r.returncode != 0 and "expired" in r.stderr
    r = _run_gate({"Results": []})
    assert r.returncode != 0 and "no Results" in r.stderr


def test_security_context_verifier_and_final_production_digest() -> None:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_security_gate_context.py")], cwd=ROOT, text=True, capture_output=True)
    assert r.returncode == 0, r.stderr
    production_image = (ROOT / "PRODUCTION_IMAGE_DIGEST").read_text(encoding="utf-8").strip()
    kustomization = (ROOT / "k8s" / "kustomization.yaml").read_text(encoding="utf-8")

    if production_image == "PENDING_HOTFIX_REBUILD":
        assert 'newTag: "PENDING_HOTFIX_REBUILD"' in kustomization
        assert "digest:" not in kustomization
        return

    match = re.fullmatch(
        r"desalvo/cybersecurity-incident-registry@(sha256:[0-9a-f]{64})",
        production_image,
    )
    assert match, f"invalid immutable production image reference: {production_image!r}"
    digest = match.group(1)
    assert "PENDING_HOTFIX_REBUILD" not in kustomization
    assert "- name: desalvo/cybersecurity-incident-registry" in kustomization
    assert "  newName: desalvo/cybersecurity-incident-registry" in kustomization
    assert f"  digest: {digest}" in kustomization
    assert "newTag:" not in kustomization


def test_release_package_has_new_layout_and_excludes_runtime_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "cir-hotfix7-test.zip"
    # Package a source-only fixture, not potentially installed CI evidence
    # from a prior build. Production packaging still validates all installed
    # receipts and MUST reject stale or tampered generated documentation.
    import shutil
    from scripts.copy_release_tree import copy_release_tree
    source = tmp_path / 'source'
    copy_release_tree(ROOT, source)
    for relative in ('docs/UI_SCREENSHOTS_SOURCE.json', 'docs/UI_SCREENSHOTS_BUILD.json',
                     'app/static/help/ui-runtime/manifest.json'):
        (source / relative).unlink(missing_ok=True)
    r = subprocess.run(['bash', str(source / "scripts" / "package_release.sh"), str(out)],
                       cwd=source, text=True, capture_output=True)
    assert r.returncode == 0, r.stderr
    assert out.is_file() and Path(str(out) + ".sha256").is_file()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        base = "cybersecurity-incident-registry-" + (ROOT / "VERSION").read_text().strip() + "/"
        # A source-only cumulative must retain both UI modes and every helper
        # needed to produce verified real screenshots in the next CI run.
        required_ui_sources = (
            "app/ui_settings.py", "app/ui_documentation.py",
            "app/templates/base.html", "app/templates/login.html", "app/templates/index.html",
            "app/templates/incident_detail.html", "app/static/app.js", "app/static/style.css",
            "app/static/cir-application-logo.svg", "app/static/ai-chatbot/albot-avatar.png",
            "app/templates/ui/navigation.html", "app/templates/ui/header.html",
            "app/templates/ui/login_modern.html", "app/templates/ui/albot.html",
            "app/templates/ui/interface_settings.html",
            "app/static/ui/ui.css", "app/static/ui/ui.js",
            "app/static/ui/incident.css", "app/static/ui/incident.js",
            "app/static/ui/albot.css", "app/static/ui/albot.js",
            "requirements-ui.txt", "scripts/seed_ui_documentation.py",
            "scripts/capture_ui_screenshots.py", "scripts/ui_documentation_evidence.py",
            "scripts/install_ui_documentation.py", "scripts/build_documentation_pdfs.py",
            "tests/test_global_ui_mode.py", "tests/test_modern_ui_shell.py",
            "tests/test_modern_ui_incident_albot.py",
            "tests/test_ui_documentation_evidence.py", "tests/test_ui_screenshot_pipeline.py",
            "app/migration_manager.py", "app/migrate.py", "docker-entrypoint.sh",
            "tests/test_migration_manager_stdlib.py", "tests/test_migration_manager_sqlalchemy.py",
            "tests/test_legacy_schema_migrations.py", "tests/test_automatic_upgrade_integration.py",
            "tests/test_postgresql_automatic_upgrade.py",
            "tests/fixtures/rc16_schema/models.py", "tests/fixtures/rc16_schema/PROVENANCE.json",
        )
        for relative in required_ui_sources:
            assert zf.read(base + relative) == (ROOT / relative).read_bytes(), relative
        for filename in ("cybersecurity-login-v2.png", "cybersecurity-hero-v2.png"):
            assert zf.read(base + "app/static/ui/" + filename) == zf.read(base + "docs/visual-assets/" + filename)
        # CI installs these after evidence validation. They are optional before
        # capture, but packaging must never discard an installed evidence batch.
        # Compare against the staged source-only fixture, not the original
        # checkout: this test deliberately removed installed CI receipts.
        evidence_root = source / "app/static/help/ui-runtime"
        if evidence_root.is_dir():
            for path in evidence_root.rglob("*"):
                if path.is_file():
                    relative = str(path.relative_to(source))
                    assert zf.read(base + relative) == path.read_bytes(), relative
        for relative in ("docs/UI_SCREENSHOTS_SOURCE.json", "docs/UI_SCREENSHOTS_BUILD.json"):
            if (source / relative).is_file():
                assert zf.read(base + relative) == (source / relative).read_bytes(), relative
            else:
                assert base + relative not in names, relative
        assert base + "app/static/help/ui-runtime/manifest.json" not in names
    base = "cybersecurity-incident-registry-" + (ROOT / "VERSION").read_text().strip() + "/"
    assert base + "README.md" in names and base + "README_en.md" in names
    assert base + "docs/SECURITY.md" in names and base + "docs/TESTING_AND_PRODUCTION.md" in names
    assert base + "sbom/SBOM_ROUND18.cdx.json" in names
    assert base + "sbom/SBOM_CURRENT.cdx.json" in names
    assert not any(Path(n).name.startswith("SECURITY_AUDIT_ROUND") and n.endswith(".md") for n in names)
    assert not any("/.pytest_cache/" in n or "/__pycache__/" in n or n.endswith("SCA_PIP_AUDIT.json") for n in names)


def test_runtime_image_excludes_historical_sbom_directory() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert re.search(r"(?m)^sbom/$", dockerignore), "sbom/ must not be copied into the runtime image"
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "cryptography==50.0.1" in requirements
    assert "pypdf==6.21.4" in requirements


def test_trivy_gate_package_specific_util_linux_versions() -> None:
    bsd = _run_gate(_report([_vuln("CVE-2026-76642", "bsdutils", installed="1:2.41.5-0+deb13u1")]))
    assert bsd.returncode == 0, bsd.stderr
    login = _run_gate(_report([_vuln("CVE-2026-76642", "login", installed="1:4.16.0-2+really2.41.5-0+deb13u1")]))
    assert login.returncode == 0, login.stderr
    wrong = _run_gate(_report([_vuln("CVE-2026-76642", "bsdutils", installed="1:2.41.6-0+deb13u1")]))
    assert wrong.returncode != 0


def test_trivy_gate_accepts_reviewed_new_trixie_residuals_only_at_exact_versions() -> None:
    cases = [
        _vuln("CVE-2026-76956", "libexpat1", installed="2.8.3-1~deb13u1"),
        _vuln("CVE-2026-76957", "libexpat1", installed="2.8.3-1~deb13u1"),
        _vuln("CVE-2026-74860", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3"),
        _vuln("CVE-2026-86138", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3"),
        _vuln("CVE-2026-86139", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3"),
        _vuln("CVE-2026-86140", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3"),
        _vuln("CVE-2026-86142", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3"),
        _vuln("CVE-2026-86143", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3"),
        _vuln("CVE-2026-86144", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3"),
    ]
    r = _run_gate(_report(cases))
    assert r.returncode == 0, r.stderr
    fixed = _run_gate(_report([_vuln("CVE-2026-86144", "libxml2", installed="2.12.7+dfsg+really2.9.14-2.1+deb13u3", fixed="2.15.4")]))
    assert fixed.returncode != 0 and "patchable" in fixed.stderr
    wrong_pkg = _run_gate(_report([_vuln("CVE-2026-76956", "expat", installed="2.8.3-1~deb13u1")]))
    assert wrong_pkg.returncode != 0


def test_ci_auto_records_promoted_digest_via_pull_request_and_skips_metadata_rebuilds() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci-release.yml").read_text(encoding="utf-8")
    assert "Detect production-impacting changes" in workflow
    assert "PRODUCTION_IMAGE_DIGEST|k8s/kustomization.yaml" in workflow
    assert "needs.release-scope.outputs.production_changed == 'true'" in workflow
    assert 'if [[ "$GITHUB_REF" == refs/tags/* ]]' in workflow
    assert "pull-requests: write" in workflow
    assert "actions: write" in workflow
    # The production PR now publishes the verified same-run documentation as well
    # as the immutable image digest.  Verify both the step and its inputs.
    assert "Open production digest and documentation pull request" in workflow
    assert "Verify repository documentation publication inputs" in workflow
    assert "scripts/verify_documentation_publication.py" in workflow
    assert "docs/UI_SCREENSHOTS_SOURCE.json docs/UI_SCREENSHOTS_BUILD.json" in workflow
    assert "docs/*.pdf docs/presentation/*" in workflow
    assert "app/static/help/ui-runtime/*.png app/static/help/ui-runtime/manifest.json" in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "scripts/record_production_digest.py" in workflow
    assert '--digest "${{ steps.published.outputs.digest }}"' in workflow
    assert "--format '{{json .Manifest}}'" in workflow
    assert 'Structured manifest inspection' in workflow
    assert 'candidate-index.json' in workflow
    assert 'published-index.json' in workflow
    assert 'imagetools inspect --raw' not in workflow
    assert 'scripts/verify_promoted_manifest.py' in workflow
    assert 'git checkout -b "$branch"' in workflow
    assert 'git push origin "HEAD:$branch"' in workflow
    assert 'gh pr create' in workflow
    assert '--base main' in workflow
    assert 'gh workflow run ci-release.yml --ref "$branch"' in workflow
    assert 'git push origin "HEAD:${GITHUB_REF_NAME}"' not in workflow
    assert "[skip ci]" not in workflow

    verify_idx = workflow.index("Verify published manifest and report digest")
    record_idx = workflow.index("Open production digest and documentation pull request")
    assert verify_idx < record_idx

    # Tag releases publish/report only and never mutate main metadata.
    record_block = workflow[record_idx:]
    assert "if: github.ref == 'refs/heads/main'" in record_block[:260]


def test_record_production_digest_script_is_strict_and_deterministic() -> None:
    script = ROOT / "scripts" / "record_production_digest.py"
    assert script.is_file()
    original_digest = (ROOT / "PRODUCTION_IMAGE_DIGEST").read_text(encoding="utf-8")
    kustomization_path = ROOT / "k8s" / "kustomization.yaml"
    original_kustomization = kustomization_path.read_text(encoding="utf-8")
    digest = "sha256:" + "a" * 64
    try:
        r = subprocess.run(
            [sys.executable, str(script), "--repository", "desalvo/cybersecurity-incident-registry", "--digest", digest],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert r.returncode == 0, r.stderr
        assert (ROOT / "PRODUCTION_IMAGE_DIGEST").read_text(encoding="utf-8").strip() == (
            "desalvo/cybersecurity-incident-registry@" + digest
        )
        rendered = kustomization_path.read_text(encoding="utf-8")
        assert "newTag: \"PENDING_HOTFIX_REBUILD\"" not in rendered
        assert "newName: desalvo/cybersecurity-incident-registry" in rendered
        assert f"digest: {digest}" in rendered

        bad = subprocess.run(
            [sys.executable, str(script), "--repository", "desalvo/cybersecurity-incident-registry:latest", "--digest", digest],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert bad.returncode != 0
        bad = subprocess.run(
            [sys.executable, str(script), "--repository", "desalvo/cybersecurity-incident-registry", "--digest", "sha256:bad"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert bad.returncode != 0
    finally:
        (ROOT / "PRODUCTION_IMAGE_DIGEST").write_text(original_digest, encoding="utf-8")
        kustomization_path.write_text(original_kustomization, encoding="utf-8")
