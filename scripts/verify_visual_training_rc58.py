#!/usr/bin/env python3
"""Independent visual-training QA; CI mode requires byte-identical real screenshots.

Does not require Flask, a running web server, or a slide-editing toolkit.  It
checks that the exact browser images from this run are embedded in the PPTX,
not merely that the screenshot paths were present in a manifest.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
REQUIRED_CI = ('registry-closed-state', 'pdf-mapping-configuration',
               'pdf-generated-preview', 'alfresco-settings-desktop',
               'alfresco-incident-documents')
REQUIRED_SLIDE_TITLES = {
    8: 'Login',
    17: 'Come cambia lo stato di un incidente: workflow generale (configurabile)',
    26: 'Sicurezza e tracciabilità dell\'applicazione',
    29: 'Cos’è un tenant',
    40: 'Workflow: selezione e import dal catalogo',
    45: 'Workflow: azioni e navigazione nell’incidente',
    48: 'Workflow: template notifiche e variabili',
    52: 'Mapping PDF: schermata di configurazione',
    59: 'AlBot: AI assistiva con RAG sanitizzato',
    77: 'Come rendere operativa l’applicazione',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_check(pptx, pdf, manifest, require_ci_images):
    if require_ci_images and manifest is None:
        raise ValueError('--require-ci-images richiede --screenshot-manifest')
    with ZipFile(pptx) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('PPTX corrotto: ' + bad)
        slides = [n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml', n)]
        if len(slides) != 79:
            raise ValueError(f'Numero slide inatteso: {len(slides)} anziche 79')
        for number, title in REQUIRED_SLIDE_TITLES.items():
            page = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            text = ''.join(node.text or '' for node in page.iter(NS+'t'))
            if title.replace('\u2019', '\u0027') not in text.replace('\u2019','\u0027'):
                raise ValueError(f'Slide {number}: manca il titolo {title!r}')
        media_digests = {
            hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith('ppt/media/') and not name.endswith('/')
        }
    # Only vetted application screenshots, locally generated CIR imagery and
    # verified same-run browser screenshots may enter the distributed deck.
    root = Path(__file__).resolve().parents[1]
    editorial_media = root / 'docs/presentation/visual_rc57_media'
    allowed = {digest(path) for path in editorial_media.iterdir() if path.is_file()}
    legacy = json.loads((root / 'docs/presentation/CIR_Visual_RC56_JPEG_Provenance.json').read_text(encoding='utf-8'))
    retired_ui = {row['jpeg_derivative_sha256'] for row in legacy['screenshots']
                  if row['id'].startswith('classic-')}
    if media_digests.intersection(retired_ui):
        raise ValueError('La presentazione contiene screenshot dell interfaccia classica')
    screenshot_count = None
    if manifest:
        manifest_path = Path(manifest).resolve()
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        if 'browser' not in str(data.get('source_kind', '')).lower():
            raise ValueError('Le screenshot non provengono da una acquisizione browser')
        records = data.get('screenshots') or []
        lookup = {row['id']: row for row in records}
        if len(lookup) != len(records):
            raise ValueError('ID di screenshot duplicati nel manifest')
        screenshot_count = len(records)
        for ident in REQUIRED_CI:
            if ident not in lookup:
                raise ValueError('Manca screenshot obbligatoria: '+ident)
            row = lookup[ident]
            path = (manifest_path.parent / row['file']).resolve()
            if not path.is_relative_to(manifest_path.parent):
                raise ValueError('Percorso screenshot esterno al manifest')
            if digest(path) != row['sha256']:
                raise ValueError('Checksum sorgente screenshot errato: ' + ident)
            allowed.add(row['sha256'])
            if require_ci_images and row['sha256'] not in media_digests:
                raise ValueError('Screenshot CI non incorporata nel PPTX: ' + ident)
    foreign = media_digests - allowed
    if foreign:
        raise ValueError(f'Media del PowerPoint senza provenienza CIR: {len(foreign)} file')
    pdf_pages = None
    if pdf:
        result = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True, check=True)
        pages = re.search(r'^Pages:\s*(\d+)\s*$', result.stdout, flags=re.MULTILINE)
        pdf_pages = int(pages.group(1)) if pages else -1
        if pdf_pages != 79:
            raise ValueError(f'PDF inaspettato: {pdf_pages} pagine invece di 79')
    summary = {'slides': len(slides), 'pdf_pages': pdf_pages,
               'verified_browser_screenshots': screenshot_count,
               'mandatory_ci_images_embedded': require_ci_images, 'status': 'PASS'}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pptx', type=Path, required=True)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--screenshot-manifest', type=Path)
    parser.add_argument('--require-ci-images', action='store_true')
    args = parser.parse_args()
    try:
        run_check(args.pptx, args.pdf, args.screenshot_manifest, args.require_ci_images)
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as exc:
        print('Visual training QA FAILED:', exc, file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
