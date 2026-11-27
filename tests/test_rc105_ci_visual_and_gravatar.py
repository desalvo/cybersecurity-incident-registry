"""RC105: document new AlBot slide and keep browser captures hermetic."""
from pathlib import Path

from scripts.verify_visual_training_rc64 import (REQUIRED_SLIDE_TITLES,
    ADDED_SLIDES, ARCH_SLIDES, WORKFLOW_INTRO_SLIDES)

ROOT = Path(__file__).resolve().parents[1]


def test_albot_presentation_gate_matches_workflow_authoring_content():
    assert REQUIRED_SLIDE_TITLES[59] == 'AlBot: AI assistiva con RAG sanitizzato'
    assert 59 + ADDED_SLIDES + ARCH_SLIDES + WORKFLOW_INTRO_SLIDES == 74
    spec = ROOT / 'docs/presentation/visual_rc64_spec.json'
    import json
    original = next(row for row in json.loads(spec.read_text())
                    if row.get('original') == 60)
    assert original['title'] == REQUIRED_SLIDE_TITLES[59]
    from scripts.verify_visual_training_rc64 import ALBOT_ADDED_SLIDES
    assert ALBOT_ADDED_SLIDES == 1
    import json
    addition = json.loads((ROOT / 'docs/presentation/visual_rc105_albot_workflow_addendum.json').read_text())
    assert addition['insert_after_original'] == 60 and len(addition['slides']) == 1
    workflow = addition['slides'][0]
    assert workflow['title'] == 'AlBot: crea e aggiorna workflow con conferma'
    text = ' '.join(workflow['bullets']).casefold()
    for key in ('workflow', 'dipendenze', 'conferma', 'json', 'tenant'):
        assert key in text


def test_documentation_capture_disables_remote_avatars_in_fixture_only():
    source = (ROOT / 'scripts/seed_ui_documentation.py').read_text()
    assert 'Setting(key="global_gravatar_enabled", value="0")' in source
    assert 'db.session.merge(Setting(key="global_gravatar_enabled", value="0"))' in source
    default = (ROOT / 'app/ui_settings.py').read_text()
    assert 'DEFAULT_GRAVATAR_ENABLED = True' in default
    assert "value not in ('0', 'false', 'off', 'no')" in default
    capture = (ROOT / 'scripts/capture_ui_screenshots.py').read_text()
    assert 'Broken visible image on {capture_id}' in capture
    assert 'no_browser_errors_or_external_requests' in capture
