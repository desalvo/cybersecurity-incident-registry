"""RC64: shared defaults inheritance and slide-specific photo regression tests."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'docs/presentation'
SPEC=json.loads((P/'visual_rc64_spec.json').read_text(encoding='utf8'))
NEW=json.loads((P/'visual_rc64_art/provenance.json').read_text(encoding='utf8'))


def test_slide30_eliminates_implementation_detail():
    assert len(SPEC)==79
    assert len(SPEC[29]['bullets'])==3
    assert not any('L’eredità deve essere visibile' in t for t in SPEC[29]['bullets'])


def test_slide31_teaches_inheritance_and_override_with_editable_diagram():
    slide=SPEC[30]
    assert slide['right_diagram']=='tenant_inheritance'
    t=' '.join(slide['bullets']).lower()
    assert all(s in t for s in ('tenants default','override','tenant','valore condiviso'))
    assert not any(s in t for s in ('duplicati','rimapp', 'id storici'))
    js=(ROOT/'scripts/build_training_visual_rc64.js').read_text(encoding='utf8')
    assert 'tenantInheritanceDiagram(slide)' in js
    assert 'photoPanel(slide,d,{x:6.45,y:1.56,w:6.12,h:2.17})' in js
    assert 'Eredita i destinatari' in js
    assert 'Override locale:' in js


def test_related_slides_have_distinct_relevant_people_free_scenes():
    chosen=(31,33,41,42,79)
    digest=[]
    for num in chosen:
        s=SPEC[num-1]
        a=NEW['slides'][str(num)]
        assert s['photo_art']==a['file']
        assert a['real_people'] is False
        f=ROOT/a['file']
        assert f.is_file()
        digest.append(hashlib.sha256(f.read_bytes()).hexdigest())
        assert digest[-1]==a['sha256']
    assert len(set(digest))==len(chosen)


def test_rc64_provenance_validation_and_pptx_scene_integrity():
    cmd=[sys.executable,str(ROOT/'scripts/check_training_visual_sources_rc64.py')]
    proc=subprocess.run(cmd,capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    deck=P/'CIR_Operational_Training_Visual_RC64.pptx'
    pdf=P/'CIR_Operational_Training_Visual_RC64.pdf'
    if not deck.exists() or not pdf.exists():
        import pytest
        pytest.skip('Deck built in release step')
    cmd=[sys.executable,str(ROOT/'scripts/verify_visual_training_rc64.py'),'--pptx',str(deck),'--pdf',str(pdf)]
    proc=subprocess.run(cmd,capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    with ZipFile(deck) as z:
        slide31=ET.fromstring(z.read('ppt/slides/slide31.xml'))
        ns='{http://schemas.openxmlformats.org/drawingml/2006/main}'
        texts=' '.join((el.text or '') for el in slide31.iter(ns+'t'))
        assert 'TENANTS DEFAULT' in texts
        assert 'SEDE A' in texts and 'SEDE B' in texts
        assert 'Eredita i destinatari' in texts
        assert 'Override locale:' in texts


def test_ci_rebuilds_rc64_with_current_browser_artifacts():
    flow=(ROOT/'.github/workflows/ci-release.yml').read_text(encoding='utf8')
    assert 'check_training_visual_sources_rc64.py' in flow
    assert 'build_training_visual_rc64.js' in flow
    assert 'verify_visual_training_rc64.py' in flow
    assert 'CIR_REQUIRE_REAL_SCREENSHOTS' in flow
    assert 'CIR_Operational_Training_Visual_RC64.pptx' in flow
