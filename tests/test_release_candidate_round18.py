from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_round18_release_candidate_offline_gate_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_release_candidate.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "offline verification: PASS" in result.stdout
    assert "live SCA" in result.stdout


def test_round18_digest_gate_rejects_mutable_tag_and_accepts_digest() -> None:
    script = str(ROOT / "scripts" / "verify_release_candidate.py")
    mutable = subprocess.run(
        [sys.executable, script, "--require-production-digest", "registry.example/cir:0.9.0-1"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert mutable.returncode != 0
    assert "not pinned" in mutable.stderr

    digest = "registry.example/cir@sha256:" + ("a" * 64)
    immutable = subprocess.run(
        [sys.executable, script, "--require-production-digest", digest],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert immutable.returncode == 0, immutable.stderr


def test_round18_sbom_is_transitive_and_matches_release() -> None:
    sbom = json.loads((ROOT / "SBOM_ROUND18.cdx.json").read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["metadata"]["component"]["version"] == (ROOT / "VERSION").read_text().strip()
    assert len(sbom["components"]) == 47
    levels = {
        prop["value"]
        for component in sbom["components"]
        for prop in component.get("properties", [])
        if prop.get("name") == "cir:dependency-level"
    }
    assert {"direct", "transitive"} <= levels


def test_round18_build_metadata_is_current_rc_build() -> None:
    assert (ROOT / "BUILD").read_text(encoding="utf-8").strip() == "20260902"
    deployment = (ROOT / "k8s" / "deployment.yaml").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'APP_BUILD, value: "20260902"' in deployment
    assert "APP_BUILD: 20260902" in compose


def test_round18_release_lineage_is_documented_consistently() -> None:
    changelog = (ROOT / "CHANGELOG.txt").read_text(encoding="utf-8")
    rc = (ROOT / "RELEASE_CANDIDATE_ROUND18.md").read_text(encoding="utf-8")
    notes_it = (ROOT / "RELEASE_NOTES_0.9.0-1.md").read_text(encoding="utf-8")
    notes_en = (ROOT / "RELEASE_NOTES_0.9.0-1_en.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README_en.md").read_text(encoding="utf-8")

    assert "0.8.0 build 20260718 - Baseline" in changelog
    assert "0.8.0-1 - Spostamento incidenti" not in changelog
    assert "Round 1-18" in changelog or "Round 1-18" in notes_it
    assert "Baseline: `0.8.0`" in rc
    assert "0.9.0-1" in notes_it and "0.8.0" in notes_it
    assert "0.9.0-1" in notes_en and "0.8.0" in notes_en
    assert "Genealogia della release" in readme
    assert "Release lineage" in readme_en

    for audit in ROOT.glob("SECURITY_AUDIT_ROUND*.md"):
        text = audit.read_text(encoding="utf-8")
        assert "Release lineage:" in text, audit.name
        assert "0.8.0" in text and "0.9.0-1" in text, audit.name



def test_release_package_includes_release_notes_and_multiarch_builder() -> None:
    package_script = (ROOT / "scripts" / "package_release.sh").read_text(encoding="utf-8")
    # package_release copies the source tree by default; these files must exist and must not be excluded.
    required = (
        "RELEASE_NOTES_0.9.0-1.md",
        "RELEASE_NOTES_0.9.0-1_en.md",
        "scripts/build_multiarch_image.sh",
        "MIGRATION_0.8.0_TO_0.9.0.md",
        "MIGRATION_0.8.0_TO_0.9.0_en.md",
    )
    for relative in required:
        assert (ROOT / relative).is_file(), relative
        assert f"--exclude='{relative}'" not in package_script
        assert relative in package_script
    assert "packaged release is missing" in package_script

    build = (ROOT / "scripts" / "build_multiarch_image.sh").read_text(encoding="utf-8")
    assert "desalvo/cybersecurity-incident-registry" in build
    assert "CIR_DOCKER_REPOSITORY" in build
    assert "CIR_DOCKER_TAG" in build
    assert "--repository|--name" in build
    assert "--tag" in build
    assert 'TAG="${CIR_DOCKER_TAG:-latest}"' in build
    assert "linux/amd64,linux/arm64" in build
    assert "docker buildx build" in build
    assert "--push" in build

    migration_it = (ROOT / "MIGRATION_0.8.0_TO_0.9.0.md").read_text(encoding="utf-8")
    migration_en = (ROOT / "MIGRATION_0.8.0_TO_0.9.0_en.md").read_text(encoding="utf-8")
    for text in (migration_it, migration_en):
        assert "docker-compose" in text.lower()
        assert "kubernetes" in text.lower()
        assert "0.8.0" in text and "0.9.0-1" in text
        assert "SETTING_ENCRYPTION_KEY" in text
        assert "CIR_TRUSTED_PROXY_CIDRS" in text
        assert "postgres:18.6" in text
