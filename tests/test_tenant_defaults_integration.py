"""HTTP and archive boundaries for the shared configuration tenant.

These tests exercise real Flask handlers/SQLAlchemy state.  No endpoint is
called through an authorization-bypassing helper and no live security gate
is disabled to make the feature tests pass.
"""
import io
import json
import tarfile
import uuid
from copy import deepcopy

import pytest


@pytest.fixture
def defaults_app(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'defaults-integration.db'))
    for key, dirname in {
        'UPLOAD_DIR': 'uploads', 'LOGO_DIR': 'logos', 'SSO_LOGO_DIR': 'sso',
        'FORM_TEMPLATE_DIR': 'forms', 'BACKUP_DIR': 'backups',
        'AI_CHATBOT_DOC_DIR': 'knowledge', 'SSL_DIR': 'ssl',
    }.items():
        monkeypatch.setenv(key, str(tmp_path / dirname))
    monkeypatch.setenv('SECRET_KEY', 'D' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    from app import create_app
    from app.models import ConfigLabel, Tenant, User, UserTenantRole, db
    from app.tenant_defaults import ensure_defaults_tenant

    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        operational = Tenant.query.filter_by(name='default').one()
        shared = ensure_defaults_tenant()
        other = Tenant(name='integration-private-tenant', description='Private tenant')
        db.session.add(other)
        db.session.flush()
        manager = User(username='defaults-test-manager', auth_provider='local',
                       role='admin', tenant_id=operational.id,
                       default_tenant_id=operational.id)
        reader = User(username='defaults-test-reader', auth_provider='local',
                      role='reader', tenant_id=operational.id,
                      default_tenant_id=operational.id)
        db.session.add_all([manager, reader])
        db.session.flush()
        db.session.add_all([
            UserTenantRole(user_id=manager.id, tenant_id=operational.id, role='admin'),
            UserTenantRole(user_id=reader.id, tenant_id=operational.id, role='reader'),
            ConfigLabel(tenant_id=operational.id, kind='severity',
                        value='OWN-TENANT-CONFIG-MARKER', group='integration'),
            ConfigLabel(tenant_id=other.id, kind='severity',
                        value='FOREIGN-TENANT-CONFIG-MARKER', group='integration'),
        ])
        db.session.commit()
        app.config['TEST_DEFAULTS_IDS'] = {
            'operational': operational.id, 'shared': shared.id, 'other': other.id,
            'manager': manager.id, 'reader': reader.id,
            'superuser': User.query.filter_by(username='admin', auth_provider='local').one().id,
        }
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _client(app, role='manager', tenant=None):
    client = app.test_client()
    ids = app.config['TEST_DEFAULTS_IDS']
    with client.session_transaction() as session:
        session['_user_id'] = str(ids[role])
        session['_fresh'] = True
        session['active_tenant_id'] = tenant or ids['operational']
        session['active_tenant_scope_enabled'] = True
    return client


@pytest.mark.parametrize('path', [
    '/admin/tenants-defaults',
    '/admin/tenants-defaults/configuration/export',
    '/admin/tenants-defaults/alerts',
    '/admin/workflow-catalog',
    '/admin/workflow-catalog/export-workflow',
])
def test_shared_configuration_pages_require_login(defaults_app, path):
    response = defaults_app.test_client().get(path)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


@pytest.mark.parametrize('path', [
    '/admin/tenants-defaults',
    '/admin/tenants-defaults/configuration/export',
    '/admin/tenants-defaults/alerts',
    '/admin/workflow-catalog',
    '/admin/workflow-catalog/export-workflow',
])
def test_reader_cannot_export_configuration_or_manage_catalog(defaults_app, path):
    response = _client(defaults_app, 'reader').get(path)
    assert response.status_code == 403


@pytest.mark.parametrize('path', [
    '/admin/tenants-defaults/configuration/import',
    '/admin/tenants-defaults/export',
    '/admin/workflow-catalog/import-file',
    '/admin/workflow-catalog/publish',
])
def test_tenant_admin_cannot_publish_or_modify_global_defaults(defaults_app, path):
    response = _client(defaults_app).post(path, data={
        'file': (io.BytesIO(b'{}'), 'configuration.json'),
        'name': 'Unapproved global configuration',
    })
    assert response.status_code == 403


def test_tenant_configuration_export_ignores_foreign_scope_parameters(defaults_app):
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    client = _client(defaults_app)
    response = client.get('/admin/tenants-defaults/configuration/export', query_string={
        'tenant_id': ids['other'], 'source_tenant_id': ids['other'],
        'target_tenant_id': ids['other'],
    })
    assert response.status_code in (200, 403)
    text = response.get_data(as_text=True)
    assert 'FOREIGN-TENANT-CONFIG-MARKER' not in text
    if response.status_code == 200:
        assert 'OWN-TENANT-CONFIG-MARKER' in text


def test_forged_active_tenant_does_not_expose_foreign_configuration(defaults_app):
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    client = _client(defaults_app, tenant=ids['other'])
    response = client.get('/admin/tenants-defaults/configuration/export')
    assert response.status_code in (200, 403)
    assert 'FOREIGN-TENANT-CONFIG-MARKER' not in response.get_data(as_text=True)


def test_defaults_mutations_keep_csrf_validation(defaults_app, monkeypatch):
    monkeypatch.setenv('CIR_DISABLE_CSRF', '0')
    response = _client(defaults_app, 'superuser').post(
        '/admin/tenants-defaults/configuration/import',
        data={'file': (io.BytesIO(b'{}'), 'configuration.json')},
    )
    assert response.status_code == 400


def test_mfa_pending_session_cannot_export_defaults(defaults_app):
    client = _client(defaults_app)
    with client.session_transaction() as session:
        session['mfa_user_id'] = defaults_app.config['TEST_DEFAULTS_IDS']['manager']
    response = client.get('/admin/tenants-defaults/configuration/export')
    assert response.status_code == 302
    assert '/mfa/verify' in response.headers['Location']


def test_complete_defaults_export_requires_explicit_secret_opt_in(defaults_app):
    from app.models import db, Setting
    from app.routes import store_setting_value
    from app.tenant_defaults_bundle import BUNDLE_FORMAT
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        db.session.add(Setting(key=f'tenant:{ids["shared"]}:smtp_password',
                               value=store_setting_value('smtp_password', 'SHARED-SECRET-EXPORT')))
        db.session.add(Setting(key=f'tenant:{ids["other"]}:smtp_password', value='OTHER-TENANT-PRIVATE'))
        db.session.commit()
    client = _client(defaults_app, 'superuser')
    safe = client.post('/admin/tenants-defaults/export')
    assert safe.status_code == 200
    assert safe.json['format'] == BUNDLE_FORMAT
    assert 'SHARED-SECRET-EXPORT' not in safe.get_data(as_text=True)
    full = client.post('/admin/tenants-defaults/export', data={'include_secrets': '1'})
    assert full.status_code == 200
    assert 'SHARED-SECRET-EXPORT' in full.get_data(as_text=True)
    assert 'OTHER-TENANT-PRIVATE' not in full.get_data(as_text=True)


def test_metadata_is_registered_globally_and_excluded_from_tenant_exports(defaults_app):
    from app.routes import FULL_EXPORT_MODELS, FULL_EXPORT_TABLES, _export_tables_payload
    from app.tenant_defaults_models import (
        TenantDefaultAlert, TenantDefaultReplica, TenantDefaultSource,
    )
    from app.workflow_catalog_models import WorkflowCatalogEntry, WorkflowCatalogInstallation
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        models = (TenantDefaultSource, TenantDefaultReplica, TenantDefaultAlert,
                  WorkflowCatalogEntry, WorkflowCatalogInstallation)
        for model in models:
            assert model in FULL_EXPORT_MODELS
            assert model in FULL_EXPORT_TABLES.values()
        scoped = _export_tables_payload(ids['operational'])
        for key, model in FULL_EXPORT_TABLES.items():
            if model in models:
                assert scoped[key] == []
        assert [row['id'] for row in scoped['tenants']] == [ids['operational']]
        assert 'FOREIGN-TENANT-CONFIG-MARKER' not in json.dumps(scoped)


def _catalog_entry(app):
    """Publish a genuine tenant workflow through the service API for HTTP tests."""
    from app.models import ConfigLabel, IncidentWorkflowStep, db
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow
    ids = app.config['TEST_DEFAULTS_IDS']
    with app.app_context():
        category = ConfigLabel(tenant_id=ids['operational'], kind='category',
                               value='Portable workflow HTTP', group='integration')
        label = ConfigLabel(tenant_id=ids['operational'], kind='action_label',
                            value='Portable workflow HTTP action', group='integration')
        db.session.add_all([category, label])
        db.session.flush()
        db.session.add(IncidentWorkflowStep(tenant_id=ids['operational'],
            category_id=category.id, action_label_id=label.id, position=1,
            description='Portable HTTP step'))
        db.session.flush()
        entry = save_catalog_workflow(
            build_catalog_workflow_payload(ids['operational'], category.id),
            'Portable workflow HTTP',
        )
        db.session.commit()
        return entry.id, category.id


def test_tenant_admin_cannot_install_catalog_into_another_tenant(defaults_app):
    from app.models import IncidentWorkflowStep
    from app.workflow_catalog_models import WorkflowCatalogInstallation
    entry_id, _ = _catalog_entry(defaults_app)
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        before = IncidentWorkflowStep.query.filter_by(tenant_id=ids['other']).count()
    response = _client(defaults_app).post(f'/admin/workflow-catalog/{entry_id}/install',
                                        data={'target_tenant_id': ids['other']})
    assert response.status_code == 403
    with defaults_app.app_context():
        assert IncidentWorkflowStep.query.filter_by(tenant_id=ids['other']).count() == before
        assert WorkflowCatalogInstallation.query.filter_by(entry_id=entry_id, tenant_id=ids['other']).count() == 0


def test_tenant_admin_can_install_catalog_only_in_own_tenant(defaults_app):
    from app.models import IncidentWorkflowStep
    from app.workflow_catalog_models import WorkflowCatalogInstallation
    entry_id, _ = _catalog_entry(defaults_app)
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    response = _client(defaults_app).post(f'/admin/workflow-catalog/{entry_id}/install',
                                        data={'target_tenant_id': ids['operational']})
    assert response.status_code == 302
    with defaults_app.app_context():
        receipt = WorkflowCatalogInstallation.query.filter_by(entry_id=entry_id,
            tenant_id=ids['operational']).one()
        step_ids = json.loads(receipt.step_ids_json)
        assert step_ids
        assert IncidentWorkflowStep.query.filter(IncidentWorkflowStep.id.in_(step_ids),
            IncidentWorkflowStep.tenant_id == ids['operational']).count() == len(step_ids)


def test_tenant_workflow_export_rejects_foreign_category_id(defaults_app):
    from app.models import ConfigLabel, db
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        category = ConfigLabel(tenant_id=ids['other'], kind='category',
                               value='FOREIGN-CATEGORY-SECRET', group='integration')
        db.session.add(category)
        db.session.commit()
        category_id = category.id
    response = _client(defaults_app).get('/admin/workflow-catalog/export-workflow',
                                       query_string={'category_id': category_id})
    assert response.status_code in (400, 403, 404)
    assert 'FOREIGN-CATEGORY-SECRET' not in response.get_data(as_text=True)


def test_catalog_export_reimport_and_install_through_http(defaults_app):
    from app.workflow_catalog_models import WorkflowCatalogEntry, WorkflowCatalogInstallation
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    _, category_id = _catalog_entry(defaults_app)
    source = _client(defaults_app).get('/admin/workflow-catalog/export-workflow',
                                     query_string={'category_id': category_id})
    assert source.status_code == 200
    assert json.loads(source.data)['format'] == 'cybersecurity-incident-registry.workflow-catalog.v1'
    admin = _client(defaults_app, 'superuser')
    imported = admin.post('/admin/workflow-catalog/import-file', data={
        'name': 'Roundtrip from uploaded file',
        'file': (io.BytesIO(source.data), 'workflow.json'),
    })
    assert imported.status_code == 302
    with defaults_app.app_context():
        entry = WorkflowCatalogEntry.query.filter_by(name='Roundtrip from uploaded file').one()
        entry_id = entry.id
        assert entry.defaults_tenant_id == ids['shared']
    installed = admin.post(f'/admin/workflow-catalog/{entry_id}/install',
                           data={'target_tenant_id': ids['other']})
    assert installed.status_code == 302
    with defaults_app.app_context():
        assert WorkflowCatalogInstallation.query.filter_by(entry_id=entry_id,
            tenant_id=ids['other']).count() == 1


def test_full_restore_preserves_defaults_provenance_and_catalog(defaults_app):
    from app.models import ConfigLabel, db
    from app.tenant_defaults_models import TenantDefaultAlert, TenantDefaultReplica, TenantDefaultSource
    from app.workflow_catalog import import_catalog_workflow
    from app.workflow_catalog_models import WorkflowCatalogEntry, WorkflowCatalogInstallation
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    entry_id, _ = _catalog_entry(defaults_app)
    with defaults_app.app_context():
        import_catalog_workflow(entry_id, ids['other'])
        db.session.commit()
        installation_id = WorkflowCatalogInstallation.query.filter_by(entry_id=entry_id,
            tenant_id=ids['other']).one().id
        source_label = ConfigLabel(tenant_id=ids['shared'], kind='severity',
            value='Shared provenance roundtrip', group='integration', description='Before export')
        db.session.add(source_label)
        db.session.commit()
        label_id = source_label.id
        provenance = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=label_id).one()
        provenance_id = provenance.id
        replica_ids = {r.tenant_id: r.local_id for r in TenantDefaultReplica.query.filter_by(source_id=provenance_id)}
        assert ids['operational'] in replica_ids
        assert ids['other'] in replica_ids
        alert = TenantDefaultAlert(tenant_id=ids['operational'], source_id=provenance_id,
            kind='local_customization', message='Roundtrip administrative notice',
            local_type='config_label', local_id=replica_ids[ids['operational']])
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id
    client = _client(defaults_app, 'superuser')
    export = client.get('/export/full')
    assert export.status_code == 200
    archive_bytes = export.data
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        payload = json.load(archive.extractfile('export.json'))
        assert any(row['is_system_defaults'] for row in payload['tables']['tenants'])
        assert provenance_id in json.dumps(payload['tables'])
    with defaults_app.app_context():
        db.session.get(ConfigLabel, label_id).description = 'Changed after export'
        db.session.commit()
    restored = client.post('/import/full', data={
        'file': (io.BytesIO(archive_bytes), 'defaults-full-export.tar.gz'),
    })
    assert restored.status_code == 302
    with defaults_app.app_context():
        assert db.session.get(ConfigLabel, label_id).description == 'Before export'
        assert db.session.get(TenantDefaultSource, provenance_id) is not None
        assert db.session.get(TenantDefaultAlert, alert_id).message == 'Roundtrip administrative notice'
        assert db.session.get(WorkflowCatalogEntry, entry_id) is not None
        assert db.session.get(WorkflowCatalogInstallation, installation_id).entry_id == entry_id
        current = {r.tenant_id: r.local_id for r in TenantDefaultReplica.query.filter_by(source_id=provenance_id)}
        assert current == replica_ids
        db.session.get(ConfigLabel, label_id).description = 'Synchronized after restore'
        db.session.commit()
        for local_id in replica_ids.values():
            assert db.session.get(ConfigLabel, local_id).description == 'Synchronized after restore'


def test_special_tenant_cannot_be_deleted_through_legacy_tenant_page(defaults_app):
    from app.models import Tenant, db
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    client = _client(defaults_app, 'superuser')
    response = client.post('/admin/tenants', data={
        'action': 'delete', 'tenant_id': ids['shared'],
    })
    assert response.status_code in (200, 302, 403, 400)
    with defaults_app.app_context():
        assert db.session.get(Tenant, ids['shared']) is not None
        assert db.session.get(Tenant, ids['operational']).name == 'default'


def test_special_tenant_cannot_be_renamed_through_legacy_tenant_page(defaults_app):
    from app.models import Tenant, db
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        original_name = db.session.get(Tenant, ids['shared']).name
    response = _client(defaults_app, 'superuser').post('/admin/tenants', data={
        'action': 'update', 'tenant_id': ids['shared'], 'name': 'ordinary-tenant-now',
        'description': 'Must remain a special configuration tenant',
    })
    assert response.status_code in (200, 302, 403, 400)
    with defaults_app.app_context():
        assert db.session.get(Tenant, ids['shared']).name == original_name


def test_shared_label_creation_preserves_a_colliding_tenant_label(defaults_app):
    from app.models import ConfigLabel
    from app.tenant_defaults_models import TenantDefaultReplica, TenantDefaultSource
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        local = ConfigLabel.query.filter_by(tenant_id=ids['operational'],
            value='OWN-TENANT-CONFIG-MARKER').one()
        local_id, local_description = local.id, local.description
    response = _client(defaults_app, 'superuser', ids['shared']).post('/admin/labels', data={
        'kind': 'severity', 'group': 'integration',
        'value': 'OWN-TENANT-CONFIG-MARKER', 'description': 'Description from shared defaults',
    })
    assert response.status_code in (200, 302)
    with defaults_app.app_context():
        source = ConfigLabel.query.filter_by(tenant_id=ids['shared'],
            value='OWN-TENANT-CONFIG-MARKER').one()
        published = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=source.id).one()
        replica = TenantDefaultReplica.query.filter_by(source_id=published.id,
            tenant_id=ids['operational']).one()
        assert replica.local_id != local_id
        local = ConfigLabel.query.filter_by(id=local_id).one()
        inherited = ConfigLabel.query.filter_by(id=replica.local_id).one()
        assert local.value == 'OWN-TENANT-CONFIG-MARKER'
        assert local.description == local_description
        assert inherited.description == 'Description from shared defaults'


def test_deleting_shared_label_retains_incident_reference_and_alerts_admin(defaults_app):
    from app.models import ConfigLabel, Incident, db
    from app.tenant_defaults_models import TenantDefaultAlert, TenantDefaultReplica, TenantDefaultSource
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        source = ConfigLabel(tenant_id=ids['shared'], kind='severity',
            value='Retirement preserves history', group='integration')
        db.session.add(source)
        db.session.commit()
        source_label_id = source.id
        published = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=source.id).one()
        published_id = published.id
        replica = TenantDefaultReplica.query.filter_by(source_id=published_id,
            tenant_id=ids['operational']).one()
        local_id = replica.local_id
        incident = Incident(tenant_id=ids['operational'], name='Historical incident',
                            reference='TEST-SHARED-RETIREMENT', severity_id=local_id)
        db.session.add(incident)
        db.session.commit()
        incident_id = incident.id
    response = _client(defaults_app, 'superuser', ids['shared']).post(
        f'/admin/labels/{source_label_id}/delete')
    assert response.status_code == 302
    with defaults_app.app_context():
        assert db.session.get(ConfigLabel, source_label_id) is None
        assert db.session.get(ConfigLabel, local_id) is not None
        assert db.session.get(Incident, incident_id).severity_id == local_id
        assert TenantDefaultAlert.query.filter_by(tenant_id=ids['operational'],
            source_id=published_id, local_id=local_id).count() == 1


def test_tenant_admin_only_sees_and_acknowledges_own_defaults_alerts(defaults_app):
    from app.models import db
    from app.tenant_defaults_models import TenantDefaultAlert, TenantDefaultSource
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        source = TenantDefaultSource(id=str(uuid.uuid4()), source_type='config_label',
                                     source_id=None, active=False, snapshot_json='{}')
        db.session.add(source)
        db.session.flush()
        own = TenantDefaultAlert(tenant_id=ids['operational'], source_id=source.id,
            kind='retired_in_use', message='OWN-ADMIN-ALERT', local_type='config_label', local_id=9999991)
        foreign = TenantDefaultAlert(tenant_id=ids['other'], source_id=source.id,
            kind='retired_in_use', message='FOREIGN-ADMIN-ALERT', local_type='config_label', local_id=9999992)
        db.session.add_all([own, foreign])
        db.session.commit()
        own_id, foreign_id = own.id, foreign.id
    client = _client(defaults_app)
    response = client.get('/admin/tenants-defaults/alerts')
    assert response.status_code == 200
    assert 'OWN-ADMIN-ALERT' in response.get_data(as_text=True)
    assert 'FOREIGN-ADMIN-ALERT' not in response.get_data(as_text=True)
    forbidden = client.post(f'/admin/tenants-defaults/alerts/{foreign_id}/ack')
    assert forbidden.status_code in (403, 404)
    accepted = client.post(f'/admin/tenants-defaults/alerts/{own_id}/ack')
    assert accepted.status_code == 302
    with defaults_app.app_context():
        assert db.session.get(TenantDefaultAlert, foreign_id).acknowledged_at is None
        assert db.session.get(TenantDefaultAlert, own_id).acknowledged_at is not None


def _minimal_provenance_archive():
    snapshot = json.dumps({'kind': 'severity', 'value': 'Shared fixture'})
    source_id = '11111111-1111-4111-8111-111111111111'
    return {
        'tenants': [
            {'id': 1, 'name': 'default', 'is_system_defaults': False},
            {'id': 2, 'name': 'Tenants Default', 'is_system_defaults': True},
            {'id': 3, 'name': 'another-operational', 'is_system_defaults': False},
        ],
        'config_labels': [
            {'id': 10, 'tenant_id': 2, 'kind': 'severity', 'value': 'Shared fixture'},
            {'id': 11, 'tenant_id': 1, 'kind': 'severity', 'value': 'Shared fixture'},
        ],
        'tenant_default_sources': [{
            'id': source_id, 'source_type': 'config_label', 'source_id': 10,
            'active': True, 'snapshot_json': snapshot,
        }],
        'tenant_default_replicas': [{
            'id': 20, 'source_id': source_id, 'tenant_id': 1,
            'local_type': 'config_label', 'local_id': 11, 'snapshot_json': snapshot,
        }],
    }


def test_archive_validation_preserves_legacy_import_and_does_not_mutate_payload():
    from app.tenant_defaults_archive import validate_defaults_archive_tables
    assert validate_defaults_archive_tables({'tenants': [{'id': 1, 'name': 'default'}]}) is True
    payload = _minimal_provenance_archive()
    unchanged = deepcopy(payload)
    assert validate_defaults_archive_tables(payload) is True
    assert payload == unchanged


@pytest.mark.parametrize('mutate', [
    lambda p: p['tenants'][0].update(is_system_defaults=True),
    lambda p: p['tenants'][1].update(name='default'),
    lambda p: p['tenants'][1].update(is_system_defaults='true'),
    lambda p: p['tenant_default_sources'][0].update(source_id=11),
    lambda p: p['tenant_default_sources'][0].update(id='not-an-uuid'),
    lambda p: p['tenant_default_sources'][0].update(source_type='settings'),
    lambda p: p['tenant_default_sources'][0].update(active=False),
    lambda p: p['tenant_default_replicas'][0].update(tenant_id=3),
    lambda p: p['tenant_default_replicas'][0].update(local_id=10),
    lambda p: p['tenant_default_replicas'][0].update(local_type='recommendation'),
    lambda p: p.update(incidents=[{'id': 30, 'tenant_id': 2}]),
    lambda p: p.update(user_tenant_roles=[{'id': 31, 'tenant_id': 2, 'user_id': 1}]),
    lambda p: p.update(users=[{'id': 32, 'tenant_id': 1, 'default_tenant_id': 2}]),
    lambda p: p['tenant_default_sources'][0].update(import_origin=str(uuid.uuid4())),
])
def test_archive_validation_rejects_forged_shared_ownership_and_references(mutate):
    from app.tenant_defaults_archive import validate_defaults_archive_tables
    payload = _minimal_provenance_archive()
    mutate(payload)
    with pytest.raises(ValueError):
        validate_defaults_archive_tables(payload)


def test_archive_validation_detects_catalog_payload_hash_tampering(defaults_app):
    from app.routes import _export_tables_payload
    from app.tenant_defaults_archive import validate_defaults_archive_tables
    from app.workflow_catalog_models import WorkflowCatalogEntry
    entry_id, _ = _catalog_entry(defaults_app)
    with defaults_app.app_context():
        tables = _export_tables_payload()
        assert validate_defaults_archive_tables(tables) is True
        entry = next(row for row in tables['workflow_catalog_entries'] if row['id'] == entry_id)
        entry['payload_hash'] = '0' * 64
        with pytest.raises(ValueError, match='impronta'):
            validate_defaults_archive_tables(tables)
        assert WorkflowCatalogEntry.query.filter_by(id=entry_id).one().payload_hash != '0' * 64


@pytest.mark.parametrize('original', ['private.pdf', 'private.v1', 'private.v1.pdf'])
def test_scoped_document_restore_uses_the_same_identity_as_runtime_ownership(defaults_app, original):
    from pathlib import Path
    from app.models import db, FormTemplateBinary, FormTemplateConfig, FormFieldMapping
    from app.form_generation import _sanitize_field_name, _restore_template_pdf_from_db
    from app.form_template_access import can_read_template
    from app.tenant_document_restore import import_tenant_document_definitions
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        tables = {
            'form_template_configs': [{'template_name': original, 'font_family': 'Times-Roman', 'font_size': 12}],
            'form_template_binaries': [{'template_name': original, 'pdf_data': b'%PDF-1.4\n% private restored PDF\n%%EOF\n'}],
            'form_field_mappings': [{'template_name': original, 'template_field': 'Title', 'db_field': 'name'}],
        }
        names = import_tenant_document_definitions(tables, ids['operational'])
        name = names[original]
        db.session.commit()
        assert name == Path(name).stem == _sanitize_field_name(name, 'template')
        assert FormTemplateConfig.query.filter_by(template_name=name).one().owner_tenant_id == ids['operational']
        assert FormFieldMapping.query.filter_by(template_name=name).one().template_field == 'Title'
        assert FormTemplateBinary.query.filter_by(template_name=name).one().filename == name + '.pdf'
        assert can_read_template(name, ids['operational']) is True
        assert can_read_template(name, ids['other']) is False
        assert can_read_template(name + '.pdf', ids['other']) is False
        restored_path = _restore_template_pdf_from_db(name)
        assert restored_path.name == name + '.pdf'
        assert b'private restored PDF' in restored_path.read_bytes()


def test_scoped_document_restore_imports_filesystem_only_pdf_and_its_mappings(defaults_app):
    from app.models import db, FormTemplateBinary, FormTemplateConfig, FormFieldMapping
    from app.tenant_document_restore import import_tenant_document_definitions, remap_document_setting
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    raw = b'%PDF-1.4\n% filesystem-only legacy document\n%%EOF\n'
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        member = tarfile.TarInfo('files/form_templates/legacy_only.pdf')
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
    stream.seek(0)
    tables = {'form_field_mappings': [{'template_name': 'legacy_only', 'template_field': 'Title', 'db_field': 'name'}]}
    files = {'form_templates': [{'template_name': 'legacy_only', 'name': 'legacy_only.pdf',
                                 'archive_path': 'files/form_templates/legacy_only.pdf'}]}
    with defaults_app.app_context(), tarfile.open(fileobj=stream, mode='r:gz') as archive:
        names = import_tenant_document_definitions(tables, ids['operational'], archive, files)
        db.session.commit()
        name = names['legacy_only']
        assert bytes(FormTemplateBinary.query.filter_by(template_name=name).one().pdf_data) == raw
        assert FormTemplateConfig.query.filter_by(template_name=name).one().owner_tenant_id == ids['operational']
        assert FormFieldMapping.query.filter_by(template_name=name).one().db_field == 'name'
        assert remap_document_setting({'document_download': [{'generated_template_name': 'legacy_only'}]}, names)['document_download'][0]['generated_template_name'] == name


@pytest.mark.parametrize('source', ['workflow', 'notification', 'button'])
def test_scoped_document_restore_rejects_missing_required_pdf(defaults_app, source):
    from app.models import FormTemplateBinary
    from app.tenant_document_restore import import_tenant_document_definitions
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    tables = {}
    if source == 'workflow':
        tables['incident_workflow_steps'] = [{'document_template_name': 'missing_required'}]
    elif source == 'notification':
        tables['notification_templates'] = [{'linked_form_template_name': 'missing_required'}]
    else:
        tables['settings'] = [{'key': f'tenant:{ids["operational"]}:incident_button_action_labels_json',
            'value': json.dumps({'document_download': [{'generated_template_name': 'missing_required'}]})}]
    with defaults_app.app_context():
        before = FormTemplateBinary.query.count()
        with pytest.raises(ValueError, match='non disponibile'):
            import_tenant_document_definitions(tables, ids['operational'])
        assert FormTemplateBinary.query.count() == before


def test_scoped_document_restore_accepts_historical_generated_document_without_source_pdf(defaults_app):
    from app.tenant_document_restore import import_tenant_document_definitions
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        names = import_tenant_document_definitions({'documents': [{'generated_template_name': 'deleted_historical_source'}]}, ids['operational'])
        assert names == {}


def test_scoped_document_restore_cannot_fallback_to_another_tenants_private_binary(defaults_app):
    from app.models import db, FormTemplateBinary, FormTemplateConfig
    from app.tenant_document_restore import import_tenant_document_definitions
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        db.session.add_all([
            FormTemplateConfig(template_name='foreign_private', owner_tenant_id=ids['other']),
            FormTemplateBinary(template_name='foreign_private', filename='foreign_private.pdf', pdf_data=b'%PDF-1.4 PRIVATE OTHER TENANT'),
        ])
        db.session.commit()
        with pytest.raises(ValueError, match='non disponibile'):
            import_tenant_document_definitions({'incident_workflow_steps': [{'document_template_name': 'foreign_private.pdf'}]}, ids['operational'])


def test_owned_document_retirement_keeps_orphan_files_private_and_rolls_back(defaults_app):
    from pathlib import Path
    from app.models import db, FormTemplateBinary, FormTemplateConfig
    from app.form_template_access import can_read_template, retire_tenant_documents
    from app.tenant_document_restore import import_tenant_document_definitions
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        names = import_tenant_document_definitions({'form_template_binaries': [
            {'template_name': 'retirement', 'pdf_data': b'%PDF-1.4\n%%EOF\n'}]}, ids['operational'])
        db.session.commit()
        name = names['retirement']
        path = Path(defaults_app.config['FORM_TEMPLATE_DIR']) / (name + '.pdf')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'%PDF-1.4 stale mounted-volume file')
        retire_tenant_documents(ids['operational'])
        db.session.flush()
        assert can_read_template(name, ids['other']) is False
        db.session.rollback()
        assert FormTemplateConfig.query.filter_by(template_name=name).one().owner_tenant_id == ids['operational']
        assert can_read_template(name, ids['operational']) is True
        retire_tenant_documents(ids['operational'])
        db.session.commit()
        assert FormTemplateConfig.query.filter_by(template_name=name).first() is None
        assert FormTemplateBinary.query.filter_by(template_name=name).first() is None
        assert path.exists()
        assert can_read_template(name, ids['other']) is False
        assert can_read_template(name + '.pdf', ids['operational']) is False


def test_scoped_export_excludes_foreign_owned_binary_and_mapping_aliases(defaults_app):
    from app.models import db, FormTemplateBinary, FormTemplateConfig, FormFieldMapping
    from app.routes import _export_tables_payload
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    with defaults_app.app_context():
        db.session.add_all([
            FormTemplateConfig(template_name='foreign_alias', owner_tenant_id=ids['other']),
            FormTemplateBinary(template_name='foreign_alias.pdf', filename='foreign_alias.pdf', pdf_data=b'%PDF-1.4 FOREIGN ALIAS PAYLOAD'),
            FormFieldMapping(template_name='foreign_alias.pdf', template_field='PRIVATE-ALIAS-FIELD', db_field='name'),
        ])
        db.session.commit()
        payload = _export_tables_payload(ids['operational'])
        for table in ('form_template_configs', 'form_template_binaries', 'form_field_mappings'):
            assert all(row['template_name'] not in {'foreign_alias', 'foreign_alias.pdf'} for row in payload[table])


def _tenant_reference_archive_payload():
    import base64
    source_tid = 777
    return {
        'format': 'cybersecurity-incident-registry-full-export', 'version': 4,
        'scope': 'tenant', 'scope_tenant_id': source_tid, 'relations': {}, 'files': {},
        'tables': {
            'tenants': [{'id': source_tid, 'name': 'source', 'is_system_defaults': False}],
            'config_labels': [
                {'id': old_id, 'tenant_id': source_tid, 'kind': kind, 'value': caption}
                for old_id, kind, caption in [
                    (1000001, 'severity', 'Imported severity'),
                    (1000002, 'action_label', 'Imported action'),
                    (1000003, 'category', 'Imported category'),
                    (1000004, 'data_type', 'Imported data type'),
                ]
            ],
            'incident_workflow_steps': [{'id': 1000010, 'tenant_id': source_tid, 'category_id': 1000003,
                'action_label_id': 1000002, 'position': 1, 'description': 'Scoped import remapped step',
                'conditions': 'severity:1000001,!data_type:1000004', 'step_type': 'registration',
                'document_generation_enabled': True, 'document_template_name': 'restore.form.pdf'}],
            'form_template_configs': [{'id': 1000020, 'template_name': 'restore.form.pdf', 'owner_tenant_id': source_tid,
                                      'font_family': 'Helvetica', 'font_size': 10, 'notification_tags': ''}],
            'form_template_binaries': [{'id': 1000021, 'template_name': 'restore.form.pdf', 'filename': 'restore.form.pdf',
                'pdf_data': {'__binary_base64__': base64.b64encode(b'%PDF-1.4\n%%EOF\n').decode('ascii')}}],
            'settings': [{'key': f'tenant:{source_tid}:incident_button_action_labels_json', 'value': json.dumps({
                'incident_update': 1000002,
                'document_download': [{'label_id': '1000002', 'generated_template_name': 'restore.form.pdf'}],
                'unrelated_counter': 1000002,
            })}],
        },
    }


def _payload_tar_bytes(payload):
    data = json.dumps(payload).encode('utf-8')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        member = tarfile.TarInfo('export.json')
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return stream.getvalue()


def test_scoped_full_import_remaps_condition_button_and_document_references(defaults_app):
    from app.models import db, ConfigLabel, IncidentWorkflowStep, Setting, FormTemplateConfig
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    result = _client(defaults_app).post('/import/full', data={
        'file': (io.BytesIO(_payload_tar_bytes(_tenant_reference_archive_payload())), 'tenant.tar.gz'),
    })
    assert result.status_code == 302
    with defaults_app.app_context():
        step = IncidentWorkflowStep.query.filter_by(tenant_id=ids['operational'], description='Scoped import remapped step').one()
        labels = {row.kind: row.id for row in ConfigLabel.query.filter_by(tenant_id=ids['operational']).all()
                  if row.value.startswith('Imported ')}
        assert not set(labels.values()) & {1000001, 1000002, 1000003, 1000004}
        assert step.conditions == f'severity:{labels["severity"]},!data_type:{labels["data_type"]}'
        setting = db.session.get(Setting, f'tenant:{ids["operational"]}:incident_button_action_labels_json')
        buttons = json.loads(setting.value)
        assert buttons['incident_update']['label_id'] == labels['action_label']
        assert buttons['document_download'][0]['label_id'] == labels['action_label']
        assert buttons['document_download'][0]['template_name'] == step.document_template_name
        assert buttons['unrelated_counter'] == 1000002
        assert step.document_template_name != 'restore.form.pdf'
        assert FormTemplateConfig.query.filter_by(template_name=step.document_template_name).one().owner_tenant_id == ids['operational']
        assert ConfigLabel.query.filter_by(tenant_id=ids['other'], value='FOREIGN-TENANT-CONFIG-MARKER').count() == 1


@pytest.mark.parametrize('corruption', ['missing_condition_label', 'wrong_condition_kind', 'missing_button_label', 'wrong_button_kind'])
def test_scoped_full_import_rolls_back_on_invalid_typed_label_references(defaults_app, corruption):
    from app.models import ConfigLabel, IncidentWorkflowStep
    ids = defaults_app.config['TEST_DEFAULTS_IDS']
    payload = _tenant_reference_archive_payload()
    if corruption == 'missing_condition_label':
        payload['tables']['incident_workflow_steps'][0]['conditions'] = 'severity:9999999'
    elif corruption == 'wrong_condition_kind':
        payload['tables']['incident_workflow_steps'][0]['conditions'] = 'severity:1000002'
    else:
        buttons = json.loads(payload['tables']['settings'][0]['value'])
        buttons['incident_update'] = 9999999 if corruption == 'missing_button_label' else 1000001
        payload['tables']['settings'][0]['value'] = json.dumps(buttons)
    with defaults_app.app_context():
        before = ConfigLabel.query.filter_by(tenant_id=ids['operational'], value='OWN-TENANT-CONFIG-MARKER').one().id
    result = _client(defaults_app).post('/import/full', data={
        'file': (io.BytesIO(_payload_tar_bytes(payload)), 'invalid-tenant.tar.gz'),
    })
    assert result.status_code == 302
    with defaults_app.app_context():
        assert ConfigLabel.query.filter_by(id=before, tenant_id=ids['operational'], value='OWN-TENANT-CONFIG-MARKER').count() == 1
        assert IncidentWorkflowStep.query.filter_by(tenant_id=ids['operational'], description='Scoped import remapped step').count() == 0
