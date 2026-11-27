"""RC97: original cartoon banners and closing thank-you slide.

Illustrations are explicitly separated from authenticated application
screenshots. A sealed CI run uses exactly these pinned cartoon files; source
images from the actual application remain manifest-authorized separately.
"""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from scripts.published_visual_training import BASE_SLIDES, GALLERY_FIRST_SLIDE
from scripts.verify_visual_training_rc64 import linked_slide_image_digests, EXPECTED_SLIDES

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT/'docs/presentation/rc97_cartoon/provenance.json'
DECK = ROOT/'docs/presentation/CIR_Operational_Training_Visual.pptx'
POSITIONS = {'01':2,'02':18,'03':37,'04':48,'05':64,'06':78,'07':91,'grazie':97,'08':98}
NS = '{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def test_nine_original_illustrations_pinned_and_complete():
    data=json.loads(ART.read_text(encoding='utf8'))
    rows=data['artwork']
    assert [x['section'] for x in rows] == ['01','02','03','04','05','06','07','08','grazie']
    for row in rows:
        img=ROOT/row['file']
        assert img.is_file()
        assert row['kind'].endswith('cartoon')
        assert row['real_people'] is False and row['contains_real_ui'] is False
        assert hashlib.sha256(img.read_bytes()).hexdigest()==row['sha256']


def test_editorial_deck_contains_the_eight_cartoon_banners_and_thank_you():
    assert BASE_SLIDES==EXPECTED_SLIDES==100
    assert GALLERY_FIRST_SLIDE==99
    rows=json.loads(ART.read_text(encoding='utf8'))['artwork']
    if not DECK.is_file():
        import pytest
        pytest.skip('RC102: generated banner deck is a GitHub Release asset, verified in the live CI job')
    with ZipFile(DECK) as deck:
        slides=[k for k in deck.namelist() if k.startswith('ppt/slides/slide') and k.endswith('.xml') and '/_rels/' not in k]
        assert len(slides)>=BASE_SLIDES
        for row in rows:
            assert row['sha256'] in linked_slide_image_digests(deck,POSITIONS[row['section']])
        def words(n):
            root=ET.fromstring(deck.read(f'ppt/slides/slide{n}.xml'))
            return ' '.join(node.text or '' for node in root.iter(NS))
        assert '07' in words(91) and 'Conclusioni' in words(91)
        assert '08' in words(98) and 'Appendici' in words(98)
        assert 'Grazie!' not in words(97)  # the sign belongs to the approved illustration
        assert 'Schermata 1' in words(99)
