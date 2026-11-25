"""RC63: photographic synthetic panels must contain no slide chrome or clipping."""
from pathlib import Path
import hashlib,json,subprocess,sys
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'docs/presentation'

def test_rc63_replaces_all_thematic_slide_like_composites():
    spec=json.loads((P/'visual_rc63_spec.json').read_text(encoding='utf8'))
    prov=json.loads((P/'visual_rc63_art/provenance.json').read_text(encoding='utf8'))
    required={3,4,5,6,7,28,29,30,31,32,33,34,35,39,40,41,42,43,44,70,73,75,76,77,78,79}
    assert len(spec)==79
    assert {int(k) for k in prov['slides']}==required
    for number in required:
        d=spec[number-1]
        assert d['photo_art'].startswith('docs/presentation/visual_rc63_art/')
        assert 'conceptual_art' not in d and 'synthetic_diagram' not in d
        assert prov['slides'][str(number)]['real_people'] is False
        im=ROOT/d['photo_art']
        assert hashlib.sha256(im.read_bytes()).hexdigest()==prov['slides'][str(number)]['sha256']

def test_rc63_audit_script_runs_and_ci_builds_current_deck():
    run=subprocess.run([sys.executable,str(ROOT/'scripts/check_training_visual_sources_rc63.py')],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    flow=(ROOT/'.github/workflows/ci-release.yml').read_text(encoding='utf8')
    for name in ('check_training_visual_sources_rc64.py','build_training_visual_rc64.js','verify_visual_training_rc64.py','CIR_Operational_Training_Visual_RC71.pptx'):
        assert name in flow
    js=(ROOT/'scripts/build_training_visual_rc63.js').read_text(encoding='utf8')
    assert 'imageSizingContain(img,6.37,1.55,6.28,5.08)' in js
    assert 'if(d.photo_art){' in js
    assert 'photoPanel(slide,d)' in js
    assert 'hash!==record.sha256' in js

def test_rc63_deck_passes_provenance_verification():
    deck=P/'CIR_Operational_Training_Visual_RC63.pptx'
    pdf=P/'CIR_Operational_Training_Visual_RC63.pdf'
    if not deck.exists() or not pdf.exists():
        import pytest
        pytest.skip('Packaged docs are built by the release workflow')
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/verify_visual_training_rc63.py'), '--pptx',str(deck),'--pdf',str(pdf)],capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)['slides']==79
