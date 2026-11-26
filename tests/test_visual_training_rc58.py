"""Verify editorial and CI-backed visual training contain distinct provenance."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'docs/presentation/visual_rc58_spec.json'
DECK = ROOT / 'docs/presentation/CIR_Operational_Training_Visual_RC58.pptx'
SCRIPT = ROOT / 'scripts/verify_visual_training_rc58.py'


def test_rc58_editorial_spec_preserves_requested_workflow_and_licenses():
    rows = json.loads(SPEC.read_text(encoding='utf8'))
    assert len(rows) == 79
    original = {row.get('original'): row for row in rows if row.get('original') is not None}
    for removed in (14, 15):
        assert removed not in original
    assert original[8]['title'] == 'Login'
    assert original[19]['title'] == 'Come cambia lo stato di un incidente: workflow generale (configurabile)'
    assert original[28]['title'].replace('’', chr(39)) == "Sicurezza e tracciabilità dell'applicazione"
    assert original[76]['title'].replace('’', chr(39)) == "Come rendere operativa l'applicazione"
    for number in range(42, 51):
        assert 'workflow' in original[number]['title'].lower()
    assert 'EUPL' in ' '.join(rows[-5]['bullets'])
    assert 'Alessandro.DeSalvo@roma1.infn.it' in ' '.join(rows[-1]['bullets'])
    assert any('%REFERENCE%' in text for text in original[50]['bullets'])
    assert 'user_alert' not in json.dumps(rows)


def test_rc58_editorial_deck_has_expected_slide_count_and_real_screenshot_gate():
    if not DECK.is_file():
        import pytest
        pytest.skip('Legacy deck intentionally removed from the repository')
    result = subprocess.run([sys.executable, str(SCRIPT), '--pptx', str(DECK)],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['slides'] == 79
    # Even a correct editorial presentation must never be described as containing
    # this run's verified images when no browser capture manifest was provided.
    invalid = subprocess.run([sys.executable, str(SCRIPT), '--pptx', str(DECK),
                              '--require-ci-images'], text=True, capture_output=True)
    assert invalid.returncode != 0
    assert 'screenshot-manifest' in invalid.stderr


def test_ci_rebuild_requires_real_browser_images_before_packaging():
    flow = (ROOT / '.github/workflows/ci-release.yml').read_text(encoding='utf8')
    assert 'scripts/build_training_visual_rc64.js' in flow
    assert 'scripts/verify_visual_training_rc64.py' in flow
    assert 'CIR_REQUIRE_REAL_SCREENSHOTS' in flow
    assert flow.index('Audit synthetic image provenance and build current visual training') < flow.index('Validate and seal complete documentation bundle')
    assert flow.index('python scripts/sync_current_documentation.py') < flow.index('bash ./scripts/package_release.sh "${RUNNER_TEMP}/cir-ui-evidence/')


def test_ci_pdf_capture_activates_visible_template_card_not_hidden_checkbox():
    """RC59 regression: the transparent checkbox cannot be clicked directly."""
    capture = (ROOT / 'scripts/capture_ui_screenshots.py').read_text(encoding='utf8')
    template = (ROOT / 'app/templates/incident_detail.html').read_text(encoding='utf8')
    style = (ROOT / 'app/static/style.css').read_text(encoding='utf8')
    assert 'label.template-select-card:has(input[value="documentation-valutazione"])' in capture
    assert "expect(form.locator('input[value=\"documentation-valutazione\"]')).to_be_checked()" in capture
    assert "form.locator('input[value=\"documentation-valutazione\"]').check()" not in capture
    assert '<label class="template-select-card"' in template
    assert 'class="template-select-input" type="checkbox"' in template
    assert '.template-select-input{position:absolute;opacity:0;pointer-events:none;}' in style
