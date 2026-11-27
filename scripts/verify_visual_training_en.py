#!/usr/bin/env python3
"""Validate the bilingual visual training deck without accepting altered UI captures.

PPTX titles and notes are English; UI images are the same exact SHA-256-bound
browser captures as in the Italian version. English cartoon assets are derived
from the pinned Italian originals, with English dialogue inside the speech balloons.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pypdf import PdfReader
try:
    from scripts.published_visual_training import BASE_SLIDES, GALLERY_FIRST_SLIDE, HIDDEN_GALLERY_IDS
    from scripts.verify_visual_training_rc64 import linked_slide_image_digests
except ModuleNotFoundError:
    from published_visual_training import BASE_SLIDES, GALLERY_FIRST_SLIDE, HIDDEN_GALLERY_IDS
    from verify_visual_training_rc64 import linked_slide_image_digests

NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}

def _page_text(z, n):
    root = ET.fromstring(z.read(f'ppt/slides/slide{n}.xml'))
    return ' '.join((x.text or '') for x in root.findall('.//a:t', NS))

def verify(pptx: Path, pdf: Path, screenshot_manifest: Path | None = None, strict=False,
           metadata_root: Path | None=None, italian_pptx: Path | None=None):
    repo = metadata_root or Path(__file__).resolve().parents[1]
    en_source = json.loads((repo / 'docs/presentation/visual_rc98_english_slides.json').read_text(encoding='utf8'))['slides']
    manifest = json.loads(screenshot_manifest.read_text()) if screenshot_manifest else None
    if strict and not manifest:
        raise ValueError('English same-run training needs a real browser screenshot manifest')
    images = [r for r in manifest.get('screenshots', []) if r['id'] not in HIDDEN_GALLERY_IDS] if manifest else []
    with ZipFile(pptx) as z:
        if z.testzip():
            raise ValueError('Corrupted English PPTX')
        slides = [n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)]
        count = len(slides)
        if count < BASE_SLIDES or strict and count != BASE_SLIDES + len(images):
            raise ValueError('Invalid English visual training slide count: '+str(count))
        # The closing sign is translated INSIDE the approved cartoon PNG.
        # Validate its exact localized image SHA below, not a duplicate text box.
        if 'Appendices' not in _page_text(z, GALLERY_FIRST_SLIDE - 1):
            raise ValueError('English appendix divider is missing')
        if 'Completed PDF document' not in _page_text(z, count - 1) or 'Notification before sending' not in _page_text(z, count):
            raise ValueError('English final appendix preview pages are missing')
        for n in (3, 4, 10, 32, 49, 63, 74, 75, 78, 91, 95):
            title=en_source[str(n)][0]
            if title not in _page_text(z,n):
                raise ValueError(f'English instructional text missing at slide {n}: {title}')
        if ('CIR' not in _page_text(z,1) or
                'training' not in _page_text(z,1).lower()):
            raise ValueError('English cover is missing')
        if any(re.search(r'(?i)\b(?:materiale didattico|schermata completa|ingrandimento|perché cir|conclusioni|appendici)\b',
                         _page_text(z,n)) for n in range(1,BASE_SLIDES+1)):
            raise ValueError('Italian slide chrome leaked into English training')
        for n in range(1, count+1):
            note=f'ppt/notesSlides/notesSlide{n}.xml'
            if note not in z.namelist():
                raise ValueError('Missing speaker notes on English slide '+str(n))
        if strict:
            if manifest.get('source_kind') != 'real-application-browser' or manifest.get('data_provenance') != 'isolated-synthetic-fixture':
                raise ValueError('English deck needs the verified real-application CI screenshots')
            for i, row in enumerate(images):
                source=(screenshot_manifest.parent / row['file']).resolve()
                if not source.is_relative_to(screenshot_manifest.parent.resolve()) or not source.is_file():
                    raise ValueError('Missing or unsafe source screenshot: '+row['id'])
                digest=hashlib.sha256(source.read_bytes()).hexdigest()
                if row['sha256'] != digest or digest not in linked_slide_image_digests(z,GALLERY_FIRST_SLIDE+i):
                    raise ValueError('English appendix does not embed exact screenshot: '+row['id'])
            # Required final notification screenshot is also directly visible.
            notification=next((r for r in images if r['id']=='notification-preview'),None)
            if notification and notification['sha256'] not in linked_slide_image_digests(z,count):
                raise ValueError('English notification preview does not show its verified screenshot')
    if italian_pptx is not None:
        # The Italian deck remains the canonical master. Only the nine
        # explicitly translated cartoons may differ; all genuine UI captures
        # and every other embedded image must remain byte-identical.
        with ZipFile(italian_pptx) as it_zip, ZipFile(pptx) as en_zip:
            it_slides = sum(bool(re.fullmatch(r'ppt/slides/slide\d+\.xml', n)) for n in it_zip.namelist())
            if it_slides != count:
                raise ValueError('Italian master and English deck have different slide counts')
            translated = json.loads((repo/'docs/presentation/rc99_cartoon_en/provenance.json').read_text(encoding='utf8'))['artwork']
            italian_art = json.loads((repo/'docs/presentation/rc97_cartoon/provenance.json').read_text(encoding='utf8'))['artwork']
            if [a['section'] for a in translated] != [a['section'] for a in italian_art]:
                raise ValueError('English cartoon order differs from the Italian master')
            positions={'01':2,'02':18,'03':37,'04':48,'05':64,'06':77,'07':90,'08':GALLERY_FIRST_SLIDE-1,'grazie':GALLERY_FIRST_SLIDE-2}
            for en_row,it_row in zip(translated,italian_art):
                if en_row['source_sha256'] != it_row['sha256']:
                    raise ValueError('English cartoon translation is stale: '+en_row['section'])
                source=repo/en_row['file']
                if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=en_row['sha256']:
                    raise ValueError('English cartoon SHA-256 mismatch: '+en_row['section'])
                if en_row['sha256'] not in linked_slide_image_digests(en_zip,positions[en_row['section']]):
                    raise ValueError('Missing localized English comic at '+en_row['section'])
                if it_row['sha256'] not in linked_slide_image_digests(it_zip,positions[it_row['section']]):
                    raise ValueError('Missing canonical Italian comic at '+it_row['section'])
            def image_multiset(z):
                return Counter(hashlib.sha256(z.read(name)).hexdigest()
                               for name in z.namelist() if name.startswith('ppt/media/'))
            it_images=image_multiset(it_zip)
            en_images=image_multiset(en_zip)
            for row in italian_art: it_images.pop(row['sha256'],None)
            for row in translated: en_images.pop(row['sha256'],None)
            if it_images != en_images:
                raise ValueError('Non-cartoon images must match the Italian master exactly')
    reader=PdfReader(str(pdf))
    if len(reader.pages)!=count:
        raise ValueError(f'English PDF/PPTX page mismatch: {len(reader.pages)} != {count}')
    # Fail if gallery pages have been replaced by blank placeholders in PDF.
    if strict:
        for i in range(len(images)):
            page=reader.pages[GALLERY_FIRST_SLIDE+i-1]
            obj=page.get('/Resources',{}).get('/XObject',{})
            if not obj:
                raise ValueError('PDF gallery page has no screenshot: '+str(GALLERY_FIRST_SLIDE+i))
    return {'status':'PASS','locale':'en','slides':count,'pdf_pages':len(reader.pages),
            'verified_browser_screenshots':len(manifest.get('screenshots', [])) if manifest else 0,
            'pdf_screenshots_visually_verified':len(images),
            'screenshot_manifest_sha256':hashlib.sha256(screenshot_manifest.read_bytes()).hexdigest() if screenshot_manifest else None}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pptx',required=True,type=Path)
    parser.add_argument('--pdf',required=True,type=Path)
    parser.add_argument('--screenshot-manifest',type=Path)
    parser.add_argument('--italian-pptx',type=Path)
    parser.add_argument('--require-ci-images',action='store_true')
    args=parser.parse_args()
    print(json.dumps(verify(args.pptx,args.pdf,args.screenshot_manifest,args.require_ci_images,italian_pptx=args.italian_pptx),indent=2))

if __name__=='__main__':main()
