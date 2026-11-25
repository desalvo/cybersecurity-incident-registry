"""RC77 original architectural photograph and supported platform inventory."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
P = ROOT/'docs/presentation'
TXT = '{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def test_architecture_overview_provenance_and_content():
    arch = json.loads((P/'visual_rc71_architecture_addendum.json').read_text())
    assert arch['insert_after_original'] == 6
    assert len(arch['slides']) == 3
    d = arch['slides'][2]
    assert (d['index'], d['arch_visual']) == (88, 'ecosystem')
    content = ' '.join(d['bullets'])
    for name in ('Flask', 'Gunicorn', 'PostgreSQL', 'Docker', 'Podman', 'Kubernetes',
                 'OpenShift', 'Helm', 'amd64', 'arm64', 'AlBot', 'Alfresco'):
        assert name in content
    prov = json.loads((P/'visual_rc77_art/provenance.json').read_text())
    row = prov['artwork'][0]
    assert row['kind'] == 'ecosystem'
    assert row['real_people'] is False
    assert row['contains_embedded_slide_chrome'] is False
    assert hashlib.sha256((ROOT/row['file']).read_bytes()).hexdigest() == row['sha256']


def test_generated_deck_has_editable_architecture_overview_when_available():
    deck = P/'CIR_Operational_Training_Visual.pptx'
    if not deck.is_file():
        return
    with ZipFile(deck) as z:
        slides = [s for s in z.namelist() if s.startswith('ppt/slides/slide') and
                  s.endswith('.xml') and '/_rels/' not in s]
        assert len(slides) == 88
        xml = ET.fromstring(z.read('ppt/slides/slide9.xml'))
        all_text = ' '.join(el.text or '' for el in xml.iter(TXT))
        assert 'Architettura CIR' in all_text
        assert 'Docker / Podman' in all_text
        assert 'Kubernetes / Helm' in all_text
        assert 'OpenShift' in all_text
