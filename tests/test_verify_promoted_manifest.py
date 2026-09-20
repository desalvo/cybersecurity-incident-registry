import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_promoted_manifest.py"
A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
C = "sha256:" + "c" * 64
D = "sha256:" + "d" * 64
E = "sha256:" + "e" * 64


def _index(amd64=A, arm64=B, attest_amd=C, attest_arm=D, extra=None):
    manifests = [
        {"digest": amd64, "platform": {"os": "linux", "architecture": "amd64"}},
        {"digest": arm64, "platform": {"os": "linux", "architecture": "arm64"}},
        {"digest": attest_amd, "platform": {"os": "unknown", "architecture": "unknown"}, "annotations": {"vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": amd64}},
        {"digest": attest_arm, "platform": {"os": "unknown", "architecture": "unknown"}, "annotations": {"vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": arm64}},
    ]
    if extra:
        manifests.append(extra)
    return {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": manifests}


def _run(tmp_path, candidate, published):
    a = tmp_path / "candidate.json"
    b = tmp_path / "published.json"
    a.write_text(json.dumps(candidate), encoding="utf-8")
    b.write_text(json.dumps(published), encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), str(a), str(b)], text=True, capture_output=True)


def test_accepts_same_child_descriptors_even_if_top_level_serialization_differs(tmp_path):
    candidate = _index()
    published = dict(_index())
    published["annotations"] = {"registry-retagged": "true"}
    published["manifests"] = list(reversed(published["manifests"]))
    result = _run(tmp_path, candidate, published)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_rejects_changed_platform_manifest(tmp_path):
    result = _run(tmp_path, _index(), _index(amd64=E))
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_rejects_changed_attestation_descriptor(tmp_path):
    result = _run(tmp_path, _index(), _index(attest_amd=E))
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_rejects_unexpected_executable_platform(tmp_path):
    extra = {"digest": E, "platform": {"os": "linux", "architecture": "s390x"}}
    result = _run(tmp_path, _index(), _index(extra=extra))
    assert result.returncode == 1
    assert "unexpected executable platform" in result.stdout
