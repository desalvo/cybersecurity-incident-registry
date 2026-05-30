import re
from pathlib import Path


def _configure_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'E' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def _csrf(html):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def _login_admin(client):
    page = client.get('/login')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'AdminPassword123!',
        '_csrf_token': token,
    }, follow_redirects=True)
    assert response.status_code == 200


def test_external_recipient_auto_insertion_mechanisms_are_removed_from_routes():
    routes = Path('app/routes.py').read_text()
    assert 'ensure_external_recipients_from_addresses' not in routes
    assert 'ensure_incident_recipient_email_in_address_book' not in routes
    assert 'external_recipient_delete_all' in routes
    assert "action == 'delete_all'" in routes


def test_external_recipient_management_exposes_confirmed_remove_all_button():
    template = Path('app/templates/admin_external_recipients.html').read_text()
    assert 'Rimuovi tutto' in template
    assert 'delete_all' in template
    assert "confirm('Rimuovere tutti i destinatari esterni registrati" in template
    assert 'aggiunte automaticamente' not in template


def test_external_recipient_delete_all_removes_all_visible_recipients(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, ExternalRecipient, Tenant

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').one()
        db.session.add_all([
            ExternalRecipient(tenant_id=tenant.id, name='Alpha', email='alpha@example.test'),
            ExternalRecipient(tenant_id=tenant.id, name='Beta', email='beta@example.test'),
        ])
        db.session.commit()
        assert ExternalRecipient.query.count() == 2

    page = client.get('/admin/external-recipients')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/external-recipients', data={
        '_csrf_token': token,
        'action': 'delete_all',
    }, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Rimossi 2 destinatari esterni dalla rubrica.' in html
    assert 'Nessun destinatario esterno configurato.' in html

    with app.app_context():
        assert ExternalRecipient.query.count() == 0


def test_notification_preview_explains_manual_addresses_are_not_saved():
    preview = Path('app/templates/notification_preview.html').read_text()
    assert 'non vengono aggiunti automaticamente alla rubrica' in preview
    assert 'aggiunti automaticamente alla rubrica usando il Riferimento' not in preview
