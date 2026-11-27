"""RC74: mandate actual focused UI evidence and automatic document regeneration.

No fabricated screenshot in this test is distributed as authentic UI evidence.
The CI must acquire images from the real running application separately.
"""
from __future__ import annotations
import json
from pathlib import Path
import re

from scripts import capture_ui_screenshots as capture
from scripts import ui_documentation_evidence as evidence
from scripts.verify_visual_training_rc64 import REQUIRED_CI

ROOT = Path(__file__).resolve().parents[1]


def test_mandatory_browser_captures_are_consistent_with_evidence_validator():
    assert capture.REQUIRED_CAPTURES == evidence.REQUIRED_SCREENSHOTS
    assert len(capture.REQUIRED_CAPTURES) == 32
    assert {'tenant-wizard-next-step', 'notification-preview', 'pdf-generated-preview'} <= capture.REQUIRED_CAPTURES
    assert evidence.ELEMENT_CAPTURE_SELECTORS['tenant-wizard-next-step'] == '.setup-wizard-shell'
    assert evidence.DOCUMENTATION_CAPTURE_ROUTES['tenant-wizard-next-step'] == '/admin/setup-wizard'
    for ident, selector in {
        'workflow-steps-focused': '#incident-workflow .workflow-steps-ordered',
        'statistics-desktop': '.stats-card:first-child',
        'assistant-panel-closeup': '#cir-albot-panel',
    }.items():
        assert ident in REQUIRED_CI
        assert ident in capture.REQUIRED_CAPTURES
        assert evidence.ELEMENT_CAPTURE_SELECTORS[ident] == selector
    source = (ROOT/'scripts/capture_ui_screenshots.py').read_text(encoding='utf8')
    assert 'go(page, "/reports/stats")' in source
    assert '"width": 1100' in source
    assert 'element_selector=\'#incident-workflow .workflow-steps-ordered\'' in source
    assert 'element_selector=\'#cir-albot-panel\'' in source


def test_specific_instructional_slides_and_future_classification_note():
    spec=json.loads((ROOT/'docs/presentation/visual_rc64_spec.json').read_text())
    by_id={item['index']:item for item in spec}
    assert by_id[61]['title'] == '06 / Laboratorio didattico: esempio di incidente di SPAM'
    assert by_id[73]['title'] == 'Considerazioni sull’esempio didattico per un incidente di tipo SPAM'
    text=' '.join(by_id[70]['bullets']).lower()
    assert 'prima categoria' in text
    assert 'quello predefinito' in text
    assert 'non somma i workflow' in text
    assert 'duplicazion' not in text
    assert 'in fase di definizione' in ' '.join(by_id[18]['bullets']).lower()
    assert 'albot' in ' '.join(by_id[59]['bullets']).lower()
    assert 'workflow' in ' '.join(by_id[59]['bullets']).lower()
    assert 'conferm' in ' '.join(by_id[59]['bullets']).lower()
    assert (ROOT / 'app/static/ai-chatbot/albot-avatar.png').is_file()


def test_real_ui_slide_focus_and_avatar_are_hard_gates():
    builder=(ROOT/'scripts/build_training_visual_rc64.js').read_text()
    verifier=(ROOT/'scripts/verify_visual_training_rc64.py').read_text()
    assert "48:'workflow-steps-focused'" in builder
    assert "57:'statistics-desktop'" in builder
    assert "60:'assistant-panel-closeup'" in builder
    assert "app/static/ai-chatbot/albot-avatar.png" in builder
    # The full CI gallery links every screenshot, including focused DOM
    # regions; the training chapter also renders exact-pixel detail crops.
    for ident in ('workflow-steps-focused', 'statistics-desktop', 'assistant-panel-closeup'):
        assert ident in REQUIRED_CI
    assert 'for ident in REQUIRED_CI:' in verifier
    assert 'linked_slide_image_digests(linked_archive, n)' in verifier
    assert 'linked_slide_image_digests(rich_archive, slide)' in verifier


def test_documentation_rebuild_on_main_changes_and_manual_dispatch():
    workflow=(ROOT/'.github/workflows/ci-release.yml').read_text()
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert 'documentation_needed=true' in workflow
    assert 'production_changed=false' in workflow
    assert "needs.release-scope.outputs.documentation_needed == 'true'" in workflow
    assert 'scripts/training_release_assets.py' in workflow
    assert 'scripts/publish_training_release.sh' in workflow
    assert 'scripts/verify_visual_training_rc64.py' in workflow
    from scripts.documentation_publication_policy import generated, needs_publication
    source_paths=[
        'app/routes.py', 'app/static/ui/incident.css',
        'app/templates/stats.html', 'app/plugins/ai_chatbot/templates/ai_chatbot_chat.html',
        'docs/presentation/visual_rc64_spec.json',
        'scripts/build_training_visual_rc64.js',
        'scripts/capture_ui_screenshots.py',
        '.github/workflows/ci-release.yml',
    ]
    assert all(not generated(path) for path in source_paths)
    assert all(needs_publication([path]) for path in source_paths)
    assert not needs_publication([
       'docs/presentation/CIR_Operational_Training_Visual.pptx',
       'docs/presentation/CIR_Operational_Training_Visual.pdf',
       'docs/presentation/CIR_Operational_Training_IT.pptx',
    ])
