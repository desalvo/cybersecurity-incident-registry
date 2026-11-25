"""Transactional propagation of the configuration owned by Tenants Default.

All public mutators leave commit/rollback to the caller. The optional session
listeners reconcile before the outer commit, including changes already flushed
by existing admin routes. Set session.info['cir_defaults_suspended'] while
replacing the schema or importing a complete backup; synchronize after restore.
"""
import json
import re
import uuid

from sqlalchemy import event, select, inspect
from sqlalchemy.orm import Session

from .models import (
    db, Tenant, Setting, ConfigLabel, NotificationType, Recommendation,
    Incident, IncidentTemplate, IncidentWorkflowStep, NotificationTemplate,
    Document, DeadlineNotificationState, FormTemplateConfig, FormTemplateBinary,
    ExternalRecipient, BackupJob,
)
from .tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica, TenantDefaultAlert


DEFAULTS_TENANT_NAME = 'Tenants Default'
CONFIGURATION_FORMAT = 'cybersecurity-incident-registry.tenant-configuration.v1'
MAX_CONFIGURATION_ITEMS = 2000
MAX_CONFIGURATION_BYTES = 4 * 1024 * 1024
_ORIGIN_SETTING = '__cir_tenant_configuration_origin'
# Provenance marker for a category or affected-data label already owned by the receiving tenant.
# Keep the original key for backwards compatibility with existing snapshots.
# It is stored in the existing replica snapshot; no schema/DDL change required.
_LOCAL_CATEGORY_MARKER = '__cir_existing_tenant_category'


def _locally_owned_category_replica(replica):
    if not replica or replica.local_type != 'config_label':
        return False
    try:
        return json.loads(replica.snapshot_json).get(_LOCAL_CATEGORY_MARKER) is True
    except (ValueError, TypeError, AttributeError):
        return False


def _category_equivalent(left, right):
    return ' '.join((left or '').strip().casefold().split()) == ' '.join((right or '').strip().casefold().split())

_MODELS = {
    'config_label': ConfigLabel, 'notification_type': NotificationType,
    'recommendation': Recommendation, 'external_recipient': ExternalRecipient,
    'notification_template': NotificationTemplate, 'incident_template': IncidentTemplate,
    'backup_job': BackupJob,
}
_BASIC_TYPES = {'config_label', 'notification_type', 'recommendation'}
_FIELDS = {
    'config_label': ('kind', 'group', 'value', 'description', 'max_completion_hours',
                     'default_exportable', 'description_required', 'automatic_operations'),
    'notification_type': ('code', 'label', 'description', 'enabled'),
    'recommendation': ('text',),
    'external_recipient': ('name', 'email', 'notes'),
    'notification_template': ('kind', 'name', 'subject', 'body', 'linked_form_template_name',
                              'action_label_id', 'recipient_source', 'recipient_value',
                              'recipient_editable', 'recipient_external_allowed', 'cc_source',
                              'cc_value', 'cc_editable', 'cc_external_allowed', 'is_default'),
    'incident_template': ('name', 'description', 'incident_name', 'reference', 'recipient',
                          'recipient_email', 'incident_description', 'severity_id', 'personal_data',
                          'data_subjects_count', 'data_volume', 'status', 'category_ids',
                          'data_type_ids', 'people_ids', 'recommendation_ids'),
    'backup_job': ('name', 'enabled', 'cron_expression', 'categories', 'destination', 'local_path',
                   's3_endpoint_url', 's3_bucket', 's3_prefix', 's3_access_key', 's3_secret_key', 'notify_admin'),
}
_DEFAULTS = {
    'config_label': {'group': 'default', 'description': '', 'max_completion_hours': 0,
                     'default_exportable': True, 'description_required': False, 'automatic_operations': ''},
    'notification_type': {'description': '', 'enabled': True},
    'recommendation': {},
    'external_recipient': {'name': '', 'notes': ''},
    'notification_template': {'subject': '', 'body': '', 'linked_form_template_name': None,
                              'action_label_id': None, 'recipient_source': 'empty', 'recipient_value': '',
                              'recipient_editable': True, 'recipient_external_allowed': True,
                              'cc_source': 'empty', 'cc_value': '', 'cc_editable': True,
                              'cc_external_allowed': True, 'is_default': False},
    'incident_template': {'description': '', 'incident_name': '', 'reference': None,
                          'recipient': None, 'recipient_email': None, 'incident_description': '',
                          'severity_id': None, 'personal_data': False, 'data_subjects_count': None,
                          'data_volume': None, 'status': 'aperto', 'category_ids': '',
                          'data_type_ids': '', 'people_ids': '', 'recommendation_ids': ''},
    'backup_job': {'enabled': False, 'cron_expression': '0 2 * * *',
                   'categories': 'incidents,database,templates,logos,uploads',
                   'destination': 'local', 'local_path': '/data/backups', 's3_endpoint_url': '',
                   's3_bucket': '', 's3_prefix': 'cybersecurity-incident-registry',
                   's3_access_key': '', 's3_secret_key': '', 'notify_admin': False},
}
_ID_FIELDS = {'notification_template': {'action_label_id': 'config_label'},
              'incident_template': {'severity_id': 'config_label'}}
_CSV_FIELDS = {'incident_template': {'category_ids': 'config_label', 'data_type_ids': 'config_label',
                                    'recommendation_ids': 'recommendation'}}
_BOOLEAN_FIELDS = {'default_exportable', 'description_required', 'enabled', 'recipient_editable',
                   'recipient_external_allowed', 'cc_editable', 'cc_external_allowed', 'is_default',
                   'personal_data', 'notify_admin'}
_NULLABLE_TEXT_FIELDS = {'linked_form_template_name', 'reference', 'recipient', 'recipient_email',
                        'data_subjects_count', 'data_volume'}


def _session(session=None):
    return session if session is not None else db.session()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def configuration_record_payload(kind, row):
    """Configuration fields only; runtime scheduling and incident state excluded.

Backup credentials remain encrypted in internal synchronization snapshots.
Portable exports redact or decrypt them according to the caller's explicit mode.
"""
    return {name: getattr(row, name) for name in _FIELDS[kind]}


def ensure_defaults_tenant(session=None, *, seed_from_default=False):
    session = _session(session)
    existing = session.scalars(select(Tenant).where(Tenant.is_system_defaults.is_(True))).all()
    if len(existing) > 1:
        raise ValueError('Esiste più di un tenant Tenants Default: ripristinare il vincolo di unicità.')
    if existing:
        return existing[0]
    # Never convert a possibly private pre-existing tenant by matching its name.
    conflict = session.scalar(select(Tenant).where(Tenant.name == DEFAULTS_TENANT_NAME))
    if conflict:
        raise ValueError('Il nome Tenants Default è già usato da un tenant ordinario. Rinominarlo prima di creare il catalogo condiviso.')
    tenant = Tenant(name=DEFAULTS_TENANT_NAME, description='Configurazioni e catalogo condivisi per tutti i tenant', is_system_defaults=True)
    session.add(tenant)
    session.flush()
    if seed_from_default:
        from .tenant_defaults_seed import seed_new_defaults_tenant
        seed_new_defaults_tenant(tenant, session=session)
    return tenant


def _lock_defaults(session):
    # PostgreSQL serializes publishing and new-tenant provisioning on one row.
    # SQLite serializes the enclosing write transaction itself.
    locked_id = session.info.get('cir_defaults_locked_id')
    if locked_id:
        return session.get(Tenant, locked_id)
    rows = session.scalars(select(Tenant).where(Tenant.is_system_defaults.is_(True)).with_for_update()).all()
    if len(rows) > 1:
        raise ValueError('Configurazione Tenants Default ambigua.')
    if rows:
        session.info['cir_defaults_locked_id'] = rows[0].id
        return rows[0]
    return None


def _available_data(session, kind, data, tenant_id, *, excluding_id=None, suffix='Tenants Default'):
    """Resolve only the receiving unique key; IDs always come from the DB."""
    result = dict(data)
    model = _MODELS[kind]
    field = {'config_label': 'value', 'notification_type': 'code', 'recommendation': 'text'}.get(kind, 'name')
    limit = {'config_label': 255, 'notification_type': 40, 'recommendation': 20000,
             'external_recipient': 160}.get(kind, 160)
    original = str(data[field])
    query = select(model.id).where(model.tenant_id == tenant_id)
    if kind == 'config_label':
        query = query.where(model.kind == data['kind'])
    elif kind == 'notification_template':
        query = query.where(model.kind == data['kind'])
    elif kind == 'external_recipient':
        # Contact email is a delivery address, never a key to rewrite or an
        # excuse to overwrite a tenant's existing address-book entry.
        query = query.where(model.email == data['email'])
    if excluding_id is not None:
        query = query.where(model.id != excluding_id)
    candidate = original
    number = 0
    while session.scalar(query.where(getattr(model, field) == candidate)) is not None:
        number += 1
        ending = (f'_td{number if number > 1 else ""}' if kind == 'notification_type'
                  else f' [{suffix}{" " + str(number) if number > 1 else ""}]')
        candidate = original[:limit - len(ending)] + ending
    result[field] = candidate
    return result


def _referenced_local_id(session, kind, source_id, tenant_id, defaults_id, *, expected_kind=None):
    source_row = session.get(_MODELS[kind], int(source_id))
    if source_row is None or source_row.tenant_id != defaults_id:
        raise ValueError('Una configurazione condivisa fa riferimento a dati di un altro tenant o mancanti.')
    if expected_kind is not None and source_row.kind != expected_kind:
        raise ValueError('Una configurazione condivisa fa riferimento a una label di tipo errato.')
    source = session.scalar(select(TenantDefaultSource).where(
        TenantDefaultSource.source_type == kind, TenantDefaultSource.source_id == source_row.id,
        TenantDefaultSource.active.is_(True)))
    replica = session.scalar(select(TenantDefaultReplica).where(
        TenantDefaultReplica.source_id == source.id, TenantDefaultReplica.tenant_id == tenant_id)) if source else None
    if replica is None:
        raise ValueError('Dipendenza condivisa non ancora pubblicata nel tenant destinatario.')
    return replica.local_id


def _replica_data(session, kind, data, tenant_id, defaults_id):
    result = dict(data)
    for field, ref_type in _ID_FIELDS.get(kind, {}).items():
        if result.get(field) is not None:
            expected_kind = 'action_label' if field == 'action_label_id' else 'severity'
            result[field] = _referenced_local_id(session, ref_type, result[field], tenant_id, defaults_id,
                                                 expected_kind=expected_kind)
    for field, ref_type in _CSV_FIELDS.get(kind, {}).items():
        expected_kind = {'category_ids': 'category', 'data_type_ids': 'data_type'}.get(field)
        result[field] = ','.join(str(_referenced_local_id(session, ref_type, value, tenant_id, defaults_id,
                                                         expected_kind=expected_kind))
                                 for value in str(result.get(field) or '').split(',') if value.strip())
    if kind == 'notification_template':
        notification = session.scalar(select(NotificationType).where(
            NotificationType.tenant_id == defaults_id, NotificationType.code == data['kind']))
        if notification is None:
            raise ValueError('Il template condiviso richiede un tipo di notifica definito in Tenants Default.')
        local_id = _referenced_local_id(session, 'notification_type', notification.id, tenant_id, defaults_id)
        result['kind'] = session.get(NotificationType, local_id).code
        _require_form_template(session, data.get('linked_form_template_name'), defaults_id)
    if kind == 'incident_template' and result.get('people_ids'):
        raise ValueError('I modelli condivisi non possono referenziare personale privato: rimuovere le persone dal modello.')
    if kind == 'backup_job':
        from .routes import _tenant_backup_local_path
        result['local_path'] = _tenant_backup_local_path(tenant_id)
    return result


def _require_form_template(session, name, defaults_id):
    if not name:
        return
    binary = session.scalar(select(FormTemplateBinary).where(FormTemplateBinary.template_name == name))
    config = session.scalar(select(FormTemplateConfig).where(FormTemplateConfig.template_name == name))
    if binary is None or not binary.pdf_data or config is None:
        raise ValueError(f'Modulo documento mancante: {name}. Importare un pacchetto completo con i documenti necessari.')
    if config.owner_tenant_id not in (None, defaults_id):
        raise ValueError(f'Il modulo {name} appartiene a un tenant privato: importarne una copia in Tenants Default prima di condividerlo.')
    if config.owner_tenant_id is None and config.notification_tag_list:
        # A global legacy tag has no source tenant identity. Reusing its code
        # could bind a same-named private notification type in a destination.
        raise ValueError('Importare/copiare il documento nel tenant Tenants Default prima di pubblicarlo: i tag di un modulo legacy non hanno provenienza condivisa.')


def _write_row(row, data):
    for key, value in data.items():
        setattr(row, key, value)


def _json_contains_reference(value, identifier):
    if isinstance(value, dict):
        return any(_json_contains_reference(v, identifier) for v in value.values())
    if isinstance(value, list):
        return any(_json_contains_reference(v, identifier) for v in value)
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return str(value) == str(identifier)
    if isinstance(value, str):
        if value == str(identifier):
            return True
        return any(token.lstrip('!') in {f'severity:{identifier}', f'data_type:{identifier}'} for token in value.split(','))
    return False


def configuration_reference_reason(kind, row, session=None):
    """Conservative reference check, covering FK and embedded legacy values.

An operational dependency is also retained, even without an incident, because
deleting it would break the tenant's configured workflow or form template.
"""
    session = _session(session)
    from .configuration_usage import configuration_incident_usage
    incident_reason = configuration_incident_usage(kind, row, session)
    if incident_reason:
        return incident_reason
    table = row.__table__
    for candidate in db.metadata.sorted_tables:
        for foreign_key in candidate.foreign_keys:
            if foreign_key.column.table is table and foreign_key.column.name == 'id':
                if session.execute(select(foreign_key.parent).where(foreign_key.parent == row.id).limit(1)).first():
                    return 'utilizzato da incidenti o configurazioni operative'
    if kind == 'config_label':
        for template in session.scalars(select(IncidentTemplate).where(IncidentTemplate.tenant_id == row.tenant_id)):
            if row.id in template.category_id_list() or row.id in template.data_type_id_list():
                return 'utilizzato da un modello di incidente'
        for step in session.scalars(select(IncidentWorkflowStep).where(IncidentWorkflowStep.tenant_id == row.tenant_id)):
            if _json_contains_reference(step.conditions or '', row.id):
                return 'utilizzato nelle condizioni di un workflow'
    elif kind == 'recommendation':
        for template in session.scalars(select(IncidentTemplate).where(IncidentTemplate.tenant_id == row.tenant_id)):
            if row.id in template.recommendation_id_list():
                return 'utilizzato da un modello di incidente'
    elif kind == 'notification_type':
        if session.scalar(select(NotificationTemplate.id).where(NotificationTemplate.tenant_id == row.tenant_id, NotificationTemplate.kind == row.code).limit(1)):
            return 'utilizzato da un modello di notifica'
        if session.scalar(select(IncidentWorkflowStep.id).where(IncidentWorkflowStep.tenant_id == row.tenant_id, IncidentWorkflowStep.required_notification_type == row.code).limit(1)):
            return 'utilizzato da un workflow'
        for doc in session.scalars(select(Document).join(Incident, Document.incident_id == Incident.id).where(Incident.tenant_id == row.tenant_id)):
            if row.code in doc.notification_tag_list:
                return 'utilizzato da un documento di incidente'
        if session.scalar(select(DeadlineNotificationState.id).join(Incident, DeadlineNotificationState.incident_id == Incident.id).where(Incident.tenant_id == row.tenant_id, DeadlineNotificationState.notification_type == row.code).limit(1)):
            return 'utilizzato dallo storico delle notifiche'
        for form in session.scalars(select(FormTemplateConfig)):
            if row.code in form.notification_tag_list:
                return 'utilizzato da un modulo documento condiviso'
    elif kind == 'external_recipient':
        if session.scalar(select(Incident.id).where(Incident.tenant_id == row.tenant_id,
                                                  Incident.recipient_email == row.email).limit(1)):
            return 'destinatario già presente in un incidente'
    elif kind == 'notification_template':
        from .models import Action
        if row.action_label_id and session.scalar(select(Action.id).join(
                Incident, Action.incident_id == Incident.id).where(
                Incident.tenant_id == row.tenant_id, Action.label_id == row.action_label_id).limit(1)):
            return 'associato ad azioni già registrate in un incidente'
        for document in session.scalars(select(Document).join(Incident, Document.incident_id == Incident.id).where(Incident.tenant_id == row.tenant_id)):
            if row.kind in document.notification_tag_list or (row.linked_form_template_name and document.generated_template_name == row.linked_form_template_name):
                return 'associato a documenti di incidente già presenti'
    elif kind == 'incident_template':
        # Legacy incidents do not record the template ID they originated from.
        # Keep a potentially used template rather than infer a false absence.
        if session.scalar(select(Incident.id).where(Incident.tenant_id == row.tenant_id).limit(1)):
            return 'potenzialmente utilizzato da incidenti esistenti (origine del modello non registrata)'
    prefix = f'tenant:{row.tenant_id}:'
    for setting in session.scalars(select(Setting).where(Setting.key.startswith(prefix))):
        logical_key = setting.key[len(prefix):]
        if not any(marker in logical_key for marker in ('label', 'workflow', 'consequence', 'incident_custom', 'button_action', 'notification')):
            continue
        try:
            value = json.loads(setting.value or 'null')
        except (ValueError, TypeError):
            value = setting.value or ''
        identifier = row.code if kind == 'notification_type' else row.id
        if _json_contains_reference(value, identifier):
            return 'utilizzato da un parametro operativo del tenant'
    return ''


def _alert(session, source, replica, kind, reason):
    existing = session.scalar(select(TenantDefaultAlert).where(
        TenantDefaultAlert.tenant_id == replica.tenant_id,
        TenantDefaultAlert.source_id == source.id,
        TenantDefaultAlert.kind == kind,
        TenantDefaultAlert.local_id == replica.local_id,
    ))
    if existing is not None:
        return
    label = json.loads(replica.snapshot_json)
    caption = label.get('value') or label.get('label') or label.get('text') or label.get('name') or source.source_type
    session.add(TenantDefaultAlert(
        tenant_id=replica.tenant_id, source_id=source.id, kind=kind,
        local_type=replica.local_type, local_id=replica.local_id,
        message=f'{caption}: {reason}. Il dato locale è stato conservato con ID {replica.local_id}.',
    ))


def _retire_source(session, source):
    for replica in session.scalars(select(TenantDefaultReplica).where(TenantDefaultReplica.source_id == source.id)).all():
        local = session.get(_MODELS[replica.local_type], replica.local_id, populate_existing=True)
        if _locally_owned_category_replica(replica):
            # A local category/data-type label predated publication. Removing the
            # shared source must never remove the original tenant label.
            session.delete(replica)
            continue
        if local is not None and local.tenant_id == replica.tenant_id:
            reason = configuration_reference_reason(replica.local_type, local, session)
            customized = _json(configuration_record_payload(replica.local_type, local)) != replica.snapshot_json
            if reason or customized:
                _alert(session, source, replica, 'retired_in_use' if reason else 'retired_customized',
                       f'rimosso da Tenants Default ma {reason or "personalizzato localmente"}')
            else:
                session.delete(local)
        session.delete(replica)
    source.active = False
    source.source_id = None


def _sync_source_to_tenant(session, source, data, tenant_id):
    model = _MODELS[source.source_type]
    replica = session.scalar(select(TenantDefaultReplica).where(TenantDefaultReplica.source_id == source.id, TenantDefaultReplica.tenant_id == tenant_id).execution_options(populate_existing=True))
    local = session.get(model, replica.local_id, populate_existing=True) if replica else None
    if local is not None and local.tenant_id != tenant_id:
        raise ValueError('Provenienza Tenants Default incoerente: tenant destinatario non corrispondente.')
    if local is not None and source.source_type == 'config_label' and data['kind'] in ('category', 'data_type') and not _locally_owned_category_replica(replica):
        # Reconcile old [Tenants Default] category/data-type duplicates if removing
        # the duplicate is demonstrably safe. Categories already referenced
        # by incidents, workflows or other settings remain untouched; the
        # incident picker consolidates their display without erasing history.
        if local.value != data['value'] and _category_equivalent(
                re.sub(r'\s*\[Tenants Default(?:\s+\d+)?\]$', '', local.value, flags=re.I), data['value']):
            target = session.scalar(select(ConfigLabel).where(
                ConfigLabel.tenant_id == tenant_id, ConfigLabel.kind == data['kind'],
                ConfigLabel.value == data['value'], ConfigLabel.id != local.id))
            if target is not None:
                claimed = session.scalar(select(TenantDefaultReplica.id).where(
                    TenantDefaultReplica.local_type == 'config_label',
                    TenantDefaultReplica.local_id == target.id).limit(1))
                if claimed is None and not configuration_reference_reason('config_label', local, session):
                    snapshot = configuration_record_payload('config_label', target)
                    snapshot[_LOCAL_CATEGORY_MARKER] = True
                    # Do not destroy local target values; retire only the
                    # unreferenced former replica. All changes share transaction.
                    session.delete(local)
                    session.flush()
                    replica.local_id = target.id
                    replica.snapshot_json = _json(snapshot)
                    return
                if claimed is None:
                    # An old duplicate is still referenced by incidents or
                    # workflows. Neither rename nor detach it: doing so would
                    # create a third category and orphan semantic provenance.
                    _alert(session, source, replica, 'legacy_category_in_use',
                           'categoria legacy ancora utilizzata; consolidamento automatico sospeso per preservare i riferimenti')
                    return
    if _locally_owned_category_replica(replica):
        # Remapping, not replication: never overwrite a pre-existing tenant
        # category, even if the shared source changes its description/group.
        # Its ID stays usable by incident categories and workflow conditions.
        if local is not None and local.kind == data['kind'] and _category_equivalent(local.value, data['value']):
            return
        # A tenant admin renamed/removed the local category: the old semantic
        # association is gone, so unlink it without deleting tenant data.
        session.delete(replica)
        session.flush()
        replica = local = None
    if replica and local and _json(configuration_record_payload(source.source_type, local)) != replica.snapshot_json:
        _alert(session, source, replica, 'local_customization', 'personalizzazione locale separata dalla configurazione condivisa')
        session.delete(replica)
        session.flush()
        replica = local = None
    if replica and local is None:
        session.delete(replica)
        session.flush()
        replica = None
    defaults = _lock_defaults(session)
    mapped = _replica_data(session, source.source_type, data, tenant_id, defaults.id)
    if local is None and source.source_type == 'config_label' and data['kind'] in ('category', 'data_type'):
        # Reuse an existing local category/data-type choice instead of creating
        # an equivalent '[Tenants Default]' label. Preserve its ID, fields
        # and historical operational references.
        candidates = session.scalars(select(ConfigLabel).where(
            ConfigLabel.tenant_id == tenant_id, ConfigLabel.kind == data['kind']).order_by(ConfigLabel.id)).all()
        for candidate in candidates:
            if not _category_equivalent(candidate.value, mapped['value']):
                continue
            claimed = session.scalar(select(TenantDefaultReplica.id).where(
                TenantDefaultReplica.local_type == 'config_label',
                TenantDefaultReplica.local_id == candidate.id).limit(1))
            if claimed is not None:
                continue
            snapshot = configuration_record_payload('config_label', candidate)
            snapshot[_LOCAL_CATEGORY_MARKER] = True
            session.add(TenantDefaultReplica(
                source_id=source.id, tenant_id=tenant_id,
                local_type='config_label', local_id=candidate.id,
                snapshot_json=_json(snapshot)))
            return
    desired = _available_data(session, source.source_type, mapped, tenant_id, excluding_id=local.id if local else None)
    if local is not None and source.source_type == 'notification_type':
        # Code aliases can already occur in document tags and other string
        # references. Do not rename them merely because a collision vanished.
        desired['code'] = local.code
    if source.source_type == 'notification_template' and desired['is_default']:
        existing_default = select(NotificationTemplate.id).where(
            NotificationTemplate.tenant_id == tenant_id, NotificationTemplate.kind == desired['kind'],
            NotificationTemplate.is_default.is_(True))
        if local is not None:
            existing_default = existing_default.where(NotificationTemplate.id != local.id)
        if session.scalar(existing_default.limit(1)) is not None:
            desired['is_default'] = False
    if local is None:
        local = model(tenant_id=tenant_id, **desired)
        session.add(local)
        session.flush()
        replica = TenantDefaultReplica(source_id=source.id, tenant_id=tenant_id, local_type=source.source_type, local_id=local.id, snapshot_json=_json(desired))
        session.add(replica)
    else:
        _write_row(local, desired)
        replica.snapshot_json = _json(desired)


def sync_defaults_configuration(session=None):
    """Synchronize all published items within the current DB transaction."""
    session = _session(session)
    if session.info.get('cir_defaults_syncing'):
        return {'sources': 0, 'tenants': 0}
    session.info['cir_defaults_syncing'] = True
    try:
        with session.no_autoflush:
            defaults = _lock_defaults(session)
        if defaults is None:
            return {'sources': 0, 'tenants': 0}
        session.flush()
        sources = session.scalars(select(TenantDefaultSource).execution_options(populate_existing=True)).all()
        current = {}
        for kind, model in _MODELS.items():
            for row in session.scalars(select(model).where(model.tenant_id == defaults.id).order_by(model.id).execution_options(populate_existing=True)):
                current[(kind, row.id)] = row
        priorities = {kind: position for position, kind in enumerate(_MODELS)}
        for source in sorted(sources, key=lambda item: priorities.get(item.source_type, -1), reverse=True):
            if source.active and (source.source_type, source.source_id) not in current:
                _retire_source(session, source)
        session.flush()
        source_map = {(s.source_type, s.source_id): s for s in sources if s.active}
        tenants = session.scalars(select(Tenant.id).where(Tenant.is_system_defaults.is_(False))).all()
        for (kind, record_id), row in current.items():
            data = configuration_record_payload(kind, row)
            if kind == 'backup_job' and data['s3_secret_key'] and not data['s3_secret_key'].startswith('enc:v1:'):
                from .routes import encrypt_backup_secret
                row.s3_secret_key = encrypt_backup_secret(data['s3_secret_key'])
                data['s3_secret_key'] = row.s3_secret_key
            if kind == 'incident_template' and data.get('people_ids'):
                raise ValueError('I modelli condivisi non possono referenziare personale privato.')
            source = source_map.get((kind, record_id))
            if source is None:
                source = TenantDefaultSource(source_type=kind, source_id=record_id, snapshot_json=_json(data))
                session.add(source)
                session.flush()
            else:
                previous = json.loads(source.snapshot_json)
                immutable = 'kind' if kind == 'config_label' else ('code' if kind == 'notification_type' else None)
                if immutable and previous.get(immutable) != data[immutable]:
                    raise ValueError(f'Il campo {immutable} di un parametro pubblicato è immutabile: creare un nuovo parametro.')
                source.snapshot_json = _json(data)
            for tenant_id in tenants:
                _sync_source_to_tenant(session, source, data, tenant_id)
        session.flush()
        session.info.pop('cir_defaults_dirty', None)
        return {'sources': len(current), 'tenants': len(tenants)}
    finally:
        session.info.pop('cir_defaults_syncing', None)


def _valid_uuid(value, field):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f'{field}: UUID non valido.') from exc
    return value


def _validate_data(kind, raw):
    if not isinstance(raw, dict) or set(raw) - set(_FIELDS[kind]):
        raise ValueError('Campi di configurazione non consentiti.')
    data = dict(_DEFAULTS[kind])
    data.update(raw)
    required = {'config_label': ('kind', 'value'), 'notification_type': ('code', 'label'),
                'recommendation': ('text',), 'external_recipient': ('email',),
                'notification_template': ('kind', 'name'), 'incident_template': ('name',),
                'backup_job': ('name',)}[kind]
    for name in required:
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ValueError(f'Campo {name} obbligatorio.')
    for key, value in data.items():
        if key in _BOOLEAN_FIELDS:
            if type(value) is not bool:
                raise ValueError(f'Campo {key}: booleano richiesto.')
        elif key == 'max_completion_hours':
            if type(value) is not int or not 0 <= value <= 1000000:
                raise ValueError('Durata massima non valida.')
        elif key in _ID_FIELDS.get(kind, {}):
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f'Campo {key}: riferimento non valido.')
        elif key in _CSV_FIELDS.get(kind, {}):
            if not isinstance(value, str) or (value and not re.fullmatch(r'[1-9][0-9]*(?:,[1-9][0-9]*)*', value)):
                raise ValueError(f'Campo {key}: elenco riferimenti non valido.')
        elif value is None and key in _NULLABLE_TEXT_FIELDS:
            continue
        else:
            maximum = {'kind': 40, 'group': 80, 'value': 255, 'code': 40, 'label': 160,
                       'automatic_operations': 255, 'name': 160, 'email': 255, 'subject': 255,
                       'linked_form_template_name': 255, 'recipient_source': 40, 'cc_source': 40,
                       'recipient_value': 255, 'cc_value': 255, 'incident_name': 255,
                       'reference': 255, 'recipient': 255, 'recipient_email': 255, 'status': 40,
                       'data_subjects_count': 255, 'cron_expression': 120, 'destination': 40,
                       'local_path': 500, 's3_endpoint_url': 500, 's3_bucket': 255,
                       's3_prefix': 255, 's3_access_key': 255, 's3_secret_key': 8192,
                       'body': 200000}.get(key, 20000)
            if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
                raise ValueError(f'Campo {key}: testo non valido o troppo lungo.')
    if kind == 'config_label':
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', data['kind']):
            raise ValueError('Tipo di label non valido.')
        operations = {x.strip() for x in data['automatic_operations'].split(',') if x.strip()}
        if operations - {'close_without_warnings', 'end_breach', 'global_check'}:
            raise ValueError('Operazione automatica non riconosciuta.')
    if kind == 'notification_type' and not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', data['code']):
        raise ValueError('Codice del tipo di notifica non valido.')
    if kind == 'external_recipient' and not re.fullmatch(r'[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+', data['email']):
        raise ValueError('Indirizzo del destinatario esterno non valido.')
    if kind == 'incident_template' and data['people_ids']:
        raise ValueError('Rimuovere il personale privato dai modelli prima di condividerli in Tenants Default.')
    if kind == 'notification_template':
        allowed_sources = {'type_default', 'incident_recipient_email', 'incident_creator_email', 'fixed', 'empty', 'manual'}
        if data['recipient_source'] not in allowed_sources or data['cc_source'] not in allowed_sources:
            raise ValueError('Origine indirizzo del template di notifica non valida.')
    if kind == 'backup_job' and data['destination'] not in {'local', 's3', 'download'}:
        raise ValueError('Destinazione backup non valida.')
    return data


def _validate_portable_data(kind, raw):
    if not isinstance(raw, dict):
        raise ValueError('Configurazione non valida.')
    converted = dict(raw)
    for field in _ID_FIELDS.get(kind, {}):
        if converted.get(field) is not None:
            _valid_uuid(converted[field], field)
        converted[field] = None
    for field in _CSV_FIELDS.get(kind, {}):
        values = converted.get(field, [])
        if not isinstance(values, list) or len(values) > MAX_CONFIGURATION_ITEMS:
            raise ValueError(f'Campo {field}: elenco UUID richiesto.')
        for value in values:
            _valid_uuid(value, field)
        if len(set(values)) != len(values):
            raise ValueError(f'Campo {field}: riferimenti duplicati.')
        converted[field] = ''
    if kind == 'notification_template':
        _valid_uuid(converted.get('kind'), 'Tipo di notifica')
        converted['kind'] = 'reference'
    validated = _validate_data(kind, converted)
    for field in _ID_FIELDS.get(kind, {}):
        validated[field] = raw.get(field)
    for field in _CSV_FIELDS.get(kind, {}):
        validated[field] = list(raw.get(field, []))
    if kind == 'notification_template':
        validated['kind'] = raw['kind']
    if kind == 'backup_job' and validated['s3_secret_key'].startswith('enc:v1:'):
        raise ValueError('La credenziale backup portabile deve essere decifrata, oppure omessa esplicitamente.')
    return validated


def validate_configuration_payload(payload):
    if not isinstance(payload, dict) or set(payload) - {'format', 'origin', 'items'}:
        raise ValueError('Formato del file di configurazione non valido.')
    if payload.get('format') != CONFIGURATION_FORMAT:
        raise ValueError('Formato del file di configurazione non supportato.')
    try:
        if len(_json(payload).encode('utf-8')) > MAX_CONFIGURATION_BYTES:
            raise ValueError('File di configurazione troppo grande.')
    except (TypeError, RecursionError) as exc:
        raise ValueError('File di configurazione non valido.') from exc
    origin = _valid_uuid(payload.get('origin'), 'Origine')
    items = payload.get('items')
    if not isinstance(items, list) or len(items) > MAX_CONFIGURATION_ITEMS:
        raise ValueError('Elenco configurazioni non valido o troppo grande.')
    seen = set()
    normalized = []
    for item in items:
        if (not isinstance(item, dict) or set(item) - {'key', 'type', 'data', 'redacted_fields'}
                or not {'key', 'type', 'data'} <= set(item) or item.get('type') not in _MODELS):
            raise ValueError('Elemento di configurazione non valido.')
        key = _valid_uuid(item['key'], 'Chiave elemento')
        if key in seen:
            raise ValueError('Chiave di configurazione duplicata.')
        seen.add(key)
        data = _validate_portable_data(item['type'], item['data'])
        result = {'key': key, 'type': item['type'], 'data': data}
        redacted = item.get('redacted_fields', [])
        if not isinstance(redacted, list) or (redacted and (item['type'] != 'backup_job' or redacted != ['s3_secret_key'])):
            raise ValueError('Campi omessi non validi.')
        if redacted:
            if data['s3_secret_key']:
                raise ValueError('Una credenziale omessa deve avere valore vuoto.')
            result['redacted_fields'] = redacted
        normalized.append(result)
    by_key = {item['key']: item for item in normalized}

    def check_reference(reference, required_type, required_label_kind=None):
        target = by_key.get(reference)
        if target is None or target['type'] != required_type:
            raise ValueError('Dipendenza mancante o di tipo errato nel file di configurazione.')
        if required_label_kind and target['data']['kind'] != required_label_kind:
            raise ValueError('Tipo di label errato nella dipendenza di configurazione.')

    for item in normalized:
        kind, data = item['type'], item['data']
        for field, ref_type in _ID_FIELDS.get(kind, {}).items():
            if data[field] is not None:
                check_reference(data[field], ref_type, 'action_label' if field == 'action_label_id' else 'severity')
        for field, ref_type in _CSV_FIELDS.get(kind, {}).items():
            expected_kind = {'category_ids': 'category', 'data_type_ids': 'data_type'}.get(field)
            for reference in data[field]:
                check_reference(reference, ref_type, expected_kind)
        if kind == 'notification_template':
            check_reference(data['kind'], 'notification_type')
    return {'format': CONFIGURATION_FORMAT, 'origin': origin, 'items': normalized}


def exported_configuration_key(origin, kind, tenant_id, record_id):
    return str(uuid.uuid5(uuid.UUID(origin), f'{kind}:{int(tenant_id)}:{int(record_id)}'))


def export_configuration(tenant_id, session=None, *, include_extended=False, include_secrets=False,
                         strip_personnel_references=False):
    """Export reusable fields only. Caller commits the new origin if needed."""
    session = _session(session)
    tenant = session.get(Tenant, int(tenant_id))
    if tenant is None:
        raise ValueError('Tenant non trovato.')
    setting = session.get(Setting, _ORIGIN_SETTING)
    if setting is None:
        setting = Setting(key=_ORIGIN_SETTING, value=str(uuid.uuid4()))
        session.add(setting)
        session.flush()
    origin = _valid_uuid(setting.value, 'Origine installazione')
    items = []
    chosen_models = _MODELS if include_extended else {kind: model for kind, model in _MODELS.items() if kind in _BASIC_TYPES}
    rows_by_type = {kind: list(session.scalars(select(model).where(model.tenant_id == tenant.id).order_by(model.id)))
                    for kind, model in chosen_models.items()}

    def reference_key(kind, raw_id):
        if not any(row.id == int(raw_id) for row in rows_by_type.get(kind, [])):
            raise ValueError('La configurazione contiene una dipendenza assente o appartenente a un altro tenant.')
        return exported_configuration_key(origin, kind, tenant.id, raw_id)

    for kind, rows in rows_by_type.items():
        for row in rows:
            key = exported_configuration_key(origin, kind, tenant.id, row.id)
            data = configuration_record_payload(kind, row)
            if kind == 'incident_template' and strip_personnel_references:
                # Initial defaults provisioning copies reusable configuration,
                # never references to private staff records in operational data.
                data['people_ids'] = ''
            for field, ref_type in _ID_FIELDS.get(kind, {}).items():
                data[field] = reference_key(ref_type, data[field]) if data[field] is not None else None
            for field, ref_type in _CSV_FIELDS.get(kind, {}).items():
                data[field] = [reference_key(ref_type, value) for value in str(data[field] or '').split(',') if value.strip()]
            if kind == 'notification_template':
                notification = next((item for item in rows_by_type['notification_type'] if item.code == row.kind), None)
                if notification is None:
                    raise ValueError('Tipo di notifica mancante nel tenant sorgente.')
                data['kind'] = reference_key('notification_type', notification.id)
            item = {'key': key, 'type': kind, 'data': data}
            if kind == 'backup_job':
                if include_secrets:
                    from .routes import decrypt_backup_secret
                    data['s3_secret_key'] = decrypt_backup_secret(data['s3_secret_key'])
                    if row.s3_secret_key and not data['s3_secret_key']:
                        raise ValueError('Credenziale backup non decifrabile: esportazione interrotta.')
                else:
                    data['s3_secret_key'] = ''
                    item['redacted_fields'] = ['s3_secret_key']
            items.append(item)
    return validate_configuration_payload({'format': CONFIGURATION_FORMAT, 'origin': origin, 'items': items})


def import_configuration(payload, target_defaults_id, session=None):
    """Add or update by export provenance; never overwrite unrelated records.

Omitted items are not deleted. All validation runs before the first mutation.
An imported ID or tenant ID cannot be used to select an existing target row.
"""
    normalized = validate_configuration_payload(payload)
    session = _session(session)
    with session.no_autoflush:
        defaults = _lock_defaults(session)
    if defaults is None or defaults.id != int(target_defaults_id):
        raise ValueError('Le configurazioni condivise si importano solo in Tenants Default.')
    session.flush()
    created = updated = unchanged = 0
    for item in normalized['items']:
        if item['type'] == 'notification_template':
            _require_form_template(session, item['data'].get('linked_form_template_name'), defaults.id)
    installed_items = {}
    priorities = {kind: position for position, kind in enumerate(_MODELS)}
    for item in sorted(normalized['items'], key=lambda value: priorities[value['type']]):
        kind = item['type']
        source = session.scalar(select(TenantDefaultSource).where(TenantDefaultSource.import_origin == normalized['origin'], TenantDefaultSource.import_key == item['key']).execution_options(populate_existing=True))
        if source and source.source_type != kind:
            raise ValueError('Tipo della configurazione importata diverso dalla sua provenienza.')
        row = session.get(_MODELS[kind], source.source_id, populate_existing=True) if source and source.active and source.source_id else None
        if row is not None and row.tenant_id != defaults.id:
            raise ValueError('Provenienza import non coerente con Tenants Default.')
        raw_data = dict(item['data'])
        for field in _ID_FIELDS.get(kind, {}):
            raw_data[field] = installed_items[raw_data[field]]['id'] if raw_data[field] is not None else None
        for field in _CSV_FIELDS.get(kind, {}):
            raw_data[field] = ','.join(str(installed_items[key]['id']) for key in raw_data[field])
        if kind == 'notification_template':
            raw_data['kind'] = installed_items[raw_data['kind']]['code']
        if kind == 'backup_job':
            from .routes import decrypt_backup_secret, encrypt_backup_secret
            if 's3_secret_key' in item.get('redacted_fields', []):
                raw_data['s3_secret_key'] = row.s3_secret_key if row is not None else ''
            elif row is not None and decrypt_backup_secret(row.s3_secret_key) == raw_data['s3_secret_key']:
                raw_data['s3_secret_key'] = row.s3_secret_key
            else:
                raw_data['s3_secret_key'] = encrypt_backup_secret(raw_data['s3_secret_key'])
        raw_data = _validate_data(kind, raw_data)
        data = _available_data(session, kind, raw_data, defaults.id, excluding_id=row.id if row else None, suffix='importato')
        if row is None:
            row = _MODELS[kind](tenant_id=defaults.id, **data)
            session.add(row)
            session.flush()
            if source is None:
                source = TenantDefaultSource(source_type=kind, import_origin=normalized['origin'], import_key=item['key'])
                session.add(source)
            source.source_id = row.id
            source.active = True
            source.snapshot_json = _json(data)
            source.import_snapshot_json = _json(raw_data)
            created += 1
        else:
            old = configuration_record_payload(kind, row)
            immutable = 'kind' if kind == 'config_label' else ('code' if kind == 'notification_type' else None)
            previous_import = json.loads(source.import_snapshot_json or source.snapshot_json)
            if immutable and previous_import[immutable] != raw_data[immutable]:
                raise ValueError(f'Il campo {immutable} pubblicato non può essere cambiato tramite import.')
            if kind == 'notification_type':
                data['code'] = old['code']
            if old == data:
                unchanged += 1
            else:
                _write_row(row, data)
                updated += 1
            source.import_snapshot_json = _json(raw_data)
        session.flush()
        result = {'type': kind, 'id': row.id}
        for field in ('code', 'value', 'name'):
            if hasattr(row, field):
                result[field] = getattr(row, field)
        installed_items[item['key']] = result
    sync_defaults_configuration(session)
    return {'created': created, 'updated': updated, 'unchanged': unchanged, 'items': installed_items}


def inherited_configuration_record(row, session=None):
    """Return provenance for the UI; None means an independently owned row."""
    session = _session(session)
    kind = next((name for name, model in _MODELS.items() if isinstance(row, model)), None)
    if not kind or not row.id:
        return None
    replica = session.scalar(select(TenantDefaultReplica).where(
        TenantDefaultReplica.local_type == kind, TenantDefaultReplica.local_id == row.id))
    return None if _locally_owned_category_replica(replica) else replica


def resolve_shared_configuration_record(source_uuid, target_tenant_id, expected_type=None, session=None):
    """Resolve a published identity to the exact destination replica.

    Callers synchronize once before resolving a collection. Natural names and
    imported numeric IDs never select a destination object.
    """
    session = _session(session)
    _valid_uuid(source_uuid, 'Identità del parametro condiviso')
    source = session.get(TenantDefaultSource, source_uuid)
    if source is None or not source.active or source.source_type not in _MODELS:
        raise ValueError('Parametro condiviso assente o ritirato.')
    if expected_type is not None and source.source_type != expected_type:
        raise ValueError('Tipo del parametro condiviso non corrispondente.')
    defaults = session.scalar(select(Tenant).where(Tenant.is_system_defaults.is_(True)))
    origin = session.get(_MODELS[source.source_type], source.source_id)
    if defaults is None or origin is None or origin.tenant_id != defaults.id:
        raise ValueError('Provenienza del parametro condiviso non valida.')
    if int(target_tenant_id) == defaults.id:
        return origin
    replica = session.scalar(select(TenantDefaultReplica).where(
        TenantDefaultReplica.source_id == source.id,
        TenantDefaultReplica.tenant_id == int(target_tenant_id)))
    local = session.get(_MODELS[source.source_type], replica.local_id) if replica else None
    if local is None and not session.info.get('cir_defaults_syncing'):
        # A newly created tenant may not have received its published replicas
        # yet. Synchronize in the caller transaction, then resolve by UUID.
        sync_defaults_configuration(session)
        replica = session.scalar(select(TenantDefaultReplica).where(
            TenantDefaultReplica.source_id == source.id,
            TenantDefaultReplica.tenant_id == int(target_tenant_id)))
        local = session.get(_MODELS[source.source_type], replica.local_id) if replica else None
    if local is None or local.tenant_id != int(target_tenant_id) or replica.local_type != source.source_type:
        raise ValueError('Replica del parametro condiviso non disponibile nel tenant destinatario.')
    return local


def _configuration_objects_changed(session):
    types = (Tenant, *_MODELS.values())
    if any(isinstance(row, types) for group in (session.new, session.deleted) for row in group):
        return True
    for row in session.dirty:
        if isinstance(row, Tenant) and session.is_modified(row, include_collections=False):
            return True
        kind = next((kind for kind, model in _MODELS.items() if isinstance(row, model)), None)
        if kind and any(inspect(row).attrs[name].history.has_changes() for name in (*_FIELDS[kind], 'tenant_id')):
            return True
    return False


def _mark_configuration_dirty(session, flush_context, instances):
    if session.info.get('cir_defaults_suspended') or session.info.get('cir_defaults_syncing'):
        return
    if _configuration_objects_changed(session):
        session.info['cir_defaults_dirty'] = True
        # Take the shared row lock before ORM writes, including explicit early
        # flushes in existing routes. This keeps concurrent publishers in a
        # consistent lock order and closes the new-tenant provisioning race.
        with session.no_autoflush:
            _lock_defaults(session)


def _before_configuration_commit(session):
    if session.info.get('cir_defaults_suspended') or session.info.get('cir_defaults_syncing') or session.in_nested_transaction():
        return
    changed = _configuration_objects_changed(session)
    if changed or session.info.get('cir_defaults_dirty'):
        sync_defaults_configuration(session)


def _clear_configuration_dirty(session, transaction):
    # A savepoint finishing must not lose a source change already flushed in
    # the outer transaction. Reconcile that change at its real commit.
    if transaction.parent is None:
        session.info.pop('cir_defaults_dirty', None)
        session.info.pop('cir_defaults_locked_id', None)


def register_defaults_events():
    """Install once process-wide; no implicit commits or out-of-band writes."""
    listeners = (
        ('before_flush', _mark_configuration_dirty),
        ('before_commit', _before_configuration_commit),
        ('after_transaction_end', _clear_configuration_dirty),
    )
    for name, function in listeners:
        if not event.contains(Session, name, function):
            event.listen(Session, name, function)
