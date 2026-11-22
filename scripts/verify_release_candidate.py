#!/usr/bin/env python3
"""Offline release-candidate consistency and hardening gate.

This gate verifies facts that can be established from the source tree alone.
External release gates (live SCA, real PostgreSQL, final image scan, registry
image digest) are reported separately and must be completed before production.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import importlib.util
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata, validate_build, validate_version


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def _declaration(value: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Compare the source requirement subset without importing installed deps."""
    if not isinstance(value, str):
        raise ValueError("Dependency declaration must be text")
    match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[([A-Za-z0-9_,.-]+)\])?\s*([<>=!~0-9A-Za-z.,*+-]+)", value.strip())
    if not match:
        raise ValueError(f"Unsupported source dependency declaration: {value!r}")
    name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
    extras = tuple(sorted(item.lower() for item in (match.group(2) or "").split(",") if item))
    specifiers = tuple(sorted(match.group(3).split(",")))
    return name, extras, specifiers


def check_current_sbom(root: Path, version: str) -> None:
    """Source inventories are declarations, never invented installed graphs."""
    requirements = root / 'requirements.txt'
    expected = {}
    for line in requirements.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            declaration = _declaration(line)
            if declaration[0] in expected:
                raise ValueError('Duplicate source requirement')
            expected[declaration[0]] = declaration
    sbom = json.loads((root / 'sbom/SBOM_CURRENT.cdx.json').read_text(encoding='utf-8'))
    if sbom.get('bomFormat') != 'CycloneDX' or sbom.get('specVersion') != '1.6':
        raise ValueError('Current SBOM must use CycloneDX 1.6')
    metadata = sbom.get('metadata', {})
    component = metadata.get('component', {})
    if component.get('name') != 'cybersecurity-incident-registry' or component.get('version') != version:
        raise ValueError('Current SBOM application version does not match VERSION')
    properties = {item['name']: item['value'] for item in metadata.get('properties', [])}
    if (properties.get('cir:inventory-source') != 'declared-requirements'
            or properties.get('cir:resolution-status') != 'not-resolved'):
        raise ValueError('Current source SBOM must explicitly identify unresolved declarations')
    if properties.get('cir:source-requirements-sha256') != hashlib.sha256(requirements.read_bytes()).hexdigest():
        raise ValueError('Current SBOM requirements checksum does not match requirements.txt')
    actual = {}
    for dependency in sbom.get('components', []):
        props = {item['name']: item['value'] for item in dependency.get('properties', [])}
        declaration = _declaration(props.get('cir:declared-requirement'))
        name = re.sub(r'[-_.]+', '-', dependency.get('name', '')).lower()
        if name != declaration[0] or name in actual or props.get('cir:dependency-level') != 'direct':
            raise ValueError('Current source SBOM has invalid or duplicate direct dependencies')
        specs = declaration[2]
        pinned = specs[0][2:] if len(specs) == 1 and specs[0].startswith('==') and '*' not in specs[0] else None
        if dependency.get('version') != pinned or dependency.get('hashes'):
            raise ValueError('Declared source SBOM cannot invent resolved versions or wheel hashes')
        actual[name] = declaration
    if not expected or actual != expected:
        raise ValueError('Current source SBOM does not contain exactly the declared runtime requirements')


def check_reviewed_policy(policy: dict, version: str) -> None:
    """Keep release scope separate from the dated security review evidence."""
    if policy.get('release') != version:
        raise ValueError('R8 Trivy risk policy release scope does not match VERSION')
    baseline = policy.get('reviewed_baseline', {})
    validate_version(baseline.get('release'))
    validate_build(baseline.get('build'))
    if (policy.get('build') != baseline.get('build')
            or policy.get('baseline_image') != baseline.get('image')
            or not isinstance(baseline.get('image'), str)
            or not baseline['image'].endswith(':' + baseline['release'])):
        raise ValueError('R8 reviewed baseline metadata is inconsistent')
    if policy.get('release_status') != 'review_required':
        raise ValueError('Development release must keep security review_required status')
    reviewed = date.fromisoformat(policy['reviewed_on'])
    expires = date.fromisoformat(policy['valid_until'])
    if reviewed > expires:
        raise ValueError('R8 risk policy has an invalid review/expiry interval')


def check_source_tree() -> list[str]:
    errors: list[str] = []
    try:
        metadata = read_release_metadata(ROOT)
    except (OSError, ValueError) as exc:
        return [f"Invalid release metadata: {exc}"]
    version = metadata.version

    compose = read("docker-compose.yml")
    deployment = read("k8s/deployment.yaml")
    kustomization = read("k8s/kustomization.yaml")
    production = read("docker-compose.production.yml")

    for label, text in (("docker-compose.yml", compose), ("k8s/deployment.yaml", deployment)):
        if re.search(r"(?:name:\s*APP_(?:VERSION|BUILD)\b|^\s*APP_(?:VERSION|BUILD)\s*:)", text, re.M):
            fail(errors, f"{label} must use image VERSION/BUILD rather than static runtime overrides")
    if f'image: desalvo/cybersecurity-incident-registry:{version}' not in deployment:
        fail(errors, f"k8s/deployment.yaml does not select VERSION {version}")

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
        "ADMIN_ALFRESCO.md", "MIGRATION.md", "TESTING_AND_PRODUCTION.md", "HANDOFF.md", "TRAINING.md",
    }
    missing_docs = sorted(name for name in required_docs if not (ROOT / "docs" / name).is_file())
    if missing_docs:
        fail(errors, f"consolidated docs missing: {missing_docs}")
    root_sboms = sorted(p.name for p in ROOT.glob("SBOM*.json"))
    if root_sboms:
        fail(errors, f"SBOM artifacts must not remain in root: {root_sboms}")

    package_script = read("scripts/package_release.sh")
    required_release_docs = (
        "application_identity.py",
        "app/documentation.py",
        "app/templates/documentation/cover.html",
        "app/templates/documentation/guide.html",
        "app/static/ui/documentation.css",
        "app/static/branding/platforms/manifest.json",
        "scripts/documentation_cover.py",
        "scripts/documentation_markdown_pdf.py",
        "scripts/build_training_presentation.py",
        "scripts/presentation_evidence.py",
        "scripts/finalize_documentation_bundle.py",
        "scripts/review_production_target.py",
        "requirements-docs.txt",
        ".github/workflows/security-review.yml",
        "tests/test_documentation_online.py",
        "tests/test_periodic_security_review.py",
        "tests/test_training_presentation_builder.py",
        "docs/presentation/presentation-receipt.json",
        "docs/presentation/manual-first-page-documentazione_utente.png",
        "docs/presentation/manual-first-page-documentazione_amministrativa.png",
        "docs/presentation/manual-first-page-user_documentation_en.png",
        "docs/presentation/manual-first-page-administrator_documentation_en.png",
        "docs/presentation/manual-first-page-ADMIN_ALFRESCO.png",
        "README.md",
        "README_en.md",
        "docs/DEVELOPMENT_HISTORY.md",
        "docs/SECURITY.md",
        "docs/RELEASE.md",
        "docs/DEPLOYMENT.md",
        "docs/ADMIN_ALFRESCO.md",
        "docs/MIGRATION.md",
        "docs/TESTING_AND_PRODUCTION.md",
        "docs/HANDOFF.md",
        "docs/TRAINING.md",
        "docs/presentation/CIR_Operational_Training_IT.pptx",
        "docs/presentation/content_it.json",
        "docs/presentation/build.mjs",
        "docs/presentation/assets/sources.json",
        "scripts/build_brochures.py",
        "sbom/SBOM_ROUND18.cdx.json",
        "sbom/SBOM_CURRENT.cdx.json",
        "release_metadata.py",
        "scripts/prepare_release_metadata.py",
        "TRIVY_RISK_ACCEPTANCE_R8.json",
        "scripts/build_multiarch_image.sh",
        "scripts/run_trivy_production_gate.sh",
        "scripts/evaluate_trivy_gate.py",
        "scripts/verify_security_gate_context.py",
        "scripts/record_production_digest.py",
        "PRODUCTION_IMAGE_DIGEST",
        ".github/workflows/ci-release.yml",
        "k8s/migrate-separated-pvcs-to-cir-data.example.yaml",
        "charts/cybersecurity-incident-registry/Chart.yaml",
        "charts/cybersecurity-incident-registry/values.yaml",
        "charts/cybersecurity-incident-registry/values-openshift.yaml",
        "charts/cybersecurity-incident-registry/values.schema.json",
        "charts/cybersecurity-incident-registry/templates/_helpers.tpl",
        "charts/cybersecurity-incident-registry/templates/deployment.yaml",
        "charts/cybersecurity-incident-registry/templates/postgresql.yaml",
        "charts/cybersecurity-incident-registry/templates/service.yaml",
        "charts/cybersecurity-incident-registry/templates/pvc.yaml",
        "charts/cybersecurity-incident-registry/templates/exposure.yaml",
        "charts/cybersecurity-incident-registry/templates/NOTES.txt",
        "openshift/cir-template.yaml",
        "openshift/helm-repository.example.yaml",
        "scripts/check_installation_package.py",
        "scripts/package_installers.py",
        "scripts/install_cluster.sh",
        "scripts/render_openshift_template.py",
        "tests/test_cluster_installation_package.py",
    )
    for relative in required_release_docs:
        if not (ROOT / relative).is_file():
            fail(errors, f"required release documentation/tool missing: {relative}")
        if relative not in package_script:
            fail(errors, f"release packaging does not enforce required file: {relative}")

    try:
        installer_spec = importlib.util.spec_from_file_location(
            "cir_installation_verifier", ROOT / "scripts/check_installation_package.py"
        )
        installer_verifier = importlib.util.module_from_spec(installer_spec)
        installer_spec.loader.exec_module(installer_verifier)
        installer_verifier.source_checks(ROOT)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        fail(errors, f"installation source consistency failed: {exc}")

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
    for required_pin in ("pypdf==6.19.0", "cryptography==50.0.1"):
        if required_pin not in requirements_text:
            fail(errors, f"required R4 security pin missing: {required_pin}")

    try:
        check_current_sbom(ROOT, version)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        fail(errors, f"Current source SBOM verification failed: {exc}")
    # Historical inventories retain the versions and dependency graphs that
    # were actually recorded. They are not current vulnerability scan evidence.
    for sbom_path in sorted((ROOT / 'sbom').glob('SBOM_ROUND*.cdx.json')):
        try:
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            if sbom.get('bomFormat') != 'CycloneDX' or sbom.get('specVersion') not in ('1.5', '1.6') or not sbom.get('components'):
                raise ValueError('Expected a nonempty historical CycloneDX inventory')
        except (OSError, ValueError, AttributeError) as exc:
            fail(errors, f"Historical SBOM {sbom_path.name} is invalid: {exc}")

    policy_path = ROOT / "TRIVY_RISK_ACCEPTANCE_R8.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(errors, f"TRIVY_RISK_ACCEPTANCE_R8.json is invalid: {exc}")
    else:
        try:
            check_reviewed_policy(policy, version)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            fail(errors, f"R8 risk review metadata is invalid: {exc}")
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
