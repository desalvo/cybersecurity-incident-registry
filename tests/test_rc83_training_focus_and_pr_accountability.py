"""RC83: exact-source callout and fail-closed documentation PR accountability."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from scripts.verify_visual_training_rc64 import verified_native_zoom

ROOT = Path(__file__).resolve().parents[1]


def make_slide(tmp_path, *, crop=True, caption=True, same_image=True):
    outfile = tmp_path / 'zoom.pptx'
    picture = b'original-browser-screenshot-for-structural-test'
    other = b'not-the-verified-source'
    picture_xml = (
        '<p:pic><p:blipFill><a:blip r:embed="rId1"/></p:blipFill></p:pic>'
        '<p:pic><p:blipFill><a:blip r:embed="rId2"/>'
        + ('<a:srcRect l="12000" t="18000" r="26000" b="42000"/>' if crop else '')
        + '</p:blipFill></p:pic>'
    )
    xml = ('<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
           'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
           + ('<a:t>INGRANDIMENTO della funzione</a:t>' if caption else '')
           + picture_xml + '</p:sld>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/original.png"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/'
            + ('original.png' if same_image else 'other.png') + '"/></Relationships>')
    with ZipFile(outfile, 'w') as z:
        z.writestr('ppt/slides/slide55.xml', xml)
        z.writestr('ppt/slides/_rels/slide55.xml.rels', rels)
        z.writestr('ppt/media/original.png', picture)
        z.writestr('ppt/media/other.png', other)
    return outfile, sha256(picture).hexdigest()


@pytest.mark.parametrize(('crop', 'caption', 'same_image', 'valid'), [
    (True, True, True, True),
    (False, True, True, False),
    (True, False, True, False),
    (True, True, False, False),
])
def test_zoom_must_crop_the_identical_verified_source(tmp_path, crop, caption, same_image, valid):
    name, checksum = make_slide(tmp_path, crop=crop, caption=caption, same_image=same_image)
    with ZipFile(name) as z:
        assert verified_native_zoom(z, 55, checksum) is valid


def test_main_branch_publication_has_accountability_gate():
    jobs = yaml.safe_load((ROOT / '.github/workflows/ci-release.yml').read_text())['jobs']
    publisher = jobs['documentation-publication']
    watcher = jobs['documentation-publication-accountability']
    assert publisher['outputs']['result'] == '${{ steps.publish.outputs.result }}'
    assert 'always()' in watcher['if']
    assert 'refs/heads/main' in watcher['if']
    assert 'documentation-publication' in watcher['needs']
    code = '\n'.join(str(step.get('run', '')) for step in watcher['steps'])
    assert 'Required documentation publication was skipped or failed' in code
    assert 'Publication job did not report a verified outcome' in code
    publish_script = '\n'.join(str(step.get('run', '')) for step in publisher['steps'])
    assert 'result=already-current' in publish_script
    assert 'result=pr-opened' in publish_script
    assert 'gh pr create' in publish_script


def test_no_future_ci_screenshot_promises_in_editorial_slide_text():
    source = (ROOT / 'scripts/build_training_visual_rc64.js').read_text()
    spec = json.loads((ROOT / 'docs/presentation/visual_rc64_spec.json').read_text())
    text = '\n'.join(x for slide in spec for x in slide.get('bullets', []))
    assert 'prossima CI' not in text
    assert 'screenshot reale sarà integrata dalla CI' not in source
    assert 'Vista reale del Wizard integrata dalla CI' not in source
    assert 'addCiZoom(slide,shot,null,d)' in source
    assert 'imageSizingCrop(shot.path' in source
    assert 'CIR_REQUIRE_REAL_SCREENSHOTS' in source


def test_strict_ci_accepts_only_real_browser_with_isolated_synthetic_test_data():
    js = (ROOT / 'scripts/build_training_visual_rc64.js').read_text()
    py = (ROOT / 'scripts/verify_visual_training_rc64.py').read_text()
    for source in (js, py):
        assert 'real-application-browser' in source
        assert 'isolated-synthetic-fixture' in source
    assert "ciManifest.source_kind!=='real-application-browser'" in js
    assert "data.get('source_kind') != 'real-application-browser'" in py
