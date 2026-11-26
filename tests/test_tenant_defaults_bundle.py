"""Complete portable tenant configuration, cross-instance keys and safe merge."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path

import pytest


@pytest.fixture
def bundle_apps(tmp_path, monkeypatch):
    from flask import Flask
    from sqlalchemy import event
    from app.models import db, Tenant
    from app.tenant_defaults import ensure_defaults_tenant
    from app.workflow_catalog_models import WorkflowCatalogEntry
    from app.tenant_defaults_models import TenantDefaultSource

    monkeypatch.delenv('SETTING_ENCRYPTION_KEY', raising=False)
    monkeypatch.delenv('SETTING_ENCRYPTION_KEY_FILE', raising=False)
    monkeypatch.delenv('SETTING_ENCRYPTION_PREVIOUS_KEYS', raising=False)

    @contextmanager
    def open_instance(name):
        root = tmp_path / name
        root.mkdir()
        app = Flask('bundle_' + name)
        app.config.update(TESTING=True, SECRET_KEY='a distinct secret for ' + name,
            SQLALCHEMY_DATABASE_URI='sqlite:///' + str(root / 'test.db'),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            FORM_TEMPLATE_DIR=str(root / 'forms'), LOGO_DIR=str(root / 'logos'),
            SSO_LOGO_DIR=str(root / 'sso'))
        for key in ('FORM_TEMPLATE_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR'):
            Path(app.config[key]).mkdir()
        db.init_app(app)
        with app.app_context():
            @event.listens_for(db.engine, 'connect')
            def foreign_keys(connection, _record):
                connection.execute('PRAGMA foreign_keys=ON')

            db.create_all()
            db.session.info['cir_defaults_suspended'] = True
            operational = Tenant(name='default')
            private = Tenant(name='private-unrelated')
            db.session.add_all([operational, private])
            defaults = ensure_defaults_tenant()
            db.session.commit()
            try:
                yield app, defaults, operational, private
            finally:
                db.session.rollback()
                db.session.remove()

    return open_instance


def _seed_source(tenant, unrelated):
    from app.models import (
        db, ConfigLabel, Recommendation, NotificationType, NotificationTemplate,
        ExternalRecipient, IncidentTemplate, BackupJob, IncidentWorkflowStep,
        FormTemplateConfig, FormTemplateBinary, FormFieldMapping, Setting, Incident,
    )
    from app.routes import store_setting_value, encrypt_backup_secret
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow

    labels = {}
    for kind, value in [('category', 'Response'), ('action_label', 'Review'),
                        ('severity', 'Urgent'), ('data_type', 'Contacts')]:
        row = ConfigLabel(tenant_id=tenant.id, kind=kind, value=value, description='Reusable ' + kind)
        db.session.add(row)
        labels[kind] = row
    recommendation = Recommendation(tenant_id=tenant.id, text='Reusable advice')
    notice = NotificationType(tenant_id=tenant.id, code='notice', label='Notify operators')
    db.session.add_all([recommendation, notice])
    db.session.flush()
    db.session.add_all([
        FormTemplateConfig(template_name='shared_form', owner_tenant_id=tenant.id,
                           font_family='Times-Roman', font_size=12, notification_tags='notice'),
        FormTemplateBinary(template_name='shared_form', filename='shared_form.pdf',
                           pdf_data=b'%PDF-1.4\n% Reusable source document\n%%EOF\n'),
        FormFieldMapping(template_name='shared_form', template_field='IncidentTitle', db_field='name'),
        NotificationTemplate(tenant_id=tenant.id, kind='notice', name='Reusable notice',
            subject='Incident update', body='Template body', action_label_id=labels['action_label'].id,
            linked_form_template_name='shared_form', recipient_source='manual',
            recipient_value='security@example.test', cc_source='manual', cc_value=''),
        ExternalRecipient(tenant_id=tenant.id, name='Security desk', email='security@example.test', notes='Shared service'),
        IncidentTemplate(tenant_id=tenant.id, name='Reusable incident', severity_id=labels['severity'].id,
            category_ids=str(labels['category'].id), data_type_ids=str(labels['data_type'].id),
            recommendation_ids=str(recommendation.id), people_ids=''),
        BackupJob(tenant_id=tenant.id, name='Shared backup', enabled=False, destination='s3',
            s3_bucket='backup-bucket', s3_access_key='example-access',
            s3_secret_key=encrypt_backup_secret('SOURCE-BACKUP-SECRET')),
        Incident(tenant_id=unrelated.id, name='PRIVATE INCIDENT NOT CONFIGURATION', reference='PRIVATE'),
        Setting(key=f'tenant:{unrelated.id}:smtp_password', value='PRIVATE OTHER TENANT SECRET'),
        Setting(key='application_external_url', value='https://server-only.example.test'),
    ])
    step = IncidentWorkflowStep(tenant_id=tenant.id, category_id=labels['category'].id,
        action_label_id=labels['action_label'].id, position=1, description='Editable source draft',
        required=True, requires_notification=True, required_notification_type='notice',
        document_generation_enabled=True, document_template_name='shared_form')
    step.set_condition_tokens([f"severity:{labels['severity'].id}", f"!data_type:{labels['data_type'].id}"])
    db.session.add(step)
    values = {
        'smtp_host': 'mail.example.test', 'smtp_password': 'SOURCE-SMTP-SECRET',
        'sso_profiles_json': json.dumps([{'id': 'corp', 'sso_enabled': '1',
            'sso_provider_name': 'Corporate identity', 'sso_client_id': 'portable-client',
            'sso_authorization_url': 'https://identity.example.test/auth',
            'sso_client_secret': 'SOURCE-SSO-SECRET'}]),
        'button_action_config_json': json.dumps({'action_label_id': labels['action_label'].id,
            'notification_type': notice.code, 'template_name': 'shared_form',
            'category_ids': str(labels['category'].id),
            'conditions': f"severity:{labels['severity'].id},!data_type:{labels['data_type'].id}"}),
    }
    for key, value in values.items():
        db.session.add(Setting(key=f'tenant:{tenant.id}:{key}', value=store_setting_value(key, value)))
    db.session.commit()
    entry = save_catalog_workflow(build_catalog_workflow_payload(tenant.id, labels['category'].id), 'Reusable catalog')
    db.session.commit()
    return {'labels': labels, 'step': step, 'entry': entry, 'notice': notice}


def _export(open_instance, *, include_secrets=False, operational=False):
    from app.models import db
    from app.tenant_defaults_bundle import export_defaults_bundle
    with open_instance('source') as (_app, defaults, ordinary, unrelated):
        source = ordinary if operational else defaults
        source.description = 'Portable source description'
        seeded = _seed_source(source, unrelated)
        payload = export_defaults_bundle(include_secrets=include_secrets,
            source_tenant_id=source.id if operational else None)
        source_ids = {kind: row.id for kind, row in seeded['labels'].items()}
        db.session.commit()
    return payload, source_ids


def test_complete_bundle_contains_configuration_documents_settings_drafts_and_catalog_only(bundle_apps):
    payload, _ = _export(bundle_apps)
    from app.tenant_defaults_bundle import BUNDLE_FORMAT
    assert payload['format'] == BUNDLE_FORMAT
    assert payload['tenant']['name'] == 'Tenants Default'
    assert {row['type'] for row in payload['configuration']['items']} == {
        'config_label', 'recommendation', 'notification_type', 'notification_template',
        'external_recipient', 'incident_template', 'backup_job',
    }
    assert len(payload['documents']) == len(payload['draft_workflows']) == len(payload['catalog']) == 1
    assert payload['documents'][0]['mappings'] == [{'template_field': 'IncidentTitle', 'db_field': 'name'}]
    assert payload['draft_workflows'][0]['steps'][0]['description'] == 'Editable source draft'
    raw = json.dumps(payload)
    assert 'PRIVATE' not in raw
    assert 'server-only.example.test' not in raw
    assert 'SOURCE-SMTP-SECRET' not in raw and 'SOURCE-SSO-SECRET' not in raw and 'SOURCE-BACKUP-SECRET' not in raw
    settings = {row['key']: row for row in payload['settings']}
    assert settings['smtp_password']['value'] == ''
    assert settings['smtp_password']['redacted_paths'] == [[]]
    profiles = settings['sso_profiles_json']
    assert profiles['value'][0]['sso_client_id'] == 'portable-client'
    assert profiles['value'][0]['sso_client_secret'] == ''
    assert profiles['redacted_paths'] == [[0, 'sso_client_secret']]


def test_complete_bundle_reencrypts_secrets_and_remaps_all_dependencies_in_new_instance(bundle_apps):
    from app.models import (db, Setting, ConfigLabel, NotificationTemplate, FormTemplateConfig,
                            FormTemplateBinary, FormFieldMapping, IncidentWorkflowStep, BackupJob, IncidentTemplate)
    from app.routes import decrypt_setting_value, decrypt_backup_secret
    from app.tenant_defaults_bundle import import_defaults_bundle
    from app.workflow_catalog_models import WorkflowCatalogEntry
    payload, source_ids = _export(bundle_apps, include_secrets=True)
    with bundle_apps('destination') as (_app, defaults, ordinary, _other):
        for index in range(9):
            db.session.add(ConfigLabel(tenant_id=ordinary.id, kind='severity', value=f'Existing {index}'))
        db.session.commit()
        result = import_defaults_bundle(payload)
        db.session.commit()
        assert result['documents'] == result['draft_workflows'] == result['catalog'] == 1
        assert defaults.description == 'Portable source description'
        assert WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=defaults.id).count() == 1
        step = IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id).one()
        assert step.action_label_id != source_ids['action_label']
        assert step.category_id != source_ids['category']
        assert step.document_template_name != 'shared_form'
        assert step.description == 'Editable source draft'
        for token in step.condition_tokens():
            label = db.session.get(ConfigLabel, int(token.split(':', 1)[1]))
            assert label.tenant_id == defaults.id
            assert label.id not in source_ids.values()
        template = NotificationTemplate.query.filter_by(tenant_id=defaults.id).one()
        assert template.action_label_id == step.action_label_id
        assert template.linked_form_template_name == step.document_template_name
        cfg = FormTemplateConfig.query.filter_by(template_name=step.document_template_name).one()
        assert cfg.owner_tenant_id == defaults.id and cfg.font_family == 'Times-Roman' and cfg.font_size == 12
        assert cfg.notification_tag_list == [step.required_notification_type]
        assert FormFieldMapping.query.filter_by(template_name=cfg.template_name).one().db_field == 'name'
        assert b'Reusable source document' in FormTemplateBinary.query.filter_by(template_name=cfg.template_name).one().pdf_data
        for key, expected in [('smtp_password', 'SOURCE-SMTP-SECRET')]:
            setting = db.session.get(Setting, f'tenant:{defaults.id}:{key}')
            assert setting.value.startswith('enc:v1:') and expected not in setting.value
            assert decrypt_setting_value(key, setting.value) == expected
        profiles = db.session.get(Setting, f'tenant:{defaults.id}:sso_profiles_json')
        assert profiles.value.startswith('enc:v1:')
        assert json.loads(decrypt_setting_value('sso_profiles_json', profiles.value))[0]['sso_client_secret'] == 'SOURCE-SSO-SECRET'
        backup = BackupJob.query.filter_by(tenant_id=defaults.id).one()
        assert backup.s3_secret_key.startswith('enc:v1:')
        assert decrypt_backup_secret(backup.s3_secret_key) == 'SOURCE-BACKUP-SECRET'
        buttons = json.loads(db.session.get(Setting, f'tenant:{defaults.id}:button_action_config_json').value)
        assert buttons['action_label_id'] == step.action_label_id
        assert buttons['template_name'] == cfg.template_name
        assert buttons['notification_type'] == step.required_notification_type
        assert buttons['conditions'] == step.conditions
        incident_template = IncidentTemplate.query.filter_by(tenant_id=defaults.id).one()
        assert incident_template.category_id_list() == [step.category_id]
        # Internal provenance must not retain clear-text encrypted credentials.
        internal = '\n'.join(row.value or '' for row in Setting.query.filter(Setting.key.startswith('__cir_defaults_bundle:')))
        assert 'SOURCE-SMTP-SECRET' not in internal and 'SOURCE-SSO-SECRET' not in internal


def test_reimport_is_stable_and_preserves_independently_edited_settings_documents_and_drafts(bundle_apps):
    from app.models import db, Setting, FormTemplateBinary, FormTemplateConfig, IncidentWorkflowStep
    from app.tenant_defaults_bundle import import_defaults_bundle
    from app.workflow_catalog_models import WorkflowCatalogEntry
    payload, _ = _export(bundle_apps)
    with bundle_apps('destination') as (_app, defaults, _ordinary, _other):
        import_defaults_bundle(payload)
        db.session.commit()
        original = IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id).one()
        original_id, original_form = original.id, original.document_template_name
        second = import_defaults_bundle(payload)
        db.session.commit()
        assert second['documents'] == second['draft_workflows'] == 0
        assert IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id).count() == 1
        assert FormTemplateBinary.query.count() == WorkflowCatalogEntry.query.count() == 1
        original.description = 'Locally edited draft'
        cfg = FormTemplateConfig.query.filter_by(template_name=original_form).one()
        cfg.font_size = 16
        setting = db.session.get(Setting, f'tenant:{defaults.id}:smtp_host')
        setting.value = 'locally-edited.example.test'
        db.session.commit()
        third = import_defaults_bundle(payload)
        db.session.commit()
        assert third['documents'] == third['draft_workflows'] == third['preserved_drafts'] == 1
        assert 'smtp_host' in third['preserved_settings']
        assert setting.value == 'locally-edited.example.test'
        assert db.session.get(IncidentWorkflowStep, original_id).description == 'Locally edited draft'
        assert FormTemplateConfig.query.filter_by(template_name=original_form).one().font_size == 16
        copied = IncidentWorkflowStep.query.filter(IncidentWorkflowStep.tenant_id == defaults.id, IncidentWorkflowStep.id != original_id).one()
        assert copied.document_template_name != original_form
        assert FormTemplateConfig.query.filter_by(template_name=copied.document_template_name).one().font_size == 12


def test_ordinary_tenant_bundle_is_scoped_and_imports_only_into_defaults(bundle_apps):
    from app.models import db, NotificationTemplate, IncidentWorkflowStep
    from app.tenant_defaults_bundle import import_defaults_bundle
    payload, _ = _export(bundle_apps, operational=True)
    assert payload['tenant']['is_system_defaults'] is False
    assert payload['tenant']['name'] == 'default'
    assert payload['catalog'] == []
    assert len(payload['documents']) == len(payload['draft_workflows']) == 1
    with bundle_apps('destination') as (_app, defaults, ordinary, _other):
        import_defaults_bundle(payload)
        db.session.commit()
        assert IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id).count() == 1
        assert IncidentWorkflowStep.query.filter_by(tenant_id=ordinary.id).count() == 0
        assert NotificationTemplate.query.filter_by(tenant_id=defaults.id).count() == 1


def test_ordinary_export_includes_inherited_settings_and_remaps_them_to_local_replicas(bundle_apps):
    from app.models import db, Setting, ConfigLabel
    from app.tenant_defaults import sync_defaults_configuration
    from app.tenant_defaults_bundle import export_defaults_bundle
    with bundle_apps('source') as (_app, defaults, ordinary, _other):
        action = ConfigLabel(tenant_id=defaults.id, kind='action_label', value='Shared action')
        db.session.add(action)
        db.session.flush()
        db.session.add_all([
            Setting(key=f'tenant:{defaults.id}:smtp_host', value='shared.example.test'),
            Setting(key=f'tenant:{defaults.id}:smtp_port', value='587'),
            Setting(key=f'tenant:{ordinary.id}:smtp_port', value='465'),
            Setting(key=f'tenant:{defaults.id}:scheduler_last_run_at', value='PRIVATE RUNTIME'),
            Setting(key=f'tenant:{defaults.id}:incident_button_action_labels_json',
                    value=json.dumps({'save': {'label_id': action.id}})),
        ])
        sync_defaults_configuration()
        db.session.commit()
        source_bundle = export_defaults_bundle()
        payload = export_defaults_bundle(source_tenant_id=ordinary.id)
        assert source_bundle['origin'] == payload['origin']
        assert source_bundle['bundle_id'] != payload['bundle_id']
        settings = {row['key']: row['value'] for row in payload['settings']}
        assert settings['smtp_host'] == 'shared.example.test'
        assert settings['smtp_port'] == '465'
        assert 'scheduler_last_run_at' not in settings
        reference = settings['incident_button_action_labels_json']['save']['label_id']['$cir_ref']
        action_item = next(row for row in payload['configuration']['items'] if row['key'] == reference)
        assert action_item['type'] == 'config_label' and action_item['data']['kind'] == 'action_label'


def test_bundles_from_two_tenants_in_one_instance_do_not_claim_each_others_settings(bundle_apps):
    from app.models import db, Setting
    from app.tenant_defaults_bundle import export_defaults_bundle, import_defaults_bundle
    with bundle_apps('source') as (_app, defaults, ordinary, _other):
        db.session.add_all([
            Setting(key=f'tenant:{defaults.id}:smtp_host', value='shared.example.test'),
            Setting(key=f'tenant:{ordinary.id}:smtp_host', value='ordinary.example.test'),
        ])
        db.session.commit()
        first = export_defaults_bundle()
        second = export_defaults_bundle(source_tenant_id=ordinary.id)
        db.session.commit()
    with bundle_apps('destination') as (_app, defaults, _ordinary, _other):
        import_defaults_bundle(first)
        db.session.commit()
        result = import_defaults_bundle(second)
        db.session.commit()
        assert result['preserved_settings'] == ['smtp_host']
        assert db.session.get(Setting, f'tenant:{defaults.id}:smtp_host').value == 'shared.example.test'


def test_legacy_unscoped_parameters_export_only_with_the_operational_default_tenant(bundle_apps):
    from app.models import db, Setting
    from app.routes import store_setting_value
    from app.tenant_defaults_bundle import export_defaults_bundle
    with bundle_apps('source') as (_app, defaults, ordinary, private):
        db.session.add_all([
            Setting(key='smtp_host', value='legacy.default.example.test'),
            Setting(key='smtp_password', value=store_setting_value('smtp_password', 'LEGACY-SECRET')),
            Setting(key='application_external_url', value='https://server-only.example.test'),
            Setting(key='scheduler_last_run_at', value='RUNTIME'),
        ])
        db.session.commit()
        shared_payload = export_defaults_bundle()
        other_payload = export_defaults_bundle(source_tenant_id=private.id)
        default_payload = export_defaults_bundle(source_tenant_id=ordinary.id)
        assert shared_payload['settings'] == other_payload['settings'] == []
        settings = {row['key']: row for row in default_payload['settings']}
        assert set(settings) == {'smtp_host', 'smtp_password'}
        assert settings['smtp_host']['value'] == 'legacy.default.example.test'
        assert settings['smtp_password']['value'] == ''
        assert settings['smtp_password']['redacted_paths'] == [[]]


def test_legacy_button_ids_and_aliases_are_portable_without_touching_unrelated_numbers(bundle_apps):
    from app.models import db, Setting, ConfigLabel, IncidentWorkflowStep
    from app.routes import BUTTON_ACTIONS_SETTING
    from app.tenant_defaults_bundle import export_defaults_bundle, import_defaults_bundle
    with bundle_apps('source') as (_app, defaults, _ordinary, other):
        source = _seed_source(defaults, other)
        action_id = source['labels']['action_label'].id
        db.session.add(Setting(key=f'tenant:{defaults.id}:{BUTTON_ACTIONS_SETTING}', value=json.dumps({
            'incident_update': action_id,
            'document_upload': [{'label_id': action_id, 'tags': ['notice'], 'generated_template_name': 'shared_form'}],
            'unrelated_future_number': 12345,
        })))
        db.session.commit()
        payload = export_defaults_bundle()
        exported = next(row['value'] for row in payload['settings'] if row['key'] == BUTTON_ACTIONS_SETTING)
        assert '$cir_ref' in exported['incident_update']['label_id']
        assert exported['document_upload'][0]['template_name'] == 'shared_form'
        assert '$cir_code' in exported['document_upload'][0]['notification_tags'][0]
        assert exported['unrelated_future_number'] == 12345
        db.session.commit()
    with bundle_apps('destination') as (_app, defaults, ordinary, _other):
        db.session.add_all([ConfigLabel(tenant_id=ordinary.id, kind='severity', value=f'Existing {i}') for i in range(8)])
        db.session.commit()
        import_defaults_bundle(payload)
        db.session.commit()
        actual = json.loads(db.session.get(Setting, f'tenant:{defaults.id}:{BUTTON_ACTIONS_SETTING}').value)
        step = IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id).one()
        assert actual['incident_update']['label_id'] == step.action_label_id
        assert actual['incident_update']['label_id'] != action_id
        assert actual['document_upload'][0]['template_name'] == step.document_template_name
        assert actual['document_upload'][0]['notification_tags'] == [step.required_notification_type]
        assert actual['unrelated_future_number'] == 12345


@pytest.mark.parametrize('corruption', ['raw_id', 'wrong_ref_kind', 'wrong_label_kind', 'missing_pdf', 'path_traversal',
                                      'bad_conditions', 'missing_asset', 'foreign_catalog', 'negative_redaction'])
def test_invalid_bundle_fails_before_any_import_mutation(bundle_apps, corruption):
    from app.models import db, ConfigLabel, FormTemplateBinary, Setting
    from app.tenant_defaults_bundle import import_defaults_bundle
    payload, _ = _export(bundle_apps)
    settings = {row['key']: row for row in payload['settings']}
    buttons = settings['button_action_config_json']['value']
    items = payload['configuration']['items']
    if corruption == 'raw_id':
        buttons['action_label_id'] = 1
    elif corruption == 'wrong_ref_kind':
        buttons['action_label_id']['$cir_ref'] = next(row['key'] for row in items if row['type'] == 'recommendation')
    elif corruption == 'wrong_label_kind':
        buttons['action_label_id']['$cir_ref'] = next(row['key'] for row in items if row['type'] == 'config_label' and row['data']['kind'] == 'severity')
    elif corruption == 'missing_pdf':
        payload['documents'] = []
    elif corruption == 'path_traversal':
        payload['documents'][0]['name'] = '../private'
    elif corruption == 'bad_conditions':
        payload['draft_workflows'][0]['steps'][0]['conditions'][0]['kind'] = 'data_type'
    elif corruption == 'missing_asset':
        payload['settings'].append({'key': 'logo_path', 'value': '/old/logos/logo.png', 'structured': False, 'redacted_paths': []})
    elif corruption == 'foreign_catalog':
        payload['tenant']['is_system_defaults'] = False
    elif corruption == 'negative_redaction':
        settings['sso_profiles_json']['redacted_paths'] = [[-1, 'sso_client_secret']]
    with bundle_apps('destination') as (_app, _defaults, _ordinary, _other):
        before = (ConfigLabel.query.count(), FormTemplateBinary.query.count(), Setting.query.count())
        with pytest.raises(ValueError):
            import_defaults_bundle(payload)
        assert (ConfigLabel.query.count(), FormTemplateBinary.query.count(), Setting.query.count()) == before
        assert not db.session.new


def test_export_rejects_private_pdf_owned_by_other_tenant(bundle_apps):
    from app.models import db, FormTemplateConfig
    from app.tenant_defaults_bundle import export_defaults_bundle
    with bundle_apps('source') as (_app, defaults, _ordinary, other):
        _seed_source(defaults, other)
        config = FormTemplateConfig.query.filter_by(template_name='shared_form').one()
        config.owner_tenant_id = other.id
        db.session.commit()
        with pytest.raises(ValueError, match='altro tenant'):
            export_defaults_bundle()


def test_export_pdf_suffix_alias_cannot_bypass_canonical_owner(bundle_apps):
    from app.models import db, FormTemplateConfig
    from app.tenant_defaults_bundle import _export_document
    with bundle_apps('source') as (app, defaults, _ordinary, other):
        db.session.add(FormTemplateConfig(template_name='foreign', owner_tenant_id=other.id))
        db.session.commit()
        (Path(app.config['FORM_TEMPLATE_DIR']) / 'foreign.pdf').write_bytes(b'%PDF-1.4 PRIVATE FOREIGN DOCUMENT')
        with pytest.raises(ValueError, match='altro tenant'):
            _export_document('foreign.pdf', {}, defaults.id)


def test_export_own_pdf_suffix_alias_preserves_canonical_field_mappings(bundle_apps):
    from app.models import db, FormTemplateConfig, FormTemplateBinary, FormFieldMapping
    from app.tenant_defaults_bundle import _export_document
    with bundle_apps('source') as (_app, defaults, _ordinary, _other):
        db.session.add_all([
            FormTemplateConfig(template_name='own', owner_tenant_id=defaults.id),
            FormTemplateBinary(template_name='own', filename='own.pdf', pdf_data=b'%PDF-1.4\n%%EOF\n'),
            FormFieldMapping(template_name='own', template_field='Title', db_field='name'),
        ])
        db.session.commit()
        exported = _export_document('own.pdf', {}, defaults.id)
        assert exported['mappings'] == [{'template_field': 'Title', 'db_field': 'name'}]


def test_import_never_overwrites_unrelated_same_name_document(bundle_apps):
    from app.models import db, FormTemplateBinary, FormTemplateConfig, IncidentWorkflowStep
    from app.tenant_defaults_bundle import import_defaults_bundle
    payload, _ = _export(bundle_apps)
    with bundle_apps('destination') as (_app, defaults, ordinary, _other):
        original = FormTemplateBinary(template_name='shared_form', filename='shared_form.pdf', pdf_data=b'%PDF-1.4 PRIVATE DESTINATION')
        original_config = FormTemplateConfig(template_name='shared_form', owner_tenant_id=ordinary.id, font_size=16)
        db.session.add_all([original, original_config])
        db.session.commit()
        import_defaults_bundle(payload)
        db.session.commit()
        assert original.pdf_data == b'%PDF-1.4 PRIVATE DESTINATION'
        assert original_config.owner_tenant_id == ordinary.id and original_config.font_size == 16
        assert IncidentWorkflowStep.query.filter_by(tenant_id=defaults.id).one().document_template_name != 'shared_form'


def test_export_rejects_tampered_catalog_snapshot(bundle_apps):
    from app.models import db
    from app.tenant_defaults_bundle import export_defaults_bundle
    with bundle_apps('source') as (_app, defaults, _ordinary, other):
        seeded = _seed_source(defaults, other)
        seeded['entry'].payload_hash = '0' * 64
        db.session.commit()
        with pytest.raises(ValueError, match='Impronta'):
            export_defaults_bundle()


def test_ordinary_bundle_resolves_shared_pdf_tag_through_provenance_despite_code_collision(bundle_apps):
    from app.models import db, Setting, NotificationType
    from app.tenant_defaults import sync_defaults_configuration
    from app.tenant_defaults_bundle import export_defaults_bundle
    with bundle_apps('source') as (_app, defaults, ordinary, other):
        _seed_source(defaults, other)
        # The synthetic generic setting used by the other tests is not one of
        # the application's inherited typed button settings.
        db.session.delete(db.session.get(Setting, f'tenant:{defaults.id}:button_action_config_json'))
        db.session.add(NotificationType(tenant_id=ordinary.id, code='notice', label='LOCAL UNRELATED NOTICE'))
        sync_defaults_configuration()
        db.session.commit()
        payload = export_defaults_bundle(source_tenant_id=ordinary.id)
        reference = payload['documents'][0]['notification_refs'][0]
        item = next(row for row in payload['configuration']['items'] if row['key'] == reference)
        assert item['type'] == 'notification_type'
        assert item['data']['code'] == 'notice'
        assert item['data']['label'] == 'LOCAL UNRELATED NOTICE'
        assert len([r for r in payload['configuration']['items'] if r['type'] == 'notification_type' and r['data']['code'] == 'notice']) == 1


def test_redacted_reimport_keeps_previously_imported_secrets(bundle_apps):
    from app.models import db, Setting, BackupJob
    from app.routes import decrypt_setting_value, decrypt_backup_secret
    from app.tenant_defaults_bundle import import_defaults_bundle
    payload, _ = _export(bundle_apps, include_secrets=True)
    redacted = copy.deepcopy(payload)
    redacted['includes_secrets'] = False
    for setting in redacted['settings']:
        if setting['key'] == 'smtp_password':
            setting.update(value='', redacted_paths=[[]])
        if setting['key'] == 'sso_profiles_json':
            setting['value'][0]['sso_client_secret'] = ''
            setting['redacted_paths'] = [[0, 'sso_client_secret']]
    for item in redacted['configuration']['items']:
        if item['type'] == 'backup_job':
            item['data']['s3_secret_key'] = ''
            item['redacted_fields'] = ['s3_secret_key']
    with bundle_apps('destination') as (_app, defaults, _ordinary, _other):
        import_defaults_bundle(payload)
        db.session.commit()
        import_defaults_bundle(redacted)
        db.session.commit()
        setting = db.session.get(Setting, f'tenant:{defaults.id}:smtp_password')
        assert decrypt_setting_value('smtp_password', setting.value) == 'SOURCE-SMTP-SECRET'
        setting = db.session.get(Setting, f'tenant:{defaults.id}:sso_profiles_json')
        assert json.loads(decrypt_setting_value('sso_profiles_json', setting.value))[0]['sso_client_secret'] == 'SOURCE-SSO-SECRET'
        assert decrypt_backup_secret(BackupJob.query.filter_by(tenant_id=defaults.id).one().s3_secret_key) == 'SOURCE-BACKUP-SECRET'
