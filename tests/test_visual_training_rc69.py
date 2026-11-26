"""RC69 editorial content and media evidence regressions."""
import hashlib
import json
from pathlib import Path
import pytest
from test_rc2_training_and_brochure_media import _validate_screenshot_receipt_rows

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'docs/presentation'


def test_repeated_screenshot_media_allowed_only_for_same_sha256():
    sha = hashlib.sha256(b'synthetic screenshot bytes').hexdigest()
    media = {'ppt/media/image11.jpg': sha}
    rows = [{'id':'registry-desktop','media_file':'ppt/media/image11.jpg','sha256':sha},
            {'id':'registry-closed-state','media_file':'ppt/media/image11.jpg','sha256':sha}]
    assert _validate_screenshot_receipt_rows(rows,media) == {'ppt/media/image11.jpg'}
    with pytest.raises(AssertionError):
        _validate_screenshot_receipt_rows([{**rows[0], 'sha256':'0'*64}],media)
    with pytest.raises(AssertionError):
        _validate_screenshot_receipt_rows([rows[0],{**rows[0]}],media)
    with pytest.raises(AssertionError):
        _validate_screenshot_receipt_rows(rows,media,{'ppt/media/image11.jpg'})


def test_incident_opening_addendum_covers_both_paths_and_administrator_crud():
    src=json.loads((P/'visual_rc69_addendum.json').read_text())
    assert src['insert_after_original'] == 14
    assert len(src['slides']) == 6
    assert [row['training_flow'] for row in src['slides']] == [
        'incident-entry', 'incident-blank', 'incident-model',
        'incident-admin', 'incident-from-existing', 'incident-template'
    ]
    assert [row['index'] for row in src['slides']] == list(range(80,86))
    names=' '.join(x['title'] for x in src['slides']).lower()
    bullets=' '.join(' '.join(x['bullets']) for x in src['slides']).lower()
    for term in ('dalla pagina principale','da zero','modello','cancellazione'):
        assert term in names or term in bullets
    assert 'admin' in bullets and 'writer' in bullets and 'superuser' in bullets
    assert 'data e ora' in bullets and 'documenti' in bullets
    assert all(len(x['bullets'])==4 for x in src['slides'])


def test_editable_schematics_provenance_and_ui_authorization_match_source():
    src=(ROOT/'scripts/build_training_visual_rc64.js').read_text()
    assert 'incidentTrainingRight(slide,d,accent)' in src
    assert 'boxNode(slide' in src
    assert "ciById.get('registry-desktop')" in src
    art=json.loads((P/'visual_rc69_art/provenance.json').read_text())['artwork'][0]
    assert art['human_people'] is False
    assert hashlib.sha256((ROOT/art['file']).read_bytes()).hexdigest()==art['sha256']
    routes=(ROOT/'app/routes.py').read_text()
    assert "return user_role_for_tenant() in ['superuser','admin','writer']" in routes
    assert "return user_role_for_tenant() in ['superuser','admin']" in routes
    assert "@bp.route('/admin/incident-templates'" in routes
    assert "@bp.route('/incident/new'" in routes


def test_ci_validator_matches_reordered_real_slide_76():
    verifier=(ROOT/'scripts/verify_visual_training_rc64.py').read_text()
    from scripts.verify_visual_training_rc64 import (EXPECTED_SLIDES, PALETTE_SLIDE,
        ARCH_SLIDES, ADDED_SLIDES, WORKFLOW_INTRO_SLIDES, APPENDIX_PREVIEWS, APPENDIX_BANNER_SLIDES, THANK_YOU_SLIDES)
    assert 'EXPECTED_SLIDES = 79 + ADDED_SLIDES + ARCH_SLIDES + WORKFLOW_INTRO_SLIDES + THANK_YOU_SLIDES + APPENDIX_BANNER_SLIDES + APPENDIX_PREVIEWS' in verifier
    assert 'PALETTE_SLIDE = 70 + ADDED_SLIDES + ARCH_SLIDES + WORKFLOW_INTRO_SLIDES' in verifier
    assert EXPECTED_SLIDES == 79 + ADDED_SLIDES + ARCH_SLIDES + WORKFLOW_INTRO_SLIDES + THANK_YOU_SLIDES + APPENDIX_BANNER_SLIDES + APPENDIX_PREVIEWS
    assert PALETTE_SLIDE == 85
    assert 'linked_slide_image_digests(archive, PALETTE_SLIDE)' in verifier
