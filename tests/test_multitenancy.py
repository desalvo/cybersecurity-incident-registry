import re


def _configure_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'M' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def _csrf(html):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def test_bootstrap_creates_default_tenant_and_superuser_admin(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import Tenant, User, ConfigLabel

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').one()
        admin = User.query.filter_by(username='admin', auth_provider='local').one()
        assert admin.role == 'superuser'
        assert admin.tenant_id == tenant.id
        assert ConfigLabel.query.filter_by(tenant_id=tenant.id).count() > 0


def test_superuser_can_create_tenant_by_cloning_default_config(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import Tenant, ConfigLabel, Setting

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})

    page = client.get('/admin/tenants')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/tenants', data={
        '_csrf_token': token,
        'action': 'create',
        'name': 'tenant-lab',
        'description': 'Tenant laboratorio',
        'clone_from_tenant_id': '1',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'tenant-lab' in response.data

    with app.app_context():
        tenant = Tenant.query.filter_by(name='tenant-lab').one()
        assert ConfigLabel.query.filter_by(tenant_id=tenant.id).count() > 0
        assert Setting.query.filter(Setting.key.startswith(f'tenant:{tenant.id}:')).count() > 10
        from app.models import db
        assert db.session.get(Setting, f'tenant:{tenant.id}:application_timezone') is None
        assert db.session.get(Setting, f'tenant:{tenant.id}:application_external_url') is None


def test_admin_menu_and_user_form_expose_tenant_management():
    base = open('app/templates/base.html', encoding='utf-8').read()
    users = open('app/templates/admin_users.html', encoding='utf-8').read()
    tenants = open('app/templates/admin_tenants.html', encoding='utf-8').read()
    assert "url_for('main.admin_tenants')" in base
    assert 'current_user.role==\'superuser\'' in base
    assert 'name="tenant_id"' in users
    assert 'role_options' in users
    assert 'class="user-record-card"' in users
    assert 'Aggiungi/Aggiorna tenant' in users
    assert 'u.is_builtin_admin' in users
    assert 'Clona configurazioni da' in tenants
    assert 'Il tenant default non può essere eliminato' in open('app/routes.py', encoding='utf-8').read()


def test_active_tenant_uses_user_default_tenant(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, User
    from app.routes import active_tenant_id, upsert_user_tenant_role

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='lab', description='Laboratorio')
        db.session.add(lab)
        db.session.flush()
        lab_id = lab.id
        user = User(username='multi', auth_provider='local', role='reader', tenant_id=default.id, default_tenant_id=lab_id)
        db.session.add(user)
        db.session.flush()
        upsert_user_tenant_role(user, default.id, 'reader')
        upsert_user_tenant_role(user, lab.id, 'writer')
        db.session.commit()

    with app.test_request_context('/'):
        with app.app_context():
            from flask_login import login_user
            user = User.query.filter_by(username='multi').one()
            login_user(user)
            assert active_tenant_id() == lab_id


def test_admin_users_template_exposes_default_tenant_selector():
    users = open('app/templates/admin_users.html', encoding='utf-8').read()
    assert 'Tenant attivo predefinito' in users
    assert 'name="default_tenant_id"' in users
    assert 'user_default_tenant_options' in users


def test_user_default_tenant_schema_migration_is_idempotent_static():
    source = open('app/__init__.py', encoding='utf-8').read()
    assert 'ALTER TABLE "user" ADD COLUMN default_tenant_id INTEGER' in source
    assert 'UPDATE \\\"user\\\" SET default_tenant_id = tenant_id' in source
    assert "username <> 'admin'" in source


def test_tenant_switch_filters_index_immediately_for_superuser(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, Incident
    from datetime import datetime

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='lab', description='Laboratorio')
        db.session.add(lab)
        db.session.flush()
        inc_default = Incident(tenant_id=default.id, name='Incidente default', reference='REF-default', creator_name='Admin', creator_email='admin@example.test', status='aperto')
        inc_default.start_at = datetime(2026, 1, 1, 10, 0)
        inc_lab = Incident(tenant_id=lab.id, name='Incidente lab', reference='REF-lab', creator_name='Admin', creator_email='admin@example.test', status='aperto')
        inc_lab.start_at = datetime(2026, 1, 2, 10, 0)
        db.session.add_all([inc_default, inc_lab])
        db.session.commit()
        lab_id = lab.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})

    page = client.get('/')
    html = page.get_data(as_text=True)
    token = _csrf(html)
    assert 'Incidente default' in html
    assert 'Incidente lab' not in html

    response = client.post('/admin/tenants/active', data={'active_tenant_id': str(lab_id), '_csrf_token': token, 'next': '/'}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'Incidente lab' in html
    assert 'Incidente default' not in html


def test_superuser_can_move_incident_between_tenants(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, Incident, ConfigLabel, Person, Recommendation, Action
    from datetime import datetime

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='lab', description='Laboratorio')
        db.session.add(lab)
        db.session.flush()
        severity = ConfigLabel(tenant_id=default.id, kind='severity', value='Grave', group='default')
        category = ConfigLabel(tenant_id=default.id, kind='category', value='Phishing', group='default')
        data_type = ConfigLabel(tenant_id=default.id, kind='data_type', value='Email', group='default')
        action_label = ConfigLabel(tenant_id=default.id, kind='action_label', value='Analisi move', group='default')
        person = Person(tenant_id=default.id, name='Mario Rossi', email='mario@example.test', group='personale')
        rec = Recommendation(tenant_id=default.id, text='Cambiare password')
        db.session.add_all([severity, category, data_type, action_label, person, rec])
        db.session.flush()
        inc = Incident(tenant_id=default.id, name='Da spostare', reference='REF-move', creator_name='Admin', creator_email='admin@example.test', status='aperto', severity=severity)
        inc.start_at = datetime(2026, 1, 3, 10, 0)
        inc.categories = [category]
        inc.data_types = [data_type]
        inc.people = [person]
        inc.recommendations = [rec]
        inc.actions = [Action(when_at=datetime(2026, 1, 3, 11, 0), person_name='Admin', label=action_label, description='Analisi iniziale')]
        db.session.add(inc)
        db.session.commit()
        inc_id = inc.id
        lab_id = lab.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/')
    html = page.get_data(as_text=True)
    assert 'tenant-move-menu' in html
    assert 'tenant-move-search' in html
    assert 'Da spostare' in html
    token = _csrf(html)
    response = client.post(f'/incident/{inc_id}/move-tenant', data={'target_tenant_id': str(lab_id), '_csrf_token': token, 'next': '/'}, follow_redirects=True)
    assert response.status_code == 200
    moved_html = response.get_data(as_text=True)
    assert 'Incidente spostato nel tenant lab' in moved_html
    assert 'Da spostare' in moved_html

    with app.app_context():
        inc = db.session.get(Incident, inc_id)
        assert inc.tenant_id == lab_id
        assert inc.severity.tenant_id == lab_id
        assert [c.tenant_id for c in inc.categories] == [lab_id]
        assert [d.tenant_id for d in inc.data_types] == [lab_id]
        assert [p.tenant_id for p in inc.people] == [lab_id]
        assert [r.tenant_id for r in inc.recommendations] == [lab_id]
        assert inc.actions[0].label.tenant_id == lab_id


def test_delete_tenant_removes_templates_before_labels(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, ConfigLabel, IncidentTemplate, IncidentWorkflowStep

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        tenant = Tenant(name='to-delete', description='Tenant eliminabile')
        db.session.add(tenant)
        db.session.flush()
        severity = ConfigLabel(tenant_id=tenant.id, kind='severity', value='Critica', group='default')
        action = ConfigLabel(tenant_id=tenant.id, kind='action_label', value='Analisi move', group='default')
        db.session.add_all([severity, action])
        db.session.flush()
        db.session.add(IncidentTemplate(tenant_id=tenant.id, name='Template legacy', severity_id=severity.id))
        db.session.add(IncidentWorkflowStep(tenant_id=tenant.id, category_id=None, action_label_id=action.id, position=10))
        db.session.commit()
        tenant_id = tenant.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/admin/tenants')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/tenants', data={'_csrf_token': token, 'action': 'delete', 'tenant_id': str(tenant_id)}, follow_redirects=True)
    assert response.status_code == 200
    assert 'Tenant eliminato' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Tenant, tenant_id) is None
        assert ConfigLabel.query.filter_by(tenant_id=tenant_id).count() == 0
        assert IncidentTemplate.query.filter_by(tenant_id=tenant_id).count() == 0
        assert IncidentWorkflowStep.query.filter_by(tenant_id=tenant_id).count() == 0


def test_clone_tenant_config_does_not_create_spurious_source_workflows(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, ConfigLabel, IncidentWorkflowStep
    from app.routes import clone_tenant_config

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        source = Tenant(name='source', description='Sorgente')
        dest = Tenant(name='dest', description='Destinazione')
        db.session.add_all([source, dest])
        db.session.flush()
        action = ConfigLabel(tenant_id=source.id, kind='action_label', value='Analisi sorgente', group='azioni')
        db.session.add(action)
        db.session.flush()
        db.session.add(IncidentWorkflowStep(tenant_id=source.id, category_id=None, action_label_id=action.id, position=10))
        db.session.commit()
        source_id, dest_id = source.id, dest.id

        clone_tenant_config(source_id, dest_id)
        db.session.commit()

        assert IncidentWorkflowStep.query.filter_by(tenant_id=source_id).count() == 1
        assert IncidentWorkflowStep.query.filter_by(tenant_id=dest_id).count() == 1
        assert IncidentWorkflowStep.query.filter(IncidentWorkflowStep.tenant_id.is_(None)).count() == 0


def test_workflow_admin_can_delete_entire_current_tenant_workflow(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, IncidentWorkflowStep

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        before = IncidentWorkflowStep.query.filter_by(tenant_id=default.id, category_id=None).count()
        assert before > 0

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/admin/incident-workflows')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/incident-workflows', data={'_csrf_token': token, 'action': 'delete_workflow', 'delete_scope': 'default'}, follow_redirects=True)
    assert response.status_code == 200
    assert 'Flusso eliminato per Flusso di default' in response.get_data(as_text=True)
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        assert IncidentWorkflowStep.query.filter_by(tenant_id=default.id, category_id=None).count() == 0


def test_menu_tenant_switcher_posts_with_current_page_reload_hook():
    base = open('app/templates/base.html', encoding='utf-8').read()
    js = open('app/static/app.js', encoding='utf-8').read()
    assert 'data-tenant-switcher-form' in base
    assert 'data-tenant-switch-select' in base
    assert 'data-tenant-switch-next' in base
    assert 'initTenantSwitcher()' in js
    assert "window.location.pathname + window.location.search + window.location.hash" in js
    assert "select.addEventListener('change', submitSwitch)" in js


def test_incident_move_control_is_only_on_index_with_searchable_dropdown():
    index = open('app/templates/index.html', encoding='utf-8').read()
    detail = open('app/templates/incident_detail.html', encoding='utf-8').read()
    js = open('app/static/app.js', encoding='utf-8').read()
    assert 'tenant_move_control' in index
    assert 'tenant-move-button' in index
    assert 'tenant-move-search' in index
    assert 'incident_move_tenant' in index
    assert 'current_user_is_superuser' in index
    assert 'incident_move_tenant' not in detail
    assert 'initIncidentTenantMoveMenus' in js
    assert "options.forEach" in js


def test_tenant_switch_redirects_with_see_other_and_updates_session(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        lab = Tenant(name='reload-lab', description='Tenant reload')
        db.session.add(lab)
        db.session.commit()
        lab_id = lab.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})

    page = client.get('/?q=abc')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/tenants/active', data={
        'active_tenant_id': str(lab_id),
        '_csrf_token': token,
        'next': '/?q=abc#main-content',
    }, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['Location'].endswith('/?q=abc#main-content')
    with client.session_transaction() as sess:
        assert sess['active_tenant_id'] == lab_id
        assert sess['active_tenant_scope_enabled'] is True


def test_clone_tenant_config_reuses_existing_tenant_objects(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, ConfigLabel, IncidentWorkflowStep, NotificationType, NotificationTemplate, IncidentTemplate, ExternalRecipient, BackupJob
    from app.routes import clone_tenant_config

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        source = Tenant(name='source-idempotent', description='Sorgente')
        dest = Tenant(name='dest-idempotent', description='Destinazione')
        db.session.add_all([source, dest])
        db.session.flush()
        action = ConfigLabel(tenant_id=source.id, kind='action_label', value='Azione idempotente', group='azioni')
        severity = ConfigLabel(tenant_id=source.id, kind='severity', value='Alta idempotente', group='gravita')
        db.session.add_all([action, severity])
        db.session.flush()
        db.session.add(IncidentWorkflowStep(tenant_id=source.id, category_id=None, action_label_id=action.id, position=10, description='Step'))
        db.session.add(NotificationType(tenant_id=source.id, code='notice_idempotent', label='Avviso idempotente'))
        db.session.add(NotificationTemplate(tenant_id=source.id, kind='notice_idempotent', name='Template idempotente', subject='Oggetto', body='Corpo', action_label_id=action.id))
        db.session.add(IncidentTemplate(tenant_id=source.id, name='Template incidente idempotente', severity_id=severity.id))
        db.session.add(ExternalRecipient(tenant_id=source.id, name='CSIRT', email='csirt-idempotent@example.test'))
        db.session.add(BackupJob(tenant_id=source.id, name='Backup idempotente'))
        db.session.commit()
        source_id, dest_id = source.id, dest.id

        clone_tenant_config(source_id, dest_id)
        clone_tenant_config(source_id, dest_id)
        db.session.commit()

        assert ConfigLabel.query.filter_by(tenant_id=dest_id, kind='action_label', value='Azione idempotente').count() == 1
        assert ConfigLabel.query.filter_by(tenant_id=dest_id, kind='severity', value='Alta idempotente').count() == 1
        assert IncidentWorkflowStep.query.filter_by(tenant_id=dest_id, position=10, description='Step').count() == 1
        assert NotificationType.query.filter_by(tenant_id=dest_id, code='notice_idempotent').count() == 1
        assert NotificationTemplate.query.filter_by(tenant_id=dest_id, kind='notice_idempotent', name='Template idempotente').count() == 1
        assert IncidentTemplate.query.filter_by(tenant_id=dest_id, name='Template incidente idempotente').count() == 1
        assert ExternalRecipient.query.filter_by(tenant_id=dest_id, email='csirt-idempotent@example.test').count() == 1
        assert BackupJob.query.filter_by(tenant_id=dest_id, name='Backup idempotente').count() == 1


def test_new_cross_tenant_workflow_destination_reuses_existing_category(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, ConfigLabel
    from app.routes import create_new_workflow_destination_for_clone

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        source = Tenant(name='source-workflow-new', description='Sorgente')
        dest = Tenant(name='dest-workflow-new', description='Destinazione')
        db.session.add_all([source, dest])
        db.session.flush()
        src_category = ConfigLabel(tenant_id=source.id, kind='category', value='Categoria condivisa', group='incidenti')
        dst_category = ConfigLabel(tenant_id=dest.id, kind='category', value='Categoria condivisa', group='incidenti')
        db.session.add_all([src_category, dst_category])
        db.session.flush()
        first_id, first_err = create_new_workflow_destination_for_clone(src_category.id, source.id, dest.id)
        second_id, second_err = create_new_workflow_destination_for_clone(src_category.id, source.id, dest.id)
        db.session.commit()

        assert first_err is None
        assert second_err is None
        assert first_id == dst_category.id
        assert second_id == dst_category.id
        assert ConfigLabel.query.filter_by(tenant_id=dest.id, kind='category', value='Categoria condivisa').count() == 1


def test_admin_users_search_can_filter_by_tenant(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, User
    from app.routes import upsert_user_tenant_role

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='search-lab', description='Tenant search')
        db.session.add(lab)
        db.session.flush()
        u_default = User(username='tenant-default-user', auth_provider='local', role='disabled', tenant_id=default.id, default_tenant_id=default.id)
        u_lab = User(username='tenant-lab-user', auth_provider='local', role='disabled', tenant_id=lab.id, default_tenant_id=lab.id)
        db.session.add_all([u_default, u_lab])
        db.session.flush()
        upsert_user_tenant_role(u_default, default.id, 'reader')
        upsert_user_tenant_role(u_lab, lab.id, 'reader')
        db.session.commit()
        lab_id = lab.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    response = client.get(f'/admin/users?tenant_id={lab_id}')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="tenant_id"' in html
    assert 'tenant-lab-user' in html
    assert 'tenant-default-user' not in html



def test_admin_users_search_form_has_separate_fields():
    users = open('app/templates/admin_users.html', encoding='utf-8').read()
    assert 'class="user-search-form user-search-form-detailed"' in users
    assert 'name="username"' in users
    assert 'name="name"' in users
    assert 'name="email"' in users
    assert 'name="auth_provider"' in users
    assert 'name="role"' in users
    assert 'Tenant di appartenenza' in users
    assert 'searchable_tenants' in users


def test_admin_users_search_filters_by_separate_fields(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, User
    from app.routes import hash_password, upsert_user_tenant_role

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='separate-fields-lab', description='Tenant ricerca dettagliata')
        db.session.add(lab)
        db.session.flush()
        matching = User(username='ricerca-campi', name='Mario Ricercato', email='ricerca@example.test', auth_provider='local', role='disabled', tenant_id=lab.id, default_tenant_id=lab.id, password_hash=hash_password('DummyPassword123!'))
        other = User(username='altro-campi', name='Mario Altro', email='altro@example.test', auth_provider='local', role='disabled', tenant_id=default.id, default_tenant_id=default.id, password_hash=hash_password('DummyPassword123!'))
        db.session.add_all([matching, other])
        db.session.flush()
        upsert_user_tenant_role(matching, lab.id, 'writer')
        upsert_user_tenant_role(other, default.id, 'reader')
        db.session.commit()
        lab_id = lab.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    response = client.get(f'/admin/users?username=ricerca&name=Mario&email=ricerca%40example.test&auth_provider=local&role=writer&tenant_id={lab_id}')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'ricerca-campi' in html
    assert 'altro-campi' not in html
    assert 'value="ricerca"' in html
    assert 'value="Mario"' in html
    assert 'value="ricerca@example.test"' in html
    assert 'value="local" selected' in html
    assert 'value="writer" selected' in html

def test_index_paginates_incidents_and_exposes_bulk_selection(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, Incident
    from datetime import datetime

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        db.session.add(Tenant(name='page-lab', description='Tenant per bulk'))
        db.session.flush()
        for i in range(25):
            inc = Incident(tenant_id=default.id, name=f'Incidente paginazione {i:02d}', reference=f'PAGE-{i:02d}', creator_name='Admin', creator_email='admin@example.test', status='aperto')
            inc.start_at = datetime(2026, 1, 1, 10, i % 60)
            db.session.add(inc)
        db.session.commit()

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page1 = client.get('/')
    html1 = page1.get_data(as_text=True)
    assert 'Incidenti per pagina' in html1
    assert 'data-incident-select-all' in html1
    assert '/incidents/bulk/move-tenant' in html1
    assert 'bulk-tenant-move-menu' in html1
    assert 'Sposta selezionati' in html1
    assert 'bulk-tenant-search' not in html1
    assert 'bulk-tenant-select' not in html1
    assert '/incidents/bulk/delete' in html1
    assert 'Incidente paginazione 24' in html1
    assert 'Incidente paginazione 05' in html1
    assert 'Incidente paginazione 04' not in html1
    page2 = client.get('/?page=2')
    html2 = page2.get_data(as_text=True)
    assert 'Incidente paginazione 04' in html2


def test_bulk_move_and_delete_incidents(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, Incident
    from datetime import datetime

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='bulk-lab', description='Tenant bulk')
        db.session.add(lab)
        db.session.flush()
        inc1 = Incident(tenant_id=default.id, name='Bulk move 1', reference='BM-1', creator_name='Admin', creator_email='admin@example.test', status='aperto')
        inc1.start_at = datetime(2026, 1, 2, 10, 0)
        inc2 = Incident(tenant_id=default.id, name='Bulk move 2', reference='BM-2', creator_name='Admin', creator_email='admin@example.test', status='aperto')
        inc2.start_at = datetime(2026, 1, 2, 11, 0)
        db.session.add_all([inc1, inc2])
        db.session.commit()
        inc1_id, inc2_id, lab_id = inc1.id, inc2.id, lab.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/incidents/bulk/move-tenant', data={
        '_csrf_token': token,
        'incident_ids': [str(inc1_id), str(inc2_id)],
        'target_tenant_id': str(lab_id),
        'next': '/',
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Incident, inc1_id).tenant_id == lab_id
        assert db.session.get(Incident, inc2_id).tenant_id == lab_id

    token = _csrf(response.get_data(as_text=True))
    delete_response = client.post('/incidents/bulk/delete', data={
        '_csrf_token': token,
        'incident_ids': [str(inc1_id), str(inc2_id)],
        'next': '/',
    }, follow_redirects=True)
    assert delete_response.status_code == 200
    with app.app_context():
        assert db.session.get(Incident, inc1_id) is None
        assert db.session.get(Incident, inc2_id) is None


def test_tenant_clone_absorbs_legacy_global_labels_without_duplicates(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, ConfigLabel

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        existing = ConfigLabel.query.filter_by(tenant_id=default.id, kind='category').first()
        assert existing is not None
        # Simula un backup/migrazione legacy con label globali non tenantizzate
        # aventi la stessa chiave funzionale della label del tenant default.
        db.session.add(ConfigLabel(tenant_id=None, kind=existing.kind, group=existing.group, value=existing.value, description='legacy global'))
        db.session.commit()
        source_id = default.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/admin/tenants')
    token = _csrf(page.get_data(as_text=True))
    response = client.post('/admin/tenants', data={
        '_csrf_token': token,
        'action': 'create',
        'name': 'tenant-clone-dedupe',
        'description': 'Tenant dedupe',
        'clone_from_tenant_id': str(source_id),
    }, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        cloned = Tenant.query.filter_by(name='tenant-clone-dedupe').one()
        keys = [
            (label.kind, label.value)
            for label in ConfigLabel.query.filter_by(tenant_id=cloned.id).all()
        ]
        assert len(keys) == len(set(keys))
        assert ConfigLabel.query.filter(ConfigLabel.tenant_id.is_(None)).count() == 0


def test_admin_labels_page_shows_only_active_tenant_labels_for_superuser(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, ConfigLabel

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        lab = Tenant(name='lab-labels', description='Lab labels')
        db.session.add(lab)
        db.session.flush()
        db.session.add(ConfigLabel(tenant_id=lab.id, kind='category', value='Categoria solo lab', group='default'))
        db.session.add(ConfigLabel(tenant_id=default.id, kind='category', value='Categoria solo default', group='default'))
        db.session.commit()
        lab_id = lab.id

    login_page = client.get('/login')
    token = _csrf(login_page.get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/')
    token = _csrf(page.get_data(as_text=True))
    client.post('/admin/tenants/active', data={'active_tenant_id': str(lab_id), '_csrf_token': token, 'next': '/admin/labels'}, follow_redirects=False)
    labels_page = client.get('/admin/labels').get_data(as_text=True)
    assert 'Categoria solo lab' in labels_page
    assert 'Categoria solo default' not in labels_page


def test_move_incident_to_tenant_preserves_category_order(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, ConfigLabel, Incident
    from app.routes import move_incident_to_tenant, incident_ordered_categories

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        source = Tenant.query.filter_by(name='default').one()
        target = Tenant(name='tenant-target-order', description='Tenant destinazione')
        db.session.add(target)
        db.session.flush()
        cat_a = ConfigLabel(tenant_id=source.id, kind='category', value='Ordine A')
        cat_b = ConfigLabel(tenant_id=source.id, kind='category', value='Ordine B')
        db.session.add_all([cat_a, cat_b])
        db.session.flush()
        inc = Incident(tenant_id=source.id, name='Incidente ordine categorie', reference='ORD-1')
        inc.categories = [cat_a, cat_b]
        inc.category_order = f'{cat_b.id},{cat_a.id}'
        db.session.add(inc)
        db.session.flush()

        assert move_incident_to_tenant(inc, target.id) is True
        db.session.flush()

        ordered_values = [label.value for label in incident_ordered_categories(inc)]
        ordered_ids = [int(raw) for raw in inc.category_order.split(',') if raw]
        assert inc.tenant_id == target.id
        assert ordered_values == ['Ordine B', 'Ordine A']
        assert ordered_ids == [label.id for label in incident_ordered_categories(inc)]
        assert all(label.tenant_id == target.id for label in inc.categories)


def test_tenant_switcher_hidden_on_incident_create_and_edit_pages():
    base = open('app/templates/base.html', encoding='utf-8').read()
    assert "tenant_switch_hidden_endpoints = ['main.incident_new', 'main.incident_detail']" in base
    assert 'request.endpoint not in tenant_switch_hidden_endpoints' in base


def test_admin_user_update_redirect_reopens_card_and_preserves_filters(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, User
    from app.routes import hash_password, upsert_user_tenant_role

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        user = User(username='persist-card', email='old@example.test', auth_provider='local', role='disabled', tenant_id=default.id, default_tenant_id=default.id, password_hash=hash_password('DummyPassword123!'))
        db.session.add(user)
        db.session.flush()
        upsert_user_tenant_role(user, default.id, 'reader')
        db.session.commit()
        uid = user.id

    token = _csrf(client.get('/login').get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/admin/users?username=persist')
    token = _csrf(page.get_data(as_text=True))
    response = client.post(f'/admin/user/{uid}/role', data={
        '_csrf_token': token,
        'email': 'new@example.test',
        'default_tenant_id': '',
        'return_query': 'username=persist',
    }, follow_redirects=False)
    assert response.status_code in (302, 303)
    location = response.headers['Location']
    assert 'username=persist' in location
    assert f'open_user={uid}' in location
    assert f'#user-card-{uid}' in location
    reopened = client.get(location)
    html = reopened.get_data(as_text=True)
    assert f'id="user-card-{uid}" open' in html
    assert 'value="persist"' in html


def test_superuser_can_reset_local_user_password_from_admin_users(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, User
    from app.auth import verify_password
    from app.routes import hash_password, upsert_user_tenant_role

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        user = User(username='local-reset', email='reset@example.test', auth_provider='local', role='disabled', tenant_id=default.id, default_tenant_id=default.id, password_hash=hash_password('OldPassword123!'))
        db.session.add(user)
        db.session.flush()
        upsert_user_tenant_role(user, default.id, 'reader')
        db.session.commit()
        uid = user.id

    token = _csrf(client.get('/login').get_data(as_text=True))
    client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!', '_csrf_token': token})
    page = client.get('/admin/users?username=local-reset')
    html = page.get_data(as_text=True)
    token = _csrf(html)
    assert 'admin_user_password' in html or f'/admin/user/{uid}/password' in html
    response = client.post(f'/admin/user/{uid}/password', data={
        '_csrf_token': token,
        'new_password': 'NuovaCredenziale123!',
        'new_password2': 'NuovaCredenziale123!',
        'return_query': 'username=local-reset',
    }, follow_redirects=False)
    assert response.status_code in (302, 303)
    assert f'open_user={uid}' in response.headers['Location']
    with app.app_context():
        user = db.session.get(User, uid)
        assert verify_password(user.password_hash, 'NuovaCredenziale123!')
