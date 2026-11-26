"""RC61 visual deck must distinguish synthetic art from authenticated screenshots."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRES = ROOT / 'docs/presentation'
SPEC = PRES / 'visual_rc61_spec.json'
DECK = PRES / 'CIR_Operational_Training_Visual_RC61.pptx'
VERIFY = ROOT / 'scripts/verify_visual_training_rc61.py'
ART = PRES / 'visual_rc61_art'


def test_rc61_spec_uses_distinct_thematic_artwork_and_corrects_text():
    rows = json.loads(SPEC.read_text(encoding='utf8'))
    assert len(rows) == 79
    selected = [3,4,5,6,7, *range(28,34), 35, *range(39,45),
                73, *range(75,80)]
    paths = [rows[n-1]['conceptual_art'] for n in selected]
    assert len(paths) == len(set(paths)) == 24
    assert all((ROOT / path).is_file() for path in paths)
    assert len(rows[20]['report_pages']) == 2
    assert all((ROOT / path).is_file() for path in rows[20]['report_pages'])
    assert 'drag & drop' in ' '.join(rows[33]['bullets']).lower()
    assert 'esempio' in rows[38]['title'].lower()
    assert 'discusso in dettaglio' in ' '.join(rows[43]['bullets']).lower()
    assert 'esempio didattico' in rows[46]['title'].lower()
    assert 'prima l’admin' in ' '.join(rows[54]['bullets']).lower()
    assert 'Dati interessati disponibili' in ' '.join(rows[69]['bullets'])
    assert not rows[69]['images'], 'RC61 must not present obsolete duplicate screenshot as authentic'


def test_rc61_packaged_deck_passes_static_verifier_and_ci_requires_fresh_capture():
    if not DECK.exists():
        import pytest
        pytest.skip('Legacy deck intentionally removed from the repository')
    good = subprocess.run([sys.executable, str(VERIFY), '--pptx', str(DECK)], capture_output=True, text=True)
    assert good.returncode == 0, good.stderr
    assert json.loads(good.stdout)['slides'] == 79
    missing = subprocess.run([sys.executable, str(VERIFY), '--pptx', str(DECK), '--require-ci-images'], capture_output=True, text=True)
    assert missing.returncode != 0 and 'screenshot-manifest' in missing.stderr
    assert "'spam-incident-config-labels'" in VERIFY.read_text(encoding='utf8')


def test_rc61_real_capture_validates_both_available_palettes():
    capture = (ROOT / 'scripts/capture_ui_screenshots.py').read_text(encoding='utf8')
    seed = (ROOT / 'scripts/seed_ui_documentation.py').read_text(encoding='utf8')
    assert 'Duplicate {kind} choices rendered by CIR' in capture
    assert 'spam-incident-config-labels' in capture
    assert "for kind in ('categories', 'data_types'):" in capture
    assert "('data_type', 'E-mail didattica')" in seed
    flow = (ROOT / '.github/workflows/ci-release.yml').read_text(encoding='utf8')
    assert 'Audit synthetic image provenance and build current visual training' in flow
    assert 'scripts/build_training_visual_rc64.js' in flow
    assert 'scripts/verify_visual_training_rc64.py' in flow
