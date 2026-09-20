#!/usr/bin/env python3
"""Offline release-candidate consistency and hardening gate.

This gate verifies facts that can be established from the source tree alone.
External release gates (live SCA, real PostgreSQL, final image scan, registry
image digest) are reported separately and must be completed before production.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def check_source_tree() -> list[str]:
    errors: list[str] = []
    version = read("VERSION").strip()
    build = read("BUILD").strip()

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version):
        fail(errors, f"VERSION has unexpected format: {version!r}")
    if not re.fullmatch(r"\d{8}", build):
        fail(errors, f"BUILD must be YYYYMMDD: {build!r}")
    else:
        try:
            datetime.strptime(build, "%Y%m%d")
        except ValueError:
            fail(errors, f"BUILD is not a valid calendar date: {build!r}")

    compose = read("docker-compose.yml")
    deployment = read("k8s/deployment.yaml")
    kustomization = read("k8s/kustomization.yaml")
    production = read("docker-compose.production.yml")

    for label, text in (("docker-compose.yml", compose), ("k8s/deployment.yaml", deployment)):
        if version not in text:
            fail(errors, f"{label} does not contain VERSION {version}")
        if build not in text:
            fail(errors, f"{label} does not contain BUILD {build}")

    production_digest_path = ROOT / "PRODUCTION_IMAGE_DIGEST"
    production_digest = production_digest_path.read_text(encoding="utf-8").strip() if production_digest_path.exists() else ""
    digest_value = production_digest.split("@sha256:", 1)[1] if "@sha256:" in production_digest else ""
    has_release_tag = f'newTag: "{version}"' in kustomization
    has_release_digest = bool(digest_value) and f"digest: sha256:{digest_value}" in kustomization
    pending_rebuild = production_digest.startswith("PENDING_")
    has_pending_tag = 'newTag: "PENDING_HOTFIX_REBUILD"' in kustomization and "digest:" not in kustomization
    if pending_rebuild:
        if not has_pending_tag:
            fail(errors, "pending production rebuild requires fail-closed PENDING_HOTFIX_REBUILD Kustomize tag")
    elif not (has_release_tag or has_release_digest):
        fail(errors, "k8s/kustomization.yaml must match VERSION tag or recorded production digest")
    if ":latest" in deployment or ":latest" in kustomization:
        fail(errors, "active Kubernetes release manifests must not use :latest")

    production_requirements = (
        "CIR_PRODUCTION_IMAGE:?",
        "read_only: true",
        "no-new-privileges:true",
        "CIR_PRODUCTION: \"1\"",
        "CIR_DISABLE_CSRF: \"0\"",
        "SESSION_COOKIE_SECURE: \"1\"",
        "CIR_FORCE_HSTS: \"1\"",
        "CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE: \"0\"",
    )
    for needle in production_requirements:
        if needle not in production:
            fail(errors, f"docker-compose.production.yml missing hardening requirement: {needle}")

    if "automountServiceAccountToken: false" not in deployment:
        fail(errors, "Kubernetes deployment must disable automatic service-account token mounting")
    for needle in ("runAsNonRoot: true", "readOnlyRootFilesystem: true", 'drop: ["ALL"]', "RuntimeDefault"):
        if needle not in deployment:
            fail(errors, f"Kubernetes deployment missing hardening requirement: {needle}")

    pvc = read("k8s/pvc.yaml")
    if "mountPath: /data}" not in deployment or "claimName: cir-data" not in deployment:
        fail(errors, "Kubernetes deployment must mount the shared cir-data PVC at /data")
    for obsolete_mount in ("mountPath: /data/uploads}", "mountPath: /data/backups}", "claimName: cir-uploads", "claimName: cir-backups"):
        if obsolete_mount in deployment:
            fail(errors, f"Kubernetes deployment still contains obsolete split-PVC layout: {obsolete_mount}")
    if "name: cir-data" not in pvc or "ReadWriteMany" not in pvc:
        fail(errors, "k8s/pvc.yaml must define the shared cir-data RWX claim used by the two-replica example")

    kustomized = {line.strip()[2:] for line in kustomization.splitlines() if line.strip().startswith("- ")}
    if "secrets.example.yaml" in kustomized:
        fail(errors, "k8s/secrets.example.yaml must never be an active Kustomize resource")

    root_markdown = sorted(p.name for p in ROOT.glob("*.md"))
    if root_markdown != ["README.md", "README_en.md"]:
        fail(errors, f"root Markdown layout must contain only README.md and README_en.md, found: {root_markdown}")
    required_docs = {
        "DEVELOPMENT_HISTORY.md", "SECURITY.md", "RELEASE.md", "DEPLOYMENT.md",
        "ADMIN_ALFRESCO.md", "MIGRATION.md", "TESTING_AND_PRODUCTION.md",
    }
    missing_docs = sorted(name for name in required_docs if not (ROOT / "docs" / name).is_file())
    if missing_docs:
        fail(errors, f"consolidated docs missing: {missing_docs}")
    root_sboms = sorted(p.name for p in ROOT.glob("SBOM*.json"))
    if root_sboms:
        fail(errors, f"SBOM artifacts must not remain in root: {root_sboms}")

    package_script = read("scripts/package_release.sh")
    required_release_docs = (
        "README.md",
        "README_en.md",
        "docs/DEVELOPMENT_HISTORY.md",
        "docs/SECURITY.md",
        "docs/RELEASE.md",
        "docs/DEPLOYMENT.md",
        "docs/ADMIN_ALFRESCO.md",
        "docs/MIGRATION.md",
        "docs/TESTING_AND_PRODUCTION.md",
        "sbom/SBOM_ROUND18.cdx.json",
        "TRIVY_RISK_ACCEPTANCE_R8.json",
        "scripts/build_multiarch_image.sh",
        "scripts/run_trivy_production_gate.sh",
        "scripts/evaluate_trivy_gate.py",
        "scripts/verify_security_gate_context.py",
        "PRODUCTION_IMAGE_DIGEST",
        ".github/workflows/ci-release.yml",
        "k8s/migrate-separated-pvcs-to-cir-data.example.yaml",
    )
    for relative in required_release_docs:
        if not (ROOT / relative).is_file():
            fail(errors, f"required release documentation/tool missing: {relative}")
        if relative not in package_script:
            fail(errors, f"release packaging does not enforce required file: {relative}")

    for excluded in ("--exclude='.env'", "--exclude='*.key'", "--exclude='*.crt'", "--exclude='instance/*'", "--exclude='app/uploads/*'"):
        if excluded not in package_script:
            fail(errors, f"release packaging is missing sensitive/runtime exclusion: {excluded}")

    dockerfile = read("Dockerfile")
    for needle in (
        "FROM python:3.12.14-slim-trixie AS python-deps",
        "FROM python:3.12.14-slim-trixie AS runtime",
        "COPY --from=python-deps /opt/cir-venv /opt/cir-venv",
        "pip uninstall -y pip setuptools wheel",
        "libreoffice-writer-nogui",
    ):
        if needle not in dockerfile:
            fail(errors, f"Dockerfile missing R7 runtime-minimization requirement: {needle}")

    requirements_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for required_pin in ("pypdf==6.16.2", "cryptography==50.0.1"):
        if required_pin not in requirements_text:
            fail(errors, f"required R4 security pin missing: {required_pin}")

    sbom_path = ROOT / "sbom/SBOM_ROUND18.cdx.json"
    if not sbom_path.exists():
        fail(errors, "sbom/SBOM_ROUND18.cdx.json is missing")
    else:
        try:
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(errors, f"sbom/SBOM_ROUND18.cdx.json is invalid JSON: {exc}")
        else:
            component = sbom.get("metadata", {}).get("component", {})
            if component.get("version") != version:
                fail(errors, "SBOM application version does not match VERSION")
            if sbom.get("specVersion") != "1.6":
                fail(errors, "SBOM must use CycloneDX 1.6")
            if len(sbom.get("components", [])) < 1:
                fail(errors, "SBOM contains no dependency components")

    policy_path = ROOT / "TRIVY_RISK_ACCEPTANCE_R8.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(errors, f"TRIVY_RISK_ACCEPTANCE_R8.json is invalid: {exc}")
    else:
        if policy.get("release") != version or policy.get("build") != build:
            fail(errors, "R8 Trivy risk policy release/build does not match VERSION/BUILD")
        rules = policy.get("policy", {})
        for key in ("python_high_critical_allowed", "new_os_high_critical_allowed", "fixed_version_available_allowed"):
            if rules.get(key) is not False:
                fail(errors, f"R8 Trivy policy must keep {key}=false")
        if not policy.get("accepted_residual_vulnerabilities"):
            fail(errors, "R8 Trivy risk policy contains no reviewed residual CVEs")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-production-digest",
        metavar="IMAGE",
        help="also require IMAGE to be an immutable image@sha256:<64 hex> reference",
    )
    args = parser.parse_args()

    errors = check_source_tree()
    if args.require_production_digest:
        if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-fA-F]{64}", args.require_production_digest):
            errors.append("production image is not pinned by an immutable sha256 digest")

    if errors:
        print("Release-candidate verification: FAIL", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 1

    if args.require_production_digest:
        print("Release-candidate offline verification: PASS")
        print(f"Version: {read('VERSION').strip()}  Build: {read('BUILD').strip()}")
        print(f"Immutable production digest syntax verified: {args.require_production_digest}")
        print("External gate evidence is recorded separately in docs/RELEASE.md.")
    else:
        print("Release-candidate offline verification: PASS")
        print(f"Version: {read('VERSION').strip()}  Build: {read('BUILD').strip()}")
        print("External production gates must be evidenced separately before promotion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
