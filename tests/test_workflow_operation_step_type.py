from pathlib import Path


def _configure_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'O' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def test_operation_step_type_is_protected_and_uses_section_target(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.routes import workflow_step_type_records, workflow_step_type_uses_section_target

    app = create_app()
    with app.app_context():
        records = {item['code']: item for item in workflow_step_type_records()}
        assert records['operation']['label'] == 'Operazione'
        assert records['operation']['description'] == 'Effettua operazione'
        assert records['operation']['protected'] is True
        assert workflow_step_type_uses_section_target('operation') is True
        assert workflow_step_type_uses_section_target('update_section') is True


def test_operation_step_type_ui_shows_update_section_fields():
    html = Path('app/templates/admin_incident_workflows.html').read_text()
    assert "['update_section','operation'].includes(select.value)" in html


def test_operation_step_type_static_backend_paths():
    routes = Path('app/routes.py').read_text()
    assert "{'code': 'operation', 'label': 'Operazione', 'description': 'Effettua operazione', 'protected': True}" in routes
    assert 'def workflow_step_type_uses_section_target(value):' in routes
    assert 'workflow_step_type_uses_section_target(step_type)' in routes
    assert 'workflow_step_type_uses_section_target(step.step_type)' in routes
