"""RC103: AlBot authoring is a reviewable tenant-scoped transaction, not autonomous AI execution."""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlsplit

import pytest


@pytest.fixture
def authoring_app(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'authoring.db'))
    for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
                'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR'):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv('SECRET_KEY', 'ALBOT-AUTHORING-TEST-SECRET-' * 3)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'TestAdminPasswordOnly123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    from app import create_app
    from app.models import db, Tenant, User, UserTenantRole, Setting
    from app.plugins.ai_chatbot import routes
    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').one()
        defaults = Tenant.query.filter_by(is_system_defaults=True).one()
        admin = User.query.filter_by(username='admin', auth_provider='local').one()
        reader = User(username='authoring-reader', auth_provider='local', role='reader',
                      tenant_id=tenant.id, default_tenant_id=tenant.id)
        db.session.add(reader)
        db.session.flush()
        db.session.add(UserTenantRole(user_id=reader.id, tenant_id=tenant.id, role='reader'))
        for source in (tenant, defaults):
            db.session.merge(Setting(key=f'tenant:{source.id}:plugin_ai_chatbot_enabled', value='1'))
        db.session.commit()
        app.config['AUTHORING_IDS'] = {'tenant': tenant.id, 'defaults': defaults.id,
                                       'admin': admin.id, 'reader': reader.id}
    class AI:
        def generate(self, messages, context):
            return json.dumps({
                'operation': 'create', 'name': 'Review Alerts',
                'steps': [
                    {'key': 'received', 'name': 'Receive alert', 'description': 'Register a new alert'},
                    {'key': 'triage', 'name': 'Perform triage', 'depends_on': ['received'],
                     'conditions': [{'kind': 'personal_data', 'negated': False}]},
                    {'key': 'close', 'name': 'Finish review', 'depends_on': ['triage'], 'required': False},
                ],
            })
    monkeypatch.setattr(routes, 'get_engine', lambda *args: AI())
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def client_for(app, role='admin', tenant='tenant'):
    client = app.test_client()
    ids = app.config['AUTHORING_IDS']
    with client.session_transaction() as values:
        values['_user_id'] = str(ids[role])
        values['_fresh'] = True
        values['active_tenant_id'] = ids[tenant]
        values['active_tenant_scope_enabled'] = True
    return client


def make_request(client, description='Crea un workflow Review Alerts con tre step: ricezione, triage dopo ricezione, chiusura dopo triage'):
    resp = client.post('/ai-chatbot/widget/ask', json={'question': description})
    return resp


def draft_token(response):
    assert response.status_code == 200, response.get_data(as_text=True)
    text = response.get_json()['answer']
    match = re.search(r'/ai-chatbot/workflows/([0-9a-f]{32})/preview', text)
    assert match, text
    return match.group(1)


def test_preview_and_export_do_not_write_until_explicit_confirmation(authoring_app):
    from app.models import db, ConfigLabel, IncidentWorkflowStep, Incident, Action
    from app.workflow_catalog import validate_catalog_payload
    from app.routes import workflow_step_condition_status, workflow_steps_for_incident
    client = client_for(authoring_app)
    token = draft_token(make_request(client))
    preview = client.get(f'/ai-chatbot/workflows/{token}/preview')
    assert preview.status_code == 200
    assert b'Review Alerts' in preview.data
    exported = client.get(f'/ai-chatbot/workflows/{token}/download')
    assert exported.status_code == 200
    assert 'attachment' in exported.headers.get('Content-Disposition', '')
    with authoring_app.app_context():
        portable = validate_catalog_payload(exported.get_json())
        assert [x['kind'] for x in portable['workflow']['steps'][1]['conditions']] == ['step_completed', 'personal_data']
        assert ConfigLabel.query.filter_by(kind='category', value='Review Alerts').count() == 0
        assert IncidentWorkflowStep.query.filter_by(tenant_id=authoring_app.config['AUTHORING_IDS']['tenant']).filter(
            IncidentWorkflowStep.description=='Register a new alert').count() == 0
    assert client.get(f'/ai-chatbot/workflows/{token}/apply').status_code == 405
    missing = client.post(f'/ai-chatbot/workflows/{token}/apply', data={}, follow_redirects=False)
    assert missing.status_code == 302
    with authoring_app.app_context():
        assert ConfigLabel.query.filter_by(kind='category', value='Review Alerts').count() == 0
    accepted = client.post(f'/ai-chatbot/workflows/{token}/apply', data={'confirm': 'yes'}, follow_redirects=False)
    assert accepted.status_code == 302
    with authoring_app.app_context():
        tid = authoring_app.config['AUTHORING_IDS']['tenant']
        category = ConfigLabel.query.filter_by(tenant_id=tid, kind='category', value='Review Alerts').one()
        steps = IncidentWorkflowStep.query.filter_by(tenant_id=tid, category_id=category.id).order_by(
            IncidentWorkflowStep.position).all()
        assert len(steps) == 3
        assert steps[1].condition_tokens()[0] == f'step_completed:{steps[0].action_label_id}'
        assert steps[2].condition_tokens()[0] == f'step_completed:{steps[1].action_label_id}'
        incident = Incident(tenant_id=tid, name='Example alert', reference='R-1',
                            categories=[category], category_order=str(category.id))
        db.session.add(incident)
        db.session.flush()
        incident.personal_data = True
        db.session.flush()
        assert steps[1] in workflow_steps_for_incident(incident)
        ok, detail = workflow_step_condition_status(steps[2], incident)
        assert not ok and any(x['token'].startswith('step_completed:') for x in detail)
        db.session.add(Action(incident_id=incident.id, label_id=steps[1].action_label_id,
                              when_at=datetime(2026, 11, 27, 8, 0), person_name='Admin'))
        db.session.flush()
        assert workflow_step_condition_status(steps[2], incident)[0]
        db.session.rollback()
    assert client.get(f'/ai-chatbot/workflows/{token}/download').status_code == 403


def test_export_only_cannot_be_applied_directly(authoring_app):
    from app.models import ConfigLabel
    client=client_for(authoring_app)
    answer=make_request(client, 'Scarica il JSON per un workflow Review Alerts con tre step di ricezione triage e chiusura')
    assert answer.status_code == 200
    token=re.search(r'/ai-chatbot/workflows/([0-9a-f]{32})/download', answer.get_json()['answer']).group(1)
    assert client.get(f'/ai-chatbot/workflows/{token}/download').status_code == 200
    assert client.post(f'/ai-chatbot/workflows/{token}/apply',data={'confirm':'yes'}).status_code == 302
    with authoring_app.app_context():
        assert ConfigLabel.query.filter_by(kind='category', value='Review Alerts').count()==0


def test_reader_cannot_generate_or_read_admins_draft(authoring_app):
    owner=client_for(authoring_app)
    token=draft_token(make_request(owner))
    viewer=client_for(authoring_app,'reader')
    denied=make_request(viewer)
    assert denied.status_code==403
    assert viewer.get(f'/ai-chatbot/workflows/{token}/preview').status_code==403
    assert viewer.get(f'/ai-chatbot/workflows/{token}/download').status_code==403
    assert viewer.post(f'/ai-chatbot/workflows/{token}/apply',data={'confirm':'yes'}).status_code==403


def test_system_defaults_superadmin_can_prepare_without_writing(authoring_app):
    from app.models import ConfigLabel
    client=client_for(authoring_app,tenant='defaults')
    token=draft_token(make_request(client))
    assert client.get(f'/ai-chatbot/workflows/{token}/preview').status_code==200
    with authoring_app.app_context():
        tid=authoring_app.config['AUTHORING_IDS']['defaults']
        assert ConfigLabel.query.filter_by(tenant_id=tid,kind='category',value='Review Alerts').first() is None


def test_authoring_intent_does_not_intercept_how_to_questions():
    from app.plugins.ai_chatbot.workflow_authoring import is_authoring_intent
    assert is_authoring_intent('Crea un workflow con due step e una dipendenza')
    assert is_authoring_intent('Update the workflow with new conditions')
    assert not is_authoring_intent('Come posso creare un workflow?')
    assert not is_authoring_intent('Quali categorie supporta la procedura?')
