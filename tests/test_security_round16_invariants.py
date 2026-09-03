import re

import pytest
from werkzeug.exceptions import NotFound


def _configure_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'round16.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'R' * 64)
    monkeypatch.setenv('SETTING_ENCRYPTION_KEY', 'S' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def test_notification_templates_are_scoped_to_active_tenant(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from flask import session
    from flask_login import login_user
    from app import create_app
    from app.models import db, NotificationTemplate, Tenant, User
    from app.routes import get_notification_template, writable_notification_template_or_404

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='round16-lab', description='Round 16 isolation')
        db.session.add(lab)
        db.session.flush()
        local = NotificationTemplate(tenant_id=default.id, kind='round16_notice', name='Default tenant template', subject='default', body='default', is_default=True)
        foreign = NotificationTemplate(tenant_id=lab.id, kind='round16_notice', name='Lab tenant template', subject='lab', body='lab', is_default=True)
        db.session.add_all([local, foreign])
        db.session.commit()
        default_id, lab_id, foreign_id = default.id, lab.id, foreign.id
        admin_id = User.query.filter_by(username='admin', auth_provider='local').one().id

    with app.test_request_context('/'):
        admin = db.session.get(User, admin_id)
        login_user(admin)
        session['active_tenant_id'] = default_id
        selected = get_notification_template('round16_notice', foreign_id)
        assert selected.tenant_id == default_id
        assert selected.subject == 'default'
        with pytest.raises(NotFound):
            writable_notification_template_or_404(foreign_id, 'round16_notice')

        session['active_tenant_id'] = lab_id
        selected = get_notification_template('round16_notice', foreign_id)
        assert selected.id == foreign_id
        assert selected.tenant_id == lab_id


def test_default_notification_templates_are_created_per_tenant(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from flask import session
    from flask_login import login_user
    from app import create_app
    from app.models import db, NotificationTemplate, Tenant, User
    from app.routes import ensure_default_notification_templates

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        lab = Tenant(name='round16-defaults', description='Round 16 defaults')
        db.session.add(lab)
        db.session.commit()
        lab_id = lab.id
        admin_id = User.query.filter_by(username='admin', auth_provider='local').one().id

    with app.test_request_context('/'):
        login_user(db.session.get(User, admin_id))
        session['active_tenant_id'] = lab_id
        ensure_default_notification_templates()
        db.session.commit()
        rows = NotificationTemplate.query.filter_by(tenant_id=lab_id).all()
        assert {row.kind for row in rows} >= {'user', 'csirt', 'dpo'}
        assert all(row.tenant_id == lab_id for row in rows)


def test_round16_notification_template_writes_have_tenant_boundary_static():
    source = open('app/routes.py', encoding='utf-8').read()
    region = source[source.index("@bp.route('/notifiche/template/nuovo'"):source.index("@bp.route('/incident/<int:iid>/notify/<kind>/preview'")]
    assert 'NotificationTemplate(tenant_id=current_tenant_id(), kind=kind)' in region
    assert 'writable_notification_template_or_404' in region
    assert 'current_tenant_notification_template_query(kind).update' in region
    assert 'NotificationTemplate.query.filter_by(id=template_id' not in region
    assert 'NotificationTemplate.query.filter_by(kind=kind).update' not in region


def test_ai_chatbot_knowledge_is_scoped_to_active_tenant(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from flask import session
    from flask_login import login_user
    from app import create_app
    from app.models import AIChatbotDocument, db, Tenant, User
    from app.plugins.ai_chatbot.knowledge import uploaded_knowledge

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='round16-ai-lab', description='AI tenant isolation')
        db.session.add(lab)
        db.session.flush()
        db.session.add_all([
            AIChatbotDocument(tenant_id=default.id, title='Default KB', filename='default.txt', original_filename='default.txt', extracted_text='ONLY_DEFAULT_KB'),
            AIChatbotDocument(tenant_id=lab.id, title='Lab KB', filename='lab.txt', original_filename='lab.txt', extracted_text='ONLY_LAB_KB'),
        ])
        db.session.commit()
        default_id, lab_id = default.id, lab.id
        admin_id = User.query.filter_by(username='admin', auth_provider='local').one().id

    with app.test_request_context('/'):
        login_user(db.session.get(User, admin_id))
        session['active_tenant_id'] = default_id
        text = uploaded_knowledge()
        assert 'ONLY_DEFAULT_KB' in text
        assert 'ONLY_LAB_KB' not in text
        session['active_tenant_id'] = lab_id
        text = uploaded_knowledge()
        assert 'ONLY_LAB_KB' in text
        assert 'ONLY_DEFAULT_KB' not in text


def test_ai_database_context_filters_superuser_to_active_tenant(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from flask import session
    from flask_login import login_user
    from app import create_app
    from app.models import db, Recommendation, Tenant, User
    from app.plugins.ai_chatbot.database_context import _tenant_filtered_count

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='round16-dbctx-lab', description='AI DB context isolation')
        db.session.add(lab)
        db.session.flush()
        db.session.add_all([
            Recommendation(tenant_id=default.id, text='default context marker'),
            Recommendation(tenant_id=lab.id, text='lab context marker'),
        ])
        db.session.commit()
        default_id, lab_id = default.id, lab.id
        admin_id = User.query.filter_by(username='admin', auth_provider='local').one().id

    with app.test_request_context('/'):
        login_user(db.session.get(User, admin_id))
        session['active_tenant_id'] = default_id
        default_count = _tenant_filtered_count(Recommendation.__table__)
        session['active_tenant_id'] = lab_id
        lab_count = _tenant_filtered_count(Recommendation.__table__)
        assert default_count >= 1
        assert lab_count == 1


def test_ai_chatbot_document_admin_paths_are_tenant_scoped_static():
    source = open('app/plugins/ai_chatbot/routes.py', encoding='utf-8').read()
    knowledge = open('app/plugins/ai_chatbot/knowledge.py', encoding='utf-8').read()
    dbctx = open('app/plugins/ai_chatbot/database_context.py', encoding='utf-8').read()
    assert 'tenant_id=current_tenant_id()' in source
    assert 'tenant_query(AIChatbotDocument).order_by' in source
    assert 'tenant_query(AIChatbotDocument).filter(AIChatbotDocument.id == doc_id).first_or_404()' in source
    assert 'safe_chatbot_document_path(doc.filename)' in source
    assert 'return bool(getattr(current_user' in source and 'can_admin()' in source
    assert 'tenant_query(AIChatbotDocument).order_by' in knowledge
    assert "if 'tenant_id' in table.c:" in dbctx
    assert 'and not is_superuser()' not in dbctx


def _csrf(html):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def test_admin_secret_fields_never_render_stored_credentials(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db
    from app.routes import save_sso_profiles, set_setting_value

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        set_setting_value('ldap_bind_password', 'ROUND16_LDAP_SECRET')
        set_setting_value('smtp_password', 'ROUND16_SMTP_SECRET')
        save_sso_profiles([{
            'id': 'round16-sso',
            'sso_provider_name': 'Round16 SSO',
            'sso_client_id': 'round16-client',
            'sso_client_secret': 'ROUND16_SSO_SECRET',
            'sso_authorization_url': 'https://idp.example.test/auth',
            'sso_token_url': 'https://idp.example.test/token',
            'sso_userinfo_url': 'https://idp.example.test/userinfo',
        }])
        db.session.commit()

    client = app.test_client()
    login = client.get('/login')
    token = _csrf(login.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})

    ldap_html = client.get('/admin/ldap').get_data(as_text=True)
    smtp_html = client.get('/notifiche/impostazioni').get_data(as_text=True)
    sso_html = client.get('/admin/sso?profile=round16-sso').get_data(as_text=True)
    assert 'ROUND16_LDAP_SECRET' not in ldap_html
    assert 'ROUND16_SMTP_SECRET' not in smtp_html
    assert 'ROUND16_SSO_SECRET' not in sso_html


def test_secret_forms_preserve_blank_values_static():
    routes = open('app/routes.py', encoding='utf-8').read()
    smtp = open('app/templates/notification_settings.html', encoding='utf-8').read()
    ldap = open('app/templates/ldap.html', encoding='utf-8').read()
    sso = open('app/templates/sso.html', encoding='utf-8').read()
    assert "elif k == 'smtp_password':" in routes
    assert "if request.form.get('ldap_bind_password'):" in routes
    assert "existing_profile.get('sso_client_secret', '')" in routes
    assert "settings['smtp_password'] = ''" in routes
    assert "ldap_settings_for_display['ldap_bind_password'] = ''" in routes
    assert "selected_for_display['sso_client_secret'] = ''" in routes
    assert "settings.get('smtp_password'" not in smtp
    assert "settings.get('ldap_bind_password'" not in ldap
    assert 'settings.sso_client_secret' not in sso


def test_background_tenant_context_isolates_settings(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant
    from app.routes import current_tenant_id, set_setting_value, setting_value, tenant_execution_context

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='round16-scheduler-lab', description='Scheduler tenant isolation')
        db.session.add(lab)
        db.session.commit()
        with tenant_execution_context(default.id):
            set_setting_value('notification_deadline_poll_seconds', '61')
            db.session.commit()
        with tenant_execution_context(lab.id):
            set_setting_value('notification_deadline_poll_seconds', '173')
            db.session.commit()
        with tenant_execution_context(default.id):
            assert current_tenant_id() == default.id
            assert setting_value('notification_deadline_poll_seconds') == '61'
        with tenant_execution_context(lab.id):
            assert current_tenant_id() == lab.id
            assert setting_value('notification_deadline_poll_seconds') == '173'


def test_background_schedulers_iterate_inside_tenant_boundary_static():
    source = open('app/routes.py', encoding='utf-8').read()
    assert 'def run_all_tenant_scheduler_services_cycle' in source
    assert 'def process_all_tenant_incident_reminders' in source
    assert 'with tenant_execution_context(tenant_id):' in source
    assert "run_all_tenant_scheduler_services_cycle(source='background_scheduler')" in source
    assert "process_all_tenant_incident_reminders(source='background_reminder_scheduler')" in source
    assert 'with tenant_execution_context(job.tenant_id):' in source
    assert 'IncidentReminder.query.join(Incident).filter(Incident.tenant_id == current_tenant_id()' in source
    assert 'Incident.query.filter(Incident.tenant_id == current_tenant_id()' in source


def test_audit_retention_is_scoped_to_active_tenant(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from datetime import timedelta
    from app import create_app
    from app.models import AuditLog, db, Tenant
    from app.routes import purge_audit_logs, tenant_execution_context, utcnow

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='round16-audit-lab', description='Audit tenant isolation')
        db.session.add(lab)
        db.session.flush()
        old = utcnow() - timedelta(days=400)
        default_log = AuditLog(tenant_id=default.id, occurred_at=old, operation_type='round16:default', username='system', actor_type='system')
        lab_log = AuditLog(tenant_id=lab.id, occurred_at=old, operation_type='round16:lab', username='system', actor_type='system')
        db.session.add_all([default_log, lab_log])
        db.session.commit()
        default_log_id, lab_log_id = default_log.id, lab_log.id
        with tenant_execution_context(default.id):
            deleted = purge_audit_logs(commit=True)
            assert deleted >= 1
        assert db.session.get(AuditLog, default_log_id) is None
        assert db.session.get(AuditLog, lab_log_id) is not None


def test_audit_admin_and_manual_purge_are_tenant_scoped_static():
    source = open('app/routes.py', encoding='utf-8').read()
    assert "q = AuditLog.query.filter(AuditLog.tenant_id == current_tenant_id())" in source
    assert "AuditLog.query.filter(AuditLog.tenant_id == current_tenant_id(), AuditLog.occurred_at < cutoff_dt)" in source
    region = source[source.index('def _audit_filtered_query_from_request():'):source.index("@bp.route('/admin/audit'")]
    assert 'AuditLog.tenant_id == current_tenant_id()' in region
