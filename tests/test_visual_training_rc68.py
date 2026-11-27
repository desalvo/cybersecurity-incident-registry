"""RC68: the provenance gate must accept *all* verified same-run screenshots.

All screenshot pixels generated here are disposable synthetic test fixtures;
none comes from a live user interface or becomes release documentation.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'scripts/build_training_visual_rc64.js'
VERIFIER = ROOT / 'scripts/verify_visual_training_rc64.py'
CAPTURE_IDS = (
    'login-desktop', 'login-mobile', 'registry-desktop', 'registry-closed-state',
    'registry-mobile', 'registry-mobile-menu', 'incident-desktop', 'incident-mobile',
    'spam-incident-desktop', 'spam-incident-config-labels', 'spam-workflow-steps',
    'workflow-steps-focused', 'statistics-desktop', 'assistant-panel-closeup',
    'tenant-setup-wizard-desktop', 'tenant-setup-wizard-panel',
    'pdf-mapping-configuration', 'pdf-generated-preview', 'alfresco-settings-desktop',
    'alfresco-incident-documents', 'assistant-desktop', 'assistant-mobile',
    'interface-settings-desktop', 'classic-registry-desktop', 'admin-modules-desktop',
    'admin-sso-desktop', 'documentation-user-desktop', 'documentation-user-mobile',
    'documentation-admin-desktop', 'documentation-admin-mobile',
    'notification-preview', 'tenant-wizard-next-step',
)


def _available():
    if not shutil.which('node'):
        return False
    return subprocess.run(
        ['node', '-e', "require('pptxgenjs');require('image-size')"],
        capture_output=True, text=True,
    ).returncode == 0


@pytest.fixture(scope='module')
def full_browser_capture(tmp_path_factory):
    if not _available():
        pytest.skip('Visual CI Node dependencies not available')
    image_module = pytest.importorskip('PIL.Image')
    directory = tmp_path_factory.mktemp('cir68_browser_fixture')
    screenshots = []
    for index, ident in enumerate(CAPTURE_IDS):
        file = directory / (ident + '.jpg')
        image_module.new('RGB', (620 + 2 * index, 310 + index),
                         (32 + 4 * index, 65 + 3 * index, 105 + 2 * index)).save(file)
        screenshots.append({
            'id': ident, 'file': file.name,
            'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
        })
    from tests.rc87_test_visual_fixtures import generated_pdf_preview
    preview = generated_pdf_preview(directory)
    manifest = directory / 'manifest.json'
    manifest.write_text(json.dumps({
        'source_kind': 'real-application-browser',
        'source_commit': 'a' * 40,
        'build': '20261125',
        'data_provenance': 'isolated-synthetic-fixture',
        'screenshots': screenshots, 'generated_pdf_preview': preview,
    }), encoding='utf8')
    pptx = directory / 'disposable_rc68_visual_fixture.pptx'
    env = {**os.environ, 'CIR_SCREENSHOT_MANIFEST': str(manifest),
           'CIR_REQUIRE_REAL_SCREENSHOTS': '1',
           'GITHUB_SHA': 'a' * 40, 'CIR_RELEASE_BUILD': '20261125'}
    proc = subprocess.run(['node', str(BUILDER), str(pptx)], cwd=ROOT,
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return directory, pptx, manifest, env


def _verify(pptx, manifest, env):
    return subprocess.run(
        [sys.executable, str(VERIFIER), '--pptx', str(pptx),
         '--screenshot-manifest', str(manifest), '--require-ci-images'],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )


def test_current_ci_captures_all_have_valid_provenance(full_browser_capture):
    _, pptx, manifest, env = full_browser_capture
    proc = _verify(pptx, manifest, env)
    assert proc.returncode == 0, proc.stderr
    details = json.loads(proc.stdout)
    assert details['slides'] == 99 + len(CAPTURE_IDS) - 1
    assert details['verified_browser_screenshots'] == len(CAPTURE_IDS)
    assert details['mandatory_ci_images_embedded'] is True


def test_rc91_appendix_separates_gallery_and_numbers_terminal_previews(full_browser_capture):
    from xml.etree import ElementTree as ET
    from scripts.verify_visual_training_rc64 import linked_slide_image_digests
    directory, deck, manifest, env = full_browser_capture
    visible = len(CAPTURE_IDS) - 1  # classic UI is deliberately excluded
    assert visible == 31
    with ZipFile(deck) as archive:
        def text(number):
            page = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            return ' '.join(el.text or '' for el in page.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
        assert '08' in text(97) and 'Appendici' in text(97)
        assert 'Schermata 1 / 33' in text(98)
        assert 'Schermata 31 / 33' in text(128)
        assert 'Schermata 32 / 33' in text(129) and 'Documento PDF compilato' in text(129)
        assert 'Schermata 33 / 33' in text(130) and 'Notifica prima' in text(130)
        preview = json.loads(manifest.read_text())['generated_pdf_preview']
        assert preview['png_sha256'] in linked_slide_image_digests(archive,129)
        notify = next(row for row in json.loads(manifest.read_text())['screenshots'] if row['id']=='notification-preview')
        assert notify['sha256'] in linked_slide_image_digests(archive,130)
        classic = next(row for row in json.loads(manifest.read_text())['screenshots'] if row['id']=='classic-registry-desktop')
        for number in range(98,131):
            assert classic['sha256'] not in linked_slide_image_digests(archive,number)


def test_nonmandatory_capture_checksum_is_checked(full_browser_capture):
    directory, pptx, manifest, env = full_browser_capture
    data = json.loads(manifest.read_text())
    next(item for item in data['screenshots'] if item['id'] == 'login-desktop')['sha256'] = '0' * 64
    altered = directory / 'wrong_hash_manifest.json'
    altered.write_text(json.dumps(data))
    proc = _verify(pptx, altered, env)
    assert proc.returncode != 0
    assert 'Checksum sorgente screenshot errato: login-desktop' in proc.stderr


def test_nonmandatory_capture_cannot_escape_directory(full_browser_capture):
    directory, pptx, manifest, env = full_browser_capture
    data = json.loads(manifest.read_text())
    next(item for item in data['screenshots'] if item['id'] == 'login-desktop')['file'] = '../elsewhere.jpg'
    altered = directory / 'invalid_path_manifest.json'
    altered.write_text(json.dumps(data))
    proc = _verify(pptx, altered, env)
    assert proc.returncode != 0
    assert 'Percorso screenshot invalido' in proc.stderr


def test_unmanifested_pptx_media_is_still_rejected(full_browser_capture):
    directory, pptx, manifest, env = full_browser_capture
    altered = directory / 'foreign_media.pptx'
    with ZipFile(pptx, 'r') as source, ZipFile(altered, 'w') as target:
        for member in source.infolist():
            target.writestr(member, source.read(member.filename))
        target.writestr('ppt/media/foreign-artwork.jpg', b'untracked image bytes')
    proc = _verify(altered, manifest, env)
    assert proc.returncode != 0
    assert 'Media del PowerPoint senza provenienza CIR: 1 file' in proc.stderr


def test_capture_manifest_must_match_ci_commit_and_build(full_browser_capture):
    _, pptx, manifest, env = full_browser_capture
    for key, value in [('GITHUB_SHA', 'b' * 40), ('CIR_RELEASE_BUILD', '20261124')]:
        conflicting = {**env, key: value}
        proc = _verify(pptx, manifest, conflicting)
        assert proc.returncode != 0
        assert 'diverso dalla build CI' in proc.stderr


def test_published_gallery_checks_the_same_real_image_links_without_rebinding_to_pr_sha(
        full_browser_capture, monkeypatch):
    """A chore PR verifies the sealed capture, not its temporary merge SHA."""
    from scripts.verify_visual_training_rc64 import run_check
    _, pptx, manifest, _ = full_browser_capture
    monkeypatch.setenv('GITHUB_SHA', 'f' * 40)
    monkeypatch.setenv('CIR_RELEASE_BUILD', '99999999')
    report = run_check(pptx, None, manifest, False, published_ci_images=True)
    assert report['slides'] == 99 + len(CAPTURE_IDS) - 1
    assert report['mandatory_ci_images_embedded'] is True
    assert report['verified_browser_screenshots'] == len(CAPTURE_IDS)
    with pytest.raises(ValueError, match='source_commit diverso'):
        run_check(pptx, None, manifest, True)
