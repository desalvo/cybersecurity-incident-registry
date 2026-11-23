#!/usr/bin/env python3
"""Render the shipped console Template offline, with strict parameter validation.

The Template is JSON (also valid YAML), so this helper needs only the standard
library. It never contacts a cluster, generates a credential, or deploys an image.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PARAMETER = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


def render_template(parameters: dict[str, str], template: dict | None = None) -> dict:
    template = template or json.loads((ROOT / "openshift/cir-template.yaml").read_text())
    declared = {row["name"]: row for row in template["parameters"]}
    unknown = set(parameters) - set(declared)
    if unknown:
        raise ValueError("Unknown template parameters: " + ", ".join(sorted(unknown)))
    values = {key: str(parameters.get(key, row.get("value", ""))) for key, row in declared.items()}
    for key, row in declared.items():
        if row.get("required") and not values[key]:
            raise ValueError(f"Required parameter missing: {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", values["IMAGE_SHA256"]):
        raise ValueError("IMAGE_SHA256 must be the approved 64-character lowercase OCI index digest")
    if not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*", values["IMAGE_REPOSITORY"]):
        raise ValueError("IMAGE_REPOSITORY must contain a repository without a tag or digest")
    for key in ("NAME", "EXISTING_SECRET"):
        if len(values[key]) > 52 or not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", values[key]):
            raise ValueError(f"{key} must be a DNS label of at most 52 characters")
    if not re.fullmatch(r"[1-9][0-9]*(?:Ki|Mi|Gi|Ti)", values["VOLUME_SIZE"]):
        raise ValueError("VOLUME_SIZE must be a positive Kubernetes storage quantity")
    if values["ROUTE_HOST"] and not re.fullmatch(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?", values["ROUTE_HOST"]):
        raise ValueError("ROUTE_HOST must be a DNS hostname")
    for cidr in filter(None, (item.strip() for item in values["TRUSTED_PROXY_CIDRS"].split(","))):
        network = ipaddress.ip_network(cidr, strict=True)
        if network.prefixlen == 0:
            raise ValueError("Trusted proxies cannot include every address")

    def substitute(value):
        if isinstance(value, dict):
            return {key: substitute(item) for key, item in value.items()}
        if isinstance(value, list):
            return [substitute(item) for item in value]
        if isinstance(value, str):
            def replacement(match):
                key = match.group(1)
                if key not in values:
                    raise ValueError(f"Undeclared parameter: {key}")
                return values[key]
            return PARAMETER.sub(replacement, value)
        return value

    return {"apiVersion": "v1", "kind": "List", "items": substitute(template["objects"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parameter", "-p", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parameters = {}
    for item in args.parameter:
        key, separator, value = item.partition("=")
        if not separator or key in parameters:
            parser.error("Parameters require NAME=VALUE and cannot repeat")
        parameters[key] = value
    try:
        rendered = render_template(parameters)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(rendered, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
