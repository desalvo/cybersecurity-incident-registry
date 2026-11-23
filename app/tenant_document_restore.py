"""Independent document definitions for tenant-scoped Full Import."""
import base64
import json
from pathlib import Path
import uuid

from .models import db, FormTemplateConfig, FormTemplateBinary, FormFieldMapping


_DOCUMENT_FIELDS = {'template_name', 'document_template_name', 'linked_form_template_name', 'generated_template_name'}


def _document_references(value, field=''):
    if isinstance(value, dict):
        return set().union(*(_document_references(item, key) for key, item in value.items())) if value else set()
    if isinstance(value, list):
        return set().union(*(_document_references(item, field) for item in value)) if value else set()
    if field in _DOCUMENT_FIELDS and isinstance(value, str) and value:
        return {value}
    return set()


def import_tenant_document_definitions(tables, target_tenant_id, archive=None, files=None):
    """Return old-to-new names; use DB binaries so rollback has no file effects."""
    from .form_generation import _sanitize_field_name

    def canonical_name(name):
        return _sanitize_field_name(Path(name).stem, 'documento')

    configs = {row['template_name']: row for row in tables.get('form_template_configs', [])}
    binaries = {row['template_name']: row for row in tables.get('form_template_binaries', [])}
    mappings = tables.get('form_field_mappings', [])
    archive_files = {row.get('template_name') or Path(row.get('name', '')).stem: row
                     for row in (files or {}).get('form_templates', [])}
    required = {row.get('document_template_name') for row in tables.get('incident_workflow_steps', [])}
    required.update(row.get('linked_form_template_name') for row in tables.get('notification_templates', []))
    # An already-generated document survives removal of its source template.
    # Copy that template when available, but do not invalidate a historical
    # archive whose generated document file is still complete.
    historical_names = {row.get('generated_template_name') for row in tables.get('documents', [])}
    for setting in tables.get('settings', []):
        logical = str(setting.get('key') or '').split(':', 2)[-1]
        if logical.startswith('__'):
            continue
        value = setting.get('value') or ''
        try:
            value = json.loads(value) if isinstance(value, str) else value
        except (ValueError, TypeError):
            pass
        required.update(_document_references(value, logical))
    required.discard(None)
    required.discard('')
    names = {}
    originals = set(configs) | set(binaries) | set(archive_files) | required | historical_names | {row.get('template_name') for row in mappings}
    originals.discard(None)
    originals.discard('')
    if any(not isinstance(name, str) for name in originals):
        raise ValueError('Nome del documento template non valido.')
    for original in sorted(originals):
        canonical = canonical_name(original)
        binary_data = (binaries.get(original) or binaries.get(canonical) or {}).get('pdf_data')
        data = configs.get(original) or configs.get(canonical) or {}
        source_mappings = ([row for row in mappings if row.get('template_name') == original]
                           or [row for row in mappings if row.get('template_name') == canonical])
        if isinstance(binary_data, dict) and set(binary_data) == {'__binary_base64__'}:
            binary_data = base64.b64decode(binary_data['__binary_base64__'], validate=True)
        file_info = archive_files.get(original) or archive_files.get(canonical)
        if not binary_data and archive is not None and file_info:
            try:
                member = archive.getmember(file_info['archive_path'])
            except (KeyError, TypeError) as exc:
                raise ValueError('PDF dichiarato ma mancante nell archivio tenant.') from exc
            if not member.isfile() or member.size > 25 * 1024**2:
                raise ValueError('Documento template non valido o troppo grande.')
            stream = archive.extractfile(member)
            binary_data = stream.read() if stream else None
        if not binary_data:
            # Legacy exports sometimes carried only references to pre-installed
            # shared templates. Preserve that compatibility without reading a
            # private document owned by another tenant.
            from .form_template_access import can_read_template
            readable = can_read_template(original, target_tenant_id)
            existing = (FormTemplateBinary.query.filter_by(template_name=original).first()
                        or FormTemplateBinary.query.filter_by(template_name=canonical).first()) if readable else None
            if existing is not None:
                binary_data = existing.pdf_data
                if not data:
                    existing_config = (FormTemplateConfig.query.filter_by(template_name=original).first()
                                       or FormTemplateConfig.query.filter_by(template_name=canonical).first())
                    if existing_config:
                        data = {column.name: getattr(existing_config, column.name) for column in existing_config.__table__.columns}
                if not source_mappings:
                    source_mappings = [{'template_field': row.template_field, 'db_field': row.db_field}
                                       for row in FormFieldMapping.query.filter_by(template_name=existing.template_name).all()]
            elif original in required:
                raise ValueError(f'Documento richiesto dal workflow non disponibile: {original}')
            else:
                continue
        if not isinstance(binary_data, (bytes, bytearray, memoryview)) or len(binary_data) > 25 * 1024**2:
            raise ValueError('Dati del documento template non validi.')
        # Use exactly the runtime's identity rules. A name ending in ".pdf"
        # or containing dots must never leave an owner under a different key
        # from the physical PDF that the runtime reader exposes.
        safe_name = canonical[:160]
        name = f'tenant{int(target_tenant_id)}_{uuid.uuid4().hex}_{safe_name}'
        config = FormTemplateConfig(template_name=name, owner_tenant_id=int(target_tenant_id),
            font_family=FormTemplateConfig.normalize_font_family(data.get('font_family')),
            font_size=FormTemplateConfig.normalize_font_size(data.get('font_size')),
            notification_tags=data.get('notification_tags') or '')
        db.session.add(config)
        db.session.add(FormTemplateBinary(template_name=name, filename=name + '.pdf', pdf_data=bytes(binary_data)))
        for row in source_mappings:
            db.session.add(FormFieldMapping(template_name=name, template_field=row['template_field'], db_field=row['db_field']))
        names[original] = name
    db.session.flush()
    return names


def remap_document_setting(value, names, field=''):
    if isinstance(value, list):
        return [remap_document_setting(item, names, field) for item in value]
    if isinstance(value, dict):
        return {key: remap_document_setting(item, names, key) for key, item in value.items()}
    if field in {'template_name', 'document_template_name', 'linked_form_template_name', 'generated_template_name'} and isinstance(value, str):
        return names.get(value, value)
    return value


def clone_owned_document_definitions(source_tenant_id, target_tenant_id):
    """Keep legacy tenant clone idempotent while isolating newly owned PDFs."""
    from .models import Setting
    mapping = {}
    for config in FormTemplateConfig.query.filter_by(owner_tenant_id=int(source_tenant_id)).all():
        key = f'tenant:{int(target_tenant_id)}:__cir_document_clone_{int(source_tenant_id)}_{config.id}'
        receipt = db.session.get(Setting, key)
        existing = FormTemplateConfig.query.filter_by(template_name=receipt.value, owner_tenant_id=int(target_tenant_id)).first() if receipt else None
        if existing is not None:
            mapping[config.template_name] = existing.template_name
            continue
        binary = FormTemplateBinary.query.filter_by(template_name=config.template_name).first()
        if binary is None or not binary.pdf_data:
            raise ValueError('Il documento del tenant sorgente non ha il PDF persistente.')
        def row(item):
            return {column.name: getattr(item, column.name) for column in item.__table__.columns}
        tables = {'form_template_configs': [row(config)], 'form_template_binaries': [row(binary)],
                  'form_field_mappings': [row(item) for item in FormFieldMapping.query.filter_by(template_name=config.template_name).all()]}
        names = import_tenant_document_definitions(tables, target_tenant_id)
        mapped_name = names[config.template_name]
        if receipt is None:
            receipt = Setting(key=key)
            db.session.add(receipt)
        receipt.value = mapped_name
        mapping.update(names)
    return mapping
