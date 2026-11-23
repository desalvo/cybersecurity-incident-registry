#!/usr/bin/env python3
"""Resolve one build identity and optionally stamp a source/staging tree.

CI first emits outputs without changing the checkout. Each downstream job then
stamps that exact build explicitly; runtime and documentation use the files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from release_metadata import ReleaseMetadata, resolve_build, validate_version, write_build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--build", help="Reuse an already resolved YYYYMMDD build")
    parser.add_argument("--source-date-epoch", help="Reproducible POSIX timestamp; defaults to SOURCE_DATE_EPOCH")
    parser.add_argument("--expected-version", help="Reject checkout/workflow version mismatch")
    parser.add_argument("--write", action="store_true", help="Atomically stamp only BUILD in --root")
    parser.add_argument("--verify-installed-documentation", action="store_true",
                        help="After stamping, reject any incomplete or differently dated installed screenshot/manual batch")
    parser.add_argument("--github-output", type=Path, help="Append validated version/build job outputs")
    parser.add_argument("--field", choices=("json", "version", "build"), default="json")
    args = parser.parse_args(argv)
    if args.verify_installed_documentation and not args.write:
        parser.error("--verify-installed-documentation requires --write")
    try:
        version = validate_version((args.root / "VERSION").read_text(encoding="utf-8").strip())
        if args.expected_version is not None and args.expected_version != version:
            raise ValueError("Checkout VERSION differs from workflow release metadata")
        explicit = args.build if args.build is not None else os.environ.get("CIR_RELEASE_BUILD")
        # An empty Docker ARG means automatic date generation, never empty BUILD.
        explicit = explicit or None
        epoch = args.source_date_epoch if args.source_date_epoch is not None else os.environ.get("SOURCE_DATE_EPOCH")
        metadata = ReleaseMetadata(version, resolve_build(explicit, epoch or None))
        if args.write:
            write_build(args.root, metadata.build)
        if args.verify_installed_documentation:
            markers = (
                args.root / "app/static/help/ui-runtime/manifest.json",
                args.root / "docs/UI_SCREENSHOTS_SOURCE.json",
                args.root / "docs/UI_SCREENSHOTS_BUILD.json",
            )
            if any(path.exists() or path.is_symlink() for path in markers):
                from scripts.ui_documentation_evidence import validate_installed_documentation
                validate_installed_documentation(args.root)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write(f"version={metadata.version}\nbuild={metadata.build}\n")
        print(json.dumps(metadata.as_dict()) if args.field == "json" else getattr(metadata, args.field))
    except (OSError, ValueError) as exc:
        print(f"Release metadata: FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
