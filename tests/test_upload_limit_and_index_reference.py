import io
import re
from datetime import datetime


def _configure_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'U' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def _csrf(html):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def _login_admin(client):
    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    response = client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    assert response.status_code in (302, 303)


def test_admin_can_configure_max_upload_size_and_oversized_workflow_import_is_rejected(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import Setting

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    page = client.get('/admin/other-configurations')
    html = page.get_data(as_text=True)
    assert 'name="max_upload_size_mb"' in html
    token = _csrf(html)
    response = client.post('/admin/other-configurations', data={
        '_csrf_token': token,
        'action': 'save',
        'application_external_url': 'http://localhost:8000',
        'application_timezone': 'Europe/Rome',
        'interface_language': 'auto',
        'max_upload_size_mb': '1',
        'audit_retention_months_part': '6',
        'audit_retention_days_part': '0',
        'audit_retention_hours_part': '0',
        'audit_retention_minutes_part': '0',
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Setting.query.get('max_upload_size_mb').value == '1'

    page = client.get('/admin/incident-workflows')
    token = _csrf(page.get_data(as_text=True))
    oversized = b'{"format":"cybersecurity-incident-registry.workflow.v1","items":[]}' + (b' ' * (2 * 1024 * 1024))
    response = client.post('/admin/incident-workflows/import/preview', data={
        '_csrf_token': token,
        'workflow_file': (io.BytesIO(oversized), 'workflow.json'),
    }, content_type='multipart/form-data')
    assert response.status_code == 413
    assert 'Upload troppo grande' in response.get_data(as_text=True)



def test_large_workflow_import_uses_server_side_preview_token(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import IncidentWorkflowStep, ConfigLabel

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    large_description = 'Descrizione workflow grande. ' * 56000
    payload = {
        'format': 'cybersecurity-incident-registry.workflow.v1',
        'workflow': {
            'scope': 'default',
            'category': None,
            'steps': [{
                'position': 12345,
                'action_label': {'kind': 'action_label', 'group': 'workflow-large', 'value': 'Azione import grande'},
                'description': large_description,
                'conditions': [],
                'required': True,
                'requires_notification': False,
                'required_notification_type': '',
            }],
        },
        'dependencies': {
            'labels': [{
                'kind': 'action_label',
                'group': 'workflow-large',
                'value': 'Azione import grande',
                'description': 'Label import grande',
                'max_completion_hours': 0,
                'default_exportable': True,
                'automatic_operations': '',
            }],
            'notification_types': [],
            'notification_templates': [],
            'form_templates': [],
        },
    }
    raw = __import__('json').dumps(payload, ensure_ascii=False).encode('utf-8')
    assert len(raw) > 1_400_000
    assert len(raw) < 2_000_000

    page = client.get('/admin/incident-workflows')
    token = _csrf(page.get_data(as_text=True))
    preview = client.post('/admin/incident-workflows/import/preview', data={
        '_csrf_token': token,
        'workflow_file': (io.BytesIO(raw), 'workflow-large.json'),
    }, content_type='multipart/form-data')
    assert preview.status_code == 200
    html = preview.get_data(as_text=True)
    assert 'Upload troppo grande' not in html
    assert 'name="import_token"' in html
    assert 'name="payload_b64"' not in html

    apply_token = _csrf(html)
    import_token_match = re.search(r'name="import_token" value="([^"]+)"', html)
    assert import_token_match, html[:500]
    applied = client.post('/admin/incident-workflows/import/apply', data={
        '_csrf_token': apply_token,
        'import_token': import_token_match.group(1),
    }, follow_redirects=True)
    assert applied.status_code == 200
    assert 'Workflow importato' in applied.get_data(as_text=True)
    with app.app_context():
        label = ConfigLabel.query.filter_by(kind='action_label', value='Azione import grande').one()
        step = IncidentWorkflowStep.query.filter_by(position=12345, action_label_id=label.id).one()
        assert step.description.startswith('Descrizione workflow grande.')

def test_index_uses_incident_reference_instead_of_compiler_column(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, Incident

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        inc = Incident(tenant_id=default.id, name='Incidente home riferimento', reference='REF-HOME-001', creator_name='Nome Compilatore Nascosto', creator_email='hidden@example.test', status='aperto')
        inc.start_at = datetime(2026, 6, 8, 10, 30)
        db.session.add(inc)
        db.session.commit()

    _login_admin(client)
    response = client.get('/?sort=reference&dir=asc')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'Riferimento' in html
    assert 'REF-HOME-001' in html
    assert 'Compilatore' not in html
    assert 'Nome Compilatore Nascosto' not in html
