from pathlib import Path


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


def test_incident_template_edit_uses_stored_category_order():
    dnd = Path('app/templates/dnd_fields.html').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    assert 'selected_template_categories=_objects_by_ids_preserving_order' in routes
    assert '{% for l in ordered_categories %}' in dnd
    assert 'for l in categories if l.id in selected_template.category_id_list()' not in dnd


def test_objects_by_ids_preserving_order_keeps_drag_drop_sequence(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import ConfigLabel
    from app.routes import _objects_by_ids_preserving_order

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        first = ConfigLabel(kind='category', group='test', value='Prima')
        second = ConfigLabel(kind='category', group='test', value='Seconda')
        third = ConfigLabel(kind='category', group='test', value='Terza')
        db.session.add_all([first, second, third])
        db.session.commit()

        ordered = _objects_by_ids_preserving_order(ConfigLabel, [third.id, first.id, second.id])
        assert [x.id for x in ordered] == [third.id, first.id, second.id]


def test_cleanup_orphan_generated_documents_removes_only_generated_unlinked_files(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)
    from app import create_app, db
    from app.models import Document, FormTemplateBinary, Incident
    from app.routes import cleanup_orphan_generated_documents

    app = create_app()
    app.config['TESTING'] = True
    upload_dir = Path(app.config['UPLOAD_DIR'])
    with app.app_context():
        db.session.add(FormTemplateBinary(template_name='TemplateA', filename='TemplateA.pdf', pdf_data=b'%PDF-1.4'))
        inc = Incident(name='Incident linked', reference='R', status='aperto', creator_name='Test')
        db.session.add(inc)
        db.session.flush()

        linked = upload_dir / 'TemplateA-1-a1b2c3d4.pdf'
        orphan = upload_dir / 'TemplateA-2-deadbeef.pdf'
        manual = upload_dir / 'manuale-non-referenziato.pdf'
        stale = upload_dir / 'stale-generated.pdf'
        for path in [linked, orphan, manual, stale]:
            path.write_bytes(b'PDF')
        db.session.add(Document(incident_id=inc.id, filename=linked.name, stored_name=linked.name, generated_template_name='TemplateA'))
        db.session.add(Document(incident_id=999999, filename=stale.name, stored_name=stale.name, generated_template_name='TemplateA'))
        db.session.commit()

        removed, errors = cleanup_orphan_generated_documents(str(upload_dir))
        assert errors == []
        removed_names = {item['name'] for item in removed}
        assert orphan.name in removed_names
        assert stale.name in removed_names
        assert linked.exists()
        assert manual.exists()
        assert not orphan.exists()
        assert not stale.exists()
        assert Document.query.filter_by(stored_name=stale.name).first() is None


def test_admin_other_configurations_exposes_orphan_cleanup_button():
    html = Path('app/templates/admin_other_configurations.html').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    assert 'Cleanup documenti orfani' in html
    assert 'cleanup_orphan_generated_documents' in html
    assert "action == 'cleanup_orphan_generated_documents'" in routes
