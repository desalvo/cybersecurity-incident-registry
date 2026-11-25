"""Behavioral regression tests for shared tenant configuration provenance."""
import copy
import json
import uuid

import pytest


@pytest.fixture
def defaults_db(tmp_path):
    from flask import Flask
    from sqlalchemy import event
    from app.models import db, Tenant
    from app.tenant_defaults import ensure_defaults_tenant, register_defaults_events

    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='tenant-defaults-test-key', SQLALCHEMY_DATABASE_URI='sqlite:///' + str(tmp_path / 'defaults.db'), SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        @event.listens_for(db.engine, 'connect')
        def enable_foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')

        db.create_all()
        db.session.info['cir_defaults_suspended'] = True
        operational = Tenant(name='default')
        other = Tenant(name='lab')
        db.session.add_all([operational, other])
        defaults = ensure_defaults_tenant()
        db.session.commit()
        db.session.info.pop('cir_defaults_suspended', None)
        register_defaults_events()
        yield db, defaults.id, operational.id, other.id
        db.session.rollback()
        db.session.remove()


def _publish(defaults_db, kind='severity', value='Shared', **kwargs):
    from app.models import ConfigLabel
    db, default_id, _, _ = defaults_db
    label = ConfigLabel(tenant_id=default_id, kind=kind, value=value, description='original', **kwargs)
    db.session.add(label)
    db.session.commit()
    return label


def _replica(label, tenant_id):
    from app.models import ConfigLabel
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    source = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=label.id).one()
    record = TenantDefaultReplica.query.filter_by(source_id=source.id, tenant_id=tenant_id).one()
    return ConfigLabel.query.filter_by(id=record.local_id).one()


def test_system_tenant_is_separate_and_idempotent(defaults_db):
    from app.models import Tenant
    from app.tenant_defaults import ensure_defaults_tenant
    _, defaults_id, operational_id, _ = defaults_db
    assert defaults_id != operational_id
    assert ensure_defaults_tenant().id == defaults_id
    assert Tenant.query.filter_by(is_system_defaults=True).count() == 1
    assert not Tenant.query.filter_by(id=operational_id).one().is_tenants_default


def test_create_update_and_new_tenant_propagate_with_fresh_ids(defaults_db):
    from app.models import Tenant
    db, defaults_id, operational_id, other_id = defaults_db
    label = _publish(defaults_db)
    local = _replica(label, operational_id)
    other = _replica(label, other_id)
    assert len({label.id, local.id, other.id}) == 3
    label.value = 'Renamed shared'
    label.description = 'updated centrally'
    db.session.commit()
    assert local.value == other.value == 'Renamed shared'
    assert local.description == other.description == 'updated centrally'
    new = Tenant(name='new-tenant')
    db.session.add(new)
    db.session.commit()
    assert _replica(label, new.id).description == 'updated centrally'


def test_source_update_after_early_flush_still_propagates(defaults_db):
    db, _, operational_id, _ = defaults_db
    label = _publish(defaults_db)
    label.description = 'flushed before commit'
    db.session.flush()
    db.session.commit()
    assert _replica(label, operational_id).description == 'flushed before commit'


@pytest.mark.parametrize('rollback_savepoint', [False, True])
def test_savepoint_does_not_discard_pending_outer_propagation(defaults_db, rollback_savepoint):
    db, _, operational_id, _ = defaults_db
    label = _publish(defaults_db)
    label.description = 'outer change'
    db.session.flush()
    savepoint = db.session.begin_nested()
    if rollback_savepoint:
        savepoint.rollback()
    else:
        savepoint.commit()
    db.session.commit()
    assert _replica(label, operational_id).description == 'outer change'


def test_name_collision_never_reuses_or_overwrites_local_row(defaults_db):
    from app.models import ConfigLabel
    db, _, operational_id, other_id = defaults_db
    local = ConfigLabel(tenant_id=operational_id, kind='severity', value='Shared', description='private settings')
    db.session.add(local)
    db.session.commit()
    original_id = local.id
    published = _publish(defaults_db)
    inherited = _replica(published, operational_id)
    assert inherited.id != original_id
    assert inherited.value == 'Shared [Tenants Default]'
    assert local.description == 'private settings'
    assert _replica(published, other_id).value == 'Shared'
    published.description = 'new shared value'
    db.session.commit()
    assert inherited.description == 'new shared value'
    assert local.description == 'private settings'


def test_local_edit_detaches_and_shared_item_remains_visible(defaults_db):
    from app.tenant_defaults_models import TenantDefaultAlert
    db, _, operational_id, _ = defaults_db
    published = _publish(defaults_db)
    local = _replica(published, operational_id)
    local.description = 'tenant customization'
    local_id = local.id
    db.session.commit()
    replacement = _replica(published, operational_id)
    assert replacement.id != local_id
    assert replacement.description == 'original'
    assert local.description == 'tenant customization'
    alert = TenantDefaultAlert.query.filter_by(tenant_id=operational_id).one()
    assert alert.kind == 'local_customization'
    assert alert.local_id == local_id


def test_deleting_unused_source_removes_only_its_replicas(defaults_db):
    from app.models import ConfigLabel, Tenant
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    db, _, operational_id, _ = defaults_db
    published = _publish(defaults_db)
    local_id = _replica(published, operational_id).id
    own = ConfigLabel(tenant_id=operational_id, kind='severity', value='own')
    db.session.add(own)
    db.session.commit()
    db.session.delete(published)
    db.session.flush()
    db.session.commit()
    assert db.session.get(ConfigLabel, local_id) is None
    assert db.session.get(ConfigLabel, own.id) is not None
    assert TenantDefaultReplica.query.count() == 0
    assert TenantDefaultSource.query.one().active is False
    new = Tenant(name='later')
    db.session.add(new)
    db.session.commit()
    assert ConfigLabel.query.filter_by(tenant_id=new.id).count() == 0


@pytest.mark.parametrize('usage', ['severity', 'category', 'data_type', 'action', 'condition', 'template', 'setting'])
def test_retirement_preserves_referenced_labels_and_alerts_tenant(defaults_db, usage):
    from app.models import ConfigLabel, Incident, Action, IncidentWorkflowStep, IncidentTemplate, Setting
    from app.tenant_defaults_models import TenantDefaultAlert, TenantDefaultReplica
    from app.timeutils import utcnow
    db, _, operational_id, other_id = defaults_db
    kind = {'category': 'category', 'data_type': 'data_type', 'action': 'action_label'}.get(usage, 'severity')
    published = _publish(defaults_db, kind=kind)
    local = _replica(published, operational_id)
    local_id = local.id
    other_id_to_delete = _replica(published, other_id).id
    incident = Incident(tenant_id=operational_id, name='Existing incident', reference='A1')
    db.session.add(incident)
    db.session.flush()
    if usage == 'severity':
        incident.severity_id = local.id
    elif usage == 'category':
        incident.categories.append(local)
    elif usage == 'data_type':
        incident.data_types.append(local)
    elif usage == 'action':
        db.session.add(Action(incident_id=incident.id, label_id=local.id, when_at=utcnow()))
    elif usage == 'condition':
        own = ConfigLabel(tenant_id=operational_id, kind='action_label', value='local action')
        db.session.add(own)
        db.session.flush()
        db.session.add(IncidentWorkflowStep(tenant_id=operational_id, action_label_id=own.id, conditions=f'!severity:{local.id}'))
    elif usage == 'template':
        db.session.add(IncidentTemplate(tenant_id=operational_id, name='template', category_ids=str(local.id)))
    else:
        db.session.add(Setting(key=f'tenant:{operational_id}:incident_button_action_labels_json', value=json.dumps({'rule': {'label_id': local.id}})))
    db.session.commit()
    db.session.delete(published)
    db.session.commit()
    assert db.session.get(ConfigLabel, local_id) is not None
    assert db.session.get(ConfigLabel, other_id_to_delete) is None
    assert TenantDefaultReplica.query.filter_by(local_id=local_id).count() == 0
    alerts = TenantDefaultAlert.query.filter_by(tenant_id=operational_id).all()
    assert len(alerts) == 1 and alerts[0].kind == 'retired_in_use'
    from app.tenant_defaults import sync_defaults_configuration
    sync_defaults_configuration()
    db.session.commit()
    assert TenantDefaultAlert.query.filter_by(tenant_id=operational_id).count() == 1


def test_recommendation_used_in_incident_is_retained(defaults_db):
    from app.models import Recommendation, Incident
    from app.tenant_defaults_models import TenantDefaultAlert
    db, defaults_id, operational_id, _ = defaults_db
    row = Recommendation(tenant_id=defaults_id, text='Shared recommendation')
    db.session.add(row)
    db.session.commit()
    local = Recommendation.query.filter_by(tenant_id=operational_id).one()
    incident = Incident(tenant_id=operational_id, name='Incident', reference='R1', recommendations=[local])
    db.session.add(incident)
    db.session.commit()
    db.session.delete(row)
    db.session.commit()
    assert incident.recommendations == [local]
    assert TenantDefaultAlert.query.filter_by(tenant_id=operational_id).one().kind == 'retired_in_use'


def test_notification_alias_and_document_reference_are_preserved(defaults_db):
    from app.models import NotificationType, Incident, Document
    from app.tenant_defaults_models import TenantDefaultAlert
    db, defaults_id, operational_id, _ = defaults_db
    own = NotificationType(tenant_id=operational_id, code='security', label='Local notice')
    shared = NotificationType(tenant_id=defaults_id, code='security', label='Shared notice')
    db.session.add_all([own, shared])
    db.session.commit()
    replica = NotificationType.query.filter_by(tenant_id=operational_id, code='security_td').one()
    incident = Incident(tenant_id=operational_id, name='Incident', reference='N1')
    db.session.add(incident)
    db.session.flush()
    document = Document(incident_id=incident.id, notification_tags='security_td')
    db.session.add(document)
    db.session.delete(own)
    shared.label = 'Updated shared notice'
    db.session.commit()
    assert replica.code == document.notification_tags == 'security_td'
    assert replica.label == 'Updated shared notice'
    db.session.delete(shared)
    db.session.commit()
    assert db.session.get(NotificationType, replica.id) is not None
    assert TenantDefaultAlert.query.filter_by(tenant_id=operational_id).one().kind == 'retired_in_use'


def test_publishing_failure_rolls_back_source_and_every_replica(defaults_db, monkeypatch):
    from app import tenant_defaults as service
    db, _, operational_id, other_id = defaults_db
    published = _publish(defaults_db)
    original = service._sync_source_to_tenant

    def fail_second(session, source, data, tenant_id):
        if tenant_id == other_id:
            raise RuntimeError('simulated sync failure')
        return original(session, source, data, tenant_id)

    monkeypatch.setattr(service, '_sync_source_to_tenant', fail_second)
    published.description = 'must roll back'
    with pytest.raises(RuntimeError, match='simulated'):
        db.session.commit()
    db.session.rollback()
    assert published.description == 'original'
    assert _replica(published, operational_id).description == 'original'
    assert _replica(published, other_id).description == 'original'


def test_configuration_export_import_is_scoped_and_idempotent(defaults_db):
    from app.models import ConfigLabel, Setting, NotificationType
    from app.tenant_defaults import export_configuration, import_configuration
    from app.tenant_defaults_models import TenantDefaultSource
    db, defaults_id, operational_id, other_id = defaults_db
    own = ConfigLabel(tenant_id=operational_id, kind='action_label', value='Configured action', description='reuse this', max_completion_hours=72, description_required=True)
    existing = ConfigLabel(tenant_id=defaults_id, kind='action_label', value='Configured action', description='do not replace')
    db.session.add_all([own, existing, ConfigLabel(tenant_id=other_id, kind='severity', value='Other tenant private'),
                        Setting(key=f'tenant:{operational_id}:smtp_password', value='SECRET')])
    db.session.commit()
    payload = export_configuration(operational_id)
    db.session.commit()
    serialized = json.dumps(payload)
    assert 'SECRET' not in serialized
    assert 'Other tenant private' not in serialized
    assert all('id' not in item['data'] and 'tenant_id' not in item['data'] for item in payload['items'])
    assert export_configuration(operational_id) == payload
    result = import_configuration(payload, defaults_id)
    db.session.commit()
    assert result['created'] >= 1
    assert existing.description == 'do not replace'
    imported = ConfigLabel.query.filter_by(tenant_id=defaults_id, value='Configured action [importato]').one()
    assert imported.max_completion_hours == 72 and imported.description_required
    second = import_configuration(payload, defaults_id)
    db.session.commit()
    assert second['created'] == second['updated'] == 0
    updated = copy.deepcopy(payload)
    selected = next(item for item in updated['items'] if item['data'].get('value') == 'Configured action')
    selected['data']['description'] = 'new exported description'
    result = import_configuration(updated, defaults_id)
    db.session.commit()
    assert imported.description == 'new exported description'
    assert existing.description == 'do not replace'
    assert TenantDefaultSource.query.filter_by(import_origin=payload['origin'], import_key=selected['key']).count() == 1


@pytest.mark.parametrize('bad', ['tenant', 'id', 'secret', 'wrong_type', 'duplicate', 'negative_hours', 'wrong_boolean'])
def test_configuration_import_rejects_malformed_records_without_writes(defaults_db, bad):
    from app.models import ConfigLabel
    from app.tenant_defaults import CONFIGURATION_FORMAT, import_configuration
    db, defaults_id, operational_id, _ = defaults_db
    payload = {'format': CONFIGURATION_FORMAT, 'origin': str(uuid.uuid4()), 'items': [
        {'key': str(uuid.uuid4()), 'type': 'config_label', 'data': {'kind': 'severity', 'value': 'new'}}]}
    data = payload['items'][0]['data']
    if bad == 'tenant': data['tenant_id'] = operational_id
    elif bad == 'id': data['id'] = 1
    elif bad == 'secret': data['smtp_password'] = 'unwanted'
    elif bad == 'wrong_type': payload['items'][0]['type'] = 'users'
    elif bad == 'duplicate': payload['items'].append(copy.deepcopy(payload['items'][0]))
    elif bad == 'negative_hours': data['max_completion_hours'] = -1
    else: data['default_exportable'] = 'false'
    before = ConfigLabel.query.count()
    with pytest.raises(ValueError):
        import_configuration(payload, defaults_id)
    assert ConfigLabel.query.count() == before


def test_configuration_import_cannot_target_operational_tenant(defaults_db):
    from app.tenant_defaults import CONFIGURATION_FORMAT, import_configuration
    _, _, operational_id, _ = defaults_db
    payload = {'format': CONFIGURATION_FORMAT, 'origin': str(uuid.uuid4()), 'items': []}
    with pytest.raises(ValueError, match='solo in Tenants Default'):
        import_configuration(payload, operational_id)


def test_explicit_sync_works_during_suspended_restore(defaults_db):
    from app.models import ConfigLabel
    from app.tenant_defaults import sync_defaults_configuration
    db, defaults_id, operational_id, _ = defaults_db
    db.session.info['cir_defaults_suspended'] = True
    source = ConfigLabel(tenant_id=defaults_id, kind='severity', value='restored source')
    db.session.add(source)
    db.session.commit()
    assert ConfigLabel.query.filter_by(tenant_id=operational_id).count() == 0
    sync_defaults_configuration()
    db.session.commit()
    assert _replica(source, operational_id).value == 'restored source'
    db.session.info.pop('cir_defaults_suspended', None)


def _generic_replica(source_row, source_type, tenant_id):
    from app.tenant_defaults import _MODELS
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    source = TenantDefaultSource.query.filter_by(source_type=source_type, source_id=source_row.id).one()
    replica = TenantDefaultReplica.query.filter_by(source_id=source.id, tenant_id=tenant_id).one()
    return _MODELS[source_type].query.filter_by(id=replica.local_id).one()


def test_notification_templates_remap_dependencies_and_preserve_local_default(defaults_db):
    from app.models import ConfigLabel, NotificationType, NotificationTemplate, FormTemplateConfig, FormTemplateBinary
    db, defaults_id, operational_id, _ = defaults_db
    local_type = NotificationType(tenant_id=operational_id, code='notice', label='Local type')
    source_type = NotificationType(tenant_id=defaults_id, code='notice', label='Shared type')
    action = ConfigLabel(tenant_id=defaults_id, kind='action_label', value='Notify')
    db.session.add_all([local_type, source_type, action])
    db.session.commit()
    inherited_type = _generic_replica(source_type, 'notification_type', operational_id)
    own = NotificationTemplate(tenant_id=operational_id, kind=inherited_type.code,
                               name='Notification', subject='LOCAL', is_default=True)
    db.session.add_all([own, FormTemplateConfig(template_name='notice-form'),
                       FormTemplateBinary(template_name='notice-form', filename='notice-form.pdf', pdf_data=b'%PDF-1.4\n%%EOF\n')])
    db.session.commit()
    source = NotificationTemplate(tenant_id=defaults_id, kind='notice', name='Notification', subject='SHARED',
                                  action_label_id=action.id, linked_form_template_name='notice-form', is_default=True)
    db.session.add(source)
    db.session.commit()
    local = _generic_replica(source, 'notification_template', operational_id)
    assert local.kind == inherited_type.code == 'notice_td'
    assert local.action_label_id == _replica(action, operational_id).id
    assert local.linked_form_template_name == 'notice-form'
    assert local.name == 'Notification [Tenants Default]'
    assert own.subject == 'LOCAL' and own.is_default is True
    assert local.is_default is False
    source.subject = 'Changed centrally'
    db.session.commit()
    assert local.subject == 'Changed centrally' and own.subject == 'LOCAL'


def test_incident_template_remaps_all_label_and_recommendation_ids(defaults_db):
    from app.models import ConfigLabel, Recommendation, IncidentTemplate
    db, defaults_id, operational_id, _ = defaults_db
    severity = ConfigLabel(tenant_id=defaults_id, kind='severity', value='Critical')
    category = ConfigLabel(tenant_id=defaults_id, kind='category', value='Category')
    datatype = ConfigLabel(tenant_id=defaults_id, kind='data_type', value='Data')
    recommendation = Recommendation(tenant_id=defaults_id, text='Shared advice')
    db.session.add_all([severity, category, datatype, recommendation])
    db.session.commit()
    source = IncidentTemplate(tenant_id=defaults_id, name='Incident blueprint', severity_id=severity.id,
                              category_ids=str(category.id), data_type_ids=str(datatype.id),
                              recommendation_ids=str(recommendation.id), personal_data=True)
    db.session.add(source)
    db.session.commit()
    local = _generic_replica(source, 'incident_template', operational_id)
    assert local.severity_id == _replica(severity, operational_id).id
    assert local.category_id_list() == [_replica(category, operational_id).id]
    assert local.data_type_id_list() == [_replica(datatype, operational_id).id]
    assert local.recommendation_id_list() == [_generic_replica(recommendation, 'recommendation', operational_id).id]
    assert local.personal_data is True


def test_shared_contact_collision_preserves_actual_email_and_existing_record(defaults_db):
    from app.models import ExternalRecipient
    db, defaults_id, operational_id, _ = defaults_db
    own = ExternalRecipient(tenant_id=operational_id, name='Security desk', email='desk@example.org', notes='LOCAL')
    shared = ExternalRecipient(tenant_id=defaults_id, name='Security desk', email='desk@example.org', notes='SHARED')
    db.session.add_all([own, shared])
    db.session.commit()
    local = _generic_replica(shared, 'external_recipient', operational_id)
    assert own.email == local.email == 'desk@example.org'
    assert own.id != local.id and own.notes == 'LOCAL'
    assert local.name == 'Security desk [Tenants Default]'


def test_backup_configuration_propagates_without_runtime_state(defaults_db, monkeypatch):
    from app.models import BackupJob
    from app import tenant_defaults as service
    from app.routes import _tenant_backup_local_path
    from app.timeutils import utcnow
    db, defaults_id, operational_id, _ = defaults_db
    shared = BackupJob(tenant_id=defaults_id, name='Central backup', enabled=True,
                       last_run_at=utcnow(), last_status='completed', last_message='SOURCE RUNTIME')
    db.session.add(shared)
    db.session.commit()
    local = _generic_replica(shared, 'backup_job', operational_id)
    assert local.enabled is True and local.last_run_at is None
    assert local.last_status == 'never' and local.last_message == ''
    assert local.local_path == _tenant_backup_local_path(operational_id)
    assert local.local_path != _tenant_backup_local_path(defaults_id)

    def unexpected_sync(*args, **kwargs):
        raise AssertionError('Runtime status must not publish configuration')

    monkeypatch.setattr(service, 'sync_defaults_configuration', unexpected_sync)
    local.last_status = 'completed'
    local.last_message = 'LOCAL RUNTIME'
    db.session.commit()
    assert shared.last_message == 'SOURCE RUNTIME'


def test_extended_portable_configuration_remaps_cross_model_ids(defaults_db):
    from app.models import ConfigLabel, NotificationType, NotificationTemplate, IncidentTemplate
    from app.tenant_defaults import export_configuration, import_configuration
    db, defaults_id, operational_id, _ = defaults_db
    severity = ConfigLabel(tenant_id=operational_id, kind='severity', value='Local severity')
    action = ConfigLabel(tenant_id=operational_id, kind='action_label', value='Local action')
    notification = NotificationType(tenant_id=operational_id, code='custom', label='Custom notice')
    db.session.add_all([severity, action, notification])
    db.session.flush()
    template = NotificationTemplate(tenant_id=operational_id, kind='custom', name='Template', action_label_id=action.id)
    incident_template = IncidentTemplate(tenant_id=operational_id, name='Blueprint', severity_id=severity.id)
    db.session.add_all([template, incident_template])
    db.session.commit()
    payload = export_configuration(operational_id, include_extended=True)
    selected = next(item for item in payload['items'] if item['type'] == 'notification_template')
    assert isinstance(selected['data']['action_label_id'], str)
    assert uuid.UUID(selected['data']['action_label_id'])
    assert uuid.UUID(selected['data']['kind'])
    result = import_configuration(payload, defaults_id)
    db.session.commit()
    target = db.session.get(NotificationTemplate, result['items'][selected['key']]['id'])
    assert target.tenant_id == defaults_id
    assert target.action_label_id == result['items'][selected['data']['action_label_id']]['id']
    assert target.action_label_id != action.id
    assert target.kind == result['items'][selected['data']['kind']]['code']
    assert import_configuration(payload, defaults_id)['updated'] == 0


def test_backup_secret_redaction_preserves_existing_imported_secret(defaults_db):
    from app.models import BackupJob
    from app.tenant_defaults import export_configuration, import_configuration
    from app.routes import encrypt_backup_secret, decrypt_backup_secret
    db, defaults_id, operational_id, _ = defaults_db
    original = BackupJob(tenant_id=operational_id, name='Backup', destination='s3',
                         s3_secret_key=encrypt_backup_secret('private-s3-secret'))
    db.session.add(original)
    db.session.commit()
    with_secret = export_configuration(operational_id, include_extended=True, include_secrets=True)
    result = import_configuration(with_secret, defaults_id)
    db.session.commit()
    item = next(item for item in with_secret['items'] if item['type'] == 'backup_job')
    imported = db.session.get(BackupJob, result['items'][item['key']]['id'])
    assert imported.s3_secret_key.startswith('enc:v1:')
    without_secret = export_configuration(operational_id, include_extended=True)
    assert 'private-s3-secret' not in json.dumps(without_secret)
    import_configuration(without_secret, defaults_id)
    db.session.commit()
    assert decrypt_backup_secret(imported.s3_secret_key) == 'private-s3-secret'


def test_extended_import_rejects_missing_document_before_writing(defaults_db):
    from app.models import NotificationType, NotificationTemplate
    from app.tenant_defaults import CONFIGURATION_FORMAT, import_configuration
    _, defaults_id, _, _ = defaults_db
    type_key = str(uuid.uuid4())
    payload = {'format': CONFIGURATION_FORMAT, 'origin': str(uuid.uuid4()), 'items': [
        {'key': type_key, 'type': 'notification_type', 'data': {'code': 'notice', 'label': 'Notice'}},
        {'key': str(uuid.uuid4()), 'type': 'notification_template',
         'data': {'kind': type_key, 'name': 'Missing PDF', 'linked_form_template_name': 'missing-form'}},
    ]}
    with pytest.raises(ValueError, match='Modulo documento mancante'):
        import_configuration(payload, defaults_id)
    assert NotificationType.query.count() == NotificationTemplate.query.count() == 0


@pytest.mark.parametrize('owner', ['legacy_global', 'defaults', 'private'])
def test_shared_notification_document_owner_is_checked(defaults_db, owner):
    from app.models import NotificationType, NotificationTemplate, FormTemplateConfig, FormTemplateBinary
    db, defaults_id, operational_id, _ = defaults_db
    owner_id = {'legacy_global': None, 'defaults': defaults_id, 'private': operational_id}[owner]
    db.session.add_all([
        NotificationType(tenant_id=defaults_id, code='notice', label='Notice'),
        FormTemplateConfig(template_name='owned-document', owner_tenant_id=owner_id),
        FormTemplateBinary(template_name='owned-document', filename='owned-document.pdf',
                           pdf_data=b'%PDF-1.4\n%%EOF\n'),
    ])
    db.session.commit()
    source = NotificationTemplate(tenant_id=defaults_id, kind='notice', name='Template',
                                  linked_form_template_name='owned-document')
    db.session.add(source)
    if owner == 'private':
        with pytest.raises(ValueError, match='tenant privato'):
            db.session.commit()
        db.session.rollback()
        assert NotificationTemplate.query.count() == 0
    else:
        db.session.commit()
        assert _generic_replica(source, 'notification_template', operational_id).linked_form_template_name == 'owned-document'


def test_shared_template_rejects_label_of_wrong_kind_atomically(defaults_db):
    from app.models import NotificationType, NotificationTemplate
    db, defaults_id, _, _ = defaults_db
    severity = _publish(defaults_db, kind='severity')
    db.session.add(NotificationType(tenant_id=defaults_id, code='notice', label='Notice'))
    db.session.commit()
    db.session.add(NotificationTemplate(tenant_id=defaults_id, kind='notice', name='Wrong action',
                                        action_label_id=severity.id))
    with pytest.raises(ValueError, match='label di tipo errato'):
        db.session.commit()
    db.session.rollback()
    assert NotificationTemplate.query.count() == 0


def test_consequence_rules_inherit_defaults_and_keep_incident_tenant_scope(defaults_db):
    from types import SimpleNamespace
    from app.models import Setting
    from app.routes import tenant_execution_context
    from app.consequences import configured_consequence_rules, incident_consequence_list
    db, defaults_id, operational_id, other_id = defaults_db
    shared_rules = json.dumps([{'code': 'shared', 'text': 'Shared consequence', 'conditions': []}])
    local_rules = json.dumps([{'code': 'local', 'text': 'Private tenant consequence', 'conditions': []}])
    db.session.add_all([
        Setting(key=f'tenant:{defaults_id}:consequence_rules_json', value=shared_rules),
        Setting(key=f'tenant:{other_id}:consequence_rules_json', value=local_rules),
    ])
    db.session.commit()
    with tenant_execution_context(operational_id):
        assert configured_consequence_rules()[0]['text'] == 'Shared consequence'
        other_incident = SimpleNamespace(tenant_id=other_id, actions=[])
        assert incident_consequence_list(other_incident) == ['Private tenant consequence']
    with tenant_execution_context(other_id):
        assert configured_consequence_rules()[0]['text'] == 'Private tenant consequence'
        inherited_incident = SimpleNamespace(tenant_id=operational_id, actions=[])
        assert incident_consequence_list(inherited_incident) == ['Shared consequence']


def test_report_settings_use_explicit_incident_tenant_and_defaults(defaults_db):
    from app.models import Setting
    from app.routes import tenant_execution_context
    from app.reports import _setting_value
    db, defaults_id, operational_id, other_id = defaults_db
    db.session.add_all([
        Setting(key='security_owner_name', value='Legacy owner'),
        Setting(key=f'tenant:{defaults_id}:security_owner_name', value='Shared owner'),
        Setting(key=f'tenant:{other_id}:security_owner_name', value='Private owner'),
    ])
    db.session.commit()
    with tenant_execution_context(other_id):
        assert _setting_value('security_owner_name') == 'Private owner'
        assert _setting_value('security_owner_name', tenant_id=operational_id) == 'Shared owner'
    with tenant_execution_context(operational_id):
        assert _setting_value('security_owner_name', tenant_id=other_id) == 'Private owner'


@pytest.mark.parametrize('key', ['smtp_password', 'ldap_bind_password', 'sso_client_secret', 'ai_chatbot_chatgpt_api_key'])
def test_new_tenant_never_inherits_private_legacy_settings(defaults_db, key):
    from app.models import Setting, Tenant
    from app.routes import tenant_execution_context, setting_value, setting_map, store_setting_value
    db, defaults_id, operational_id, _ = defaults_db
    db.session.add_all([
        Setting(key=key, value=store_setting_value(key, 'PRIVATE-LEGACY-SECRET')),
        Setting(key='application_external_url', value='https://cir.example.org'),
    ])
    fresh = Tenant(name='fresh-defaults-consumer')
    db.session.add(fresh)
    db.session.commit()
    with tenant_execution_context(fresh.id):
        assert setting_value(key, 'unset') == 'unset'
        assert key not in setting_map()
        assert setting_value('application_external_url') == 'https://cir.example.org'
        assert setting_map()['application_external_url'] == 'https://cir.example.org'
    with tenant_execution_context(operational_id):
        assert setting_value(key) == setting_map()[key] == 'PRIVATE-LEGACY-SECRET'
    with tenant_execution_context(defaults_id):
        assert setting_value(key, 'unset') == 'unset'
        assert key not in setting_map()

    shared = Setting(key=f'tenant:{defaults_id}:{key}', value=store_setting_value(key, 'SHARED-PUBLISHED-SECRET'))
    db.session.add(shared)
    db.session.commit()
    with tenant_execution_context(fresh.id):
        assert setting_value(key) == setting_map()[key] == 'SHARED-PUBLISHED-SECRET'
    db.session.add(Setting(key=f'tenant:{fresh.id}:{key}', value=store_setting_value(key, 'LOCAL-OVERRIDE')))
    shared.value = store_setting_value(key, 'UPDATED-SHARED-SECRET')
    db.session.commit()
    with tenant_execution_context(fresh.id):
        assert setting_value(key) == setting_map()[key] == 'LOCAL-OVERRIDE'
    with tenant_execution_context(defaults_id):
        assert setting_value(key) == setting_map()[key] == 'UPDATED-SHARED-SECRET'


def test_shared_notification_rejects_ambiguous_tagged_legacy_document(defaults_db):
    from app.models import NotificationType, NotificationTemplate, FormTemplateConfig, FormTemplateBinary
    db, defaults_id, operational_id, _ = defaults_db
    db.session.add_all([
        NotificationType(tenant_id=defaults_id, code='csirt', label='Shared CSIRT'),
        NotificationType(tenant_id=operational_id, code='csirt', label='Private CSIRT'),
        FormTemplateConfig(template_name='legacy-tagged', notification_tags='csirt'),
        FormTemplateBinary(template_name='legacy-tagged', filename='legacy-tagged.pdf',
                           pdf_data=b'%PDF-1.4\n%%EOF\n'),
    ])
    db.session.commit()
    db.session.add(NotificationTemplate(tenant_id=defaults_id, kind='csirt', name='Shared notice',
                                        linked_form_template_name='legacy-tagged'))
    with pytest.raises(ValueError, match='Importare/copiare il documento'):
        db.session.commit()
    db.session.rollback()
    assert NotificationTemplate.query.count() == 0


def test_existing_tenant_category_is_remapped_not_replicated(defaults_db):
    """Publishing SPAM reuses the tenant category, with its original ID."""
    from app.models import ConfigLabel, db
    from app.routes import incident_category_choices
    from app.tenant_defaults import inherited_configuration_record, sync_defaults_configuration
    from app.tenant_defaults_models import TenantDefaultReplica, TenantDefaultSource
    db, defaults_id, operational_id, other_id = defaults_db
    local = ConfigLabel(tenant_id=operational_id, kind='category', value='SPAM',
                        description='Locally curated procedure')
    db.session.add(local)
    db.session.commit()
    local_id = local.id
    published = _publish(defaults_db, kind='category', value='SPAM')
    shared = TenantDefaultSource.query.filter_by(source_type='config_label',
                                                 source_id=published.id).one()
    replica = TenantDefaultReplica.query.filter_by(source_id=shared.id,
                                                   tenant_id=operational_id).one()
    assert replica.local_id == local_id
    assert inherited_configuration_record(local) is None
    assert ConfigLabel.query.filter_by(tenant_id=operational_id, kind='category').count() == 1
    assert len(incident_category_choices(operational_id)) == 1
    assert incident_category_choices(operational_id)[0].ui_choice_name == 'SPAM'
    assert 'Tenants Default' in incident_category_choices(operational_id)[0].ui_choice_origin
    assert len(incident_category_choices(other_id)) == 1  # new tenant receives replica
    published.description = 'Shared text, not an override'
    db.session.commit()
    assert db.session.get(ConfigLabel, local_id).description == 'Locally curated procedure'
    sync_defaults_configuration()
    db.session.commit()
    assert ConfigLabel.query.filter_by(tenant_id=operational_id, kind='category').count() == 1
    assert TenantDefaultReplica.query.filter_by(source_id=shared.id,
                                                tenant_id=operational_id).one().local_id == local_id
    # The exported archive must validate the local-ownership marker before
    # any destructive Full Import begins.
    from app.routes import _export_tables_payload
    from app.tenant_defaults_archive import validate_defaults_archive_tables
    assert validate_defaults_archive_tables(_export_tables_payload()) is True
    db.session.delete(published)
    db.session.commit()
    assert db.session.get(ConfigLabel, local_id) is not None  # never delete local
    assert db.session.get(ConfigLabel, local_id).description == 'Locally curated procedure'


def test_incident_category_picker_shows_inherited_origin_when_no_local_override(defaults_db):
    from app.routes import incident_category_choices
    _, _, operational_id, _ = defaults_db
    published = _publish(defaults_db, kind='category', value='SPAM')
    inherited = _replica(published, operational_id)
    choices = incident_category_choices(operational_id)
    assert len(choices) == 1
    assert choices[0].id == inherited.id
    assert choices[0].ui_choice_name == 'SPAM'
    assert 'Tenants Default' in choices[0].ui_choice_origin


def test_incident_category_picker_uses_inherited_workflow_if_local_has_none(defaults_db):
    """Do not hide the operational workflow behind an unconfigured local alias."""
    from app.models import ConfigLabel, IncidentWorkflowStep, db
    from app.routes import incident_category_choices
    _, _, operational_id, _ = defaults_db
    local = ConfigLabel(tenant_id=operational_id, kind='category', value='SPAM')
    action = ConfigLabel(tenant_id=operational_id, kind='action_label', value='Triage')
    db.session.add_all([local, action]);db.session.commit()
    published = _publish(defaults_db, kind='category', value='SPAM')
    inherited = _replica(published, operational_id)
    assert inherited.id == local.id  # workflow uses original tenant category
    db.session.add(IncidentWorkflowStep(tenant_id=operational_id, category_id=inherited.id,
                                        action_label_id=action.id, position=1, description='Analisi'))
    db.session.commit()
    choices = incident_category_choices(operational_id)
    assert len(choices) == 1
    assert choices[0].id == inherited.id
    assert choices[0].ui_choice_name == 'SPAM'


def test_old_unreferenced_suffix_replica_is_reconciled_to_existing_category(defaults_db):
    """RC56-era duplicate is retired only when its ID is unused."""
    from app.models import ConfigLabel, db
    from app.tenant_defaults import sync_defaults_configuration
    from app.tenant_defaults_models import TenantDefaultReplica, TenantDefaultSource
    db, _, operational_id, _ = defaults_db
    shared = _publish(defaults_db, kind='category', value='SPAM')
    source = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=shared.id).one()
    inherited = _replica(shared, operational_id)
    stale_id = inherited.id
    db.session.info['cir_defaults_suspended'] = True
    try:
        inherited.value = 'SPAM [Tenants Default]'
        local = ConfigLabel(tenant_id=operational_id, kind='category', value='SPAM')
        db.session.add(local)
        db.session.commit()
    finally:
        db.session.info.pop('cir_defaults_suspended', None)
    sync_defaults_configuration()
    db.session.commit()
    replica = TenantDefaultReplica.query.filter_by(source_id=source.id, tenant_id=operational_id).one()
    assert replica.local_id == local.id
    assert db.session.get(ConfigLabel, stale_id) is None
    assert ConfigLabel.query.filter_by(tenant_id=operational_id, kind='category').count() == 1


def test_old_used_suffix_replica_is_not_deleted_while_incidents_refer_to_it(defaults_db):
    """Historical categories are retained if an incident still references them."""
    from app.models import ConfigLabel, Incident, db
    from app.tenant_defaults import sync_defaults_configuration
    from app.routes import incident_category_choices
    from app.timeutils import utcnow
    db, _, operational_id, _ = defaults_db
    shared = _publish(defaults_db, kind='category', value='SPAM')
    inherited = _replica(shared, operational_id)
    stale_id = inherited.id
    db.session.info['cir_defaults_suspended'] = True
    try:
        inherited.value = 'SPAM [Tenants Default]'
        local = ConfigLabel(tenant_id=operational_id, kind='category', value='SPAM')
        incident = Incident(tenant_id=operational_id, name='Historical SPAM incident', reference='TEST-LEGACY-SPAM',
                            status='aperto', start_date=utcnow().date())
        incident.categories.append(inherited)
        db.session.add_all([local, incident])
        db.session.commit()
    finally:
        db.session.info.pop('cir_defaults_suspended', None)
    sync_defaults_configuration()
    db.session.commit()
    assert db.session.get(ConfigLabel, stale_id) is not None
    assert any(label.id == stale_id for label in db.session.get(Incident, incident.id).categories)
    assert len(incident_category_choices(operational_id)) == 1


def test_legacy_unmapped_suffix_does_not_double_incident_category_choices(defaults_db):
    """An old export can lack source mappings, but must keep historic IDs."""
    from app.models import ConfigLabel, db
    from app.routes import incident_category_choices
    _, _, tenant_id, _ = defaults_db
    local = ConfigLabel(tenant_id=tenant_id, kind='category', value='SPAM', group='local')
    orphan = ConfigLabel(tenant_id=tenant_id, kind='category', value='SPAM [Tenants Default]', group='legacy')
    db.session.add_all([local, orphan])
    db.session.commit()
    existing_ids = {local.id, orphan.id}
    selected = incident_category_choices(tenant_id)
    assert len(selected) == 1
    assert selected[0].id == local.id
    assert selected[0].ui_choice_name == 'SPAM'
    assert {x.id for x in ConfigLabel.query.filter_by(tenant_id=tenant_id, kind='category')} == existing_ids
