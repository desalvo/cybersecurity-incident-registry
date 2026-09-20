import json
import tarfile
from pathlib import Path


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'bootstrap.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SSL_DIR', str(tmp_path / 'ssl'))
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'DestinationAdmin123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def test_bootstrap_export_is_default_tenant_only_and_anonymized(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import (
        AIChatbotDocument, AuditLog, ConfigLabel, ExternalRecipient,
        FormTemplateBinary, FormTemplateConfig, Incident, IncidentWorkflowStep,
        NotificationTemplate, NotificationType, Person, Setting, Tenant, User,
    )
    from app.routes import (
        BOOTSTRAP_EXPORT_PROFILE, build_anonymized_default_tenant_bootstrap_archive,
        store_setting_value,
    )

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        other = Tenant(name='private-tenant', description='PRIVATE TENANT')
        db.session.add(other); db.session.flush()

        admin = User.query.filter_by(username='admin', auth_provider='local').one()
        admin.name = 'Private Administrator Name'
        admin.email = 'private-admin@example.org'
        admin.password_hash = 'PRIVATE_PASSWORD_HASH'
        private_user = User(username='alice-private', auth_provider='local', name='Alice Private', email='alice@example.org', role='admin', tenant_id=default.id, password_hash='PRIVATE_USER_HASH')
        db.session.add(private_user)
        db.session.add(Person(tenant_id=default.id, name='Mario Rossi', email='mario.rossi@example.org'))
        db.session.add(ExternalRecipient(tenant_id=default.id, name='DPO Mario', email='dpo@example.org', notes='private notes'))
        db.session.add(AuditLog(tenant_id=default.id, operation_type='private', username='alice-private', details='PERSONAL AUDIT DETAIL'))
        db.session.add(AIChatbotDocument(tenant_id=default.id, title='Private KB', filename='private.md', original_filename='private.md', extracted_text='TOP SECRET KNOWLEDGE'))
        db.session.add(Incident(tenant_id=default.id, creator_id=admin.id, creator_name='Private Administrator Name', creator_email='private-admin@example.org', name='PRIVATE INCIDENT', reference='PRIVATE-1'))

        action_label = ConfigLabel(tenant_id=default.id, kind='action_label', value='Bootstrap action', description='Reusable workflow action')
        db.session.add(action_label); db.session.flush()
        nt = NotificationType(tenant_id=default.id, code='bootstrap_notice', label='Bootstrap notice')
        db.session.add(nt)
        tpl_name = 'bootstrap-required'
        db.session.add(FormTemplateConfig(template_name=tpl_name, font_family='Helvetica', font_size=10, notification_tags='bootstrap_notice'))
        db.session.add(FormTemplateBinary(template_name=tpl_name, filename=tpl_name + '.pdf', pdf_data=b'%PDF-1.4 bootstrap template'))
        db.session.add(NotificationTemplate(tenant_id=default.id, kind='bootstrap_notice', name='Bootstrap template', subject='Reusable', body='Reusable body', linked_form_template_name=tpl_name, action_label_id=action_label.id, recipient_source='manual', recipient_value='personal-recipient@example.org', cc_source='manual', cc_value='personal-cc@example.org'))
        db.session.add(IncidentWorkflowStep(tenant_id=default.id, action_label_id=action_label.id, position=1, description='Reusable workflow', required=True, requires_notification=True, required_notification_type='bootstrap_notice', document_generation_enabled=True, document_template_name=tpl_name))

        db.session.merge(Setting(key=f'tenant:{default.id}:smtp_password', value=store_setting_value('smtp_password', 'SMTP-PRIVATE-SECRET')))
        db.session.merge(Setting(key=f'tenant:{default.id}:security_owner_email', value='owner@example.org'))
        profiles = [{'id': 'corp', 'sso_enabled': '1', 'sso_provider_name': 'Corporate SSO', 'sso_authorization_url': 'https://sso.example.org/auth', 'sso_token_url': 'https://sso.example.org/token', 'sso_client_id': 'bootstrap-client', 'sso_client_secret': 'SSO-PRIVATE-SECRET'}]
        db.session.merge(Setting(key=f'tenant:{default.id}:sso_profiles_json', value=store_setting_value('sso_profiles_json', json.dumps(profiles))))
        db.session.merge(Setting(key=f'tenant:{other.id}:smtp_host', value='private-other-tenant.example.org'))
        db.session.commit()

        archive_path = build_anonymized_default_tenant_bootstrap_archive(prefix='test-bootstrap')

    with tarfile.open(archive_path, 'r:gz') as archive:
        payload = json.load(archive.extractfile('export.json'))
        names = set(archive.getnames())
        raw = json.dumps(payload, ensure_ascii=False)

    assert payload['bootstrap']['profile'] == BOOTSTRAP_EXPORT_PROFILE
    assert payload['bootstrap']['anonymized'] is True
    assert payload['scope'] == 'global'
    assert [row['name'] for row in payload['tables']['tenants']] == ['default']
    assert payload['tables']['incidents'] == []
    assert payload['tables']['actions'] == []
    assert payload['tables']['documents'] == []
    assert payload['tables']['people'] == []
    assert payload['tables']['external_recipients'] == []
    assert payload['tables']['audit_logs'] == []
    assert payload['tables']['ai_chatbot_documents'] == []
    assert len(payload['tables']['users']) == 1
    assert payload['tables']['users'][0]['username'] == 'admin'
    assert payload['tables']['users'][0]['password_hash'] is None
    assert payload['tables']['users'][0]['email'] == 'admin@example.local'
    assert payload['tables']['incident_workflow_steps']
    assert payload['tables']['notification_templates'][0]['recipient_value'] == ''
    assert payload['tables']['notification_templates'][0]['cc_value'] == ''
    assert payload['tables']['form_template_binaries']
    assert 'files/form_templates/bootstrap-required.pdf' in names

    assert 'SMTP-PRIVATE-SECRET' not in raw
    assert 'SSO-PRIVATE-SECRET' not in raw
    assert 'owner@example.org' not in raw
    assert 'private-admin@example.org' not in raw
    assert 'alice@example.org' not in raw
    assert 'Mario Rossi' not in raw
    assert 'PRIVATE INCIDENT' not in raw
    assert 'TOP SECRET KNOWLEDGE' not in raw
    assert 'private-other-tenant.example.org' not in raw
    settings = {row['key']: row['value'] for row in payload['tables']['settings']}
    sso_raw = settings[f'tenant:{payload["tables"]["tenants"][0]["id"]}:sso_profiles_json']
    sanitized_profiles = json.loads(sso_raw)
    assert sanitized_profiles[0]['sso_client_id'] == 'bootstrap-client'
    assert sanitized_profiles[0]['sso_client_secret'] == ''
    assert sanitized_profiles[0]['sso_enabled'] == '0'


def test_bootstrap_admin_reset_uses_destination_password(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app import create_app
    from app.auth import verify_password
    from app.models import User
    from app.routes import _reset_bootstrap_admin_credentials

    app = create_app(); app.config['TESTING'] = True
    with app.app_context():
        admin = User.query.filter_by(username='admin', auth_provider='local').one()
        admin.name = 'Source Name'; admin.email = 'source@example.org'; admin.mfa_enabled = True; admin.external_id = 'source-id'
        _reset_bootstrap_admin_credentials(admin, 'DestinationAdmin123!')
        assert verify_password(admin.password_hash, 'DestinationAdmin123!')
        assert admin.name == 'Administrator'
        assert admin.email == 'admin@example.local'
        assert admin.mfa_enabled is False
        assert admin.external_id is None
        assert admin.role == 'superuser'


def test_export_menu_exposes_bootstrap_option_and_import_requires_destination_password():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    menu = Path('app/templates/base.html').read_text(encoding='utf-8')
    assert "request.args.get('mode') == 'bootstrap'" in routes
    assert "get_admin_initial_password()" in routes
    assert 'ADMIN_INITIAL_PASSWORD nella nuova istanza' in routes
    assert "url_for('main.export_full', mode='bootstrap')" in menu
