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
REQUIRED_CI = ('workflow-steps-focused', 'statistics-desktop', 'assistant-panel-closeup',
               'tenant-setup-wizard-desktop', 'tenant-setup-wizard-panel', 'registry-closed-state', 'spam-incident-config-labels', 'pdf-mapping-configuration',
               'pdf-generated-preview', 'alfresco-settings-desktop',
               'alfresco-incident-documents','notification-preview','tenant-wizard-next-step')
ADDED_SLIDES = 6
INSERT_AFTER = 14
ARCH_SLIDES = 4  # three architecture diagrams plus the alert chapter
ARCH_AFTER = 6
APPENDIX_PREVIEWS = 2
APPENDIX_BANNER_SLIDES = 1
THANK_YOU_SLIDES = 1
WORKFLOW_INTRO_SLIDES = 5
WORKFLOW_AFTER = 38
ALBOT_AFTER = 60
ALBOT_ADDED_SLIDES = 1
SUPPORT_ADDED_SLIDES = 1
EXPECTED_SLIDES = 79 + ADDED_SLIDES + ARCH_SLIDES + WORKFLOW_INTRO_SLIDES + ALBOT_ADDED_SLIDES + SUPPORT_ADDED_SLIDES + THANK_YOU_SLIDES + APPENDIX_BANNER_SLIDES + APPENDIX_PREVIEWS
GALLERY_FIRST_SLIDE = EXPECTED_SLIDES - APPENDIX_PREVIEWS + 1
HIDDEN_GALLERY_IDS = frozenset({'classic-registry-desktop'})
PALETTE_SLIDE = 70 + ADDED_SLIDES + ARCH_SLIDES + WORKFLOW_INTRO_SLIDES + ALBOT_ADDED_SLIDES + SUPPORT_ADDED_SLIDES
LAB_SPAM_OPENING_SLIDE = 62 + ADDED_SLIDES + ARCH_SLIDES + WORKFLOW_INTRO_SLIDES + ALBOT_ADDED_SLIDES + SUPPORT_ADDED_SLIDES
REQUIRED_SLIDE_TITLES = {
    8: 'Login',
    17: 'Come cambia lo stato di un incidente: workflow generale (configurabile)',
    26: 'Sicurezza e tracciabilità dell\'applicazione',
    29: 'Cos’è un tenant',
    39: 'Esempio: dal workflow SPAM all',
    40: 'Workflow: selezione e import dal catalogo',
    45: 'Workflow: azioni e navigazione nell’incidente',
    48: 'Workflow: template notifiche e variabili',
    52: 'Mapping PDF: schermata di configurazione',
    59: 'AlBot: AI assistiva con RAG sanitizzato',
    77: 'Come rendere operativa l’applicazione',
}
REQUIRED_NEW_SLIDE_TITLES = {
    19: 'Aprire un incidente: dalla pagina principale',
    20: 'Aprire un incidente da zero: compilazione manuale',
    21: 'Modelli incidente: cosa sono, a cosa servono e permessi',
    22: 'Amministrare i modelli: creazione, modifica e cancellazione',
    23: 'Creare un modello da un incidente già registrato',
    24: 'Aprire un incidente usando un modello',
}


REQUIRED_ARCH_TITLES = {
    7: 'Plugin disponibili e possibilità di estensione',
    8: 'Da registro incidenti a workflow manager generico',
    9: 'Architettura CIR: componenti, piattaforme e funzioni',
    10: 'Alert, scadenze e promemoria operativi',
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


def verified_native_zoom(archive, slide_number, checksum):
    """Prove a highlighted callout is a native crop of this exact CI image.

    A decorative crop of another image is not sufficient.  The full image and
    cropped instance must refer to identical verified screenshot bytes.
    """
    from xml.etree import ElementTree as ET
    page = ET.fromstring(archive.read(f'ppt/slides/slide{slide_number}.xml'))
    rels = ET.fromstring(archive.read(f'ppt/slides/_rels/slide{slide_number}.xml.rels'))
    targets = {}
    for rel in rels.iter(PACKAGE_REL + 'Relationship'):
        if not rel.get('Type', '').endswith('/image') or rel.get('TargetMode') == 'External':
            continue
        target = rel.get('Target', '')
        name = (target.lstrip('/') if target.startswith('/') else
                posixpath.normpath(posixpath.join('ppt/slides', target)))
        if name.startswith('ppt/media/'):
            targets[rel.get('Id')] = hashlib.sha256(archive.read(name)).hexdigest()
    base = focus = 0
    graphic = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
    for pic in page.iter(graphic + 'pic'):
        blip = next(pic.iter(NS + 'blip'), None)
        if blip is None or targets.get(blip.get(OFFICE_REL + 'embed')) != checksum:
            continue
        cropped = next(pic.iter(NS + 'srcRect'), None)
        if cropped is None or not any(int(v) > 0 for v in cropped.attrib.values()):
            base += 1
        else:
            focus += 1
    text = ''.join(x.text or '' for x in page.iter(NS + 't'))
    return base >= 1 and focus >= 1 and 'INGRANDIMENTO' in text


# Editorial exports are intentionally permitted to show illustrative fallbacks.
# In strict same-run CI exports, those captions indicate that a screenshot was
# *not* integrated; blocking them prevents an apparently successful publication
# from leaving the user with a deck asking them to wait for a future CI run.
UNRESOLVED_CI_CAPTIONS = (
    'la screenshot reale sarà integrata dalla CI',
    'cattura reale richiesta alla CI',
    'Vista reale del Wizard integrata dalla CI',
    'ESEMPIO CIR · SCHERMATA EDITORIALE',
)


def reject_unresolved_ci_captions(archive, slide_names):
    for name in slide_names:
        xml = ET.fromstring(archive.read(name))
        visible = ''.join(node.text or '' for node in xml.iter(NS + 't'))
        if any(phrase.casefold() in visible.casefold()
               for phrase in UNRESOLVED_CI_CAPTIONS):
            raise ValueError('Screenshot CI non sostituita nella slide ' +
                             name.rsplit('/', 1)[-1])


def run_check(pptx, pdf, manifest, require_ci_images, published_ci_images=False):
    strict_images = require_ci_images or published_ci_images
    if strict_images and manifest is None:
        raise ValueError('--require-ci-images richiede --screenshot-manifest')
    with ZipFile(pptx) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('PPTX corrotto: ' + bad)
        slides = [n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml', n)]
        if strict_images:
            reject_unresolved_ci_captions(archive, slides)
        # A strict same-run build appends one visible screenshot gallery slide
        # for each visible application-browser capture; editorial builds have 91.
        if len(slides) < EXPECTED_SLIDES:
            raise ValueError(f'Numero slide inatteso: {len(slides)} (base {EXPECTED_SLIDES})')
        def visible_slide_text(number):
            slide = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            return ' '.join(node.text or '' for node in slide.iter(NS + 't'))
        if ('08' not in visible_slide_text(GALLERY_FIRST_SLIDE - 1) or
                'Appendici' not in visible_slide_text(GALLERY_FIRST_SLIDE - 1)):
            raise ValueError('Missing section 08 Appendici divider before screenshot gallery')
        if ('Documento PDF compilato' not in visible_slide_text(len(slides)-1) or
                'Notifica prima dell' not in visible_slide_text(len(slides))):
            raise ValueError('Dedicated PDF and notification previews must close the appendix')
        visible_gallery_size = len(slides) - EXPECTED_SLIDES
        expected_first = 'Schermata '+str(visible_gallery_size+1)
        expected_last = 'Schermata '+str(visible_gallery_size+2)
        if (expected_first not in visible_slide_text(len(slides)-1) or
                expected_last not in visible_slide_text(len(slides))):
            raise ValueError('Terminal preview screenshot numbers do not follow the full gallery')
        # Offline editorials intentionally restore every available historical
        # screenshot as a provenance-labelled gallery. Strict CI always uses
        # the entire sealed browser manifest instead.
        if not strict_images and not manifest:
            archived_dir = Path(__file__).resolve().parents[1] / 'app/static/help/ui-runtime'
            archived_rows = sorted((p for p in archived_dir.iterdir() if p.is_file() and p.suffix.lower() in {'.png','.jpg'} and p.stem not in HIDDEN_GALLERY_IDS), key=lambda p:p.name)
            expected_editorial = EXPECTED_SLIDES+len(archived_rows)
            if len(slides)!=expected_editorial:
                raise ValueError(f'Incomplete editorial gallery: {len(slides)} instead of {expected_editorial}')
            for idx,img in enumerate(archived_rows,start=GALLERY_FIRST_SLIDE):
                if digest(img) not in linked_slide_image_digests(archive,idx):
                    raise ValueError('Missing historical application screenshot from slide '+str(idx)+': '+img.name)
        for original_number, title in REQUIRED_SLIDE_TITLES.items():
            number = original_number + (ARCH_SLIDES if original_number > ARCH_AFTER else 0) + (ADDED_SLIDES if original_number > INSERT_AFTER else 0) + (WORKFLOW_INTRO_SLIDES if original_number > WORKFLOW_AFTER else 0) + (ALBOT_ADDED_SLIDES if original_number >= ALBOT_AFTER else 0) + (SUPPORT_ADDED_SLIDES if original_number >= ALBOT_AFTER else 0)
            page = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            text = ''.join(node.text or '' for node in page.iter(NS+'t'))
            if title.replace('\u2019', '\u0027') not in text.replace('\u2019','\u0027'):
                raise ValueError(f'Slide {number}: manca il titolo {title!r}')
        # AlBot is expressly designed to author/update tenant workflows.  The
        # visual-training gate must preserve the confirmation and JSON-only
        # paths, rather than checking only a historical assistant title.
        albot_title_slide = (59 + ARCH_SLIDES + ADDED_SLIDES + WORKFLOW_INTRO_SLIDES + ALBOT_ADDED_SLIDES)
        albot_text = visible_slide_text(albot_title_slide)
        rag_text = visible_slide_text(albot_title_slide - 1)
        if 'AlBot: AI assistiva con RAG sanitizzato' not in rag_text or 'sanitizzata' not in rag_text:
            raise ValueError('The original sanitized-RAG training slide must be retained')
        if 'AlBot: crea e aggiorna workflow con conferma' not in albot_text:
            raise ValueError('The workflow-authoring slide must follow the sanitized-RAG slide')
        support_text = visible_slide_text(albot_title_slide + 1)
        for required in ('Support Tickets', 'Supporto', 'super admin', 'Markdown', 'notifiche'):
            if required.casefold() not in support_text.casefold():
                raise ValueError('Missing Support Tickets usage teaching slide: ' + required)
        for required in ('creare o aggiornare workflow', 'dipendenze',
                         'conferma', 'JSON'):
            if required.casefold() not in albot_text.casefold():
                raise ValueError(f'Slide {albot_title_slide}: manca informazione AlBot {required!r}')
        for number, title in {**REQUIRED_ARCH_TITLES, **REQUIRED_NEW_SLIDE_TITLES,
                              **{49:'Che cos',50:'Categorie: come si classifica',
                                 51:'Step: i passaggi operativi',52:'Condizioni: quando',
                                 53:'Dipendenze: risorse e prerequisiti'}}.items():
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
        lab_opening_digests = linked_slide_image_digests(archive, LAB_SPAM_OPENING_SLIDE)
    # RC88: validate the ordered teaching introduction without weakening CI provenance.
    workflow_intro = json.loads((Path(__file__).resolve().parents[1] / 'docs/presentation/visual_rc88_workflow_intro.json').read_text(encoding='utf8'))
    if workflow_intro.get('insert_after_original') != WORKFLOW_AFTER or len(workflow_intro.get('slides', [])) != WORKFLOW_INTRO_SLIDES or [row.get('workflow_intro') for row in workflow_intro['slides']] != ['workflow','categories','steps','conditions','dependencies']:
        raise ValueError('Incomplete RC88 workflow terminology introduction')
    # Lossless callout crops are deterministic descendants of two originals.
    # Reconstruct exact output PNG hashes rather than allowing arbitrary media.
    from tempfile import TemporaryDirectory
    try:
        from scripts.training_image_roi import crop_region
    except ModuleNotFoundError:
        from training_image_roi import crop_region
    def add_full_width_rois(source: Path, kind: str) -> None:
        from PIL import Image
        with Image.open(source) as src:
            tall=src.height>src.width*1.28
        if kind=='steps':
            try:
                from scripts.training_step_card_roi import step_card_regions
            except ModuleNotFoundError:
                from training_step_card_roi import step_card_regions
            metadata = None
            if manifest and manifest_path.is_file():
                rows = json.loads(manifest_path.read_text(encoding='utf8')).get('screenshots', [])
                metadata = next((row for row in rows if row.get('id')=='workflow-steps-focused'
                                 and (manifest_path.parent/row.get('file','')).resolve()==source.resolve()), None)
            regions=step_card_regions(source,metadata)
        else:
            regions=([(.15,.555,.83,.100),(.15,.654,.83,.112)] if tall else
                     [(.01,.01,.98,.47),(.01,.48,.98,.50)])
        checksums=set()
        with TemporaryDirectory() as temp:
            for idx,region in enumerate(regions):
                dest=Path(temp)/(str(idx)+'.png')
                crop_region(source,dest,region)
                checksums.add(digest(dest))
        allowed.update(checksums)
        return checksums
    def add_original_rois(source: Path, kind: str) -> None:
        from PIL import Image
        with Image.open(source) as src:
            tall=src.height>src.width*1.28
        if kind=='steps':
            regions=([(.16,.098,.40,.118),(.56,.098,.41,.118)] if tall else
                     [(.00,.01,.52,.83),(.47,.01,.53,.83)])
        else:
            regions=([(.15,.558,.82,.108),(.15,.664,.82,.106)] if tall else
                     [(.01,.02,.98,.46),(.01,.50,.98,.48)])
        with TemporaryDirectory() as temp:
            for idx,region in enumerate(regions):
                output=Path(temp)/(str(idx)+'.png')
                crop_region(source,output,region)
                allowed.add(digest(output))
    # Only vetted application screenshots, locally generated CIR imagery and
    # verified same-run browser screenshots may enter the distributed deck.
    root = Path(__file__).resolve().parents[1]
    editorial_media = root / 'docs/presentation/visual_rc57_media'
    allowed = {digest(path) for path in editorial_media.iterdir() if path.is_file()}
    # Offline preview may show already checked-in UI captures, but it is not
    # same-run CI evidence. Strict CI never uses this archive fallback.
    if not strict_images and not manifest:
        archived = root / 'app/static/help/ui-runtime'
        allowed.update(digest(path) for path in archived.iterdir()
                       if path.is_file() and path.suffix.lower() in {'.png', '.jpg'})
    if not strict_images and not manifest:
        archived = root / 'app/static/help/ui-runtime'
        add_original_rois(archived/'spam-workflow-steps.png','categories')
        add_full_width_rois(archived/'spam-workflow-steps.png','steps')
        add_full_width_rois(archived/'spam-workflow-steps.png','categories')
        add_original_rois(archived/'spam-workflow-steps.png','steps')
    approved_document = root / 'docs/presentation/rc95_user_supplied/data_breach_notification_anonymized.png'
    approved_hash = '17898ab5874ae15ded91a0c8f2d022402eac9f6c5d212bd72b24dd213965a9ce'
    if digest(approved_document) != approved_hash:
        raise ValueError('Approved anonymized document preview checksum mismatch')
    allowed.add(approved_hash)
    cartoon_data=json.loads((root/'docs/presentation/rc97_cartoon/provenance.json').read_text(encoding='utf8'))
    cartoons=cartoon_data.get('artwork',[])
    if len(cartoons)!=9 or [row.get('section') for row in cartoons] != [f'{i:02d}' for i in range(1,9)]+['grazie']:
        raise ValueError('Missing or unordered RC97 banner/thank-you illustrations')
    banner_positions={'01':2,'02':18,'03':37,'04':48,'05':64,'06':78,'07':91,'08':GALLERY_FIRST_SLIDE-1,'grazie':GALLERY_FIRST_SLIDE-2}
    with ZipFile(pptx) as image_archive:
        for row in cartoons:
            source=root/row['file']
            if not row['file'].startswith('docs/presentation/rc97_cartoon/') or row.get('real_people') is not False or row.get('contains_real_ui') is not False or digest(source)!=row['sha256']:
                raise ValueError('Invalid original cartoon SHA-256 or provenance: '+str(row.get('section')))
            if row['sha256'] not in linked_slide_image_digests(image_archive,banner_positions[row['section']]):
                raise ValueError('Approved cartoon not displayed in correct chapter: '+row['section'])
            allowed.add(row['sha256'])
    allowed.add(digest(root/'app/static/ai-chatbot/albot-avatar.png'))
    support_art = root/'docs/presentation/rc109_support_tickets_art.png'
    support_provenance = json.loads((root/'docs/presentation/rc109_support_tickets_provenance.json').read_text(encoding='utf8'))
    with ZipFile(pptx) as support_image_archive:
        support_image_digests = linked_slide_image_digests(support_image_archive, 76)
    if (support_provenance.get('file') != 'docs/presentation/rc109_support_tickets_art.png'
            or support_provenance.get('real_people') is not False
            or support_provenance.get('contains_real_ui') is not False
            or digest(support_art) != support_provenance.get('sha256')
            or support_provenance['sha256'] not in support_image_digests):
        raise ValueError('Missing or altered synthetic Support Tickets artwork on slide 76')
    allowed.add(support_provenance['sha256'])
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
            # The authenticated wizard replaces slide 33's editorial illustration
            # during strict CI generation. Its actual slide link is checked below.
            if not (n == 33 and strict_images):
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
    if arch_extra['insert_after_original'] != ARCH_AFTER or len(arch_extra['slides']) != ARCH_SLIDES - 1:
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
    # RC77 photographic architecture overview has separately recorded provenance.
    ecosystem = json.loads((root/'docs/presentation/visual_rc77_art/provenance.json').read_text(encoding='utf8'))
    if [row['kind'] for row in ecosystem['artwork']] != ['ecosystem']:
        raise ValueError('Architecture ecosystem illustration missing')
    for row in ecosystem['artwork']:
        if row['real_people'] is not False or row['contains_embedded_slide_chrome'] is not False:
            raise ValueError('Untrusted architecture artwork')
        if digest(root/row['file']) != row['sha256']:
            raise ValueError('Architecture artwork SHA-256 mismatch')
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
        if strict_images and (data.get('source_kind') != 'real-application-browser' or
                              data.get('data_provenance') != 'isolated-synthetic-fixture'):
            raise ValueError('Il manifest CI non dimostra browser reale su dati sintetici isolati')
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
        if strict_images:
            # The two new preview captures are mandatory members of the
            # FINAL, full-gallery appendix, not merely earlier illustrations.
            for required in ('pdf-generated-preview','notification-preview'):
                if required not in lookup or required in HIDDEN_GALLERY_IDS:
                    raise ValueError('Mandatory preview missing from complete browser gallery: '+required)
            add_original_rois(manifest_path.parent / lookup['workflow-steps-focused']['file'],'steps')
            chosen=(lookup['workflow-steps-focused'] if lookup['workflow-steps-focused'].get('step_card_rois') else lookup.get('spam-workflow-steps') or lookup['workflow-steps-focused'])
            required_step_rois=add_full_width_rois(manifest_path.parent / chosen['file'],'steps')
            required_category_rois=add_full_width_rois(manifest_path.parent / lookup['spam-incident-config-labels']['file'],'categories')
            with ZipFile(pptx) as linked:
                if not required_step_rois.issubset(linked_slide_image_digests(linked,61)):
                    raise ValueError('Step cards zoom does not use verified screenshot pixels in slide 61')
                if not required_category_rois.issubset(linked_slide_image_digests(linked, PALETTE_SLIDE)):
                    raise ValueError('Screenshot CI non collegata alla slide ' + str(PALETTE_SLIDE) + ': category focus crops')
            add_original_rois(manifest_path.parent / lookup['spam-incident-config-labels']['file'],'categories')
        # A generated PDF preview is separate from the browser screenshots.
        # It must be the rasterized page of an app-produced PDF, with two
        # independent hashes. Never treat it as an unverified arbitrary image.
        preview = data.get('generated_pdf_preview')
        if strict_images:
            if not isinstance(preview, dict) or preview.get('source_kind') != 'cir-generated-mapped-acroform':
                raise ValueError('Generated PDF preview evidence is required')
            for key, checksum_key, extension in (('pdf_file', 'pdf_sha256', '.pdf'),
                                                  ('png_file', 'png_sha256', '.png')):
                name = preview.get(key)
                checksum = preview.get(checksum_key)
                if (not isinstance(name, str) or not name or name.startswith('/') or
                        '..' in name.split('/') or '\\' in name or ':' in name or
                        not name.lower().endswith(extension) or
                        not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum)):
                    raise ValueError('Generated PDF preview path or hash invalid')
                if not published_ci_images:
                    # Same-run CI: verify the actual generated PDF and its PNG
                    # rather than merely trusting the manifest's hashes.
                    file = manifest_path.parent / name
                    if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(manifest_path.parent):
                        raise ValueError('Generated PDF preview file missing or outside manifest')
                    if digest(file) != checksum:
                        raise ValueError('Generated PDF preview SHA-256 mismatch')
            if published_ci_images:
                # On documentation PRs CI scratch assets are intentionally not
                # committed. The sealed source manifest and exact PPTX/PDF
                # artifact hashes are checked by check_published_receipt; the
                # preview raster MUST still be linked on the dedicated slide.
                try:
                    from scripts.published_visual_training import validate_published_pdf_preview
                except ModuleNotFoundError:
                    from published_visual_training import validate_published_pdf_preview
                # main() already requires check_published_receipt() to bind
                # this installed manifest to the original hashed manifest.
                # Keep run_check() reusable by isolated published-mode tests
                # which have no repository-wide original source file.
                validate_published_pdf_preview(data, data)
            elif not (manifest_path.parent / preview['pdf_file']).read_bytes().startswith(b'%PDF-'):
                raise ValueError('Generated PDF preview source is not a PDF')
            allowed.add(preview['png_sha256'])
            with ZipFile(pptx) as linked_archive:
                if preview['png_sha256'] not in linked_slide_image_digests(linked_archive, EXPECTED_SLIDES + len([r for r in records if r['id'] not in HIDDEN_GALLERY_IDS]) - 1):
                    raise ValueError('Generated PDF preview not visible on its dedicated appendix page')
                notify = lookup.get('notification-preview')
                if notify and notify['sha256'] not in linked_slide_image_digests(linked_archive, EXPECTED_SLIDES + len([r for r in records if r['id'] not in HIDDEN_GALLERY_IDS])):
                    raise ValueError('Notification preview not visible on its dedicated appendix page')
        screenshot_count = len(records)
        visible_records = [row for row in records if row['id'] not in HIDDEN_GALLERY_IDS]
        expected_count = EXPECTED_SLIDES + (len(visible_records) if strict_images else 0)
        if strict_images and len(slides) != expected_count:
            raise ValueError(f'Appendice screenshot CI incompleta: {len(slides)} slide, attese {expected_count}')
        if strict_images:
            with ZipFile(pptx) as linked_archive:
                for offset, row in enumerate(visible_records):
                    n = GALLERY_FIRST_SLIDE + offset
                    if row['sha256'] not in linked_slide_image_digests(linked_archive, n):
                        raise ValueError(f'Screenshot CI non visibile nella slide {n}: {row["id"]}')
        if strict_images:
            with ZipFile(pptx) as rich_archive:
                for slide, ident in ((12, 'login-desktop'),
                                     (15, 'registry-desktop'),
                                     (62 + WORKFLOW_INTRO_SLIDES, 'pdf-mapping-configuration'),
                                     (69 + WORKFLOW_INTRO_SLIDES, 'assistant-panel-closeup')):
                    if ident not in lookup or lookup[ident]['sha256'] not in linked_slide_image_digests(rich_archive, slide):
                        raise ValueError(f'Screenshot focalizzata non incorporata nella slide {slide}: {ident}')
                    if not verified_native_zoom(rich_archive, slide, lookup[ident]['sha256']):
                        raise ValueError(f'Callout zoom assente o non proveniente dalla cattura CI: slide {slide}, {ident}')
        for ident in REQUIRED_CI:
            if ident not in lookup:
                raise ValueError('Manca screenshot obbligatoria: '+ident)
            checksum = lookup[ident]['sha256']
            if strict_images and checksum not in media_digests:
                raise ValueError('Screenshot CI non incorporata nel PPTX: ' + ident)
            if strict_images and ident == 'spam-incident-config-labels':
                # The full-image screenshot is intentionally kept in the
                # final gallery. The learning slide uses 100%-pixel crops,
                # separately proven above by exact reconstructed SHA-256.
                if not required_category_rois.issubset(slide70_digests):
                    raise ValueError('Screenshot CI non collegata alla slide ' + str(PALETTE_SLIDE) + ': ' + ident)
                if checksum not in lab_opening_digests:
                    raise ValueError('Screenshot CI non collegata al laboratorio SPAM slide ' + str(LAB_SPAM_OPENING_SLIDE) + ': ' + ident)
    foreign = media_digests - allowed
    if foreign:
        sample = ', '.join(value[:12] for value in sorted(foreign)[:5])
        raise ValueError(f'Media del PowerPoint senza provenienza CIR: {len(foreign)} file (SHA-256: {sample})')
    pdf_pages = None
    if pdf:
        result = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True, check=True)
        pages = re.search(r'^Pages:\s*(\d+)\s*$', result.stdout, flags=re.MULTILINE)
        pdf_pages = int(pages.group(1)) if pages else -1
        expected_pages = len(slides)
        if pdf_pages != expected_pages:
            raise ValueError(f'PDF inaspettato: {pdf_pages} pagine invece di {expected_pages}')
    pdf_verified = 0
    if pdf and strict_images:
        try:
            from scripts.verify_pdf_screenshot_gallery import verify
        except ModuleNotFoundError:  # direct script execution without project on sys.path
            from verify_pdf_screenshot_gallery import verify
        pdf_verified = verify(Path(pdf), [manifest_path.parent / row['file'] for row in visible_records],
                              base_slides=GALLERY_FIRST_SLIDE - 1)
    summary = {'pdf_screenshots_visually_verified': pdf_verified, 'slides': len(slides), 'pdf_pages': pdf_pages,
               'verified_browser_screenshots': screenshot_count,
               'mandatory_ci_images_embedded': strict_images, 'status': 'PASS'}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pptx', type=Path, required=True)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--screenshot-manifest', type=Path)
    parser.add_argument('--require-ci-images', action='store_true')
    parser.add_argument('--published-receipt', type=Path,
                        help='Audit previously sealed CI images on a documentation PR')
    args = parser.parse_args()
    try:
        if args.published_receipt:
            if args.require_ci_images:
                raise ValueError('Published receipt and same-run CI modes are mutually exclusive')
            if args.screenshot_manifest is None:
                raise ValueError('--published-receipt requires --screenshot-manifest')
            from published_visual_training import check_published_receipt
            check_published_receipt(Path(__file__).resolve().parents[1], args.pptx, args.pdf,
                                    args.screenshot_manifest, args.published_receipt)
        run_check(args.pptx, args.pdf, args.screenshot_manifest, args.require_ci_images,
                  published_ci_images=bool(args.published_receipt))
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as exc:
        print('Visual training QA FAILED:', exc, file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
