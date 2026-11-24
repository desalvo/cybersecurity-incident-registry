"""Transfer only the image assets explicitly referenced by shared settings.

Imported files receive unpredictable, exclusively created names. They are never
written over existing assets. Session transaction hooks remove new files on
rollback (including Session.close), and retain used files only after commit.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import uuid
import warnings

from defusedxml import ElementTree as SafeElementTree
from flask import current_app, has_app_context
from PIL import Image
from sqlalchemy import event
from sqlalchemy.orm import Session

from .models import db

MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_ASSETS_BYTES = 16 * 1024 * 1024
MAX_ASSETS = 100
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
_KIND_DIR = {'logo_path': 'LOGO_DIR', 'sso_logo_path': 'SSO_LOGO_DIR'}
_RASTER = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.gif': 'GIF', '.webp': 'WEBP'}
_NAME = re.compile(r'^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,199}$')
_DIGEST = re.compile(r'^[0-9a-f]{64}$')
_PENDING = 'cir_defaults_imported_assets'
_COMMITTED = 'cir_defaults_asset_committed_transactions'


def _filename(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value) or value in {'.', '..'}:
        raise ValueError('Nome immagine non valido.')
    return value


def _reference_filename(kind, reference):
    if kind not in _KIND_DIR or not isinstance(reference, str) or not reference or len(reference) > 4096 or '\x00' in reference or '\\' in reference:
        raise ValueError('Riferimento immagine non valido.')
    if kind == 'sso_logo_path':
        name = reference[4:] if reference.startswith('sso/') else reference
        return _filename(name)
    # An imported source path is an opaque identifier, never a path to read on
    # the receiving host. Export performs the directory membership check.
    path = Path(reference)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Il logo applicativo deve indicare un file assoluto gestito.')
    return _filename(path.name)


def _references(value, field=''):
    if field in _KIND_DIR:
        if value in (None, ''):
            return set()
        _reference_filename(field, value)
        return {(field, value)}
    if isinstance(value, dict):
        found = set()
        for key, child in value.items():
            found.update(_references(child, key))
        return found
    if isinstance(value, list):
        found = set()
        for child in value:
            found.update(_references(child, ''))
        return found
    return set()


def _setting_references(settings):
    if not isinstance(settings, list) or len(settings) > 2000:
        raise ValueError('Elenco parametri per le immagini non valido.')
    found = set()
    for setting in settings:
        if not isinstance(setting, dict) or not isinstance(setting.get('key'), str) or 'value' not in setting:
            raise ValueError('Parametro immagine non valido.')
        found.update(_references(setting['value'], setting['key']))
    if len(found) > MAX_ASSETS:
        raise ValueError('Troppe immagini referenziate nel bundle.')
    return found


# Editor metadata is not part of the rendered logo. Only these exact XML
# metadata containers may be removed, and only after checking their subtree
# for active content, references and unexpected elements.
_LEGACY_SVG_METADATA = {'metadata', 'RDF', 'Work', 'format', 'type', 'title', 'namedview'}


def _normalize_legacy_svg(content):
    """Strip inert editor metadata; preserve the original file on disk.

    Reject suspicious content even when it occurs inside metadata that would
    otherwise be discarded. The strict SVG validator runs on the result.
    """
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Il logo SVG deve essere codificato in UTF-8.') from exc
    if '\x00' in text or '<?xml-stylesheet' in text.lower():
        raise ValueError('Il logo SVG contiene istruzioni o codifica non ammesse.')
    try:
        root = SafeElementTree.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        raise ValueError('Logo SVG non valido o con entità esterne.') from exc
    if root.tag not in {'svg', '{http://www.w3.org/2000/svg}svg'}:
        raise ValueError('Il documento non è un logo SVG.')
    removed = False
    count = 0
    for parent in root.iter():
        for child in list(parent):
            name = child.tag.rsplit('}', 1)[-1] if isinstance(child.tag, str) else ''
            if name not in {'metadata', 'namedview'}:
                continue
            for node in child.iter():
                count += 1
                if count > 5000 or not isinstance(node.tag, str):
                    raise ValueError('Metadati SVG troppo complessi.')
                local = node.tag.rsplit('}', 1)[-1]
                if local not in _LEGACY_SVG_METADATA:
                    raise ValueError('Metadati SVG con elementi non ammessi.')
                for attr, value in node.attrib.items():
                    key = attr.rsplit('}', 1)[-1].lower()
                    val = value.lower()
                    if key.startswith('on') or key in {'href', 'style', 'base'} or any(x in val for x in ('javascript:', 'data:', 'file:', '@import', 'url(')) or (('http:' in val or 'https:' in val) and not (local == 'type' and key == 'resource')):
                        raise ValueError('Metadati SVG con riferimenti o contenuti attivi.')
            parent.remove(child)
            removed = True
    if not removed:
        return content
    normalized = SafeElementTree.tostring(root, encoding='utf-8')
    _validate_svg(normalized)
    return normalized


def _validate_svg(content):
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Il logo SVG deve essere codificato in UTF-8.') from exc
    # ElementTree deliberately omits processing instructions from its tree.
    # Restrict the encoding before checking them so UTF-16 cannot hide a
    # stylesheet instruction behind interleaved NUL bytes.
    if '\x00' in text:
        raise ValueError('Il logo SVG deve essere codificato in UTF-8.')
    if '<?xml-stylesheet' in text.lower():
        raise ValueError('Il logo SVG contiene un foglio di stile esterno.')
    try:
        root = SafeElementTree.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        raise ValueError('Logo SVG non valido o con entità esterne.') from exc
    if root.tag not in {'svg', '{http://www.w3.org/2000/svg}svg'}:
        raise ValueError('Il documento non è un logo SVG.')
    allowed = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon',
               'defs', 'clipPath', 'mask', 'linearGradient', 'radialGradient', 'stop',
               'title', 'desc', 'use', 'symbol'}
    count = 0
    for node in root.iter():
        count += 1
        if count > 5000 or not isinstance(node.tag, str):
            raise ValueError('Logo SVG troppo complesso.')
        tag = node.tag.rsplit('}', 1)[-1]
        if tag not in allowed or (node.tag.startswith('{') and not node.tag.startswith('{http://www.w3.org/2000/svg}')):
            raise ValueError('Il logo SVG contiene elementi attivi o non ammessi.')
        for attr, value in node.attrib.items():
            name = attr.rsplit('}', 1)[-1].lower()
            lowered_value = value.lower()
            # xml:base could turn an otherwise allowed local #fragment href
            # into a reference on a different document or external server.
            if name.startswith('on') or name in {'style', 'base'} or '\\' in value or any(word in lowered_value for word in ('javascript:', 'data:', 'http:', 'https:', 'file:', '@import')):
                raise ValueError('Il logo SVG contiene attributi attivi o risorse esterne.')
            if name == 'href' and not re.fullmatch(r'#[A-Za-z_][A-Za-z0-9_.:-]*', value):
                raise ValueError('Il logo SVG contiene collegamenti esterni.')
            if 'url' in lowered_value and not re.fullmatch(r'url\(\s*[\'"]?#[A-Za-z_][A-Za-z0-9_.:-]*[\'"]?\s*\)', value, re.I):
                raise ValueError('Il logo SVG contiene riferimenti CSS non ammessi.')


def _validate_image(content, filename, kind):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_ASSET_BYTES:
        raise ValueError('Immagine vuota o più grande di 2 MiB.')
    suffix = Path(filename).suffix.lower()
    if suffix == '.svg':
        if kind != 'sso_logo_path':
            raise ValueError('Per il logo applicativo usare PNG, JPG, GIF o WEBP.')
        _validate_svg(content)
        return
    expected = _RASTER.get(suffix)
    if expected is None:
        raise ValueError('Formato immagine non supportato.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as img:
                if img.format != expected or img.width <= 0 or img.height <= 0 or img.width * img.height > MAX_IMAGE_PIXELS or getattr(img, 'n_frames', 1) > 100:
                    raise ValueError('Formato, dimensioni o numero di fotogrammi non ammessi.')
                img.verify()
    except Exception as exc:
        raise ValueError('Immagine non valida o troppo complessa.') from exc


def _validate_assets(assets):
    if not isinstance(assets, list) or len(assets) > MAX_ASSETS:
        raise ValueError('Elenco immagini non valido o troppo lungo.')
    output, seen, total = [], set(), 0
    fields = {'kind', 'source_ref', 'filename', 'sha256', 'content_base64'}
    for item in assets:
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError('Record immagine non valido.')
        kind, reference = item['kind'], item['source_ref']
        if not isinstance(kind, str):
            raise ValueError('Tipo immagine non valido.')
        name = _reference_filename(kind, reference)
        if item['filename'] != name or (kind, reference) in seen:
            raise ValueError('Nome immagine incoerente o riferimento duplicato.')
        seen.add((kind, reference))
        digest, encoded = item['sha256'], item['content_base64']
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest) or not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_ASSET_BYTES + 2) // 3):
            raise ValueError('Impronta o contenuto immagine non valido.')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Codifica immagine base64 non valida.') from exc
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError('Impronta immagine non corrispondente.')
        total += len(content)
        if total > MAX_ASSETS_BYTES:
            raise ValueError('Le immagini superano complessivamente 16 MiB.')
        _validate_image(content, name, kind)
        output.append(dict(item))
    return output


def export_defaults_assets(settings):
    """Read exactly the logo slots present in explicit source-tenant settings."""
    output = []
    for kind, reference in sorted(_setting_references(settings)):
        filename = _reference_filename(kind, reference)
        base = Path(current_app.config[_KIND_DIR[kind]]).resolve()
        raw_path = Path(reference) if kind == 'logo_path' else base / filename
        # Reject symlinks even if they eventually point inside the allowed base:
        # only a directly managed regular image is eligible for transfer.
        if raw_path.is_symlink():
            raise ValueError('Il logo referenziato è un collegamento simbolico.')
        path = raw_path.resolve()
        if path.parent != base:
            raise ValueError('Il logo referenziato è fuori dalla directory gestita.')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        try:
            fd = os.open(path, flags)
            with os.fdopen(fd, 'rb') as handle:
                metadata = os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ASSET_BYTES:
                    raise ValueError('Il logo non è un file regolare di dimensioni ammesse.')
                content = handle.read(MAX_ASSET_BYTES + 1)
        except OSError as exc:
            raise ValueError('Un logo referenziato non è disponibile nella directory gestita.') from exc
        if kind == 'sso_logo_path' and filename.lower().endswith('.svg'):
            content = _normalize_legacy_svg(content)
        _validate_image(content, filename, kind)
        output.append({'kind': kind, 'source_ref': reference, 'filename': filename,
                       'sha256': hashlib.sha256(content).hexdigest(), 'content_base64': base64.b64encode(content).decode('ascii')})
    return validate_defaults_assets(output, settings)


def validate_defaults_assets(assets, settings):
    """Require one verified payload for every nonempty supported logo reference."""
    assets = _validate_assets(assets)
    expected = _setting_references(settings)
    actual = {(item['kind'], item['source_ref']) for item in assets}
    if expected != actual:
        raise ValueError('Le immagini del bundle non corrispondono ai loghi referenziati nei parametri.')
    return assets


def _remove_owned_file(record):
    path = record['path']
    try:
        metadata = path.lstat()
        # Never remove a path replaced by another writer or an existing asset.
        if (metadata.st_dev, metadata.st_ino) != record['identity'] or not stat.S_ISREG(metadata.st_mode):
            return
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != record['identity']:
                return
            content = handle.read(MAX_ASSET_BYTES + 1)
        if hashlib.sha256(content).hexdigest() != record['sha256']:
            return
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # A cleanup failure does not authorize removing any other file.
        if has_app_context():
            current_app.logger.warning('Impossibile rimuovere un nuovo logo di importazione annullata: %s', path.name)


def _assets_after_commit(session):
    if not session.info.get(_PENDING):
        return
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is not None:
        session.info.setdefault(_COMMITTED, set()).add(transaction)


def _assets_transaction_ended(session, transaction):
    records = session.info.get(_PENDING, [])
    committed = session.info.get(_COMMITTED, set())
    was_committed = transaction in committed
    committed.discard(transaction)
    survivors = []
    for record in records:
        if record['transaction'] is not transaction:
            survivors.append(record)
        elif was_committed and transaction.parent is not None:
            record['transaction'] = transaction.parent
            survivors.append(record)
        elif was_committed and record['used']:
            pass  # Referenced in committed settings: ownership is now persistent.
        else:
            _remove_owned_file(record)
    if survivors:
        session.info[_PENDING] = survivors
    else:
        session.info.pop(_PENDING, None)
    if not committed:
        session.info.pop(_COMMITTED, None)


def _register_transaction_cleanup():
    if not event.contains(Session, 'after_commit', _assets_after_commit):
        event.listen(Session, 'after_commit', _assets_after_commit)
        event.listen(Session, 'after_transaction_end', _assets_transaction_ended)


class _AssetMapping(dict):
    def __init__(self, records):
        super().__init__()
        self.records = records

    def __getitem__(self, key):
        result = super().__getitem__(key)
        self.records[key]['used'] = True
        return result


def import_defaults_assets(assets):
    """Return (field, original reference) -> new reference, with rollback cleanup."""
    assets = _validate_assets(assets)
    _register_transaction_cleanup()
    session = db.session()
    if not session.in_transaction():
        session.begin()
    transaction = session.get_nested_transaction() or session.get_transaction()
    owned = {}
    mapping = _AssetMapping(owned)
    pending = session.info.setdefault(_PENDING, [])
    try:
        for item in assets:
            kind = item['kind']
            base = Path(current_app.config[_KIND_DIR[kind]]).resolve()
            base.mkdir(parents=True, exist_ok=True)
            content = base64.b64decode(item['content_base64'], validate=True)
            suffix = Path(item['filename']).suffix.lower()
            for _attempt in range(8):
                name = f'td_{item["sha256"][:12]}_{uuid.uuid4().hex}{suffix}'
                path = base / name
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    break
                except FileExistsError:
                    continue
            else:
                raise ValueError('Impossibile assegnare un nome nuovo al logo importato.')
            with os.fdopen(fd, 'wb') as handle:
                metadata = os.fstat(handle.fileno())
                record = {'path': path, 'identity': (metadata.st_dev, metadata.st_ino),
                          'sha256': item['sha256'], 'transaction': transaction, 'used': False}
                # Track before writing so an interrupted write can be cleaned.
                pending.append(record)
                owned[(kind, item['source_ref'])] = record
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            mapping[(kind, item['source_ref'])] = str(path) if kind == 'logo_path' else 'sso/' + name
        return mapping
    except Exception:
        for record in owned.values():
            # Partially written new files still belong to this operation.
            try:
                metadata = record['path'].lstat()
                if (metadata.st_dev, metadata.st_ino) == record['identity']:
                    record['path'].unlink()
            except FileNotFoundError:
                pass
            if record in pending:
                pending.remove(record)
        raise


def remap_defaults_asset_references(value, field, mapping):
    if field in _KIND_DIR:
        if value in (None, ''):
            return value
        _reference_filename(field, value)
        try:
            return mapping[(field, value)]
        except KeyError as exc:
            raise ValueError('Immagine referenziata mancante dalla mappa di importazione.') from exc
    if isinstance(value, dict):
        return {key: remap_defaults_asset_references(child, key, mapping) for key, child in value.items()}
    if isinstance(value, list):
        return [remap_defaults_asset_references(child, '', mapping) for child in value]
    return value
