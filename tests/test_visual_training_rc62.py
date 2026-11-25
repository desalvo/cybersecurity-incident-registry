"""RC62 provenance and people-free synthetic visual regression tests."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
PRES=ROOT/'docs/presentation'
SPEC=json.loads((PRES/'visual_rc62_spec.json').read_text(encoding='utf8'))
PROV=json.loads((PRES/'visual_rc62_provenance.json').read_text(encoding='utf8'))


def test_people_free_visuals_use_original_synthetic_asset_and_native_diagrams():
    assert len(SPEC)==79
    replaced={28:'roles',33:'tenant_local',35:'matrix',42:'lifecycle',43:'governance'}
    for n,typ in replaced.items():
        assert SPEC[n-1]['synthetic_diagram']==typ
        assert not SPEC[n-1].get('conceptual_art')
    assert PROV['background']['contains_real_people'] is False
    assert PROV['background']['contains_human_silhouettes'] is False
    bg=ROOT/PROV['background']['path']
    assert hashlib.sha256(bg.read_bytes()).hexdigest()==PROV['background']['sha256']


def test_provenance_preflight_passes_and_rejects_unvetted_images():
    check=ROOT/'scripts/check_training_visual_sources_rc62.py'
    proc=subprocess.run([sys.executable,str(check)],capture_output=True,text=True)
    assert proc.returncode==0, proc.stderr
    assert json.loads(proc.stdout)['status']=='PASS'
    generator=(ROOT/'scripts/build_training_visual_rc62.js').read_text(encoding='utf8')
    assert 'Image provenance mismatch' in generator
    assert 'External media disallowed' in generator


def test_rc62_presentation_and_pdf_reject_retired_people_silhouettes():
    deck=PRES/'CIR_Operational_Training_Visual_RC62.pptx'
    pdf=PRES/'CIR_Operational_Training_Visual_RC62.pdf'
    verify=ROOT/'scripts/verify_visual_training_rc62.py'
    proc=subprocess.run([sys.executable,str(verify),'--pptx',str(deck),'--pdf',str(pdf)],capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)['slides']==79
    old=json.loads((PRES/'visual_rc61_art/provenance.json').read_text(encoding='utf8'))
    forbidden={old['slides'][str(n)]['sha256'] for n in PROV['replaced_illustrations']}
    with ZipFile(deck) as arch:
        hashes={hashlib.sha256(arch.read(n)).hexdigest() for n in arch.namelist() if n.startswith('ppt/media/') and not n.endswith('/')}
    assert not (hashes & forbidden)
    assert PROV['background']['sha256'] in hashes


def test_ci_uses_current_rc63_and_real_screenshots():
    flow=(ROOT/'.github/workflows/ci-release.yml').read_text(encoding='utf8')
    assert 'scripts/check_training_visual_sources_rc64.py' in flow
    assert 'scripts/build_training_visual_rc64.js' in flow
    assert 'scripts/verify_visual_training_rc64.py' in flow
    assert 'CIR_REQUIRE_REAL_SCREENSHOTS' in flow
    assert 'CIR_Operational_Training_Visual_RC71.pptx' in flow
