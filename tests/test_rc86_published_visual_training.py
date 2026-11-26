"""RC86: documentation PRs must audit sealed evidence, not assume 88 slides."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.published_visual_training import (BASE_SLIDES, check_published_receipt,
                                               expected_visual_slides, sha256)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


@pytest.fixture
def published(tmp_path):
    root = tmp_path
    docs = root / 'docs'
    runtime = root / 'app/static/help/ui-runtime'
    presentation = docs / 'presentation'
    runtime.mkdir(parents=True)
    presentation.mkdir(parents=True)
    source_commit = 'a' * 40
    img = b'isolated-synthetic-fixture screenshot source bytes'
    (runtime / 'example-capture.png').write_bytes(img)
    row = {'id': 'example-capture', 'sha256': hashlib.sha256(img).hexdigest()}
    preview = {'source_kind': 'cir-generated-mapped-acroform',
               'pdf_file': 'screenshots/generated-mapped-example.pdf',
               'pdf_sha256': 'b' * 64,
               'png_file': 'screenshots/generated-mapped-example.png',
               'png_sha256': 'c' * 64}
    original = {'source_kind': 'real-application-browser',
                'data_provenance': 'isolated-synthetic-fixture',
                'source_commit': source_commit, 'build': '20261126',
                'screenshots': [{**row, 'file': 'capture.png'}],
                'generated_pdf_preview': preview}
    installed = {**original, 'screenshots': [{**row, 'file': 'example-capture.png'}]}
    source_path = docs / 'UI_SCREENSHOTS_SOURCE.json'
    manifest_path = runtime / 'manifest.json'
    write_json(source_path, original)
    write_json(manifest_path, installed)
    write_json(docs / 'UI_SCREENSHOTS_BUILD.json', {
        'source_commit': source_commit,
        'installed_manifest_sha256': sha256(manifest_path),
    })
    pptx = presentation / 'CIR_Operational_Training_Visual.pptx'
    pdf = presentation / 'CIR_Operational_Training_Visual.pdf'
    pptx.write_bytes(b'sealed demo PPTX')
    pdf.write_bytes(b'sealed demo PDF')
    receipt_path = presentation / 'visual-training-receipt.json'
    write_json(receipt_path, {
        'schema_version': 1, 'source_commit': source_commit, 'build': '20261126',
        'screenshot_manifest_sha256': sha256(source_path),
        'screenshots': [row], 'pptx_file': pptx.name, 'pptx_sha256': sha256(pptx),
        'pdf_file': pdf.name, 'pdf_sha256': sha256(pdf),
        'slide_count': BASE_SLIDES + 1, 'pdf_pages': BASE_SLIDES + 1,
        'pdf_screenshots_visually_verified': 1,
        'screenshot_gallery_first_slide': BASE_SLIDES + 1,
    })
    return root, pptx, pdf, manifest_path, receipt_path


def test_source_edition_keeps_base_without_archived_gallery(tmp_path):
    assert expected_visual_slides(tmp_path, tmp_path / 'example.pptx',
                                  tmp_path / 'example.pdf') == BASE_SLIDES


def test_published_gallery_count_is_derived_from_sealed_capture(published, monkeypatch):
    root, deck, pdf, manifest, receipt = published
    # A PR checkout is not the workflow that acquired the original screenshots.
    monkeypatch.setenv('GITHUB_SHA', 'b' * 40)
    monkeypatch.setenv('CIR_RELEASE_BUILD', '99999999')
    assert expected_visual_slides(root, deck, pdf) == BASE_SLIDES + 1
    assert check_published_receipt(root, deck, pdf, manifest, receipt) == BASE_SLIDES + 1


@pytest.mark.parametrize('mutation', [
    'modified_image', 'modified_deck', 'modified_pdf', 'wrong_slide_count',
    'wrong_gallery_start', 'wrong_pdf_coverage', 'wrong_receipt_source',
    'wrong_original_manifest_hash', 'wrong_installed_manifest_hash',
    'wrong_capture_provenance', 'wrong_capture_order',
    'wrong_pdf_preview_metadata',
])
def test_published_gallery_rejects_inconsistent_or_tampered_evidence(published, mutation):
    root, deck, pdf, manifest, receipt = published
    data = json.loads(receipt.read_text())
    if mutation == 'modified_image':
        (manifest.parent / 'example-capture.png').write_bytes(b'changed screenshot')
    elif mutation == 'modified_deck':
        deck.write_bytes(b'changed PPTX')
    elif mutation == 'modified_pdf':
        pdf.write_bytes(b'changed PDF')
    elif mutation == 'wrong_slide_count':
        data['slide_count'] = BASE_SLIDES
    elif mutation == 'wrong_gallery_start':
        data['screenshot_gallery_first_slide'] = BASE_SLIDES
    elif mutation == 'wrong_pdf_coverage':
        data['pdf_screenshots_visually_verified'] = 0
    elif mutation == 'wrong_receipt_source':
        data['source_commit'] = 'f' * 40
    elif mutation == 'wrong_original_manifest_hash':
        data['screenshot_manifest_sha256'] = '0' * 64
    elif mutation == 'wrong_installed_manifest_hash':
        build_path = root / 'docs/UI_SCREENSHOTS_BUILD.json'
        metadata = json.loads(build_path.read_text())
        metadata['installed_manifest_sha256'] = '0' * 64
        write_json(build_path, metadata)
    elif mutation == 'wrong_capture_provenance':
        installed = json.loads(manifest.read_text())
        installed['data_provenance'] = 'unverified-fixture'
        write_json(manifest, installed)
        build_path = root / 'docs/UI_SCREENSHOTS_BUILD.json'
        metadata = json.loads(build_path.read_text())
        metadata['installed_manifest_sha256'] = sha256(manifest)
        write_json(build_path, metadata)
    elif mutation == 'wrong_pdf_preview_metadata':
        installed = json.loads(manifest.read_text())
        installed['generated_pdf_preview']['png_sha256'] = 'f' * 64
        write_json(manifest, installed)
        build_path = root / 'docs/UI_SCREENSHOTS_BUILD.json'
        metadata = json.loads(build_path.read_text())
        metadata['installed_manifest_sha256'] = sha256(manifest)
        write_json(build_path, metadata)
    elif mutation == 'wrong_capture_order':
        data['screenshots'] = [{'id': 'another-capture', 'sha256': 'f' * 64}]
    write_json(receipt, data)
    with pytest.raises(ValueError):
        expected_visual_slides(root, deck, pdf)


def test_unsealed_gallery_is_not_accepted(published):
    root, deck, pdf, manifest, receipt = published
    receipt.unlink()
    with pytest.raises(ValueError, match='Unsealed'):
        expected_visual_slides(root, deck, pdf)


def test_visual_verifier_has_separate_published_and_same_run_modes():
    from scripts.verify_visual_training_rc64 import run_check
    assert 'published_ci_images' in run_check.__code__.co_varnames
    source = (Path(__file__).resolve().parents[1] /
              'scripts/verify_visual_training_rc64.py').read_text()
    assert 'if require_ci_images:' in source
    assert 'if strict_images' in source
    assert '--published-receipt' in source
    assert 'Appendice screenshot CI incompleta' in source
    assert 'verified_native_zoom' in source
