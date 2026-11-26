#!/usr/bin/env python3
"""Verify the committed visual-training bundle without pretending it is this PR's run.

The documentation PR contains browser evidence captured on its source-commit
workflow, whereas pull_request CI checks out a different merge commit.  A
published bundle is valid only when the original/installed manifests and
sealed presentation receipt agree on source identity, image SHA-256 and exact
PPTX/PDF bytes.  This check never substitutes GITHUB_SHA for source_commit.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from pathlib import PurePosixPath

BASE_SLIDES = 97  # 94 content + 1 appendix divider + 2 terminal previews
GALLERY_FIRST_SLIDE = 96  # gallery starts immediately after slide 95 divider
HIDDEN_GALLERY_IDS = frozenset({'classic-registry-desktop'})
MAX_SCREENSHOTS = 80


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Missing, linked or oversized visual-training evidence: ' + str(path))
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Visual-training evidence must be a JSON object: ' + str(path))
    return data


def screenshot_rows(data: dict, label: str) -> list[tuple[str, str]]:
    rows = data.get('screenshots')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_SCREENSHOTS:
        raise ValueError('Missing or excessive screenshot records in ' + label)
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('sha256'), str):
            raise ValueError('Invalid screenshot record in ' + label)
        ident, checksum = row['id'], row['sha256']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', ident) or not re.fullmatch(r'[a-f0-9]{64}', checksum):
            raise ValueError('Invalid screenshot identity in ' + label)
        result.append((ident, checksum))
    if len({ident for ident, _ in result}) != len(result):
        raise ValueError('Duplicate screenshot IDs in ' + label)
    return result



def validate_published_pdf_preview(original: dict, installed: dict) -> dict:
    """Audit sealed PDF-preview metadata without requiring CI scratch files.

    The same-run verifier already checked both actual PDF and raster bytes and
    required the raster on the dedicated slide. A publication PR preserves the
    SHA-bound source manifest and the exact deck, but does not publish temporary
    generated-mapped-example.pdf/.png. The raster hash must still be checked
    against the PPTX by the visual verifier on every PR.
    """
    preview = original.get('generated_pdf_preview')
    if not isinstance(preview, dict) or preview != installed.get('generated_pdf_preview'):
        raise ValueError('Published generated PDF preview differs from the sealed source manifest')
    if preview.get('source_kind') != 'cir-generated-mapped-acroform':
        raise ValueError('Published generated PDF preview has invalid source kind')
    for key, hash_key, extension in (('pdf_file', 'pdf_sha256', '.pdf'),
                                     ('png_file', 'png_sha256', '.png')):
        name, checksum = preview.get(key), preview.get(hash_key)
        if (not isinstance(name, str) or not name.endswith(extension) or
                '\\' in name or ':' in name or
                PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or
                not isinstance(checksum, str) or
                not re.fullmatch(r'[a-f0-9]{64}', checksum)):
            raise ValueError('Published PDF preview has invalid path or SHA-256: ' + key)
    if preview['pdf_file'] == preview['png_file']:
        raise ValueError('Published PDF preview image and source must be distinct files')
    return preview


def check_published_receipt(root: Path, pptx: Path, pdf: Path, manifest: Path, receipt: Path) -> int:
    """Return exact expected slide count; fail closed on any inconsistent evidence."""
    root = root.resolve()
    original_path = root / 'docs/UI_SCREENSHOTS_SOURCE.json'
    build_path = root / 'docs/UI_SCREENSHOTS_BUILD.json'
    original, build = read_json(original_path), read_json(build_path)
    installed, seal = read_json(manifest), read_json(receipt)
    source_commit = seal.get('source_commit')
    if not isinstance(source_commit, str) or not re.fullmatch(r'[a-fA-F0-9]{40}', source_commit):
        raise ValueError('Invalid published screenshot source commit')
    for label, record in (('original', original), ('installed', installed), ('build', build)):
        if record.get('source_commit') != source_commit:
            raise ValueError(f'Published {label} manifest uses a different source commit')
    if (original.get('source_kind') != 'real-application-browser' or
            installed.get('source_kind') != 'real-application-browser' or
            original.get('data_provenance') != 'isolated-synthetic-fixture' or
            installed.get('data_provenance') != 'isolated-synthetic-fixture'):
        raise ValueError('Published screenshots lack real-browser isolated-fixture provenance')
    for record, label in ((original, 'original'), (installed, 'installed'), (seal, 'receipt')):
        if str(record.get('build')) != str(seal.get('build')):
            raise ValueError(f'Published {label} evidence has inconsistent build identity')
    if seal.get('screenshot_manifest_sha256') != sha256(original_path):
        raise ValueError('Original browser manifest hash differs from presentation receipt')
    if build.get('installed_manifest_sha256') != sha256(manifest):
        raise ValueError('Installed browser manifest hash differs from documentation build')
    validate_published_pdf_preview(original, installed)
    original_rows = screenshot_rows(original, 'original manifest')
    installed_rows = screenshot_rows(installed, 'installed manifest')
    receipt_rows = screenshot_rows(seal, 'presentation receipt')
    if original_rows != installed_rows or original_rows != receipt_rows:
        raise ValueError('Published screenshots differ from original, installed or sealed capture order')
    for row in installed['screenshots']:
        name = row.get('file')
        ident = row['id']
        if (not isinstance(name, str) or name not in (ident + '.png', ident + '.jpg')):
            raise ValueError('Published screenshot path is not canonical: ' + ident)
        image = manifest.parent / name
        if not image.is_file() or image.is_symlink() or sha256(image) != row['sha256']:
            raise ValueError('Published screenshot bytes differ from sealed capture: ' + ident)
    expected = BASE_SLIDES + sum(ident not in HIDDEN_GALLERY_IDS for ident, _ in installed_rows)
    if (seal.get('screenshot_gallery_first_slide') != GALLERY_FIRST_SLIDE or
            seal.get('slide_count') != expected or seal.get('pdf_pages') != expected or
            seal.get('pdf_screenshots_visually_verified') != expected - BASE_SLIDES):
        raise ValueError('Published visual-training gallery has incorrect slide/page coverage')
    for path, filename_key, checksum_key in ((pptx, 'pptx_file', 'pptx_sha256'),
                                             (pdf, 'pdf_file', 'pdf_sha256')):
        if path.name != seal.get(filename_key) or not path.is_file() or path.is_symlink():
            raise ValueError('Published visual-training artifact missing or renamed')
        if sha256(path) != seal.get(checksum_key):
            raise ValueError('Published visual-training artifact hash differs from sealed verification')
    return expected


def expected_visual_slides(root: Path, pptx: Path, pdf: Path) -> int:
    """Allow 97 fixed slides (with divider/previews), plus a sealed screenshot gallery."""
    receipt = root / 'docs/presentation/visual-training-receipt.json'
    manifest = root / 'app/static/help/ui-runtime/manifest.json'
    if not receipt.exists() and not manifest.exists():
        # The checked-in editorial presentation retains every previously
        # captured application screenshot (except the classical UI) even
        # before CI attaches the new manifest and the publication receipt.
        archive = root / 'app/static/help/ui-runtime'
        if archive.is_dir() and pptx.is_file() and pdf.is_file():
            preserved = sum(p.is_file() and p.suffix.lower() in {'.png', '.jpg'}
                            and p.stem not in HIDDEN_GALLERY_IDS for p in archive.iterdir())
            return BASE_SLIDES + preserved
        return BASE_SLIDES
    if not receipt.is_file() or not manifest.is_file():
        raise ValueError('Unsealed browser screenshots found in current visual-training bundle')
    return check_published_receipt(root, pptx, pdf, manifest, receipt)
