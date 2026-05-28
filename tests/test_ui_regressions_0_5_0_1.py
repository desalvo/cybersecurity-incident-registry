from pathlib import Path
from datetime import datetime


def test_new_incident_recipient_email_obeys_default_visibility_configuration():
    html = Path('app/templates/incident_form.html').read_text()
    assert "if 'recipient_email' not in incident_form_visible_fields" in html
    assert "id=\"new-recipient-email\"" in html


def test_workflow_task_box_uses_configurable_step_type_caption():
    html = Path('app/templates/incident_detail.html').read_text()
    assert '<p class="workflow-confirm-phase"><strong>{{ step.step_type_description }}: </strong>{{ step.label }}</p>' in html


def test_ldap_lookup_reports_non_json_responses_without_json_parse_exception():
    js = Path('app/static/app.js').read_text()
    assert "content-type" in js
    assert "La ricerca LDAP non ha restituito JSON valido" in js
    assert "credentials:'same-origin'" in js
    assert "X-Requested-With" in js


def _configure_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db'))
    monkeypatch.setenv('UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('LOGO_DIR', str(tmp_path / 'logos'))
    monkeypatch.setenv('SSO_LOGO_DIR', str(tmp_path / 'sso'))
    monkeypatch.setenv('FORM_TEMPLATE_DIR', str(tmp_path / 'forms'))
    monkeypatch.setenv('BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setenv('AI_CHATBOT_DOC_DIR', str(tmp_path / 'ai_docs'))
    monkeypatch.setenv('SECRET_KEY', 'T' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def test_close_without_warnings_accepts_legacy_italian_operation_label(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)

    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep
    from app.routes import apply_action_automatic_operations

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        category = ConfigLabel(kind='category', group='workflow-test', value='Categoria legacy tag italiano')
        closing = ConfigLabel(
            kind='action_label',
            group='workflow-test',
            value='Chiusura con tag testuale',
            automatic_operations='Chiusura del task in assenza di avvisi procedurali',
        )
        db.session.add_all([category, closing])
        db.session.flush()
        db.session.add(IncidentWorkflowStep(category_id=category.id, action_label_id=closing.id, position=1, required=True))
        inc = Incident(name='Legacy Italian close tag', reference='REF', status='aperto', creator_name='Test', creator_email='test@example.invalid')
        inc.categories = [category]
        db.session.add(inc)
        db.session.commit()

        # Simula una relazione azioni già letta prima del flush dell'azione manuale.
        assert inc.actions == []
        action = Action(
            incident_id=inc.id,
            when_at=datetime(2026, 5, 27, 10, 30),
            person_name='Operatore',
            label_id=closing.id,
            description='Chiusura finale',
        )
        db.session.add(action)

        assert apply_action_automatic_operations(inc.id, action) is True
        assert inc.status == 'chiuso'
        assert inc.end_date is not None
        assert getattr(inc, '_closure_blocked_by_procedural_warnings', False) is False


def test_incident_visibility_settings_separate_external_and_ldap_searches():
    routes = Path('app/routes.py').read_text()
    admin = Path('app/templates/admin_incident_form_fields.html').read_text()
    new_form = Path('app/templates/incident_form.html').read_text()
    detail = Path('app/templates/incident_detail.html').read_text()
    assert "('external_recipient_lookup', 'Ricerca destinatari esterni'" in routes
    assert "('ldap_recipient_lookup', 'Ricerca utente via LDAP'" in routes
    assert 'new_visible_field' in admin
    assert 'detail_visible_field' in admin
    assert 'Dati generali incidente' in admin
    assert 'show_external_recipient_lookup' in new_form
    assert 'show_ldap_recipient_lookup' in new_form
    assert 'incident_detail_visible_fields' in detail


def test_admin_menu_renames_incident_field_visibility_page():
    html = Path('app/templates/base.html').read_text()
    assert 'Layout campi incidenti' in html
    assert 'Campi nuovo incidente' not in html


def test_ldap_incident_recipient_search_imports_jsonify():
    routes = Path('app/routes.py').read_text()
    assert 'jsonify' in routes.split('\n', 8)[5]
    assert "def ldap_incident_recipient_search" in routes


def test_incident_detail_visibility_empty_saved_setting_hides_both_lookup_panels(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import Setting
    from app.routes import incident_detail_general_visible_fields

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        assert incident_detail_general_visible_fields() == {'external_recipient_lookup', 'ldap_recipient_lookup'}
        db.session.add(Setting(key='incident_detail_general_visible_fields', value=''))
        db.session.commit()
        assert incident_detail_general_visible_fields() == set()


def test_ldap_incident_search_returns_configured_attributes_for_each_result():
    routes = Path('app/routes.py').read_text()
    js = Path('app/static/app.js').read_text()
    assert "'attributes': attr_values" in routes
    assert "'attribute_order': attrs" in routes
    assert "ldap-recipient-attributes" in js
    assert "Seleziona" in js


def test_workflow_step_type_configuration_and_dynamic_caption_are_present():
    routes = Path('app/routes.py').read_text()
    model = Path('app/models.py').read_text()
    admin = Path('app/templates/admin_incident_workflows.html').read_text()
    detail = Path('app/templates/incident_detail.html').read_text()
    assert 'step_type=db.Column' in model
    assert 'WORKFLOW_STEP_TYPES' in routes
    assert 'workflow_step_types_json' in routes
    assert 'workflow_step_type_records' in routes
    assert 'name="step_type"' in admin
    assert 'name="step_type_{{step.id}}"' in admin
    assert '{{ step.step_type_description }}' in detail
    assert 'Conferma fase: </strong>{{ step.label }}' not in detail


def test_default_incident_visibility_fields_are_all_selected(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app
    from app.routes import incident_form_visible_fields, incident_detail_general_visible_fields, INCIDENT_FORM_FIELDS, INCIDENT_DETAIL_VISIBILITY_FIELDS

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        assert incident_form_visible_fields() == {code for code, _label, _required in INCIDENT_FORM_FIELDS}
        assert incident_detail_general_visible_fields() == {code for code, _label, _required in INCIDENT_DETAIL_VISIBILITY_FIELDS}


def test_workflow_step_types_are_configurable_and_defaults_are_protected(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import IncidentWorkflowStep, Setting
    from app.routes import (
        workflow_step_type_records,
        save_workflow_step_type_records,
        normalize_workflow_step_type,
        workflow_step_type_description,
    )

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        defaults = workflow_step_type_records()
        assert [item['code'] for item in defaults[:2]] == ['confirm', 'execution']
        assert all(item['protected'] for item in defaults[:2])

        save_workflow_step_type_records(defaults + [{'code': 'review', 'label': 'Revisione', 'description': 'Rivedi fase', 'protected': False}])
        assert normalize_workflow_step_type('review') == 'review'
        assert workflow_step_type_description('review') == 'Rivedi fase'

        step = IncidentWorkflowStep(action_label_id=1, step_type='review')
        db.session.add(step)
        db.session.commit()
        assert db.session.get(IncidentWorkflowStep, step.id).step_type == 'review'

        saved = db.session.get(Setting, 'workflow_step_types_json')
        assert saved is not None and 'review' in saved.value


def test_workflow_step_type_admin_template_supports_add_edit_delete_custom_types():
    routes = Path('app/routes.py').read_text()
    admin = Path('app/templates/admin_incident_workflows.html').read_text()
    init = Path('app/__init__.py').read_text()
    assert "action == 'add_step_type'" in routes
    assert "action == 'save_step_types'" in routes
    assert "action == 'delete_step_type'" in routes
    assert 'Default protetta' in admin
    assert 'Personalizzata' in admin
    assert 'new_step_type_label' in admin
    assert 'delete_step_type' in admin
    assert "WHERE step_type IS NULL OR step_type = ''" in init
    assert "NOT IN ('confirm','execution')" not in init


def test_workflow_clone_ui_and_server_confirmation_are_present():
    routes = Path('app/routes.py').read_text()
    admin = Path('app/templates/admin_incident_workflows.html').read_text()
    assert "action == 'clone_workflow'" in routes
    assert 'clone_workflow_steps' in routes
    assert 'clone_overwrite_confirm' in admin
    assert 'data-workflow-clone-form' in admin
    assert 'confermare la sovrascrittura' in routes


def test_incident_workflow_uses_first_category_order(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import ConfigLabel, Incident, IncidentWorkflowStep
    from app.routes import workflow_steps_for_incident, incident_category_order_ids

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        cat_a = ConfigLabel(kind='category', group='workflow-order', value='A prima')
        cat_b = ConfigLabel(kind='category', group='workflow-order', value='B seconda')
        act_a = ConfigLabel(kind='action_label', group='workflow-order', value='Azione categoria A')
        act_b = ConfigLabel(kind='action_label', group='workflow-order', value='Azione categoria B')
        db.session.add_all([cat_a, cat_b, act_a, act_b])
        db.session.flush()
        step_a = IncidentWorkflowStep(category_id=cat_a.id, action_label_id=act_a.id, position=10, required=True)
        step_b = IncidentWorkflowStep(category_id=cat_b.id, action_label_id=act_b.id, position=10, required=True)
        inc = Incident(name='Ordine categorie workflow', reference='REF', status='aperto', creator_name='Test', creator_email='test@example.invalid')
        inc.categories = [cat_a, cat_b]
        inc.category_order = f'{cat_b.id},{cat_a.id}'
        db.session.add_all([step_a, step_b, inc])
        db.session.commit()

        assert incident_category_order_ids(inc) == [cat_b.id, cat_a.id]
        steps = workflow_steps_for_incident(inc)
        assert [s.action_label_id for s in steps] == [act_b.id]


def test_clone_workflow_steps_overwrite_requires_confirmation(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import ConfigLabel, IncidentWorkflowStep
    from app.routes import clone_workflow_steps

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        src = ConfigLabel(kind='category', group='clone', value='Sorgente clone')
        dst = ConfigLabel(kind='category', group='clone', value='Destinazione clone')
        act_src = ConfigLabel(kind='action_label', group='clone', value='Azione sorgente clone')
        act_dst = ConfigLabel(kind='action_label', group='clone', value='Azione destinazione clone')
        db.session.add_all([src, dst, act_src, act_dst])
        db.session.flush()
        db.session.add(IncidentWorkflowStep(category_id=src.id, action_label_id=act_src.id, position=10, description='Da clonare'))
        db.session.add(IncidentWorkflowStep(category_id=dst.id, action_label_id=act_dst.id, position=20, description='Esistente'))
        db.session.commit()

        result = clone_workflow_steps(src.id, dst.id, overwrite=False)
        assert result['ok'] is False
        assert IncidentWorkflowStep.query.filter_by(category_id=dst.id).count() == 1

        result = clone_workflow_steps(src.id, dst.id, overwrite=True)
        assert result['ok'] is True
        cloned = IncidentWorkflowStep.query.filter_by(category_id=dst.id).one()
        assert cloned.action_label_id == act_src.id
        assert cloned.description == 'Da clonare'


def test_bootstrap_skips_default_config_labels_when_database_already_populated():
    source = Path('app/__init__.py').read_text()
    assert 'database_already_populated = database_has_existing_operational_data()' in source
    assert 'if not database_already_populated:' in source
    assert 'restore_missing_default_config_labels()' in source
    assert "Database già popolato" in source


def test_admin_labels_has_restore_missing_defaults_button():
    html = Path('app/templates/admin_labels.html').read_text()
    routes = Path('app/routes.py').read_text()
    assert 'Reinserisci valori predefiniti mancanti' in html
    assert "admin_labels_restore_defaults" in html
    assert "@bp.route('/admin/labels/restore-defaults'" in routes
    assert 'restore_missing_default_config_labels()' in routes


def test_incident_detail_shows_incident_name_at_top_before_workflow():
    html = Path('app/templates/incident_detail.html').read_text()
    assert 'id="incident-page-title-heading"' in html
    assert '<h1 id="incident-page-title-heading">{{ inc.name }}</h1>' in html
    assert html.index('incident-page-title-heading') < html.index('id="incident-workflow"')


def test_desktop_workflow_layout_limits_steps_to_three_per_row():
    css = Path('app/static/style.css').read_text()
    assert '.workflow-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));' in css
    assert 'gap: .75rem 1.65rem;' in css
    assert '.workflow-steps-ordered { grid-template-columns: repeat(3, minmax(0, 1fr)); }' in css
    assert '.workflow-steps-ordered .workflow-step { width: 100%; min-width: 0; max-width: none; position: relative; }' in css
    assert '.workflow-step-arrow { display: none; }' in css
    assert '.workflow-steps-ordered .workflow-step-card:not(:nth-of-type(3n))::after' in css
    assert 'content: "→";' in css
    assert '@media (max-width: 720px) { .workflow-steps, .workflow-steps-ordered { grid-template-columns: 1fr;' in css
    assert 'content: "↓";' in css


def test_incident_workflow_steps_show_sequence_and_emphasized_clickable_task_box():
    html = Path('app/templates/incident_detail.html').read_text()
    css = Path('app/static/style.css').read_text()
    assert 'class="workflow-step-sequence"' in html
    assert 'aria-label="Fase {{ loop.index }}"' in html
    assert '{{ loop.index }}</span>' in html
    assert '.workflow-step-sequence{position:absolute;' in css
    assert '.workflow-step-task{cursor:pointer;border:3px solid #2563eb;' in css
    assert '.workflow-step-task:hover,.workflow-step-task:focus{border-color:#1d4ed8;' in css


def test_workflow_first_incomplete_phase_and_list_status_icons_are_present():
    routes = Path('app/routes.py').read_text()
    detail = Path('app/templates/incident_detail.html').read_text()
    index = Path('app/templates/index.html').read_text()
    css = Path('app/static/style.css').read_text()
    assert "first_incomplete = (not done and not first_missing_found)" in routes
    assert "'first_incomplete': first_incomplete" in routes
    assert 'workflow-first-incomplete-arrow' in detail
    assert 'Prima fase non completata' in detail
    assert 'workflow_list_state' in routes
    assert "'warning' if has_active_warnings" in routes
    assert 'procedure-finalized-icon' in index
    assert 'procedure-ok-icon' in index
    assert 'workflow_status_icon(i)' in index
    assert '.workflow-step.first-incomplete' in css
    assert '.workflow-first-incomplete-arrow' in css
    assert '.procedure-finalized-icon' in css
    assert '.procedure-ok-icon' in css


def test_incident_list_status_icons_follow_active_warning_and_closed_state(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import ConfigLabel, Incident, IncidentWorkflowStep
    from app.routes import annotate_procedural_status

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        action = ConfigLabel(kind='action_label', group='workflow-list-icons', value='Azione richiesta')
        db.session.add(action)
        db.session.flush()
        db.session.add(IncidentWorkflowStep(action_label_id=action.id, position=10, required=True))
        inc_warning = Incident(name='Warning', reference='W', status='aperto', creator_name='Test', creator_email='test@example.invalid')
        inc_finalized = Incident(name='Finalizzato', reference='F', status='in lavorazione', creator_name='Test', creator_email='test@example.invalid')
        inc_ok = Incident(name='Ok', reference='O', status='chiuso', creator_name='Test', creator_email='test@example.invalid')
        db.session.add_all([inc_warning, inc_finalized, inc_ok])
        db.session.flush()
        # I due incidenti senza workflow applicabile attivo non hanno avvisi pendenti.
        IncidentWorkflowStep.query.delete()
        db.session.commit()

        annotate_procedural_status([inc_finalized, inc_ok])
        assert inc_finalized.workflow_list_state == 'finalized'
        assert inc_ok.workflow_list_state == 'ok'

        db.session.add(IncidentWorkflowStep(action_label_id=action.id, position=10, required=True))
        db.session.commit()
        annotate_procedural_status([inc_warning])
        assert inc_warning.workflow_list_state == 'warning'
        assert inc_warning.has_procedural_warnings is True
