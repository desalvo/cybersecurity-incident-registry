#!/usr/bin/env python3
"""Validate editable presentation media against the same CI documentation batch.

No office application or presentation library is imported by the installer or
Docker build. ZIP/XML inspection verifies the actual embedded image bytes,
native slide text, native notes and the current release footer.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import posixpath
import re
import struct
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from release_metadata import read_release_metadata
from scripts.ui_documentation_evidence import EvidenceError, REQUIRED_SCREENSHOTS, _read_json, sha256

PRESENTATION_FILE = 'CIR_Operational_Training_IT.pptx'
PRESENTATION_RECEIPT = 'presentation-receipt.json'
MANUAL_PDFS = frozenset({
    'documentazione_utente.pdf', 'documentazione_amministrativa.pdf',
    'user_documentation_en.pdf', 'administrator_documentation_en.pdf', 'ADMIN_ALFRESCO.pdf',
})
MANUAL_PREVIEWS = {name: 'manual-first-page-' + Path(name).stem + '.png' for name in MANUAL_PDFS}
PRESENTATION_ARTIFACTS = frozenset({PRESENTATION_FILE, PRESENTATION_RECEIPT, *MANUAL_PREVIEWS.values()})
NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'pr': 'http://schemas.openxmlformats.org/package/2006/relationships',
}


def _xml(archive: ZipFile, name: str):
    try:
        return ET.fromstring(archive.read(name))
    except (ET.ParseError, KeyError) as exc:
        raise EvidenceError('Presentation XML is missing or invalid: ' + name) from exc


def _relationships(archive: ZipFile, part: str) -> dict[str, tuple[str, str]]:
    path = PurePosixPath(part)
    rels_name = str(path.parent / '_rels' / (path.name + '.rels'))
    result = {}
    for row in _xml(archive, rels_name).findall('pr:Relationship', NS):
        rid, target, kind = row.get('Id'), row.get('Target'), row.get('Type')
        if not rid or rid in result or not target or not kind or row.get('TargetMode') == 'External':
            raise EvidenceError('Presentation relationships must be unique and local')
        resolved = posixpath.normpath(posixpath.join(str(path.parent), target))
        if resolved.startswith('../') or resolved.startswith('/') or '\\' in resolved or ':' in resolved:
            raise EvidenceError('Presentation relationship escapes its package')
        result[rid] = (resolved, kind)
    return result


def _presentation_parts(archive: ZipFile, version: str, build: str, slide_count: int) -> set[str]:
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if len(entries) > 10000 or len(names) != len(set(names)):
        raise EvidenceError('Presentation archive has duplicate or excessive entries')
    if sum(entry.file_size for entry in entries) > 250 * 1024 * 1024:
        raise EvidenceError('Presentation archive is too large when expanded')
    for entry in entries:
        path = PurePosixPath(entry.filename)
        if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename or ':' in entry.filename
                or entry.file_size > 80 * 1024 * 1024 or entry.flag_bits & 1
                or path.suffix.lower() in {'.bin', '.exe', '.vba'}):
            raise EvidenceError('Presentation archive contains an unsafe entry')
    if {'[Content_Types].xml', 'ppt/presentation.xml', 'docProps/core.xml'} - set(names):
        raise EvidenceError('Presentation package is incomplete')
    for name in names:
        if name.endswith('.rels'):
            for row in _xml(archive, name).findall('pr:Relationship', NS):
                if row.get('TargetMode') == 'External':
                    raise EvidenceError('Presentation cannot depend on external resources')
    slides = sorted(name for name in names if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml', name))
    notes = {name for name in names if re.fullmatch(r'ppt/notesSlides/notesSlide[0-9]+\.xml', name)}
    if not slides or len(slides) != slide_count or len(notes) != slide_count:
        raise EvidenceError('Presentation slide or speaker-note count differs from receipt')
    presentation = _xml(archive, 'ppt/presentation.xml')
    presentation_rels = _relationships(archive, 'ppt/presentation.xml')
    visible_slides = []
    for row in presentation.findall('p:sldIdLst/p:sldId', NS):
        target = presentation_rels.get(row.get('{' + NS['r'] + '}id'))
        if target is None or not target[1].endswith('/slide'):
            raise EvidenceError('Presentation slide list contains an invalid relationship')
        visible_slides.append(target[0])
    if len(visible_slides) != slide_count or set(visible_slides) != set(slides):
        raise EvidenceError('Presentation receipt cannot rely on orphaned or hidden package slides')
    footer = version + ' · Build ' + build
    used_media = set()
    used_notes = set()
    for name in slides:
        slide = _xml(archive, name)
        native = [''.join(node.itertext()) for node in slide.findall('.//p:sp/p:txBody//a:t', NS)]
        text = ' '.join(' '.join(native).split())
        if len(native) < 2 or footer not in text or len(text.replace(footer, '').strip()) < 12:
            raise EvidenceError('Presentation needs editable text and the current version/build footer on every slide')
        relationships = _relationships(archive, name)
        note_targets = [target for target, kind in relationships.values() if kind.endswith('/notesSlide')]
        if len(note_targets) != 1 or note_targets[0] not in notes or note_targets[0] in used_notes:
            raise EvidenceError('Every presentation slide needs its own native speaker notes')
        note_name = note_targets[0]
        used_notes.add(note_name)
        note_text = ' '.join(node.text or '' for node in _xml(archive, note_name).findall('.//a:t', NS)).strip()
        if len(note_text) < 40:
            raise EvidenceError('Presentation speaker notes are missing or only placeholders')
        for blip in slide.findall('.//p:pic//a:blip', NS):
            relation = relationships.get(blip.get('{' + NS['r'] + '}embed'))
            if relation is None or not relation[1].endswith('/image') or not relation[0].startswith('ppt/media/'):
                raise EvidenceError('Presentation image is not embedded locally')
            used_media.add(relation[0])
    return used_media


def _embedded_hash(archive: ZipFile, media_file, expected_hash, used_media):
    if (not isinstance(media_file, str) or not re.fullmatch(r'ppt/media/[A-Za-z0-9_.-]+', media_file)
            or media_file not in used_media):
        raise EvidenceError('Presentation receipt refers to unused or unsafe media')
    try:
        import hashlib
        actual = hashlib.sha256(archive.read(media_file)).hexdigest()
    except KeyError as exc:
        raise EvidenceError('Presentation media is missing') from exc
    if actual != expected_hash:
        raise EvidenceError('Presentation embedded media checksum mismatch')


def validate_detached_presentation_receipt(
    paths: dict[str, Path], source_commit: str, manifest_hash: str,
    screenshot_evidence: dict, *, metadata_root: Path, deck_sha256: str,
) -> dict:
    """Validate the compact evidence left in a slim runtime Docker context.

    The full PowerPoint is verified *before* installation by validate_manuals()
    and validate_presentation(). Only after this check does .dockerignore omit
    it from the runtime image. This function checks the same-run receipt,
    screenshot hashes, PDF/preview bindings and deck checksum claim, but must
    never be presented as re-verification of absent PowerPoint bytes.
    """
    receipt = _read_json(paths[PRESENTATION_RECEIPT])
    metadata = read_release_metadata(metadata_root)
    if receipt.get('schema_version') != 1 or receipt.get('source_commit') != source_commit:
        raise EvidenceError('External presentation receipt belongs to another source commit or schema')
    if receipt.get('functional_version') != metadata.version or str(receipt.get('build')) != metadata.build:
        raise EvidenceError('External presentation release metadata differs from this build')
    if (receipt.get('real_screenshots') is not True or receipt.get('editable_text') is not True
            or receipt.get('speaker_notes') is not True):
        raise EvidenceError('External presentation receipt lacks provenance or editability evidence')
    if receipt.get('screenshot_manifest_sha256') != manifest_hash:
        raise EvidenceError('External presentation screenshot manifest checksum mismatch')
    if (receipt.get('file') != PRESENTATION_FILE
            or receipt.get('sha256') != deck_sha256
            or not re.fullmatch(r'[0-9a-f]{64}', deck_sha256)):
        raise EvidenceError('External presentation checksum differs from the installed publication receipt')
    count = receipt.get('slides')
    if type(count) is not int or not 5 <= count <= 250:
        raise EvidenceError('External presentation slide count is invalid')

    rows = receipt.get('screenshots')
    screenshot_hashes = {row['id']: row['sha256'] for row in screenshot_evidence['screenshots']}
    if not isinstance(rows, list) or len(rows) != len(REQUIRED_SCREENSHOTS):
        raise EvidenceError('External presentation screenshot list is incomplete')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or row.get('id') not in REQUIRED_SCREENSHOTS
                or row['id'] in seen or row.get('sha256') != screenshot_hashes.get(row['id'])
                or not isinstance(row.get('media_file'), str)
                or not re.fullmatch(r'ppt/media/[A-Za-z0-9_.-]+', row['media_file'])):
            raise EvidenceError('External presentation screenshot binding is invalid')
        seen.add(row['id'])

    pages = receipt.get('manual_first_pages')
    if not isinstance(pages, list) or len(pages) != len(MANUAL_PDFS):
        raise EvidenceError('External presentation manual preview list is incomplete')
    seen = set()
    for row in pages:
        if not isinstance(row, dict) or row.get('pdf') not in MANUAL_PDFS or row['pdf'] in seen:
            raise EvidenceError('External presentation manual preview reference is invalid')
        pdf = row['pdf']
        png = MANUAL_PREVIEWS[pdf]
        seen.add(pdf)
        if (row.get('page') != 1 or type(row.get('page')) is not int
                or row.get('png') != png
                or row.get('pdf_sha256') != sha256(paths[pdf])
                or row.get('png_sha256') != sha256(paths[png])
                or not isinstance(row.get('media_file'), str)
                or not re.fullmatch(r'ppt/media/[A-Za-z0-9_.-]+', row['media_file'])):
            raise EvidenceError('External presentation manual preview checksum or binding mismatch')
        header = paths[png].read_bytes()[:24]
        if len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
            raise EvidenceError('External presentation preview is not a PNG')
        width, height = struct.unpack('>II', header[16:24])
        if not (400 <= width <= 4000 and 600 <= height <= 6000 and 0.65 <= width / height <= 0.75):
            raise EvidenceError('External presentation preview has invalid dimensions')
    return receipt


def validate_presentation(paths: dict[str, Path], source_commit: str, manifest_hash: str,
                          screenshot_evidence: dict, *, metadata_root: Path) -> dict:
    """Verify a full PPTX receipt and each source/embedded image, without writes."""
    receipt = _read_json(paths[PRESENTATION_RECEIPT])
    metadata = read_release_metadata(metadata_root)
    if receipt.get('schema_version') != 1 or receipt.get('source_commit') != source_commit:
        raise EvidenceError('Presentation belongs to a different source commit or schema')
    if (receipt.get('functional_version') != metadata.version or str(receipt.get('build')) != metadata.build):
        raise EvidenceError('Presentation release metadata differs from this release')
    if (receipt.get('real_screenshots') is not True or receipt.get('editable_text') is not True
            or receipt.get('speaker_notes') is not True):
        raise EvidenceError('Presentation requires real screenshots, editable text and speaker notes')
    if receipt.get('screenshot_manifest_sha256') != manifest_hash:
        raise EvidenceError('Presentation was not built from these screenshots')
    if receipt.get('file') != PRESENTATION_FILE or receipt.get('sha256') != sha256(paths[PRESENTATION_FILE]):
        raise EvidenceError('Presentation file checksum mismatch')
    count = receipt.get('slides')
    if type(count) is not int or not 5 <= count <= 250:
        raise EvidenceError('Presentation slide count is invalid')
    rows = receipt.get('screenshots')
    if not isinstance(rows, list) or len(rows) != len(REQUIRED_SCREENSHOTS):
        raise EvidenceError('Presentation must include every required real UI view')
    screenshot_hashes = {row['id']: row['sha256'] for row in screenshot_evidence['screenshots']}
    seen = set()
    first_pages = receipt.get('manual_first_pages')
    if not isinstance(first_pages, list) or len(first_pages) != len(MANUAL_PDFS):
        raise EvidenceError('Presentation must include the actual first page of all five manuals')
    try:
        with ZipFile(paths[PRESENTATION_FILE]) as archive:
            used_media = _presentation_parts(archive, metadata.version, metadata.build, count)
            for row in rows:
                if not isinstance(row, dict) or row.get('id') not in REQUIRED_SCREENSHOTS or row['id'] in seen:
                    raise EvidenceError('Presentation screenshot IDs are missing, duplicated or unexpected')
                seen.add(row['id'])
                if row.get('sha256') != screenshot_hashes.get(row['id']):
                    raise EvidenceError('Presentation screenshot differs from the verified browser capture')
                _embedded_hash(archive, row.get('media_file'), row['sha256'], used_media)
            seen_pdfs = set()
            for row in first_pages:
                if not isinstance(row, dict) or row.get('pdf') not in MANUAL_PDFS or row['pdf'] in seen_pdfs:
                    raise EvidenceError('Presentation manual previews are missing, duplicated or unexpected')
                pdf = row['pdf']
                png = MANUAL_PREVIEWS[pdf]
                seen_pdfs.add(pdf)
                if row.get('page') != 1 or type(row.get('page')) is not int or row.get('png') != png:
                    raise EvidenceError('Presentation preview must be the actual first page of its manual')
                if row.get('pdf_sha256') != sha256(paths[pdf]) or row.get('png_sha256') != sha256(paths[png]):
                    raise EvidenceError('Presentation manual/preview checksum mismatch')
                header = paths[png].read_bytes()[:24]
                if len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
                    raise EvidenceError('Presentation manual preview is not a PNG')
                width, height = struct.unpack('>II', header[16:24])
                if not (400 <= width <= 4000 and 600 <= height <= 6000 and 0.65 <= width / height <= 0.75):
                    raise EvidenceError('Presentation manual preview has invalid page dimensions')
                _embedded_hash(archive, row.get('media_file'), row['png_sha256'], used_media)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise EvidenceError('Presentation package is unreadable') from exc
    return receipt
