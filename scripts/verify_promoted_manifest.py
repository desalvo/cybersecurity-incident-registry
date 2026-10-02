#!/usr/bin/env python3
"""Verify that a promoted OCI index preserves the Trivy-approved descriptors.

A registry-side retag performed with ``docker buildx imagetools create`` can
serialize a new top-level OCI index and therefore produce a different index
digest.  Promotion is safe only when the immutable child descriptors are
unchanged.  This verifier compares the complete manifest descriptor set and
requires exactly the expected executable Linux platforms.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
EXPECTED_PLATFORMS = {("linux", "amd64"), ("linux", "arm64")}
ATTESTATION_TYPE = "attestation-manifest"
REFERENCE_TYPE = "vnd.docker.reference.type"
REFERENCE_DIGEST = "vnd.docker.reference.digest"


def _load_index(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid OCI index JSON: {exc}") from exc
    manifests = payload.get("manifests")
    if not isinstance(manifests, list):
        raise ValueError(f"{path}: expected OCI/Docker multi-arch index")
    return payload


def _descriptor_fingerprint(path: Path) -> tuple[frozenset[tuple[str, str, str, str, str]], dict[tuple[str, str], str]]:
    payload = _load_index(path)
    fingerprints: set[tuple[str, str, str, str, str]] = set()
    platforms: dict[tuple[str, str], str] = {}

    for item in payload["manifests"]:
        if not isinstance(item, dict):
            raise ValueError(f"{path}: malformed manifest descriptor")
        digest = item.get("digest", "")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(f"{path}: invalid manifest digest {digest!r}")

        platform = item.get("platform") or {}
        if not isinstance(platform, dict):
            raise ValueError(f"{path}: malformed platform descriptor for {digest}")
        os_name = str(platform.get("os") or "")
        architecture = str(platform.get("architecture") or "")
        key = (os_name, architecture)

        annotations = item.get("annotations") or {}
        if not isinstance(annotations, dict):
            raise ValueError(f"{path}: malformed annotations for {digest}")
        reference_type = str(annotations.get(REFERENCE_TYPE) or "")
        reference_digest = str(annotations.get(REFERENCE_DIGEST) or "")

        if key in EXPECTED_PLATFORMS:
            if key in platforms:
                raise ValueError(f"{path}: duplicate platform descriptor for {key}")
            platforms[key] = digest
        elif key == ("unknown", "unknown"):
            if reference_type != ATTESTATION_TYPE:
                raise ValueError(f"{path}: unknown/unknown descriptor is not an attestation: {digest}")
            if not SHA256_RE.fullmatch(reference_digest):
                raise ValueError(f"{path}: attestation {digest} has invalid reference digest {reference_digest!r}")
        else:
            raise ValueError(f"{path}: unexpected executable platform {key} for {digest}")

        fingerprints.add((digest, os_name, architecture, reference_type, reference_digest))

    if set(platforms) != EXPECTED_PLATFORMS:
        raise ValueError(
            f"{path}: expected exactly linux/amd64 and linux/arm64, got {sorted(platforms)}"
        )

    platform_digests = set(platforms.values())
    for digest, os_name, architecture, reference_type, reference_digest in fingerprints:
        if (os_name, architecture) == ("unknown", "unknown") and reference_digest not in platform_digests:
            raise ValueError(
                f"{path}: attestation {digest} references non-platform digest {reference_digest}"
            )

    return frozenset(fingerprints), platforms


def verify(candidate_path: Path, published_path: Path) -> None:
    candidate_descriptors, candidate_platforms = _descriptor_fingerprint(candidate_path)
    published_descriptors, published_platforms = _descriptor_fingerprint(published_path)

    if candidate_platforms != published_platforms:
        raise ValueError(
            "Published platform manifests differ from the Trivy-approved candidate: "
            f"candidate={candidate_platforms}, published={published_platforms}"
        )
    if candidate_descriptors != published_descriptors:
        raise ValueError(
            "Published OCI child descriptors differ from the Trivy-approved candidate"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("published", type=Path)
    args = parser.parse_args()
    try:
        verify(args.candidate, args.published)
    except ValueError as exc:
        print(f"Promoted manifest verification: FAIL: {exc}")
        return 1
    print("Promoted manifest verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
