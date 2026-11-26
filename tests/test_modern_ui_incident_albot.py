"""Real HTTP rendering of the approved incident and tenant-scoped AlBot UI.

Browser interaction is exercised separately by the CI screenshot workflow.
These regressions deliberately keep route authorization and template rendering.
"""
from datetime import datetime
from html.parser import HTMLParser

import pytest


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.form_depth = 0
        self.nested_forms = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))
        if tag == 'form':
            if self.form_depth:
                self.nested_forms += 1
            self.form_depth += 1

    def handle_endtag(self, tag):
        if tag == 'form':
            self.form_depth = max(0, self.form_depth - 1)

    def named(self, element_id):
        return [attrs for _tag, attrs in self.elements if attrs.get('id') == element_id]

    def classes(self, value):
        return [attrs for _tag, attrs in self.elements
                if value in attrs.get('class', '').split()]


@pytest.fixture
def incident_ui_app(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'incident-ui.db'))
    for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
                'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR'):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv('SECRET_KEY', 'MODERN-INCIDENT-TEST-' * 5)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'IncidentUiTestPassword123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.delenv('CIR_DISABLE_CSRF', raising=False)
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    from app import create_app
    from app.models import (db, Tenant, User, UserTenantRole, ConfigLabel,
                            Incident, IncidentWorkflowStep, Action, Setting)
    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').one()
        admin = User.query.filter_by(username='admin', auth_provider='local').one()
        reader = User(username='ui-procedure-reader', auth_provider='local', role='reader',
                      tenant_id=tenant.id, default_tenant_id=tenant.id)
        category = ConfigLabel(tenant_id=tenant.id, kind='category', value='UI procedure')
        labels = [ConfigLabel(tenant_id=tenant.id, kind='action_label',
                              value=f'UI action {n}', description=f'Reusable task {n}')
                  for n in range(1, 5)]
        db.session.add_all([reader, category, *labels])
        db.session.flush()
        db.session.add(UserTenantRole(user_id=reader.id, tenant_id=tenant.id, role='reader'))
        incident = Incident(tenant_id=tenant.id, creator_id=admin.id,
                            creator_name='UI test operator', creator_email='ui@example.invalid',
                            name='Incident <script>unsafe()</script>', reference='UI-DETAIL-01',
                            start_at=datetime(2026, 11, 22, 9, 42),
                            categories=[category], category_order=str(category.id))
        db.session.add(incident)
        db.session.flush()
        for n, label in enumerate(labels, start=1):
            db.session.add(IncidentWorkflowStep(tenant_id=tenant.id,
                category_id=category.id, action_label_id=label.id, position=n,
                description=f'Procedure description {n}', required=True))
        db.session.add(Action(incident_id=incident.id, label_id=labels[0].id,
                              when_at=datetime(2026, 11, 22, 9, 42),
                              person_name='UI test operator', description='First phase recorded'))
        db.session.merge(Setting(key=f'tenant:{tenant.id}:plugin_ai_chatbot_enabled', value='1'))
        db.session.merge(Setting(key=f'tenant:{tenant.id}:ai_chatbot_include_database_context', value='0'))
        db.session.commit()
        app.config['INCIDENT_UI_IDS'] = {'tenant': tenant.id, 'admin': admin.id,
            'reader': reader.id, 'incident': incident.id, 'labels': [row.id for row in labels]}
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def client_for(app, role='admin'):
    client = app.test_client()
    client.environ_base['HTTP_ACCEPT_LANGUAGE'] = 'it-IT,it;q=0.9'
    with client.session_transaction() as session:
        session['_user_id'] = str(app.config['INCIDENT_UI_IDS'][role])
        session['_fresh'] = True
        session['active_tenant_id'] = app.config['INCIDENT_UI_IDS']['tenant']
        session['active_tenant_scope_enabled'] = True
    return client


def set_mode(app, mode):
    from app.models import db, Setting
    from app.ui_settings import GLOBAL_UI_MODE_KEY
    with app.app_context():
        db.session.merge(Setting(key=GLOBAL_UI_MODE_KEY, value=mode))
        db.session.commit()


@pytest.mark.parametrize('mode', ['modern', 'classic'])
def test_incident_keeps_real_workflow_targets_and_post_forms(incident_ui_app, mode):
    set_mode(incident_ui_app, mode)
    ids = incident_ui_app.config['INCIDENT_UI_IDS']
    response = client_for(incident_ui_app).get(f'/incident/{ids["incident"]}')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page = Page(html)
    assert page.nested_forms == 0
    assert 'Incident &lt;script&gt;unsafe()&lt;/script&gt;' in html
    assert 'Incident <script>unsafe()</script>' not in html
    cards = page.classes('workflow-step-card')
    assert len(cards) == 4
    assert sum('done' in card['class'].split() for card in cards) == 1
    assert sum('first-incomplete' in card['class'].split() for card in cards) == 1
    tasks = page.classes('workflow-step-action')
    assert [int(task['data-action-label-id']) for task in tasks] == ids['labels']
    assert all(task['role'] == 'button' and task['tabindex'] == '0' for task in tasks)
    # A missing first phase must not create a new blanket sequential lock.
    assert all('disabled' not in task and task.get('aria-disabled') != 'true' for task in tasks)
    for section in ('incident-workflow', 'incident-main', 'incident-contacts',
                    'incident-consequences', 'incident-actions', 'incident-reminders',
                    'incident-documents', 'incident-forms'):
        assert len(page.named(section)) == 1
    # The built-in admin intentionally cannot send incident notifications.
    assert not page.named('incident-notifications')
    assert not any(attrs.get('href') == '#incident-notifications'
                   for _tag, attrs in page.elements)
    post_targets = {attrs.get('action', '') for tag, attrs in page.elements
                    if tag == 'form' and attrs.get('method', '').lower() == 'post'}
    assert '' in post_targets  # Existing edit form submits to the same incident.
    assert any('/clone' in value for value in post_targets)
    assert any(value.endswith('/action') for value in post_targets)
    assert any(tag == 'input' and attrs.get('name') == '_csrf_token'
               for tag, attrs in page.elements)
    assert bool(page.named('cir-incident-navigation')) == (mode == 'modern')
    assert bool(page.classes('cir-workflow-command')) == (mode == 'modern')


def test_modern_albot_is_tenant_scoped_and_does_not_render_legacy_widget(incident_ui_app):
    ids = incident_ui_app.config['INCIDENT_UI_IDS']
    response = client_for(incident_ui_app).get(f'/incident/{ids["incident"]}')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page = Page(html)
    assert page.named('cir-albot')[0]['data-tenant-id'] == str(ids['tenant'])
    assert page.named('cir-albot')[0]['data-ask-url'] == '/ai-chatbot/widget/ask'
    assert page.named('cir-albot-form')[0]['method'] == 'post'
    assert page.named('cir-albot-form')[0]['action'] == '/ai-chatbot/widget/ask'
    assert 'hidden' in page.named('cir-albot-panel')[0]
    assert not page.named('ai-chatbot-widget')
    assert not page.named('ai-chatbot-fab')
    assert 'ai-chatbot/albot-avatar.png' in html
    assert 'cir-albot-avatar' in html
    for control in ('cir-albot-open', 'cir-albot-close', 'cir-albot-back',
                    'cir-albot-expand', 'cir-albot-new-question', 'cir-albot-question'):
        assert len(page.named(control)) == 1
    assert 'non legge automaticamente l’incidente aperto' in html
    assert 'è disattivato per questo tenant' in html
    assert 'non vengono anonimizzati automaticamente' in html


def test_albot_context_reports_actual_snapshot_setting(incident_ui_app):
    from app.models import db, Setting
    ids = incident_ui_app.config['INCIDENT_UI_IDS']
    with incident_ui_app.app_context():
        db.session.merge(Setting(key=f'tenant:{ids["tenant"]}:ai_chatbot_include_database_context', value='1'))
        db.session.commit()
    response = client_for(incident_ui_app).get('/')
    assert response.status_code == 200
    assert 'è attivo per questo tenant' in response.get_data(as_text=True)


def test_classic_albot_and_plugin_off_behavior_are_preserved(incident_ui_app):
    from app.models import db, Setting
    ids = incident_ui_app.config['INCIDENT_UI_IDS']
    client = client_for(incident_ui_app)
    set_mode(incident_ui_app, 'classic')
    classic = Page(client.get('/').get_data(as_text=True))
    assert classic.named('ai-chatbot-widget')
    assert not classic.named('cir-albot-panel')
    set_mode(incident_ui_app, 'modern')
    with incident_ui_app.app_context():
        db.session.merge(Setting(key=f'tenant:{ids["tenant"]}:plugin_ai_chatbot_enabled', value='0'))
        db.session.commit()
    modern = Page(client.get('/').get_data(as_text=True))
    assert not modern.named('cir-albot-panel')
    assert not modern.named('cir-albot-open')
    anonymous = Page(incident_ui_app.test_client().get('/login').get_data(as_text=True))
    assert not anonymous.named('cir-albot-panel')


def test_reader_does_not_receive_new_write_shortcut(incident_ui_app):
    ids = incident_ui_app.config['INCIDENT_UI_IDS']
    response = client_for(incident_ui_app, 'reader').get(f'/incident/{ids["incident"]}')
    assert response.status_code == 200
    page = Page(response.get_data(as_text=True))
    assert not page.named('cir-incident-register-action')
    assert page.named('cir-albot-open')
    # Normal users retain the existing notification section and its navigation.
    assert page.named('incident-notifications')
    assert any(attrs.get('href') == '#incident-notifications'
               for _tag, attrs in page.elements)
    links = {attrs.get('href') for tag, attrs in page.elements if tag == 'a'}
    assert '/ai-chatbot/admin/plugins' not in links
    assert '/alfresco/admin/plugins' not in links


@pytest.mark.parametrize('mode', ['modern', 'classic'])
def test_defaults_tenant_keeps_ai_configuration_without_runtime_launchers(incident_ui_app, mode):
    from app.models import db, Setting, Tenant
    set_mode(incident_ui_app, mode)
    with incident_ui_app.app_context():
        source_id = Tenant.query.filter_by(is_system_defaults=True).one().id
        db.session.merge(Setting(key=f'tenant:{source_id}:plugin_ai_chatbot_enabled', value='1'))
        db.session.commit()
    client = client_for(incident_ui_app)
    with client.session_transaction() as session:
        session['active_tenant_id'] = source_id
    for route in ('/admin/interface', '/ai-chatbot/admin/plugins'):
        response = client.get(route)
        assert response.status_code == 200, (mode, route)
        page = Page(response.get_data(as_text=True))
        for element_id in ('cir-albot-open', 'cir-albot', 'cir-albot-panel',
                           'ai-chatbot-mobile-open', 'ai-chatbot-widget', 'ai-chatbot-fab'):
            assert not page.named(element_id), (mode, route, element_id)
        links = {attrs.get('href') for tag, attrs in page.elements if tag == 'a'}
        assert '/ai-chatbot' not in links
        assert '/ai-chatbot/admin/plugins' in links
        assert '/alfresco/admin/plugins' in links
