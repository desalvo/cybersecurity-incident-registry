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
