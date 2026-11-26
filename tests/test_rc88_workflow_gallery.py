"""RC88: workflow-first teaching and complete authentic screenshot appendix.

Editor builds retain only historical application captures; CI builds must
include every sealed same-run screenshot, including both new preview captures.
The previous classic registry UI is never part of the teaching gallery.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from scripts.verify_visual_training_rc64 import (
    EXPECTED_SLIDES, HIDDEN_GALLERY_IDS, linked_slide_image_digests,
)
from scripts.published_visual_training import BASE_SLIDES
from scripts.training_image_roi import crop_region

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'scripts/build_training_visual_rc64.js'
DECK=ROOT/'docs/presentation/CIR_Operational_Training_Visual.pptx'
PDF=ROOT/'docs/presentation/CIR_Operational_Training_Visual.pdf'
ARCHIVE=ROOT/'app/static/help/ui-runtime'
DOC=ROOT/'docs/presentation/visual_rc88_workflow_intro.json'
TEXT='{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def _visible_text(archive: ZipFile, number: int) -> str:
    page=ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
    return ' '.join(node.text or '' for node in page.iter(TEXT))


def test_workflow_definitions_precede_the_spam_example():
    import json
    spec=json.loads(DOC.read_text(encoding='utf8'))
    assert spec['insert_after_original']==38
    assert [row['workflow_intro'] for row in spec['slides']]==[
        'workflow','categories','steps','conditions','dependencies']
    assert 'prima categoria' in ' '.join(spec['slides'][1]['bullets']).lower()
    assert 'predefinito' in ' '.join(spec['slides'][1]['bullets']).lower()
    src=SRC.read_text(encoding='utf8')
    assert "if(item.index===38)data.push(...workflowIntro.slides);" in src
    assert 'd.spam_intro_case' in src


def test_ci_gallery_requires_both_preview_captures_and_excludes_classic_ui():
    src=SRC.read_text(encoding='utf8')
    assert 'MANDATORY_GALLERY_IDS' in src
    assert "'pdf-generated-preview','notification-preview'" in src
    assert "new Set(['classic-registry-desktop'])" in src
    assert 'ciManifest.screenshots.filter(row=>!HIDDEN_GALLERY_IDS.has(row.id))' in src
    assert "GALLERY_ITEMS.entries()" in src
    assert 'generatedPdfPreview?.path' in src
    assert "id==='generated-pdf'" in src
    assert 'screenshot_manifest_sha256' in (ROOT/'scripts/published_visual_training.py').read_text(encoding='utf8')


def test_editorial_gallery_reuses_every_archived_screenshot_except_classic(tmp_path):
    if not DECK.is_file() or not PDF.is_file():
        import pytest
        pytest.skip('Source edition not generated in current checkout')
    files=sorted((p for p in ARCHIVE.iterdir() if p.is_file() and p.suffix.lower() in {'.png','.jpg'}
                  and p.stem not in HIDDEN_GALLERY_IDS),key=lambda p:p.name)
    assert len(files)>=15
    assert BASE_SLIDES==EXPECTED_SLIDES==96
    with ZipFile(DECK) as z:
        slides=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
        assert len(slides)==EXPECTED_SLIDES+len(files)
        assert 'Anteprima di un documento PDF compilato' in _visible_text(z,95)
        assert 'Anteprima di una notifica prima dell’invio' in _visible_text(z,96)
        for n,image in enumerate(files,start=EXPECTED_SLIDES+1):
            checksum=hashlib.sha256(image.read_bytes()).hexdigest()
            assert checksum in linked_slide_image_digests(z,n), (image.name,n)
            assert 'CATTURA CI DEL RUN' not in _visible_text(z,n)
        old=ARCHIVE/'classic-registry-desktop.png'
        assert old.exists()
        forbidden=hashlib.sha256(old.read_bytes()).hexdigest()
        all_refs=set()
        for number in range(1,len(slides)+1):
            all_refs.update(linked_slide_image_digests(z,number))
        assert forbidden not in all_refs


def test_step_card_and_category_zoom_are_deterministic_real_pixel_crops(tmp_path):
    if not DECK.is_file():
        import pytest
        pytest.skip('Source edition not built')
    from PIL import Image
    source=ARCHIVE/'spam-workflow-steps.png'
    with Image.open(source) as im:
        assert im.height>im.width
    with ZipFile(DECK) as z:
        step_refs=linked_slide_image_digests(z,61)
        category_refs=linked_slide_image_digests(z,85)
    for idx,pos in enumerate([.154,.294,.430,.565,.703,.838]):
        output=tmp_path/f'step-{idx}.png'
        crop_region(source,output,(pos,.108,.132,.112))
        assert hashlib.sha256(output.read_bytes()).hexdigest() in step_refs
    for idx,rect in enumerate([(.15,.555,.83,.100),(.15,.654,.83,.112)]):
        output=tmp_path/f'category-{idx}.png'
        crop_region(source,output,rect)
        assert hashlib.sha256(output.read_bytes()).hexdigest() in category_refs
