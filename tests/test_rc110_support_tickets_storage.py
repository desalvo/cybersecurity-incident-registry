"""RC110: Support Tickets storage is isolated in tests and persistent in deployments."""
import os
from pathlib import Path

import pytest


@pytest.mark.parametrize('explicit', [False, True])
def test_support_tickets_uses_isolated_or_explicit_private_storage(monkeypatch, tmp_path, explicit):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'tickets-storage.db'))
    locations = {
        'UPLOAD_DIR': 'uploads', 'LOGO_DIR': 'logos', 'SSO_LOGO_DIR': 'sso',
        'FORM_TEMPLATE_DIR': 'forms', 'BACKUP_DIR': 'backups',
        'AI_CHATBOT_DOC_DIR': 'knowledge',
    }
    for name, subdir in locations.items():
        monkeypatch.setenv(name, str(tmp_path / subdir))
    expected = tmp_path / ('explicit-private-support' if explicit else 'support_tickets')
    if explicit:
        monkeypatch.setenv('SUPPORT_TICKETS_DIR', str(expected))
    else:
        monkeypatch.delenv('SUPPORT_TICKETS_DIR', raising=False)
    monkeypatch.setenv('SECRET_KEY', 'TEST-SUPPORT-ISOLATION-' * 4)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'TestAdminSupport123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    from app import create_app
    from app.models import db
    app = create_app()
    assert Path(app.config['SUPPORT_TICKETS_DIR']) == expected
    assert expected.is_dir()
    assert str(expected).startswith(str(tmp_path))
    assert app.config['UPLOAD_DIR'] != app.config['SUPPORT_TICKETS_DIR']
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_ui_documentation_fixture_provides_private_support_storage(tmp_path):
    from scripts.seed_ui_documentation import isolated_environment
    directory = tmp_path / 'fresh-fixture'
    directory.mkdir()
    original = os.environ.get('SUPPORT_TICKETS_DIR')
    with isolated_environment(directory):
        assert os.environ['SUPPORT_TICKETS_DIR'] == str(directory / 'support-tickets')
        assert os.environ['UPLOAD_DIR'] == str(directory / 'uploads')
    assert os.environ.get('SUPPORT_TICKETS_DIR') == original


def test_container_entrypoint_and_deployments_persist_support_tickets():
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'docker-entrypoint.sh').read_text()
    dockerfile = (root / 'Dockerfile').read_text()
    compose = (root / 'docker-compose.yml').read_text()
    workflow = (root / '.github/workflows/ci-release.yml').read_text()
    assert 'DATA_DIRS="$UPLOAD_DIR' in entrypoint
    assert '$SUPPORT_TICKETS_DIR' in entrypoint
    assert '/data/support_tickets' in dockerfile
    assert 'support_tickets:${SUPPORT_TICKETS_DIR:-/data/support_tickets}' in compose
    assert 'support_tickets: {}' in compose
    assert 'cir-pytest/support-tickets' in workflow
    assert 'cir-postgres-tests/support-tickets' in workflow
