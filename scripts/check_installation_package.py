#!/usr/bin/env python3
"""Check installation sources and, optionally, rendered Kubernetes objects.

A source-only PASS is not a Helm render, cluster admission, or image security
approval. --require-helm performs real Helm lint/template checks with fixture
image digests that are never deployed or written to release metadata.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata

CHART = ROOT / "charts/cybersecurity-incident-registry"
IMMUTABLE = re.compile(r"^[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}$")
REQUIRED = (
    "VERSION",
    "BUILD",
    "release_metadata.py",
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
    "openshift/cir-template.yaml",
    "openshift/helm-repository.example.yaml",
    "scripts/install_cluster.sh",
    "scripts/package_installers.py",
    "scripts/render_openshift_template.py",
)


def validate_objects(objects: list[dict], platform: str) -> None:
    if not objects:
        raise ValueError("Rendered manifest is empty")
    web_seen = False
    for obj in objects:
        if obj.get("kind") in {"RoleBinding", "ClusterRoleBinding", "SecurityContextConstraints"}:
            raise ValueError("Installer must not grant SCC or cluster permissions")
        if obj.get("kind") == "Secret":
            raise ValueError("Installation manifests reference existing Secrets; credentials must not be embedded")
        if obj.get("kind") == "Route":
            tls = obj["spec"].get("tls", {})
            if platform != "openshift" or tls.get("termination") != "edge" or tls.get("insecureEdgeTerminationPolicy") != "Redirect":
                raise ValueError("OpenShift Route must enforce HTTPS edge termination")
        if obj.get("kind") == "Ingress":
            if not obj["spec"].get("tls") or not all(item.get("secretName") for item in obj["spec"]["tls"]):
                raise ValueError("Production Ingress must reference TLS secrets")
        if obj.get("kind") == "Service" and obj["spec"].get("type", "ClusterIP") != "ClusterIP":
            raise ValueError("Service must be ClusterIP behind the TLS endpoint")
        if obj.get("kind") not in {"Deployment", "StatefulSet"}:
            continue
        pod = obj["spec"]["template"]["spec"]
        if pod.get("automountServiceAccountToken") is not False:
            raise ValueError("Pods must disable service account token mounting")
        if pod.get("initContainers") or pod.get("hostNetwork") or pod.get("hostPID") or pod.get("hostIPC"):
            raise ValueError("No privileged preparation or host namespaces are permitted")
        if any("hostPath" in vol for vol in pod.get("volumes", [])):
            raise ValueError("hostPath is not permitted")
        pod_security = pod.get("securityContext", {})
        if pod_security.get("runAsNonRoot") is not True or pod_security.get("seccompProfile", {}).get("type") != "RuntimeDefault":
            raise ValueError("Pod must require non-root and RuntimeDefault seccomp")
        if platform == "openshift" and any(key in pod_security for key in ("runAsUser", "runAsGroup", "fsGroup")):
            raise ValueError("OpenShift SCC must allocate UID/GID/fsGroup")
        if platform == "kubernetes" and any(not isinstance(pod_security.get(key), int) or pod_security[key] < 1 for key in ("runAsUser", "runAsGroup", "fsGroup")):
            raise ValueError("Kubernetes pod requires explicit non-root IDs and volume group")
        for container in pod.get("containers", []):
            if not IMMUTABLE.fullmatch(container.get("image", "")):
                raise ValueError("Every container must use an immutable sha256 image digest")
            security = container.get("securityContext", {})
            if security.get("runAsNonRoot") is not True or security.get("allowPrivilegeEscalation") is not False or security.get("readOnlyRootFilesystem") is not True:
                raise ValueError("Container must be non-root, read-only and disallow escalation")
            if security.get("capabilities") != {"drop": ["ALL"]} or security.get("seccompProfile", {}).get("type") != "RuntimeDefault":
                raise ValueError("Container must drop ALL capabilities and use RuntimeDefault")
            if security.get("privileged") or (platform == "openshift" and any(key in security for key in ("runAsUser", "runAsGroup"))):
                raise ValueError("Container security is incompatible with restricted OpenShift")
            if not all(container.get(probe) for probe in ("startupProbe", "readinessProbe", "livenessProbe")):
                raise ValueError("Startup, readiness and liveness probes are required")
            env = {item["name"]: item for item in container.get("env", [])}
            mounts = {item["mountPath"] for item in container.get("volumeMounts", [])}
            if container.get("name") == "web":
                web_seen = True
                if not {"/data", "/tmp"} <= mounts:
                    raise ValueError("CIR requires writable /data and /tmp volumes")
                for key, expected in {"CIR_PRODUCTION":"1", "CIR_DISABLE_CSRF":"0", "SESSION_COOKIE_SECURE":"1", "CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE":"0"}.items():
                    if env.get(key, {}).get("value") != expected:
                        raise ValueError(f"Unsafe CIR environment: {key}")
                for key in ("DATABASE_URL", "SECRET_KEY", "ADMIN_INITIAL_PASSWORD", "SETTING_ENCRYPTION_KEY"):
                    if not env.get(key, {}).get("valueFrom", {}).get("secretKeyRef", {}).get("name"):
                        raise ValueError(f"Existing Secret reference missing: {key}")
                if "postgresql://" not in " ".join(container.get("args", [])):
                    raise ValueError("CIR startup must reject non-PostgreSQL URLs")
                if "tcpSocket" not in container["livenessProbe"]:
                    raise ValueError("Web liveness must not terminate an import on request-worker saturation")
            elif container.get("name") == "postgres":
                if not {"/var/lib/postgresql", "/var/run/postgresql", "/tmp", "/dev/shm"} <= mounts:
                    raise ValueError("PostgreSQL writable volumes are incomplete")
                if env.get("PGDATA", {}).get("value") != "/var/lib/postgresql/18/docker":
                    raise ValueError("PostgreSQL 18 storage layout must be explicit")
                for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
                    command = " ".join(container[probe].get("exec", {}).get("command", []))
                    if "pg_isready -h 127.0.0.1" not in command:
                        raise ValueError("PostgreSQL probes must wait for the final TCP listener")
                startup = container["startupProbe"]
                if startup.get("periodSeconds", 0) * startup.get("failureThreshold", 0) < 300:
                    raise ValueError("PostgreSQL startup budget is too short")
    if not web_seen:
        raise ValueError("CIR application Deployment missing")


def load_yaml_documents(path: Path) -> list[dict]:
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("Rendered YAML checks require PyYAML (installed with the project development toolchain)") from exc
    documents = [item for item in yaml.safe_load_all(path.read_text()) if item is not None]
    if len(documents) == 1 and documents[0].get("kind") == "List":
        return documents[0]["items"]
    return documents


def source_checks(root: Path = ROOT) -> None:
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise ValueError("Missing installer files: " + ", ".join(missing))
    chart = root / "charts/cybersecurity-incident-registry"
    schema = json.loads((chart / "values.schema.json").read_text())
    if schema.get("additionalProperties") is not False or schema["properties"]["image"]["properties"]["digest"].get("pattern") != "^sha256:[0-9a-f]{64}$":
        raise ValueError("Chart schema must reject unknown options and mutable image references")
    metadata = read_release_metadata(root)
    if f'appVersion: "{metadata.version}"' not in (chart / "Chart.yaml").read_text():
        raise ValueError("Chart appVersion must match the authoritative VERSION file")
    module_path = root / "scripts/render_openshift_template.py"
    spec = importlib.util.spec_from_file_location("cir_template_renderer", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = json.loads((root / "openshift/cir-template.yaml").read_text())
    # A syntax-only fixture, never a production release or deployment.
    rendered = module.render_template({"IMAGE_SHA256":"a" * 64,"EXISTING_SECRET":"cir-check-secret"}, template)
    validate_objects(rendered["items"], "openshift")


def validate_helm_version(version: str) -> None:
    match = re.fullmatch(r"v?3\.([0-9]+)\.[0-9]+(?:\+[A-Za-z0-9.-]+)?", version.strip())
    if not match or int(match.group(1)) < 14:
        raise ValueError(f"Helm 3.14+ (major 3) is required; found {version!r}")


def ensure_helm() -> str:
    helm = shutil.which("helm")
    if not helm:
        raise ValueError("Helm is required for render verification; install Helm 3.14+ (major 3) and rerun --require-helm")
    result = subprocess.run([helm, "version", "--template", "{{.Version}}"], check=True, text=True, capture_output=True)
    validate_helm_version(result.stdout)
    return helm


def helm_checks() -> None:
    helm = ensure_helm()
    fixture = {"image":{"digest":"sha256:" + "a" * 64},"existingSecret":"cir-check-secret"}
    with tempfile.TemporaryDirectory(prefix="cir-chart-check-") as directory:
        directory = Path(directory)
        for platform in ("kubernetes", "openshift"):
            for mode in ("external", "internal"):
                values = json.loads(json.dumps(fixture))
                values.update({"platform":platform,"route":{"enabled":platform == "openshift"},"database":{"mode":mode,"internal":{"image":{"digest":"sha256:" + "b" * 64},"existingSecret":"cir-postgres-check-secret"}}})
                path = directory / "values.json"
                path.write_text(json.dumps(values))
                subprocess.run([helm,"lint",str(CHART),"--strict","-f",str(path)],check=True)
                result = subprocess.run([helm,"template","cir",str(CHART),"-f",str(path)],check=True,text=True,capture_output=True)
                rendered = directory / "rendered.yaml"
                rendered.write_text(result.stdout)
                validate_objects(load_yaml_documents(rendered), platform)
        rejected = subprocess.run([helm,"template","cir",str(CHART)],text=True,capture_output=True)
        if rejected.returncode == 0:
            raise ValueError("Helm unexpectedly accepted missing image digest/Secret")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-helm", action="store_true")
    parser.add_argument("--check-helm-version", action="store_true")
    parser.add_argument("--rendered", type=Path)
    parser.add_argument("--platform", choices=("kubernetes", "openshift"), default="kubernetes")
    args = parser.parse_args()
    try:
        source_checks()
        if args.rendered:
            validate_objects(load_yaml_documents(args.rendered), args.platform)
        if args.check_helm_version:
            ensure_helm()
        if args.require_helm:
            helm_checks()
    except (ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"Installation package verification: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.require_helm:
        mode = "source + real Helm render; cluster not validated"
    elif args.rendered:
        mode = "source + supplied rendered objects; cluster not validated"
    elif args.check_helm_version:
        mode = "source + Helm client version; render/cluster not validated"
    else:
        mode = "source structure only; Helm/cluster not validated"
    print(f"Installation package verification: PASS ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
