"""Portable catalog dependency graphs, tenant isolation and non-destructive import."""
import base64
import copy
import json

import pytest


@pytest.fixture
def catalog_db(tmp_path):
    from flask import Flask
    from app.models import db, Tenant
    from app.workflow_catalog_models import WorkflowCatalogEntry, WorkflowCatalogInstallation
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica, TenantDefaultAlert

    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///' + str(tmp_path / 'catalog.db'),
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, FORM_TEMPLATE_DIR=str(tmp_path / 'forms'))
    (tmp_path / 'forms').mkdir()
    db.init_app(app)
    with app.app_context():
        db.create_all()
        # Do not let globally registered listeners from an earlier test change
        # this service-only fixture. Application integration is tested elsewhere.
        db.session.info['cir_defaults_suspended'] = True
        source = Tenant(name='source')
        target = Tenant(name='target')
        db.session.add_all([source, target])
        db.session.commit()
        yield app, source, target
        db.session.remove()


def _source_workflow(source):
    from app.models import (db, ConfigLabel, IncidentWorkflowStep, NotificationType,
                            NotificationTemplate, FormTemplateConfig, FormTemplateBinary,
                            FormFieldMapping, Setting)
    labels = {}
    for kind, name in [('category', 'Network breach'), ('action_label', 'Triage'),
                       ('severity', 'Critical'), ('data_type', 'Contact data')]:
        row = ConfigLabel(tenant_id=source.id, kind=kind, value=name,
                          description='Reusable configuration', description_required=kind == 'action_label')
        db.session.add(row)
        labels[kind] = row
    db.session.flush()
    db.session.add(NotificationType(tenant_id=source.id, code='notice', label='Reusable notice'))
    db.session.add(NotificationType(tenant_id=source.id, code='private_other', label='PRIVATE unrelated type'))
    db.session.add(Setting(key=f'tenant:{source.id}:smtp_password', value='PRIVATE_SMTP_SECRET'))
    db.session.add(FormTemplateConfig(template_name='triage_form', notification_tags='notice'))
    db.session.add(FormTemplateBinary(template_name='triage_form', filename='triage_form.pdf',
                                     pdf_data=b'%PDF-1.4\n% Reusable template\n%%EOF\n'))
    db.session.add(FormFieldMapping(template_name='triage_form', template_field='IncidentName', db_field='name'))
    db.session.add(NotificationTemplate(tenant_id=source.id, kind='notice', name='Notify',
        subject='Triage update', body='Reusable body', action_label_id=labels['action_label'].id,
        recipient_source='fixed', recipient_value='private-recipient@example.test',
        recipient_editable=False, recipient_external_allowed=False,
        cc_source='fixed', cc_value='private-cc@example.test', cc_editable=True,
        cc_external_allowed=True))
    step = IncidentWorkflowStep(tenant_id=source.id, category_id=labels['category'].id,
        action_label_id=labels['action_label'].id, position=1, description='Investigate',
        document_generation_enabled=True, document_template_name='triage_form',
        requires_notification=True, required_notification_type='notice')
    step.set_condition_tokens([f"severity:{labels['severity'].id}", f"!data_type:{labels['data_type'].id}", 'personal_data'])
    db.session.add(step)
    db.session.commit()
    return labels, step


def test_catalog_round_trip_remaps_dependencies_and_keeps_local_configuration(catalog_db):
    from app.models import (db, ConfigLabel, IncidentWorkflowStep, NotificationType,
                            NotificationTemplate, FormTemplateConfig, FormTemplateBinary, FormFieldMapping)
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    app, source, target = catalog_db
    labels, original_step = _source_workflow(source)
    local_labels = []
    for kind, original in labels.items():
        row = ConfigLabel(tenant_id=target.id, kind=kind, value=original.value, description='LOCAL ORIGINAL')
        db.session.add(row)
        local_labels.append(row)
    local_notice = NotificationType(tenant_id=target.id, code='notice', label='LOCAL NOTICE')
    db.session.add(local_notice)
    db.session.commit()
    original_pdf = bytes(FormTemplateBinary.query.filter_by(template_name='triage_form').one().pdf_data)
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    assert len(payload['workflow']['steps']) == 1
    assert payload['dependencies']['form_templates'][0]['mappings'] == [{'template_field': 'IncidentName', 'db_field': 'name'}]
    raw = json.dumps(payload)
    assert 'PRIVATE_' not in raw
    assert 'private-recipient@example.test' in raw and 'private-cc@example.test' in raw
    entry = save_catalog_workflow(payload, 'Incident triage')
    result = import_catalog_workflow(entry.id, target.id)
    db.session.commit()
    assert result['created'] == 1
    installed = db.session.get(IncidentWorkflowStep, result['step_ids'][0])
    assert installed.tenant_id == target.id
    assert installed.action_label_id != original_step.action_label_id
    assert installed.action_label_id not in {row.id for row in local_labels}
    assert installed.category_id not in {row.id for row in local_labels}
    assert installed.required_notification_type != 'notice'
    assert installed.document_template_name != 'triage_form'
    for token in installed.condition_tokens():
        if ':' in token:
            row = db.session.get(ConfigLabel, int(token.split(':', 1)[1]))
            assert row.tenant_id == target.id
            assert row.id not in {row.id for row in local_labels}
    assert installed.condition_tokens()[1].startswith('!data_type:')
    assert all(row.description == 'LOCAL ORIGINAL' for row in local_labels)
    assert local_notice.label == 'LOCAL NOTICE'
    assert bytes(FormTemplateBinary.query.filter_by(template_name='triage_form').one().pdf_data) == original_pdf
    cfg = FormTemplateConfig.query.filter_by(template_name=installed.document_template_name).one()
    assert cfg.owner_tenant_id == target.id
    assert cfg.notification_tag_list == [installed.required_notification_type]
    assert FormFieldMapping.query.filter_by(template_name=installed.document_template_name).one().db_field == 'name'
    template = NotificationTemplate.query.filter_by(tenant_id=target.id, kind=installed.required_notification_type).one()
    assert template.action_label_id == installed.action_label_id
    assert template.recipient_source == 'fixed' and template.recipient_value == 'private-recipient@example.test'
    assert template.recipient_editable is False and template.recipient_external_allowed is False
    assert template.cc_source == 'fixed' and template.cc_value == 'private-cc@example.test'
    assert template.cc_editable is True and template.cc_external_allowed is True
    # No file side effects before/after this DB-only service transaction.
    from pathlib import Path
    assert not (Path(app.config['FORM_TEMPLATE_DIR']) / (installed.document_template_name + '.pdf')).exists()


def test_catalog_repeated_import_creates_named_copies_and_revision_does_not_change_them(catalog_db):
    from app.models import db, ConfigLabel, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    from app.workflow_catalog_models import WorkflowCatalogInstallation
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    entry = save_catalog_workflow(payload, 'Triage')
    first = import_catalog_workflow(entry.id, target.id, copy_name='Triage gruppo A')
    second = import_catalog_workflow(entry.id, target.id, copy_name='Triage gruppo B')
    db.session.commit()
    assert first['created'] == second['created'] == 1
    assert first['step_ids'] != second['step_ids']
    assert first['category_id'] != second['category_id']
    assert first['installation_id'] != second['installation_id']
    assert db.session.get(ConfigLabel, first['category_id']).value == 'Triage gruppo A'
    assert db.session.get(ConfigLabel, second['category_id']).value == 'Triage gruppo B'
    receipts = WorkflowCatalogInstallation.query.filter_by(entry_id=entry.id, tenant_id=target.id, entry_version=1).all()
    assert len(receipts) == 2
    assert {r.copy_name for r in receipts} == {'Triage gruppo A', 'Triage gruppo B'}
    installed = db.session.get(IncidentWorkflowStep, first['step_ids'][0])
    installed.description = 'LOCAL EDIT'
    db.session.commit()
    payload['workflow']['steps'][0]['description'] = 'New catalog revision'
    revised = save_catalog_workflow(payload, 'Triage', entry_id=entry.id)
    db.session.commit()
    assert revised.version == 2
    assert installed.description == 'LOCAL EDIT'
    third = import_catalog_workflow(entry.id, target.id, copy_name='Triage nuova revisione')
    db.session.commit()
    assert third['created'] == 1 and third['category_id'] not in {first['category_id'], second['category_id']}
    assert installed.description == 'LOCAL EDIT'


def test_catalog_copy_remains_after_catalog_retirement(catalog_db):
    from app.models import db, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow, export_catalog_entry
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    entry = save_catalog_workflow(build_catalog_workflow_payload(source.id, labels['category'].id), 'Triage')
    result = import_catalog_workflow(entry.id, target.id)
    entry.active = False
    db.session.commit()
    assert db.session.get(IncidentWorkflowStep, result['step_ids'][0]) is not None
    with pytest.raises(ValueError, match='non disponibile'):
        import_catalog_workflow(entry.id, target.id)
    with pytest.raises(ValueError, match='non disponibile'):
        export_catalog_entry(entry.id)


def test_catalog_rejects_cross_tenant_label_references(catalog_db):
    from app.models import db, ConfigLabel
    from app.workflow_catalog import build_catalog_workflow_payload
    _, source, target = catalog_db
    labels, step = _source_workflow(source)
    foreign = ConfigLabel(tenant_id=target.id, kind='severity', value='PRIVATE FOREIGN')
    db.session.add(foreign)
    db.session.flush()
    step.conditions = f'severity:{foreign.id}'
    db.session.commit()
    with pytest.raises(ValueError, match='Condizione'):
        build_catalog_workflow_payload(source.id, labels['category'].id)
    with pytest.raises(ValueError, match='Categoria'):
        build_catalog_workflow_payload(target.id, labels['category'].id)


def test_catalog_default_workflow_cannot_overwrite_existing_default(catalog_db):
    from app.models import db, ConfigLabel, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, step = _source_workflow(source)
    step.category_id = None
    db.session.commit()
    payload = build_catalog_workflow_payload(source.id)
    entry = save_catalog_workflow(payload, 'Default triage')
    existing_label = ConfigLabel(tenant_id=target.id, kind='action_label', value='Existing local')
    db.session.add(existing_label)
    db.session.flush()
    existing_step = IncidentWorkflowStep(tenant_id=target.id, action_label_id=existing_label.id, position=1)
    db.session.add(existing_step)
    db.session.commit()
    with pytest.raises(ValueError, match='già un workflow di default'):
        import_catalog_workflow(entry.id, target.id, as_default=True)
    assert IncidentWorkflowStep.query.filter_by(tenant_id=target.id).count() == 1
    copied = import_catalog_workflow(entry.id, target.id)
    db.session.commit()
    assert copied['category_id'] is not None
    assert existing_step.category_id is None


def test_catalog_default_workflow_can_be_installed_into_empty_default(catalog_db):
    from app.models import db, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    entry = save_catalog_workflow(build_catalog_workflow_payload(source.id, labels['category'].id), 'Triage')
    result = import_catalog_workflow(entry.id, target.id, as_default=True)
    db.session.commit()
    assert result['category_id'] is None
    assert IncidentWorkflowStep.query.filter_by(tenant_id=target.id, category_id=None).count() == 1


def test_catalog_custom_step_type_collisions_fit_postgresql_varchar_20(catalog_db):
    from app.models import db, Setting, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, step = _source_workflow(source)
    code = 'custom_triage_type'
    step.step_type = code
    db.session.add(Setting(key=f'tenant:{source.id}:workflow_step_types_json', value=json.dumps([
        {'code': code, 'label': 'Source triage', 'description': 'Source semantics'}])))
    db.session.add(Setting(key=f'tenant:{target.id}:workflow_step_types_json', value=json.dumps([
        {'code': code, 'label': 'LOCAL TYPE', 'description': 'LOCAL'}])))
    db.session.commit()
    entry = save_catalog_workflow(build_catalog_workflow_payload(source.id, labels['category'].id), 'Custom triage')
    result = import_catalog_workflow(entry.id, target.id)
    db.session.commit()
    installed = db.session.get(IncidentWorkflowStep, result['step_ids'][0])
    assert installed.step_type != code
    assert len(installed.step_type) <= 20
    settings = json.loads(db.session.get(Setting, f'tenant:{target.id}:workflow_step_types_json').value)
    assert next(row for row in settings if row['code'] == code)['label'] == 'LOCAL TYPE'
    assert next(row for row in settings if row['code'] == installed.step_type)['label'] == 'Source triage'


def test_catalog_validation_and_transaction_rollback_leave_no_partial_install(catalog_db):
    from app.models import db, IncidentWorkflowStep, ConfigLabel
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    from app.workflow_catalog_models import WorkflowCatalogInstallation
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    entry = save_catalog_workflow(payload, 'Triage')
    db.session.commit()
    import_catalog_workflow(entry.id, target.id)
    db.session.rollback()
    assert IncidentWorkflowStep.query.filter_by(tenant_id=target.id).count() == 0
    assert ConfigLabel.query.filter_by(tenant_id=target.id).count() == 0
    assert WorkflowCatalogInstallation.query.filter_by(tenant_id=target.id).count() == 0


@pytest.mark.parametrize('alteration', [
    'unsafe_pdf_path', 'bad_pdf_base64', 'not_pdf', 'missing_label', 'wrong_condition_kind',
    'missing_notification', 'missing_form', 'duplicate_label_ref', 'invalid_boolean', 'malformed_font',
    'invalid_address_source', 'oversize_address', 'invalid_address_flag',
])
def test_catalog_rejects_incomplete_or_malformed_dependencies(catalog_db, alteration):
    from app.workflow_catalog import build_catalog_workflow_payload, validate_catalog_payload, save_catalog_workflow
    from app.workflow_catalog_models import WorkflowCatalogEntry
    _, source, _ = catalog_db
    labels, _ = _source_workflow(source)
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    deps = payload['dependencies']
    step = payload['workflow']['steps'][0]
    if alteration == 'unsafe_pdf_path':
        deps['form_templates'][0]['template_name'] = '../../outside'
    elif alteration == 'bad_pdf_base64':
        deps['form_templates'][0]['binary']['pdf_base64'] = '%%%'
    elif alteration == 'not_pdf':
        deps['form_templates'][0]['binary']['pdf_base64'] = base64.b64encode(b'not a PDF').decode()
    elif alteration == 'missing_label':
        step['action_label_ref'] = 'nonexistent'
    elif alteration == 'wrong_condition_kind':
        step['conditions'][0]['kind'] = ['severity']
    elif alteration == 'missing_notification':
        step['required_notification_type'] = 'not_included'
    elif alteration == 'missing_form':
        step['document_template_name'] = 'not_included'
    elif alteration == 'duplicate_label_ref':
        deps['labels'].append(copy.deepcopy(deps['labels'][0]))
    elif alteration == 'invalid_boolean':
        step['required'] = 'false'
    elif alteration == 'malformed_font':
        deps['form_templates'][0]['font_family'] = []
    elif alteration == 'invalid_address_source':
        deps['notification_templates'][0]['recipient_source'] = 'shell_command'
    elif alteration == 'oversize_address':
        deps['notification_templates'][0]['cc_value'] = 'a' * 256
    elif alteration == 'invalid_address_flag':
        deps['notification_templates'][0]['recipient_editable'] = 'false'
    with pytest.raises(ValueError):
        validate_catalog_payload(payload)
    with pytest.raises(ValueError):
        save_catalog_workflow(payload, 'Invalid')
    assert WorkflowCatalogEntry.query.count() == 0


def test_catalog_rejects_legacy_ambiguous_condition_ids(catalog_db):
    from app.workflow_catalog import validate_catalog_payload
    label = {'kind': 'action_label', 'value': 'Triage'}
    payload = {'format': 'cybersecurity-incident-registry.workflow.v1',
               'dependencies': {'labels': [label]},
               'workflow': {'category': None, 'steps': [
                   {'action_label': label, 'conditions': ['severity:123']}]}}
    with pytest.raises(ValueError, match='non rimappabili'):
        validate_catalog_payload(payload)


def test_catalog_accepts_legacy_workflow_without_ambiguous_ids(catalog_db):
    from app.workflow_catalog import validate_catalog_payload, CATALOG_FORMAT
    label = {'kind': 'action_label', 'value': 'Triage'}
    payload = {'format': 'cybersecurity-incident-registry.workflow.v1',
               'dependencies': {'labels': [label]},
               'workflow': {'category': None, 'steps': [
                   {'action_label': label, 'conditions': ['personal_data']}]}}
    normalized = validate_catalog_payload(payload)
    assert normalized['format'] == CATALOG_FORMAT
    assert normalized['workflow']['steps'][0]['conditions'] == [{'kind': 'personal_data', 'negated': False}]


def test_catalog_import_rejects_changed_payload_fingerprint(catalog_db):
    from app.models import db
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    entry = save_catalog_workflow(build_catalog_workflow_payload(source.id, labels['category'].id), 'Triage')
    payload = json.loads(entry.payload_json)
    payload['workflow']['steps'][0]['description'] = 'Changed without updating fingerprint'
    entry.payload_json = json.dumps(payload)
    db.session.commit()
    with pytest.raises(ValueError, match='impronta'):
        import_catalog_workflow(entry.id, target.id)


def test_catalog_preserves_inherited_legacy_custom_step_settings(catalog_db):
    from app.models import db, Setting, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, step = _source_workflow(source)
    step.step_type = 'legacy_triage'
    legacy = [{'code': 'legacy_triage', 'label': 'Legacy triage', 'description': 'Reusable'},
              {'code': 'unrelated_type', 'label': 'Preserved unrelated', 'description': 'Do not lose'}]
    db.session.add(Setting(key=f'tenant:{source.id}:workflow_step_types_json', value=json.dumps(legacy)))
    db.session.commit()
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    assert [row['code'] for row in payload['dependencies']['step_types']] == ['legacy_triage']
    entry = save_catalog_workflow(payload, 'Legacy workflow')
    result = import_catalog_workflow(entry.id, target.id)
    db.session.commit()
    installed = db.session.get(IncidentWorkflowStep, result['step_ids'][0])
    assert installed.step_type == 'legacy_triage'
    stored = json.loads(db.session.get(Setting, f'tenant:{target.id}:workflow_step_types_json').value)
    assert [item["code"] for item in stored] == ["legacy_triage"]
    assert stored[0]["label"] == "Legacy triage"
    assert db.session.get(Setting, 'workflow_step_types_json') is None


def test_catalog_copy_parameters_and_documents_are_independent(catalog_db):
    from app.models import (db, IncidentWorkflowStep, NotificationTemplate, FormTemplateConfig,
                            FormTemplateBinary, FormFieldMapping)
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow, export_catalog_entry
    _, source, target = catalog_db
    labels, source_step = _source_workflow(source)
    snapshot = build_catalog_workflow_payload(source.id, labels['category'].id)
    entry = save_catalog_workflow(snapshot, 'Reusable triage')
    first = import_catalog_workflow(entry.id, target.id, copy_name='Triage sicurezza')
    second = import_catalog_workflow(entry.id, target.id, copy_name='Triage privacy')
    db.session.commit()
    a = db.session.get(IncidentWorkflowStep, first['step_ids'][0])
    b = db.session.get(IncidentWorkflowStep, second['step_ids'][0])
    assert a.action_label_id != b.action_label_id
    assert a.required_notification_type != b.required_notification_type
    assert a.document_template_name != b.document_template_name
    assert a.conditions != b.conditions
    first_template = NotificationTemplate.query.filter_by(tenant_id=target.id, kind=a.required_notification_type).one()
    second_template = NotificationTemplate.query.filter_by(tenant_id=target.id, kind=b.required_notification_type).one()
    a.action_label.max_completion_hours = 72
    a.action_label.description = 'Local changed action'
    a.description = 'Local changed step'
    a.set_condition_tokens([])
    first_template.body = 'Local changed notification'
    first_template.recipient_source = 'incident_creator_email'
    first_template.recipient_value = 'first-only@example.test'
    first_template.recipient_editable = True
    first_template.recipient_external_allowed = True
    first_template.cc_source = 'empty'
    first_template.cc_value = ''
    first_template.cc_editable = False
    first_template.cc_external_allowed = False
    FormTemplateConfig.query.filter_by(template_name=a.document_template_name).one().font_size = 16
    FormTemplateBinary.query.filter_by(template_name=a.document_template_name).one().pdf_data = b'%PDF-1.4\n%LOCAL\n%%EOF'
    FormFieldMapping.query.filter_by(template_name=a.document_template_name).one().db_field = 'description'
    db.session.commit()
    assert b.action_label.max_completion_hours == 0
    assert b.action_label.description == 'Reusable configuration'
    assert b.description == 'Investigate' and b.condition_tokens()
    assert second_template.body == 'Reusable body'
    assert second_template.recipient_source == 'fixed'
    assert second_template.recipient_value == 'private-recipient@example.test'
    assert second_template.recipient_editable is False and second_template.recipient_external_allowed is False
    assert second_template.cc_source == 'fixed' and second_template.cc_value == 'private-cc@example.test'
    assert second_template.cc_editable is True and second_template.cc_external_allowed is True
    assert FormTemplateConfig.query.filter_by(template_name=b.document_template_name).one().font_size == 10
    assert FormTemplateBinary.query.filter_by(template_name=b.document_template_name).one().pdf_data == b'%PDF-1.4\n% Reusable template\n%%EOF\n'
    assert FormFieldMapping.query.filter_by(template_name=b.document_template_name).one().db_field == 'name'
    assert source_step.description == 'Investigate'
    assert export_catalog_entry(entry.id) == snapshot


def test_catalog_repeated_names_are_disambiguated_without_overwrite(catalog_db):
    from app.models import db, ConfigLabel
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    entry = save_catalog_workflow(build_catalog_workflow_payload(source.id, labels['category'].id), 'Triage')
    results = [import_catalog_workflow(entry.id, target.id, copy_name='Same name') for _ in range(3)]
    db.session.commit()
    values = [db.session.get(ConfigLabel, r['category_id']).value for r in results]
    assert values[0] == 'Same name'
    assert len(set(values)) == 3
    assert len({r['installation_id'] for r in results}) == 3


@pytest.mark.parametrize('copy_name', ['', '   ', 'x' * 161, [], 42])
def test_catalog_rejects_invalid_copy_name_before_creating_rows(catalog_db, copy_name):
    from app.models import db, ConfigLabel
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    entry = save_catalog_workflow(build_catalog_workflow_payload(source.id, labels['category'].id), 'Triage')
    db.session.commit()
    with pytest.raises(ValueError, match='Nome della copia'):
        import_catalog_workflow(entry.id, target.id, copy_name=copy_name)
    assert ConfigLabel.query.filter_by(tenant_id=target.id).count() == 0


def test_catalog_custom_types_resolve_shared_defaults_before_legacy(catalog_db):
    from app.models import db, Setting, IncidentWorkflowStep
    from app.tenant_defaults import ensure_defaults_tenant
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, step = _source_workflow(source)
    shared = ensure_defaults_tenant()
    step.step_type = 'shared_triage'
    shared_types = [{'code': 'shared_triage', 'label': 'Shared triage', 'description': 'Reusable'},
                    {'code': 'shared_other', 'label': 'Keep shared definition', 'description': 'Reusable'}]
    db.session.add(Setting(key=f'tenant:{shared.id}:workflow_step_types_json', value=json.dumps(shared_types)))
    db.session.add(Setting(key='workflow_step_types_json', value=json.dumps([
        {'code': 'private_legacy', 'label': 'PRIVATE LEGACY', 'description': 'Never copied'}])))
    db.session.commit()
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    assert [row['code'] for row in payload['dependencies']['step_types']] == ['shared_triage']
    assert 'PRIVATE LEGACY' not in json.dumps(payload)
    entry = save_catalog_workflow(payload, 'Shared triage')
    result = import_catalog_workflow(entry.id, target.id, copy_name='Copied shared triage')
    db.session.commit()
    copy = db.session.get(IncidentWorkflowStep, result['step_ids'][0])
    assert copy.step_type != 'shared_triage'
    target_types = json.loads(db.session.get(Setting, f'tenant:{target.id}:workflow_step_types_json').value)
    assert target_types[:2] == shared_types
    assert 'PRIVATE LEGACY' not in json.dumps(target_types)
    assert next(row for row in target_types if row['code'] == copy.step_type)['label'] == 'Shared triage'


def test_catalog_custom_types_respect_explicit_local_override_including_empty(catalog_db):
    from app.models import db, Setting
    from app.tenant_defaults import ensure_defaults_tenant
    from app.workflow_catalog import _effective_step_types_json
    _, source, _ = catalog_db
    shared = ensure_defaults_tenant()
    db.session.add(Setting(key=f'tenant:{shared.id}:workflow_step_types_json', value='[{"code":"shared","label":"Shared"}]'))
    local = Setting(key=f'tenant:{source.id}:workflow_step_types_json', value='[{"code":"local","label":"Local"}]')
    db.session.add(local)
    db.session.commit()
    assert json.loads(_effective_step_types_json(source.id))[0]['code'] == 'local'
    local.value = ''
    db.session.commit()
    assert _effective_step_types_json(source.id) == ''


def test_catalog_special_tenant_does_not_inherit_legacy_custom_types(catalog_db):
    from app.models import db, Setting, ConfigLabel, IncidentWorkflowStep
    from app.tenant_defaults import ensure_defaults_tenant
    from app.workflow_catalog import _effective_step_types_json, build_catalog_workflow_payload
    shared = ensure_defaults_tenant()
    db.session.add(Setting(key='workflow_step_types_json', value=json.dumps([
        {'code': 'private_legacy', 'label': 'Private legacy type', 'description': 'Private'}])))
    action = ConfigLabel(tenant_id=shared.id, kind='action_label', value='Draft action')
    db.session.add(action)
    db.session.flush()
    db.session.add(IncidentWorkflowStep(tenant_id=shared.id, action_label_id=action.id, step_type='private_legacy'))
    db.session.commit()
    assert _effective_step_types_json(shared.id) == ''
    with pytest.raises(ValueError, match='non incluso'):
        build_catalog_workflow_payload(shared.id)


@pytest.mark.parametrize('reference', ['triage_form', 'triage_form.pdf'])
def test_catalog_export_cannot_read_a_foreign_private_pdf(catalog_db, reference):
    from pathlib import Path
    from app.models import db, FormTemplateConfig, FormTemplateBinary
    from app.workflow_catalog import build_catalog_workflow_payload
    app, source, target = catalog_db
    labels, step = _source_workflow(source)
    config = FormTemplateConfig.query.filter_by(template_name='triage_form').one()
    config.owner_tenant_id = target.id
    step.document_template_name = reference
    binary = FormTemplateBinary.query.filter_by(template_name='triage_form').one()
    (Path(app.config['FORM_TEMPLATE_DIR']) / 'triage_form.pdf').write_bytes(binary.pdf_data)
    db.session.commit()
    with pytest.raises(ValueError, match='privato di un altro tenant'):
        build_catalog_workflow_payload(source.id, labels['category'].id)


def test_catalog_export_may_read_a_shared_defaults_pdf(catalog_db):
    from app.models import db, FormTemplateConfig
    from app.tenant_defaults import ensure_defaults_tenant
    from app.workflow_catalog import build_catalog_workflow_payload
    _, source, _ = catalog_db
    labels, _ = _source_workflow(source)
    shared = ensure_defaults_tenant()
    config = FormTemplateConfig.query.filter_by(template_name='triage_form').one()
    config.owner_tenant_id = shared.id
    db.session.commit()
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    assert payload['dependencies']['form_templates'][0]['template_name'] == 'triage_form'


def test_catalog_export_shared_pdf_remaps_notification_tags_by_provenance(catalog_db):
    from app.models import db, FormTemplateConfig, NotificationType
    from app.tenant_defaults import ensure_defaults_tenant
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    from app.workflow_catalog import build_catalog_workflow_payload
    _, source, _ = catalog_db
    labels, step = _source_workflow(source)
    shared = ensure_defaults_tenant()
    origin_type = NotificationType(tenant_id=shared.id, code='notice', label='Shared notice')
    copied_type = NotificationType(tenant_id=source.id, code='notice_td', label='Published shared notice')
    db.session.add_all([origin_type, copied_type])
    db.session.flush()
    origin = TenantDefaultSource(source_type='notification_type', source_id=origin_type.id)
    db.session.add(origin)
    db.session.flush()
    db.session.add(TenantDefaultReplica(source_id=origin.id, tenant_id=source.id,
        local_type='notification_type', local_id=copied_type.id, snapshot_json='{}'))
    config = FormTemplateConfig.query.filter_by(template_name='triage_form').one()
    config.owner_tenant_id = shared.id
    # The PDF is the only notification dependency. The unrelated same-code
    # local type and its private notification template must not be exported.
    step.requires_notification = False
    step.required_notification_type = None
    db.session.commit()
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    assert payload['dependencies']['form_templates'][0]['notification_tags'] == ['notice_td']
    assert [row['code'] for row in payload['dependencies']['notification_types']] == ['notice_td']
    assert payload['dependencies']['notification_templates'] == []


def test_catalog_address_sources_match_ui_and_keep_legacy_manual_compatibility():
    from app.routes import notification_template_address_sources
    from app.workflow_catalog import NOTIFICATION_ADDRESS_SOURCES
    assert NOTIFICATION_ADDRESS_SOURCES == {code for code, _ in notification_template_address_sources()} | {'manual'}


@pytest.mark.parametrize('source_code', ['type_default', 'incident_recipient_email',
                                      'incident_creator_email', 'fixed', 'empty', 'manual'])
def test_catalog_preserves_all_notification_address_configuration(catalog_db, source_code):
    from app.models import db, NotificationTemplate, IncidentWorkflowStep
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    _, source, target = catalog_db
    labels, _ = _source_workflow(source)
    original = NotificationTemplate.query.filter_by(tenant_id=source.id, kind='notice').one()
    original.recipient_source = source_code
    original.cc_source = source_code
    original.cc_editable = False
    original.cc_external_allowed = False
    db.session.commit()
    fields = ('recipient_source', 'recipient_value', 'recipient_editable', 'recipient_external_allowed',
              'cc_source', 'cc_value', 'cc_editable', 'cc_external_allowed')
    expected = {field: getattr(original, field) for field in fields}
    payload = build_catalog_workflow_payload(source.id, labels['category'].id)
    exported = payload['dependencies']['notification_templates'][0]
    assert {field: exported[field] for field in fields} == expected
    entry = save_catalog_workflow(payload, 'Address behavior')
    result = import_catalog_workflow(entry.id, target.id)
    db.session.commit()
    step = db.session.get(IncidentWorkflowStep, result['step_ids'][0])
    installed = NotificationTemplate.query.filter_by(tenant_id=target.id, kind=step.required_notification_type).one()
    assert {field: getattr(installed, field) for field in fields} == expected
