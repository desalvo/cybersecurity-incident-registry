#!/usr/bin/env python3
"""Record an already-promoted immutable OCI index digest in release metadata.

This script is intentionally deterministic and performs no registry operations.
The CI pipeline must call it only after the candidate digest has passed all gates,
has been promoted, and the published tag has been re-inspected successfully.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE_NAME = "desalvo/cybersecurity-incident-registry"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*[A-Za-z0-9]$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, help="OCI repository without tag or digest")
    parser.add_argument("--digest", required=True, help="Immutable OCI index digest (sha256:...)")
    return parser.parse_args()


def validate(repository: str, digest: str) -> None:
    if not repository or "://" in repository or "@" in repository or repository.endswith("/"):
        raise ValueError(f"invalid OCI repository: {repository!r}")
    # A registry host may contain a port; reject only an apparent tag after the final slash.
    tail = repository.rsplit("/", 1)[-1]
    if ":" in tail:
        raise ValueError(f"repository must not include a tag: {repository!r}")
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError(f"invalid OCI repository: {repository!r}")
    if not DIGEST_RE.fullmatch(digest):
        raise ValueError(f"invalid OCI digest: {digest!r}")


def update_kustomization(repository: str, digest: str) -> None:
    path = ROOT / "k8s" / "kustomization.yaml"
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        images_idx = next(i for i, line in enumerate(lines) if line.strip() == "images:")
    except StopIteration as exc:
        raise RuntimeError("k8s/kustomization.yaml has no images section") from exc

    start = None
    end = len(lines)
    for i in range(images_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("- name:"):
            if start is None and stripped.split(":", 1)[1].strip() == DEFAULT_IMAGE_NAME:
                start = i
                continue
            if start is not None:
                end = i
                break
        elif start is not None and lines[i] and not lines[i].startswith((" ", "\t")):
            end = i
            break
    if start is None:
        raise RuntimeError(f"Kustomize image entry not found: {DEFAULT_IMAGE_NAME}")

    replacement = [
        f"- name: {DEFAULT_IMAGE_NAME}",
        f"  newName: {repository}",
        f"  digest: {digest}",
    ]
    lines[start:end] = replacement
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repository = args.repository.strip()
    digest = args.digest.strip()
    try:
        validate(repository, digest)
        immutable = f"{repository}@{digest}"
        (ROOT / "PRODUCTION_IMAGE_DIGEST").write_text(immutable + "\n", encoding="utf-8")
        update_kustomization(repository, digest)
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(immutable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
