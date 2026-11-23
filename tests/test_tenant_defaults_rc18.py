"""RC18 seed, portable shared provenance, anonymous restore and deletion guards."""
import io
import json
import tarfile
import uuid

import pytest

from test_tenant_defaults_bundle import bundle_apps
from test_tenant_defaults_core import defaults_db


def _ordinary_configuration(tenant_id, private_tenant_id):
    from pypdf import PdfWriter
    from app.models import (db, ConfigLabel, NotificationType, NotificationTemplate,
        FormTemplateConfig, FormTemplateBinary, IncidentWorkflowStep, IncidentTemplate,
        Person, User, Incident, Setting, ExternalRecipient)
    from app.routes import store_setting_value
    writer, output = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    severity = ConfigLabel(tenant_id=tenant_id, kind='severity', value='Source severity')
    action = ConfigLabel(tenant_id=tenant_id, kind='action_label', value='Source action')
    category = ConfigLabel(tenant_id=tenant_id, kind='category', value='Source category')
    notice = NotificationType(tenant_id=tenant_id, code='source_notice', label='Source notice')
    person = Person(tenant_id=tenant_id, name='Private Personnel', email='person@example.test')
    admin = User(username='admin', role='superuser', auth_provider='local', tenant_id=tenant_id,
                 name='Private Administrator', email='private@example.test')
    db.session.add_all([severity, action, category, notice, person, admin])
    db.session.flush()
    template = IncidentTemplate(tenant_id=tenant_id, name='Seed incident model',
        severity_id=severity.id, category_ids=str(category.id), people_ids=str(person.id))
    db.session.add_all([
        template,
        FormTemplateConfig(template_name='seed_form', font_size=10, notification_tags=notice.code),
        FormTemplateBinary(template_name='seed_form', filename='seed_form.pdf', pdf_data=output.getvalue()),
        NotificationTemplate(tenant_id=tenant_id, kind=notice.code, name='Seed notification',
            action_label_id=action.id, linked_form_template_name='seed_form',
            subject='Reusable notice', body='Private Personnel SOURCE-SEED-SECRET',
            recipient_source='manual', recipient_value='person@example.test'),
        IncidentWorkflowStep(tenant_id=tenant_id, category_id=category.id, action_label_id=action.id,
            position=1, description='Reusable source workflow', requires_notification=True,
            required_notification_type=notice.code, document_generation_enabled=True,
            document_template_name='seed_form'),
        ExternalRecipient(tenant_id=tenant_id, name='Private Personnel', email='person@example.test'),
        Incident(tenant_id=tenant_id, name='PRIVATE OPERATIONAL INCIDENT', reference='PRIVATE-1',
                 severity_id=severity.id, creator_id=admin.id),
        Setting(key='smtp_password', value=store_setting_value('smtp_password', 'SOURCE-SEED-SECRET')),
        Setting(key=f'tenant:{private_tenant_id}:smtp_password', value='EXCLUDED-OTHER-TENANT'),
        Setting(key=f'tenant:{tenant_id}:smtp_host', value='source-mail.example.test'),
    ])
    db.session.flush()
    db.session.add(Setting(key=f'tenant:{tenant_id}:bootstrap_config_json',
                           value=json.dumps({'incident_template_id': template.id})))
    db.session.commit()
    return {'severity': severity.id, 'category': category.id, 'action': action.id,
            'person': person.id, 'template': template.id}


def test_absent_defaults_is_seeded_once_without_copying_operational_records(bundle_apps):
    from app.models import (db, Tenant, ConfigLabel, User, Incident, Person, IncidentTemplate,
                            Setting, NotificationTemplate, FormTemplateConfig, WorkflowCatalogEntry)
    from app.routes import decrypt_setting_value
    from app.tenant_defaults import ensure_defaults_tenant, sync_defaults_configuration
    with bundle_apps('seed') as (_app, empty, ordinary, private):
        db.session.delete(empty)
        db.session.commit()
        original = _ordinary_configuration(ordinary.id, private.id)
        source = ensure_defaults_tenant(seed_from_default=True)
        db.session.commit()
        source_id = source.id
        assert source_id != ordinary.id
        assert ConfigLabel.query.filter_by(tenant_id=source_id).count() == 3
        assert not User.query.filter_by(tenant_id=source_id).first()
        assert not Incident.query.filter_by(tenant_id=source_id).first()
        assert not Person.query.filter_by(tenant_id=source_id).first()
        assert db.session.get(IncidentTemplate, original['template']).people_ids == str(original['person'])
        assert IncidentTemplate.query.filter_by(tenant_id=source_id).one().people_ids == ''
        password = db.session.get(Setting, f'tenant:{source_id}:smtp_password')
        assert decrypt_setting_value('smtp_password', password.value) == 'SOURCE-SEED-SECRET'
        assert 'EXCLUDED-OTHER-TENANT' not in '\n'.join(row.value or '' for row in Setting.query.filter(Setting.key.startswith(f'tenant:{source_id}:')))
        template = NotificationTemplate.query.filter_by(tenant_id=source_id).one()
        assert template.linked_form_template_name != 'seed_form'
        assert FormTemplateConfig.query.filter_by(template_name=template.linked_form_template_name).one().owner_tenant_id == source_id
        assert WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source_id).count() == 1
        marker = json.loads(db.session.get(Setting, '__cir_defaults_initial_seed').value)
        assert marker['templates_with_personnel_links_removed'] == 1
        before = (ConfigLabel.query.count(), WorkflowCatalogEntry.query.count())
        assert ensure_defaults_tenant(seed_from_default=True).id == source_id
        db.session.commit()
        assert (ConfigLabel.query.count(), WorkflowCatalogEntry.query.count()) == before
        new = Tenant(name='post-seed-tenant')
        db.session.add(new)
        sync_defaults_configuration()
        db.session.commit()
        assert ConfigLabel.query.filter_by(tenant_id=new.id).count() == 3
        assert db.session.get(ConfigLabel, original['severity']).value == 'Source severity'


def test_preexisting_empty_defaults_is_not_populated_or_overwritten(bundle_apps):
    from app.models import db, ConfigLabel, Setting, WorkflowCatalogEntry
    from app.tenant_defaults import ensure_defaults_tenant
    with bundle_apps('preexisting') as (_app, source, ordinary, private):
        _ordinary_configuration(ordinary.id, private.id)
        assert ensure_defaults_tenant(seed_from_default=True).id == source.id
        db.session.commit()
        assert ConfigLabel.query.filter_by(tenant_id=source.id).count() == 0
        assert WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source.id).count() == 0
        assert db.session.get(Setting, '__cir_defaults_initial_seed') is None


def test_seed_failure_rolls_back_new_source_and_metadata(bundle_apps):
    from app.models import db, Tenant, Setting, FormTemplateBinary, TenantDefaultSource
    from app.tenant_defaults import ensure_defaults_tenant
    with bundle_apps('seed-failure') as (_app, source, ordinary, private):
        db.session.delete(source)
        db.session.commit()
        _ordinary_configuration(ordinary.id, private.id)
        FormTemplateBinary.query.filter_by(template_name='seed_form').delete()
        db.session.commit()
        with pytest.raises(ValueError, match='PDF non disponibile'):
            ensure_defaults_tenant(seed_from_default=True)
        db.session.rollback()
        assert Tenant.query.filter_by(is_system_defaults=True).count() == 0
        assert TenantDefaultSource.query.count() == 0
        assert db.session.get(Setting, '__cir_defaults_initial_seed') is None


def test_bundle_rebinds_catalog_source_uuids_to_exact_destination_replicas(bundle_apps):
    from app.models import (db, TenantDefaultSource, TenantDefaultReplica, ConfigLabel,
                            IncidentWorkflowStep, WorkflowCatalogEntry)
    from app.tenant_defaults import ensure_defaults_tenant
    from app.tenant_defaults_bundle import export_defaults_bundle, import_defaults_bundle
    from app.workflow_catalog import import_catalog_workflow
    with bundle_apps('portable-source') as (_app, source, ordinary, private):
        db.session.delete(source)
        db.session.commit()
        _ordinary_configuration(ordinary.id, private.id)
        source = ensure_defaults_tenant(seed_from_default=True)
        payload = export_defaults_bundle(include_secrets=True)
        db.session.commit()
        old_sources = set(payload['configuration_sources'])
        assert old_sources
    with bundle_apps('portable-target') as (_app, source, ordinary, private):
        collision = ConfigLabel(tenant_id=ordinary.id, kind='action_label', value='Source action')
        db.session.add(collision)
        db.session.commit()
        imported = import_defaults_bundle(payload)
        db.session.commit()
        assert imported['catalog'] == 1
        entry = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source.id).one()
        content = json.loads(entry.payload_json)
        action = next(row for row in content['dependencies']['labels'] if row['kind'] == 'action_label')
        assert action['shared_source_id'] not in old_sources
        published = db.session.get(TenantDefaultSource, action['shared_source_id'])
        replica = TenantDefaultReplica.query.filter_by(source_id=published.id, tenant_id=ordinary.id).one()
        assert replica.local_id != collision.id
        import_catalog_workflow(entry.id, ordinary.id, copy_name='First exact replica copy')
        import_catalog_workflow(entry.id, ordinary.id, copy_name='Second exact replica copy')
        db.session.commit()
        installed = IncidentWorkflowStep.query.filter_by(tenant_id=ordinary.id, action_label_id=replica.local_id).all()
        assert len(installed) == 2
        assert collision.value == 'Source action'


def test_bootstrap_retains_source_catalog_and_redacts_secret_snapshots(bundle_apps):
    from app.models import db, WorkflowCatalogEntry
    from app.tenant_defaults import ensure_defaults_tenant
    from app.tenant_defaults_bootstrap import bootstrap_configuration_snapshot
    from app.tenant_defaults_archive import validate_defaults_archive_tables
    from app.workflow_lifecycle import set_catalog_workflow_status
    with bundle_apps('anonymous') as (_app, source, ordinary, private):
        db.session.delete(source)
        db.session.commit()
        _ordinary_configuration(ordinary.id, private.id)
        source = ensure_defaults_tenant(seed_from_default=True)
        entry = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source.id).one()
        set_catalog_workflow_status(entry.id, 'obsolete')
        db.session.commit()
        tables, forms, included = bootstrap_configuration_snapshot(ordinary.id)
        assert included == (ordinary.id, source.id)
        assert {row['name'] for row in tables['tenants']} == {'default', 'Tenants Default'}
        assert tables['tenant_default_sources'] and tables['tenant_default_replicas']
        assert tables['workflow_catalog_entries'][0]['status'] == 'obsolete'
        assert tables['form_template_binaries'] and forms
        assert not tables['workflow_obsolescence_notices']
        assert not tables['incidents'] and not tables['people']
        assert all(row['people_ids'] == '' for row in tables['incident_templates'])
        assert all(not row['enabled'] and row['s3_secret_key'] == '' for row in tables['backup_jobs'])
        assert len(tables['users']) == 1
        assert tables['users'][0]['email'] == 'admin@example.local'
        assert tables['users'][0]['password_hash'] is None
        raw = json.dumps(tables, ensure_ascii=False)
        for secret in ('SOURCE-SEED-SECRET', 'EXCLUDED-OTHER-TENANT', 'Private Personnel',
                       'Private Administrator', 'person@example.test', 'PRIVATE OPERATIONAL INCIDENT'):
            assert secret not in raw
        assert validate_defaults_archive_tables(tables) is True


def test_portable_bundle_keeps_obsolete_catalog_and_source_draft_state(bundle_apps):
    from app.models import db, WorkflowCatalogEntry, TenantWorkflow
    from app.tenant_defaults import ensure_defaults_tenant
    from app.tenant_defaults_bundle import export_defaults_bundle, import_defaults_bundle
    from app.workflow_catalog import import_catalog_workflow
    from app.workflow_lifecycle import set_catalog_workflow_status
    with bundle_apps('obsolete-source') as (_app, source, ordinary, private):
        db.session.delete(source)
        db.session.commit()
        _ordinary_configuration(ordinary.id, private.id)
        source = ensure_defaults_tenant(seed_from_default=True)
        entry = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source.id).one()
        set_catalog_workflow_status(entry.id, 'obsolete')
        payload = export_defaults_bundle()
        db.session.commit()
    with bundle_apps('obsolete-target') as (_app, source, ordinary, _private):
        import_defaults_bundle(payload)
        db.session.commit()
        entry = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source.id).one()
        assert entry.status == 'obsolete'
        state = TenantWorkflow.query.filter_by(tenant_id=source.id, scope_key=entry.source_scope_key).one()
        assert state.status == 'obsolete'
        with pytest.raises(ValueError, match='obsoleto|obsoleta'):
            import_catalog_workflow(entry.id, ordinary.id)


@pytest.mark.parametrize('legacy_incident', [False, True])
def test_local_configuration_deletion_detects_default_and_legacy_incident_usage(defaults_db, legacy_incident):
    from app.models import db, ConfigLabel, Incident, IncidentWorkflowStep
    from app.configuration_usage import configuration_incident_usage, workflow_incident_usage
    _db, _source, ordinary, private = defaults_db
    severity = ConfigLabel(tenant_id=ordinary, kind='severity', value='Used severity')
    action = ConfigLabel(tenant_id=None if legacy_incident else ordinary, kind='action_label', value='Used action')
    db.session.add_all([severity, action])
    db.session.flush()
    step = IncidentWorkflowStep(tenant_id=None if legacy_incident else ordinary, action_label_id=action.id,
        category_id=None, position=1, conditions=f'severity:{severity.id}')
    incident = Incident(tenant_id=None if legacy_incident else ordinary, name='Old incident', reference='OLD-1', severity_id=severity.id)
    db.session.add_all([step, incident])
    db.session.commit()
    assert configuration_incident_usage('config_label', severity)
    assert configuration_incident_usage('config_label', action)
    assert workflow_incident_usage(ordinary, None)
    assert not workflow_incident_usage(private, None)


def test_workflow_deletion_usage_respects_explicit_first_category(defaults_db):
    from app.models import db, ConfigLabel, Incident, IncidentWorkflowStep
    from app.configuration_usage import workflow_incident_usage
    _db, _source, ordinary, _private = defaults_db
    first = ConfigLabel(tenant_id=ordinary, kind='category', value='First inserted')
    effective = ConfigLabel(tenant_id=ordinary, kind='category', value='First selected')
    action = ConfigLabel(tenant_id=ordinary, kind='action_label', value='Action')
    db.session.add_all([first, effective, action])
    db.session.flush()
    for category in (first, effective):
        db.session.add(IncidentWorkflowStep(tenant_id=ordinary, category_id=category.id, action_label_id=action.id, position=1))
    incident = Incident(tenant_id=ordinary, name='Ordered incident', reference='ORDER', category_order=f'{effective.id},{first.id}')
    incident.categories = [first, effective]
    db.session.add(incident)
    db.session.commit()
    assert not workflow_incident_usage(ordinary, first.id)
    assert workflow_incident_usage(ordinary, effective.id)


def test_recipient_and_form_deletion_guards_cover_legacy_aliases(defaults_db):
    from app.models import db, Incident, Document, ExternalRecipient
    from app.configuration_usage import configuration_incident_usage, form_template_incident_usage
    from app.tenant_defaults import configuration_reference_reason
    _db, _source, ordinary, _private = defaults_db
    recipient = ExternalRecipient(tenant_id=ordinary, name='Contact', email='contact@example.test')
    incident = Incident(tenant_id=None, name='Legacy incident', reference='LEGACY',
                        recipient_email='Contact Name <CONTACT@example.test>, other@example.test')
    db.session.add_all([recipient, incident])
    db.session.flush()
    db.session.add(Document(incident_id=incident.id, filename='report.pdf', generated_template_name='legacy-form.pdf'))
    db.session.commit()
    assert configuration_incident_usage('external_recipient', recipient)
    assert configuration_reference_reason('external_recipient', recipient)
    assert form_template_incident_usage('legacy-form', ordinary)
    from types import SimpleNamespace
    assert configuration_incident_usage('form_template', SimpleNamespace(template_name='legacy-form'))


def test_tenant_scoped_lifecycle_restore_keeps_unknown_origin_obsolete(defaults_db):
    from app.models import db, ConfigLabel
    from app.tenant_defaults_scoped import restore_scoped_workflow_states
    from app.workflow_lifecycle import get_workflow_state
    _db, _source, ordinary, _private = defaults_db
    category = ConfigLabel(tenant_id=ordinary, kind='category', value='Imported workflow')
    db.session.add(category)
    db.session.flush()
    restore_scoped_workflow_states([{'public_id': str(uuid.uuid4()), 'category_id': 9876,
        'source_entry_id': None, 'source_entry_public_id': str(uuid.uuid4()),
        'status': 'current', 'name': 'Unknown source copy', 'personalized': True}],
        ordinary, {9876: category.id}, {'public_ids': set(), 'scopes': set()})
    db.session.commit()
    state = get_workflow_state(ordinary, category.id)
    assert state.status == 'obsolete'
    assert state.source_entry_id is None
    assert state.personalized is True


def test_legacy_tenant_restore_does_not_reactivate_an_obsolete_scope(defaults_db):
    from app.models import db, ConfigLabel, IncidentWorkflowStep
    from app.tenant_defaults_scoped import capture_scoped_obsolete_workflows, restore_scoped_workflow_states
    from app.workflow_lifecycle import ensure_workflow_state, get_workflow_state
    _db, _source, ordinary, _private = defaults_db
    label = ConfigLabel(tenant_id=ordinary, kind='action_label', value='Retired action')
    db.session.add(label)
    db.session.flush()
    db.session.add(IncidentWorkflowStep(tenant_id=ordinary, category_id=None, action_label_id=label.id, position=1))
    state = ensure_workflow_state(ordinary)
    state.status = 'obsolete'
    db.session.commit()
    previous = capture_scoped_obsolete_workflows(ordinary)
    db.session.delete(state)
    db.session.flush()
    restore_scoped_workflow_states([], ordinary, {}, previous)
    db.session.commit()
    assert get_workflow_state(ordinary).status == 'obsolete'


def _real_app(monkeypatch, root):
    root.mkdir()
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(root / 'app.db'))
    for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR', 'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR'):
        monkeypatch.setenv(key, str(root / key.lower()))
    monkeypatch.setenv('SECRET_KEY', 'R' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'BootstrapDestination123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _superuser_client(app):
    from app.models import User, Tenant
    with app.app_context():
        admin_id = User.query.filter_by(username='admin', auth_provider='local').one().id
        default_id = Tenant.query.filter_by(name='default').one().id
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=str(admin_id), _fresh=True, active_tenant_id=default_id,
                       active_tenant_scope_enabled=True)
    return client


@pytest.mark.parametrize('anonymous', [False, True])
def test_full_and_bootstrap_restore_shared_configuration_into_separate_instance(monkeypatch, tmp_path, anonymous):
    from app.models import (db, Tenant, ConfigLabel, Setting, IncidentWorkflowStep,
        WorkflowCatalogEntry, TenantDefaultSource, TenantDefaultReplica, TenantWorkflow, User)
    from app.routes import store_setting_value, decrypt_setting_value
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    from app.workflow_lifecycle import set_catalog_workflow_status
    source_app = _real_app(monkeypatch, tmp_path / 'real-source')
    with source_app.app_context():
        shared = Tenant.query.filter_by(is_system_defaults=True).one()
        ordinary = Tenant.query.filter_by(name='default').one()
        label = ConfigLabel(tenant_id=shared.id, kind='action_label', value='RC18 archive action')
        category = ConfigLabel(tenant_id=shared.id, kind='category', value='RC18 archive category')
        db.session.add_all([label, category])
        db.session.flush()
        db.session.add(IncidentWorkflowStep(tenant_id=shared.id, category_id=category.id,
            action_label_id=label.id, position=1, description='RC18 preserved draft'))
        db.session.merge(Setting(key=f'tenant:{shared.id}:smtp_password',
                                value=store_setting_value('smtp_password', 'RC18-ARCHIVE-SECRET')))
        db.session.commit()
        source_uuid = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=label.id).one().id
        entry = save_catalog_workflow(build_catalog_workflow_payload(shared.id, category.id), 'RC18 archive catalog')
        db.session.flush()
        import_catalog_workflow(entry.id, ordinary.id, copy_name='RC18 preserved tenant copy')
        set_catalog_workflow_status(entry.id, 'obsolete')
        db.session.commit()
        catalog_uuid = entry.public_id
    response = _superuser_client(source_app).get('/export/full', query_string={'mode': 'bootstrap'} if anonymous else {})
    assert response.status_code == 200
    archive_bytes = response.data
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        manifest = json.load(archive.extractfile('export.json'))
        assert any(row['is_system_defaults'] for row in manifest['tables']['tenants'])
        assert manifest['tables']['tenant_workflows']
        if anonymous:
            assert not manifest['tables']['workflow_obsolescence_notices']
            assert 'RC18-ARCHIVE-SECRET' not in json.dumps(manifest)
    target_app = _real_app(monkeypatch, tmp_path / 'real-target')
    result = _superuser_client(target_app).post('/import/full', data={
        'file': (io.BytesIO(archive_bytes), 'rc18-cross-instance.tar.gz'),
    })
    assert result.status_code == 302, result.get_data(as_text=True)
    with target_app.app_context():
        entry = WorkflowCatalogEntry.query.filter_by(public_id=catalog_uuid).one()
        assert entry.status == 'obsolete'
        states = TenantWorkflow.query.filter_by(source_entry_id=entry.id).all()
        assert states and all(state.status == 'obsolete' for state in states)
        source = db.session.get(TenantDefaultSource, source_uuid)
        assert source is not None
        shared = Tenant.query.filter_by(is_system_defaults=True).one()
        secret = db.session.get(Setting, f'tenant:{shared.id}:smtp_password').value
        assert decrypt_setting_value('smtp_password', secret) == ('' if anonymous else 'RC18-ARCHIVE-SECRET')
        row = db.session.get(ConfigLabel, source.source_id)
        row.description = 'Live after cross-instance restore'
        db.session.commit()
        assert all(db.session.get(ConfigLabel, replica.local_id).description == row.description
                   for replica in TenantDefaultReplica.query.filter_by(source_id=source_uuid))
        if anonymous:
            from app.auth import verify_password
            assert verify_password(User.query.filter_by(username='admin', auth_provider='local').one().password_hash,
                                   'BootstrapDestination123!')
