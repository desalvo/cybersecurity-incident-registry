"""RC67: same-run CI category palette must replace editorial fallback on slide 70.

The optional end-to-end builder test uses deliberately synthetic, disposable
raster test fixtures. It never treats them as production screenshots and never
packages them into the release presentation.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'scripts/build_training_visual_rc64.js'
VERIFIER = ROOT / 'scripts/verify_visual_training_rc64.py'
REQUIRED = ('registry-closed-state', 'spam-incident-config-labels', 'pdf-mapping-configuration',
            'pdf-generated-preview', 'alfresco-settings-desktop', 'alfresco-incident-documents')


def test_browser_palette_has_precedence_over_the_original_photo():
    src = BUILDER.read_text(encoding='utf8')
    right_panel = src.split('function rightPanel(slide,d,accent)', 1)[1]
    assert right_panel.index("d.index===70 && categoryPalette?.id==='spam-incident-config-labels'") < right_panel.index('if(d.photo_art)')
    assert 'slide.addImage({path:categoryPalette.path' in right_panel
    assert 'imageSizingContain(categoryPalette.path' in right_panel
    assert "paletteCI?['spam-incident-config-labels']" in src


def test_validator_proves_actual_linkage_to_slide70():
    src = VERIFIER.read_text(encoding='utf8')
    assert 'linked_slide_image_digests(archive, PALETTE_SLIDE)' in src
    assert "checksum not in slide70_digests" in src
    assert 'Screenshot CI non collegata alla slide ' in src


def _can_run_builder():
    if shutil.which('node') is None:
        return False
    proc = subprocess.run(['node', '-e', "require('pptxgenjs');require('image-size')"],
                          capture_output=True, text=True)
    return proc.returncode == 0


@pytest.mark.skipif(not _can_run_builder(), reason='Visual CI Node dependencies not available')
def test_same_run_palette_is_embedded_and_referenced_by_slide70(tmp_path):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip('Pillow not installed in this test environment')
    records = []
    for index, ident in enumerate(REQUIRED):
        file = tmp_path / (ident + '.jpg')
        Image.new('RGB', (560 + index * 3, 230 + index * 2),
                  (40 + index * 18, 70 + index * 11, 105 + index * 8)).save(file, quality=90)
        records.append({'id': ident, 'file': file.name,
                        'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'source_kind': 'real_browser',
                                    'source_commit': 'a' * 40, 'build': '20261125',
                                    'screenshots': records}), encoding='utf8')
    deck = tmp_path / 'CI_visual_test_only.pptx'
    env = {**os.environ, 'CIR_SCREENSHOT_MANIFEST': str(manifest),
           'CIR_REQUIRE_REAL_SCREENSHOTS': '1', 'GITHUB_SHA': 'a' * 40,
           'CIR_RELEASE_BUILD': '20261125'}
    proc = subprocess.run(['node', str(BUILDER), str(deck)], cwd=ROOT,
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    checked = subprocess.run([sys.executable, str(VERIFIER), '--pptx', str(deck),
                              '--screenshot-manifest', str(manifest), '--require-ci-images'],
                             cwd=ROOT, capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)['slides'] == 87

    # Prove that the validator will reject an image that is still in the PPTX
    # media pool but is no longer referenced by the intended slide.
    tampered = tmp_path / 'unlinked_palette_test_only.pptx'
    slide_name = 'ppt/slides/slide78.xml'
    with ZipFile(deck) as source, ZipFile(tampered, 'w') as target:
        for entry in source.infolist():
            contents = source.read(entry.filename)
            if entry.filename == slide_name:
                page = ET.fromstring(contents)
                ns = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
                rel = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
                # Remove image links while leaving every original media byte.
                for blip in page.iter(ns + 'blip'):
                    blip.attrib.pop(rel + 'embed', None)
                contents = ET.tostring(page, encoding='utf-8', xml_declaration=True)
            target.writestr(entry, contents)
    rejected = subprocess.run([sys.executable, str(VERIFIER), '--pptx', str(tampered),
                               '--screenshot-manifest', str(manifest), '--require-ci-images'],
                              cwd=ROOT, capture_output=True, text=True)
    assert rejected.returncode != 0
    assert 'Screenshot CI non collegata alla slide ' in rejected.stderr
