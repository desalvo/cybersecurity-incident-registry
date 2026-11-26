"""RC73: current-only GitHub documentation and screenshot-visible PDF evidence.

Generated test rasters in this module are disposable fixtures, never authentic
browser evidence and never distributed as CIR application screenshots.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from scripts.documentation_publication_policy import generated, needs_publication
from scripts.sync_current_documentation import sync

ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / 'docs/presentation'


def test_repository_has_only_canonical_presentation_binaries():
    assert {p.name for p in PRESENTATION.glob('*.pptx')} == {
        'CIR_Operational_Training_IT.pptx', 'CIR_Operational_Training_Visual.pptx'}
    assert {p.name for p in PRESENTATION.glob('*.pdf')} == {'CIR_Operational_Training_Visual.pdf'}
    assert not list(PRESENTATION.glob('CIR_Operational_Training_Visual_RC*'))
    assert not (PRESENTATION / 'CIR_SPAM_Workflow_Module.pptx').exists()


def test_source_changes_trigger_document_publication_but_generated_merges_do_not():
    generated_files = ['docs/UI_SCREENSHOTS_BUILD.json',
                       'docs/presentation/CIR_Operational_Training_Visual.pptx',
                       'docs/presentation/CIR_Operational_Training_Visual.pdf',
                       'app/static/help/ui-runtime/login-desktop.png',
                       'PRODUCTION_IMAGE_DIGEST', 'k8s/kustomization.yaml']
    assert all(generated(item) for item in generated_files)
    assert needs_publication(generated_files) is False
    for item in ('scripts/build_training_visual_rc64.js', 'docs/presentation/visual_rc64_spec.json',
                 'docs/TRAINING.md', 'app/__init__.py', '.github/workflows/ci-release.yml'):
        assert generated(item) is False
        assert needs_publication(generated_files + [item]) is True


def test_cleanup_is_idempotent_and_keeps_non_presentation_documents(tmp_path):
    root = tmp_path / 'repo'
    presentation = root / 'docs/presentation'
    presentation.mkdir(parents=True)
    for filename in ('CIR_Operational_Training_Visual_RC71.pptx',
                     'CIR_Operational_Training_Visual_RC64.pdf',
                     'CIR_Operational_Training_Extended_IT.pptx',
                     'CIR_Operational_Training_IT.pptx'):
        (presentation / filename).write_bytes(b'o' * 5000)
    (presentation / 'visual_rc64_spec.json').write_text('{}')
    (root / 'docs/documentazione_utente.pdf').write_bytes(b'valid manual')
    pptx, pdf, receipt = [tmp_path / name for name in ('current.pptx', 'current.pdf', 'receipt.json')]
    pptx.write_bytes(b'P' * 5000)
    pdf.write_bytes(b'F' * 5000)
    receipt.write_text('{}')
    removed = sync(root, pptx, pdf, receipt)
    assert len(removed) == 3
    assert sync(root, pptx, pdf, receipt) == []
    assert {p.name for p in presentation.glob('*.pptx')} == {
        'CIR_Operational_Training_IT.pptx', 'CIR_Operational_Training_Visual.pptx'}
    assert (presentation / 'CIR_Operational_Training_Visual.pdf').read_bytes() == b'F' * 5000
    assert (presentation / 'visual_rc64_spec.json').read_text() == '{}'
    assert (root / 'docs/documentazione_utente.pdf').exists()


def test_yaml_publication_is_not_dependent_on_docker_rebuild():
    yaml = pytest.importorskip('yaml')
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci-release.yml').read_text())
    jobs = workflow['jobs']
    publish = jobs['documentation-publication']
    assert {'quality-gates', 'ui-documentation', 'release-scope', 'docker-release'} <= set(publish['needs'])
    condition = publish['if']
    assert "needs.docker-release.result == 'skipped'" in condition
    assert "needs.ui-documentation.result == 'success'" in condition
    assert "needs.release-scope.outputs.documentation_needed == 'true'" in condition
    commands = '\n'.join(item.get('run','') for item in publish['steps'])
    assert 'scripts/verify_documentation_publication.py' in commands
    assert 'scripts/sync_current_documentation.py' in commands
    assert 'git add -A -f' in commands
    assert 'gh pr create' in commands
    docker_commands = '\n'.join(item.get('run','') for item in jobs['docker-release']['steps'])
    assert 'gh pr create' not in docker_commands
    docs_commands = '\n'.join(item.get('run','') for item in jobs['ui-documentation']['steps'])
    assert 'scripts/seal_visual_training.py' in docs_commands
    assert 'scripts/verify_visual_training_rc64.py' in docs_commands


def test_pdf_gallery_rejects_replaced_image(monkeypatch, tmp_path):
    from PIL import Image
    from scripts.verify_pdf_screenshot_gallery import verify
    original = tmp_path / 'test-only-source.png'
    Image.new('RGB', (640, 280), (25, 75, 155)).save(original)
    screenshot_area = (.76, 1.48, 11.81, 4.98)
    scale = 960 / 13.33333
    x, y, w, h = [round(v * scale) for v in screenshot_area]
    canvas = Image.new('RGB', (960, 540), '#ffffff')
    fitted_w, fitted_h = (w, round(280 * w / 640))
    canvas.paste(Image.new('RGB', (fitted_w, fitted_h), (25, 75, 155)),
                 (x, y + (h - fitted_h) // 2))
    def render(args, **kwargs):
        canvas.save(Path(args[-1]).with_suffix('.png'))
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(subprocess, 'run', render)
    assert verify(tmp_path/'fake-pdf.pdf', [original], base_slides=0) == 1
    canvas.paste((210, 35, 25), (x, y + (h - fitted_h) // 2,
                                 x+fitted_w, y + (h + fitted_h) // 2))
    with pytest.raises(ValueError, match='does not match'):
        verify(tmp_path/'fake-pdf.pdf', [original], base_slides=0)


def test_visual_receipt_requires_all_pdf_pages_verified(tmp_path):
    from scripts.seal_visual_training import seal
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'source_commit':'a'*40, 'build':'20261125',
                                   'screenshots':[{'id':'test', 'sha256':'b'*64}]}))
    validation = tmp_path/'verification.json'
    validation.write_text(json.dumps({'status':'PASS', 'verified_browser_screenshots':1,
                                     'pdf_screenshots_visually_verified':0,
                                     'slides':88,'pdf_pages':88}))
    deck=tmp_path/'deck.pptx'; pdf=tmp_path/'deck.pdf'
    deck.write_bytes(b'test');pdf.write_bytes(b'test')
    with pytest.raises(ValueError, match='not fully verified'):
        seal(deck,pdf,manifest,validation,tmp_path/'receipt.json')
