import base64


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


def test_workflow_import_ignores_identical_existing_items_without_overwrite_warning(monkeypatch, tmp_path):
    _configure_test_env(monkeypatch, tmp_path)

    from app import create_app, db
    from app.models import ConfigLabel, FormTemplateBinary, FormTemplateConfig, IncidentWorkflowStep, NotificationTemplate, NotificationType
    from app.routes import apply_workflow_import, workflow_import_diff

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        # Isola il caso di test dai dati bootstrap, usando nomi univoci.
        label = ConfigLabel(kind='action_label', group='workflow-test', value='Azione identica test', description='Descrizione', max_completion_hours=4, default_exportable=True, automatic_operations='')
        nt = NotificationType(code='test_identical_notice', label='Avviso test', description='Descrizione tipo', enabled=True)
        form = FormTemplateConfig(template_name='identical_test_form.pdf', font_family='Helvetica', font_size=10, notification_tags='test_identical_notice')
        binary = FormTemplateBinary(template_name='identical_test_form.pdf', filename='identical_test_form.pdf', pdf_data=b'%PDF-test')
        db.session.add_all([label, nt, form, binary])
        db.session.flush()
        tpl = NotificationTemplate(kind='test_identical_notice', name='Template identico', subject='Oggetto', body='Corpo', linked_form_template_name='identical_test_form.pdf', action_label_id=label.id, recipient_source='manual', recipient_value='', recipient_editable=True, recipient_external_allowed=True, cc_source='manual', cc_value='', cc_editable=True, cc_external_allowed=True, is_default=False)
        step = IncidentWorkflowStep(category_id=None, action_label_id=label.id, position=990, description='Step identico', required=True, requires_notification=True, required_notification_type='test_identical_notice')
        step.set_condition_tokens(['personal_data'])
        db.session.add_all([tpl, step])
        db.session.commit()

        payload = {
            'format': 'cybersecurity-incident-registry.workflow.v1',
            'workflow': {
                'scope': 'default',
                'category': None,
                'steps': [{
                    'position': 990,
                    'action_label': {
                        'kind': 'action_label', 'group': 'workflow-test', 'value': 'Azione identica test',
                        'description': 'Descrizione', 'max_completion_hours': 4,
                        'default_exportable': True, 'automatic_operations': '',
                    },
                    'description': 'Step identico',
                    'conditions': ['personal_data'],
                    'required': True,
                    'requires_notification': True,
                    'required_notification_type': 'test_identical_notice',
                }],
            },
            'dependencies': {
                'labels': [{
                    'kind': 'action_label', 'group': 'workflow-test', 'value': 'Azione identica test',
                    'description': 'Descrizione', 'max_completion_hours': 4,
                    'default_exportable': True, 'automatic_operations': '',
                }],
                'notification_types': [{
                    'code': 'test_identical_notice', 'label': 'Avviso test',
                    'description': 'Descrizione tipo', 'enabled': True,
                }],
                'form_templates': [{
                    'template_name': 'identical_test_form.pdf', 'font_family': 'Helvetica',
                    'font_size': 10, 'notification_tags': ['test_identical_notice'],
                    'binary': {'filename': 'identical_test_form.pdf', 'pdf_base64': base64.b64encode(b'%PDF-test').decode('ascii')},
                }],
                'notification_templates': [{
                    'kind': 'test_identical_notice', 'name': 'Template identico',
                    'subject': 'Oggetto', 'body': 'Corpo',
                    'linked_form_template_name': 'identical_test_form.pdf',
                    'action_label': {'kind': 'action_label', 'value': 'Azione identica test'},
                    'recipient_source': 'manual', 'recipient_value': '',
                    'recipient_editable': True, 'recipient_external_allowed': True,
                    'cc_source': 'manual', 'cc_value': '',
                    'cc_editable': True, 'cc_external_allowed': True,
                    'is_default': False,
                }],
            },
        }

        assert workflow_import_diff(payload) == []
        result = apply_workflow_import(payload, overwrite_keys=[])
        assert result == {'created': 0, 'updated': 0, 'skipped': 0, 'unchanged': 5}
        assert ConfigLabel.query.filter_by(kind='action_label', value='Azione identica test').count() == 1
        assert NotificationType.query.filter_by(code='test_identical_notice').count() == 1
        assert FormTemplateConfig.query.filter_by(template_name='identical_test_form.pdf').count() == 1
        assert NotificationTemplate.query.filter_by(kind='test_identical_notice', name='Template identico').count() == 1
        assert IncidentWorkflowStep.query.filter_by(position=990, action_label_id=label.id).count() == 1
