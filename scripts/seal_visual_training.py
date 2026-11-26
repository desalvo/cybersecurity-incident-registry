#!/usr/bin/env python3
"""Seal same-run, PDF-rendered screenshot evidence for the publish PR."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
try:
    from scripts.published_visual_training import BASE_SLIDES, HIDDEN_GALLERY_IDS
except ModuleNotFoundError:
    from published_visual_training import BASE_SLIDES, HIDDEN_GALLERY_IDS


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(pptx: Path, pdf: Path, manifest: Path, verification: Path, output: Path):
    data = json.loads(manifest.read_text(encoding='utf8'))
    checked = json.loads(verification.read_text(encoding='utf8'))
    screens = data['screenshots']
    if (checked.get('status') != 'PASS' or
            checked.get('verified_browser_screenshots') != len(screens) or
            checked.get('pdf_screenshots_visually_verified') != sum(row['id'] not in HIDDEN_GALLERY_IDS for row in screens) or
            checked.get('slides') != checked.get('pdf_pages') or
            checked.get('slides') != BASE_SLIDES + sum(row['id'] not in HIDDEN_GALLERY_IDS for row in screens)):
        raise ValueError('Same-run PPTX/PDF screenshot coverage is not fully verified')
    record = {
        'schema_version': 1,
        'source_commit': data['source_commit'], 'build': str(data['build']),
        'screenshot_manifest_sha256': sha(manifest),
        'screenshots': [{'id': row['id'], 'sha256': row['sha256']} for row in screens],
        'pptx_file': 'CIR_Operational_Training_Visual.pptx', 'pptx_sha256': sha(pptx),
        'pdf_file': 'CIR_Operational_Training_Visual.pdf', 'pdf_sha256': sha(pdf),
        'slide_count': checked['slides'], 'pdf_pages': checked['pdf_pages'],
        'pdf_screenshots_visually_verified': checked['pdf_screenshots_visually_verified'],
        'screenshot_gallery_first_slide': BASE_SLIDES + 1,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return record


def main():
    p = argparse.ArgumentParser()
    for name in ('pptx', 'pdf', 'manifest', 'verification', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    args=p.parse_args()
    result=seal(args.pptx,args.pdf,args.manifest,args.verification,args.output)
    print('Visual training evidence sealed:', result['slide_count'], 'slides')

if __name__ == '__main__':
    main()
