"""Validate shared configuration provenance before a Full Import mutates data.

This module performs no queries or writes.  Archive IDs are checked against the
archive itself, so neither existing destination IDs nor forged ownership can
turn a tenant-local row into a shared source.  Old exports without the feature
remain importable and obtain the special tenant during normal bootstrap.
"""
import hashlib
import json
import re
import uuid


_NEW_TABLES = (
    'tenant_default_sources', 'tenant_default_replicas', 'tenant_default_alerts',
    'workflow_catalog_entries', 'workflow_catalog_installations',
    'tenant_workflows', 'workflow_obsolescence_notices',
)
_CONFIG_TABLES = {
    'config_label': 'config_labels',
    'notification_type': 'notification_types',
    'recommendation': 'recommendations',
    'notification_template': 'notification_templates',
    'external_recipient': 'external_recipients',
    'incident_template': 'incident_templates',
    'backup_job': 'backup_jobs',
}
_DIGEST = re.compile(r'^[0-9a-f]{64}$')


def _fail(message):
    raise ValueError('Archivio Tenants Default non valido: ' + message)


def _rows(tables, name):
    rows = tables.get(name, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        _fail(f'{name}: elenco di record richiesto.')
    return rows


def _integer(value, field):
    if type(value) is not int or value <= 0:
        _fail(f'{field}: ID/intero positivo richiesto.')
    return value


def _uuid(value, field):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        _fail(f'{field}: UUID non valido.')
    return value


def _text(value, field, maximum, *, required=False):
    if not isinstance(value, str) or '\x00' in value or len(value) > maximum:
        _fail(f'{field}: testo non valido.')
    if required and not value.strip():
        _fail(f'{field}: testo obbligatorio.')
    return value


def _boolean(value, field):
    if type(value) is not bool:
        _fail(f'{field}: booleano richiesto.')
    return value


def _json(value, field, expected_type):
    if not isinstance(value, str):
        _fail(f'{field}: stringa JSON richiesta.')
    try:
        result = json.loads(value)
    except (ValueError, TypeError, RecursionError):
        _fail(f'{field}: JSON non valido.')
    if not isinstance(result, expected_type):
        _fail(f'{field}: struttura JSON non valida.')
    return result


def _index(tables, name, *, uuid_key=False):
    result = {}
    for row in _rows(tables, name):
        key = (_uuid if uuid_key else _integer)(row.get('id'), name + '.id')
        if key in result:
            _fail(f'{name}: ID duplicato.')
        result[key] = row
    return result


def _unique(seen, key, field):
    if key in seen:
        _fail(f'{field}: relazione duplicata.')
    seen.add(key)


def _validate_workflow_rows(tables, tenants, entries, defaults_id=None, *, tenant_scoped=False):
    workflows = _index(tables, 'tenant_workflows')
    labels = _index(tables, 'config_labels')
    scopes, public_ids = set(), set()
    for workflow in workflows.values():
        tenant_id = _integer(workflow.get('tenant_id'), 'workflow.tenant_id')
        if tenant_id not in tenants:
            _fail('workflow con tenant inesistente.')
        _unique(public_ids, _uuid(workflow.get('public_id'), 'workflow.public_id'), 'workflow.public_id')
        category_id = workflow.get('category_id')
        if category_id is not None:
            category_id = _integer(category_id, 'workflow.category_id')
            category = labels.get(category_id)
            legacy_default = (category is not None and category.get('tenant_id') is None
                              and tenants[tenant_id].get('name') == 'default'
                              and not tenants[tenant_id].get('is_system_defaults'))
            if category is None or (category.get('tenant_id') != tenant_id and not legacy_default) or category.get('kind') != 'category':
                _fail('workflow con categoria appartenente a un altro tenant o tipo.')
        expected_scope = 'default' if category_id is None else f'category:{category_id}'
        if workflow.get('scope_key') != expected_scope:
            _fail('scope locale del workflow non coerente con la categoria.')
        _unique(scopes, (tenant_id, expected_scope), 'workflow.scope')
        _text(workflow.get('name', ''), 'workflow.name', 160)
        _boolean(workflow.get('personalized', False), 'workflow.personalized')
        status = workflow.get('status', 'current')
        if status not in ('current', 'obsolete'):
            _fail('stato locale del workflow non valido.')
        portable_origin = workflow.get('source_entry_public_id')
        if portable_origin is not None:
            _uuid(portable_origin, 'workflow.source_entry_public_id')
        source_id = workflow.get('source_entry_id')
        if tenant_scoped and source_id is not None:
            _fail('un export tenant non può usare ID numerici di catalogo esterni al suo ambito.')
        if source_id is not None:
            source = entries.get(_integer(source_id, 'workflow.source_entry_id'))
            if source is None or tenant_id == defaults_id:
                _fail('origine di catalogo della copia non valida.')
            if source.get('status', 'current') == 'obsolete' and status != 'obsolete':
                _fail('copia corrente proveniente da un catalogo obsoleto.')
    return workflows


def validate_defaults_archive_tables(tables):
    """Check all new ownership/identity invariants, with legacy compatibility."""
    if not isinstance(tables, dict):
        _fail('oggetto tables richiesto.')
    tenant_rows = _rows(tables, 'tenants')
    for row in tenant_rows:
        if 'is_system_defaults' in row:
            _boolean(row['is_system_defaults'], 'tenant.is_system_defaults')
    special_rows = [row for row in tenant_rows if row.get('is_system_defaults') is True]
    known_tenant_ids = {row.get('id') for row in tenant_rows if type(row.get('id')) is int}
    for form in _rows(tables, 'form_template_configs'):
        owner = form.get('owner_tenant_id')
        if owner is not None and _integer(owner, 'form_template.owner_tenant_id') not in known_tenant_ids:
            _fail('modello documento con tenant proprietario inesistente.')
    if len(special_rows) > 1:
        _fail('è ammesso un solo tenant di configurazione condivisa.')
    has_metadata = any(_rows(tables, key) for key in _NEW_TABLES)
    if not special_rows and not has_metadata:
        return True
    if not special_rows:
        if any(_rows(tables, key) for key in _NEW_TABLES if key != 'tenant_workflows'):
            _fail('metadati condivisi senza Tenants Default.')
        # A tenant-scoped restore carries local lifecycle and portable public
        # origin only. It never imports global catalog/source identities.
        _validate_workflow_rows(tables, _index(tables, 'tenants'), {}, tenant_scoped=True)
        return True
    tenants = _index(tables, 'tenants')
    defaults_id = _integer(special_rows[0].get('id'), 'Tenants Default.id')
    special_name = _text(special_rows[0].get('name'), 'Tenants Default.name', 80, required=True)
    if special_name.strip().lower() == 'default':
        _fail('il tenant operativo default non può essere Tenants Default.')
    operational_ids = set(tenants) - {defaults_id}
    for name in ('incidents', 'user_tenant_roles'):
        if any(row.get('tenant_id') == defaults_id for row in _rows(tables, name)):
            _fail(f'{name}: il tenant condiviso non può contenere dati operativi o membership.')
    for user in _rows(tables, 'users'):
        if user.get('tenant_id') == defaults_id or user.get('default_tenant_id') == defaults_id:
            _fail('Tenants Default non può essere il tenant personale di un utente.')

    config = {kind: _index(tables, table) for kind, table in _CONFIG_TABLES.items()}
    sources = _index(tables, 'tenant_default_sources', uuid_key=True)
    # Imported lazily: legacy archives need no new configuration/catalog logic.
    from .tenant_defaults import _validate_data

    source_records, origins = set(), set()
    for source in sources.values():
        kind = source.get('source_type')
        if not isinstance(kind, str) or kind not in config:
            _fail('tipo sorgente non consentito.')
        active = _boolean(source.get('active'), 'source.active')
        _validate_data(kind, _json(source.get('snapshot_json'), 'source.snapshot_json', dict))
        if active:
            record_id = _integer(source.get('source_id'), 'source.source_id')
            record = config[kind].get(record_id)
            if record is None or record.get('tenant_id') != defaults_id:
                _fail('sorgente attiva non appartenente al tenant condiviso.')
            _unique(source_records, (kind, record_id), 'source.record')
        elif source.get('source_id') is not None:
            _fail('sorgente ritirata con riferimento operativo ancora attivo.')
        origin, key = source.get('import_origin'), source.get('import_key')
        if (origin is None) != (key is None):
            _fail('origine import parziale.')
        if origin is not None:
            _unique(origins, (_uuid(origin, 'source.import_origin'),
                             _uuid(key, 'source.import_key')), 'source.import_identity')
        if source.get('import_snapshot_json') is not None:
            _validate_data(kind, _json(source['import_snapshot_json'], 'source.import_snapshot_json', dict))

    replica_pairs, local_records = set(), set()
    for replica in _index(tables, 'tenant_default_replicas').values():
        source = sources.get(_uuid(replica.get('source_id'), 'replica.source_id'))
        tenant_id = _integer(replica.get('tenant_id'), 'replica.tenant_id')
        local_type = replica.get('local_type')
        local_id = _integer(replica.get('local_id'), 'replica.local_id')
        if source is None or not source['active'] or local_type != source['source_type']:
            _fail('replica senza sorgente attiva corrispondente.')
        local = config[local_type].get(local_id)
        if tenant_id not in operational_ids or local is None or local.get('tenant_id') != tenant_id:
            _fail('replica riferita a un tenant/record locale diverso.')
        _validate_data(local_type, _json(replica.get('snapshot_json'), 'replica.snapshot_json', dict))
        _unique(replica_pairs, (source['id'], tenant_id), 'replica.source_tenant')
        _unique(local_records, (local_type, local_id), 'replica.local_record')

    alert_keys = set()
    for alert in _index(tables, 'tenant_default_alerts').values():
        source = sources.get(_uuid(alert.get('source_id'), 'alert.source_id'))
        tenant_id = _integer(alert.get('tenant_id'), 'alert.tenant_id')
        local_type = alert.get('local_type')
        local_id = _integer(alert.get('local_id'), 'alert.local_id')
        if source is None or local_type != source['source_type'] or tenant_id not in operational_ids:
            _fail('avviso con proprietario o provenienza non validi.')
        local = config[local_type].get(local_id)
        # Retained alerts are audit records: a later deliberate local deletion
        # may leave no row, but an existing row cannot belong to another tenant.
        if local is not None and local.get('tenant_id') != tenant_id:
            _fail('avviso riferito a un record di un altro tenant.')
        kind = _text(alert.get('kind'), 'alert.kind', 40, required=True)
        _text(alert.get('message'), 'alert.message', 100000, required=True)
        _unique(alert_keys, (tenant_id, source['id'], kind, local_id), 'alert.event')

    entries = _index(tables, 'workflow_catalog_entries')
    public_ids = set()
    if entries:
        from .workflow_catalog import validate_catalog_payload
    for entry in entries.values():
        if _integer(entry.get('defaults_tenant_id'), 'catalog.defaults_tenant_id') != defaults_id:
            _fail('workflow di catalogo non appartenente a Tenants Default.')
        _unique(public_ids, _uuid(entry.get('public_id'), 'catalog.public_id'), 'catalog.public_id')
        _integer(entry.get('version'), 'catalog.version')
        _boolean(entry.get('active'), 'catalog.active')
        if entry.get('status', 'current') not in ('current', 'obsolete'):
            _fail('stato del catalogo non valido.')
        scope = entry.get('source_scope_key')
        if scope is not None and (not isinstance(scope, str) or not re.fullmatch(r'default|category:[1-9][0-9]*', scope)):
            _fail('scope sorgente del catalogo non valido.')
        _text(entry.get('name'), 'catalog.name', 160, required=True)
        _text(entry.get('description', ''), 'catalog.description', 100000)
        payload = validate_catalog_payload(_json(entry.get('payload_json'), 'catalog.payload_json', dict))
        for dependency_kind, source_type in (('labels', 'config_label'), ('notification_types', 'notification_type'),
                                             ('notification_templates', 'notification_template')):
            for item in payload['dependencies'][dependency_kind]:
                source = sources.get(item.get('shared_source_id'))
                if source is not None:
                    if source['source_type'] != source_type:
                        _fail('dipendenza di catalogo con provenienza di un altro tipo.')
                    if source_type == 'config_label' and _json(source['snapshot_json'], 'source.snapshot_json', dict).get('kind') != item['kind']:
                        _fail('dipendenza di catalogo con tipo label diverso dalla sorgente.')
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        if entry.get('payload_hash') != digest:
            _fail('impronta del workflow di catalogo non corrispondente.')
    entries_by_public_id = {entry['public_id']: entry for entry in entries.values()}
    for entry in entries.values():
        payload = _json(entry['payload_json'], 'catalog.payload_json', dict)
        parent_id = payload.get('workflow', {}).get('catalog_source_public_id')
        parent = entries_by_public_id.get(parent_id)
        if (parent is not None and parent['id'] != entry['id']
                and parent.get('status', 'current') == 'obsolete'
                and entry.get('status', 'current') != 'obsolete'):
            _fail('catalogo derivato corrente con sorgente obsoleta.')

    steps = _index(tables, 'incident_workflow_steps')
    workflows = _validate_workflow_rows(tables, tenants, entries, defaults_id)
    for installation in _index(tables, 'workflow_catalog_installations').values():
        tenant_id = _integer(installation.get('tenant_id'), 'installation.tenant_id')
        entry = entries.get(_integer(installation.get('entry_id'), 'installation.entry_id'))
        version = _integer(installation.get('entry_version'), 'installation.entry_version')
        digest = installation.get('payload_hash')
        if entry is None or tenant_id not in operational_ids or version > entry['version']:
            _fail('ricevuta installazione con tenant, versione o catalogo non validi.')
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            _fail('impronta installazione non valida.')
        if version == entry['version'] and digest != entry['payload_hash']:
            _fail('impronta della versione installata non corrispondente.')
        # Several copies of the same catalogue revision are intentionally
        # permitted in one tenant; each receipt has its own ID and copy name.
        _text(installation.get('copy_name', ''), 'installation.copy_name', 160)
        workflow_id = installation.get('workflow_id')
        if workflow_id is not None:
            local = workflows.get(_integer(workflow_id, 'installation.workflow_id'))
            if local is not None and (local['tenant_id'] != tenant_id or local.get('source_entry_id') != entry['id']):
                _fail('ricevuta installazione collegata al workflow di un altro tenant o catalogo.')
        category_id = installation.get('category_id')
        if category_id is not None:
            category = config['config_label'].get(_integer(category_id, 'installation.category_id'))
            if category is not None and (category.get('tenant_id') != tenant_id or category.get('kind') != 'category'):
                _fail('categoria installata appartenente a un altro tenant o tipo.')
        step_ids = _json(installation.get('step_ids_json'), 'installation.step_ids_json', list)
        seen_steps = set()
        for step_id in step_ids:
            _integer(step_id, 'installation.step_id')
            _unique(seen_steps, step_id, 'installation.step_id')
            step = steps.get(step_id)
            if step is not None and step.get('tenant_id') != tenant_id:
                _fail('step installato appartenente a un altro tenant.')
    users = _index(tables, 'users')
    notice_recipients = set()
    for notice in _index(tables, 'workflow_obsolescence_notices').values():
        user_id = _integer(notice.get('user_id'), 'notice.user_id')
        entry_id = _integer(notice.get('entry_id'), 'notice.entry_id')
        event_id = _uuid(notice.get('event_id'), 'notice.event_id')
        if user_id not in users or entry_id not in entries:
            _fail('avviso workflow con utente o catalogo inesistente.')
        _unique(notice_recipients, (event_id, user_id), 'notice.recipient')
        _text(notice.get('message'), 'notice.message', 100000, required=True)
    return True
