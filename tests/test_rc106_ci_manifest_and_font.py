"""Regression safeguards for RC106: strict manifest identity and English fonts."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_rc67_verifier_receives_the_same_fixture_identity_and_rejects_mismatch():
    src = (ROOT / 'tests/test_visual_training_rc67.py').read_text(encoding='utf-8')
    assert 'text=True, env=env)' in src
    assert "env={**env, 'GITHUB_SHA': 'b' * 40}" in src
    assert "env={**env, 'CIR_RELEASE_BUILD': '20261127'}" in src
    verifier = (ROOT / 'scripts/verify_visual_training_rc64.py').read_text(encoding='utf-8')
    assert "('GITHUB_SHA', 'source_commit')" in verifier
    assert "('CIR_RELEASE_BUILD', 'build')" in verifier


def test_english_cartoon_has_a_checked_font_fallback_not_a_bitmap_placeholder():
    src = (ROOT / 'scripts/localize_cartoon_en.py').read_text(encoding='utf-8')
    ast.parse(src)
    assert 'fonts-comic-neue' in src
    assert 'DejaVuSans-Bold.ttf' in src
    assert 'ImageFont.truetype(path, 16)' in src
    assert 'ImageFont.load_default' not in src
    flow = (ROOT / '.github/workflows/ci-release.yml').read_text(encoding='utf-8')
    assert 'fonts-comic-neue fonts-dejavu-core' in flow
    assert 'ComicNeue-Bold.otf' in flow
