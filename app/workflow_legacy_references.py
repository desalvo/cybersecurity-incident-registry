"""Safe source-reference mapping for the older workflow.v1 transfer UI.

An unqualified numeric ID in a historical condition is never interpreted as a
destination database ID. Its meaning must be stated by an included definition.
"""
import re
import uuid

_CONDITION = re.compile(r'^(severity|data_type):([1-9][0-9]*)$')
_KINDS = {'action_label', 'category', 'severity', 'data_type'}
_REEXPORT = ('ID di condizione non attribuibile alle definizioni incluse: '
             'riesportare il workflow dal catalogo con le dipendenze e ripetere l’importazione.')


def _identity(value):
    if (not isinstance(value, dict) or not isinstance(value.get('kind'), str) or value['kind'] not in _KINDS
            or not isinstance(value.get('value'), str) or not value['value'].strip()):
        raise ValueError('Definizione label del workflow non valida.')
    return value['kind'], value['value']


def legacy_workflow_label_index(payload):
    """Validate all condition attribution before the first database mutation."""
    if not isinstance(payload, dict):
        raise ValueError('Workflow JSON non valido.')
    dependencies, workflow = payload.get('dependencies') or {}, payload.get('workflow') or {}
    if not isinstance(dependencies, dict) or not isinstance(workflow, dict):
        raise ValueError('Workflow JSON non valido.')
    labels, steps = dependencies.get('labels') or [], workflow.get('steps') or []
    if not isinstance(labels, list) or not isinstance(steps, list):
        raise ValueError('Definizioni workflow non valide.')
    index = {'identities': {}, 'source_ids': {}}
    for label in labels:
        identity = _identity(label)
        if identity in index['identities']:
            raise ValueError('Definizioni label duplicate o ambigue nel workflow.')
        source_id = label.get('source_id', label.get('id'))
        if 'source_id' in label and 'id' in label and label['source_id'] != label['id']:
            raise ValueError('ID sorgente ambiguo nel workflow.')
        if source_id is not None:
            if type(source_id) is not int or source_id <= 0:
                raise ValueError('ID sorgente della label non valido.')
            key = (identity[0], source_id)
            if key in index['source_ids']:
                raise ValueError('ID sorgente ambiguo nel workflow.')
            index['source_ids'][key] = label
        source_uuid = label.get('shared_source_id')
        if source_uuid is not None:
            try:
                if not isinstance(source_uuid, str) or str(uuid.UUID(source_uuid)) != source_uuid:
                    raise ValueError
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError('Identità della label condivisa non valida.') from exc
        index['identities'][identity] = label
    references = [workflow.get('category')] if workflow.get('category') else []
    templates = dependencies.get('notification_templates') or []
    if not isinstance(templates, list) or any(not isinstance(item, dict) for item in templates):
        raise ValueError('Template di notifica del workflow non validi.')
    references.extend(item['action_label'] for item in templates if item.get('action_label'))
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError('Step workflow non valido.')
        references.append(step.get('action_label'))
        legacy_map_conditions(step.get('conditions') or [], index, lambda label: 'validated')
    for reference in references:
        if _identity(reference) not in index['identities']:
            raise ValueError('Label richiesta dal workflow assente dalle definizioni incluse.')
        definition = index['identities'][_identity(reference)]
        for field in ('source_id', 'shared_source_id'):
            if field in reference and field in definition and reference[field] != definition[field]:
                raise ValueError('Provenienza label incoerente fra step e dipendenze.')
    return index


def legacy_map_conditions(tokens, index, resolve_id):
    if not isinstance(tokens, list) or any(not isinstance(token, str) for token in tokens):
        raise ValueError('Condizioni workflow non valide.')
    mapped = []
    for token in tokens:
        negated = token.startswith('!')
        value = token[1:] if negated else token
        if value != 'personal_data':
            match = _CONDITION.fullmatch(value)
            if match is None:
                raise ValueError('Condizione workflow non supportata.')
            kind, source_id = match.group(1), int(match.group(2))
            definition = index['source_ids'].get((kind, source_id))
            if definition is None:
                raise ValueError(_REEXPORT)
            destination_id = resolve_id(definition)
            if destination_id is None:
                raise ValueError('Dipendenza condizionale non disponibile nel tenant destinatario.')
            value = f'{kind}:{destination_id}'
        mapped.append(('!' if negated else '') + value)
    return mapped


def legacy_label_metadata(label, source_type='config_label'):
    from .models import db, Tenant
    from .tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    metadata = {'source_id': label.id}
    owner = db.session.get(Tenant, label.tenant_id) if label.tenant_id else None
    if owner is not None and owner.is_system_defaults:
        source = TenantDefaultSource.query.filter_by(source_type=source_type, source_id=label.id, active=True).first()
    else:
        replica = TenantDefaultReplica.query.filter_by(local_type=source_type, local_id=label.id).first()
        source = db.session.get(TenantDefaultSource, replica.source_id) if replica else None
    if source is not None and source.active:
        metadata['shared_source_id'] = source.id
    return metadata


def legacy_shared_record_target(record, source_type, tenant_id):
    from .workflow_catalog import _resolve_shared_dependency, _shared_reference
    _shared_reference(record)  # unknown external identities are also validated
    return _resolve_shared_dependency(record, tenant_id, source_type)


def legacy_shared_label_target(label, index, tenant_id):
    from .workflow_catalog import _resolve_shared_dependency
    definition = index['identities'][_identity(label)]
    return _resolve_shared_dependency(definition, tenant_id, 'config_label')


def legacy_label_target(label, index, tenant_id):
    from sqlalchemy import or_
    from .models import db, Tenant, ConfigLabel
    definition = index['identities'][_identity(label)]
    shared = legacy_shared_label_target(definition, index, tenant_id)
    if shared is not None:
        return shared
    tenant = db.session.get(Tenant, int(tenant_id))
    query = ConfigLabel.query.filter_by(kind=definition['kind'], value=definition['value'])
    if tenant is not None and tenant.name == 'default' and not tenant.is_system_defaults:
        query = query.filter(or_(ConfigLabel.tenant_id == tenant.id, ConfigLabel.tenant_id.is_(None)))
    else:
        query = query.filter_by(tenant_id=int(tenant_id))
    return query.first()
