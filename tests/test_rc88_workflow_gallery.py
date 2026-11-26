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
    import json
    from scripts.published_visual_training import check_published_receipt
    manifest=ARCHIVE/'manifest.json'
    receipt=ROOT/'docs/presentation/visual-training-receipt.json'
    published=manifest.is_file() and receipt.is_file()
    assert BASE_SLIDES==EXPECTED_SLIDES==97
    if published:
        # A documentation PR replaces the archived screenshots with a sealed
        # *different run*. Never compare those images with old history.
        check_published_receipt(ROOT,DECK,PDF,manifest,receipt)
        rows=json.loads(manifest.read_text(encoding='utf8'))['screenshots']
        files=[(ARCHIVE/row['file'],row['sha256']) for row in rows
               if row['id'] not in HIDDEN_GALLERY_IDS]
    else:
        files=[(p,hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(
            (p for p in ARCHIVE.iterdir() if p.is_file() and p.suffix.lower() in {'.png','.jpg'}
             and p.stem not in HIDDEN_GALLERY_IDS), key=lambda p:p.name)]
    assert len(files)>=15
    with ZipFile(DECK) as z:
        slides=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
        assert len(slides)==EXPECTED_SLIDES+len(files)
        assert '08' in _visible_text(z,95) and 'Appendici' in _visible_text(z,95)
        assert 'Documento PDF compilato' in _visible_text(z,len(slides)-1)
        assert 'Notifica prima' in _visible_text(z,len(slides))
        assert ('Schermata '+str(len(files)+1)) in _visible_text(z,len(slides)-1)
        assert ('Schermata '+str(len(files)+2)) in _visible_text(z,len(slides))
        for n,(image,checksum) in enumerate(files,start=96):
            assert image.is_file() and hashlib.sha256(image.read_bytes()).hexdigest()==checksum
            assert checksum in linked_slide_image_digests(z,n), (image.name,n)
            if not published:
                assert 'CATTURA CI DEL RUN' not in _visible_text(z,n)
        # The classic UI is intentionally invisible even when it is retained
        # as a technical screenshot in the publication manifest.
        classic=next((row for row in json.loads(manifest.read_text())['screenshots']
                      if row['id']=='classic-registry-desktop'),None) if published else None
        old=ARCHIVE/'classic-registry-desktop.png'
        assert classic is not None or old.exists()
        forbidden=classic['sha256'] if classic else hashlib.sha256(old.read_bytes()).hexdigest()
        all_refs=set()
        for number in range(1,len(slides)+1):
            all_refs.update(linked_slide_image_digests(z,number))
        assert forbidden not in all_refs


def test_step_card_and_category_zoom_are_deterministic_real_pixel_crops(tmp_path):
    if not DECK.is_file():
        import pytest
        pytest.skip('Source edition not built')
    import json
    from PIL import Image
    manifest=ARCHIVE/'manifest.json'
    if manifest.is_file():
        # On a published PR, both crops are made from authenticated images of
        # that run, rather than the obsolete spam-workflow-steps.png file.
        rows={row['id']:row for row in json.loads(manifest.read_text())['screenshots']}
        step_id='spam-workflow-steps' if 'spam-workflow-steps' in rows else 'workflow-steps-focused'
        source=ARCHIVE/rows[step_id]['file']
        categories=ARCHIVE/rows['spam-incident-config-labels']['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==rows[step_id]['sha256']
        assert hashlib.sha256(categories.read_bytes()).hexdigest()==rows['spam-incident-config-labels']['sha256']
    else:
        source=categories=ARCHIVE/'spam-workflow-steps.png'
    with ZipFile(DECK) as z:
        step_refs=linked_slide_image_digests(z,61)
        category_refs=linked_slide_image_digests(z,85)
    with Image.open(source) as im:
        tall=im.height>im.width*1.28
    positions=[.154,.294,.430,.565,.703,.838] if tall else [.02,.183,.346,.509,.672,.835]
    for idx,pos in enumerate(positions):
        output=tmp_path/f'step-{idx}.png'
        crop_region(source,output,(pos,.108 if tall else .015,.132 if tall else .163,.112 if tall else .95))
        assert hashlib.sha256(output.read_bytes()).hexdigest() in step_refs
    with Image.open(categories) as im:
        category_tall=im.height>im.width*1.28
    rois=([(.15,.555,.83,.100),(.15,.654,.83,.112)] if category_tall else
          [(.01,.01,.98,.47),(.01,.48,.98,.50)])
    for idx,rect in enumerate(rois):
        output=tmp_path/f'category-{idx}.png'
        crop_region(categories,output,rect)
        assert hashlib.sha256(output.read_bytes()).hexdigest() in category_refs
