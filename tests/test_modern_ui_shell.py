"""HTTP rendering regressions for the approved UI and the retained classic UI."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import re

import pytest


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def links(self):
        return {attrs['href'] for tag, attrs in self.elements
                if tag == 'a' and 'href' in attrs}


@pytest.fixture
def ui_shell_app(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'ui.db'))
    for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
                'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR'):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv('SECRET_KEY', 'UI-SHELL-TEST-' * 6)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'UiShellTestPassword123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('CIR_DISABLE_CSRF', raising=False)
    from app import create_app
    from app.models import db, Tenant, User, UserTenantRole, Incident
    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').one()
        admin = User.query.filter_by(username='admin', auth_provider='local').one()
        reader = User(username='ui-reader', auth_provider='local', role='reader',
                      tenant_id=tenant.id, default_tenant_id=tenant.id)
        db.session.add(reader)
        db.session.flush()
        db.session.add(UserTenantRole(user_id=reader.id, tenant_id=tenant.id, role='reader'))
        incident = Incident(name='Shell regression incident', reference='UI-REGRESSION',
                            tenant_id=tenant.id, creator_id=admin.id)
        db.session.add(incident)
        db.session.commit()
        app.config['UI_SHELL_IDS'] = {'admin': admin.id, 'reader': reader.id,
                                     'tenant': tenant.id, 'incident': incident.id}
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def client_for(app, role='admin'):
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(app.config['UI_SHELL_IDS'][role])
        session['_fresh'] = True
        session['active_tenant_id'] = app.config['UI_SHELL_IDS']['tenant']
        session['active_tenant_scope_enabled'] = True
    return client


def set_mode(app, mode):
    from app.models import Setting, db
    from app.ui_settings import GLOBAL_UI_MODE_KEY
    with app.app_context():
        db.session.merge(Setting(key=GLOBAL_UI_MODE_KEY, value=mode))
        db.session.commit()


@pytest.mark.parametrize('mode', ['modern', 'classic'])
def test_real_login_retains_credentials_and_csrf(ui_shell_app, mode):
    set_mode(ui_shell_app, mode)
    response = ui_shell_app.test_client().get('/login')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    elements = Elements(html).elements
    assert any(tag == 'body' and attrs.get('data-cir-ui') == mode for tag, attrs in elements)
    assert any(tag == 'input' and attrs.get('name') == 'username' and 'required' in attrs
               for tag, attrs in elements)
    assert any(tag == 'input' and attrs.get('name') == 'password' and attrs.get('type') == 'password'
               for tag, attrs in elements)
    assert any(tag == 'input' and attrs.get('name') == '_csrf_token' and attrs.get('value')
               for tag, attrs in elements)
    assert 'value="cir-demo"' not in html
    assert 'value="demo"' not in html
    assert 'Mockup' not in html
    assert not any(key.startswith('on') for _, attrs in elements for key in attrs)
    assert ('ui/cybersecurity-login-v2.png' in html) == (mode == 'modern')


def test_modern_registry_keeps_all_classic_navigation_and_incident_operations(ui_shell_app):
    client = client_for(ui_shell_app)
    set_mode(ui_shell_app, 'classic')
    classic = client.get('/')
    assert classic.status_code == 200
    set_mode(ui_shell_app, 'modern')
    modern = client.get('/')
    assert modern.status_code == 200
    classic_links = Elements(classic.get_data(as_text=True)).links()
    modern_html = modern.get_data(as_text=True)
    modern_links = Elements(modern_html).links()
    assert classic_links <= modern_links
    assert 'Shell regression incident' in modern_html
    assert 'class="table incident-table"' in modern_html
    assert 'cir-brand-banner' in modern_html
    # The real forms/URLs remain, not demo buttons that claim success locally.
    classic_posts = {attrs.get('action') for tag, attrs in Elements(classic.get_data(as_text=True)).elements
                     if tag == 'form' and attrs.get('method', '').lower() == 'post'}
    modern_posts = {attrs.get('action') for tag, attrs in Elements(modern_html).elements
                    if tag == 'form' and attrs.get('method', '').lower() == 'post'}
    assert classic_posts <= modern_posts


@pytest.mark.parametrize('mode', ['modern', 'classic'])
def test_reader_has_no_admin_switch_or_destructive_registry_controls(ui_shell_app, mode):
    set_mode(ui_shell_app, mode)
    response = client_for(ui_shell_app, 'reader').get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    nodes = Elements(html)
    assert '/admin/interface' not in nodes.links()
    assert '/admin/users' not in nodes.links()
    assert not any(tag == 'form' and any(part in attrs.get('action', '')
                                       for part in ('/delete', '/clone', '/move-tenant'))
                   for tag, attrs in nodes.elements)
    assert 'Shell regression incident' in html


def test_search_sort_and_pagination_parameters_survive_modern_render(ui_shell_app):
    response = client_for(ui_shell_app).get('/?q=Shell&label=&sort=reference&dir=desc&per_page=50&page=1')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    nodes = Elements(html)
    assert any(tag == 'input' and attrs.get('name') == 'q' and attrs.get('value') == 'Shell'
               for tag, attrs in nodes.elements)
    assert any(tag == 'input' and attrs.get('name') == 'sort' and attrs.get('value') == 'reference'
               for tag, attrs in nodes.elements)
    assert any(tag == 'input' and attrs.get('name') == 'dir' and attrs.get('value') == 'desc'
               for tag, attrs in nodes.elements)
    assert any(tag == 'option' and attrs.get('value') == '50' and 'selected' in attrs
               for tag, attrs in nodes.elements)
    assert any('sort=name' in link and 'q=Shell' in link and 'per_page=50' in link
               for link in nodes.links())


def test_runtime_photographs_match_approved_assets():
    root = Path(__file__).resolve().parents[1]
    for name in ('cybersecurity-login-v2.png', 'cybersecurity-hero-v2.png'):
        original = root / 'docs' / 'visual-assets' / name
        runtime = root / 'app' / 'static' / 'ui' / name
        assert hashlib.sha256(runtime.read_bytes()).digest() == hashlib.sha256(original.read_bytes()).digest()


def test_templates_do_not_require_unsafe_inline_csp_exceptions():
    """Forms, reset actions and charts must work under the production CSP."""
    root = Path(__file__).resolve().parents[1]
    templates = list((root / 'app' / 'templates').rglob('*.html'))
    templates += list((root / 'app' / 'plugins').rglob('*.html'))
    offenders = []
    for path in templates:
        if re.search(r'\b(?:on[a-z]+|style)\s*=\s*["\']', path.read_text()):
            offenders.append(str(path.relative_to(root)))
    assert not offenders, 'Move inline handlers/layouts to external assets: ' + ', '.join(offenders)
