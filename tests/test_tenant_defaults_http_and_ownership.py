"""HTTP regressions for document ownership and explicit tenant overrides.

The fixture logs in real tenant administrators and exercises registered Flask
routes. Authorization checks are never monkeypatched out.
"""
import base64
import io
import json
from pathlib import Path

import pytest


def _pdf(title):
    from pypdf import PdfWriter
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({'/Title': title})
    writer.write(stream)
    return stream.getvalue()


@pytest.fixture
def ownership_app(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'ownership.db'))
    for key, directory in {
        'UPLOAD_DIR': 'uploads', 'LOGO_DIR': 'logos', 'SSO_LOGO_DIR': 'sso',
        'FORM_TEMPLATE_DIR': 'forms', 'BACKUP_DIR': 'backups',
        'AI_CHATBOT_DOC_DIR': 'knowledge', 'SSL_DIR': 'ssl',
    }.items():
        monkeypatch.setenv(key, str(tmp_path / directory))
    monkeypatch.setenv('SECRET_KEY', 'O' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    from app import create_app
    from app.models import (db, Tenant, User, UserTenantRole, ConfigLabel,
                            IncidentWorkflowStep, FormTemplateConfig, FormTemplateBinary)
    from app.tenant_defaults import ensure_defaults_tenant

    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        own = Tenant.query.filter_by(name='default').one()
        shared = ensure_defaults_tenant()
        foreign = Tenant(name='ownership-private')
        db.session.add(foreign)
        db.session.flush()
        manager = User(username='ownership-manager', auth_provider='local', role='admin',
                       tenant_id=own.id, default_tenant_id=own.id)
        db.session.add(manager)
        db.session.flush()
        db.session.add(UserTenantRole(user_id=manager.id, tenant_id=own.id, role='admin'))
        category = ConfigLabel(tenant_id=own.id, kind='category', value='Ownership workflow')
        action = ConfigLabel(tenant_id=own.id, kind='action_label', value='Ownership action')
        db.session.add_all([category, action])
        db.session.flush()
        step = IncidentWorkflowStep(tenant_id=own.id, category_id=category.id,
            action_label_id=action.id, position=1, description='Original workflow step')
        db.session.add(step)
        for name, owner_id, title in [
            ('ownership_local', own.id, 'LOCAL DOCUMENT'),
            ('ownership_private', foreign.id, 'FOREIGN PRIVATE PDF MARKER'),
            ('ownership_shared', shared.id, 'SHARED DOCUMENT'),
        ]:
            db.session.add(FormTemplateConfig(template_name=name, owner_tenant_id=owner_id,
                                              font_family='Helvetica', font_size=11))
            db.session.add(FormTemplateBinary(template_name=name, filename=name + '.pdf',
                                              pdf_data=_pdf(title)))
        db.session.commit()
        app.config['OWNERSHIP_IDS'] = {'own': own.id, 'shared': shared.id, 'foreign': foreign.id,
                                      'manager': manager.id, 'category': category.id, 'step': step.id}
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _defaults_admin_client(app):
    from app.models import User
    with app.app_context():
        admin_id = User.query.filter_by(username='admin', auth_provider='local').one().id
    client = _client(app)
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['active_tenant_id'] = app.config['OWNERSHIP_IDS']['shared']
    return client


def test_defaults_audit_configuration_get_and_save_preserve_existing_logs(ownership_app):
    from datetime import datetime
    from app.models import db, AuditLog, Setting
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        old_logs = [AuditLog(tenant_id=ids[scope], occurred_at=datetime.utcnow(),
                            operation_type='audit:preserve_old', username='retained-' + scope,
                            actor_type='system', details='Retain this historical audit record')
                    for scope in ('shared', 'foreign')]
        db.session.add_all(old_logs)
        db.session.commit()
        old_ids = [row.id for row in old_logs]
    client = _defaults_admin_client(ownership_app)
    response = client.get('/admin/audit')
    assert response.status_code == 200
    response = client.post('/admin/audit', data={
        'action': 'save_audit_config', 'audit_records_per_page': '37', 'audit_max_records': '700',
    })
    assert response.status_code == 302
    with ownership_app.app_context():
        assert db.session.get(Setting, f'tenant:{ids["shared"]}:audit_records_per_page').value == '37'
        assert db.session.get(Setting, f'tenant:{ids["shared"]}:audit_max_records').value == '700'
        assert all(db.session.get(AuditLog, log_id) is not None for log_id in old_ids)


@pytest.mark.parametrize('action', ['purge_keep_count', 'purge_older_than', 'unknown_future_action', ''])
def test_defaults_audit_rejects_every_post_other_than_configuration(ownership_app, action):
    from datetime import datetime
    from app.models import db, AuditLog
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        old = AuditLog(tenant_id=ids['shared'], occurred_at=datetime(2000, 1, 1),
                       operation_type='audit:must_not_purge', username='retained', actor_type='system')
        db.session.add(old)
        db.session.commit()
        old_id = old.id
    response = _defaults_admin_client(ownership_app).post('/admin/audit', data={
        'action': action, 'purge_keep_count': '0', 'purge_older_than': '2099-01-01T00:00',
    })
    assert response.status_code == 403
    with ownership_app.app_context():
        assert db.session.get(AuditLog, old_id) is not None


@pytest.mark.parametrize('method', ['HEAD', 'OPTIONS'])
def test_defaults_audit_allows_only_explicit_get_and_save_post_methods(ownership_app, method):
    response = _defaults_admin_client(ownership_app).open('/admin/audit', method=method)
    assert response.status_code == 403


def test_settings_page_displays_effective_legacy_shared_and_local_provenance_without_values(ownership_app):
    import re
    from app.models import db, Setting
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        values = {
            'review_legacy_only': 'LEGACY-SECRET-MARKER',
            'review_all_layers': 'HIDDEN-LEGACY-FALLBACK',
            f'tenant:{ids["shared"]}:review_all_layers': 'HIDDEN-SHARED-VALUE',
            f'tenant:{ids["own"]}:review_all_layers': '',
            f'tenant:{ids["shared"]}:review_inherited_setting': 'HIDDEN-INHERITED-VALUE',
        }
        for key, value in values.items():
            db.session.merge(Setting(key=key, value=value))
        db.session.commit()
    response = _client(ownership_app).get('/admin/tenants-defaults/settings')
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    rows = re.findall(r'<tr>.*?</tr>', text, re.S)
    assert 'Compatibilità legacy' in next(row for row in rows if '<code>review_legacy_only</code>' in row)
    assert 'Personalizzazione locale' in next(row for row in rows if '<code>review_all_layers</code>' in row)
    assert 'Ereditato da Tenants Default' in next(row for row in rows if '<code>review_inherited_setting</code>' in row)
    assert all(value not in text for value in values.values() if value)


def test_defaults_settings_page_does_not_expose_private_legacy_parameter_names(ownership_app):
    from app.models import db, Setting
    with ownership_app.app_context():
        db.session.merge(Setting(key='review_source_must_not_inherit', value='LEGACY PRIVATE CONFIGURATION'))
        db.session.commit()
    response = _defaults_admin_client(ownership_app).get('/admin/tenants-defaults/settings')
    assert response.status_code == 200
    assert 'review_source_must_not_inherit' not in response.get_data(as_text=True)
    assert 'LEGACY PRIVATE CONFIGURATION' not in response.get_data(as_text=True)


def _client(app):
    client = app.test_client()
    ids = app.config['OWNERSHIP_IDS']
    with client.session_transaction() as session:
        session['_user_id'] = str(ids['manager'])
        session['_fresh'] = True
        session['active_tenant_id'] = ids['own']
        session['active_tenant_scope_enabled'] = True
    return client


def _legacy_payload(app):
    from app.routes import build_workflow_export_payload, tenant_execution_context
    ids = app.config['OWNERSHIP_IDS']
    with app.app_context(), tenant_execution_context(ids['own']):
        return build_workflow_export_payload(ids['category'])


@pytest.mark.parametrize('stage', ['preview', 'apply'])
@pytest.mark.parametrize('reference', ['dependency', 'step', 'step_alias', 'notification'])
def test_legacy_workflow_import_rejects_foreign_pdf_before_mutation(ownership_app, stage, reference):
    from app.models import db, FormTemplateConfig, FormTemplateBinary, IncidentWorkflowStep
    ids = ownership_app.config['OWNERSHIP_IDS']
    payload = _legacy_payload(ownership_app)
    payload['workflow']['steps'][0]['description'] = 'UNAUTHORIZED MODIFICATION'
    if reference == 'dependency':
        payload['dependencies']['form_templates'] = [{
            'template_name': 'ownership_private', 'font_size': 16,
            'binary': {'filename': 'ownership_private.pdf',
                       'pdf_base64': base64.b64encode(_pdf('REPLACEMENT')).decode('ascii')},
        }]
    elif reference in {'step', 'step_alias'}:
        payload['workflow']['steps'][0]['document_template_name'] = 'ownership_private.pdf' if reference == 'step_alias' else 'ownership_private'
        payload['workflow']['steps'][0]['document_generation_enabled'] = True
    else:
        payload['dependencies']['notification_types'] = [
            {'code': 'ownership_notice', 'label': 'Imported notice', 'enabled': True}]
        payload['dependencies']['notification_templates'] = [{
            'kind': 'ownership_notice', 'name': 'Forged attachment',
            'linked_form_template_name': 'ownership_private', 'subject': '', 'body': '',
        }]
    with ownership_app.app_context():
        original = bytes(FormTemplateBinary.query.filter_by(template_name='ownership_private').one().pdf_data)
        step_count = IncidentWorkflowStep.query.filter_by(tenant_id=ids['own']).count()
    raw = json.dumps(payload).encode('utf-8')
    data = ({'workflow_file': (io.BytesIO(raw), 'workflow.json')} if stage == 'preview' else
            {'payload_b64': base64.b64encode(raw).decode('ascii'),
             'overwrite_key': ['form_template::ownership_private', 'workflow_step::1::Ownership action']})
    response = _client(ownership_app).post('/admin/incident-workflows/import/' + stage, data=data)
    assert response.status_code in (400, 403)
    assert base64.b64encode(original) not in response.data
    with ownership_app.app_context():
        config = FormTemplateConfig.query.filter_by(template_name='ownership_private').one()
        assert config.owner_tenant_id == ids['foreign'] and config.font_size == 11
        assert bytes(FormTemplateBinary.query.filter_by(template_name='ownership_private').one().pdf_data) == original
        assert db.session.get(IncidentWorkflowStep, ids['step']).description == 'Original workflow step'
        assert IncidentWorkflowStep.query.filter_by(tenant_id=ids['own']).count() == step_count


@pytest.mark.parametrize('stage', ['preview', 'download'])
@pytest.mark.parametrize('reference', ['step', 'step_alias', 'notification'])
def test_legacy_workflow_export_rejects_foreign_pdf_references(ownership_app, stage, reference):
    from app.models import db, IncidentWorkflowStep, NotificationType, NotificationTemplate, FormTemplateBinary
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        step = db.session.get(IncidentWorkflowStep, ids['step'])
        if reference in {'step', 'step_alias'}:
            step.document_generation_enabled = True
            step.document_template_name = 'ownership_private.pdf' if reference == 'step_alias' else 'ownership_private'
        else:
            db.session.add(NotificationType(tenant_id=ids['own'], code='ownership_notice', label='Notice'))
            db.session.add(NotificationTemplate(tenant_id=ids['own'], kind='ownership_notice',
                name='Stale private reference', linked_form_template_name='ownership_private'))
            step.requires_notification = True
            step.required_notification_type = 'ownership_notice'
        db.session.commit()
        encoded = base64.b64encode(bytes(FormTemplateBinary.query.filter_by(template_name='ownership_private').one().pdf_data))
    response = _client(ownership_app).post('/admin/incident-workflows/export/' + stage,
                                         data={'category_id': ids['category']})
    assert response.status_code in (400, 403)
    assert encoded not in response.data


def test_legacy_import_rolls_back_prior_label_edits_when_shared_pdf_is_read_only(ownership_app):
    from app.models import db, ConfigLabel, IncidentWorkflowStep, FormTemplateConfig
    ids = ownership_app.config['OWNERSHIP_IDS']
    payload = _legacy_payload(ownership_app)
    action = next(row for row in payload['dependencies']['labels'] if row['kind'] == 'action_label')
    with ownership_app.app_context():
        action_id = db.session.get(IncidentWorkflowStep, ids['step']).action_label_id
        original_description = db.session.get(ConfigLabel, action_id).description
    action['description'] = 'MUTATED BEFORE DOCUMENT CHECK'
    payload['dependencies']['form_templates'] = [{
        'template_name': 'ownership_shared', 'font_family': 'Helvetica', 'font_size': 16,
        'notification_tags': [],
    }]
    response = _client(ownership_app).post('/admin/incident-workflows/import/apply', data={
        'payload_b64': base64.b64encode(json.dumps(payload).encode('utf-8')).decode('ascii'),
        'overwrite_key': ['label::action_label::Ownership action', 'form_template::ownership_shared'],
    })
    assert response.status_code in (400, 403)
    with ownership_app.app_context():
        assert db.session.get(ConfigLabel, action_id).description == original_description
        config = FormTemplateConfig.query.filter_by(template_name='ownership_shared').one()
        assert config.owner_tenant_id == ids['shared'] and config.font_size == 11


@pytest.mark.parametrize('action', ['save_mapping', 'delete_template', 'rename_template', 'replace_pdf_template'])
def test_modules_reject_mutation_of_another_tenants_pdf(ownership_app, action):
    from app.models import FormTemplateConfig, FormTemplateBinary
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        original = bytes(FormTemplateBinary.query.filter_by(template_name='ownership_private').one().pdf_data)
    response = _client(ownership_app).post('/modules/configuration', data={
        'action': action, 'template_name': 'ownership_private',
        'new_template_name': 'stolen_document', 'font_family': 'Times-Roman', 'font_size': '16',
        'replacement_pdf_template': (io.BytesIO(_pdf('REPLACEMENT')), 'replacement.pdf'),
    })
    assert response.status_code == 403
    with ownership_app.app_context():
        config = FormTemplateConfig.query.filter_by(template_name='ownership_private').one()
        assert config.owner_tenant_id == ids['foreign'] and config.font_size == 11
        assert bytes(FormTemplateBinary.query.filter_by(template_name='ownership_private').one().pdf_data) == original
        assert FormTemplateConfig.query.filter_by(template_name='stolen_document').first() is None
    # Listing may materialize the database PDF, but the denied request must
    # neither rename nor modify that file.
    path = Path(ownership_app.config['FORM_TEMPLATE_DIR']) / 'ownership_private.pdf'
    if path.exists():
        assert path.read_bytes() == original


def test_modules_allow_owner_to_edit_their_own_document(ownership_app):
    from app.models import FormTemplateConfig
    response = _client(ownership_app).post('/modules/configuration', data={
        'action': 'save_mapping', 'template_name': 'ownership_local',
        'font_family': 'Times-Roman', 'font_size': '12',
    })
    assert response.status_code == 302
    with ownership_app.app_context():
        config = FormTemplateConfig.query.filter_by(template_name='ownership_local').one()
        assert config.owner_tenant_id == ownership_app.config['OWNERSHIP_IDS']['own']
        assert config.font_family == 'Times-Roman' and config.font_size == 12


def test_owned_document_visibility_and_explicit_background_read_scope(ownership_app):
    from app.form_generation import get_template, list_templates
    from app.routes import tenant_execution_context
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context(), tenant_execution_context(ids['own']):
        visible = {template.name for template in list_templates()}
        assert {'ownership_local', 'ownership_shared'} <= visible
        assert 'ownership_private' not in visible
        assert 'ownership_private' in {template.name for template in list_templates(all_tenants=True)}
        with pytest.raises(ValueError, match='altro tenant'):
            get_template('ownership_private', tenant_id=ids['own'])
        assert get_template('ownership_private', tenant_id=ids['foreign']).path.exists()


def test_shared_pdf_is_readable_but_tags_resolve_to_the_tenants_replica(ownership_app):
    from app.models import db, FormTemplateConfig, NotificationType
    from app.form_generation import get_template
    from app.form_template_access import can_edit_template
    from app.routes import tenant_execution_context, notification_tags_for_form_template_config
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        local = NotificationType(tenant_id=ids['own'], code='ownership_notice', label='Unrelated local notice')
        db.session.add(local)
        db.session.commit()
        origin = NotificationType(tenant_id=ids['shared'], code='ownership_notice', label='Published notice')
        db.session.add(origin)
        FormTemplateConfig.query.filter_by(template_name='ownership_shared').one().set_notification_tags(['ownership_notice'])
        db.session.commit()
        source = TenantDefaultSource.query.filter_by(source_type='notification_type', source_id=origin.id).one()
        replica = TenantDefaultReplica.query.filter_by(source_id=source.id, tenant_id=ids['own']).one()
        copied = db.session.get(NotificationType, replica.local_id)
        assert copied.code != local.code
        with tenant_execution_context(ids['own']):
            assert get_template('ownership_shared', tenant_id=ids['own']).path.exists()
            assert can_edit_template('ownership_shared', ids['own']) is False
            assert notification_tags_for_form_template_config('ownership_shared') == [copied.code]
    denied = _client(ownership_app).post('/modules/configuration', data={
        'action': 'delete_template', 'template_name': 'ownership_shared',
    })
    assert denied.status_code == 403


def _seed_settings(app):
    from app.models import db, Setting
    ids = app.config['OWNERSHIP_IDS']
    with app.app_context():
        for scope, value in [('shared', 'SHARED VALUE'), ('own', 'OWN OVERRIDE'), ('foreign', 'PRIVATE OVERRIDE')]:
            db.session.merge(Setting(key=f'tenant:{ids[scope]}:security_owner_name', value=value))
        db.session.commit()


def test_http_inherit_removes_only_the_active_tenants_override(ownership_app):
    from app.models import db, Setting
    from app.routes import _setting_value_without_request_user
    ids = ownership_app.config['OWNERSHIP_IDS']
    _seed_settings(ownership_app)
    response = _client(ownership_app).post('/admin/tenants-defaults/settings/inherit', data={
        'source_tenant_id': ids['own'], 'key': 'security_owner_name',
    })
    assert response.status_code == 302
    with ownership_app.app_context():
        assert db.session.get(Setting, f'tenant:{ids["own"]}:security_owner_name') is None
        assert db.session.get(Setting, f'tenant:{ids["foreign"]}:security_owner_name').value == 'PRIVATE OVERRIDE'
        assert db.session.get(Setting, f'tenant:{ids["shared"]}:security_owner_name').value == 'SHARED VALUE'
        assert _setting_value_without_request_user('security_owner_name', tenant_id=ids['own']) == 'SHARED VALUE'


@pytest.mark.parametrize('forgery', ['source_tenant', 'physical_key'])
def test_http_inherit_cannot_target_another_tenants_setting(ownership_app, forgery):
    from app.models import db, Setting
    ids = ownership_app.config['OWNERSHIP_IDS']
    _seed_settings(ownership_app)
    data = {'source_tenant_id': ids['own'], 'key': 'security_owner_name'}
    if forgery == 'source_tenant':
        data['source_tenant_id'] = ids['foreign']
    else:
        data['key'] = f'tenant:{ids["foreign"]}:security_owner_name'
    response = _client(ownership_app).post('/admin/tenants-defaults/settings/inherit', data=data)
    assert response.status_code in (400, 403)
    with ownership_app.app_context():
        assert db.session.get(Setting, f'tenant:{ids["own"]}:security_owner_name').value == 'OWN OVERRIDE'
        assert db.session.get(Setting, f'tenant:{ids["foreign"]}:security_owner_name').value == 'PRIVATE OVERRIDE'


def test_repeated_catalog_install_post_keeps_both_requested_copy_names(ownership_app):
    from app.models import db, ConfigLabel, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow
    from app.workflow_catalog_models import WorkflowCatalogInstallation
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        entry = save_catalog_workflow(build_catalog_workflow_payload(ids['own'], ids['category']), 'HTTP repeated copies')
        db.session.commit()
        entry_id = entry.id
    client = _client(ownership_app)
    for name in ['Copia gruppo A', 'Copia gruppo B']:
        response = client.post(f'/admin/workflow-catalog/{entry_id}/install', data={
            'target_tenant_id': ids['own'], 'copy_name': name,
        })
        assert response.status_code == 302
    with ownership_app.app_context():
        receipts = WorkflowCatalogInstallation.query.filter_by(entry_id=entry_id, tenant_id=ids['own']).order_by(WorkflowCatalogInstallation.id).all()
        assert [receipt.copy_name for receipt in receipts] == ['Copia gruppo A', 'Copia gruppo B']
        assert [db.session.get(ConfigLabel, receipt.category_id).value for receipt in receipts] == ['Copia gruppo A', 'Copia gruppo B']
        installed = [db.session.get(IncidentWorkflowStep, json.loads(receipt.step_ids_json)[0]) for receipt in receipts]
        assert installed[0].id != installed[1].id
        assert installed[0].action_label_id != installed[1].action_label_id
        assert all(step.tenant_id == ids['own'] for step in installed)


@pytest.mark.parametrize('stored_name', ['owner_alias', 'owner_alias.pdf', 'owner_alias.v1'])
def test_pdf_ownership_cannot_be_bypassed_with_filename_alias(ownership_app, stored_name):
    from app.models import db, FormTemplateConfig
    from app.form_template_access import can_read_template, can_edit_template
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        db.session.add(FormTemplateConfig(template_name=stored_name, owner_tenant_id=ids['foreign']))
        db.session.commit()
        for reference in ('owner_alias', 'owner_alias.pdf'):
            assert can_read_template(reference, ids['own']) is False
            assert can_edit_template(reference, ids['own']) is False
            assert can_read_template(reference, ids['foreign']) is True


def test_scoped_export_filters_alias_binaries_and_maps_shared_document_tags(ownership_app):
    from app.models import db, FormTemplateConfig, FormTemplateBinary, FormFieldMapping, NotificationType
    from app.models import TenantDefaultSource, TenantDefaultReplica
    from app.routes import _export_tables_payload
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        db.session.add(FormTemplateBinary(template_name='ownership_private.pdf', filename='ownership_private.pdf',
                                         pdf_data=_pdf('PRIVATE ALIAS')))
        db.session.add(FormFieldMapping(template_name='ownership_private.pdf', template_field='private', db_field='name'))
        db.session.add(NotificationType(tenant_id=ids['own'], code='owner_notice', label='LOCAL NOTICE'))
        source_type = NotificationType(tenant_id=ids['shared'], code='owner_notice', label='SHARED NOTICE')
        db.session.add(source_type)
        FormTemplateConfig.query.filter_by(template_name='ownership_shared').one().set_notification_tags(['owner_notice'])
        db.session.commit()
        origin = TenantDefaultSource.query.filter_by(source_type='notification_type', source_id=source_type.id).one()
        replica = TenantDefaultReplica.query.filter_by(source_id=origin.id, tenant_id=ids['own']).one()
        mapped_code = db.session.get(NotificationType, replica.local_id).code
        assert mapped_code != 'owner_notice'
        tables = _export_tables_payload(ids['own'])
        for table in ('form_template_configs', 'form_template_binaries', 'form_field_mappings'):
            assert not any(row['template_name'].startswith('ownership_private') for row in tables[table])
        shared = next(row for row in tables['form_template_configs'] if row['template_name'] == 'ownership_shared')
        assert shared['owner_tenant_id'] == ids['own']
        assert shared['notification_tags'] == mapped_code


def test_document_delete_is_blocked_by_workflow_pdf_alias(ownership_app):
    from app.models import db, IncidentWorkflowStep, FormTemplateConfig
    from app.form_template_access import template_in_use
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        step = db.session.get(IncidentWorkflowStep, ids['step'])
        step.document_template_name = 'ownership_local.pdf'
        step.document_generation_enabled = True
        db.session.commit()
        assert template_in_use('ownership_local') is True
        assert template_in_use('ownership_local.pdf') is True
    response = _client(ownership_app).post('/modules/configuration', data={
        'action': 'delete_template', 'template_name': 'ownership_local'})
    assert response.status_code == 302
    with ownership_app.app_context():
        assert FormTemplateConfig.query.filter_by(template_name='ownership_local').one().owner_tenant_id == ids['own']


def _installed_http_workflows(app):
    from app.models import db
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    ids = app.config['OWNERSHIP_IDS']
    with app.app_context():
        entry = save_catalog_workflow(build_catalog_workflow_payload(ids['own'], ids['category']), 'HTTP lifecycle')
        own_copy = import_catalog_workflow(entry.id, ids['own'], copy_name='HTTP own')
        foreign_copy = import_catalog_workflow(entry.id, ids['foreign'], copy_name='HTTP foreign')
        db.session.commit()
        return entry.id, own_copy, foreign_copy


def test_workflow_lifecycle_http_rejects_foreign_admin_mutations(ownership_app):
    from app.models import db, TenantWorkflow
    _, own_copy, foreign_copy = _installed_http_workflows(ownership_app)
    client = _client(ownership_app)
    assert client.post(f"/admin/workflow-catalog/local/{foreign_copy['workflow_id']}/status",
                       data={'status': 'obsolete'}).status_code == 403
    assert client.post(f"/admin/workflow-catalog/local/{foreign_copy['workflow_id']}/personalize").status_code == 403
    response = client.post(f"/admin/workflow-catalog/local/{own_copy['workflow_id']}/status",
                           data={'status': 'obsolete'})
    assert response.status_code == 302
    with ownership_app.app_context():
        assert db.session.get(TenantWorkflow, own_copy['workflow_id']).status == 'obsolete'
        assert db.session.get(TenantWorkflow, foreign_copy['workflow_id']).status == 'current'


def test_workflow_catalog_status_requires_superuser_and_blocks_later_install(ownership_app):
    from app.models import db, WorkflowCatalogEntry, TenantWorkflow
    entry_id, own_copy, _ = _installed_http_workflows(ownership_app)
    manager = _client(ownership_app)
    assert manager.post(f'/admin/workflow-catalog/{entry_id}/status', data={'status': 'obsolete'}).status_code == 403
    response = _defaults_admin_client(ownership_app).post(f'/admin/workflow-catalog/{entry_id}/status',
                                                        data={'status': 'obsolete'})
    assert response.status_code == 302
    assert manager.post(f'/admin/workflow-catalog/{entry_id}/install', data={'copy_name': 'Denied copy'}).status_code == 400
    assert manager.post(f"/admin/workflow-catalog/local/{own_copy['workflow_id']}/status",
                        data={'status': 'current'}).status_code == 400
    with ownership_app.app_context():
        assert db.session.get(WorkflowCatalogEntry, entry_id).status == 'obsolete'
        assert db.session.get(TenantWorkflow, own_copy['workflow_id']).status == 'obsolete'


def test_workflow_notices_are_personal_and_superuser_sees_them_across_tenants(ownership_app):
    from app.models import db, User, WorkflowObsolescenceNotice
    from app.workflow_lifecycle import set_catalog_workflow_status
    ids = ownership_app.config['OWNERSHIP_IDS']
    entry_id, _, _ = _installed_http_workflows(ownership_app)
    with ownership_app.app_context():
        set_catalog_workflow_status(entry_id, 'obsolete')
        db.session.commit()
        super_id = User.query.filter_by(username='admin', auth_provider='local').one().id
        own_notice = WorkflowObsolescenceNotice.query.filter_by(user_id=ids['manager'], entry_id=entry_id).one().id
        super_notice = WorkflowObsolescenceNotice.query.filter_by(user_id=super_id, entry_id=entry_id).one().id
    manager = _client(ownership_app)
    assert manager.post(f'/admin/workflow-catalog/notices/{super_notice}/acknowledge').status_code == 404
    assert manager.post(f'/admin/workflow-catalog/notices/{own_notice}/acknowledge').status_code == 302
    super_client = _defaults_admin_client(ownership_app)
    with super_client.session_transaction() as session:
        session['active_tenant_id'] = ids['foreign']
    page = super_client.get('/admin/workflow-catalog/notices')
    assert page.status_code == 200
    assert 'HTTP lifecycle' in page.get_data(as_text=True)
    with ownership_app.app_context():
        assert db.session.get(WorkflowObsolescenceNotice, own_notice).read_at is not None
        assert db.session.get(WorkflowObsolescenceNotice, super_notice).read_at is None
