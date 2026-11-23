#!/usr/bin/env python3
"""Generate CycloneDX inventories without inventing installed dependencies.

The generator intentionally uses only Python package metadata already installed in
this environment.  It does not contact package indexes.  Direct dependencies are
read from requirements.txt, then their active transitive dependencies are walked
through ``Requires-Dist`` metadata.  When ``--wheel-dir`` is provided, SHA-256
hashes of matching wheels are attached to components as supply-chain evidence.
``--declared-only`` creates an explicitly unresolved source inventory from the
requirements. It does not assert transitive versions or installed wheel hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
from urllib.parse import quote

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_requirements(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            _, nested = line.split(None, 1)
            requirements.extend(_read_requirements((path.parent / nested).resolve()))
            continue
        # Project requirement files are intentionally simple pinned/specifier
        # lines; options such as --index-url do not describe components.
        if line.startswith("-"):
            continue
        requirements.append(Requirement(line))
    return requirements


def _installed_distributions() -> dict[str, metadata.Distribution]:
    result: dict[str, metadata.Distribution] = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            result[canonicalize_name(name)] = dist
    return result


def _marker_applies(req: Requirement, extras: set[str]) -> bool:
    if req.marker is None:
        return True
    candidates = extras or {""}
    return any(req.marker.evaluate({"extra": extra}) for extra in candidates)


def _resolve_graph(
    direct: list[Requirement],
    installed: dict[str, metadata.Distribution],
) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    direct_names = {canonicalize_name(req.name) for req in direct}
    extras_by_name: dict[str, set[str]] = {
        canonicalize_name(req.name): set(req.extras) for req in direct
    }

    for req in direct:
        key = canonicalize_name(req.name)
        dist = installed.get(key)
        if dist is None:
            raise RuntimeError(f"Direct dependency is not installed: {req.name}")
        if req.specifier and not req.specifier.contains(dist.version, prereleases=True):
            raise RuntimeError(
                f"Installed {req.name}=={dist.version} does not satisfy {req.specifier}"
            )

    graph: dict[str, set[str]] = {}
    reachable: set[str] = set(direct_names)
    queue = list(sorted(direct_names))

    while queue:
        key = queue.pop(0)
        dist = installed.get(key)
        if dist is None:
            raise RuntimeError(f"Transitive dependency is not installed: {key}")
        graph.setdefault(key, set())
        active_extras = extras_by_name.get(key, set())
        for raw_req in dist.requires or []:
            req = Requirement(raw_req)
            if not _marker_applies(req, active_extras):
                continue
            child = canonicalize_name(req.name)
            child_dist = installed.get(child)
            if child_dist is None:
                raise RuntimeError(
                    f"{dist.metadata.get('Name', key)} requires missing dependency {req.name}"
                )
            if req.specifier and not req.specifier.contains(child_dist.version, prereleases=True):
                raise RuntimeError(
                    f"Installed {req.name}=={child_dist.version} does not satisfy {req.specifier} "
                    f"required by {dist.metadata.get('Name', key)}"
                )
            graph[key].add(child)
            before = set(extras_by_name.get(child, set()))
            after = before | set(req.extras)
            extras_by_name[child] = after
            if child not in reachable:
                reachable.add(child)
                queue.append(child)
            elif after != before:
                # New extras can enable additional conditional dependencies.
                queue.append(child)

    return reachable, graph, extras_by_name


def _wheel_evidence(wheel_dir: Path | None) -> dict[tuple[str, str], tuple[str, str]]:
    if wheel_dir is None:
        return {}
    evidence: dict[tuple[str, str], tuple[str, str]] = {}
    for wheel in sorted(wheel_dir.glob("*.whl")):
        try:
            name, version, _build, _tags = parse_wheel_filename(wheel.name)
        except Exception:
            continue
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        evidence[(canonicalize_name(str(name)), str(version))] = (wheel.name, digest)
    return evidence


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{quote(canonicalize_name(name), safe='-._~')}@{quote(version, safe='-._~')}"


def build_declared_sbom(requirements_path: Path) -> dict:
    """Inventory source declarations; retain version ranges as ranges.

    This is useful for source candidates prepared without an environment that
    satisfies the exact project requirements. CI generates the installed graph
    separately after dependency installation; historical SBOMs are not relabeled.
    """
    direct = _read_requirements(requirements_path)
    app_version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    root_ref = f"pkg:generic/cybersecurity-incident-registry@{quote(app_version, safe='-._~')}"
    components = []
    identities = set()
    for req in sorted(direct, key=lambda item: canonicalize_name(item.name)):
        name = canonicalize_name(req.name)
        if name in identities:
            raise ValueError(f"Duplicate direct dependency declaration: {name}")
        identities.add(name)
        specs = list(req.specifier)
        pinned = specs[0].version if len(specs) == 1 and specs[0].operator == "==" and "*" not in specs[0].version else None
        ref = _purl(name, pinned) if pinned else f"pkg:pypi/{quote(name, safe='-._~')}"
        component = {
            "type": "library", "name": req.name, "bom-ref": ref, "purl": ref,
            "properties": [
                {"name": "cir:dependency-level", "value": "direct"},
                {"name": "cir:declared-requirement", "value": str(req)},
            ],
        }
        if pinned:
            component["version"] = pinned
        components.append(component)
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {
            "component": {
                "type": "application", "name": "cybersecurity-incident-registry",
                "version": app_version, "bom-ref": root_ref, "purl": root_ref,
            },
            "properties": [
                {"name": "cir:inventory-source", "value": "declared-requirements"},
                {"name": "cir:resolution-status", "value": "not-resolved"},
                {"name": "cir:source-requirements", "value": requirements_path.name},
                {"name": "cir:source-requirements-sha256", "value": hashlib.sha256(requirements_path.read_bytes()).hexdigest()},
            ],
        },
        "components": components,
        "dependencies": [{"ref": root_ref, "dependsOn": [component["bom-ref"] for component in components]}],
    }


def build_sbom(requirements_path: Path, wheel_dir: Path | None = None) -> dict:
    direct = _read_requirements(requirements_path)
    installed = _installed_distributions()
    reachable, graph, _extras = _resolve_graph(direct, installed)
    direct_names = {canonicalize_name(req.name) for req in direct}
    wheel_hashes = _wheel_evidence(wheel_dir)

    version_path = PROJECT_ROOT / "VERSION"
    app_version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else "unknown"
    root_ref = f"pkg:generic/cybersecurity-incident-registry@{quote(app_version, safe='-._~')}"

    components = []
    refs: dict[str, str] = {}
    for key in sorted(reachable):
        dist = installed[key]
        display_name = dist.metadata.get("Name") or key
        version = dist.version
        ref = _purl(display_name, version)
        refs[key] = ref
        properties = [
            {
                "name": "cir:dependency-level",
                "value": "direct" if key in direct_names else "transitive",
            }
        ]
        component = {
            "type": "library",
            "name": display_name,
            "version": version,
            "bom-ref": ref,
            "purl": ref,
            "properties": properties,
        }
        wheel = wheel_hashes.get((key, version))
        if wheel:
            filename, digest = wheel
            component["hashes"] = [{"alg": "SHA-256", "content": digest}]
            properties.append({"name": "cir:wheel-filename", "value": filename})
        components.append(component)

    dependencies = [
        {
            "ref": root_ref,
            "dependsOn": [refs[key] for key in sorted(direct_names)],
        }
    ]
    for key in sorted(reachable):
        dependencies.append(
            {
                "ref": refs[key],
                "dependsOn": [refs[child] for child in sorted(graph.get(key, set())) if child in refs],
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "cybersecurity-incident-registry",
                "version": app_version,
                "bom-ref": root_ref,
                "purl": root_ref,
            },
            "properties": [
                {"name": "cir:inventory-source", "value": "installed-environment"},
                {"name": "cir:resolution-status", "value": "resolved"},
                {"name": "cir:source-requirements-sha256", "value": hashlib.sha256(requirements_path.read_bytes()).hexdigest()},
                {"name": "cir:python-version", "value": sys.version.split()[0]},
                {"name": "cir:source-requirements", "value": requirements_path.name},
            ],
        },
        "components": components,
        "dependencies": dependencies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", default=str(PROJECT_ROOT / "requirements.txt"))
    parser.add_argument("--wheel-dir", default=None)
    parser.add_argument("--declared-only", action="store_true", help="inventory direct source declarations, explicitly unresolved; do not inspect installed packages")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "sbom/SBOM_CURRENT.cdx.json"))
    args = parser.parse_args()
    if args.declared_only and args.wheel_dir:
        parser.error("--declared-only cannot attach installed wheel evidence")

    requirements_path = Path(args.requirements).resolve()
    wheel_dir = Path(args.wheel_dir).resolve() if args.wheel_dir else None
    output = Path(args.output).resolve()
    sbom = build_declared_sbom(requirements_path) if args.declared_only else build_sbom(requirements_path, wheel_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output} with {len(sbom['components'])} Python components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
