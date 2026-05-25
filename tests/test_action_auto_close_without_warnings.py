from datetime import datetime


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


def _incident(db, Incident, categories=None):
    inc = Incident(
        name='Auto close test',
        reference='REF-AUTO-CLOSE',
        status='aperto',
        creator_name='Test',
        creator_email='test@example.invalid',
    )
    if categories:
        inc.categories = categories
    db.session.add(inc)
    db.session.flush()
    return inc


def test_action_with_close_without_warnings_closes_after_resolving_last_warning(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)

    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep, Setting
    from app.routes import apply_action_automatic_operations, incident_procedural_status

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        Setting.query.filter_by(key='application_timezone').delete()
        db.session.add(Setting(key='application_timezone', value='Europe/Rome'))
        category = ConfigLabel(kind='category', group='workflow-test', value='Categoria chiusura automatica test')
        closing = ConfigLabel(
            kind='action_label',
            group='workflow-test',
            value='Chiusura test senza avvisi',
            automatic_operations='close_without_warnings',
        )
        db.session.add_all([category, closing])
        db.session.flush()
        db.session.add(IncidentWorkflowStep(category_id=category.id, action_label_id=closing.id, position=1, required=True))
        inc = _incident(db, Incident, [category])
        db.session.commit()

        # Carica la relazione azioni prima dell'inserimento, come accade nella rotta
        # quando vengono eseguiti i controlli di blocco workflow.
        assert inc.actions == []
        assert incident_procedural_status(inc)['has_warnings'] is True

        action = Action(
            incident_id=inc.id,
            when_at=datetime(2026, 5, 25, 10, 30),
            person_name='Operatore',
            label_id=closing.id,
            description='Chiusura finale',
        )
        db.session.add(action)
        db.session.flush()

        changed = apply_action_automatic_operations(inc.id, action)
        assert changed is True
        assert inc.status == 'chiuso'
        assert inc.end_date is not None
        assert inc.end_time is not None
        assert getattr(inc, '_closure_blocked_by_procedural_warnings', False) is False


def test_action_with_close_without_warnings_does_not_close_when_other_warning_remains(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)

    from app import create_app, db
    from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep
    from app.routes import apply_action_automatic_operations

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        category = ConfigLabel(kind='category', group='workflow-test', value='Categoria chiusura con residuo test')
        closing = ConfigLabel(
            kind='action_label',
            group='workflow-test',
            value='Chiusura test con altro avviso',
            automatic_operations='close_without_warnings',
        )
        other = ConfigLabel(
            kind='action_label',
            group='workflow-test',
            value='Task obbligatorio residuo',
            automatic_operations='',
        )
        db.session.add_all([category, closing, other])
        db.session.flush()
        db.session.add_all([
            IncidentWorkflowStep(category_id=category.id, action_label_id=closing.id, position=1, required=True),
            IncidentWorkflowStep(category_id=category.id, action_label_id=other.id, position=2, required=True),
        ])
        inc = _incident(db, Incident, [category])
        db.session.commit()
        assert inc.actions == []

        action = Action(
            incident_id=inc.id,
            when_at=datetime(2026, 5, 25, 10, 30),
            person_name='Operatore',
            label_id=closing.id,
            description='Tentativo chiusura',
        )
        db.session.add(action)
        db.session.flush()

        changed = apply_action_automatic_operations(inc.id, action)
        assert changed is False
        assert inc.status == 'aperto'
        assert getattr(inc, '_closure_blocked_by_procedural_warnings', False) is True
