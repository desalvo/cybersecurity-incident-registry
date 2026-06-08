import re


def _configure_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'W' * 64)
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


def test_initial_setup_wizard_is_available_and_saves_groups(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import Setting

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    menu = client.get('/')
    assert 'Wizard setup iniziale' in menu.get_data(as_text=True)

    page = client.get('/admin/setup-wizard')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Cybersecurity Incident Registry' in html
    assert 'Versione 0.7.0-1' in html
    assert 'role="progressbar"' in html
    assert 'Salta questo gruppo' in html
    assert 'Riesegui da capo' in html

    token = _csrf(html)
    response = client.post('/admin/setup-wizard?step=general', data={
        '_csrf_token': token,
        'action': 'save_next',
        'application_external_url': 'https://registry.example.test',
        'application_timezone': 'Europe/Rome',
        'interface_language': 'it',
        'max_upload_size_mb': '64',
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Setting.query.get('application_external_url').value == 'https://registry.example.test'
        assert Setting.query.get('application_timezone').value == 'Europe/Rome'
        assert Setting.query.get('interface_language').value == 'it'
        assert Setting.query.get('max_upload_size_mb').value == '64'
        assert 'general' in Setting.query.get('setup_wizard_progress_json').value


def test_initial_setup_wizard_shows_packaged_release_even_with_stale_environment(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    monkeypatch.setenv('APP_VERSION', '0.6.0-41')
    monkeypatch.setenv('APP_BUILD', '20260530')
    from app import create_app

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    page = client.get('/admin/setup-wizard')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Versione 0.7.0-1' in html
    assert 'build 20260608' in html
    assert '0.6.0-41' not in html
    assert '20260530' not in html


def test_initial_setup_wizard_can_skip_and_finish(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import Setting

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    page = client.get('/admin/setup-wizard?step=organization')
    token = _csrf(page.get_data(as_text=True))
    skipped = client.post('/admin/setup-wizard?step=organization', data={
        '_csrf_token': token,
        'action': 'skip',
    }, follow_redirects=True)
    assert skipped.status_code == 200
    with app.app_context():
        assert 'organization' in Setting.query.get('setup_wizard_progress_json').value

    token = _csrf(skipped.get_data(as_text=True))
    finished = client.post('/admin/setup-wizard?step=documentation', data={
        '_csrf_token': token,
        'action': 'finish',
    }, follow_redirects=True)
    assert finished.status_code == 200
    with app.app_context():
        assert Setting.query.get('setup_wizard_completed').value == '1'


def test_initial_setup_wizard_uses_default_app_logo_and_exposes_extended_groups(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    page = client.get('/admin/setup-wizard')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert '/static/cir-application-logo.svg' in html
    assert '/logo' not in html.split('setup-wizard-brand', 1)[1].split('</div>', 1)[0]
    for label in ['Logo custom', 'LDAP', 'SSO / OAuth2', 'Motori di AI', 'Alfresco', 'Personale', 'Tenant']:
        assert label in html


def test_initial_setup_wizard_saves_identity_plugin_people_and_tenant_groups(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import Setting, Person, Tenant
    from app.routes import setting_value

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    _login_admin(client)

    page = client.get('/admin/setup-wizard?step=ldap')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/setup-wizard?step=ldap', data={
        '_csrf_token': token,
        'action': 'save_next',
        'ldap_uri': 'ldaps://ldap.example.test',
        'ldap_base_dn': 'dc=example,dc=test',
        'ldap_bind_dn': 'cn=reader,dc=example,dc=test',
        'ldap_bind_password': 'SecretLdapPassword',
        'ldap_user_filter': '(uid={uid})',
        'ldap_incident_search_filter': '(uid={uid})',
        'ldap_incident_search_attributes': 'uid,cn,mail',
        'ldap_incident_reference_attribute': 'cn',
        'ldap_incident_email_attribute': 'mail',
    }, follow_redirects=True)
    assert response.status_code == 200

    page = client.get('/admin/setup-wizard?step=sso')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/setup-wizard?step=sso', data={
        '_csrf_token': token,
        'action': 'save_next',
        'sso_profile_id': 'primary',
        'sso_enabled': '1',
        'sso_provider_name': 'Example SSO',
        'sso_authorization_url': 'https://sso.example.test/authorize',
        'sso_token_url': 'https://sso.example.test/token',
        'sso_userinfo_url': 'https://sso.example.test/userinfo',
        'sso_client_id': 'client-id',
        'sso_client_secret': 'client-secret',
        'sso_scopes': 'openid email profile',
        'sso_username_claim': 'preferred_username',
        'sso_email_claim': 'email',
        'sso_name_claim': 'name',
        'sso_subject_claim': 'sub',
        'sso_auto_create_users': '1',
        'sso_default_role': 'reader',
    }, follow_redirects=True)
    assert response.status_code == 200

    page = client.get('/admin/setup-wizard?step=ai')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/setup-wizard?step=ai', data={
        '_csrf_token': token,
        'action': 'save_next',
        'plugin_ai_chatbot_enabled': '1',
        'ai_chatbot_engine': 'ollama',
        'ai_chatbot_include_database_context': '1',
        'ai_chatbot_ollama_endpoint': 'http://ollama.example.test/api/chat',
        'ai_chatbot_ollama_model': 'llama3.1',
    }, follow_redirects=True)
    assert response.status_code == 200

    page = client.get('/admin/setup-wizard?step=alfresco')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/setup-wizard?step=alfresco', data={
        '_csrf_token': token,
        'action': 'save_next',
        'plugin_alfresco_enabled': '1',
        'alfresco_base_url': 'https://alfresco.example.test',
        'alfresco_username': 'api-user',
        'alfresco_password': 'alfresco-secret',
        'alfresco_site': 'cybersecurity',
        'alfresco_target_path': 'Cybersecurity Incident Registry',
        'alfresco_timeout': '45',
        'alfresco_verify_tls': '1',
    }, follow_redirects=True)
    assert response.status_code == 200

    page = client.get('/admin/setup-wizard?step=people')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/setup-wizard?step=people', data={
        '_csrf_token': token,
        'action': 'save_next',
        'wizard_people_lines': 'Mario Rossi <mario.rossi@example.test>\nAnna Bianchi; anna.bianchi@example.test',
    }, follow_redirects=True)
    assert response.status_code == 200

    page = client.get('/admin/setup-wizard?step=tenants')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/setup-wizard?step=tenants', data={
        '_csrf_token': token,
        'action': 'save_next',
        'wizard_tenant_name': 'research',
        'wizard_tenant_description': 'Research tenant',
        'wizard_tenant_clone_from': '1',
    }, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert setting_value('ldap_uri') == 'ldaps://ldap.example.test'
        assert 'Example SSO' in setting_value('sso_profiles_json')
        assert setting_value('plugin_ai_chatbot_enabled') == '1'
        assert setting_value('ai_chatbot_engine') == 'ollama'
        assert setting_value('plugin_alfresco_enabled') == '1'
        assert setting_value('alfresco_base_url') == 'https://alfresco.example.test'
        assert Person.query.filter_by(name='Mario Rossi').first() is not None
        assert Tenant.query.filter_by(name='research').first() is not None
