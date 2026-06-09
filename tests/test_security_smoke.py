import os
import pytest


def test_production_requires_strong_secret(monkeypatch):
    from app.security import validate_production_configuration

    class App:
        config = {
            'SECRET_KEY': 'change-me',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:////tmp/test.db',
        }

    monkeypatch.setenv('CIR_PRODUCTION', '1')
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'adminpass')
    with pytest.raises(RuntimeError):
        validate_production_configuration(App())


def test_csrf_field_injected_in_post_forms(monkeypatch):
    from flask import Flask
    from app.security import init_security

    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-for-csrf-smoke-tests'
    init_security(app)

    @app.route('/')
    def index():
        return '<form method="post" action="/save"><button>Save</button></form>'

    with app.test_client() as client:
        response = client.get('/')
        assert response.status_code == 200
        assert b'name="_csrf_token"' in response.data


def test_trace_and_track_methods_are_blocked(monkeypatch):
    from flask import Flask
    from app.security import init_security

    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-for-method-block-smoke-tests'
    init_security(app)

    @app.route('/', methods=['GET', 'TRACE', 'TRACK'])
    def index():
        return 'ok'

    with app.test_client() as client:
        assert client.open('/', method='TRACE').status_code == 405
        assert client.open('/', method='TRACK').status_code == 405


def test_login_lockout_is_server_side_model_backed():
    from app.models import LoginFailure
    from app import routes

    assert LoginFailure.__table__.c.rate_key.unique
    assert 'session.get(\'_login_failures\')' not in routes.login_is_blocked.__code__.co_names
    assert 'session.get(\'_login_failures\')' not in routes.register_login_failure.__code__.co_names


def test_session_timeout_accepts_flask_timedelta_config(monkeypatch, tmp_path):
    import os

    base = tmp_path
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(base / 'test.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(base / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(base / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(base / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(base / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(base / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(base / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)

    from app import create_app

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        response = client.get('/login')
        assert response.status_code == 200


def test_csrf_can_be_disabled_only_outside_production(monkeypatch):
    from flask import Flask
    from app.security import init_security

    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-for-disabled-csrf-smoke-tests'
    init_security(app)

    @app.route('/save', methods=['POST'])
    def save():
        return 'saved'

    @app.route('/')
    def index():
        return '<form method="post" action="/save"><button>Save</button></form>'

    with app.test_client() as client:
        page = client.get('/')
        assert page.status_code == 200
        assert b'name="_csrf_token"' not in page.data
        response = client.post('/save', data={'value': 'ok'})
        assert response.status_code == 200
        assert response.data == b'saved'


def test_csrf_disable_is_refused_in_production(monkeypatch):
    from app.security import validate_production_configuration

    class App:
        config = {
            'SECRET_KEY': 'S' * 64,
            'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg2://u:p@db:5432/incidents',
        }

    monkeypatch.setenv('CIR_PRODUCTION', '1')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'VeryStrongAdminPassword123!')
    with pytest.raises(RuntimeError) as exc:
        validate_production_configuration(App())
    assert 'CIR_DISABLE_CSRF cannot be enabled in production' in str(exc.value)


def test_login_page_contains_explicit_csrf_token_when_enabled(monkeypatch, tmp_path):
    base = tmp_path
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(base / 'login_csrf.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(base / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(base / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(base / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(base / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(base / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(base / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'L' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '0')
    monkeypatch.setenv('CIR_PRODUCTION', '0')

    from app import create_app

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        response = client.get('/login')
        assert response.status_code == 200
        assert b'name="_csrf_token"' in response.data


def test_login_with_disabled_csrf_uses_admin_initial_password(monkeypatch, tmp_path):
    base = tmp_path
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(base / 'login_admin.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(base / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(base / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(base / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(base / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(base / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(base / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'A' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', '"AdminPassword123!"')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    monkeypatch.setenv('CIR_PRODUCTION', '0')

    from app import create_app

    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        response = client.post('/login', data={'username': 'admin', 'password': 'AdminPassword123!'}, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/')


def test_csrf_login_post_works_on_plain_http_when_secure_cookie_is_disabled(monkeypatch):
    import re
    from flask import Flask, request
    from app.security import init_security

    monkeypatch.setenv('CIR_PRODUCTION', '1')
    monkeypatch.setenv('SESSION_COOKIE_SECURE', '0')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '0')
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'VeryStrongAdminPassword123!')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'S' * 64
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://u:p@db:5432/incidents'
    init_security(app)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            return 'logged-in'
        return '<form method="post"><button>Login</button></form>'

    with app.test_client() as client:
        page = client.get('/login', base_url='http://localhost')
        assert page.status_code == 200
        set_cookie_headers = page.headers.getlist('Set-Cookie')
        assert any('session=' in header and 'Secure' not in header for header in set_cookie_headers)
        assert any('cir_csrf_token=' in header and 'Secure' not in header for header in set_cookie_headers)
        token = re.search(r'name="_csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)
        response = client.post('/login', data={'_csrf_token': token}, base_url='http://localhost')
        assert response.status_code == 200
        assert response.data == b'logged-in'


def test_secure_cookie_flag_remains_available_for_https_deployments(monkeypatch):
    from flask import Flask
    from app.security import init_security

    monkeypatch.setenv('CIR_PRODUCTION', '1')
    monkeypatch.setenv('SESSION_COOKIE_SECURE', '1')
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'VeryStrongAdminPassword123!')

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'S' * 64
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://u:p@db:5432/incidents'
    init_security(app)

    assert app.config['SESSION_COOKIE_SECURE'] is True
    assert app.config['REMEMBER_COOKIE_SECURE'] is True
