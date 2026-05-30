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
    assert 'markWorkflowRedirectedSection(section)' in js
    assert 'input.name = \'workflow_update_section_redirect\'' in js


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
