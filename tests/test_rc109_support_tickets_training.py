"""RC109 course integrity: the two AlBot slides AND Support Tickets must coexist."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
ASSET=ROOT/'docs/presentation/rc109_support_tickets_art.png'
PROVENANCE=ROOT/'docs/presentation/rc109_support_tickets_provenance.json'
MASTER=ROOT/'docs/presentation/visual_rc109_support_tickets_addendum.json'


def _texts(archive,number):
    root=ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
    return ' '.join(n.text or '' for n in root.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'))


def test_support_art_is_original_synthetic_and_pinned():
    import hashlib
    prov=json.loads(PROVENANCE.read_text())
    assert prov['file']==str(ASSET.relative_to(ROOT))
    assert prov['real_people'] is False and prov['contains_real_ui'] is False
    assert hashlib.sha256(ASSET.read_bytes()).hexdigest()==prov['sha256']


def test_support_slide_follows_both_albot_teaching_slides():
    from scripts.verify_visual_training_rc64 import EXPECTED_SLIDES,GALLERY_FIRST_SLIDE
    assert EXPECTED_SLIDES==100 and GALLERY_FIRST_SLIDE==99
    assert 'Support Tickets' in MASTER.read_text()
    assert 'supportTicketsAddendum.slides' in (ROOT/'scripts/build_training_visual_rc64.js').read_text()


def test_support_slide_bilingual_source_is_anchored_to_italian_fingerprints():
    translated=json.loads((ROOT/'docs/presentation/visual_rc98_english_slides.json').read_text())
    assert len(translated['italian_master_fingerprints'])==96
    assert 'Support Tickets' in translated['slides']['76'][0]
    assert len(translated['slides'])==95
