"""RC102: release assets are externally published only after same-run checks."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pytest
import yaml
from scripts.training_release_assets import ASSETS, RECEIPTS, stage, verify_staged

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 40


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(tmp_path):
    visual = tmp_path/'visual'; visual.mkdir()
    doc = tmp_path/'doc'; doc.mkdir()
    output = tmp_path/'release'
    evidence = tmp_path/'manifest.json'
    evidence.write_text(json.dumps({'source_commit': SHA, 'screenshots': [{'id': 'login', 'sha256': _digest(b'x')}]}))
    source_sha = _digest(evidence.read_bytes())
    base = dict(source_commit=SHA, screenshot_manifest_sha256=source_sha,
                screenshots=[{'id': 'login', 'sha256': _digest(b'x')}],
                slide_count=42, pdf_pages=42, pdf_screenshots_visually_verified=1)
    records = {}
    for name, (kind, _) in ASSETS.items():
        path = (visual if kind in ('visual','english') else doc) / name
        path.write_bytes((name.encode('utf-8') + b'\x00') * 200)
        records[name] = _digest(path.read_bytes())
    it = dict(base, locale='it', pptx_sha256=records['CIR_Operational_Training_Visual.pptx'],
              pdf_sha256=records['CIR_Operational_Training_Visual.pdf'])
    en = dict(base, locale='en', pptx_sha256=records['CIR_Operational_Training_Visual_EN.pptx'],
              pdf_sha256=records['CIR_Operational_Training_Visual_EN.pdf'])
    op = dict(base, file='CIR_Operational_Training_IT.pptx', real_screenshots=True,
              sha256=records['CIR_Operational_Training_IT.pptx'])
    doc_receipt=dict(base, schema_version=2, real_screenshots=True,
                     files=[{'file':'CIR_UI_Screenshots.pdf', 'sha256': records['CIR_UI_Screenshots.pdf']}])
    for key, row in [('visual',it),('english',en),('operational',op),('documentation',doc_receipt)]:
        (visual if key in ('visual','english') else doc).joinpath(RECEIPTS[key]).write_text(json.dumps(row))
    return visual, doc, evidence, output


def test_staging_and_verified_manifest(tmp_path):
    visual,doc,evidence,output = fixture(tmp_path)
    record=stage(visual,doc,evidence,output,SHA)
    assert record['source_commit']==SHA
    assert record['release_tag']=='training-'+SHA
    assert len(record['files'])==10
    assert record['stable_download_urls']['CIR_Operational_Training_Visual.pdf'].endswith('/releases/latest/download/CIR_Operational_Training_Visual.pdf')
    assert verify_staged(output,SHA)==record


def test_reject_modified_presentation(tmp_path):
    visual,doc,evidence,output=fixture(tmp_path)
    (visual/'CIR_Operational_Training_Visual_EN.pdf').write_bytes(b'tamper'*2000)
    with pytest.raises(ValueError,match='checksum mismatch'):
        stage(visual,doc,evidence,output,SHA)


def test_reject_modified_staged_release(tmp_path):
    visual,doc,evidence,output=fixture(tmp_path)
    stage(visual,doc,evidence,output,SHA)
    (output/'CIR_Operational_Training_Visual.pptx').write_bytes(b'CORRUPTED')
    with pytest.raises(ValueError,match='tampered'):
        verify_staged(output,SHA)


def test_reject_foreign_english_manifest(tmp_path):
    visual,doc,evidence,output=fixture(tmp_path)
    path=visual/RECEIPTS['english'];row=json.loads(path.read_text());row['source_commit']='b'*40
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError,match='another commit'):
        stage(visual,doc,evidence,output,SHA)


def test_reject_different_english_slide_count(tmp_path):
    visual,doc,evidence,output=fixture(tmp_path)
    path=visual/RECEIPTS['english'];row=json.loads(path.read_text());row['slide_count']=99
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError,match='same-run Italian master'):
        stage(visual,doc,evidence,output,SHA)


def test_gh_ci_release_without_documentation_chore_pr():
    wf=yaml.safe_load((ROOT/'.github/workflows/ci-release.yml').read_text())['jobs']
    publisher=wf['documentation-publication']
    script='\n'.join(str(step.get('run','')) for step in publisher['steps'])
    assert 'training_release_assets.py' in script
    assert 'publish_training_release.sh' in script
    assert 'gh pr create' not in script
    assert 'contents' in publisher['permissions']
    assert 'production-digest-publication' in wf
    digest='\n'.join(str(step.get('run','')) for step in wf['production-digest-publication']['steps'])
    assert 'docs/' not in digest or 'No screenshots' in digest
    assert 'gh pr create' in digest
    assert wf['production-digest-publication']['permissions']['actions'] == 'write'
    assert 'sync_current_documentation.py' not in (ROOT/'.github/workflows/ci-release.yml').read_text()


def test_source_archive_and_docs_refuse_binary_reintroduction():
    assert not (ROOT/'docs/presentation/CIR_Operational_Training_Visual.pptx').exists()
    assert not (ROOT/'docs/presentation/CIR_Operational_Training_Visual_EN.pdf').exists()
    from scripts.package_cumulative import EXTERNAL_RELEASE_ASSETS
    assert 'docs/presentation/CIR_Operational_Training_Visual.pptx' in EXTERNAL_RELEASE_ASSETS
    assert 'docs/CIR_UI_Screenshots.pdf' in EXTERNAL_RELEASE_ASSETS
    assert 'releases/latest/download/CIR_Operational_Training_Visual.pdf' in (ROOT/'docs/presentation/visual_rc64_spec.json').read_text()
    assert 'releases/latest/download/CIR_Operational_Training_Visual_EN.pdf' in (ROOT/'docs/presentation/visual_rc98_english_slides.json').read_text()


def test_reject_unsealed_gallery(tmp_path):
    visual, doc, evidence, output = fixture(tmp_path)
    (doc/'CIR_UI_Screenshots.pdf').write_bytes(b'changed screenshot gallery' * 400)
    with pytest.raises(ValueError, match='checksum mismatch'):
        stage(visual, doc, evidence, output, SHA)

def test_skip_expensive_browser_doc_after_digest_only_merge():
    wf=yaml.safe_load((ROOT/'.github/workflows/ci-release.yml').read_text())['jobs']
    ui=wf['ui-documentation']
    assert 'release-scope' in ui['needs']
    assert "needs.ci-mode.outputs.digest_only != 'true'" in ui['if']
    assert 'HEAD^ HEAD' in '\n'.join(str(x.get('run','')) for x in wf['ci-mode']['steps'])
    assert "digest_only: ${{ steps.mode.outputs.digest_only }}" == 'digest_only: '+wf['ci-mode']['outputs']['digest_only']
    assert "documentation_needed == 'true'" in ui['if']
    assert "production_changed == 'true'" in ui['if']
    assert 'workflow_dispatch' in ui['if']
    assert 'gh workflow run ci-release.yml --ref' in '\n'.join(str(x.get('run','')) for x in wf['production-digest-publication']['steps'])
