"""Anonymous bootstrap snapshots containing both operational and shared defaults.

Only reusable configuration and its provenance are retained. Operational rows,
personal notifications and credentials are never copied. Binary form templates
remain the reusable template assets; operational uploaded documents are excluded.
"""
import hashlib
import json

from .models import (
    db, Tenant, Setting, ConfigLabel, NotificationType, Recommendation,
    NotificationTemplate, IncidentTemplate, ExternalRecipient, BackupJob,
    IncidentWorkflowStep, FormTemplateConfig, FormTemplateBinary, FormFieldMapping,
    TenantDefaultSource, TenantDefaultReplica, WorkflowCatalogEntry,
)
from .tenant_defaults import _FIELDS, _MODELS
from .tenant_defaults_bundle import _SECRET_NAME


_CONFIG_TABLES = {
    'config_labels': ConfigLabel, 'notification_types': NotificationType,
    'recommendations': Recommendation, 'notification_templates': NotificationTemplate,
    'incident_templates': IncidentTemplate, 'external_recipients': ExternalRecipient,
    'backup_jobs': BackupJob, 'incident_workflow_steps': IncidentWorkflowStep,
}
_TECHNICAL = {
    'id', 'key', 'ref', 'code', 'kind', 'source_type', 'local_type', 'scope_key', 'source_scope_key',
    'public_id', 'shared_source_id', 'import_origin', 'import_key', 'source_id',
    'template_name', 'filename', 'document_template_name', 'linked_form_template_name',
    'generated_template_name', 'sso_logo_path', 'pdf_data', 'pdf_base64', 'content_base64', 'sha256',
    'payload_hash', 'step_ids_json', 'conditions', 'condition_tokens', 'notification_tags',
    'required_notification_type', 'auth_provider', 'step_type', 'section_target',
    'recipient_source', 'cc_source', 'automatic_operations', 'status',
    'created_at', 'updated_at', 'obsolete_at', 'last_run_at', 'read_at', 'acknowledged_at',
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sanitize_bootstrap_setting_value(key, value):
    """Return portable, credential-free settings, including nested JSON."""
    from .routes import (decrypt_setting_value, _sanitize_bootstrap_sso_profiles,
                         BOOTSTRAP_RESET_SETTING_KEYS, BOOTSTRAP_SECRET_SETTING_KEYS)
    if key in BOOTSTRAP_SECRET_SETTING_KEYS or (key != 'sso_profiles_json' and _SECRET_NAME.search(key)):
        return ''
    if key in BOOTSTRAP_RESET_SETTING_KEYS or key in {'ssl_cert_path', 'ssl_key_path'}:
        return ''
    plain = decrypt_setting_value(key, value or '')
    if (value or '').startswith('enc:v1:') and (not plain or plain.startswith('enc:v1:')):
        raise ValueError('Parametro bootstrap non decifrabile: ' + key)
    if key == 'sso_profiles_json':
        plain = _sanitize_bootstrap_sso_profiles(plain)
    elif key == 'sso_enabled':
        return '0'
    elif key == 'application_external_url':
        return 'http://localhost:8000'
    elif key == 'ssl_enabled':
        return '0'
    try:
        structured = json.loads(plain)
    except (ValueError, TypeError):
        return plain

    def remove_secrets(item, field=''):
        if field != 'sso_profiles_json' and _SECRET_NAME.search(field):
            return ''
        if isinstance(item, dict):
            return {child_key: remove_secrets(child, child_key) for child_key, child in item.items()}
        if isinstance(item, list):
            return [remove_secrets(child) for child in item]
        return item

    return _canonical(remove_secrets(structured)) if isinstance(structured, (dict, list)) else plain


def _redact(value, redactions, field=''):
    from .routes import _redact_bootstrap_value
    if field in _TECHNICAL or field.endswith(('_id', '_ids', '_ref')):
        return value
    if field in {'recipient_value', 'cc_value', 's3_access_key', 's3_secret_key'} or _SECRET_NAME.search(field):
        return ''
    if isinstance(value, dict):
        is_document = 'pdf_base64' in value or 'pdf_data' in value
        return {key: (child if is_document and key == 'name' else _redact(child, redactions, key))
                for key, child in value.items()}
    if isinstance(value, list):
        return [_redact(child, redactions, field) for child in value]
    return _redact_bootstrap_value(value, redactions)


def _configuration_row(kind, row, redactions):
    result = _redact(dict(row), redactions)
    if kind == 'external_recipient':
        result['name'] = 'Destinatario bootstrap ' + str(row['id'])
        result['email'] = 'recipient-' + str(row['id']) + '@example.local'
        result['notes'] = ''
    elif kind == 'incident_template':
        result.update(people_ids='', incident_name='', reference=None, recipient=None,
                      recipient_email=None, incident_description='', data_subjects_count=None,
                      data_volume=None, status='aperto')
    elif kind == 'backup_job':
        result.update(enabled=False, s3_access_key='', s3_secret_key='', last_run_at=None,
                      last_status='never', last_message='', local_path='/data/backups')
    # Redaction may collapse several labels/names to one placeholder. Preserve
    # identities and uniqueness with the original numeric ID, never by merging.
    name = {'config_label': 'value', 'notification_template': 'name',
            'incident_template': 'name', 'backup_job': 'name', 'recommendation': 'text'}.get(kind)
    if name and result.get(name) != row.get(name):
        limit = 255 if kind == 'config_label' else (20000 if kind == 'recommendation' else 160)
        suffix = f' [{row["id"]}]'
        result[name] = str(result.get(name) or 'Bootstrap')[:limit - len(suffix)] + suffix
    return result


def _known_secret_values(tenant_ids):
    """Remove credentials also when copied into free-text configuration fields."""
    from .routes import decrypt_setting_value, decrypt_backup_secret
    values = set()

    def inspect(value, field=''):
        if _SECRET_NAME.search(field) and isinstance(value, str) and len(value.strip()) >= 3:
            values.add(value.strip())
        if isinstance(value, dict):
            for key, child in value.items():
                inspect(child, key)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    prefixes = tuple(f'tenant:{tid}:' for tid in tenant_ids)
    for setting in Setting.query.all():
        if setting.key.startswith('tenant:') and not setting.key.startswith(prefixes):
            continue
        if setting.key.startswith(('__', 'scheduler_')):
            continue
        logical = setting.key.split(':', 2)[2] if setting.key.startswith(prefixes) else setting.key
        plain = decrypt_setting_value(logical, setting.value or '')
        inspect(plain, logical)
        try:
            structured = json.loads(plain)
        except (TypeError, ValueError):
            continue
        inspect(structured)
    for job in BackupJob.query.filter(BackupJob.tenant_id.in_(tenant_ids)):
        for value in (job.s3_access_key, decrypt_backup_secret(job.s3_secret_key)):
            if isinstance(value, str) and len(value.strip()) >= 3:
                values.add(value.strip())
    return values


def _required_extended_configuration_ids(tables):
    """Keep additional ordinary-tenant definitions only when settings need them."""
    fields = {'external_recipient_id': 'external_recipients',
              'incident_template_id': 'incident_templates', 'backup_job_id': 'backup_jobs'}
    result = {name: set() for name in fields.values()}

    def visit(value, field=''):
        table = fields.get(field)
        if table and type(value) in (int, str) and str(value).isdigit():
            result[table].add(int(value))
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, key)
        elif isinstance(value, list):
            for child in value:
                visit(child, field)

    for row in tables.get('settings', []):
        try:
            value = json.loads(row['value'])
        except (TypeError, ValueError):
            value = row['value']
        visit(value, row['key'].split(':', 2)[-1])
    return result


def bootstrap_configuration_snapshot(default_tenant_id):
    """Return sanitized tables, required document names, and included tenant IDs."""
    from .routes import (_row, _bootstrap_export_tables, _bootstrap_setting_rows,
                         _bootstrap_referenced_form_templates, _bootstrap_redaction_values,
                         FULL_EXPORT_TABLES)
    from .tenant_defaults import ensure_defaults_tenant
    defaults = ensure_defaults_tenant(seed_from_default=True)
    tenant_ids = (int(default_tenant_id), defaults.id)
    template_names = set()
    redactions = set()
    for tenant_id in tenant_ids:
        template_names.update(_bootstrap_referenced_form_templates(tenant_id))
        redactions.update(_bootstrap_redaction_values(tenant_id))
    redactions.update(_known_secret_values(tenant_ids))
    # Source-owned documents are configuration even before a draft uses them.
    template_names.update(row.template_name for row in FormTemplateConfig.query.filter_by(owner_tenant_id=defaults.id))
    redactions = sorted(redactions, key=len, reverse=True)
    # Documents are assembled below with their true owner. The old one-tenant
    # helper rebinds them to the operational tenant and is intentionally given
    # no documents here, so it cannot remap the source's tags twice.
    tables = _bootstrap_export_tables(default_tenant_id, set())
    source_tenant = _row(defaults)
    source_tenant.update(name='Tenants Default', description='')
    tables['tenants'].append(source_tenant)
    required_extended = _required_extended_configuration_ids(tables)
    for name, model in _CONFIG_TABLES.items():
        # Reusable definitions may be referenced by settings/workflows through
        # numeric IDs. Retain the records and sanitize their private fields;
        # deleting only the ordinary tenant's copies would break those links.
        tables[name] = [_row(row) for row in model.query.filter(model.tenant_id.in_(tenant_ids)).order_by(model.id)
                        if name not in required_extended or row.tenant_id == defaults.id
                        or row.id in required_extended[name]]
    source_settings = _bootstrap_setting_rows(defaults.id, include_unscoped=False)
    tables['settings'].extend(source_settings)
    for name, model in (('form_template_configs', FormTemplateConfig), ('form_template_binaries', FormTemplateBinary),
                        ('form_field_mappings', FormFieldMapping)):
        # Preserve the true owner now that both tenants exist in the archive.
        tables[name] = [_row(row) for row in model.query.filter(model.template_name.in_(template_names or ['__none__'])).order_by(model.id)]
        if name == 'form_template_configs' and any(row.get('owner_tenant_id') not in (None, *tenant_ids) for row in tables[name]):
            raise ValueError('Documento bootstrap appartenente a un tenant privato escluso.')
    tables['workflow_catalog_entries'] = [_row(row) for row in WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=defaults.id).order_by(WorkflowCatalogEntry.id)]
    for name in ('tenant_workflows', 'workflow_catalog_installations'):
        model = FULL_EXPORT_TABLES.get(name)
        if model is not None:
            tables[name] = [_row(row) for row in model.query.filter(model.tenant_id.in_(tenant_ids)).order_by(model.id)]
    tables['workflow_obsolescence_notices'] = []
    tables['tenant_default_alerts'] = []
    tables['tenant_default_sources'] = [_row(row) for row in TenantDefaultSource.query.order_by(TenantDefaultSource.id)]
    tables['tenant_default_replicas'] = [_row(row) for row in TenantDefaultReplica.query.filter_by(tenant_id=int(default_tenant_id)).order_by(TenantDefaultReplica.id)]

    config_by_kind = {}
    for kind, model in _MODELS.items():
        name = next(key for key, candidate in _CONFIG_TABLES.items() if candidate is model)
        tables[name] = [_configuration_row(kind, row, redactions) for row in tables[name]]
        config_by_kind[kind] = {row['id']: row for row in tables[name]}
    for name in ('tenants', 'users', 'user_tenant_roles', 'incident_workflow_steps', 'tenant_workflows', 'workflow_catalog_installations'):
        tables[name] = [_redact(row, redactions) for row in tables.get(name, [])]
    for row in tables['settings']:
        # These values are already decrypted/sanitized. Recursively redact
        # personal text without corrupting embedded JSON syntax or typed IDs.
        try:
            structured = json.loads(row['value'])
        except (ValueError, TypeError):
            row['value'] = _redact(row['value'], redactions)
        else:
            row['value'] = _canonical(_redact(structured, redactions)) if isinstance(structured, (dict, list)) else _redact(row['value'], redactions)
    for source in tables['tenant_default_sources']:
        kind = source['source_type']
        current = config_by_kind[kind].get(source.get('source_id')) if source['active'] else None
        if current is not None:
            snapshot = {field: current[field] for field in _FIELDS[kind]}
        else:
            old = json.loads(source['snapshot_json'])
            old['id'] = source.get('source_id') or source['id'][:8]
            sanitized = _configuration_row(kind, old, redactions)
            snapshot = {field: sanitized[field] for field in _FIELDS[kind]}
        source['snapshot_json'] = _canonical(snapshot)
        if source.get('import_snapshot_json') is not None:
            source['import_snapshot_json'] = _canonical(snapshot)
    valid_sources = {row['id'] for row in tables['tenant_default_sources']}
    replicas = []
    for replica in tables['tenant_default_replicas']:
        current = config_by_kind[replica['local_type']].get(replica['local_id'])
        if current is not None and replica['source_id'] in valid_sources:
            replica['snapshot_json'] = _canonical({field: current[field] for field in _FIELDS[replica['local_type']]})
            replicas.append(replica)
    tables['tenant_default_replicas'] = replicas
    from .workflow_catalog import validate_catalog_payload
    for entry in tables['workflow_catalog_entries']:
        entry['name'] = _redact(entry['name'], redactions)
        entry['description'] = _redact(entry['description'], redactions)
        original = json.loads(entry['payload_json'])
        content = _redact(original, redactions)
        for index, (old, new) in enumerate(zip(original['dependencies'].get('notification_templates', []),
                                              content['dependencies'].get('notification_templates', [])), 1):
            if old['name'] != new['name']:
                suffix = f' [bootstrap {index}]'
                new['name'] = new['name'][:160 - len(suffix)] + suffix
        content = validate_catalog_payload(content)
        entry['payload_json'] = _canonical(content)
        entry['payload_hash'] = hashlib.sha256(entry['payload_json'].encode('utf-8')).hexdigest()
    entries = {row['id']: row for row in tables['workflow_catalog_entries']}
    for installation in tables.get('workflow_catalog_installations', []):
        entry = entries.get(installation['entry_id'])
        if entry and installation['entry_version'] == entry['version']:
            installation['payload_hash'] = entry['payload_hash']
    # The canonical bootstrap identity is intentionally non-personal.
    for admin in tables.get('users', []):
        admin.update(username='admin', name='Administrator', email='admin@example.local', password_hash=None)
    return tables, template_names, tenant_ids
