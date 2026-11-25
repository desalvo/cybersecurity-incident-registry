#!/usr/bin/env python3
"""Independent visual-training QA; CI mode requires byte-identical real screenshots.

Does not require Flask, a running web server, or a slide-editing toolkit.  It
checks that the exact browser images from this run are embedded in the PPTX,
not merely that the screenshot paths were present in a manifest.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
OFFICE_REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PACKAGE_REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
REQUIRED_CI = ('registry-closed-state', 'spam-incident-config-labels', 'pdf-mapping-configuration',
               'pdf-generated-preview', 'alfresco-settings-desktop',
               'alfresco-incident-documents')
ADDED_SLIDES = 6
INSERT_AFTER = 14
ARCH_SLIDES = 2
ARCH_AFTER = 6
EXPECTED_SLIDES = 79 + ADDED_SLIDES + ARCH_SLIDES
PALETTE_SLIDE = 70 + ADDED_SLIDES + ARCH_SLIDES
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
REQUIRED_NEW_SLIDE_TITLES = {
    17: 'Aprire un incidente: dalla pagina principale',
    18: 'Aprire un incidente da zero: compilazione manuale',
    19: 'Modelli incidente: cosa sono, a cosa servono e permessi',
    20: 'Amministrare i modelli: creazione, modifica e cancellazione',
    21: 'Creare un modello da un incidente già registrato',
    22: 'Aprire un incidente usando un modello',
}


REQUIRED_ARCH_TITLES = {
    7: 'Plugin disponibili e possibilità di estensione',
    8: 'Da registro incidenti a workflow manager generico',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linked_slide_image_digests(archive, slide_number):
    """Return only image bytes actually referenced by the requested slide.

    The PPTX can contain media files unrelated to the slide, so checking
    ppt/media/ alone is not sufficient to prove that the learner will see the
    browser evidence on slide 70.
    """
    slide_name = f'ppt/slides/slide{slide_number}.xml'
    page = ET.fromstring(archive.read(slide_name))
    linked_ids = {node.get(OFFICE_REL + 'embed') for node in page.iter(NS + 'blip')}
    rel_name = f'ppt/slides/_rels/slide{slide_number}.xml.rels'
    relations = ET.fromstring(archive.read(rel_name))
    hashes = set()
    for relation in relations.iter(PACKAGE_REL + 'Relationship'):
        if relation.get('Id') not in linked_ids or not relation.get('Type', '').endswith('/image'):
            continue
        if relation.get('TargetMode') == 'External':
            continue
        target = relation.get('Target', '')
        member = (target.lstrip('/') if target.startswith('/') else
                  posixpath.normpath(posixpath.join('ppt/slides', target)))
        if not member.startswith('ppt/media/'):
            raise ValueError(f'Slide {slide_number}: percorso media non valido: {member}')
        hashes.add(hashlib.sha256(archive.read(member)).hexdigest())
    return hashes


def run_check(pptx, pdf, manifest, require_ci_images):
    if require_ci_images and manifest is None:
        raise ValueError('--require-ci-images richiede --screenshot-manifest')
    with ZipFile(pptx) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('PPTX corrotto: ' + bad)
        slides = [n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml', n)]
        if len(slides) != EXPECTED_SLIDES:
            raise ValueError(f'Numero slide inatteso: {len(slides)} anziche {EXPECTED_SLIDES}')
        for original_number, title in REQUIRED_SLIDE_TITLES.items():
            number = original_number + (ARCH_SLIDES if original_number > ARCH_AFTER else 0) + (ADDED_SLIDES if original_number > INSERT_AFTER else 0)
            page = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            text = ''.join(node.text or '' for node in page.iter(NS+'t'))
            if title.replace('\u2019', '\u0027') not in text.replace('\u2019','\u0027'):
                raise ValueError(f'Slide {number}: manca il titolo {title!r}')
        for number, title in {**REQUIRED_ARCH_TITLES, **REQUIRED_NEW_SLIDE_TITLES}.items():
            page = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            text = ''.join(node.text or '' for node in page.iter(NS + 't'))
            if title.replace('’', "'") not in text.replace('’', "'"):
                raise ValueError(f'Slide {number}: missing incident-opening title {title!r}')
        media_digests = {
            hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith('ppt/media/') and not name.endswith('/')
        }
        # Only the target slide itself may prove that a specific piece of
        # CI evidence is visible; unused /ppt/media members do not count.
        slide70_digests = linked_slide_image_digests(archive, PALETTE_SLIDE)
    # Only vetted application screenshots, locally generated CIR imagery and
    # verified same-run browser screenshots may enter the distributed deck.
    root = Path(__file__).resolve().parents[1]
    editorial_media = root / 'docs/presentation/visual_rc57_media'
    allowed = {digest(path) for path in editorial_media.iterdir() if path.is_file()}
    art = root / 'docs/presentation/visual_rc61_art'
    art_provenance = json.loads((art/'provenance.json').read_text(encoding='utf8'))
    obsolete = {row['sha256'] for row in art_provenance['slides'].values()}
    if media_digests.intersection(obsolete):
        raise ValueError('Obsolete slide-like illustration with embedded header or footer found')
    prev_prov = json.loads((root/'docs/presentation/visual_rc63_art/provenance.json').read_text(encoding='utf8'))
    new_prov = json.loads((root/'docs/presentation/visual_rc64_art/provenance.json').read_text(encoding='utf8'))
    spec = json.loads((root/'docs/presentation/visual_rc64_spec.json').read_text(encoding='utf8'))
    if len(spec)!=79 or len(prev_prov['slides'])!=26 or set(new_prov['slides'])!={'31','33','41','42','79'}:
        raise ValueError('Incomplete photographic illustration catalog')
    for n,row in enumerate(spec,1):
        if not row.get('photo_art'):
            continue
        origin=new_prov if str(n) in new_prov['slides'] else prev_prov
        item=origin['slides'][str(n)]
        if item.get('real_people') is not False or row['photo_art'] != item['file']:
            raise ValueError('Invalid people-free photo provenance: '+str(n))
        source=root/item['file']
        if digest(source) != item['sha256']:
            raise ValueError('Image sha256 mismatch: '+str(n))
        allowed.add(item['sha256'])
        if n in (31,33,41,42,79) and item['sha256'] not in media_digests:
            raise ValueError('Updated thematic artwork not embedded: '+str(n))
    additional = json.loads((root/'docs/presentation/visual_rc69_art/provenance.json').read_text(encoding='utf8'))
    for row in additional['artwork']:
        if row['human_people'] is not False or row['contains_embedded_slide_chrome'] is not False:
            raise ValueError('Invalid synthetic incident-opening illustration')
        if digest(root/row['file']) != row['sha256']:
            raise ValueError('Incident-opening illustration SHA-256 mismatch')
        allowed.add(row['sha256'])
    extra = json.loads((root/'docs/presentation/visual_rc69_addendum.json').read_text(encoding='utf8'))
    if extra['insert_after_original'] != INSERT_AFTER or len(extra['slides']) != ADDED_SLIDES:
        raise ValueError('Incomplete incident-opening instructional addendum')
    arch_extra = json.loads((root/'docs/presentation/visual_rc71_architecture_addendum.json').read_text(encoding='utf8'))
    if arch_extra['insert_after_original'] != ARCH_AFTER or len(arch_extra['slides']) != ARCH_SLIDES:
        raise ValueError('Incomplete modular architecture chapter')
    modular_art=json.loads((root/'docs/presentation/visual_rc71_art/provenance.json').read_text(encoding='utf8'))
    if {x['kind'] for x in modular_art['artwork']} != {'modules','procedures'}:
        raise ValueError('Missing verified modular illustrations')
    for row in modular_art['artwork']:
        if row['real_people'] is not False or row['contains_embedded_slide_chrome'] is not False:
            raise ValueError('Invalid modular artwork provenance')
        source=root/row['file']
        if digest(source)!=row['sha256']:
            raise ValueError('Modular artwork hash mismatch')
        allowed.add(row['sha256'])
    # Chapter-cover art is separately pinned to its RC62 source, and is not
    # embedded in any right-panel thematic illustration.
    rc62 = json.loads((root/'docs/presentation/visual_rc62_provenance.json').read_text(encoding='utf8'))
    chapter_path = root/rc62['background']['path']
    if digest(chapter_path) != rc62['background']['sha256']:
        raise ValueError('Chapter artwork checksum mismatch')
    allowed.add(rc62['background']['sha256'])
    for name in ('example_report_page_1.png', 'example_report_page_2.png'):
        allowed.add(digest(art/name))
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
        records = data.get('screenshots')
        if not isinstance(records, list) or not records or len(records) > 80:
            raise ValueError('Manifest browser senza elenco screenshot valido')
        if require_ci_images:
            for env_name, manifest_key in (('GITHUB_SHA', 'source_commit'),
                                           ('CIR_RELEASE_BUILD', 'build')):
                expected = os.environ.get(env_name)
                if expected and str(data.get(manifest_key)) != expected:
                    raise ValueError(f'Manifest screenshot di un {manifest_key} diverso dalla build CI')
            if (data.get('source_kind') == 'real-application-browser' and
                    data.get('data_provenance') != 'isolated-synthetic-fixture'):
                raise ValueError('Il manifest CI non contiene dati sintetici isolati')
        lookup = {}
        seen_files = set()
        # The previous verifier allowlisted only the six mandatory images,
        # even though the deck correctly uses other real browser captures
        # (login, registry, workflows, manuals, assistant, etc.). Validate
        # *all* same-run captures before trusting their SHA-256 digests.
        for row in records:
            if not isinstance(row, dict):
                raise ValueError('Voce screenshot non valida nel manifest')
            ident, filename, checksum = row.get('id'), row.get('file'), row.get('sha256')
            if (not isinstance(ident, str) or
                    not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', ident) or
                    ident in lookup):
                raise ValueError('ID di screenshot invalido o duplicato nel manifest')
            if (not isinstance(filename, str) or not filename or
                    '\\' in filename or ':' in filename or
                    filename.startswith('/') or
                    '..' in filename.split('/') or
                    not filename.lower().endswith(('.png', '.jpg')) or
                    filename in seen_files):
                raise ValueError('Percorso screenshot invalido o duplicato: ' + ident)
            source = manifest_path.parent / filename
            if (any(part.is_symlink() for part in (source, *source.parents)
                    if part != manifest_path.parent and part.is_relative_to(manifest_path.parent)) or
                    not source.is_file()):
                raise ValueError('Screenshot mancante o collegamento non ammesso: ' + ident)
            path = source.resolve()
            if not path.is_relative_to(manifest_path.parent):
                raise ValueError('Percorso screenshot esterno al manifest')
            if (not isinstance(checksum, str) or
                    not re.fullmatch(r'[a-f0-9]{64}', checksum) or
                    digest(path) != checksum):
                raise ValueError('Checksum sorgente screenshot errato: ' + ident)
            seen_files.add(filename)
            lookup[ident] = row
            allowed.add(checksum)
        screenshot_count = len(records)
        for ident in REQUIRED_CI:
            if ident not in lookup:
                raise ValueError('Manca screenshot obbligatoria: '+ident)
            checksum = lookup[ident]['sha256']
            if require_ci_images and checksum not in media_digests:
                raise ValueError('Screenshot CI non incorporata nel PPTX: ' + ident)
            if require_ci_images and ident == 'spam-incident-config-labels' and checksum not in slide70_digests:
                raise ValueError('Screenshot CI non collegata alla slide ' + str(PALETTE_SLIDE) + ': ' + ident)
    foreign = media_digests - allowed
    if foreign:
        sample = ', '.join(value[:12] for value in sorted(foreign)[:5])
        raise ValueError(f'Media del PowerPoint senza provenienza CIR: {len(foreign)} file (SHA-256: {sample})')
    pdf_pages = None
    if pdf:
        result = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True, check=True)
        pages = re.search(r'^Pages:\s*(\d+)\s*$', result.stdout, flags=re.MULTILINE)
        pdf_pages = int(pages.group(1)) if pages else -1
        if pdf_pages != EXPECTED_SLIDES:
            raise ValueError(f'PDF inaspettato: {pdf_pages} pagine invece di {EXPECTED_SLIDES}')
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
