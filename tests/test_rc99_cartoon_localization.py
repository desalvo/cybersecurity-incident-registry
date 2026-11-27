"""RC99: Italian cartoon master, English bubble text, and speaker assignment."""
from pathlib import Path
import hashlib,json
from zipfile import ZipFile
from scripts.verify_visual_training_rc64 import linked_slide_image_digests

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'docs/presentation/rc97_cartoon/provenance.json'
EN=ROOT/'docs/presentation/rc99_cartoon_en/provenance.json'
POS={'01':2,'02':18,'03':37,'04':48,'05':64,'06':76,'07':89,'08':96,'grazie':95}

def test_nine_english_cartoon_derivatives_pinned_to_it():
    italy=json.loads(ART.read_text())['artwork']
    en=json.loads(EN.read_text())['artwork']
    assert len(italy)==len(en)==9
    if not (ROOT/'docs/presentation/CIR_Operational_Training_Visual.pptx').is_file():
        import pytest
        pytest.skip('RC102: IT/EN PPTX artwork is checked against generated CI assets')
    with ZipFile(ROOT/'docs/presentation/CIR_Operational_Training_Visual.pptx') as it_deck, ZipFile(ROOT/'docs/presentation/CIR_Operational_Training_Visual_EN.pptx') as en_deck:
        for original,translated in zip(italy,en):
            assert original['section']==translated['section']
            assert original['sha256']==translated['source_sha256']
            assert translated['sha256']!=original['sha256']
            assert hashlib.sha256((ROOT/translated['file']).read_bytes()).hexdigest()==translated['sha256']
            assert original['sha256'] in linked_slide_image_digests(it_deck,POS[original['section']])
            assert translated['sha256'] in linked_slide_image_digests(en_deck,POS[original['section']])

def test_english_dialogue_and_ci_automatic_derivation():
    art=(ROOT/'scripts/localize_cartoon_en.py').read_text()
    assert 'Can I borrow your' in art
    assert 'The workflow, yes' in art or 'The workflow, sure' in art
    assert '112 steps!' in art
    flow=(ROOT/'.github/workflows/ci-release.yml').read_text()
    assert 'python scripts/localize_cartoon_en.py' in flow
    builder=(ROOT/'scripts/build_training_visual_rc64.js').read_text()
    assert 'rc99_cartoon_en/provenance.json' in builder
