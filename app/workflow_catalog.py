"""Portable workflow snapshots for Tenants Default.

Every mutation participates in the caller's database transaction; none commits.
Numeric IDs in an imported document are never used as destination database IDs.
PDFs remain in FormTemplateBinary until the normal lazy materializer writes them,
so a failed transaction cannot overwrite files belonging to another tenant.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import uuid
from pathlib import Path

from flask import current_app

from .models import (
    db, ConfigLabel, FormFieldMapping, FormTemplateBinary, FormTemplateConfig,
    IncidentWorkflowStep, NotificationTemplate, NotificationType, Setting, Tenant,
)
from .workflow_catalog_models import WorkflowCatalogEntry, WorkflowCatalogInstallation

CATALOG_FORMAT = 'cybersecurity-incident-registry.workflow-catalog.v1'
LEGACY_FORMAT = 'cybersecurity-incident-registry.workflow.v1'
MAX_CATALOG_BYTES = 25 * 1024 * 1024
MAX_PDF_BYTES = 12 * 1024 * 1024
LABEL_KINDS = {'severity', 'category', 'data_type', 'action_label'}
STANDARD_STEP_TYPES = {'registration', 'execution', 'update_section', 'operation'}
# Match the configurable routing sources. ``manual`` remains accepted for
# legacy exports; preserve its value rather than silently rewriting behavior.
NOTIFICATION_ADDRESS_SOURCES = {
    'type_default', 'incident_recipient_email', 'incident_creator_email',
    'fixed', 'empty', 'manual',
}
SECTION_TARGETS = {
    'incident-main', 'incident-workflow', 'incident-procedural-alerts',
    'incident-actions', 'incident-reminders', 'incident-documents',
    'incident-forms', 'incident-notifications',
}
_CODE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_-]{0,39}$')
_REF = re.compile(r'^[A-Za-z0-9_-]{1,80}$')
_FORM_NAME = re.compile(r'^[A-Za-z0-9_-]{1,200}(?:\.pdf)?$')


def _text(value, field, length, *, required=False):
    if not isinstance(value, str) or len(value) > length or '\x00' in value:
        raise ValueError(f'{field}: testo non valido o troppo lungo.')
    if required and not value.strip():
        raise ValueError(f'{field}: valore obbligatorio.')
    return value


def _boolean(data, name, default=False):
    value = data.get(name, default)
    if type(value) is not bool:
        raise ValueError(f'{name}: atteso un valore booleano.')
    return value


def _integer(value, name, minimum=0, maximum=1000000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name}: numero non valido.')
    return value


def _objects(value, field, maximum=512):
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(x, dict) for x in value):
        raise ValueError(f'{field}: elenco non valido o troppo lungo.')
    return value


def _code(value, field):
    if not isinstance(value, str) or not _CODE.fullmatch(value):
        raise ValueError(f'{field}: codice non valido.')
    return value


def _form_name(value):
    if not isinstance(value, str) or not _FORM_NAME.fullmatch(value):
        raise ValueError('Nome del modello PDF non valido; sono ammessi nomi semplici senza percorsi.')
    return value


def _canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _shared_reference(item):
    value = item.get('shared_source_id')
    if value is None:
        return {}
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Identità del parametro condiviso non valida.') from exc
    return {'shared_source_id': value}


def _legacy_to_portable(payload):
    """Upgrade legacy documents only when reference remapping is unambiguous."""
    deps = payload.get('dependencies')
    wf = payload.get('workflow')
    if not isinstance(deps, dict) or not isinstance(wf, dict):
        raise ValueError('Workflow legacy non valido.')
    labels = []
    refs = {}
    source_ids = {}
    for index, item in enumerate(_objects(deps.get('labels', []), 'labels')):
        identity = (item.get('kind'), item.get('value'))
        if identity in refs:
            raise ValueError('Label duplicate nel workflow legacy.')
        ref = f'label_{index}'
        refs[identity] = ref
        labels.append({**item, 'ref': ref})
        if item.get('source_id') is not None or item.get('id') is not None:
            source_ids[(item.get('kind'), str(item.get('source_id', item.get('id'))))] = ref

    def label_ref(item):
        if not isinstance(item, dict) or (item.get('kind'), item.get('value')) not in refs:
            raise ValueError('Dipendenza label assente; esportare nuovamente il workflow dal tenant sorgente.')
        return refs[(item.get('kind'), item.get('value'))]

    steps = []
    for item in _objects(wf.get('steps', []), 'steps', 256):
        conditions = []
        for token in item.get('conditions', []):
            if not isinstance(token, str):
                raise ValueError('Condizione legacy non valida.')
            negated = token.startswith('!')
            token = token[1:] if negated else token
            if token == 'personal_data':
                conditions.append({'kind': token, 'negated': negated})
            else:
                parts = token.split(':', 1)
                ref = source_ids.get(tuple(parts)) if len(parts) == 2 else None
                if not ref:
                    raise ValueError('Il vecchio export contiene ID di condizioni non rimappabili: esportare il workflow con il nuovo export catalogo.')
                conditions.append({'kind': parts[0], 'label_ref': ref, 'negated': negated})
        steps.append({**item, 'action_label_ref': label_ref(item.get('action_label')), 'conditions': conditions})
    templates = []
    for item in _objects(deps.get('notification_templates', []), 'notification_templates', 256):
        templates.append({**item, 'action_label_ref': label_ref(item['action_label']) if item.get('action_label') else None})
    return {
        'format': CATALOG_FORMAT,
        'workflow': {'category_ref': label_ref(wf['category']) if wf.get('category') else None, 'steps': steps,
                     **{key: wf[key] for key in ('status', 'catalog_source_public_id') if key in wf}},
        'dependencies': {
            'labels': labels,
            'notification_types': deps.get('notification_types', []),
            'notification_templates': templates,
            'form_templates': deps.get('form_templates', []),
            'step_types': deps.get('step_types', []),
        },
    }


def validate_catalog_payload(payload):
    """Return a canonical whitelist-only snapshot, rejecting broken references."""
    if not isinstance(payload, dict):
        raise ValueError('Il file deve contenere un oggetto JSON workflow.')
    try:
        if len(_canonical(payload).encode('utf-8')) > MAX_CATALOG_BYTES:
            raise ValueError('Workflow troppo grande (massimo 25 MiB).')
    except (TypeError, RecursionError) as exc:
        raise ValueError('Documento workflow non valido.') from exc
    if payload.get('format') == LEGACY_FORMAT:
        try:
            payload = _legacy_to_portable(payload)
        except (TypeError, AttributeError, KeyError) as exc:
            raise ValueError('Documento workflow legacy non valido.') from exc
    if payload.get('format') != CATALOG_FORMAT:
        raise ValueError('Formato workflow non supportato.')
    wf, deps = payload.get('workflow'), payload.get('dependencies')
    if not isinstance(wf, dict) or not isinstance(deps, dict):
        raise ValueError('Definizione workflow o dipendenze mancanti.')
    labels, labels_by_ref = [], {}
    for item in _objects(deps.get('labels', []), 'labels'):
        ref = item.get('ref')
        if not isinstance(ref, str) or not _REF.fullmatch(ref) or ref in labels_by_ref:
            raise ValueError('Riferimento label assente, duplicato o non valido.')
        kind = item.get('kind')
        if not isinstance(kind, str) or kind not in LABEL_KINDS:
            raise ValueError('Tipo label non ammesso nel catalogo workflow.')
        operations = _text(item.get('automatic_operations', ''), 'automatic_operations', 200)
        if any(op not in {'close_without_warnings', 'end_breach', 'global_check'} for op in operations.split(',') if op):
            raise ValueError('Operazione automatica sconosciuta.')
        row = {
            **_shared_reference(item),
            'ref': ref, 'kind': kind, 'value': _text(item.get('value'), 'value', 255, required=True),
            'group': _text(item.get('group', 'default'), 'group', 80),
            'description': _text(item.get('description', ''), 'description', 100000),
            'max_completion_hours': _integer(item.get('max_completion_hours', 0), 'max_completion_hours'),
            'default_exportable': _boolean(item, 'default_exportable', True),
            'description_required': _boolean(item, 'description_required'),
            'automatic_operations': operations,
        }
        labels_by_ref[ref] = row
        labels.append(row)

    def require_label(ref, kind):
        if not isinstance(ref, str) or ref not in labels_by_ref or labels_by_ref[ref]['kind'] != kind:
            raise ValueError(f'Riferimento a label {kind} mancante o non coerente.')
        return ref

    category_ref = wf.get('category_ref')
    if category_ref is not None:
        require_label(category_ref, 'category')
    notification_types, notification_codes = [], set()
    for item in _objects(deps.get('notification_types', []), 'notification_types', 128):
        code = _code(item.get('code'), 'notification code')
        if code in notification_codes:
            raise ValueError('Codice notifica duplicato.')
        notification_codes.add(code)
        notification_types.append({
            **_shared_reference(item),
            'code': code, 'label': _text(item.get('label'), 'label', 160, required=True),
            'description': _text(item.get('description', ''), 'description', 100000),
            'enabled': _boolean(item, 'enabled', True),
        })
    step_types, custom_codes = [], set()
    for item in _objects(deps.get('step_types', []), 'step_types', 64):
        code = _code(item.get('code'), 'step_type')
        if code != code.lower() or code in STANDARD_STEP_TYPES or code in custom_codes:
            raise ValueError('Tipo step duplicato o riservato.')
        custom_codes.add(code)
        step_types.append({'code': code, 'label': _text(item.get('label'), 'label', 80, required=True),
                           'description': _text(item.get('description', ''), 'description', 120)})
    forms, form_names = [], set()
    for item in _objects(deps.get('form_templates', []), 'form_templates', 64):
        name = _form_name(item.get('template_name'))
        if name in form_names:
            raise ValueError('Modello PDF duplicato.')
        form_names.add(name)
        binary = item.get('binary')
        if not isinstance(binary, dict):
            raise ValueError(f'PDF mancante per il modello {name}.')
        encoded = binary.get('pdf_base64')
        if not isinstance(encoded, str) or len(encoded) > ((MAX_PDF_BYTES + 2) // 3) * 4:
            raise ValueError('PDF troppo grande o non valido.')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('PDF codificato in base64 non valido.') from exc
        if not content.startswith(b'%PDF-') or len(content) > MAX_PDF_BYTES:
            raise ValueError('Il documento allegato non è un PDF supportato.')
        tags = item.get('notification_tags', [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) or tag not in notification_codes for tag in tags):
            raise ValueError('Il modello PDF usa un tipo notifica non incluso nel file.')
        mappings, fields = [], set()
        for mapping in _objects(item.get('mappings', []), 'mappings'):
            field = _text(mapping.get('template_field'), 'template_field', 255, required=True)
            db_field = _text(mapping.get('db_field'), 'db_field', 255, required=True)
            if field in fields or not re.fullmatch(r'[A-Za-z0-9_.:-]+', db_field):
                raise ValueError('Mappatura PDF duplicata o non valida.')
            fields.add(field)
            mappings.append({'template_field': field, 'db_field': db_field})
        forms.append({
            'template_name': name, 'font_family': FormTemplateConfig.normalize_font_family(_text(item.get('font_family', 'Helvetica'), 'font_family', 40)),
            'font_size': _integer(item.get('font_size', 10), 'font_size', 8, 16),
            'notification_tags': list(dict.fromkeys(tags)), 'mappings': mappings,
            'binary': {'filename': Path(name).stem + '.pdf', 'pdf_base64': encoded},
        })
    templates, template_keys = [], set()
    for item in _objects(deps.get('notification_templates', []), 'notification_templates', 256):
        kind = _code(item.get('kind'), 'notification kind')
        name = _text(item.get('name'), 'notification name', 160, required=True)
        if kind not in notification_codes or (kind, name) in template_keys:
            raise ValueError('Template di notifica duplicato o senza tipo corrispondente.')
        template_keys.add((kind, name))
        ref = item.get('action_label_ref')
        if ref is not None:
            require_label(ref, 'action_label')
        form = _text(item.get('linked_form_template_name') or '', 'linked_form_template_name', 255)
        if form and form not in form_names:
            raise ValueError('Il template di notifica richiede un PDF assente.')
        recipient_source = _text(item.get('recipient_source', 'type_default'), 'recipient_source', 40)
        cc_source = _text(item.get('cc_source', 'type_default'), 'cc_source', 40)
        if recipient_source not in NOTIFICATION_ADDRESS_SOURCES or cc_source not in NOTIFICATION_ADDRESS_SOURCES:
            raise ValueError('Origine indirizzo del template di notifica non valida.')
        # A catalog snapshot is configuration export, not an anonymized
        # bootstrap. Retain routing settings and configured addresses exactly.
        templates.append({
            **_shared_reference(item),
            'kind': kind, 'name': name, 'subject': _text(item.get('subject', ''), 'subject', 255),
            'body': _text(item.get('body', ''), 'body', 200000),
            'action_label_ref': ref, 'linked_form_template_name': form,
            'recipient_source': recipient_source,
            'recipient_value': _text(item.get('recipient_value', ''), 'recipient_value', 255),
            'recipient_editable': _boolean(item, 'recipient_editable', True),
            'recipient_external_allowed': _boolean(item, 'recipient_external_allowed', True),
            'cc_source': cc_source, 'cc_value': _text(item.get('cc_value', ''), 'cc_value', 255),
            'cc_editable': _boolean(item, 'cc_editable', True),
            'cc_external_allowed': _boolean(item, 'cc_external_allowed', True),
            'is_default': _boolean(item, 'is_default'),
        })
    steps = []
    for item in _objects(wf.get('steps', []), 'steps', 256):
        ref = require_label(item.get('action_label_ref'), 'action_label')
        step_type = _text(item.get('step_type') or 'registration', 'step_type', 40)
        if step_type not in STANDARD_STEP_TYPES | custom_codes:
            raise ValueError('Tipo step personalizzato non incluso nel file.')
        conditions = []
        for condition in _objects(item.get('conditions', []), 'conditions', 128):
            kind = _text(condition.get('kind'), 'condition kind', 40)
            row = {'kind': kind, 'negated': _boolean(condition, 'negated')}
            if kind in {'severity', 'data_type'}:
                row['label_ref'] = require_label(condition.get('label_ref'), kind)
            elif kind != 'personal_data':
                raise ValueError('Tipo condizione non valido.')
            conditions.append(row)
        code = _text(item.get('required_notification_type') or '', 'required_notification_type', 40)
        if code and code not in notification_codes:
            raise ValueError('Tipo notifica richiesto dallo step assente.')
        requires_notification = _boolean(item, 'requires_notification')
        if requires_notification and not code:
            raise ValueError('Lo step richiede una notifica ma non ne indica il tipo.')
        form = _text(item.get('document_template_name') or '', 'document_template_name', 255)
        if form and form not in form_names:
            raise ValueError('Modello documento richiesto dallo step assente.')
        generates_document = _boolean(item, 'document_generation_enabled')
        if generates_document and not form:
            raise ValueError('Lo step genera un documento ma non indica un modello.')
        section = _text(item.get('section_target') or '', 'section_target', 80)
        if section and (section not in SECTION_TARGETS or step_type not in {'operation', 'update_section'}):
            raise ValueError('Sezione di destinazione non valida per lo step.')
        steps.append({
            'position': _integer(item.get('position', len(steps)), 'position'),
            'action_label_ref': ref, 'description': _text(item.get('description', ''), 'description', 100000),
            'step_type': step_type, 'conditions': conditions, 'required': _boolean(item, 'required', True),
            'requires_notification': requires_notification, 'required_notification_type': code,
            'document_generation_enabled': generates_document, 'document_template_name': form, 'section_target': section,
        })
    if not steps:
        raise ValueError('Il workflow selezionato non contiene step.')
    workflow = {'category_ref': category_ref, 'steps': steps}
    if 'status' in wf:
        if not isinstance(wf['status'], str) or wf['status'] not in {'current', 'obsolete'}:
            raise ValueError('Stato del workflow esportato non valido.')
        workflow['status'] = wf['status']
    if 'catalog_source_public_id' in wf:
        if wf['catalog_source_public_id'] is None:
            raise ValueError('Origine pubblica del workflow non valida.')
        workflow['catalog_source_public_id'] = _shared_reference(
            {'shared_source_id': wf['catalog_source_public_id']})['shared_source_id']
    return {'format': CATALOG_FORMAT, 'workflow': workflow,
            'dependencies': {'labels': labels, 'notification_types': notification_types,
                             'notification_templates': templates, 'form_templates': forms, 'step_types': step_types}}


def _effective_step_types_json(tenant_id):
    # Explicit tenant context is essential here: catalog installation may target
    # a different tenant from the administrator's currently selected one.
    # The central reader applies local > shared defaults > legacy, and prevents
    # Tenants Default from inheriting private legacy/default-tenant settings.
    from .routes import _setting_value_without_request_user
    return _setting_value_without_request_user('workflow_step_types_json', '', tenant_id=int(tenant_id))


def build_catalog_workflow_payload(tenant_id, category_id=None):
    """Export exactly one workflow and its transitive dependencies."""
    tenant = db.session.get(Tenant, int(tenant_id))
    if tenant is None:
        raise ValueError('Tenant sorgente inesistente.')
    category = None
    if category_id is not None:
        category = ConfigLabel.query.filter_by(id=int(category_id), tenant_id=tenant.id, kind='category').first()
        if category is None:
            raise ValueError('Categoria non appartenente al tenant sorgente.')
    steps = IncidentWorkflowStep.query.filter_by(tenant_id=tenant.id, category_id=category.id if category else None).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    labels, notifications, templates, forms = {}, {}, {}, {}
    used_step_types = set()

    def shared_origin(record, source_type):
        from .tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
        source = None
        if tenant.is_system_defaults:
            source = TenantDefaultSource.query.filter_by(source_type=source_type, source_id=record.id, active=True).first()
        else:
            replica = TenantDefaultReplica.query.filter_by(tenant_id=tenant.id, local_type=source_type, local_id=record.id).first()
            if replica:
                source = db.session.get(TenantDefaultSource, replica.source_id)
        return {'shared_source_id': source.id} if source is not None and source.active else {}

    def add_label(label_id, kind):
        label = ConfigLabel.query.filter_by(id=label_id, tenant_id=tenant.id, kind=kind).first()
        if label is None:
            raise ValueError('Il workflow riferisce una label assente o appartenente a un altro tenant.')
        ref = f'label_{label.id}'
        labels[ref] = {field: getattr(label, field) for field in (
            'kind', 'group', 'value', 'description', 'max_completion_hours', 'default_exportable',
            'description_required', 'automatic_operations')}
        labels[ref].update(ref=ref, group=label.group or 'default', description=label.description or '', automatic_operations=label.automatic_operations or '', **shared_origin(label, 'config_label'))
        return ref

    def add_notification(code):
        if not code or code in notifications:
            return
        nt = NotificationType.query.filter_by(tenant_id=tenant.id, code=code).first()
        if nt is None:
            raise ValueError(f'Tipo notifica {code} assente nel tenant sorgente.')
        notifications[code] = {'code': nt.code, 'label': nt.label, 'description': nt.description or '', 'enabled': bool(nt.enabled), **shared_origin(nt, 'notification_type')}
        for template in NotificationTemplate.query.filter_by(tenant_id=tenant.id, kind=code).order_by(NotificationTemplate.id).all():
            templates[template.id] = {
                **shared_origin(template, 'notification_template'),
                'kind': code, 'name': template.name, 'subject': template.subject or '', 'body': template.body or '',
                'action_label_ref': add_label(template.action_label_id, 'action_label') if template.action_label_id else None,
                'linked_form_template_name': template.linked_form_template_name or '',
                'recipient_source': template.recipient_source or 'type_default',
                'recipient_value': template.recipient_value or '',
                'recipient_editable': bool(template.recipient_editable),
                'recipient_external_allowed': bool(template.recipient_external_allowed),
                'cc_source': template.cc_source or 'type_default',
                'cc_value': template.cc_value or '', 'cc_editable': bool(template.cc_editable),
                'cc_external_allowed': bool(template.cc_external_allowed), 'is_default': bool(template.is_default),
            }
            if template.linked_form_template_name:
                add_form(template.linked_form_template_name)

    def add_form(name):
        if not name or name in forms:
            return
        _form_name(name)
        cfg = FormTemplateConfig.query.filter_by(template_name=name).first()
        canonical_name = Path(name).stem
        file_cfg = (FormTemplateConfig.query.filter_by(template_name=canonical_name).first()
                    if canonical_name != name else cfg)
        # Runtime materialization uses the filename stem. Check both identities
        # so an optional .pdf suffix cannot bypass an owner's configuration.
        for candidate in (cfg, file_cfg):
            candidate_owner = getattr(candidate, 'owner_tenant_id', None) if candidate is not None else None
            if candidate_owner not in (None, tenant.id):
                owner = db.session.get(Tenant, candidate_owner)
                if owner is None or not owner.is_system_defaults:
                    raise ValueError('Il workflow riferisce un modello PDF privato di un altro tenant.')
        cfg = cfg or file_cfg
        owner_id = getattr(cfg, 'owner_tenant_id', None) if cfg is not None else None
        binary = FormTemplateBinary.query.filter_by(template_name=name).first()
        if binary is None and canonical_name != name:
            binary = FormTemplateBinary.query.filter_by(template_name=canonical_name).first()
        content = bytes(binary.pdf_data) if binary and binary.pdf_data else None
        if content is None:
            base = Path(current_app.config['FORM_TEMPLATE_DIR']).resolve()
            raw_path = base / (canonical_name + '.pdf')
            path = raw_path.resolve()
            if raw_path.is_symlink() or path.parent != base or not path.is_file() or path.stat().st_size > MAX_PDF_BYTES:
                raise ValueError(f'PDF del modello {name} non disponibile.')
            content = path.read_bytes()
        tags = cfg.notification_tag_list if cfg else []
        if owner_id not in (None, tenant.id):
            # The only readable foreign owner is Tenants Default (checked
            # above). Its tag codes belong to the source definitions; resolve
            # through provenance before reading this tenant's dependencies.
            # A same-named local type is not the shared type after a collision.
            from .tenant_default_settings import shared_notification_codes
            tags = shared_notification_codes(tags, tenant.id)
        # Reserve before recursion through a template -> form -> tag -> template.
        forms[name] = {
            'template_name': name, 'font_family': cfg.font_family if cfg else 'Helvetica',
            'font_size': cfg.font_size if cfg else 10, 'notification_tags': tags,
            'binary': {'filename': Path(name).stem + '.pdf', 'pdf_base64': base64.b64encode(content).decode('ascii')},
            'mappings': [{'template_field': m.template_field, 'db_field': m.db_field} for m in FormFieldMapping.query.filter_by(template_name=cfg.template_name if cfg else canonical_name).order_by(FormFieldMapping.id).all()],
        }
        for code in tags:
            add_notification(code)

    category_ref = add_label(category.id, 'category') if category else None
    exported_steps = []
    for step in steps:
        conditions = []
        for token in step.condition_tokens():
            negated = token.startswith('!')
            token = token[1:] if negated else token
            if token == 'personal_data':
                conditions.append({'kind': token, 'negated': negated})
            else:
                try:
                    kind, source_id = token.split(':', 1)
                    if kind not in {'severity', 'data_type'}:
                        raise ValueError
                    ref = add_label(int(source_id), kind)
                except (ValueError, TypeError) as exc:
                    raise ValueError('Condizione del workflow non valida o non appartenente al tenant.') from exc
                conditions.append({'kind': kind, 'label_ref': ref, 'negated': negated})
        if step.required_notification_type:
            add_notification(step.required_notification_type)
        if step.document_template_name:
            add_form(step.document_template_name)
        used_step_types.add(step.step_type or 'registration')
        exported_steps.append({
            'position': step.position, 'action_label_ref': add_label(step.action_label_id, 'action_label'),
            'description': step.description or '', 'step_type': step.step_type or 'registration',
            'conditions': conditions, 'required': bool(step.required), 'requires_notification': bool(step.requires_notification),
            'required_notification_type': step.required_notification_type or '',
            'document_generation_enabled': bool(step.document_generation_enabled),
            'document_template_name': step.document_template_name or '', 'section_target': step.section_target or '',
        })
    custom = []
    raw_step_types = _effective_step_types_json(tenant.id)
    try:
        configured = json.loads(raw_step_types) if raw_step_types else []
    except (ValueError, TypeError) as exc:
        raise ValueError('Configurazione tipi step del tenant non valida.') from exc
    if not isinstance(configured, list) or any(not isinstance(item, dict) or not isinstance(item.get('code'), str) for item in configured):
        raise ValueError('Configurazione tipi step del tenant non valida.')
    for item in configured:
        if isinstance(item, dict) and item.get('code') in used_step_types - STANDARD_STEP_TYPES:
            custom.append({key: item.get(key, '') for key in ('code', 'label', 'description')})
    from .workflow_lifecycle import portable_workflow_lifecycle
    lifecycle = portable_workflow_lifecycle(tenant.id, category.id if category else None)
    if lifecycle.get('status') == 'current':
        lifecycle.pop('status')
    return validate_catalog_payload({'format': CATALOG_FORMAT,
        'workflow': {'category_ref': category_ref, 'steps': exported_steps,
                     **lifecycle},
        'dependencies': {'labels': list(labels.values()), 'notification_types': list(notifications.values()),
                         'notification_templates': list(templates.values()), 'form_templates': list(forms.values()), 'step_types': custom}})


def save_catalog_workflow(payload, name, description='', entry_id=None):
    """Create or revise an explicit catalog snapshot; existing installs stay local."""
    payload = validate_catalog_payload(payload)
    from .workflow_lifecycle import lock_workflow_configuration
    lock_workflow_configuration()
    if payload['workflow'].get('status', 'current') == 'current':
        from .workflow_lifecycle import validate_portable_workflow_lifecycle
        validate_portable_workflow_lifecycle(payload['workflow'])
    name = _text(name, 'Nome workflow', 160, required=True).strip()
    description = _text(description, 'Descrizione workflow', 100000)
    from .tenant_defaults import ensure_defaults_tenant
    tenant = ensure_defaults_tenant()
    serialized = _canonical(payload)
    digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    if entry_id is None:
        entry = WorkflowCatalogEntry(defaults_tenant_id=tenant.id, name=name, description=description,
                                     payload_json=serialized, payload_hash=digest, version=1, active=True,
                                     status='current')
        db.session.add(entry)
    else:
        entry = WorkflowCatalogEntry.query.filter_by(id=int(entry_id), defaults_tenant_id=tenant.id).populate_existing().with_for_update().first()
        if entry is None:
            raise ValueError('Workflow di catalogo inesistente.')
        if entry.payload_hash != digest:
            entry.version += 1
        entry.name, entry.description = name, description
        entry.payload_json, entry.payload_hash, entry.active = serialized, digest, True
    db.session.flush()
    if payload['workflow'].get('status') == 'obsolete':
        from .workflow_lifecycle import set_catalog_workflow_status
        set_catalog_workflow_status(entry.id, 'obsolete')
    return entry


def export_catalog_entry(entry_id):
    entry = WorkflowCatalogEntry.query.filter_by(id=int(entry_id), active=True).first()
    if entry is None:
        raise ValueError('Workflow di catalogo non disponibile.')
    payload = validate_catalog_payload(json.loads(entry.payload_json))
    if hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest() != entry.payload_hash:
        raise ValueError('Il contenuto del workflow non coincide con la sua impronta registrata.')
    if entry.status == 'obsolete' or 'status' in payload['workflow']:
        payload['workflow']['status'] = entry.status
    return payload


def _unique_value(original, exists, suffix, limit):
    candidate, index = original[:limit], 1
    while exists(candidate):
        ending = suffix if index == 1 else f'{suffix}_{index}'
        if len(ending) >= limit:
            ending = '_' + hashlib.sha256(ending.encode('utf-8')).hexdigest()[:10]
        candidate = original[:limit - len(ending)] + ending
        index += 1
    return candidate



def _catalog_copy_name(requested, tenant_id):
    """Reserve one visible name for both a workflow and its category.

    A category is an independent workflow scope, not a severity-like
    classification to deduplicate. Even a category inherited from Tenants
    Default must not become the target of a newly imported workflow.
    """
    from .workflow_catalog_models import TenantWorkflow
    existing_categories = (row.value for row in ConfigLabel.query.filter_by(
        tenant_id=tenant_id, kind='category').all())
    existing_workflows = (row.name for row in TenantWorkflow.query.filter_by(
        tenant_id=tenant_id).all())
    taken = {name.strip().casefold() for name in (*existing_categories, *existing_workflows) if name}
    if requested.casefold() not in taken:
        return requested
    match = re.fullmatch(r'(.+?) v([2-9][0-9]*)', requested, flags=re.IGNORECASE)
    root, version = (match.group(1), int(match.group(2)) + 1) if match else (requested, 2)
    for index in range(version, version + 10000):
        suffix = f' v{index}'
        candidate = root[:160 - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
    raise ValueError('Impossibile assegnare un nome univoco al workflow nel tenant.')


def _existing_tenant_severity(tenant_id, value):
    """Keep existing tenant severity IDs and settings, including replicas."""
    normalized = value.strip().casefold()
    return next((row for row in ConfigLabel.query.filter_by(
        tenant_id=tenant_id, kind='severity').order_by(ConfigLabel.id)
        if row.value.strip().casefold() == normalized), None)


def import_catalog_workflow(entry_id, target_tenant_id, *, as_default=False, copy_name=None):
    """Install a new independent copy, even for a previously installed revision."""
    if type(as_default) is not bool:
        raise ValueError('La destinazione default deve essere un valore booleano.')
    from .workflow_lifecycle import lock_workflow_configuration
    lock_workflow_configuration()
    target = Tenant.query.filter_by(id=int(target_tenant_id)).with_for_update().first()
    if target is None or target.is_system_defaults:
        raise ValueError('Scegliere un tenant operativo come destinazione del workflow.')
    entry = WorkflowCatalogEntry.query.filter_by(id=int(entry_id), active=True).populate_existing().with_for_update().first()
    if entry is None:
        raise ValueError('Workflow di catalogo non disponibile.')
    if entry.status != 'current':
        raise ValueError('Il workflow di catalogo è obsoleto e non può essere importato.')
    payload = validate_catalog_payload(json.loads(entry.payload_json))
    digest = hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()
    if digest != entry.payload_hash:
        raise ValueError('Il contenuto del workflow non coincide con la sua impronta registrata.')
    from .workflow_lifecycle import validate_portable_workflow_lifecycle
    # An explicit catalogue lifecycle transition is authoritative over the
    # status captured when its content snapshot was first imported. Do not
    # rewrite the content hash: installation receipts remain verifiable.
    validate_portable_workflow_lifecycle({**payload['workflow'], 'status': entry.status})
    copy_name = _text(entry.name if copy_name is None else copy_name, 'Nome della copia', 160, required=True).strip()
    if as_default and IncidentWorkflowStep.query.filter_by(tenant_id=target.id, category_id=None).first():
        raise ValueError('Il tenant ha già un workflow di default: importare come nuova categoria.')
    if any(row.get('shared_source_id') for kind in ('labels', 'notification_types', 'notification_templates')
           for row in payload['dependencies'][kind]):
        from .tenant_defaults import sync_defaults_configuration
        sync_defaults_configuration()
    # Resolve collisions only after inheriting Tenants Default categories:
    # workflow name and category label must always remain identical.
    if not as_default:
        copy_name = _catalog_copy_name(copy_name, target.id)
    result = _materialize_workflow_payload(payload, target, entry, copy_name, as_default)
    from .workflow_lifecycle import ensure_workflow_state
    state = ensure_workflow_state(target.id, result['category_id'], name=copy_name, source_entry_id=entry.id)
    installation = WorkflowCatalogInstallation(entry_id=entry.id, tenant_id=target.id, entry_version=entry.version,
        copy_name=copy_name, payload_hash=digest, category_id=result['category_id'],
        workflow_id=state.id, step_ids_json=json.dumps(result['step_ids']))
    db.session.add(installation)
    db.session.flush()
    result.update(entry_version=entry.version, installation_id=installation.id, copy_name=copy_name,
                  workflow_id=state.id)
    return result


def _resolve_shared_dependency(item, target_id, source_type):
    source_id = item.get('shared_source_id')
    if not source_id:
        return None
    from .tenant_defaults_models import TenantDefaultSource
    from .tenant_defaults import resolve_shared_configuration_record
    source = db.session.get(TenantDefaultSource, source_id)
    if source is None:
        # A portable file from another installation has no local source yet.
        # Materialize its snapshot independently; never bind an equal name/ID.
        return None
    row = resolve_shared_configuration_record(source_id, target_id, expected_type=source_type)
    if source_type == 'config_label' and row.kind != item['kind']:
        raise ValueError('Il riferimento condiviso identifica un tipo di label diverso.')
    return row


def resolve_shared_copy_dependency(record, source_type, target_tenant_id):
    """Legacy cross-tenant clones can preserve the same UUID-based mapping."""
    from .tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    from .tenant_defaults import resolve_shared_configuration_record
    owner = db.session.get(Tenant, record.tenant_id) if record.tenant_id else None
    if owner is not None and owner.is_system_defaults:
        source = TenantDefaultSource.query.filter_by(source_type=source_type, source_id=record.id).first()
    else:
        replica = TenantDefaultReplica.query.filter_by(local_type=source_type, local_id=record.id).first()
        source = db.session.get(TenantDefaultSource, replica.source_id) if replica else None
    if source is None:
        return None
    return resolve_shared_configuration_record(source.id, target_tenant_id, expected_type=source_type)


def _materialize_workflow_payload(payload, target, entry, copy_name, as_default, *,
                                  use_shared=True, existing_steps=None):
    """Create dependencies, or detach one existing copy in its own scope."""
    deps, wf = payload['dependencies'], payload['workflow']
    suffix = f' [Catalogo {entry.id} v{entry.version}]'
    label_map, notification_map, form_map, step_type_map = {}, {}, {}, {}
    for item in deps['labels']:
        is_scope = item['ref'] == wf['category_ref']
        if is_scope and as_default:
            continue
        if existing_steps is not None and is_scope:
            label_map[item['ref']] = db.session.get(ConfigLabel, existing_steps[0].category_id)
            continue
        # A severity already in the tenant is the same classification: use
        # its original ID and never replace its locally configured details.
        # Categories are different: each imported workflow needs its own
        # independent category with exactly the workflow's visible name.
        existing_severity = (_existing_tenant_severity(target.id, item['value'])
                             if item['kind'] == 'severity' else None)
        if existing_severity is not None:
            label_map[item['ref']] = existing_severity
            continue
        # Other shared parameters keep provenance-based mappings. Avoid
        # deduplicating action labels/data types that may differ in behavior.
        shared = _resolve_shared_dependency(item, target.id, 'config_label') if use_shared and not is_scope else None
        if shared is not None:
            label_map[item['ref']] = shared
            continue
        base_value = copy_name if not as_default and is_scope else item['value']
        if is_scope:
            if ConfigLabel.query.filter_by(tenant_id=target.id, kind='category', value=base_value).first():
                raise ValueError('Categoria workflow già presente: ripetere l’importazione per scegliere un altro nome.')
            value = base_value
        else:
            value = _unique_value(base_value, lambda v: ConfigLabel.query.filter_by(tenant_id=target.id, kind=item['kind'], value=v).first() is not None, suffix, 255)
        fields = {key: value for key, value in item.items() if key not in {'ref', 'value', 'shared_source_id'}}
        label = ConfigLabel(tenant_id=target.id, value=value, **fields)
        db.session.add(label)
        db.session.flush()
        label_map[item['ref']] = label
    category = None
    if not as_default:
        if wf['category_ref']:
            category = label_map[wf['category_ref']]
        else:
            if ConfigLabel.query.filter_by(tenant_id=target.id, kind='category', value=copy_name).first():
                raise ValueError('Categoria workflow già presente: ripetere l’importazione per scegliere un altro nome.')
            category = ConfigLabel(tenant_id=target.id, kind='category', value=copy_name, group='catalogo workflow', description=entry.description)
            db.session.add(category)
            db.session.flush()
    for item in deps['notification_types']:
        shared = _resolve_shared_dependency(item, target.id, 'notification_type') if use_shared else None
        if shared is not None:
            notification_map[item['code']] = shared.code
            continue
        code = _unique_value(item['code'], lambda c: NotificationType.query.filter_by(tenant_id=target.id, code=c).first() is not None, f'_c{entry.id}v{entry.version}', 40).replace(' ', '_')
        notification_map[item['code']] = code
        db.session.add(NotificationType(tenant_id=target.id, code=code, **{k: v for k, v in item.items() if k not in {'code', 'shared_source_id'}}))
        db.session.flush()
    for item in deps['form_templates']:
        original = Path(item['template_name']).stem
        base = Path(current_app.config['FORM_TEMPLATE_DIR']).resolve()
        def exists(name):
            return (FormTemplateConfig.query.filter_by(template_name=name).first() is not None
                    or FormTemplateBinary.query.filter_by(template_name=name).first() is not None
                    or FormFieldMapping.query.filter_by(template_name=name).first() is not None
                    or (base / (name + '.pdf')).exists())
        name = _unique_value(original, exists, f'_catalog_{entry.id}_v{entry.version}_t{target.id}', 200).replace(' ', '_')
        form_map[item['template_name']] = name
        cfg = FormTemplateConfig(template_name=name, owner_tenant_id=target.id, font_family=item['font_family'], font_size=item['font_size'])
        cfg.set_notification_tags([notification_map[c] for c in item['notification_tags']])
        db.session.add(cfg)
        db.session.add(FormTemplateBinary(template_name=name, filename=name + '.pdf', pdf_data=base64.b64decode(item['binary']['pdf_base64'], validate=True)))
        for mapping in item['mappings']:
            db.session.add(FormFieldMapping(template_name=name, **mapping))
        db.session.flush()
    setting = db.session.get(Setting, f'tenant:{target.id}:workflow_step_types_json')
    raw_step_types = _effective_step_types_json(target.id)
    try:
        configured = json.loads(raw_step_types) if raw_step_types else []
    except (ValueError, TypeError) as exc:
        raise ValueError('Tipi step della destinazione non validi; correggere prima di importare.') from exc
    if not isinstance(configured, list) or any(not isinstance(row, dict) or not isinstance(row.get('code'), str) for row in configured):
        raise ValueError('Tipi step della destinazione non validi.')
    codes = STANDARD_STEP_TYPES | {row.get('code') for row in configured}
    for item in deps['step_types']:
        code = _unique_value(item['code'], lambda c: c in codes, f'_c{entry.id}v{entry.version}', 20).replace(' ', '_')
        codes.add(code)
        step_type_map[item['code']] = code
        configured.append({**item, 'code': code, 'protected': False})
    if deps['step_types']:
        if setting is None:
            setting = Setting(key=f'tenant:{target.id}:workflow_step_types_json')
            db.session.add(setting)
        setting.value = json.dumps(configured, ensure_ascii=False)
    for item in deps['notification_templates']:
        shared = _resolve_shared_dependency(item, target.id, 'notification_template') if use_shared else None
        if shared is not None:
            if shared.kind != notification_map[item['kind']]:
                raise ValueError('Tipo notifica non coerente con il template condiviso.')
            continue
        fields = {key: value for key, value in item.items() if key not in {'kind', 'action_label_ref', 'linked_form_template_name', 'shared_source_id'}}
        mapped_kind = notification_map[item['kind']]
        fields['name'] = _unique_value(fields['name'], lambda name: NotificationTemplate.query.filter_by(
            tenant_id=target.id, kind=mapped_kind, name=name).first() is not None, suffix, 160)
        if fields['is_default'] and NotificationTemplate.query.filter_by(tenant_id=target.id, kind=mapped_kind, is_default=True).first():
            fields['is_default'] = False
        label = label_map.get(item['action_label_ref'])
        db.session.add(NotificationTemplate(tenant_id=target.id, kind=mapped_kind,
            action_label_id=label.id if label else None, linked_form_template_name=form_map.get(item['linked_form_template_name']), **fields))
    step_ids = []
    for index, item in enumerate(wf['steps']):
        conditions = []
        for condition in item['conditions']:
            token = condition['kind']
            if condition.get('label_ref'):
                token += ':' + str(label_map[condition['label_ref']].id)
            conditions.append(('!' if condition['negated'] else '') + token)
        fields = {key: value for key, value in item.items() if key not in {'action_label_ref', 'conditions', 'step_type', 'required_notification_type', 'document_template_name'}}
        fields.update(action_label_id=label_map[item['action_label_ref']].id,
                      step_type=step_type_map.get(item['step_type'], item['step_type']),
                      required_notification_type=notification_map.get(item['required_notification_type']),
                      document_template_name=form_map.get(item['document_template_name']))
        if existing_steps is None:
            step = IncidentWorkflowStep(tenant_id=target.id, category_id=category.id if category else None, **fields)
        else:
            step = existing_steps[index]
            for field, value in fields.items():
                setattr(step, field, value)
        step.set_condition_tokens(conditions)
        db.session.add(step)
        db.session.flush()
        step_ids.append(step.id)
    return {'created': len(step_ids), 'unchanged': 0, 'category_id': category.id if category else None,
            'step_ids': step_ids}


def personalize_workflow_parameters(workflow_id):
    """Detach a copied workflow's dependencies without modifying other copies."""
    from .workflow_catalog_models import TenantWorkflow
    from .configuration_usage import workflow_incident_usage
    from .workflow_lifecycle import lock_workflow_configuration
    lock_workflow_configuration()
    state = TenantWorkflow.query.filter_by(id=int(workflow_id)).populate_existing().with_for_update().first()
    if state is None or state.source_entry_id is None:
        raise ValueError('Selezionare una copia proveniente dal catalogo.')
    if state.personalized:
        return state
    used = workflow_incident_usage(state.tenant_id, state.category_id)
    if used:
        raise ValueError('Il workflow è già usato da incidenti. Importare una nuova copia con un altro nome prima di personalizzare i parametri.')
    target = db.session.get(Tenant, state.tenant_id)
    entry = db.session.get(WorkflowCatalogEntry, state.source_entry_id)
    if target is None or target.is_system_defaults or entry is None:
        raise ValueError('Origine o destinazione del workflow non valida.')
    payload = build_catalog_workflow_payload(target.id, state.category_id)
    steps = IncidentWorkflowStep.query.filter_by(tenant_id=target.id, category_id=state.category_id).order_by(
        IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    _materialize_workflow_payload(payload, target, entry, state.name, state.category_id is None,
                                  use_shared=False, existing_steps=steps)
    state.personalized = True
    db.session.flush()
    return state


def publish_defaults_workflows(defaults_tenant_id):
    """Publish seeded/source draft scopes once; pair lifecycle with their source."""
    from .workflow_lifecycle import ensure_workflow_state, workflow_scope_key
    source = db.session.get(Tenant, int(defaults_tenant_id))
    if source is None or not source.is_system_defaults:
        raise ValueError('La pubblicazione automatica richiede Tenants Default.')
    scopes = [cid for (cid,) in db.session.query(IncidentWorkflowStep.category_id).filter_by(
        tenant_id=source.id).distinct().all()]
    published = []
    for category_id in scopes:
        scope_key = workflow_scope_key(category_id)
        if WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source.id, source_scope_key=scope_key).first():
            continue
        state = ensure_workflow_state(source.id, category_id)
        entry = save_catalog_workflow(build_catalog_workflow_payload(source.id, category_id), state.name)
        entry.source_scope_key = scope_key
        published.append(entry)
    db.session.flush()
    return published


def prepare_legacy_workflow_clone_dependencies(payload, source_tenant_id, target_tenant_id):
    """Map the validated dependency graph for the existing scope-clone UI.

    Ordinary labels keep the established reuse-by-name behavior of that UI.
    Defaults-origin rows always resolve through UUID provenance. Notification
    code conflicts and PDF ownership never overwrite destination definitions.
    """
    from .routes import _copy_label_to_tenant
    from .tenant_document_restore import import_tenant_document_definitions
    payload = validate_catalog_payload(payload)
    deps = payload['dependencies']
    labels, notifications, custom_codes = {}, {}, {}
    for item in deps['labels']:
        if item['ref'] == payload['workflow']['category_ref']:
            continue
        try:
            source_id = int(item['ref'].removeprefix('label_'))
        except (ValueError, TypeError) as exc:
            raise ValueError('Il clone richiede riferimenti generati dal tenant sorgente.') from exc
        source = db.session.get(ConfigLabel, source_id)
        if source is None or source.tenant_id != int(source_tenant_id) or source.kind != item['kind']:
            raise ValueError('Dipendenza del clone non appartenente al tenant sorgente.')
        labels[source.id] = _copy_label_to_tenant(source, target_tenant_id).id
    for item in deps['notification_types']:
        source = NotificationType.query.filter_by(tenant_id=int(source_tenant_id), code=item['code']).first()
        if source is None:
            raise ValueError('Tipo di notifica sorgente mancante.')
        shared = _resolve_shared_dependency(item, target_tenant_id, 'notification_type')
        if shared is not None:
            notifications[item['code']] = shared.code
            continue
        code = _unique_value(item['code'], lambda c: NotificationType.query.filter_by(
            tenant_id=target_tenant_id, code=c).first() is not None, f'_clone_t{int(source_tenant_id)}', 40)
        notifications[item['code']] = code
        db.session.add(NotificationType(tenant_id=target_tenant_id, code=code, label=source.label,
            description=source.description, recipient_mode=source.recipient_mode,
            recipient_setting_key=source.recipient_setting_key, cc_setting_key=source.cc_setting_key,
            enabled=source.enabled))
        db.session.flush()
    tables = {'form_template_configs': [], 'form_template_binaries': [], 'form_field_mappings': []}
    for item in deps['form_templates']:
        name = item['template_name']
        tables['form_template_configs'].append({'template_name': name, 'font_family': item['font_family'],
            'font_size': item['font_size'], 'notification_tags': ','.join(notifications[code] for code in item['notification_tags'])})
        tables['form_template_binaries'].append({'template_name': name,
            'pdf_data': {'__binary_base64__': item['binary']['pdf_base64']}})
        tables['form_field_mappings'].extend({'template_name': name, **mapping} for mapping in item['mappings'])
    forms = import_tenant_document_definitions(tables, target_tenant_id) if deps['form_templates'] else {}
    for item in deps['notification_templates']:
        shared = _resolve_shared_dependency(item, target_tenant_id, 'notification_template')
        if shared is not None:
            if shared.kind != notifications[item['kind']]:
                raise ValueError('Tipo di notifica condiviso non coerente con il template del clone.')
            continue
        kind = notifications[item['kind']]
        fields = {key: value for key, value in item.items()
                  if key not in {'kind', 'name', 'action_label_ref', 'linked_form_template_name', 'shared_source_id'}}
        name = _unique_value(item['name'], lambda v: NotificationTemplate.query.filter_by(
            tenant_id=target_tenant_id, kind=kind, name=v).first() is not None, ' [clone]', 160)
        source_label_id = int(item['action_label_ref'].removeprefix('label_')) if item['action_label_ref'] else None
        db.session.add(NotificationTemplate(tenant_id=target_tenant_id, kind=kind, name=name,
            action_label_id=labels.get(source_label_id),
            linked_form_template_name=forms.get(item['linked_form_template_name']), **fields))
    raw = _effective_step_types_json(target_tenant_id)
    try:
        configured = json.loads(raw) if raw else []
    except (ValueError, TypeError) as exc:
        raise ValueError('Tipi step della destinazione non validi.') from exc
    if not isinstance(configured, list) or any(not isinstance(row, dict) or not isinstance(row.get('code'), str) for row in configured):
        raise ValueError('Tipi step della destinazione non validi.')
    codes = STANDARD_STEP_TYPES | {row['code'] for row in configured}
    for item in deps['step_types']:
        code = _unique_value(item['code'], lambda value: value in codes, '_clone', 20)
        codes.add(code)
        custom_codes[item['code']] = code
        configured.append({**item, 'code': code, 'protected': False})
    if deps['step_types']:
        key = f'tenant:{int(target_tenant_id)}:workflow_step_types_json'
        setting = db.session.get(Setting, key)
        if setting is None:
            setting = Setting(key=key)
            db.session.add(setting)
        setting.value = json.dumps(configured, ensure_ascii=False)
    db.session.flush()
    return {'label_ids': labels, 'notification_codes': notifications, 'form_names': forms, 'step_types': custom_codes}
