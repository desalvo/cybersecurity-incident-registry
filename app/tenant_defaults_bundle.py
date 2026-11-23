"""Portable, non-destructive backup of the complete shared configuration tenant.

This JSON format is independent of database IDs and the source encryption key.
It contains no application identities, incidents, audit trails or other tenants.
Callers own commit/rollback and must enforce superuser authorization.
"""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path

from flask import current_app

from .models import (
    db, Setting, Tenant, ConfigLabel, NotificationType, Recommendation,
    NotificationTemplate, ExternalRecipient, IncidentTemplate, BackupJob,
    IncidentWorkflowStep, FormTemplateConfig, FormTemplateBinary, FormFieldMapping,
    TenantDefaultSource,
)
from .workflow_catalog_models import WorkflowCatalogEntry
from .tenant_default_settings import is_tenant_parameter

BUNDLE_FORMAT = 'cybersecurity-incident-registry.tenants-default-bundle.v1'
MAX_BUNDLE_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
_CONFIG_MODELS = {
    'config_label': ConfigLabel, 'notification_type': NotificationType,
    'recommendation': Recommendation, 'notification_template': NotificationTemplate,
    'external_recipient': ExternalRecipient, 'incident_template': IncidentTemplate,
    'backup_job': BackupJob,
}
_ID_FIELDS = {
    'label_id': 'config_label', 'action_label_id': 'config_label',
    'severity_id': 'config_label', 'category_id': 'config_label',
    'data_type_id': 'config_label', 'recommendation_id': 'recommendation',
    'external_recipient_id': 'external_recipient',
    'notification_template_id': 'notification_template', 'incident_template_id': 'incident_template',
}
_CSV_FIELDS = {
    'category_ids': 'config_label', 'data_type_ids': 'config_label',
    'control_action_label_ids': 'config_label', 'recommendation_ids': 'recommendation',
}
_FORM_FIELDS = {'template_name', 'document_template_name', 'linked_form_template_name', 'generated_template_name'}
_SECRET_NAME = re.compile(r'password|secret|(?:^|_)api_key$|(?:^|_)token$|private_key|credential', re.I)
_SIMPLE_NAME = re.compile(r'^[A-Za-z0-9_-]{1,200}(?:\.pdf)?$')
_SETTING_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,79}$')
_DRAFT_FIELDS = (
    'position', 'description', 'personal_data_only', 'required', 'requires_notification',
    'document_generation_enabled', 'section_target', 'step_type',
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _objects(value, name, maximum=2000):
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(item, dict) for item in value):
        raise ValueError(f'{name}: elenco non valido o troppo lungo.')
    return value


def _text(value, name, maximum=20000, required=False):
    if not isinstance(value, str) or '\x00' in value or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'{name}: testo non valido.')
    return value


def _uuid(value, name):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f'{name}: UUID non valido.')
    return value


def _json_value(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    return value if isinstance(value, (dict, list)) else raw


def _normalise_button_setting(value, allowed):
    """Give legacy button IDs typed slots without rewriting unrelated numbers."""
    if not isinstance(value, dict):
        raise ValueError('Configurazione azioni pulsanti non valida.')
    result = copy.deepcopy(value)

    def rule(entry):
        if not isinstance(entry, dict) or '$cir_ref' in entry:
            return {'label_id': entry, 'scope': 'always'}
        normalized = dict(entry)
        if 'tags' in normalized:
            normalized['notification_tags'] = normalized.get('notification_tags') or normalized.pop('tags') or []
            normalized.pop('tags', None)
        if 'generated_template_name' in normalized:
            normalized['template_name'] = normalized.get('template_name') or normalized.pop('generated_template_name') or ''
            normalized.pop('generated_template_name', None)
        return normalized

    for code in allowed:
        if code in result:
            original = result[code]
            result[code] = [rule(entry) for entry in original] if isinstance(original, list) else rule(original)
    return result


def _find_form_names(value, field=''):
    names = set()
    if isinstance(value, dict):
        for key, item in value.items():
            names.update(_find_form_names(item, key))
    elif isinstance(value, list):
        for item in value:
            names.update(_find_form_names(item, field))
    elif isinstance(value, str) and value and (field in _FORM_FIELDS or field.endswith('_template_name')):
        names.add(value)
    return names


def _redact(value, field, paths, path=()):
    if field != 'sso_profiles_json' and _SECRET_NAME.search(field):
        paths.append(list(path))
        return ''
    if isinstance(value, dict):
        return {key: _redact(item, key, paths, path + (key,)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, '', paths, path + (index,)) for index, item in enumerate(value)]
    return value


def _restore_redacted(value, previous, paths, path=()):
    if list(path) in paths:
        return previous if previous is not None else ''
    if isinstance(value, dict):
        previous = previous if isinstance(previous, dict) else {}
        return {key: _restore_redacted(item, previous.get(key), paths, path + (key,)) for key, item in value.items()}
    if isinstance(value, list):
        previous = previous if isinstance(previous, list) else []
        restored = []
        for index, item in enumerate(value):
            old = previous[index] if index < len(previous) else None
            if isinstance(item, dict) and item.get('id') is not None:
                old = next((p for p in previous if isinstance(p, dict) and p.get('id') == item['id']), None)
            restored.append(_restore_redacted(item, old, paths, path + (index,)))
        return restored
    return value


def _encode_refs(value, field, ids, codes):
    model_kind = _ID_FIELDS.get(field)
    if model_kind and value not in (None, '', 0, '0'):
        if type(value) not in (str, int) or not str(value).isdigit() or int(value) not in ids[model_kind]:
            raise ValueError(f'Il parametro {field} riferisce un record esterno a Tenants Default.')
        return {'$cir_ref': ids[model_kind][int(value)], 'string': isinstance(value, str)}
    if field in _CSV_FIELDS and value:
        raw_ids = value.split(',') if isinstance(value, str) else value
        if not isinstance(raw_ids, list):
            raise ValueError(f'{field}: elenco ID non valido.')
        return {'$cir_csv': [_encode_refs(item.strip() if isinstance(item, str) else item, 'label_id' if _CSV_FIELDS[field] == 'config_label' else 'recommendation_id', ids, codes) for item in raw_ids if str(item).strip()], 'csv': isinstance(value, str)}
    if field in {'notification_type', 'required_notification_type', 'notification_tags'}:
        if isinstance(value, str) and value:
            tags = [code.strip() for code in value.split(',') if code.strip()] if field == 'notification_tags' else [value.strip()]
            if any(code not in codes for code in tags):
                raise ValueError(f'{field}: tipo notifica non presente nel tenant condiviso.')
            refs = [{'$cir_code': codes[code]} for code in tags]
            return {'$cir_tags': refs} if field == 'notification_tags' else refs[0]
        if isinstance(value, list):
            return [_encode_refs(item, 'notification_type', ids, codes) for item in value]
    if isinstance(value, dict):
        if any(str(key).startswith('$cir_') for key in value):
            raise ValueError('Parametro con chiavi riservate al formato portabile.')
        return {key: _encode_refs(item, key, ids, codes) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode_refs(item, field, ids, codes) for item in value]
    if field in {'conditions', 'condition'} and isinstance(value, str):
        if ',' in value:
            return {'$cir_conditions': [_encode_refs(token.strip(), 'condition', ids, codes) for token in value.split(',') if token.strip()]}
        match = re.fullmatch(r'(!?)(severity|data_type):(\d+)', value)
        if match:
            source_id = int(match[3])
            if source_id not in ids['config_label']:
                raise ValueError('Condizione con label esterna a Tenants Default.')
            return {'$cir_condition': ids['config_label'][source_id], 'kind': match[2], 'negated': bool(match[1])}
    return value


def _decode_refs(value, field, items, forms):
    if isinstance(value, dict):
        if '$cir_ref' in value:
            record = items[value['$cir_ref']]
            return str(record['id']) if value.get('string') else record['id']
        if '$cir_code' in value:
            return items[value['$cir_code']]['code']
        if '$cir_condition' in value:
            return ('!' if value['negated'] else '') + value['kind'] + ':' + str(items[value['$cir_condition']]['id'])
        if '$cir_csv' in value:
            result = [_decode_refs(item, '', items, forms) for item in value['$cir_csv']]
            return ','.join(map(str, result)) if value['csv'] else result
        if '$cir_tags' in value:
            return ','.join(_decode_refs(item, '', items, forms) for item in value['$cir_tags'])
        if '$cir_conditions' in value:
            return ','.join(_decode_refs(item, 'condition', items, forms) for item in value['$cir_conditions'])
        return {key: _decode_refs(item, key, items, forms) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_refs(item, field, items, forms) for item in value]
    if isinstance(value, str) and (field in _FORM_FIELDS or field.endswith('_template_name')):
        return forms.get(value, value)
    return value


def _validate_refs(value, configuration_items, field=''):
    if field in _ID_FIELDS and value not in (None, '', 0, '0') and (not isinstance(value, dict) or '$cir_ref' not in value):
        raise ValueError('ID database grezzo non consentito nel formato portabile.')
    if field in _CSV_FIELDS and value not in (None, '', []) and (not isinstance(value, dict) or '$cir_csv' not in value):
        raise ValueError('ID database grezzi non consentiti nel formato portabile.')
    if field in {'notification_type', 'required_notification_type', 'notification_tags'} and isinstance(value, str) and value:
        raise ValueError('Codice notifica grezzo non consentito nel formato portabile.')
    if field in {'condition', 'conditions'} and isinstance(value, str) and value not in ('', 'personal_data', '!personal_data'):
        raise ValueError('Condizione con riferimento grezzo o non supportata.')
    if isinstance(value, list):
        for item in value:
            _validate_refs(item, configuration_items, field)
    elif isinstance(value, dict):
        reserved = {key for key in value if key.startswith('$cir_')}
        if reserved:
            if len(reserved) != 1:
                raise ValueError('Riferimento portabile ambiguo.')
            key = next(iter(reserved))
            schemas = {
                '$cir_ref': {'$cir_ref', 'string'}, '$cir_code': {'$cir_code'},
                '$cir_condition': {'$cir_condition', 'kind', 'negated'},
                '$cir_csv': {'$cir_csv', 'csv'}, '$cir_tags': {'$cir_tags'},
                '$cir_conditions': {'$cir_conditions'},
            }
            if key not in schemas or set(value) != schemas[key]:
                raise ValueError('Riferimento portabile non valido.')
            if key in {'$cir_ref', '$cir_code', '$cir_condition'}:
                ref = value[key]
                if not isinstance(ref, str) or ref not in configuration_items:
                    raise ValueError('Riferimento a configurazione non inclusa nel bundle.')
                expected = 'notification_type' if key == '$cir_code' else ('config_label' if key == '$cir_condition' else _ID_FIELDS.get(field))
                if expected and configuration_items[ref]['type'] != expected:
                    raise ValueError('Tipo di riferimento portabile errato.')
                label_kind = {'action_label_id': 'action_label', 'severity_id': 'severity', 'category_id': 'category', 'data_type_id': 'data_type'}.get(field)
                if key == '$cir_ref' and label_kind and configuration_items[ref]['data'].get('kind') != label_kind:
                    raise ValueError('Tipo di label del parametro non valido.')
            if key == '$cir_ref' and type(value['string']) is not bool:
                raise ValueError('Rappresentazione ID non valida.')
            if key == '$cir_condition' and (value['kind'] not in {'severity', 'data_type'} or type(value['negated']) is not bool):
                raise ValueError('Condizione portabile non valida.')
            if key == '$cir_condition' and configuration_items[value[key]]['data'].get('kind') != value['kind']:
                raise ValueError('Condizione collegata a una label di tipo errato.')
            if key == '$cir_csv' and type(value['csv']) is not bool:
                raise ValueError('Rappresentazione CSV non valida.')
            if key in {'$cir_csv', '$cir_tags'}:
                if not isinstance(value[key], list):
                    raise ValueError('Elenco riferimenti non valido.')
                child_field = ('recommendation_id' if _CSV_FIELDS.get(field) == 'recommendation' else 'label_id') if key == '$cir_csv' else 'notification_type'
                expected_wrapper = '$cir_ref' if key == '$cir_csv' else '$cir_code'
                if any(not isinstance(item, dict) or expected_wrapper not in item for item in value[key]):
                    raise ValueError('Tipo elemento elenco riferimenti non valido.')
                for item in value[key]:
                    _validate_refs(item, configuration_items, child_field)
            if key == '$cir_conditions':
                if not isinstance(value[key], list) or any(not isinstance(item, dict) and item not in ('personal_data', '!personal_data') for item in value[key]):
                    raise ValueError('Elenco condizioni non valido.')
                for item in value[key]:
                    if isinstance(item, dict) and '$cir_condition' not in item:
                        raise ValueError('Tipo condizione non valido.')
                    _validate_refs(item, configuration_items, 'condition')
        else:
            for child_field, item in value.items():
                _validate_refs(item, configuration_items, child_field)
    elif field in _ID_FIELDS and value not in (None, '', 0, '0'):
        raise ValueError('ID database grezzo non consentito nel formato portabile.')
    elif field in _CSV_FIELDS and value not in (None, '', []):
        raise ValueError('ID database grezzi non consentiti nel formato portabile.')


def _export_document(name, notification_codes, source_tenant_id):
    if not isinstance(name, str) or not _SIMPLE_NAME.fullmatch(name):
        raise ValueError('Nome modello documento non portabile.')
    canonical_name = Path(name).stem
    configs = FormTemplateConfig.query.filter(FormTemplateConfig.template_name.in_({name, canonical_name})).all()
    for candidate in configs:
        candidate_owner = db.session.get(Tenant, candidate.owner_tenant_id) if candidate.owner_tenant_id is not None else None
        if candidate.owner_tenant_id not in (None, source_tenant_id) and not (candidate_owner and candidate_owner.is_system_defaults):
            raise ValueError('Il modello documento appartiene a un altro tenant.')
    # The filesystem and runtime reader use the stem. Check both identities
    # before a raw-name miss can fall back to a different tenant's physical PDF.
    config = next((candidate for candidate in configs if candidate.template_name == name), None)
    config = config or next((candidate for candidate in configs if candidate.template_name == canonical_name), None)
    owner = db.session.get(Tenant, config.owner_tenant_id) if config and config.owner_tenant_id is not None else None
    binary = FormTemplateBinary.query.filter_by(template_name=name).first()
    if binary is None and canonical_name != name:
        binary = FormTemplateBinary.query.filter_by(template_name=canonical_name).first()
    content = bytes(binary.pdf_data) if binary and binary.pdf_data else None
    if content is None:
        base = Path(current_app.config['FORM_TEMPLATE_DIR']).resolve()
        path = (base / (Path(name).stem + '.pdf')).resolve()
        if path.parent != base or not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError(f'PDF non disponibile per {name}.')
        content = path.read_bytes()
    if not content.startswith(b'%PDF-') or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError(f'PDF non valido o troppo grande: {name}.')
    tags = config.notification_tag_list if config else []
    if owner and owner.is_system_defaults and owner.id != source_tenant_id:
        from .tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
        remapped_tags = []
        for code in tags:
            shared_type = NotificationType.query.filter_by(tenant_id=owner.id, code=code).first()
            source = TenantDefaultSource.query.filter_by(source_type='notification_type', source_id=shared_type.id, active=True).first() if shared_type else None
            replica = TenantDefaultReplica.query.filter_by(source_id=source.id, tenant_id=source_tenant_id).first() if source else None
            local = db.session.get(NotificationType, replica.local_id) if replica else None
            if local is None or local.tenant_id != source_tenant_id:
                raise ValueError('Provenienza dei tag del PDF condiviso non disponibile nel tenant sorgente.')
            remapped_tags.append(local.code)
        tags = remapped_tags
    if any(code not in notification_codes for code in tags):
        raise ValueError(f'Il modello {name} usa tipi notifica esterni al tenant condiviso.')
    return {
        'name': name, 'pdf_base64': base64.b64encode(content).decode('ascii'),
        'font_family': config.font_family if config else 'Helvetica',
        'font_size': config.font_size if config else 10,
        'notification_refs': [notification_codes[code] for code in tags],
        'mappings': [{'template_field': row.template_field, 'db_field': row.db_field}
                     for row in FormFieldMapping.query.filter_by(template_name=config.template_name if config else canonical_name).order_by(FormFieldMapping.id)],
    }


def export_defaults_bundle(*, include_secrets=False, source_tenant_id=None, _for_initial_seed=False):
    from .tenant_defaults import ensure_defaults_tenant, export_configuration, exported_configuration_key
    from .routes import decrypt_setting_value, BUTTON_ACTIONS_SETTING, INCIDENT_BUTTON_ACTIONS
    from .tenant_default_settings import inherited_setting
    defaults = ensure_defaults_tenant() if source_tenant_id is None else db.session.get(Tenant, int(source_tenant_id))
    if defaults is None:
        raise ValueError('Tenant sorgente non disponibile.')
    configuration = export_configuration(defaults.id, include_extended=True, include_secrets=include_secrets,
                                         strip_personnel_references=_for_initial_seed)
    origin = configuration['origin']
    ids = {kind: {row.id: exported_configuration_key(origin, kind, defaults.id, row.id)
                  for row in model.query.filter_by(tenant_id=defaults.id)} for kind, model in _CONFIG_MODELS.items()}
    codes = {row.code: ids['notification_type'][row.id] for row in NotificationType.query.filter_by(tenant_id=defaults.id)}
    settings, form_names = [], set()
    prefix = f'tenant:{defaults.id}:'
    effective = {}
    # Older releases stored the operational default tenant's configuration
    # without a prefix. Only that same tenant may materialize those values;
    # neither the shared source nor another ordinary tenant can export them.
    if defaults.name == 'default' and not defaults.is_system_defaults:
        for row in Setting.query.filter(~Setting.key.startswith('tenant:')).order_by(Setting.key):
            if not is_tenant_parameter(row.key):
                continue
            raw = decrypt_setting_value(row.key, row.value or '')
            if (row.value or '').startswith('enc:v1:') and not raw:
                raise ValueError(f'Impossibile decifrare il parametro legacy {row.key}.')
            effective[row.key] = raw
    if not defaults.is_system_defaults:
        shared = Tenant.query.filter_by(is_system_defaults=True).first()
        if shared is not None:
            shared_prefix = f'tenant:{shared.id}:'
            for row in Setting.query.filter(Setting.key.startswith(shared_prefix)).order_by(Setting.key):
                logical = row.key[len(shared_prefix):]
                if is_tenant_parameter(logical):
                    raw = decrypt_setting_value(logical, row.value or '')
                    if (row.value or '').startswith('enc:v1:') and not raw:
                        raise ValueError(f'Impossibile decifrare il parametro condiviso {logical}.')
                    effective[logical] = inherited_setting(logical, defaults.id)
    for row in Setting.query.filter(Setting.key.startswith(prefix)).order_by(Setting.key):
        logical = row.key[len(prefix):]
        if not is_tenant_parameter(logical):
            continue
        raw = decrypt_setting_value(logical, row.value or '')
        if (row.value or '').startswith('enc:v1:') and (not raw or raw.startswith('enc:v1:')):
            raise ValueError(f'Impossibile decifrare il parametro {logical}; verificare la chiave dell istanza sorgente.')
        effective[logical] = raw
    for logical, raw in sorted(effective.items()):
        if not _SETTING_NAME.fullmatch(logical):
            raise ValueError(f'Parametro non portabile: {logical}.')
        value = _json_value(raw)
        if logical == BUTTON_ACTIONS_SETTING:
            value = _normalise_button_setting(value, {code for code, _label in INCIDENT_BUTTON_ACTIONS})
        form_names.update(_find_form_names(value, logical))
        redacted = []
        if not include_secrets:
            value = _redact(value, logical, redacted)
        settings.append({'key': logical, 'value': _encode_refs(value, logical, ids, codes),
                         'structured': isinstance(_json_value(raw), (dict, list)), 'redacted_paths': redacted})
    for row in NotificationTemplate.query.filter_by(tenant_id=defaults.id):
        if row.linked_form_template_name:
            form_names.add(row.linked_form_template_name)
    owned_forms = FormTemplateConfig.query.filter_by(owner_tenant_id=defaults.id)
    form_names.update(row.template_name for row in owned_forms)
    if defaults.name == 'default' and not defaults.is_system_defaults:
        form_names.update(row.template_name for row in FormTemplateConfig.query.filter_by(owner_tenant_id=None))
    drafts, draft_scopes = [], {}
    from .workflow_lifecycle import portable_workflow_lifecycle, workflow_scope_key
    categories = {row.category_id for row in IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id)}
    for category_id in sorted(categories, key=lambda value: -1 if value is None else value):
        if category_id is not None and category_id not in ids['config_label']:
            raise ValueError('La bozza workflow riferisce una categoria di un altro tenant.')
        steps = []
        for row in IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id, category_id=category_id).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id):
            if row.required_notification_type and row.required_notification_type not in codes:
                raise ValueError('La bozza workflow riferisce un tipo notifica non presente nel tenant.')
            if row.document_template_name:
                form_names.add(row.document_template_name)
            conditions = [_encode_refs(token, 'conditions', ids, codes) for token in row.condition_tokens()]
            steps.append({**{field: getattr(row, field) for field in _DRAFT_FIELDS},
                'action_ref': ids['config_label'].get(row.action_label_id), 'conditions': conditions,
                'notification_ref': codes.get(row.required_notification_type) if row.required_notification_type else None,
                'document_template_name': row.document_template_name or ''})
        draft_key = str(uuid.uuid5(uuid.UUID(origin), f'draft:{defaults.id}:{category_id}'))
        draft_scopes[workflow_scope_key(category_id)] = draft_key
        drafts.append({'key': draft_key,
                       'category_ref': ids['config_label'].get(category_id) if category_id else None,
                       'steps': steps, 'status': portable_workflow_lifecycle(defaults.id, category_id)['status']})
    catalog = []
    from .workflow_catalog import validate_catalog_payload
    for row in (WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=defaults.id).order_by(WorkflowCatalogEntry.id) if defaults.is_system_defaults else []):
        portable = validate_catalog_payload(json.loads(row.payload_json))
        if _hash(portable) != row.payload_hash:
            raise ValueError('Impronta della voce catalogo non valida.')
        catalog.append({'public_id': row.public_id, 'name': row.name, 'description': row.description,
                        'version': row.version, 'active': bool(row.active),
                        'status': row.status, 'source_draft_key': draft_scopes.get(row.source_scope_key),
                        'payload': portable})
    sources = {}
    if defaults.is_system_defaults:
        for source in TenantDefaultSource.query.filter_by(active=True):
            reference = ids.get(source.source_type, {}).get(source.source_id)
            if reference is not None:
                sources[source.id] = reference
    from .tenant_defaults_assets import export_defaults_assets
    result = {'format': BUNDLE_FORMAT, 'origin': origin,
              'bundle_id': str(uuid.uuid5(uuid.UUID(origin), f'tenant-bundle:{defaults.id}')),
              'tenant': {'name': defaults.name, 'description': defaults.description or '', 'is_system_defaults': bool(defaults.is_system_defaults)},
              'includes_secrets': bool(include_secrets), 'configuration': configuration,
              'configuration_sources': sources,
              'settings': settings, 'documents': [_export_document(name, codes, defaults.id) for name in sorted(form_names)],
              'draft_workflows': drafts, 'catalog': catalog, 'assets': export_defaults_assets(settings)}
    return validate_defaults_bundle(result)


def validate_defaults_bundle(payload):
    from .tenant_defaults import validate_configuration_payload
    from .workflow_catalog import validate_catalog_payload
    from .routes import BUTTON_ACTIONS_SETTING, INCIDENT_BUTTON_ACTIONS
    expected = {'format', 'origin', 'bundle_id', 'tenant', 'includes_secrets', 'configuration', 'settings', 'documents', 'draft_workflows', 'catalog', 'assets'}
    if (not isinstance(payload, dict) or not expected <= set(payload)
            or set(payload) - expected - {'configuration_sources'} or payload.get('format') != BUNDLE_FORMAT):
        raise ValueError('Formato bundle Tenants Default non valido.')
    try:
        if len(_canonical(payload).encode('utf-8')) > MAX_BUNDLE_BYTES:
            raise ValueError('Bundle troppo grande (massimo 25 MiB).')
    except (TypeError, RecursionError) as exc:
        raise ValueError('Bundle JSON non valido.') from exc
    origin = _uuid(payload['origin'], 'Origine bundle')
    _uuid(payload['bundle_id'], 'Identità bundle')
    if type(payload['includes_secrets']) is not bool:
        raise ValueError('Indicatore credenziali non valido.')
    tenant = payload['tenant']
    if not isinstance(tenant, dict) or set(tenant) != {'name', 'description', 'is_system_defaults'}:
        raise ValueError('Metadati tenant sorgente non validi.')
    _text(tenant['name'], 'Nome tenant sorgente', 80, required=True)
    if type(tenant['is_system_defaults']) is not bool or (tenant['is_system_defaults'] and tenant['name'] != 'Tenants Default'):
        raise ValueError('Identità del tenant di configurazione non valida.')
    _text(tenant['description'], 'Descrizione tenant')
    configuration = validate_configuration_payload(payload['configuration'])
    if configuration['origin'] != origin:
        raise ValueError('Origine configurazioni diversa da quella del bundle.')
    items = {item['key']: item for item in configuration['items']}
    sources = payload.get('configuration_sources', {})
    if not isinstance(sources, dict) or len(sources) > len(items):
        raise ValueError('Provenienza delle configurazioni condivise non valida.')
    seen_source_items = set()
    for source_uuid, item_uuid in sources.items():
        _uuid(source_uuid, 'Sorgente condivisa')
        _uuid(item_uuid, 'Configurazione condivisa')
        if item_uuid not in items or item_uuid in seen_source_items:
            raise ValueError('Provenienza condivisa duplicata o priva di configurazione.')
        seen_source_items.add(item_uuid)
    if sources and not tenant['is_system_defaults']:
        raise ValueError('Solo il bundle Tenants Default può definire sorgenti condivise.')

    def ref(value, kind, nullable=False, label_kind=None):
        if value is None and nullable:
            return
        if not isinstance(value, str) or value not in items or items[value]['type'] != kind:
            raise ValueError('Riferimento configurazione mancante o di tipo non valido.')
        if label_kind and items[value]['data'].get('kind') != label_kind:
            raise ValueError('Tipo label del riferimento non valido.')

    settings, seen_settings = [], set()
    for row in _objects(payload['settings'], 'Settings'):
        if set(row) != {'key', 'value', 'structured', 'redacted_paths'}:
            raise ValueError('Record parametro non valido.')
        key = row['key']
        if not isinstance(key, str) or not _SETTING_NAME.fullmatch(key) or not is_tenant_parameter(key) or key in seen_settings:
            raise ValueError('Parametro duplicato, globale o non consentito.')
        seen_settings.add(key)
        if type(row['structured']) is not bool or not isinstance(row['redacted_paths'], list):
            raise ValueError('Metadati parametro non validi.')
        if not row['structured'] and not isinstance(row['value'], str) and not (isinstance(row['value'], dict) and any(key.startswith('$cir_') for key in row['value'])):
            raise ValueError('Il parametro semplice deve essere testo o un riferimento portabile.')
        for path in row['redacted_paths']:
            if not isinstance(path, list) or len(path) > 32 or any(type(part) not in (str, int) or (type(part) is int and part < 0) for part in path):
                raise ValueError('Percorso valore oscurato non valido.')
        if row['structured'] != isinstance(row['value'], (dict, list)) and not (isinstance(row['value'], dict) and any(key.startswith('$cir_') for key in row['value'])):
            raise ValueError('Tipo del valore parametro non coerente.')
        if key == BUTTON_ACTIONS_SETTING:
            row = copy.deepcopy(row)
            allowed_buttons = {code for code, _label in INCIDENT_BUTTON_ACTIONS}
            row['value'] = _normalise_button_setting(row['value'], allowed_buttons)
            for button, rules in row['value'].items():
                if button not in allowed_buttons:
                    continue
                for rule in rules if isinstance(rules, list) else [rules]:
                    if 'label_id' not in rule:
                        raise ValueError('Azione pulsante priva di riferimento alla label.')
                    _validate_refs(rule['label_id'], items, 'action_label_id')
        _validate_refs(row['value'], items, key)
        settings.append(copy.deepcopy(row))
    documents, names = [], set()
    for row in _objects(payload['documents'], 'Documenti', 256):
        if set(row) != {'name', 'pdf_base64', 'font_family', 'font_size', 'notification_refs', 'mappings'}:
            raise ValueError('Record documento non valido.')
        name = row['name']
        if not isinstance(name, str) or not _SIMPLE_NAME.fullmatch(name) or name in names:
            raise ValueError('Nome documento duplicato o non sicuro.')
        names.add(name)
        encoded = row['pdf_base64']
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_DOCUMENT_BYTES + 2) // 3):
            raise ValueError('PDF troppo grande.')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Codifica PDF non valida.') from exc
        if not content.startswith(b'%PDF-') or len(content) > MAX_DOCUMENT_BYTES:
            raise ValueError('Contenuto PDF non valido.')
        if not isinstance(row['notification_refs'], list):
            raise ValueError('Tag documento non validi.')
        for reference in row['notification_refs']:
            ref(reference, 'notification_type')
        fields = set()
        for mapping in _objects(row['mappings'], 'Mappature PDF'):
            if set(mapping) != {'template_field', 'db_field'}:
                raise ValueError('Mappatura PDF non valida.')
            for key in ('template_field', 'db_field'):
                _text(mapping[key], key, 255, required=True)
            if mapping['template_field'] in fields:
                raise ValueError('Mappatura PDF duplicata.')
            fields.add(mapping['template_field'])
        _text(row['font_family'], 'Font PDF', 40)
        if type(row['font_size']) is not int or not 8 <= row['font_size'] <= 16:
            raise ValueError('Dimensione font PDF non valida.')
        documents.append(copy.deepcopy(row))
    for item in items.values():
        if item['type'] == 'notification_template':
            form = item['data'].get('linked_form_template_name')
            if form and form not in names:
                raise ValueError('Documento richiesto da un template notifica non incluso.')
    for row in settings:
        if _find_form_names(row['value'], row['key']) - names:
            raise ValueError('Documento richiesto da un parametro non incluso.')
    drafts, draft_keys = [], set()
    for draft in _objects(payload['draft_workflows'], 'Bozze workflow', 256):
        if not {'key', 'category_ref', 'steps'} <= set(draft) or set(draft) - {'key', 'category_ref', 'steps', 'status'}:
            raise ValueError('Bozza workflow non valida.')
        if draft.get('status', 'current') not in ('current', 'obsolete'):
            raise ValueError('Stato bozza workflow non valido.')
        key = _uuid(draft['key'], 'Bozza workflow')
        if key in draft_keys:
            raise ValueError('Bozza duplicata.')
        draft_keys.add(key)
        ref(draft['category_ref'], 'config_label', nullable=True, label_kind='category')
        for step in _objects(draft['steps'], 'Step bozza', 256):
            if set(step) != set(_DRAFT_FIELDS) | {'action_ref', 'conditions', 'notification_ref', 'document_template_name'}:
                raise ValueError('Step bozza non valido.')
            ref(step['action_ref'], 'config_label', label_kind='action_label')
            ref(step['notification_ref'], 'notification_type', nullable=True)
            if type(step['position']) is not int or not 0 <= step['position'] <= 1000000:
                raise ValueError('Ordine step non valido.')
            for field in ('personal_data_only', 'required', 'requires_notification', 'document_generation_enabled'):
                if type(step[field]) is not bool:
                    raise ValueError('Flag step non valido.')
            _text(step['description'] or '', 'Descrizione step', 100000)
            _text(step['step_type'], 'Tipo step', 20, required=True)
            if step['section_target'] is not None:
                _text(step['section_target'], 'Sezione step', 80)
            if not isinstance(step['conditions'], list):
                raise ValueError('Condizioni step non valide.')
            for condition in step['conditions']:
                if condition != 'personal_data' and condition != '!personal_data':
                    if not isinstance(condition, dict) or '$cir_condition' not in condition:
                        raise ValueError('Condizione workflow non portabile.')
                _validate_refs(condition, items)
            if step['requires_notification'] and not step['notification_ref']:
                raise ValueError('Tipo notifica obbligatorio mancante.')
            if step['document_template_name'] and step['document_template_name'] not in names:
                raise ValueError('Documento richiesto dallo step non incluso.')
            if step['document_generation_enabled'] and not step['document_template_name']:
                raise ValueError('Documento workflow obbligatorio mancante.')
        if not draft['steps']:
            raise ValueError('Bozza priva di step.')
        drafts.append({**copy.deepcopy(draft), 'status': draft.get('status', 'current')})
    catalog, public_ids = [], set()
    for row in _objects(payload['catalog'], 'Catalogo', 256):
        if (not {'public_id', 'name', 'description', 'version', 'active', 'payload'} <= set(row)
                or set(row) - {'public_id', 'name', 'description', 'version', 'active', 'payload', 'status', 'source_draft_key'}):
            raise ValueError('Voce catalogo non valida.')
        public_id = _uuid(row['public_id'], 'Catalogo')
        if public_id in public_ids:
            raise ValueError('Voce catalogo duplicata.')
        public_ids.add(public_id)
        _text(row['name'], 'Nome catalogo', 160, required=True)
        _text(row['description'], 'Descrizione catalogo', 100000)
        if type(row['version']) is not int or row['version'] <= 0 or type(row['active']) is not bool:
            raise ValueError('Versione/stato catalogo non valido.')
        portable = validate_catalog_payload(row['payload'])
        status = row.get('status', portable['workflow'].get('status', 'current'))
        if status not in ('current', 'obsolete'):
            raise ValueError('Stato voce catalogo non valido.')
        draft_key = row.get('source_draft_key')
        if draft_key is not None:
            _uuid(draft_key, 'Bozza sorgente catalogo')
            if draft_key not in draft_keys:
                raise ValueError('Bozza sorgente della voce catalogo non inclusa.')
            if next(draft['status'] for draft in drafts if draft['key'] == draft_key) != status:
                raise ValueError('Stato della bozza sorgente non coerente con il catalogo.')
        if status == 'current' and portable['workflow'].get('status') == 'obsolete':
            raise ValueError('Stato catalogo incoerente con lo snapshot obsoleto.')
        for table, kind in (('labels', 'config_label'), ('notification_types', 'notification_type'),
                            ('notification_templates', 'notification_template')):
            for dependency in portable['dependencies'].get(table, []):
                reference = sources.get(dependency.get('shared_source_id'))
                if reference is not None and items[reference]['type'] != kind:
                    raise ValueError('Tipo della provenienza condivisa del catalogo non coerente.')
                if (reference is not None and kind == 'config_label'
                        and items[reference]['data']['kind'] != dependency['kind']):
                    raise ValueError('Tipo della label condivisa del catalogo non coerente.')
        catalog.append({**row, 'status': status, 'source_draft_key': draft_key, 'payload': portable})
    if catalog and not tenant['is_system_defaults']:
        raise ValueError('Un bundle di tenant operativo non può includere il catalogo condiviso.')
    from .tenant_defaults_assets import validate_defaults_assets
    assets = validate_defaults_assets(payload['assets'], settings)
    return {**copy.deepcopy(payload), 'configuration': configuration, 'settings': settings,
            'configuration_sources': copy.deepcopy(sources),
            'documents': documents, 'draft_workflows': drafts, 'catalog': catalog, 'assets': assets}



def _document_snapshot(name):
    binary = FormTemplateBinary.query.filter_by(template_name=name).first()
    config = FormTemplateConfig.query.filter_by(template_name=name).first()
    return {
        'binary': hashlib.sha256(bytes(binary.pdf_data or b'')).hexdigest() if binary else None,
        'font_family': config.font_family if config else None,
        'font_size': config.font_size if config else None,
        'owner_tenant_id': config.owner_tenant_id if config else None,
        'tags': config.notification_tags if config else None,
        'mappings': [{'template_field': row.template_field, 'db_field': row.db_field}
                     for row in FormFieldMapping.query.filter_by(template_name=name).order_by(FormFieldMapping.template_field)],
    }


def _draft_snapshot(rows):
    return [{**{field: getattr(row, field) for field in _DRAFT_FIELDS},
             'id': row.id, 'category_id': row.category_id, 'action_label_id': row.action_label_id,
             'conditions': row.conditions, 'required_notification_type': row.required_notification_type,
             'document_template_name': row.document_template_name} for row in sorted(rows, key=lambda r: r.id)]


def _draft_state_snapshot(rows, tenant_id, category_id):
    from .workflow_lifecycle import get_workflow_state
    state = get_workflow_state(tenant_id, category_id)
    return {'steps': _draft_snapshot(rows), 'status': state.status if state else 'current',
            'source_entry_id': state.source_entry_id if state else None,
            'personalized': bool(state.personalized) if state else False}


def _catalog_snapshot(entry):
    return {'payload': entry.payload_hash, 'name': entry.name, 'description': entry.description,
            'active': entry.active, 'status': entry.status, 'source_scope_key': entry.source_scope_key}


def _remap_catalog_shared_sources(payload, sources):
    """Bind portable source identities to their destination configuration only.

    Unmapped/retired identities retain the independent dependency snapshot and
    cannot accidentally claim a similarly named or externally supplied UUID.
    """
    result = copy.deepcopy(payload)
    for table in ('labels', 'notification_types', 'notification_templates'):
        for dependency in result['dependencies'].get(table, []):
            source = dependency.pop('shared_source_id', None)
            if source in sources:
                dependency['shared_source_id'] = sources[source]
    # The enclosing bundle re-establishes catalog/draft provenance itself.
    # An unrelated local catalog UUID must not veto or capture a portable copy.
    result['workflow'].pop('catalog_source_public_id', None)
    return result


def _unique_category(defaults_id, name):
    original = name[:230]
    candidate, count = original, 1
    while ConfigLabel.query.filter_by(tenant_id=defaults_id, kind='category', value=candidate).first():
        count += 1
        candidate = f'{original} [Import {count}]'
    row = ConfigLabel(tenant_id=defaults_id, kind='category', value=candidate, group='workflow importati')
    db.session.add(row)
    db.session.flush()
    return row.id


def import_defaults_bundle(payload):
    """Merge one complete defaults bundle without overwriting unrelated data."""
    from .tenant_defaults import ensure_defaults_tenant, import_configuration, sync_defaults_configuration
    from .routes import decrypt_setting_value, store_setting_value
    from .workflow_catalog import save_catalog_workflow
    payload = validate_defaults_bundle(payload)
    defaults = ensure_defaults_tenant()
    Tenant.query.filter_by(id=defaults.id).with_for_update().one()
    metadata_key = '__cir_defaults_bundle:' + payload['bundle_id']
    metadata_row = db.session.get(Setting, metadata_key)
    try:
        metadata = json.loads(metadata_row.value) if metadata_row else {}
    except (ValueError, TypeError) as exc:
        raise ValueError('Provenienza bundle locale non valida.') from exc
    if (not isinstance(metadata, dict)
            or any(not isinstance(metadata.get(key, {}), dict) for key in ('documents', 'settings', 'drafts', 'catalog'))
            or any(not isinstance(value, dict) for key in ('documents', 'drafts', 'catalog') for value in metadata.get(key, {}).values())):
        raise ValueError('Provenienza bundle locale non valida.')
    result = {'configuration': {}, 'documents': 0, 'assets': len(payload['assets']), 'settings': 0, 'preserved_settings': [],
              'draft_workflows': 0, 'catalog': 0, 'preserved_drafts': 0, 'preserved_catalog': 0}
    forms, document_metadata, new_forms = {}, metadata.get('documents', {}), set()
    config_payload = copy.deepcopy(payload['configuration'])
    # Reserve fresh names before config import so every notification template
    # points directly to an owned destination document, never a shared old file.
    for document in payload['documents']:
        content = base64.b64decode(document['pdf_base64'], validate=True)
        signature = _hash(document)
        previous = document_metadata.get(document['name'], {})
        candidate = previous.get('name') if previous.get('hash') == signature else None
        binary = FormTemplateBinary.query.filter_by(template_name=candidate).first() if candidate else None
        if (binary is None or bytes(binary.pdf_data or b'') != content
                or previous.get('local_hash') != _hash(_document_snapshot(candidate))):
            stem = Path(document['name']).stem[:120]
            base_name = f'td_{payload["bundle_id"][:8]}_{signature[:12]}_{stem}'
            candidate, index = base_name, 1
            base = Path(current_app.config['FORM_TEMPLATE_DIR']).resolve()
            while (FormTemplateBinary.query.filter_by(template_name=candidate).first()
                   or FormTemplateConfig.query.filter_by(template_name=candidate).first()
                   or FormFieldMapping.query.filter_by(template_name=candidate).first()
                   or (base / (candidate + '.pdf')).exists()):
                index += 1
                candidate = f'{base_name}_{index}'
            db.session.add(FormTemplateBinary(template_name=candidate, filename=candidate + '.pdf', pdf_data=content))
            db.session.add(FormTemplateConfig(template_name=candidate, owner_tenant_id=defaults.id,
                font_family=FormTemplateConfig.normalize_font_family(document['font_family']), font_size=document['font_size']))
            db.session.flush()
            new_forms.add(candidate)
            result['documents'] += 1
        forms[document['name']] = candidate
        document_metadata[document['name']] = {'name': candidate, 'hash': signature}
    for item in config_payload['items']:
        if item['type'] == 'notification_template' and item['data'].get('linked_form_template_name'):
            item['data']['linked_form_template_name'] = forms[item['data']['linked_form_template_name']]
    configuration_result = import_configuration(config_payload, defaults.id)
    result['configuration'] = {key: value for key, value in configuration_result.items() if key != 'items'}
    item_map = configuration_result['items']
    shared_sources = {}
    for source_uuid, item_uuid in payload['configuration_sources'].items():
        item = item_map[item_uuid]
        published = TenantDefaultSource.query.filter_by(source_type=item['type'], source_id=item['id'], active=True).one_or_none()
        if published is None:
            raise ValueError('Configurazione condivisa importata priva di provenienza pubblicata.')
        shared_sources[source_uuid] = published.id
    for reference, item in item_map.items():
        if item['type'] == 'notification_type':
            item['code'] = db.session.get(NotificationType, item['id']).code
    for document in payload['documents']:
        name = forms[document['name']]
        config = FormTemplateConfig.query.filter_by(template_name=name).first()
        if name in new_forms:
            config.set_notification_tags([item_map[ref]['code'] for ref in document['notification_refs']])
            for mapping in document['mappings']:
                db.session.add(FormFieldMapping(template_name=name, **mapping))
    for document in payload['documents']:
        document_metadata[document['name']]['local_hash'] = _hash(_document_snapshot(forms[document['name']]))
    from .tenant_defaults_assets import import_defaults_assets, remap_defaults_asset_references
    asset_mapping = import_defaults_assets(payload['assets'])
    setting_metadata = metadata.get('settings', {})
    for setting in payload['settings']:
        key = setting['key']
        physical = f'tenant:{defaults.id}:{key}'
        if len(physical) > 100:
            raise ValueError('Nome del parametro troppo lungo per il tenant di destinazione.')
        previous = db.session.get(Setting, physical)
        expected_hash = setting_metadata.get(key)
        if previous is not None and expected_hash != _hash(previous.value):
            result['preserved_settings'].append(key)
            continue
        old = _json_value(decrypt_setting_value(key, previous.value or '')) if previous else None
        value = _decode_refs(setting['value'], key, item_map, forms)
        value = remap_defaults_asset_references(value, key, asset_mapping)
        value = _restore_redacted(value, old, setting['redacted_paths'])
        raw = json.dumps(value, ensure_ascii=False) if setting['structured'] else str(value or '')
        stored = store_setting_value(key, raw)
        if previous is None:
            previous = Setting(key=physical, value=stored)
            db.session.add(previous)
        else:
            previous.value = stored
        setting_metadata[key] = _hash(stored)
        result['settings'] += 1
    draft_metadata = metadata.get('drafts', {})
    from .workflow_lifecycle import ensure_workflow_state, set_catalog_workflow_status, workflow_scope_key
    from .timeutils import utcnow
    for draft in payload['draft_workflows']:
        previous = draft_metadata.get(draft['key'], {})
        existing_ids = previous.get('step_ids', [])
        existing = IncidentWorkflowStep.query.filter(IncidentWorkflowStep.id.in_(existing_ids or [-1]), IncidentWorkflowStep.tenant_id == defaults.id).all()
        unchanged_local = (bool(existing_ids) and len(existing) == len(existing_ids)
                           and _hash(_draft_state_snapshot(existing, defaults.id, previous.get('category_id'))) == previous.get('local_hash'))
        incoming_hash = _hash({'draft': draft, 'forms': forms, 'items': item_map})
        if unchanged_local and previous.get('incoming_hash') == incoming_hash:
            continue
        if unchanged_local:
            category_id = previous.get('category_id')
            for row in existing:
                db.session.delete(row)
            db.session.flush()
        else:
            category_id = item_map[draft['category_ref']]['id'] if draft['category_ref'] else None
            if IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id, category_id=category_id).first():
                label = db.session.get(ConfigLabel, category_id) if category_id else None
                category_id = _unique_category(defaults.id, (label.value if label else 'Workflow di default') + ' importato')
                result['preserved_drafts'] += 1
        created = []
        for step in draft['steps']:
            fields = {key: step[key] for key in _DRAFT_FIELDS}
            row = IncidentWorkflowStep(tenant_id=defaults.id, category_id=category_id,
                action_label_id=item_map[step['action_ref']]['id'],
                required_notification_type=item_map[step['notification_ref']]['code'] if step['notification_ref'] else None,
                document_template_name=forms.get(step['document_template_name']), **fields)
            row.set_condition_tokens([_decode_refs(condition, '', item_map, forms) for condition in step['conditions']])
            db.session.add(row)
            created.append(row)
        db.session.flush()
        state = ensure_workflow_state(defaults.id, category_id)
        state.status = draft['status']
        state.obsolete_at = utcnow() if state.status == 'obsolete' else None
        draft_metadata[draft['key']] = {'category_id': category_id, 'step_ids': [row.id for row in created],
                                      'local_hash': _hash(_draft_state_snapshot(created, defaults.id, category_id)), 'incoming_hash': incoming_hash}
        result['draft_workflows'] += 1
    catalog_metadata = metadata.get('catalog', {})
    for record in payload['catalog']:
        previous = catalog_metadata.get(record['public_id'], {})
        entry = db.session.get(WorkflowCatalogEntry, previous.get('id')) if previous.get('id') else None
        if entry is not None and (entry.defaults_tenant_id != defaults.id or previous.get('local_hash') != _hash(_catalog_snapshot(entry))):
            result['preserved_catalog'] += 1
            entry = None
        portable = _remap_catalog_shared_sources(record['payload'], shared_sources)
        portable['workflow']['status'] = record['status']
        entry = save_catalog_workflow(portable, record['name'], record['description'], entry_id=entry.id if entry else None)
        if not WorkflowCatalogEntry.query.filter_by(public_id=record['public_id']).first():
            entry.public_id = record['public_id']
        entry.version = max(entry.version, record['version'])
        entry.active = record['active']
        draft_key = record['source_draft_key']
        entry.source_scope_key = workflow_scope_key(draft_metadata[draft_key]['category_id']) if draft_key else None
        if entry.status != record['status']:
            set_catalog_workflow_status(entry.id, record['status'])
        if draft_key:
            state = ensure_workflow_state(defaults.id, draft_metadata[draft_key]['category_id'])
            state.status = record['status']
            state.obsolete_at = entry.obsolete_at
        catalog_metadata[record['public_id']] = {'id': entry.id, 'local_hash': _hash(_catalog_snapshot(entry))}
        result['catalog'] += 1
    # Catalog status may have updated a linked source draft in the same import.
    for draft in payload['draft_workflows']:
        previous = draft_metadata[draft['key']]
        rows = IncidentWorkflowStep.query.filter(IncidentWorkflowStep.id.in_(previous['step_ids']),
            IncidentWorkflowStep.tenant_id == defaults.id).all()
        previous['local_hash'] = _hash(_draft_state_snapshot(rows, defaults.id, previous['category_id']))
    metadata.update(settings=setting_metadata, documents=document_metadata, drafts=draft_metadata, catalog=catalog_metadata)
    if payload['tenant']['is_system_defaults']:
        previous_description = defaults.description or ''
        expected_description = metadata.get('tenant_description_hash')
        if expected_description == _hash(previous_description) or previous_description in ('', 'Configurazioni e catalogo condivisi per tutti i tenant'):
            defaults.description = payload['tenant']['description']
            metadata['tenant_description_hash'] = _hash(defaults.description)
        else:
            result['preserved_tenant_description'] = True
    if metadata_row is None:
        metadata_row = Setting(key=metadata_key)
        db.session.add(metadata_row)
    metadata_row.value = _canonical(metadata)
    db.session.flush()
    sync_defaults_configuration()
    return result
