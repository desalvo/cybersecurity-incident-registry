"""Canonical Defaults references, independent copies and workflow retirement."""
import copy
import json
import uuid

import pytest


@pytest.fixture
def lifecycle_db(tmp_path):
    from flask import Flask
    from app.models import db, Tenant
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///' + str(tmp_path / 'workflow-lifecycle.db'),
                      SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      FORM_TEMPLATE_DIR=str(tmp_path / 'forms'))
    (tmp_path / 'forms').mkdir()
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.info['cir_defaults_suspended'] = True
        source = Tenant(name='Tenants Default', is_system_defaults=True)
        target = Tenant(name='default', is_system_defaults=False)
        other = Tenant(name='other', is_system_defaults=False)
        db.session.add_all([source, target, other])
        db.session.commit()
        yield source, target, other
        db.session.remove()
        db.engine.dispose()


def _published_workflow(source, target):
    from app.models import db, ConfigLabel, IncidentWorkflowStep, NotificationType, NotificationTemplate
    from app.tenant_defaults import sync_defaults_configuration
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow
    from app.workflow_lifecycle import ensure_workflow_state
    source_labels, unrelated = {}, {}
    for kind in ('action_label', 'severity', 'data_type', 'category'):
        local = ConfigLabel(tenant_id=target.id, kind=kind, value='Same ' + kind,
                            description='UNCHANGED LOCAL VALUE')
        origin = ConfigLabel(tenant_id=source.id, kind=kind, value=local.value,
                             description='SOURCE ' + kind)
        db.session.add_all([local, origin])
        source_labels[kind], unrelated[kind] = origin, local
    db.session.flush()
    db.session.add(NotificationType(tenant_id=source.id, code='notice', label='Shared notice'))
    db.session.add(NotificationType(tenant_id=target.id, code='notice', label='UNCHANGED LOCAL TYPE'))
    db.session.add(NotificationTemplate(tenant_id=source.id, kind='notice', name='Shared template',
        action_label_id=source_labels['action_label'].id, subject='Subject', body='Body',
        recipient_source='fixed', recipient_value='team@example.test', is_default=True))
    step = IncidentWorkflowStep(tenant_id=source.id, category_id=source_labels['category'].id,
        action_label_id=source_labels['action_label'].id, position=10, description='Source step',
        requires_notification=True, required_notification_type='notice')
    step.set_condition_tokens([f"severity:{source_labels['severity'].id}",
                               f"!data_type:{source_labels['data_type'].id}"])
    db.session.add(step)
    db.session.flush()
    sync_defaults_configuration()
    state = ensure_workflow_state(source.id, step.category_id)
    payload = build_catalog_workflow_payload(source.id, step.category_id)
    entry = save_catalog_workflow(payload, 'Published response')
    entry.source_scope_key = state.scope_key
    db.session.commit()
    return entry, source_labels, unrelated


def test_defaults_workflow_uses_exact_replica_ids_after_numeric_and_name_collisions(lifecycle_db):
    from app.models import db, ConfigLabel, IncidentWorkflowStep, NotificationTemplate
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    from app.workflow_catalog import import_catalog_workflow, save_catalog_workflow
    source, target, _ = lifecycle_db
    entry, source_labels, unrelated = _published_workflow(source, target)
    payload = json.loads(entry.payload_json)
    # Simulate the numeric reference names from an external instance colliding
    # with already occupied destination IDs. UUID provenance is authoritative.
    rewrites = {}
    for label in payload['dependencies']['labels']:
        rewrites[label['ref']] = 'label_' + str(unrelated[label['kind']].id)
        label['ref'] = rewrites[label['ref']]
    payload['workflow']['category_ref'] = rewrites[payload['workflow']['category_ref']]
    for step in payload['workflow']['steps']:
        step['action_label_ref'] = rewrites[step['action_label_ref']]
        for condition in step['conditions']:
            condition['label_ref'] = rewrites[condition['label_ref']]
    for template in payload['dependencies']['notification_templates']:
        template['action_label_ref'] = rewrites[template['action_label_ref']]
    save_catalog_workflow(payload, entry.name, entry_id=entry.id)
    replicas = {}
    for kind, row in source_labels.items():
        origin = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=row.id).one()
        replica = TenantDefaultReplica.query.filter_by(source_id=origin.id, tenant_id=target.id).one()
        replicas[kind] = db.session.get(ConfigLabel, replica.local_id)
        if kind in ('category', 'data_type'):
            # RC65: category and affected-data labels with equivalent names
            # keep the tenant's existing IDs; no duplicate picker choices.
            # Other dependencies retain independent provenance-mapped IDs.
            assert replica.local_id == unrelated[kind].id
            assert json.loads(replica.snapshot_json)['__cir_existing_tenant_category'] is True
        else:
            assert replica.local_id not in {row.id, unrelated[kind].id}
    assert ConfigLabel.query.filter_by(tenant_id=target.id, kind='category').count() == 1
    assert ConfigLabel.query.filter_by(tenant_id=target.id, kind='data_type').count() == 1
    installed = import_catalog_workflow(entry.id, target.id, copy_name='First response')
    step = db.session.get(IncidentWorkflowStep, installed['step_ids'][0])
    assert step.action_label_id == replicas['action_label'].id
    assert step.condition_tokens() == [f"severity:{replicas['severity'].id}",
                                       f"!data_type:{replicas['data_type'].id}"]
    assert step.required_notification_type != 'notice'
    template = NotificationTemplate.query.filter_by(tenant_id=target.id, kind=step.required_notification_type).one()
    assert template.action_label_id == replicas['action_label'].id
    assert step.category_id not in {replicas['category'].id, unrelated['category'].id}
    assert all(row.description == 'UNCHANGED LOCAL VALUE' for row in unrelated.values())
    assert ConfigLabel.query.filter_by(tenant_id=target.id, kind='action_label').count() == 2


def test_repeated_named_copies_detach_parameters_without_changing_siblings_or_source(lifecycle_db):
    from app.models import db, ConfigLabel, IncidentWorkflowStep, NotificationTemplate
    from app.workflow_catalog import import_catalog_workflow, personalize_workflow_parameters
    from app.workflow_catalog_models import TenantWorkflow
    source, target, _ = lifecycle_db
    entry, source_labels, _ = _published_workflow(source, target)
    first = import_catalog_workflow(entry.id, target.id, copy_name='Response A')
    second = import_catalog_workflow(entry.id, target.id, copy_name='Response B')
    first_step = db.session.get(IncidentWorkflowStep, first['step_ids'][0])
    second_step = db.session.get(IncidentWorkflowStep, second['step_ids'][0])
    assert first['workflow_id'] != second['workflow_id']
    assert first['category_id'] != second['category_id']
    assert first_step.action_label_id == second_step.action_label_id
    canonical_action = second_step.action_label_id
    canonical_conditions = second_step.conditions
    snapshot = entry.payload_json
    personalize_workflow_parameters(first['workflow_id'])
    assert first_step.action_label_id != canonical_action
    assert first_step.required_notification_type != second_step.required_notification_type
    assert first_step.conditions != canonical_conditions
    db.session.get(ConfigLabel, first_step.action_label_id).description = 'ONLY RESPONSE A'
    first_step.description = 'Edited local step'
    first_template = NotificationTemplate.query.filter_by(tenant_id=target.id,
                                                         kind=first_step.required_notification_type).one()
    first_template.recipient_value = 'a-only@example.test'
    db.session.commit()
    assert second_step.action_label_id == canonical_action and second_step.conditions == canonical_conditions
    assert db.session.get(ConfigLabel, canonical_action).description == 'SOURCE action_label'
    assert source_labels['action_label'].description == 'SOURCE action_label'
    assert entry.payload_json == snapshot
    assert db.session.get(TenantWorkflow, first['workflow_id']).source_entry_id == entry.id
    assert db.session.get(TenantWorkflow, first['workflow_id']).personalized is True
    assert db.session.get(TenantWorkflow, second['workflow_id']).personalized is False


def test_obsolete_catalog_retires_all_modified_copies_and_notifies_every_admin(lifecycle_db):
    from app.models import db, User, UserTenantRole, IncidentWorkflowStep
    from app.workflow_catalog import import_catalog_workflow, personalize_workflow_parameters
    from app.workflow_catalog_models import TenantWorkflow, WorkflowObsolescenceNotice
    from app.workflow_lifecycle import set_catalog_workflow_status, set_workflow_status
    source, target, other = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    admin_a = User(username='manager-a', role='disabled', tenant_id=target.id, auth_provider='local')
    admin_b = User(username='manager-b', role='disabled', tenant_id=other.id, auth_provider='local')
    superuser = User(username='root-user', role='superuser', tenant_id=other.id, auth_provider='local')
    reader = User(username='reader', role='reader', tenant_id=target.id, auth_provider='local')
    db.session.add_all([admin_a, admin_b, superuser, reader])
    db.session.flush()
    db.session.add_all([UserTenantRole(user_id=admin_a.id, tenant_id=target.id, role='admin'),
                        UserTenantRole(user_id=admin_b.id, tenant_id=other.id, role='admin')])
    first = import_catalog_workflow(entry.id, target.id, copy_name='A')
    second = import_catalog_workflow(entry.id, target.id, copy_name='B')
    personalize_workflow_parameters(first['workflow_id'])
    db.session.get(IncidentWorkflowStep, second['step_ids'][0]).description = 'Locally edited'
    set_catalog_workflow_status(entry.id, 'obsolete')
    db.session.commit()
    assert all(db.session.get(TenantWorkflow, result['workflow_id']).status == 'obsolete' for result in (first, second))
    assert {notice.user_id for notice in WorkflowObsolescenceNotice.query.all()} == {admin_a.id, admin_b.id, superuser.id}
    assert db.session.get(IncidentWorkflowStep, second['step_ids'][0]).description == 'Locally edited'
    with pytest.raises(ValueError, match='obsoleto'):
        import_catalog_workflow(entry.id, other.id)
    with pytest.raises(ValueError, match='riattivata'):
        set_workflow_status(target.id, first['category_id'], 'current')
    set_catalog_workflow_status(entry.id, 'obsolete')
    assert WorkflowObsolescenceNotice.query.count() == 3
    set_catalog_workflow_status(entry.id, 'current')
    assert db.session.get(TenantWorkflow, first['workflow_id']).status == 'obsolete'
    set_workflow_status(target.id, first['category_id'], 'current')
    assert db.session.get(TenantWorkflow, first['workflow_id']).status == 'current'
    assert db.session.get(TenantWorkflow, second['workflow_id']).status == 'obsolete'


def test_obsolete_local_workflow_blocks_new_assignment_but_existing_incident_runs(lifecycle_db):
    from app.models import db, Incident, ConfigLabel
    from app.routes import workflow_steps_for_incident
    from app.workflow_catalog import import_catalog_workflow, personalize_workflow_parameters
    from app.workflow_lifecycle import assert_workflow_assignable, set_workflow_status
    source, target, _ = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    result = import_catalog_workflow(entry.id, target.id)
    incident = Incident(tenant_id=target.id, name='Existing incident', reference='EXISTING')
    incident.categories = [db.session.get(ConfigLabel, result['category_id'])]
    incident.category_order = str(result['category_id'])
    # Meet the copied severity condition; the negated data condition remains true.
    from app.models import IncidentWorkflowStep
    step = db.session.get(IncidentWorkflowStep, result['step_ids'][0])
    incident.severity_id = int(step.condition_tokens()[0].split(':')[1])
    db.session.add(incident)
    db.session.flush()
    before = [row.id for row in workflow_steps_for_incident(incident)]
    with pytest.raises(ValueError, match='già usato'):
        personalize_workflow_parameters(result['workflow_id'])
    set_workflow_status(target.id, result['category_id'], 'obsolete')
    with pytest.raises(ValueError, match='obsoleto'):
        assert_workflow_assignable(target.id, [result['category_id']])
    with pytest.raises(ValueError, match='obsoleto'):
        assert_workflow_assignable(target.id, [result['category_id']], previous_category_ids=[])
    assert_workflow_assignable(target.id, [result['category_id']], previous_category_ids=[result['category_id']])
    assert before and [row.id for row in workflow_steps_for_incident(incident)] == before


def test_default_fallback_and_legacy_unscoped_category_follow_runtime(lifecycle_db):
    from app.models import db, ConfigLabel, IncidentWorkflowStep
    from app.workflow_lifecycle import ensure_workflow_state, set_workflow_status, assert_workflow_assignable, workflow_scope_for_categories
    _, target, other = lifecycle_db
    label = ConfigLabel(tenant_id=None, kind='category', value='Legacy category')
    action = ConfigLabel(tenant_id=target.id, kind='action_label', value='Legacy action')
    db.session.add_all([label, action])
    db.session.flush()
    db.session.add(IncidentWorkflowStep(tenant_id=None, category_id=label.id, action_label_id=action.id, position=1))
    db.session.flush()
    state = ensure_workflow_state(target.id, label.id)
    assert state.category_id == label.id
    assert workflow_scope_for_categories(target.id, [label.id]) == label.id
    with pytest.raises(ValueError, match='appartenente'):
        workflow_scope_for_categories(other.id, [label.id])
    set_workflow_status(target.id, None, 'obsolete')
    with pytest.raises(ValueError, match='obsoleto'):
        assert_workflow_assignable(target.id, [])
    assert_workflow_assignable(target.id, [label.id])


def test_source_draft_status_changes_linked_catalog_and_preserves_edited_step_identity(lifecycle_db):
    from app.models import db, IncidentWorkflowStep
    from app.workflow_catalog import import_catalog_workflow
    from app.workflow_lifecycle import set_workflow_status
    from app.workflow_catalog_models import TenantWorkflow
    source, target, _ = lifecycle_db
    entry, labels, _ = _published_workflow(source, target)
    result = import_catalog_workflow(entry.id, target.id)
    original_step = db.session.get(IncidentWorkflowStep, result['step_ids'][0])
    db.session.delete(original_step)
    db.session.add(IncidentWorkflowStep(tenant_id=target.id, category_id=result['category_id'],
        action_label_id=original_step.action_label_id, position=77, description='Replacement step'))
    db.session.flush()
    set_workflow_status(source.id, labels['category'].id, 'obsolete')
    assert entry.status == 'obsolete'
    assert db.session.get(TenantWorkflow, result['workflow_id']).status == 'obsolete'


@pytest.mark.parametrize('invalid', ['not-uuid', '', 12, [], None])
def test_catalog_rejects_malformed_public_origin(invalid, lifecycle_db):
    from app.workflow_catalog import validate_catalog_payload
    source, target, _ = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    payload = json.loads(entry.payload_json)
    payload['workflow']['catalog_source_public_id'] = invalid
    with pytest.raises(ValueError):
        validate_catalog_payload(payload)


def test_old_export_from_now_obsolete_catalog_cannot_bypass_assignment_gate(lifecycle_db):
    from app.workflow_catalog import import_catalog_workflow, build_catalog_workflow_payload
    from app.workflow_lifecycle import set_catalog_workflow_status, validate_portable_workflow_lifecycle
    source, target, _ = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    installed = import_catalog_workflow(entry.id, target.id)
    old_file = build_catalog_workflow_payload(target.id, installed['category_id'])
    assert old_file['workflow']['catalog_source_public_id'] == entry.public_id
    set_catalog_workflow_status(entry.id, 'obsolete')
    with pytest.raises(ValueError, match='sorgente'):
        validate_portable_workflow_lifecycle(old_file['workflow'])


def test_obsolescence_and_notices_roll_back_with_the_admin_transaction(lifecycle_db):
    from app.models import db, User
    from app.workflow_catalog_models import WorkflowCatalogEntry, WorkflowObsolescenceNotice, TenantWorkflow
    from app.workflow_catalog import import_catalog_workflow
    from app.workflow_lifecycle import set_catalog_workflow_status
    source, target, _ = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    db.session.add(User(username='admin', role='superuser', auth_provider='local', tenant_id=target.id))
    installed = import_catalog_workflow(entry.id, target.id)
    db.session.commit()
    entry_id, workflow_id = entry.id, installed['workflow_id']
    set_catalog_workflow_status(entry_id, 'obsolete')
    assert WorkflowObsolescenceNotice.query.count() == 1
    db.session.rollback()
    assert db.session.get(WorkflowCatalogEntry, entry_id).status == 'current'
    assert db.session.get(TenantWorkflow, workflow_id).status == 'current'
    assert WorkflowObsolescenceNotice.query.count() == 0


def test_legacy_cross_clone_maps_defaults_notifications_pdf_tags_and_origin(lifecycle_db):
    from app.models import (db, ConfigLabel, IncidentWorkflowStep, FormTemplateConfig,
                            FormTemplateBinary, NotificationTemplate, WorkflowCatalogEntry)
    from app.routes import clone_workflow_steps
    from app.workflow_lifecycle import get_workflow_state, set_workflow_status
    from app.tenant_defaults import sync_defaults_configuration
    source, target, _ = lifecycle_db
    entry, labels, _ = _published_workflow(source, target)
    source_step = IncidentWorkflowStep.query.filter_by(tenant_id=source.id, category_id=labels['category'].id).one()
    source_step.document_template_name = 'clone_required'
    source_step.document_generation_enabled = True
    for name in ('clone_required', 'clone_unrelated'):
        db.session.add(FormTemplateConfig(template_name=name, owner_tenant_id=source.id, notification_tags='notice'))
        db.session.add(FormTemplateBinary(template_name=name, filename=name + '.pdf',
                                         pdf_data=b'%PDF-1.4\n%%EOF\n'))
    NotificationTemplate.query.filter_by(tenant_id=source.id, kind='notice').one().linked_form_template_name = 'clone_required'
    destination = ConfigLabel(tenant_id=target.id, kind='category', value='Legacy destination')
    db.session.add(destination)
    db.session.flush()
    sync_defaults_configuration()
    # The source draft has not been explicitly published: its first direct
    # cross-tenant copy must establish a catalogue origin transactionally.
    db.session.delete(entry)
    db.session.commit()
    result = clone_workflow_steps(labels['category'].id, destination.id,
        source_tenant_id=source.id, destination_tenant_id=target.id)
    assert result['ok'] is True
    copied = IncidentWorkflowStep.query.filter_by(tenant_id=target.id, category_id=destination.id).one()
    assert copied.required_notification_type != 'notice'
    assert copied.document_template_name != 'clone_required'
    cfg = FormTemplateConfig.query.filter_by(template_name=copied.document_template_name).one()
    assert cfg.owner_tenant_id == target.id
    assert cfg.notification_tag_list == [copied.required_notification_type]
    assert FormTemplateConfig.query.filter_by(owner_tenant_id=target.id).count() == 1
    paired = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source.id,
                                                   source_scope_key=f"category:{labels['category'].id}").one()
    assert get_workflow_state(target.id, destination.id).source_entry_id == paired.id
    set_workflow_status(source.id, labels['category'].id, 'obsolete')
    assert get_workflow_state(target.id, destination.id).status == 'obsolete'


def test_backfill_does_not_attach_historical_receipt_to_recreated_scope(lifecycle_db):
    from datetime import timedelta
    from app.models import db, IncidentWorkflowStep
    from app.workflow_catalog import import_catalog_workflow
    from app.workflow_catalog_models import WorkflowCatalogInstallation, TenantWorkflow
    from app.workflow_lifecycle import backfill_workflow_states
    source, target, _ = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    installed = import_catalog_workflow(entry.id, target.id)
    state = db.session.get(TenantWorkflow, installed['workflow_id'])
    receipt = db.session.get(WorkflowCatalogInstallation, installed['installation_id'])
    receipt.workflow_id = None  # pre-RC18 receipt
    state.source_entry_id = None
    step = db.session.get(IncidentWorkflowStep, installed['step_ids'][0])
    step.created_at = receipt.created_at + timedelta(seconds=1)  # reused SQLite PK / recreated step
    db.session.flush()
    backfill_workflow_states(target.id)
    assert state.source_entry_id is None and receipt.workflow_id is None


def test_obsolescence_reaches_catalog_derivatives_exported_from_installed_copy(lifecycle_db):
    from app.models import db, TenantWorkflow
    from app.workflow_catalog import build_catalog_workflow_payload, import_catalog_workflow, save_catalog_workflow
    from app.workflow_lifecycle import set_catalog_workflow_status
    source, target, other = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    original_copy = import_catalog_workflow(entry.id, target.id)
    derivative = save_catalog_workflow(build_catalog_workflow_payload(target.id, original_copy['category_id']), 'Derived catalog')
    derivative_copy = import_catalog_workflow(derivative.id, other.id)
    set_catalog_workflow_status(entry.id, 'obsolete')
    assert derivative.status == 'obsolete'
    assert db.session.get(TenantWorkflow, derivative_copy['workflow_id']).status == 'obsolete'
    with pytest.raises(ValueError, match='sorgente originaria'):
        set_catalog_workflow_status(derivative.id, 'current')


def test_reactivating_obsolete_content_snapshot_preserves_receipt_hash(lifecycle_db):
    from app.workflow_catalog import import_catalog_workflow, save_catalog_workflow
    from app.workflow_lifecycle import set_catalog_workflow_status
    source, target, _ = lifecycle_db
    entry, _, _ = _published_workflow(source, target)
    payload = json.loads(entry.payload_json)
    payload['workflow']['status'] = 'obsolete'
    obsolete = save_catalog_workflow(payload, 'Obsolete imported snapshot')
    original_hash = obsolete.payload_hash
    assert obsolete.status == 'obsolete'
    set_catalog_workflow_status(obsolete.id, 'current')
    result = import_catalog_workflow(obsolete.id, target.id)
    assert result['created'] == 1 and obsolete.payload_hash == original_hash


def test_legacy_json_import_remaps_colliding_condition_ids_and_shared_notification_codes(lifecycle_db):
    from app.models import db, ConfigLabel, IncidentWorkflowStep, NotificationType
    from app.routes import build_workflow_export_payload, apply_workflow_import, tenant_execution_context, workflow_import_diff
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica
    source, target, _ = lifecycle_db
    _, labels, unrelated = _published_workflow(source, target)
    with tenant_execution_context(source.id):
        payload = build_workflow_export_payload(labels['category'].id)
    # The file's numeric source IDs collide with unrelated existing rows. Both
    # named and conditional references must resolve via shared UUID instead.
    for definition in payload['dependencies']['labels']:
        definition['source_id'] = unrelated[definition['kind']].id
    payload['workflow']['category']['source_id'] = unrelated['category'].id
    for step in payload['workflow']['steps']:
        step['action_label']['source_id'] = unrelated['action_label'].id
        step['conditions'] = [f"severity:{unrelated['severity'].id}", f"!data_type:{unrelated['data_type'].id}"]
    for template in payload['dependencies']['notification_templates']:
        template['action_label']['source_id'] = unrelated['action_label'].id
    with tenant_execution_context(target.id):
        result = apply_workflow_import(payload, overwrite_keys=[])
        assert result['created'] == 1
        assert workflow_import_diff(payload) == []
    replicas = {}
    for kind, original in labels.items():
        origin = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=original.id).one()
        replicas[kind] = TenantDefaultReplica.query.filter_by(source_id=origin.id, tenant_id=target.id).one().local_id
    copied = IncidentWorkflowStep.query.filter_by(tenant_id=target.id, category_id=replicas['category']).one()
    assert copied.action_label_id == replicas['action_label']
    assert copied.condition_tokens() == [f"severity:{replicas['severity']}", f"!data_type:{replicas['data_type']}"]
    assert copied.required_notification_type != 'notice'
    assert NotificationType.query.filter_by(tenant_id=target.id, code='notice').one().label == 'UNCHANGED LOCAL TYPE'
    assert all(db.session.get(ConfigLabel, row.id).description == 'UNCHANGED LOCAL VALUE' for row in unrelated.values())


def test_legacy_json_ambiguous_raw_condition_id_is_rejected_before_mutation(lifecycle_db):
    from app.models import ConfigLabel, IncidentWorkflowStep
    from app.routes import build_workflow_export_payload, apply_workflow_import, tenant_execution_context
    source, target, _ = lifecycle_db
    _, labels, _ = _published_workflow(source, target)
    with tenant_execution_context(source.id):
        payload = build_workflow_export_payload(labels['category'].id)
    for definition in payload['dependencies']['labels']:
        definition.pop('source_id', None)
        definition.pop('id', None)
    before = (ConfigLabel.query.count(), IncidentWorkflowStep.query.count())
    with tenant_execution_context(target.id), pytest.raises(ValueError, match='riesportare'):
        apply_workflow_import(payload, overwrite_keys=[])
    assert (ConfigLabel.query.count(), IncidentWorkflowStep.query.count()) == before


def test_historical_legacy_id_metadata_is_remapped_without_destination_id_lookup():
    from app.workflow_legacy_references import legacy_workflow_label_index, legacy_map_conditions
    payload = {'workflow': {'category': None, 'steps': [{'action_label': {'kind': 'action_label', 'value': 'Act'},
        'conditions': ['severity:7', '!data_type:8']}]}, 'dependencies': {'labels': [
            {'kind': 'action_label', 'value': 'Act', 'id': 4},
            {'kind': 'severity', 'value': 'Severe', 'id': 7},
            {'kind': 'data_type', 'value': 'Personal', 'id': 8}]}}
    index = legacy_workflow_label_index(payload)
    ids = {('severity', 'Severe'): 701, ('data_type', 'Personal'): 801}
    assert legacy_map_conditions(payload['workflow']['steps'][0]['conditions'], index,
        lambda row: ids[(row['kind'], row['value'])]) == ['severity:701', '!data_type:801']
