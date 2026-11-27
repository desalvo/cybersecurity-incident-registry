#!/usr/bin/env python3
"""Create a portable, reproducible CIR cumulative source archive.

The tar root is *always* cybersecurity-incident-registry-0.10.0-1/, no
matter how the checkout/staging directory is named.  Local Git metadata,
virtual environments and caches are never packaged.

Examples:
  python scripts/package_cumulative.py --source . --output ../cir.tar.zst
  python scripts/package_cumulative.py --source . --output ../cir.tar.xz --compression xz --level 6
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

CANONICAL_ROOT = "cybersecurity-incident-registry-0.10.0-1"
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "node_modules"}
EXTERNAL_RELEASE_ASSETS = {
    'docs/CIR_UI_Screenshots.pdf',
    'docs/presentation/CIR_Operational_Training_IT.pptx',
    'docs/presentation/CIR_Operational_Training_Visual.pptx',
    'docs/presentation/CIR_Operational_Training_Visual.pdf',
    'docs/presentation/CIR_Operational_Training_Visual_EN.pptx',
    'docs/presentation/CIR_Operational_Training_Visual_EN.pdf',
}
SKIP_FILES = {".env", ".coverage", "coverage.xml"}


def included(source: Path):
    paths = [source]
    for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in dirs + sorted(files):
            path = Path(root) / name
            if path.is_symlink():
                raise ValueError(f"Refusing symlink in cumulative package: {path}")
            if path.is_file() and (name in SKIP_FILES or name.endswith((".pyc", ".pyo")) or
                                   path.relative_to(source).as_posix() in EXTERNAL_RELEASE_ASSETS):
                continue
            if path.is_dir() or path.is_file():
                paths.append(path)
    return paths


def open_decompressor(path: Path, compression: str):
    cmd = ["zstd", "-dc", str(path)] if compression == "zstd" else ["xz", "-dc", str(path)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)


def make_archive(source: Path, output: Path, compression: str, level: int):
    if compression == "zstd":
        if not 1 <= level <= 22:
            raise ValueError("zstd level must be between 1 and 22")
        cmd = ["zstd", "-q", "-T2", f"-{level}"]
        if level > 19:
            cmd.insert(2, "--ultra")
    else:
        if not 0 <= level <= 9:
            raise ValueError("xz level must be between 0 and 9")
        cmd = ["xz", f"-{level}", "-T2", "-c"]
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".building")
    temp.unlink(missing_ok=True)
    paths = included(source)
    try:
        with temp.open("wb") as target:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=target)
            assert p.stdin is not None
            try:
                with tarfile.open(mode="w|", fileobj=p.stdin, format=tarfile.PAX_FORMAT) as tar:
                    for path in paths:
                        relative = path.relative_to(source)
                        name = CANONICAL_ROOT if path == source else f"{CANONICAL_ROOT}/{relative.as_posix()}"
                        info = tar.gettarinfo(str(path), arcname=name)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        info.pax_headers = {}
                        if path.is_file():
                            with path.open("rb") as fd:
                                tar.addfile(info, fd)
                        else:
                            tar.addfile(info)
            finally:
                p.stdin.close()
            if p.wait() != 0:
                raise RuntimeError("compression failed")
        verify(source, temp, compression)
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return {"output": str(output), "compression": compression, "level": level,
            "entries": len(paths), "size_bytes": output.stat().st_size,
            "sha256": hashlib.file_digest(output.open("rb"), "sha256").hexdigest(),
            "tar_root": CANONICAL_ROOT}


def verify(source: Path, archive: Path, compression: str):
    expected = {CANONICAL_ROOT if p == source else f"{CANONICAL_ROOT}/{p.relative_to(source).as_posix()}": p for p in included(source)}
    seen = set()
    p = open_decompressor(archive, compression)
    assert p.stdout is not None
    try:
        with tarfile.open(mode="r|", fileobj=p.stdout) as tar:
            for member in tar:
                name = member.name.rstrip("/")
                parts = PurePosixPath(name).parts
                if name not in expected or name in seen or not parts or parts[0] != CANONICAL_ROOT or ".." in parts or ".git" in parts:
                    raise ValueError(f"Unexpected, unsafe or duplicated archive entry: {name}")
                src = expected[name]
                if member.isfile() != src.is_file() or member.isdir() != src.is_dir():
                    raise ValueError(f"Archive entry type differs from source: {name}")
                if member.isfile():
                    stream = tar.extractfile(member)
                    assert stream is not None
                    with src.open("rb") as original:
                        while True:
                            a, b = stream.read(1024 * 1024), original.read(1024 * 1024)
                            if a != b:
                                raise ValueError(f"Archive payload differs from source: {name}")
                            if not a:
                                break
                seen.add(name)
        if seen != set(expected):
            raise ValueError(f"Archive inventory mismatch: missing={sorted(set(expected)-seen)[:6]}")
    finally:
        p.stdout.close()
        result = p.wait()
        if result != 0:
            raise RuntimeError(f"Decompressor exited with status {result}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compression", choices=["zstd", "xz"], default="zstd")
    parser.add_argument("--level", type=int)
    parser.add_argument("--report", type=Path)
    opts = parser.parse_args()
    source = opts.source.resolve()
    output = opts.output.resolve()
    if not source.is_dir() or not (source / "VERSION").is_file():
        parser.error("--source must point to the CIR project root (containing VERSION)")
    if output == source or source in output.parents:
        parser.error("output must be outside the source tree")
    level = opts.level if opts.level is not None else (19 if opts.compression == "zstd" else 6)
    report = make_archive(source, output, opts.compression, level)
    if opts.report:
        opts.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
