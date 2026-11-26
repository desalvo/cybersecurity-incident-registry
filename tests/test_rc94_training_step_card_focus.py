"""Regressions: six complete workflow cards and documented notification variables."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pytest
from PIL import Image
from scripts.training_step_card_roi import step_card_regions
from scripts.training_image_roi import crop_region
from scripts.verify_visual_training_rc64 import linked_slide_image_digests

ROOT=Path(__file__).resolve().parents[1]
PIC=ROOT/'app/static/help/ui-runtime/spam-workflow-steps.png'
DECK=ROOT/'docs/presentation/CIR_Operational_Training_Visual.pptx'
SPEC=ROOT/'docs/presentation/visual_rc64_spec.json'
TEXT='{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def test_all_six_archived_workflow_cards_are_complete_and_individual(tmp_path):
    with Image.open(PIC) as image:
        assert image.width == 1920 and image.height >= 1000
        for number, region in enumerate(step_card_regions(PIC), 1):
            x,y,w,h=region
            box=(round(x*image.width),round(y*image.height),
                 round((x+w)*image.width),round((y+h)*image.height))
            # The archival image's six card edges are at y=504..919; all six
            # individual crops must contain both the heading and final button.
            assert box[0] <= (294+(number-1)*259)+5
            assert box[1] <= 504
            assert box[2] >= 534+(number-1)*259
            assert box[3] >= 919
            dest=tmp_path/f'card-{number}.png'
            crop_region(PIC,dest,region)
            assert Image.open(dest).size[0] >= 230
            if DECK.exists():
                with ZipFile(DECK) as deck:
                    assert hashlib.sha256(dest.read_bytes()).hexdigest() in linked_slide_image_digests(deck,61)


def test_dom_measured_cards_allow_wrapped_grid_but_reject_clipping(tmp_path):
    test_source=tmp_path/'capture.png'
    Image.new('RGB',(900,1700),'white').save(test_source)
    # Real CSS layout at narrower viewports: three columns, two rows.
    cards=[[.01+(i%3)*.33,.01+(i//3)*.30,.31,.28] for i in range(6)]
    assert len(step_card_regions(test_source,{'step_card_rois':cards}))==6
    with pytest.raises(ValueError, match='clipped|small'):
        step_card_regions(test_source,{'step_card_rois':[[0,.01,.0002,.3],*cards[1:]]})
    with pytest.raises(ValueError, match='overlap'):
        step_card_regions(test_source,{'step_card_rois':[cards[0],cards[0],*cards[2:]]})
    with pytest.raises(ValueError, match='six'):
        step_card_regions(test_source,{'step_card_rois':cards[:5]})


def test_actual_browser_capture_records_six_individual_dom_regions():
    capture=(ROOT/'scripts/capture_ui_screenshots.py').read_text()
    assert 'capture[\'step_card_rois\'] = regions' in capture
    assert "if capture_id == \"workflow-steps-focused\":" in capture
    assert "cards.nth(n).bounding_box()" in capture


def test_slide_63_says_other_variables_are_documented_in_manual():
    spec=json.loads(SPEC.read_text())
    row=next(row for row in spec if row.get('original')==50)
    assert any('molte altre variabili' in s.lower() and 'manuale' in s.lower() for s in row['bullets'])
    assert 'manuale' in row['notes'].lower()
    if DECK.exists():
        with ZipFile(DECK) as pptx:
            page=ET.fromstring(pptx.read('ppt/slides/slide63.xml'))
            visible=' '.join(el.text or '' for el in page.iter(TEXT)).lower()
            assert 'molte altre variabili' in visible and 'manuale' in visible
