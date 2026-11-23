#!/usr/bin/env python3
"""Bind PDFs, editable training deck and actual manual previews into one receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.presentation_evidence import MANUAL_PREVIEWS, PRESENTATION_FILE, PRESENTATION_RECEIPT
from scripts.ui_documentation_evidence import load_evidence, safe_artifact_path, sha256, validate_manuals


def finalize(manifest: Path, documentation_dir: Path, source_commit: str, *, metadata_root: Path = ROOT):
    documentation_dir = Path(documentation_dir).absolute()
    evidence = load_evidence(manifest, source_commit, metadata_root=metadata_root)
    manifest_hash = sha256(manifest)
    intermediate = validate_manuals(documentation_dir, source_commit, manifest_hash,
                                   metadata_root=metadata_root, require_presentation=False)
    receipt = {key: value for key, value in intermediate.items() if key != '_paths'}
    receipt['schema_version'] = 2
    receipt['presentation_receipt_file'] = PRESENTATION_RECEIPT
    receipt['files'] = list(receipt['files'])
    for name in sorted([PRESENTATION_FILE, PRESENTATION_RECEIPT, *MANUAL_PREVIEWS.values()]):
        path = safe_artifact_path(documentation_dir, name)
        receipt['files'].append({'file': name, 'sha256': sha256(path)})
    # Validate the full candidate before replacing the PDF-phase receipt. Any
    # stale metadata, incomplete deck or changed media leaves it untouched.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json',
                                         prefix='.cir-documentation-', dir=documentation_dir,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        validate_manuals(documentation_dir, source_commit, manifest_hash, metadata_root=metadata_root,
                         receipt_name=temporary.name, screenshot_evidence=evidence)
        temporary.replace(documentation_dir / 'build-manifest.json')
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot-manifest', required=True, type=Path)
    parser.add_argument('--documentation-dir', required=True, type=Path)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args(argv)
    try:
        result = finalize(args.screenshot_manifest, args.documentation_dir, args.source_commit)
    except (OSError, ValueError) as exc:
        print('Documentation bundle: FAIL: ' + str(exc), file=sys.stderr)
        return 1
    print(f"Documentation bundle: PASS ({len(result['files'])} verified artifacts; {result['source_commit']})")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
