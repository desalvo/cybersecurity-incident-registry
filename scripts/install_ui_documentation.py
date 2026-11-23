#!/usr/bin/env python3
"""Install validated same-run UI documentation into the candidate build tree."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from ui_documentation_evidence import load_evidence, sha256, validate_manuals
from scripts.presentation_evidence import PRESENTATION_ARTIFACTS

ROOT = Path(__file__).resolve().parents[1]


def install(manifest: Path, documentation_dir: Path, source_commit: str, root: Path = ROOT):
    # Validate the entire batch before changing any candidate files.
    evidence = load_evidence(manifest, source_commit, metadata_root=root)
    manuals = validate_manuals(documentation_dir, source_commit, sha256(manifest),
                               metadata_root=root, screenshot_evidence=evidence)
    static = root / 'app/static/help/ui-runtime'
    docs = root / 'docs'
    static.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    normalized = {k: v for k, v in evidence.items() if k != '_paths'}
    normalized['screenshots'] = [dict(row) for row in evidence['screenshots']]
    for row in normalized['screenshots']:
        source = evidence['_paths'][row['id']]
        # Install only validated files with deterministic names; no directory
        # or file path from a downloaded artifact controls the destination.
        name = row['id'] + '.png'
        shutil.copyfile(source, static / name)
        row['file'] = name
    (static / 'manifest.json').write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + '\n')
    for name, source in manuals['_paths'].items():
        destination = docs / 'presentation' / name if name in PRESENTATION_ARTIFACTS else docs / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    receipt = {k: v for k, v in manuals.items() if k != '_paths'}
    # Keep the original artifact manifest: normalization above changes its path
    # fields, while the PDF receipt binds the exact original manifest bytes.
    shutil.copyfile(manifest, docs / 'UI_SCREENSHOTS_SOURCE.json')
    receipt['source_manifest_file'] = 'UI_SCREENSHOTS_SOURCE.json'
    receipt['installed_manifest_sha256'] = sha256(static / 'manifest.json')
    (docs / 'UI_SCREENSHOTS_BUILD.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(f'Installed real UI screenshots, manuals, brochures and editable presentation for {source_commit}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--documentation-dir', required=True, type=Path)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    install(args.manifest, args.documentation_dir, args.source_commit)


if __name__ == '__main__':
    main()
