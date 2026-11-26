"""RC82: enforce the real GitHub Actions output contract and no CI placeholders.

All fixtures are disposable text/ZIP fragments and are not published screenshots.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest
import yaml

from scripts import documentation_publication_policy as policy
from scripts.verify_visual_training_rc64 import reject_unresolved_ci_captions

ROOT = Path(__file__).resolve().parents[1]


def _policy_output(tmp_path, changed, monkeypatch):
    output = tmp_path / 'output'
    monkeypatch.setattr(sys, 'argv', ['documentation_publication_policy.py',
                                    '--before', 'a' * 40, '--head', 'b' * 40,
                                    '--publication-output', str(output)])
    with patch.object(policy.subprocess, 'check_output', return_value='\n'.join(changed)):
        policy.main()
    rows = dict(item.split('=', 1) for item in output.read_text().splitlines())
    return rows


@pytest.mark.parametrize(('changed', 'expected'), [
    (['app/routes.py'], 'true'),
    (['scripts/build_training_visual_rc64.js'], 'true'),
    (['.github/workflows/ci-release.yml'], 'true'),
    (['docs/presentation/visual_rc64_spec.json'], 'true'),
    (['docs/presentation/CIR_Operational_Training_Visual.pptx'], 'false'),
    (['docs/UI_SCREENSHOTS_BUILD.json', 'app/static/help/ui-runtime/login-desktop.png'], 'false'),
])
def test_policy_emits_exact_workflow_job_output(tmp_path, changed, expected, monkeypatch):
    rows = _policy_output(tmp_path, changed, monkeypatch)
    assert rows == {'documentation_needed': expected}


def test_policy_output_name_matches_job_gate_and_manual_override():
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci-release.yml').read_text())
    scope = workflow['jobs']['release-scope']
    job = workflow['jobs']['documentation-publication']
    assert scope['outputs']['documentation_needed'] == '${{ steps.diff.outputs.documentation_needed }}'
    assert "needs.release-scope.outputs.documentation_needed == 'true'" in job['if']
    commands = '\n'.join(str(step.get('run', '')) for step in scope['steps'])
    assert 'documentation_publication_policy.py' in commands
    assert 'echo "documentation_needed=true"' in commands
    assert 'echo "documentation_needed=false"' in commands
    assert 'Require an explicit release and documentation decision' in [step.get('name') for step in scope['steps']]
    assert 'github.ref == \'refs/heads/main\'' in job['if']
    assert "needs.docker-release.result == 'skipped'" in job['if']


def _slide_zip(tmp_path, caption):
    outfile = tmp_path / 'slide-fragment.pptx'
    with ZipFile(outfile, 'w') as zipfile:
        zipfile.writestr('ppt/slides/slide1.xml',
                         '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                         'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                         '<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>' + caption +
                         '</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
    return outfile


@pytest.mark.parametrize('placeholder', [
    'Illustrazione editoriale · la screenshot reale sarà integrata dalla CI',
    'Pannello conversazione AlBot: cattura reale richiesta alla CI',
    'Vista reale del Wizard integrata dalla CI dopo la cattura autenticata',
    'ESEMPIO CIR · SCHERMATA EDITORIALE',
])
def test_strict_visual_publishing_rejects_editorial_placeholder(tmp_path, placeholder):
    with ZipFile(_slide_zip(tmp_path, placeholder)) as archive:
        with pytest.raises(ValueError, match='Screenshot CI non sostituita'):
            reject_unresolved_ci_captions(archive, ['ppt/slides/slide1.xml'])


def test_strict_visual_publishing_accepts_real_ui_caption(tmp_path):
    with ZipFile(_slide_zip(tmp_path, 'WIZARD INIZIALE DEL TENANT · CATTURA CI VERIFICATA')) as archive:
        reject_unresolved_ci_captions(archive, ['ppt/slides/slide1.xml'])
