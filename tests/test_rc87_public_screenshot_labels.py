"""RC87: reader-facing wording must not confuse image origin with CI provenance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_appendix_labels_application_as_source_without_losing_ci_provenance():
    js = (ROOT / 'scripts/build_training_visual_rc64.js').read_text(encoding='utf-8')
    assert "APPENDICE / SCREENSHOT AUTENTICHE DELL'APPLICAZIONE" in js
    assert 'APPENDICE / SCREENSHOT AUTENTICHE DELLA CI' not in js
    assert 'Screenshot browser originale della CI' in js
    assert 'SHA-256' in js


def test_classic_interface_is_excluded_from_public_gallery():
    js = (ROOT / 'scripts/build_training_visual_rc64.js').read_text(encoding='utf-8')
    assert "HIDDEN_GALLERY_IDS=new Set(['classic-registry-desktop'])" in js
    assert 'filter(row=>!HIDDEN_GALLERY_IDS.has(row.id))' in js
