"""Real HTTP regressions for installation-wide UI selection and stale AI tabs."""
import json
import re

import pytest
from werkzeug.datastructures import MultiDict


@pytest.fixture
def ui_app(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'ui.db'))
    for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
                'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR'):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv('SECRET_KEY', 'ui-test-' + 's' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'UIRegressionPassword123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '0')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    from app import create_app, db
    from app.auth import hash_password
    from app.models import Tenant, User, UserTenantRole
    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        ordinary = Tenant(name='ui-second-tenant')
        db.session.add(ordinary)
        db.session.flush()
        for role in ('admin', 'reader', 'writer', 'operator'):
            user = User(username='ui-' + role, auth_provider='local', name='UI ' + role,
                        tenant_id=ordinary.id, default_tenant_id=ordinary.id, role=role,
                        password_hash=hash_password('UIRegressionPassword123!'))
            db.session.add(user)
            db.session.flush()
            db.session.add(UserTenantRole(user_id=user.id, tenant_id=ordinary.id, role=role))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def csrf(page):
    html = page.get_data(as_text=True)
    match = (re.search(r'name="_csrf_token" value="([^"]+)"', html)
             or re.search(r'name="csrf-token" content="([^"]+)"', html))
    assert match, page.get_data(as_text=True)[:800]
    return match.group(1)


def login(app, username='admin'):
    client = app.test_client()
    page = client.get('/login', headers={'Accept-Language': 'it'})
    result = client.post('/login', data={'username': username,
        'password': 'UIRegressionPassword123!', '_csrf_token': csrf(page)})
    assert result.status_code in (302, 303)
    return client


def mode(app):
    from app.ui_settings import global_ui_mode
    with app.app_context():
        return global_ui_mode()


def test_new_ui_default_applies_to_fresh_login_and_old_database_without_setting(ui_app):
    from app.models import Setting, db
    from app.ui_settings import GLOBAL_UI_MODE_KEY
    with ui_app.app_context():
        assert db.session.get(Setting, GLOBAL_UI_MODE_KEY) is None
    assert mode(ui_app) == 'modern'
    page = ui_app.test_client().get('/login')
    assert page.status_code == 200
    assert 'cir-modern' in page.get_data(as_text=True)


def test_mode_changes_all_tenants_and_anonymous_login_and_is_audited(ui_app):
    from app.models import AuditLog, Setting, Tenant, db
    root = login(ui_app)
    other = login(ui_app, 'ui-admin')
    with ui_app.app_context():
        for tenant in Tenant.query.all():
            db.session.add(Setting(key=f'tenant:{tenant.id}:global_ui_mode', value='modern'))
        db.session.commit()
    response = root.post('/admin/interface', data={'mode': 'classic',
        '_csrf_token': csrf(root.get('/admin/interface'))})
    assert response.status_code == 303
    assert mode(ui_app) == 'classic'
    assert 'cir-classic' in other.get('/').get_data(as_text=True)
    assert 'cir-classic' in ui_app.test_client().get('/login').get_data(as_text=True)
    with ui_app.app_context():
        entry = AuditLog.query.filter_by(operation_type='admin:global_ui_mode_update').one()
        assert json.loads(entry.details) == {'scope': 'all-tenants-and-users',
                                             'previous': 'modern', 'mode': 'classic'}
    response = root.post('/admin/interface', data={'mode': 'modern',
        '_csrf_token': csrf(root.get('/admin/interface'))})
    assert response.status_code == 303
    assert 'cir-modern' in other.get('/').get_data(as_text=True)


def test_explicit_choice_survives_application_restart(ui_app):
    root = login(ui_app)
    root.post('/admin/interface', data={'mode': 'classic',
        '_csrf_token': csrf(root.get('/admin/interface'))})
    from app import create_app
    restarted = create_app()
    restarted.config['TESTING'] = True
    assert mode(restarted) == 'classic'
    assert 'cir-classic' in restarted.test_client().get('/login').get_data(as_text=True)


@pytest.mark.parametrize('role', ['admin', 'reader', 'writer', 'operator'])
def test_tenant_roles_cannot_read_or_change_global_mode(ui_app, role):
    client = login(ui_app, 'ui-' + role)
    page = client.get('/')
    assert '/admin/interface' not in page.get_data(as_text=True)
    assert client.get('/admin/interface').status_code == 403
    result = client.post('/admin/interface', data={'mode': 'classic', '_csrf_token': csrf(page)})
    assert result.status_code == 403
    assert mode(ui_app) == 'modern'


def test_global_mode_requires_login_and_csrf_and_rejects_ambiguous_values(ui_app):
    assert ui_app.test_client().get('/admin/interface').status_code == 302
    client = login(ui_app)
    assert client.post('/admin/interface', data={'mode': 'classic'}).status_code == 400
    token = csrf(client.get('/admin/interface'))
    for values in [[], ['unknown'], ['classic', 'modern']]:
        data = MultiDict([('_csrf_token', token)] + [('mode', value) for value in values])
        assert client.post('/admin/interface', data=data).status_code == 400
    assert mode(ui_app) == 'modern'


def test_superuser_can_switch_from_tenants_default_and_value_is_not_inherited(ui_app):
    from app.models import Setting, Tenant, db
    from app.tenant_default_settings import is_tenant_parameter
    from app.routes import tenant_setting_key
    client = login(ui_app)
    with ui_app.app_context():
        source_id = Tenant.query.filter_by(is_system_defaults=True).one().id
        assert not is_tenant_parameter('global_ui_mode')
        assert tenant_setting_key('global_ui_mode', source_id) == 'global_ui_mode'
        db.session.add(Setting(key=f'tenant:{source_id}:global_ui_mode', value='classic'))
        db.session.commit()
    with client.session_transaction() as session:
        session['active_tenant_id'] = source_id
        session['active_tenant_scope_enabled'] = True
    page = client.get('/admin/interface')
    assert page.status_code == 200
    assert mode(ui_app) == 'modern'
    result = client.post('/admin/interface', data={'mode': 'classic', '_csrf_token': csrf(page)})
    assert result.status_code == 303
    assert mode(ui_app) == 'classic'


def test_albot_stale_tenant_binding_is_rejected_before_provider(ui_app, monkeypatch):
    from app.models import Setting, Tenant, db
    from app.plugins.ai_chatbot import routes as chatbot
    client = login(ui_app, 'ui-admin')
    with ui_app.app_context():
        tid = Tenant.query.filter_by(name='ui-second-tenant').one().id
        db.session.add(Setting(key=f'tenant:{tid}:plugin_ai_chatbot_enabled', value='1'))
        db.session.commit()
    calls = []
    monkeypatch.setattr(chatbot, '_generate_chatbot_answer',
        lambda question: (calls.append(question) or 'Risposta di test', 'test'))
    token = csrf(client.get('/'))
    for stale in ('999999', 'x', '01', ''):
        result = client.post('/ai-chatbot/widget/ask', json={'question': 'Guida operativa'},
            headers={'X-CSRFToken': token, 'X-CIR-Tenant-ID': stale})
        assert result.status_code == 409
    assert calls == []
    result = client.post('/ai-chatbot/widget/ask', json={'question': 'Domanda corrente'},
        headers={'X-CSRFToken': token, 'X-CIR-Tenant-ID': str(tid)})
    assert result.status_code == 200
    assert calls == ['Domanda corrente']
    # Classic widget compatibility does not require the new context header.
    result = client.post('/ai-chatbot/widget/ask', json={'question': 'Domanda classica'},
        headers={'X-CSRFToken': token})
    assert result.status_code == 200
    assert calls[-1] == 'Domanda classica'


@pytest.mark.parametrize('endpoint', ['/ai-chatbot', '/ai-chatbot/widget/ask'])
@pytest.mark.parametrize('reason', ['expired', 'mfa_pending'])
def test_ai_session_policy_stops_provider_calls(ui_app, monkeypatch, endpoint, reason):
    import time
    from app.models import Setting, Tenant, db
    from app.plugins.ai_chatbot import routes as chatbot
    client = login(ui_app, 'ui-admin')
    with ui_app.app_context():
        tid = Tenant.query.filter_by(name='ui-second-tenant').one().id
        db.session.add(Setting(key=f'tenant:{tid}:plugin_ai_chatbot_enabled', value='1'))
        db.session.commit()
    calls = []
    monkeypatch.setattr(chatbot, '_generate_chatbot_answer',
        lambda question: (calls.append(question) or 'Test answer', 'test'))
    token = csrf(client.get('/'))
    with client.session_transaction() as session:
        if reason == 'expired':
            session['last_activity'] = time.time() - 86400
        else:
            session['mfa_user_id'] = int(session['_user_id'])
    result = client.post(endpoint, data={'question': 'Must not reach AI', '_csrf_token': token})
    assert result.status_code == (401 if endpoint.endswith('/ask') else 302)
    assert calls == []
    if endpoint.endswith('/ask'):
        assert result.is_json and result.json['ok'] is False


@pytest.mark.parametrize('payload', [[], 'question', 42, {'question': []}, {'question': {}}, {'question': 42}])
def test_ai_widget_rejects_malformed_payload_before_provider(ui_app, monkeypatch, payload):
    from app.models import Setting, Tenant, db
    from app.plugins.ai_chatbot import routes as chatbot
    client = login(ui_app, 'ui-admin')
    with ui_app.app_context():
        tid = Tenant.query.filter_by(name='ui-second-tenant').one().id
        db.session.add(Setting(key=f'tenant:{tid}:plugin_ai_chatbot_enabled', value='1'))
        db.session.commit()
    calls = []
    monkeypatch.setattr(chatbot, '_generate_chatbot_answer',
        lambda question: (calls.append(question) or 'Test answer', 'test'))
    token = csrf(client.get('/'))
    response = client.post('/ai-chatbot/widget/ask', json=payload, headers={'X-CSRFToken': token})
    assert response.status_code == 400
    assert response.is_json and response.json['ok'] is False
    assert calls == []
