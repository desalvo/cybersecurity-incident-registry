from pathlib import Path


def test_workflow_step_document_auto_tags_removed_from_admin_ui_and_model_static():
    workflow_template = Path('app/templates/admin_incident_workflows.html').read_text(encoding='utf-8')
    models = Path('app/models.py').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')

    assert 'Auto tag documento' not in workflow_template
    assert 'document_auto_tag_list' not in models
    assert 'set_document_auto_tags' not in models
    assert 'workflow_document_auto_tags_from_form' not in routes
    assert 'document_auto_tags=src.document_auto_tags' not in routes


def test_document_upload_button_action_has_template_rules_and_drag_tags_static():
    template = Path('app/templates/admin_incident_button_actions.html').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    js = Path('app/static/app.js').read_text(encoding='utf-8')

    assert 'document-upload-rules' in template
    assert 'notification_tags_document_upload_' in template
    assert "code in {'document_upload', 'document_download'}" in routes
    assert "include_tags=(code == 'document_upload')" in routes
    assert 'context_documents' in routes
    assert 'initIncidentDocumentPostActions' in js
    assert 'section-scroll-top-icon' in js


def test_document_upload_template_rule_applies_tags_only_in_workflow_context(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'upload_rules.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from flask_login import login_user
    from app import create_app, db
    from app.models import ConfigLabel, Document, Incident, IncidentWorkflowStep, NotificationType, Tenant, User
    from app import routes as routes_module
    from app.routes import BUTTON_ACTIONS_SETTING, add_automatic_button_action, set_setting_value

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        label = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        admin = User.query.filter_by(username='admin').first()
        db.session.add(NotificationType(code='upload_tag_match', label='Upload tag', enabled=True))
        inc = Incident(tenant_id=tenant.id, name='Upload workflow', reference='UP-1', status='aperto')
        db.session.add(inc)
        db.session.flush()
        step = IncidentWorkflowStep(
            tenant_id=tenant.id,
            action_label_id=label.id,
            position=10,
            description='Upload da workflow',
            step_type='update_section',
            section_target='incident-documents',
            document_generation_enabled=True,
            document_template_name='template_a',
        )
        db.session.add(step)
        doc = Document(incident_id=inc.id, filename='evidence.pdf', stored_name='evidence.pdf')
        db.session.add(doc)
        monkeypatch.setattr(routes_module, '_valid_form_template_names', lambda: {'template_a'})
        set_setting_value(BUTTON_ACTIONS_SETTING, '{"document_upload":[{"label_id":%d,"scope":"always","template_name":"template_a","notification_tags":["upload_tag_match"]},{"label_id":%d,"scope":"always","template_name":"","notification_tags":["upload_tag_match"]}]}' % (label.id, label.id))
        db.session.commit()

        with app.test_request_context('/incident/%d/upload' % inc.id, method='POST', data={
            'workflow_update_section_redirect': '1',
            'workflow_update_section_target': 'incident-documents',
            'workflow_document_template': 'template_a',
        }):
            login_user(admin)
            action = add_automatic_button_action(inc, 'document_upload', context_documents=[doc])
            db.session.commit()
        assert action is not None
        assert doc.notification_tag_list == ['upload_tag_match']
