#!/usr/bin/env python3
"""Stage and check immutable, same-run CIR training GitHub Release assets.

Italian is the only editorial master.  All authentic application screenshots
are shared; the English presentation is derived from that master.  The CI
seals each PPTX/PDF before this file ever runs.  This manifest ties the
published binary bytes to one commit and the original browser manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

REPO = 'desalvo/cybersecurity-incident-registry'
TAG_PREFIX = 'training-'
ASSETS = {
    'CIR_Operational_Training_Visual.pptx': ('visual', 'pptx_sha256'),
    'CIR_Operational_Training_Visual.pdf': ('visual', 'pdf_sha256'),
    'CIR_Operational_Training_Visual_EN.pptx': ('english', 'pptx_sha256'),
    'CIR_Operational_Training_Visual_EN.pdf': ('english', 'pdf_sha256'),
    'CIR_Operational_Training_IT.pptx': ('operational', 'sha256'),
    'CIR_UI_Screenshots.pdf': ('gallery', None),
}
RECEIPTS = {
    'visual': 'visual-training-receipt.json',
    'english': 'visual-training-en-receipt.json',
    'operational': 'presentation-receipt.json',
    'documentation': 'build-manifest.json',
}
MANIFEST = 'training-release-manifest.json'


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require_commit(commit: str) -> str:
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected a full, lowercase 40-digit Git commit SHA')
    return commit


def check_receipts(receipts: dict, commit: str, manifest_hash: str) -> None:
    visual, en, op = (receipts[key] for key in ('visual', 'english', 'operational'))
    for name, row in receipts.items():
        if row.get('source_commit') != commit:
            raise ValueError(f'{name} receipt belongs to another commit')
        if row.get('screenshot_manifest_sha256') != manifest_hash:
            raise ValueError(f'{name} receipt differs from the verified browser manifest')
    if visual.get('locale') != 'it' or en.get('locale') != 'en':
        raise ValueError('Italian master and English derivative must have explicit locales')
    if (visual.get('screenshots') != en.get('screenshots') or
            visual.get('slide_count') != en.get('slide_count') or
            visual.get('pdf_pages') != en.get('pdf_pages')):
        raise ValueError('English deck does not match the same-run Italian master')
    if not op.get('real_screenshots') or op.get('file') != 'CIR_Operational_Training_IT.pptx':
        raise ValueError('Operational deck does not certify the live screenshots')
    if not visual.get('pdf_screenshots_visually_verified'):
        raise ValueError('Visual PDF screenshot coverage has not been verified')


def stage(visual: Path, documentation: Path, screenshot_manifest: Path,
          output: Path, commit: str, repository: str = REPO) -> dict:
    """Validate inputs *before* creating output; never copy unverified files."""
    require_commit(commit)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid GitHub repository')
    screenshot_record = json.loads(screenshot_manifest.read_text(encoding='utf-8'))
    if screenshot_record.get('source_commit') != commit or not screenshot_record.get('screenshots'):
        raise ValueError('Missing or mismatched browser evidence')
    screenshot_sha = sha(screenshot_manifest)
    paths = {'visual': visual, 'english': visual, 'operational': documentation,
             'documentation': documentation}
    receipts = {key: json.loads((paths[key] / name).read_text(encoding='utf-8'))
                for key, name in RECEIPTS.items()}
    check_receipts(receipts, commit, screenshot_sha)
    doc_files = {row.get('file'): row.get('sha256') for row in receipts['documentation'].get('files', [])}
    if not doc_files.get('CIR_UI_Screenshots.pdf'):
        raise ValueError('Sealed documentation receipt does not include the screenshot gallery')
    records = {}
    sources = {}
    for filename, (kind, digest_key) in ASSETS.items():
        root = visual if kind in {'visual', 'english'} else documentation
        path = root / filename
        if not path.is_file() or path.is_symlink() or path.stat().st_size < 3000:
            raise ValueError('Missing verified training release asset: ' + str(path))
        digest = sha(path)
        if ((digest_key is not None and receipts[kind].get(digest_key) != digest) or
                (kind == 'gallery' and doc_files.get(filename) != digest)):
            raise ValueError('Training receipt checksum mismatch: ' + filename)
        sources[filename] = path
        records[filename] = {'sha256': digest, 'bytes': path.stat().st_size}
    for key, name in RECEIPTS.items():
        source = paths[key] / name
        sources[name] = source
        records[name] = {'sha256': sha(source), 'bytes': source.stat().st_size}
    tag = TAG_PREFIX + commit
    latest = f'https://github.com/{repository}/releases/latest/download/'
    permalink = f'https://github.com/{repository}/releases/download/{tag}/'
    record = {
        'schema_version': 1,
        'source_commit': commit,
        'release_tag': tag,
        'repository': repository,
        'italian_master': True,
        'english_derived_from_italian': True,
        'screenshot_manifest_sha256': screenshot_sha,
        'italian_slide_count': receipts['visual']['slide_count'],
        'english_slide_count': receipts['english']['slide_count'],
        'files': records,
        'stable_download_urls': {name: latest + name for name in ASSETS},
        'immutable_download_urls': {name: permalink + name for name in ASSETS},
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        shutil.copyfile(source, output / name)
    (output / MANIFEST).write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    verify_staged(output, commit)
    return record


def verify_staged(output: Path, commit: str) -> dict:
    require_commit(commit)
    manifest = json.loads((output / MANIFEST).read_text(encoding='utf-8'))
    if (manifest.get('schema_version') != 1 or manifest.get('source_commit') != commit or
            manifest.get('release_tag') != TAG_PREFIX + commit or
            manifest.get('italian_master') is not True or manifest.get('english_derived_from_italian') is not True or
            manifest.get('italian_slide_count') != manifest.get('english_slide_count')):
        raise ValueError('Invalid training release manifest')
    expected = set(ASSETS) | set(RECEIPTS.values())
    if set(manifest.get('files', {})) != expected:
        raise ValueError('Missing or unexpected release assets')
    for filename, meta in manifest['files'].items():
        path = output / filename
        if (Path(filename).name != filename or path.is_symlink() or not path.is_file() or
                sha(path) != meta.get('sha256') or path.stat().st_size != meta.get('bytes')):
            raise ValueError('Published release asset missing, stale or tampered: '+filename)
    screenshot_hash = manifest['screenshot_manifest_sha256']
    receipts = {key: json.loads((output / name).read_text(encoding='utf-8'))
                for key, name in RECEIPTS.items()}
    check_receipts(receipts, commit, screenshot_hash)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--visual-dir', type=Path)
    p.add_argument('--documentation-dir', type=Path)
    p.add_argument('--screenshot-manifest', type=Path)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--source-commit', required=True)
    p.add_argument('--repository', default=REPO)
    p.add_argument('--verify-only', action='store_true')
    a = p.parse_args()
    if a.verify_only:
        result = verify_staged(a.output_dir, a.source_commit)
    else:
        if not all((a.visual_dir, a.documentation_dir, a.screenshot_manifest)):
            p.error('Staging requires --visual-dir, --documentation-dir, and --screenshot-manifest')
        result = stage(a.visual_dir, a.documentation_dir, a.screenshot_manifest,
                       a.output_dir, a.source_commit, a.repository)
    print(json.dumps({'status': 'PASS', 'tag': result['release_tag'], 'files': len(result['files'])}, indent=2))


if __name__ == '__main__':
    main()
