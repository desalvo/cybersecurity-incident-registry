"""RC98: reproducible English visual deck, same-run screenshot integrity, and CI publication."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile
import pytest

from scripts.verify_visual_training_en import verify
from scripts.verify_visual_training_rc64 import linked_slide_image_digests
from scripts.published_visual_training import BASE_SLIDES, GALLERY_FIRST_SLIDE, HIDDEN_GALLERY_IDS

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'docs/presentation'


def test_published_editorial_en_matches_italian_slide_and_pdf_counts():
    italian=P/'CIR_Operational_Training_Visual.pptx'
    english=P/'CIR_Operational_Training_Visual_EN.pptx'
    pdf=P/'CIR_Operational_Training_Visual_EN.pdf'
    if not (italian.is_file() and english.is_file() and pdf.is_file()):
        pytest.skip('RC102 publishes generated binaries in GitHub Releases; CI verifies the fresh PPTX/PDF')
    out=verify(english,pdf,italian_pptx=italian)
    with ZipFile(italian) as z:
        count=len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml') and '/_rels/' not in n])
    assert out['slides']==count==118
    assert out['pdf_pages']==count
    assert BASE_SLIDES==100 and GALLERY_FIRST_SLIDE==99


def test_english_localization_files_are_complete_and_reproducible():
    slides=json.loads((P/'visual_rc98_english_slides.json').read_text())['slides']
    labels=json.loads((P/'visual_rc98_english_labels.json').read_text())
    assert len(slides)==95 and len(labels)>180
    assert 'cross-tenant' in ' '.join(slides['32']).lower()
    assert 'default workflow' in ' '.join(slides['50']).lower()
    assert 'more variables' in ' '.join(slides['63']).lower()
    assert "comic" in labels["Una pausa cartoon prima del prossimo capitolo"].lower()
    js=(ROOT/'scripts/build_training_visual_rc64.js').read_text()
    assert 'CIR_TRAINING_LOCALE' in js and 'visual_rc98_english_slides.json' in js
    assert 'comicCaption' in js and "pptx.lang=english?'en-US':'it-IT'" in js


def test_bilingual_ci_installs_both_document_pairs_and_seals_same_manifest():
    flow=(ROOT/'.github/workflows/ci-release.yml').read_text()
    assert 'Build, validate and seal English visual training' in flow
    assert 'scripts/verify_visual_training_en.py' in flow
    assert '--locale en' in flow
    assert flow.count('CIR_Operational_Training_Visual_EN.pptx')>=2
    assert flow.count('CIR_Operational_Training_Visual_EN.pdf')>=2
    stage=(ROOT/'scripts/training_release_assets.py').read_text()
    assert 'visual-training-en-receipt.json' in stage
    assert 'CIR_Operational_Training_Visual_EN.pdf' in stage
    assert 'training_release_assets.py' in flow
    assert 'publish_training_release.sh' in flow


def test_bilingual_sync_fails_closed_on_incomplete_english_documents(tmp_path):
    from scripts.sync_current_documentation import sync
    root=tmp_path/'repo';dest=root/'docs/presentation';dest.mkdir(parents=True)
    it=tmp_path/'it.pptx';pdf=tmp_path/'it.pdf';en=tmp_path/'en.pptx'
    for item in (it,pdf,en): item.write_bytes(b'x'*3001)
    with pytest.raises(ValueError,match='must be supplied together'):
        sync(root,it,pdf,pptx_en=en)


def test_published_english_deck_keeps_exact_archived_screenshot_bytes():
    import re
    archive=ROOT/'app/static/help/ui-runtime'
    pictures=sorted(p for p in archive.glob('*.png') if p.stem not in HIDDEN_GALLERY_IDS)
    pictures+=sorted(p for p in archive.glob('*.jpg') if p.stem not in HIDDEN_GALLERY_IDS)
    if not (P/'CIR_Operational_Training_Visual_EN.pptx').is_file():
        pytest.skip('RC102 externally publishes live screenshots in GitHub Releases')
    with ZipFile(P/'CIR_Operational_Training_Visual_EN.pptx') as en:
        for i,pic in enumerate(sorted(pictures,key=lambda p:p.name)):
            assert hashlib.sha256(pic.read_bytes()).hexdigest() in linked_slide_image_digests(en,GALLERY_FIRST_SLIDE+i)


@pytest.fixture(scope='module')
def disposable_manifest_for_en(tmp_path_factory):
    """Artificial image fixtures for regression only. Never real CI evidence."""
    if not shutil.which('node') or not shutil.which('libreoffice'):
        pytest.skip('Node or LibreOffice unavailable')
    from PIL import Image
    from tests.rc87_test_visual_fixtures import generated_pdf_preview
    from tests.test_visual_training_rc68 import CAPTURE_IDS
    d=tmp_path_factory.mktemp('rc98-fake-ui-fixture')
    screenshots=[]
    for n,ident in enumerate(CAPTURE_IDS):
        pic=d/(ident+'.jpg')
        Image.new('RGB',(620+2*n,310+n),(24+n*4,40+n*4,75+n*3)).save(pic)
        screenshots.append({'id':ident,'file':pic.name,'sha256':hashlib.sha256(pic.read_bytes()).hexdigest()})
    preview=generated_pdf_preview(d)
    manifest=d/'manifest.json'
    manifest.write_text(json.dumps({'source_kind':'real-application-browser',
       'data_provenance':'isolated-synthetic-fixture',
       'source_commit':'a'*40,'build':'20261126',
       'screenshots':screenshots,'generated_pdf_preview':preview}))
    return d,manifest,screenshots


def test_ci_english_same_run_screenshot_checksums_and_receipt(disposable_manifest_for_en):
    d,manifest,rows=disposable_manifest_for_en
    pptx=d/'fake_training_EN.pptx'
    env={**os.environ,'CIR_TRAINING_LOCALE':'en','CIR_SCREENSHOT_MANIFEST':str(manifest),
      'CIR_REQUIRE_REAL_SCREENSHOTS':'1','GITHUB_SHA':'a'*40,
      'CIR_RELEASE_BUILD':'20261126','CIR_PYTHON':sys.executable}
    result=subprocess.run(['node',str(ROOT/'scripts/build_training_visual_rc64.js'),str(pptx)],
                          cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stderr
    pdf_folder=d/'pdf';pdf_folder.mkdir()
    result=subprocess.run(['libreoffice',f'-env:UserInstallation=file://{d}/lo',
         '--headless','--convert-to','pdf','--outdir',str(pdf_folder),str(pptx)],
         cwd=ROOT,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stderr
    pdf=pdf_folder/'fake_training_EN.pdf'
    checked=verify(pptx,pdf,manifest,strict=True)
    assert checked['slides'] == BASE_SLIDES + len(rows) - len(HIDDEN_GALLERY_IDS)
    assert checked['pdf_pages'] == checked['slides']
    assert checked['verified_browser_screenshots'] == len(rows)
    assert checked['pdf_screenshots_visually_verified'] == len(rows) - len(HIDDEN_GALLERY_IDS)
    # Audit the PDF pixels, not only the PPTX media links: the two Support
    # Tickets pages use a left-hand full capture plus a right-hand zoom.
    from scripts.verify_pdf_screenshot_gallery import verify as verify_gallery
    visible = [row for row in rows if row['id'] not in HIDDEN_GALLERY_IDS]
    assert verify_gallery(pdf, [manifest.parent / row['file'] for row in visible],
                          base_slides=GALLERY_FIRST_SLIDE - 1,
                          screenshot_ids=[row['id'] for row in visible]) == len(visible)
    from scripts.seal_visual_training import seal
    verified=d/'verification.json';verified.write_text(json.dumps(checked))
    receipt=seal(pptx,pdf,manifest,verified,d/'en-receipt.json',locale='en')
    assert receipt['locale']=='en' and receipt['pptx_file'].endswith('_EN.pptx')
    # Tampering with one input must fail even if the PPTX is unchanged.
    rows[0]['sha256']='0'*64
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()),'screenshots':rows}))
    with pytest.raises(ValueError,match='exact screenshot'):
        verify(pptx,pdf,manifest,strict=True)


def test_italian_slides_are_the_only_structural_master():
    """Every English slide must refer to unchanged Italian source contents."""
    translated=json.loads((P/'visual_rc98_english_slides.json').read_text(encoding='utf8'))
    assert translated['source_locale']=='it'
    assert len(translated['italian_master_fingerprints'])==96
    assert all(len(v)==64 for v in translated['italian_master_fingerprints'].values())
    result=subprocess.run(['node',str(ROOT/'scripts/build_training_visual_rc64.js'),
        str(P/'not-written.pptx')],cwd=ROOT,
        env={**os.environ,'CIR_DUMP_ITALIAN_MASTER_FINGERPRINTS':'1'},
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    actual=json.loads(result.stdout)
    assert len(actual)==96
    assert translated['italian_master_fingerprints']==actual


def test_english_deck_fails_closed_when_italian_master_changes(tmp_path):
    """A change to the Italian title must invalidate the EN source mapping."""
    italian=json.loads((P/'visual_rc64_spec.json').read_text(encoding='utf8'))
    italian[1]['title'] += ' (CONTENUTO ITALIANO MODIFICATO)'
    changed=tmp_path/'changed_italian_master.json'
    changed.write_text(json.dumps(italian,ensure_ascii=False),encoding='utf8')
    dest=tmp_path/'must-not-exist_EN.pptx'
    result=subprocess.run(['node',str(ROOT/'scripts/build_training_visual_rc64.js'),str(dest)],
        cwd=ROOT,env={**os.environ,'CIR_TRAINING_LOCALE':'en','CIR_SPEC':str(changed)},
        capture_output=True,text=True,timeout=25)
    assert result.returncode!=0
    assert 'Italian master slide' in result.stderr
    assert not dest.exists()


def test_italian_source_changes_do_not_require_english_when_building_italian(tmp_path):
    """EN localizations cannot replace or constrain the authoritative IT deck."""
    italian=json.loads((P/'visual_rc64_spec.json').read_text(encoding='utf8'))
    italian[1]['title'] += ' (NUOVA VERSIONE ITALIANA)'
    changed=tmp_path/'updated_it.json'
    changed.write_text(json.dumps(italian,ensure_ascii=False),encoding='utf8')
    result=subprocess.run(['node',str(ROOT/'scripts/build_training_visual_rc64.js'),str(tmp_path/'it.pptx')],
        cwd=ROOT,env={**os.environ,'CIR_TRAINING_LOCALE':'it','CIR_SPEC':str(changed)},
        capture_output=True,text=True,timeout=95)
    assert result.returncode==0,result.stderr
    assert (tmp_path/'it.pptx').exists()


def test_english_verification_rejects_tampered_italian_master_images(tmp_path):
    """EN may translate words, but must never diverge from the IT master images."""
    import io
    it=P/'CIR_Operational_Training_Visual.pptx'
    if not it.is_file():
        pytest.skip('RC102 tests same-run IT/EN bytes from CI staging, not committed binaries')
    copied=tmp_path/'modified-it.pptx'
    with ZipFile(it) as z, ZipFile(copied,'w') as out:
        changed=False
        for name in z.namelist():
            content=z.read(name)
            if name.startswith('ppt/media/') and not changed:
                content=content+b'!'
                changed=True
            out.writestr(name,content)
    assert changed
    with pytest.raises(ValueError,match='images must match'):
        verify(P/'CIR_Operational_Training_Visual_EN.pptx',
               P/'CIR_Operational_Training_Visual_EN.pdf',italian_pptx=copied)
