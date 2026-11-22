#!/usr/bin/env python3
"""Build a deterministic local Helm chart/index and standalone installation ZIP.

This uses the documented Helm tar.gz layout and a JSON index (valid YAML). It
requires no network, never publishes the repository, and never approves an image.
Use --require-helm to require actual Helm lint/template verification before packing.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tarfile
from urllib.parse import urlparse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata

CHART = ROOT / "charts/cybersecurity-incident-registry"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_package(output: Path, repository_url: str = "", require_helm: bool = False) -> dict[str, str]:
    metadata = read_release_metadata(ROOT)
    build_date = datetime.strptime(metadata.build, "%Y%m%d")
    spec = importlib.util.spec_from_file_location("cir_install_check", ROOT / "scripts/check_installation_package.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    checks.source_checks()
    if require_helm:
        checks.helm_checks()
    if repository_url:
        parsed = urlparse(repository_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Helm repository URL must be HTTPS without credentials, query or fragment")
    output = output.resolve()
    if output == CHART or CHART in output.parents:
        raise ValueError("Output must be outside the source chart")
    output.mkdir(parents=True, exist_ok=True)
    chart_text = (CHART / "Chart.yaml").read_text()
    version_match = re.search(r"^version: ([0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?)$", chart_text, re.M)
    if not version_match:
        raise ValueError("Chart version is missing or not supported")
    chart_version = version_match.group(1)
    chart_name = CHART.name
    packaged_chart = output / f"{chart_name}-{chart_version}.tgz"
    files = sorted(path for path in CHART.rglob("*") if path.is_file() and not path.is_symlink())
    if any(path.is_symlink() for path in CHART.rglob("*")):
        raise ValueError("Chart cannot contain symlinks")
    allowed_suffixes = {".yaml", ".json", ".tpl", ".txt"}
    if any(path.suffix not in allowed_suffixes and path.name != ".helmignore" for path in files):
        raise ValueError("Unexpected file in chart; remove generated archives/cache before packaging")
    tar_bytes = io.BytesIO()
    with gzip.GzipFile(fileobj=tar_bytes, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for path in files:
                data = path.read_bytes()
                info = tarfile.TarInfo(f"{chart_name}/{path.relative_to(CHART).as_posix()}")
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
    packaged_chart.write_bytes(tar_bytes.getvalue())
    chart_url = f"{repository_url.rstrip('/')}/{packaged_chart.name}" if repository_url else packaged_chart.name
    fixed_time = build_date.strftime("%Y-%m-%dT00:00:00Z")
    index = {"apiVersion":"v1", "generated":fixed_time, "entries":{chart_name:[{
        "apiVersion":"v2", "name":chart_name, "version":chart_version, "appVersion":metadata.version,
        "description":"Cybersecurity Incident Registry with hardened Kubernetes and OpenShift deployment",
        "type":"application", "kubeVersion":">=1.25.0-0", "created":fixed_time,
        "digest":sha256(packaged_chart), "urls":[chart_url],
        "annotations":{"charts.openshift.io/name":"Cybersecurity Incident Registry","charts.openshift.io/provider":"CIR project"}
    }]}}
    index_path = output / "index.yaml"
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    evidence = {"functional_version":metadata.version, "build":metadata.build, "chart_version":chart_version,
        "source_checks":"PASS", "helm_render":"PASS" if require_helm else "NOT_RUN",
        "cluster_admission":"NOT_RUN", "image_build":"NOT_RUN", "image_security_gate":"NOT_RUN",
        "production_image_digest":(ROOT / "PRODUCTION_IMAGE_DIGEST").read_text().strip(),
        "repository_published":False}
    evidence_path = output / "installation-checks.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    base = f"cybersecurity-incident-registry-{metadata.version}-installation-{chart_version}"
    zip_path = output / (base + ".zip")
    paths = [(path, f"charts/{chart_name}/{path.relative_to(CHART).as_posix()}") for path in files]
    paths += [(ROOT / name, name) for name in (
        "openshift/cir-template.yaml", "openshift/helm-repository.example.yaml",
        "scripts/check_installation_package.py", "scripts/render_openshift_template.py",
        "scripts/install_cluster.sh", "scripts/package_installers.py",
        "PRODUCTION_IMAGE_DIGEST", "VERSION", "BUILD", "release_metadata.py",
    )]
    paths += [(path, "docs/" + path.name) for path in sorted((ROOT / "docs").glob("*.md"))]
    paths += [(packaged_chart,f"helm-repository/{packaged_chart.name}"), (index_path,"helm-repository/index.yaml"), (evidence_path,"installation-checks.json")]
    manifest = {}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in sorted(paths, key=lambda item:item[1]):
            data = path.read_bytes()
            info = zipfile.ZipInfo(f"{base}/{relative}", date_time=build_date.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((0o100755 if relative.startswith("scripts/") else 0o100644) << 16)
            archive.writestr(info, data)
            manifest[relative] = hashlib.sha256(data).hexdigest()
        info = zipfile.ZipInfo(f"{base}/SHA256SUMS.json", date_time=build_date.timetuple()[:6])
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    for path in (packaged_chart, zip_path):
        path.with_name(path.name + ".sha256").write_text(f"{sha256(path)}  {path.name}\n")
    return {"chart":str(packaged_chart), "index":str(index_path), "zip":str(zip_path), "checks":str(evidence_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository-url", default="")
    parser.add_argument("--require-helm", action="store_true")
    args = parser.parse_args()
    try:
        result = build_package(args.output, args.repository_url, args.require_helm)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
