"""Run actual Tenants Default inheritance logic against SQLite without Flask.

The module extracts the implementation's functions from app/tenant_defaults.py
and executes them with minimal mapped notification models. End-to-end Flask
coverage is separately provided by test_tenant_defaults_core.py in full CI.
"""
import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parents[1]


def _mini_backend():
    Base = declarative_base()

    class Tenant(Base):
        __tablename__ = 'tenant'
        id = Column(Integer, primary_key=True)
        is_system_defaults = Column(Boolean, nullable=False, default=False)

    class NotificationType(Base):
        __tablename__ = 'notification_type'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)
        code = Column(String(40), nullable=False)
        label = Column(String(160), nullable=False, default='')
        description = Column(Text, nullable=False, default='')
        enabled = Column(Boolean, nullable=False, default=True)
        __table_args__ = (UniqueConstraint('tenant_id', 'code'),)

    class NotificationTemplate(Base):
        __tablename__ = 'notification_template'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)
        kind = Column(String(40), nullable=False)
        name = Column(String(160), nullable=False)
        subject = Column(String(255), nullable=False, default='')
        body = Column(Text, nullable=False, default='')
        linked_form_template_name = Column(String(255))
        action_label_id = Column(Integer)
        recipient_source = Column(String(40), nullable=False, default='empty')
        recipient_value = Column(String(255), nullable=False, default='')
        recipient_editable = Column(Boolean, nullable=False, default=True)
        recipient_external_allowed = Column(Boolean, nullable=False, default=True)
        cc_source = Column(String(40), nullable=False, default='empty')
        cc_value = Column(String(255), nullable=False, default='')
        cc_editable = Column(Boolean, nullable=False, default=True)
        cc_external_allowed = Column(Boolean, nullable=False, default=True)
        is_default = Column(Boolean, nullable=False, default=False)
        __table_args__ = (UniqueConstraint('tenant_id', 'kind', 'name'),)

    class Setting(Base):
        __tablename__ = 'setting'
        key = Column(String(200), primary_key=True)
        value = Column(Text)

    class Incident(Base):
        __tablename__ = 'incident'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)

    class IncidentWorkflowStep(Base):
        __tablename__ = 'incident_workflow_step'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)
        required_notification_type = Column(String(40))

    class Document(Base):
        __tablename__ = 'document'
        id = Column(Integer, primary_key=True)
        incident_id = Column(Integer, ForeignKey('incident.id'), nullable=False)
        notification_tags = Column(Text, nullable=False, default='')

        @property
        def notification_tag_list(self):
            return [x.strip() for x in (self.notification_tags or '').split(',') if x.strip()]

        def set_notification_tags(self, values):
            self.notification_tags = ','.join(dict.fromkeys(values))

    class DeadlineNotificationState(Base):
        __tablename__ = 'deadline_notification_state'
        id = Column(Integer, primary_key=True)
        incident_id = Column(Integer, ForeignKey('incident.id'), nullable=False)
        notification_type = Column(String(80), nullable=False)

    class FormTemplateConfig(Base):
        __tablename__ = 'form_template_config'
        id = Column(Integer, primary_key=True)
        owner_tenant_id = Column(Integer)
        notification_tags = Column(Text, default='')

        @property
        def notification_tag_list(self):
            return [x.strip() for x in (self.notification_tags or '').split(',') if x.strip()]

        def set_notification_tags(self, values):
            self.notification_tags = ','.join(dict.fromkeys(values))

    class TenantDefaultSource(Base):
        __tablename__ = 'tenant_default_source'
        id = Column(String(36), primary_key=True)
        source_type = Column(String(40), nullable=False)
        source_id = Column(Integer, nullable=True)
        active = Column(Boolean, nullable=False, default=True)

    class TenantDefaultReplica(Base):
        __tablename__ = 'tenant_default_replica'
        id = Column(Integer, primary_key=True)
        source_id = Column(String(36), ForeignKey('tenant_default_source.id'), nullable=False)
        tenant_id = Column(Integer, nullable=False)
        local_type = Column(String(40), nullable=False)
        local_id = Column(Integer, nullable=False)
        snapshot_json = Column(Text, nullable=False)
        __table_args__ = (UniqueConstraint('source_id', 'tenant_id'), UniqueConstraint('local_type', 'local_id'))

    class TenantDefaultAlert(Base):
        __tablename__ = 'tenant_default_alert'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)
        source_id = Column(String(36), nullable=False)
        kind = Column(String(40), nullable=False)
        local_type = Column(String(40), nullable=False)
        local_id = Column(Integer, nullable=False)
        message = Column(Text, nullable=False)

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    source = (ROOT / 'app/tenant_defaults.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    names = {
        '_category_equivalent', '_locally_owned_category_replica', '_locally_owned_notification_replica',
        '_notification_identity_matches', '_local_notification_snapshot', '_json',
        'configuration_record_payload', '_lock_defaults', '_referenced_local_id', '_replica_data',
        '_write_row', '_sync_source_to_tenant', '_alert', '_retire_source', '_tenant_notification_type_is_customized', '_available_data',
        '_legacy_notification_alias_base', '_notification_type_replacement',
        '_remap_notification_settings', 'delete_notification_type_and_templates',
    }
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for function in functions:
        if function.name == 'delete_notification_type_and_templates':
            function.body = [node for node in function.body if not (
                isinstance(node, ast.ImportFrom) and node.module == 'configuration_usage')]
    env = {
        'select': select, 'json': json, 're': re,
        'Tenant': Tenant, 'NotificationType': NotificationType, 'NotificationTemplate': NotificationTemplate,
        'TenantDefaultSource': TenantDefaultSource, 'TenantDefaultReplica': TenantDefaultReplica,
        'TenantDefaultAlert': TenantDefaultAlert, 'ConfigLabel': SimpleNamespace(),
        'Setting': Setting, 'Incident': Incident, 'Document': Document,
        'IncidentWorkflowStep': IncidentWorkflowStep,
        'DeadlineNotificationState': DeadlineNotificationState,
        'FormTemplateConfig': FormTemplateConfig,
        'configuration_incident_usage': lambda kind, row, session: '',
        '_LOCAL_CATEGORY_MARKER': '__cir_existing_tenant_category',
        '_LOCAL_NOTIFICATION_TYPE_MARKER': '__cir_existing_tenant_notification_type',
        '_LOCAL_NOTIFICATION_TEMPLATE_MARKER': '__cir_existing_tenant_notification_template',
        '_LOCAL_NOTIFICATION_MARKERS': {
            'notification_type': '__cir_existing_tenant_notification_type',
            'notification_template': '__cir_existing_tenant_notification_template',
        },
        '_MODELS': {'notification_type': NotificationType, 'notification_template': NotificationTemplate},
        '_FIELDS': {
            'notification_type': ('code', 'label', 'description', 'enabled'),
            'notification_template': ('kind', 'name', 'subject', 'body', 'linked_form_template_name',
                                      'action_label_id', 'recipient_source', 'recipient_value',
                                      'recipient_editable', 'recipient_external_allowed', 'cc_source',
                                      'cc_value', 'cc_editable', 'cc_external_allowed', 'is_default'),
        },
        '_ID_FIELDS': {'notification_template': {}}, '_CSV_FIELDS': {},
        'configuration_reference_reason': lambda *args: '',
        '_require_form_template': lambda *args: None,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                 '<CIR tenant defaults>', 'exec'), env)
    session.add_all([Tenant(id=1, is_system_defaults=True), Tenant(id=2, is_system_defaults=False),
                     Tenant(id=3, is_system_defaults=False)])
    session.commit()

    def publish(kind, row):
        session.add(row)
        session.flush()
        source = TenantDefaultSource(id=f'{kind}-{row.id}', source_type=kind, source_id=row.id)
        session.add(source)
        session.flush()
        return source

    def sync(source, row, tenant_id):
        env['_sync_source_to_tenant'](session, source, env['configuration_record_payload'](source.source_type, row), tenant_id)
        session.flush()

    def replica(source, tenant_id):
        match = session.scalar(select(TenantDefaultReplica).where(
            TenantDefaultReplica.source_id == source.id, TenantDefaultReplica.tenant_id == tenant_id))
        assert match is not None
        model = env['_MODELS'][source.source_type]
        return match, session.get(model, match.local_id)

    return SimpleNamespace(session=session, Tenant=Tenant, NotificationType=NotificationType,
                           NotificationTemplate=NotificationTemplate, Setting=Setting,
                           Incident=Incident, Document=Document,
                           IncidentWorkflowStep=IncidentWorkflowStep, DeadlineNotificationState=DeadlineNotificationState,
                           FormTemplateConfig=FormTemplateConfig, publish=publish, sync=sync,
                           replica=replica, env=env)


def test_tenant_existing_template_and_type_are_adopted_without_duplication():
    b = _mini_backend()
    s = b.session
    t = b.NotificationType(tenant_id=2, code='user', label='Tenant label')
    n = b.NotificationTemplate(tenant_id=2, kind='user', name='Welcome', subject='Tenant text', is_default=True)
    st = b.NotificationType(tenant_id=1, code='user', label='Shared label')
    sn = b.NotificationTemplate(tenant_id=1, kind='user', name='Welcome', subject='Shared text', is_default=True)
    s.add_all([t, n])
    s.flush()
    typ = b.publish('notification_type', st)
    templ = b.publish('notification_template', sn)
    b.sync(typ, st, 2)
    b.sync(templ, sn, 2)
    assert b.replica(typ, 2)[1].id == t.id
    assert b.replica(templ, 2)[1].id == n.id
    assert n.subject == 'Tenant text' and n.is_default
    sn.subject = 'New shared text'
    b.sync(templ, sn, 2)
    assert n.subject == 'Tenant text'
    assert s.scalars(select(b.NotificationTemplate).where(b.NotificationTemplate.tenant_id == 2)).all() == [n]
    s.delete(n)
    s.flush()
    b.sync(templ, sn, 2)
    _, restored = b.replica(templ, 2)
    assert restored.id != n.id and restored.name == 'Welcome'
    assert restored.subject == 'New shared text'
    assert s.scalars(select(b.NotificationTemplate).where(b.NotificationTemplate.tenant_id == 2)).all() == [restored]
    s.close()


def test_editing_an_inherited_template_is_an_override_not_a_second_copy():
    b = _mini_backend()
    s = b.session
    st = b.NotificationType(tenant_id=1, code='csirt', label='CSIRT')
    sn = b.NotificationTemplate(tenant_id=1, kind='csirt', name='Alert', subject='Standard')
    typ = b.publish('notification_type', st)
    templ = b.publish('notification_template', sn)
    b.sync(typ, st, 2)
    b.sync(templ, sn, 2)
    _, inherited = b.replica(templ, 2)
    first_id = inherited.id
    inherited.subject = 'Edited by tenant admin'
    s.flush()
    b.sync(templ, sn, 2)
    repl, original = b.replica(templ, 2)
    assert original.id == first_id and original.subject == 'Edited by tenant admin'
    assert b.env['_locally_owned_notification_replica'](repl)
    sn.subject = 'Changed globally'
    b.sync(templ, sn, 2)
    assert original.subject == 'Edited by tenant admin'
    b.sync(typ, st, 3)
    b.sync(templ, sn, 3)
    assert b.replica(templ, 3)[1].subject == 'Changed globally'
    s.delete(original)
    s.flush()
    b.sync(templ, sn, 2)
    assert b.replica(templ, 2)[1].subject == 'Changed globally'
    assert len(s.scalars(select(b.NotificationTemplate).where(b.NotificationTemplate.tenant_id == 2)).all()) == 1
    s.close()


def test_distinct_kinds_can_share_display_name_without_collision():
    b = _mini_backend()
    s = b.session
    st = b.NotificationType(tenant_id=1, code='dpo', label='DPO')
    sn = b.NotificationTemplate(tenant_id=1, kind='dpo', name='Report', subject='Default DPO')
    own = b.NotificationTemplate(tenant_id=2, kind='user', name='Report', subject='Custom user')
    s.add(own)
    typ = b.publish('notification_type', st)
    templ = b.publish('notification_template', sn)
    b.sync(typ, st, 2)
    b.sync(templ, sn, 2)
    assert b.replica(templ, 2)[1].name == 'Report'
    assert sorted(row.kind for row in s.scalars(select(b.NotificationTemplate).where(
        b.NotificationTemplate.tenant_id == 2)).all()) == ['dpo', 'user']
    s.close()


def test_depublishing_shared_source_keeps_an_adopted_tenant_override():
    b = _mini_backend()
    s = b.session
    st = b.NotificationType(tenant_id=1, code='csirt', label='CSIRT')
    own = b.NotificationType(tenant_id=2, code='csirt', label='Local CSIRT')
    s.add(own)
    typ = b.publish('notification_type', st)
    b.sync(typ, st, 2)
    b.env['_retire_source'](s, typ)
    s.flush()
    assert s.get(b.NotificationType, own.id) is own
    assert typ.active is False
    s.close()
