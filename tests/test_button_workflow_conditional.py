from pathlib import Path


def test_button_action_config_supports_workflow_update_section_scope_static():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    template = Path('app/templates/admin_incident_button_actions.html').read_text(encoding='utf-8')
    js = Path('app/static/app.js').read_text(encoding='utf-8')

    assert "scope not in {'always', WORKFLOW_UPDATE_SECTION_SCOPE}" in routes
    assert "workflow_update_section_redirect" in routes
    assert "automatic_button_action_allowed" in routes
    assert 'Solo da sezione aperta tramite step workflow' in template
    assert 'name="action_scope_{{ code }}"' in template
    assert 'markWorkflowRedirectedSection(section, step)' in js
    assert 'input.name = \'workflow_update_section_redirect\'' in js



def test_button_action_admin_template_is_valid_jinja_static():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('app/templates'))
    template = env.get_template('admin_incident_button_actions.html')
    assert template is not None


def test_legacy_button_action_config_is_backward_compatible(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'legacy_button_config.db'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('ADMIN_PASSWORD', 'AdminPassword123!')
    monkeypatch.setenv('WTF_CSRF_ENABLED', '0')
    from app import create_app, db
    from app.models import ConfigLabel
    from app.routes import BUTTON_ACTIONS_SETTING, button_action_config, set_setting_value

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        label = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        assert label is not None
        set_setting_value(BUTTON_ACTIONS_SETTING, '{"incident_update": %d}' % label.id)
        db.session.commit()
        cfg = button_action_config()
        assert cfg['incident_update']['label_id'] == label.id
        assert cfg['incident_update']['scope'] == 'always'


def test_workflow_update_section_target_helper_is_available_static():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    assert 'def workflow_update_section_target_from_form(field_name):' in routes
    assert "allowed = {code for code, _label in INCIDENT_DETAIL_SECTIONS}" in routes
    assert "workflow_update_section_target_from_form('section_target')" in routes


def test_save_tag_button_action_static_assets_are_present():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    template = Path('app/templates/admin_incident_button_actions.html').read_text(encoding='utf-8')
    incident_template = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')

    assert "('document_tags_save', 'Salva tag')" in routes
    assert "context_tags=None" in routes
    assert "configured_tags & current_tags" in routes
    partial = Path('app/templates/partials/button_action_tag_rule.html').read_text(encoding='utf-8')
    assert "notification_tags_{{ code }}_{{ idx }}" in partial
    assert "data-button-code=\"{{ code }}\"" in partial
    assert "Rilascia qui i tag che attivano questa regola" in template
    assert '>Scarica</a>' in incident_template


def test_save_tag_button_action_runs_only_for_configured_tags(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'save_tag_button.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from flask_login import login_user
    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, NotificationType, Tenant, User
    from app.routes import BUTTON_ACTIONS_SETTING, add_automatic_button_action, set_setting_value

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        label = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        admin = User.query.filter_by(username='admin').first()
        assert tenant is not None
        assert label is not None
        assert admin is not None
        db.session.add_all([
            NotificationType(code='save_tag_match', label='Tag match', enabled=True),
            NotificationType(code='save_tag_other', label='Tag other', enabled=True),
        ])
        inc = Incident(tenant_id=tenant.id, name='Test save tag', reference='TAG-1', status='aperto')
        db.session.add(inc)
        set_setting_value(BUTTON_ACTIONS_SETTING, '{"document_tags_save":{"label_id":%d,"scope":"always","notification_tags":["save_tag_match"]}}' % label.id)
        db.session.commit()
        inc_id = inc.id

        with app.test_request_context('/document/1/notification-tags', method='POST'):
            login_user(admin)
            assert add_automatic_button_action(inc, 'document_tags_save', context_tags=['save_tag_other']) is None
            db.session.commit()
        assert Action.query.filter_by(incident_id=inc_id, label_id=label.id).count() == 0

        with app.test_request_context('/document/1/notification-tags', method='POST'):
            login_user(admin)
            action = add_automatic_button_action(
                inc,
                'document_tags_save',
                description='Azione automatica da pulsante: Salva tag documento evidence.txt.',
                context_tags=['save_tag_match'],
            )
            db.session.commit()
        assert action is not None
        assert isinstance(action, list)
        actions = Action.query.filter_by(incident_id=inc_id, label_id=label.id).all()
        assert len(actions) == 1
        assert 'Salva tag documento evidence.txt' in (actions[0].description or '')


def test_save_tag_button_action_supports_multiple_tag_rules(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'save_tag_button_multi.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from flask_login import login_user
    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, NotificationType, Tenant, User
    from app.routes import BUTTON_ACTIONS_SETTING, add_automatic_button_action, button_action_config, set_setting_value

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        admin = User.query.filter_by(username='admin').first()
        label_a = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        label_b = ConfigLabel(tenant_id=tenant.id, kind='action_label', group='action_label', value='99-test tag action')
        db.session.add(label_b)
        db.session.add_all([
            NotificationType(code='multi_tag_a', label='Multi tag A', enabled=True),
            NotificationType(code='multi_tag_b', label='Multi tag B', enabled=True),
        ])
        inc = Incident(tenant_id=tenant.id, name='Test save tag multi', reference='TAG-2', status='aperto')
        db.session.add(inc)
        db.session.flush()
        set_setting_value(
            BUTTON_ACTIONS_SETTING,
            '{"document_tags_save":['
            '{"label_id":%d,"scope":"always","notification_tags":["multi_tag_a"]},'
            '{"label_id":%d,"scope":"always","notification_tags":["multi_tag_b"]}'
            ']}' % (label_a.id, label_b.id),
        )
        db.session.commit()
        inc_id = inc.id
        cfg = button_action_config()
        assert len(cfg['document_tags_save']) == 2

        with app.test_request_context('/document/1/notification-tags', method='POST'):
            login_user(admin)
            created = add_automatic_button_action(
                inc,
                'document_tags_save',
                description='Azione automatica da pulsante: Salva tag documento evidence.txt.',
                context_tags=['multi_tag_a', 'multi_tag_b'],
            )
            db.session.commit()

        assert isinstance(created, list)
        assert len(created) == 2
        assert Action.query.filter_by(incident_id=inc_id, label_id=label_a.id).count() == 1
        assert Action.query.filter_by(incident_id=inc_id, label_id=label_b.id).count() == 1


def test_save_tag_button_action_rejects_duplicate_tags_across_rules(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'save_tag_unique.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from app import create_app, db
    from app.models import ConfigLabel, NotificationType, Tenant
    from app.routes import BUTTON_ACTIONS_SETTING, button_action_config, save_button_action_config

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        label_a = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        label_b = ConfigLabel(tenant_id=tenant.id, kind='action_label', group='action_label', value='99-duplicate tag action')
        db.session.add(label_b)
        db.session.add_all([
            NotificationType(code='same_tag', label='Same tag', enabled=True),
            NotificationType(code='first_only', label='First only', enabled=True),
            NotificationType(code='second_only', label='Second only', enabled=True),
        ])
        db.session.flush()
        save_button_action_config({
            'document_tags_save': [
                {'label_id': label_a.id, 'scope': 'always', 'notification_tags': ['same_tag', 'first_only']},
                {'label_id': label_b.id, 'scope': 'always', 'notification_tags': ['same_tag', 'second_only']},
            ]
        })
        db.session.commit()
        cfg = button_action_config()

    assert cfg['document_tags_save'][0]['notification_tags'] == ['same_tag', 'first_only']
    assert cfg['document_tags_save'][1]['notification_tags'] == ['second_only']


def test_button_action_ui_prevents_duplicate_save_tag_selection_and_left_aligns_summaries():
    template = Path('app/templates/admin_incident_button_actions.html').read_text(encoding='utf-8')
    css = Path('app/static/style.css').read_text(encoding='utf-8')

    assert 'selectedTagOwners' in template
    assert 'Tag già utilizzato in un’altra regola Salva tag' in template
    assert 'drop-rejected' in template
    assert 'justify-content:flex-start;text-align:left' in template
    assert '.button-action-summary-help{font-size:.9rem;color:#64748b;text-align:left}' in template
    assert 'grid-template-rows:minmax(0,1fr) auto' in css


def test_document_download_button_action_uses_first_generic_rule_without_workflow(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'download_button.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from flask_login import login_user
    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, Tenant, User
    from app.routes import BUTTON_ACTIONS_SETTING, add_automatic_button_action, button_action_config, set_setting_value

    forms = tmp_path / 'forms'
    forms.mkdir(parents=True, exist_ok=True)
    (forms / 'template_a.pdf').write_bytes(b'%PDF-1.4\n%%EOF\n')
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        admin = User.query.filter_by(username='admin').first()
        label = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        inc = Incident(tenant_id=tenant.id, name='Download generic rule', reference='DL-1', status='aperto')
        db.session.add(inc)
        db.session.flush()
        set_setting_value(BUTTON_ACTIONS_SETTING, '{"document_download":[{"label_id":%d,"scope":"always","template_name":"template_a"},{"label_id":%d,"scope":"always","template_name":""}]}' % (label.id, label.id))
        db.session.commit()
        inc_id = inc.id
        cfg = button_action_config()
        assert cfg['document_download'][0]['template_name'] == 'template_a'
        assert cfg['document_download'][1]['template_name'] == ''

        with app.test_request_context('/document/1/download'):
            login_user(admin)
            action = add_automatic_button_action(
                inc,
                'document_download',
                description='Azione automatica da pulsante: Scarica documento evidence.pdf.',
                context_template='template_b',
            )
            db.session.commit()
        assert action is not None
        actions = Action.query.filter_by(incident_id=inc_id, label_id=label.id).all()
        assert len(actions) == 1
        assert 'Scarica documento evidence.pdf' in (actions[0].description or '')



def test_workflow_document_section_step_template_overrides_download_button_template(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'download_workflow_override.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from flask_login import login_user
    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep, Tenant, User
    from app.routes import (
        BUTTON_ACTIONS_SETTING,
        UPDATE_SECTION_STEP_TYPE,
        add_automatic_button_action,
        set_setting_value,
        workflow_document_download_template_constraints,
    )

    forms = tmp_path / 'forms'
    forms.mkdir(parents=True, exist_ok=True)
    (forms / 'template_a.pdf').write_bytes(b'%PDF-1.4\n%%EOF\n')
    (forms / 'template_b.pdf').write_bytes(b'%PDF-1.4\n%%EOF\n')
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        admin = User.query.filter_by(username='admin').first()
        label = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        inc = Incident(tenant_id=tenant.id, name='Workflow download override', reference='DL-STEP', status='aperto')
        db.session.add(inc)
        db.session.flush()
        step = IncidentWorkflowStep(
            tenant_id=tenant.id,
            action_label_id=label.id,
            position=1,
            step_type=UPDATE_SECTION_STEP_TYPE,
            section_target='incident-documents',
            document_generation_enabled=True,
            document_template_name='template_b',
            required=True,
        )
        db.session.add(step)
        set_setting_value(BUTTON_ACTIONS_SETTING, '{"document_download":[{"label_id":%d,"scope":"always","template_name":"template_b"},{"label_id":%d,"scope":"always","template_name":"template_a"}]}' % (label.id, label.id))
        db.session.commit()
        inc_id = inc.id

        assert workflow_document_download_template_constraints(inc) == ['template_b']

        with app.test_request_context('/document/1/download?workflow_update_section_redirect=1&workflow_update_section_target=incident-documents&workflow_document_template=template_b'):
            login_user(admin)
            assert add_automatic_button_action(inc, 'document_download', context_template='template_a') is None
            db.session.commit()
        assert Action.query.filter_by(incident_id=inc_id, label_id=label.id).count() == 0

        with app.test_request_context('/document/1/download?workflow_update_section_redirect=1&workflow_update_section_target=incident-documents&workflow_document_template=template_b'):
            login_user(admin)
            action = add_automatic_button_action(inc, 'document_download', context_template='template_b')
            db.session.commit()
        assert action is not None
        assert Action.query.filter_by(incident_id=inc_id, label_id=label.id).count() == 1


def test_document_download_workflow_scope_is_preserved_on_redirected_section_static():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    js = Path('app/static/app.js').read_text(encoding='utf-8')

    assert "request.values.get(\'workflow_update_section_redirect\')" in routes
    assert 'workflow_document_download_template_constraints' in routes
    assert 'document_generation_enabled' in routes
    assert 'section_target' in routes
    assert 'workflow_update_section_redirect' in js
    assert 'document' in js and 'download' in js and 'workflow_update_section_target' in js


def test_document_download_button_action_static_assets_are_present():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    template = Path('app/templates/admin_incident_button_actions.html').read_text(encoding='utf-8')

    assert "('document_download', 'Scarica documenti')" in routes
    assert "context_template=d.generated_template_name" in routes
    assert "action_template_name_document_download_{{ idx }}" in template
    assert 'Template generatore documento' in template
    assert 'Nessun template: regola generica' in template


def test_workflow_document_download_hides_when_no_matching_template_rule_static():
    incident_template = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')

    assert 'data-document-download-rule-templates' in incident_template
    assert 'document-download-filename' in incident_template
    assert 'data-document-template-name' in incident_template
    assert 'refreshDocumentDownloadVisibility' in js
    assert 'docTemplate === constrainedTemplate' in js
    assert 'workflow_document_template' in js
    assert 'current_workflow_document_download_template' in routes
    assert "for entry in rules:" in routes


def test_workflow_document_download_requires_matching_template_rule(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'download_workflow_no_match.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from flask_login import login_user
    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep, Tenant, User
    from app.routes import BUTTON_ACTIONS_SETTING, UPDATE_SECTION_STEP_TYPE, add_automatic_button_action, set_setting_value

    forms = tmp_path / 'forms'
    forms.mkdir(parents=True, exist_ok=True)
    (forms / 'template_a.pdf').write_bytes(b'%PDF-1.4\n%%EOF\n')
    (forms / 'template_b.pdf').write_bytes(b'%PDF-1.4\n%%EOF\n')
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        admin = User.query.filter_by(username='admin').first()
        label = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        inc = Incident(tenant_id=tenant.id, name='Workflow no download match', reference='DL-NO-MATCH', status='aperto')
        db.session.add(inc)
        db.session.flush()
        db.session.add(IncidentWorkflowStep(
            tenant_id=tenant.id,
            action_label_id=label.id,
            position=1,
            step_type=UPDATE_SECTION_STEP_TYPE,
            section_target='incident-documents',
            document_generation_enabled=True,
            document_template_name='template_b',
            required=True,
        ))
        set_setting_value(BUTTON_ACTIONS_SETTING, '{"document_download":[{"label_id":%d,"scope":"always","template_name":"template_a"},{"label_id":%d,"scope":"always","template_name":""}]}' % (label.id, label.id))
        db.session.commit()

        with app.test_request_context('/document/1/download?workflow_update_section_redirect=1&workflow_update_section_target=incident-documents&workflow_document_template=template_b'):
            login_user(admin)
            assert add_automatic_button_action(inc, 'document_download', context_template='template_b') is None
            db.session.commit()
        assert Action.query.filter_by(incident_id=inc.id, label_id=label.id).count() == 0


def test_workflow_document_download_constrained_ui_hides_direct_filename_links_static():
    incident_template = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')

    assert 'document-filename-download-link' in incident_template
    assert 'document-download-button' in incident_template
    assert "section.querySelectorAll('.document-filename-download-link')" in js
    assert "section.querySelectorAll('.document-download-button')" in js
    assert 'link.hidden = constrained' in js
    assert 'filename.hidden = !constrained' in js
    assert 'normalizeDocumentTemplateName(link.dataset.documentTemplateName' in js
    assert 'docTemplate === constrainedTemplate' in js
    assert 'active_workflow_document_template' in incident_template
    assert 'download_visible_for_workflow' in incident_template
    assert "Path(str((entry or {}).get('template_name') or '').strip()).stem" in routes


def test_incident_update_button_uses_workflow_step_action_rule_when_general_section_is_workflow_redirect(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'incident_update_workflow.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('APP_SECRET', 'test-secret')
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')

    from flask_login import login_user
    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, Tenant, User
    from app.routes import BUTTON_ACTIONS_SETTING, WORKFLOW_UPDATE_SECTION_SCOPE, add_automatic_button_action, set_setting_value

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        tenant = Tenant.query.filter_by(name='default').first()
        admin = User.query.filter_by(username='admin').first()
        generic = ConfigLabel.query.filter_by(kind='action_label', value='09-aggiornamento dati incidente').first()
        workflow = ConfigLabel(tenant_id=tenant.id, kind='action_label', group='action_label', value='99-workflow-update-main')
        other = ConfigLabel(tenant_id=tenant.id, kind='action_label', group='action_label', value='99-workflow-other')
        inc = Incident(tenant_id=tenant.id, name='Incident update workflow', reference='WF-MAIN-1', status='aperto')
        db.session.add_all([workflow, other, inc])
        db.session.flush()
        set_setting_value(
            BUTTON_ACTIONS_SETTING,
            '[invalid json',
        )
        set_setting_value(
            BUTTON_ACTIONS_SETTING,
            '{"incident_update":['
            '{"label_id":%d,"scope":"always"},'
            '{"label_id":%d,"scope":"%s"}'
            ']}' % (generic.id, workflow.id, WORKFLOW_UPDATE_SECTION_SCOPE),
        )
        db.session.commit()
        inc_id = inc.id

        with app.test_request_context('/incident/%d' % inc_id, method='POST'):
            login_user(admin)
            created = add_automatic_button_action(inc, 'incident_update')
            db.session.commit()
        assert created is not None
        assert created.label_id == generic.id

        with app.test_request_context('/incident/%d?workflow_update_section_redirect=1&workflow_update_section_target=incident-main&workflow_step_action_label_id=%d' % (inc_id, workflow.id), method='POST'):
            login_user(admin)
            created = add_automatic_button_action(inc, 'incident_update')
            db.session.commit()
        assert created is not None
        assert created.label_id == workflow.id

        with app.test_request_context('/incident/%d?workflow_update_section_redirect=1&workflow_update_section_target=incident-main&workflow_step_action_label_id=%d' % (inc_id, other.id), method='POST'):
            login_user(admin)
            created = add_automatic_button_action(inc, 'incident_update')
            db.session.commit()
        assert created is None
        assert Action.query.filter_by(incident_id=inc_id, label_id=generic.id).count() == 1
        assert Action.query.filter_by(incident_id=inc_id, label_id=workflow.id).count() == 1
        assert Action.query.filter_by(incident_id=inc_id, label_id=other.id).count() == 0


def test_incident_update_admin_ui_has_generic_single_rule_and_multiple_workflow_rules_static():
    template = Path('app/templates/admin_incident_button_actions.html').read_text(encoding='utf-8')
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')

    assert 'action_label_id_incident_update_generic' in template
    assert 'incident_update_workflow_rule_count' in template
    assert 'add-incident-update-workflow-rule' in template
    assert 'workflow_step_action_label_id' in js
    assert 'current_workflow_step_action_label_id' in routes
    assert "current_workflow_update_section_target() == 'incident-main'" in routes
