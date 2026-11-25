"""RC79: tenant notification type deletion with inherited types and legacy *_td aliases.

Runs against the real synchronization and deletion function bodies extracted
from the application, using transactional SQLite models without requiring Flask.
The registered Flask routes and actor permission checks run in full CI.
"""
import ast
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from test_rc78_notification_sqlalchemy_isolated import _mini_backend

ROOT = Path(__file__).resolve().parents[1]


def _backend():
    b = _mini_backend()
    s = b.session
    env = b.env
    # Maintain the real publication order: type before its templates.
    def sync_all(session):
        for row in session.scalars(select(b.NotificationType).where(b.NotificationType.tenant_id == 1)):
            source = session.scalar(select(env['TenantDefaultSource']).where(
                env['TenantDefaultSource'].source_type == 'notification_type',
                env['TenantDefaultSource'].source_id == row.id))
            b.sync(source, row, 2)
        for row in session.scalars(select(b.NotificationTemplate).where(b.NotificationTemplate.tenant_id == 1)):
            source = session.scalar(select(env['TenantDefaultSource']).where(
                env['TenantDefaultSource'].source_type == 'notification_template',
                env['TenantDefaultSource'].source_id == row.id))
            b.sync(source, row, 2)
    env['sync_defaults_configuration'] = sync_all
    env['configuration_reference_reason'] = lambda *args: ''
    return b


def _publish(b, code='risk', name='Alert'):
    s = b.session
    origin_type = b.NotificationType(tenant_id=1, code=code, label='Shared risk')
    origin_template = b.NotificationTemplate(
        tenant_id=1, kind=code, name=name, subject='Original shared message', is_default=True)
    type_source = b.publish('notification_type', origin_type)
    template_source = b.publish('notification_template', origin_template)
    return origin_type, origin_template, type_source, template_source


def test_deletion_cascades_templates_then_reinstates_shared_definition_immediately():
    b = _backend()
    typ, template, source, template_source = _publish(b)
    b.sync(source, typ, 2)
    b.sync(template_source, template, 2)
    local_type_id = b.replica(source, 2)[1].id
    local_template_id = b.replica(template_source, 2)[1].id
    result = b.env['delete_notification_type_and_templates'](b.session, 2, local_type_id)
    assert result == {'deleted_code': 'risk', 'templates_deleted': 1, 'restored_code': 'risk'}
    restored_type = b.replica(source, 2)[1]
    restored_template = b.replica(template_source, 2)[1]
    assert restored_type.code == restored_template.kind == 'risk'
    assert restored_type.label == 'Shared risk'
    assert restored_template.subject == 'Original shared message'
    assert b.session.scalars(select(b.NotificationType).where(b.NotificationType.tenant_id == 2)).all() == [restored_type]
    assert b.session.scalars(select(b.NotificationTemplate).where(b.NotificationTemplate.tenant_id == 2)).all() == [restored_template]
    assert b.session.scalar(select(b.NotificationType).where(b.NotificationType.tenant_id == 1)) is typ
    b.session.close()


def test_deleting_old_suffix_rebinds_references_and_adopts_tenant_override():
    b = _backend()
    s = b.session
    typ, template, source, template_source = _publish(b, code='security')
    # Old installations created a suffixed replica even when the tenant
    # already owned an unsuffixed custom type.
    owned_type = b.NotificationType(tenant_id=2, code='security', label='Local custom definition')
    alias = b.NotificationType(tenant_id=2, code='security_td', label='Legacy duplicate')
    old_template = b.NotificationTemplate(tenant_id=2, kind='security_td', name='Alert', subject='Old alias')
    local_template = b.NotificationTemplate(tenant_id=2, kind='security', name='Alert',
                                             subject='Custom tenant template')
    s.add_all([owned_type, alias, old_template, local_template])
    s.flush()
    s.add(b.env['TenantDefaultReplica'](
        source_id=source.id, tenant_id=2, local_type='notification_type', local_id=alias.id,
        snapshot_json=json.dumps(b.env['configuration_record_payload']('notification_type', alias))))
    s.add(b.env['TenantDefaultReplica'](
        source_id=template_source.id, tenant_id=2, local_type='notification_template',
        local_id=old_template.id,
        snapshot_json=json.dumps(b.env['configuration_record_payload']('notification_template', old_template))))
    incident = b.Incident(tenant_id=2)
    s.add(incident)
    s.flush()
    document = b.Document(incident_id=incident.id, notification_tags='security_td,csirt')
    step = b.IncidentWorkflowStep(tenant_id=2, required_notification_type='security_td')
    state = b.DeadlineNotificationState(incident_id=incident.id, notification_type='security_td')
    form = b.FormTemplateConfig(owner_tenant_id=2, notification_tags='security_td,user')
    setting = b.Setting(key='tenant:2:button_action_config', value=json.dumps({
        'rules': [{'notification_tags': ['security_td', 'csirt']}]}))
    other_setting = b.Setting(key='tenant:3:button_action_config', value=json.dumps({
        'rules': [{'notification_tags': ['security_td']}]}))
    s.add_all([document, step, state, form, setting, other_setting])
    s.flush()
    result = b.env['delete_notification_type_and_templates'](s, 2, alias.id)
    assert result['restored_code'] == 'security'
    assert result['templates_deleted'] == 1
    assert s.get(b.NotificationType, alias.id) is None
    assert b.replica(source, 2)[1].id == owned_type.id
    assert owned_type.label == 'Local custom definition'
    assert document.notification_tags == 'security,csirt'
    assert step.required_notification_type == 'security'
    assert state.notification_type == 'security'
    assert form.notification_tags == 'security,user'
    assert json.loads(setting.value)['rules'][0]['notification_tags'] == ['security', 'csirt']
    assert json.loads(other_setting.value)['rules'][0]['notification_tags'] == ['security_td']
    assert b.replica(template_source, 2)[1].kind == 'security'
    assert b.replica(template_source, 2)[1].id == local_template.id
    assert local_template.subject == 'Custom tenant template'
    assert not s.scalars(select(b.NotificationTemplate).where(b.NotificationTemplate.kind == 'security_td')).all()
    s.close()


def test_purely_local_type_deletes_with_its_templates_and_no_reseeding():
    b = _backend()
    s = b.session
    local = b.NotificationType(tenant_id=2, code='custom', label='Local')
    own_template = b.NotificationTemplate(tenant_id=2, kind='custom', name='Own', subject='Local')
    foreign = b.NotificationTemplate(tenant_id=3, kind='custom', name='Other', subject='Keep')
    s.add_all([local, own_template, foreign])
    s.flush()
    result = b.env['delete_notification_type_and_templates'](s, 2, local.id)
    assert result == {'deleted_code': 'custom', 'templates_deleted': 1, 'restored_code': None}
    assert s.get(b.NotificationType, local.id) is None
    assert s.get(b.NotificationTemplate, own_template.id) is None
    assert s.get(b.NotificationTemplate, foreign.id) is foreign
    s.close()


def test_refuses_wrong_tenant_and_source_contract_and_is_rollback_safe():
    b = _backend()
    s = b.session
    local = b.NotificationType(tenant_id=3, code='another', label='Other tenant')
    s.add(local)
    s.flush()
    with pytest.raises(ValueError, match='tenant attivo'):
        b.env['delete_notification_type_and_templates'](s, 2, local.id)
    assert s.get(b.NotificationType, local.id) is local
    s.rollback()
    s.close()


def test_route_requires_admin_and_does_not_hide_delete_for_builtin_or_inherited():
    routes = (ROOT / 'app/routes.py').read_text(encoding='utf-8')
    template = (ROOT / 'app/templates/notification_types.html').read_text(encoding='utf-8')
    body = ast.parse(routes)
    f = next(n for n in body.body if isinstance(n, ast.FunctionDef) and n.name == 'notification_types')
    source = ast.unparse(f)
    assert 'if not can_admin()' in source
    assert 'writable_notification_type_or_404(type_id)' in source
    assert 'delete_notification_type_and_templates' in source
    assert 'db.session.rollback()' in source
    assert 'db.session.commit()' in source
    assert 't.code in [' not in template.split('data-cir-confirm="Cancellare il tipo e tutti i suoi template?')[1]
    assert 'Se presente in Tenants Default' in template


def test_failure_during_reinstantiation_rolls_back_entire_cascade():
    b = _backend()
    s = b.session
    typ, template, source, template_source = _publish(b)
    b.sync(source, typ, 2)
    b.sync(template_source, template, 2)
    s.commit()
    local = b.replica(source, 2)[1]
    local_template = b.replica(template_source, 2)[1]
    b.env['sync_defaults_configuration'] = lambda session: (_ for _ in ()).throw(RuntimeError('sync failed'))
    with pytest.raises(RuntimeError, match='sync failed'):
        b.env['delete_notification_type_and_templates'](s, 2, local.id)
    s.rollback()
    assert s.get(b.NotificationType, local.id).code == 'risk'
    assert s.get(b.NotificationTemplate, local_template.id).subject == 'Original shared message'
    s.close()


def test_old_alias_without_replica_requires_actual_shared_origin():
    b = _backend()
    s = b.session
    typ, template, source, template_source = _publish(b, code='security')
    alias = b.NotificationType(tenant_id=2, code='security_td2', label='legacy untracked')
    s.add(alias)
    s.flush()
    found = b.env['_notification_type_replacement'](s, alias, 2, s.get(b.Tenant, 1))
    assert found.id == typ.id
    not_shared = b.NotificationType(tenant_id=2, code='user_td', label='independent')
    s.add(not_shared)
    s.flush()
    assert b.env['_notification_type_replacement'](s, not_shared, 2, s.get(b.Tenant, 1)) is None
    s.close()
