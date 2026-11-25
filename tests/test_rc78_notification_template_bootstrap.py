"""Ensure deleting notification templates does not trigger legacy auto-creation.

Execute CIR's actual function against isolated SQLAlchemy tables so this
regression runs even in build environments without the Flask UI package.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Boolean, Column, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def backend():
    base = declarative_base()

    class NotificationTemplate(base):
        __tablename__ = 'notification_template'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)
        kind = Column(String, nullable=False)
        name = Column(String, nullable=False)
        subject = Column(String, default='')
        body = Column(Text, default='')
        action_label_id = Column(Integer)
        recipient_source = Column(String, default='empty')
        recipient_editable = Column(Boolean, default=True)
        recipient_external_allowed = Column(Boolean, default=True)
        cc_source = Column(String, default='empty')
        cc_editable = Column(Boolean, default=True)
        cc_external_allowed = Column(Boolean, default=True)
        is_default = Column(Boolean, default=False)
        __table_args__=(UniqueConstraint('tenant_id','kind','name'),)

    class NotificationType(base):
        __tablename__ = 'notification_type'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)
        code = Column(String, nullable=False)

    class ConfigLabel(base):
        __tablename__ = 'config_label'
        id = Column(Integer, primary_key=True)
        kind = Column(String)
        value = Column(String)

    engine = create_engine('sqlite:///:memory:')
    base.metadata.create_all(engine)
    session=sessionmaker(bind=engine)()
    for tid in [10,20]:
        for code in ['user','csirt','dpo']:
            session.add(NotificationType(tenant_id=tid, code=code))
    session.commit()
    state=SimpleNamespace(tenant=10, values={})

    def template_query(kind=None):
        q=session.query(NotificationTemplate).filter(NotificationTemplate.tenant_id==state.tenant)
        return q.filter(NotificationTemplate.kind==kind) if kind else q
    def type_query():
        return session.query(NotificationType).filter(NotificationType.tenant_id==state.tenant)

    defaults = {'user':'Default user', 'csirt':'Default CSIRT', 'dpo':'Default DPO'}
    env={
        'current_tenant_id': lambda: state.tenant,
        'current_tenant_notification_template_query': template_query,
        'current_tenant_notification_type_query': type_query,
        'setting_value': lambda key, default='': state.values.get((state.tenant,key),default),
        'set_setting_value': lambda key, val: state.values.__setitem__((state.tenant,key),val),
        'tenant_query': lambda model: session.query(model),
        'ConfigLabel': ConfigLabel,
        'notification_label_value': lambda kind: 'notice:' + kind,
        'NotificationTemplate': NotificationTemplate,
        'DEFAULT_TEMPLATE_NAMES': defaults,
        'DEFAULT_NOTIFICATION_SUBJECTS': {key: 'Subject '+key for key in defaults},
        'DEFAULT_NOTIFICATION_BODIES': {key: 'Body '+key for key in defaults},
        'db': SimpleNamespace(session=session),
        'IntegrityError': IntegrityError,'ProgrammingError': ProgrammingError,'OperationalError': OperationalError,
        'current_app': SimpleNamespace(logger=SimpleNamespace(info=lambda *a,**k:None,exception=lambda *a,**k:None)),
    }
    tree=ast.parse((ROOT/'app/routes.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='ensure_default_notification_templates')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'app/routes.py','exec'),env)

    def ensure():
        env['ensure_default_notification_templates']()
        session.commit()

    yield SimpleNamespace(state=state, ensure=ensure, q=template_query, session=session,
                          Template=NotificationTemplate, defaults=defaults)
    session.close();engine.dispose()


def test_initial_bootstrap_creates_only_one_example_per_type(backend):
    b=backend
    b.ensure()
    assert {row.kind for row in b.q().all()} == {'user','csirt','dpo'}
    assert all(row.is_default for row in b.q().all())
    b.ensure()
    assert b.q().count() == 3


def test_deleting_one_or_all_examples_does_not_reseed(backend):
    b=backend
    b.ensure()
    t=b.q('user').one()
    b.session.delete(t);b.session.commit()
    b.ensure()
    assert b.q('user').count() == 0
    for row in b.q().all(): b.session.delete(row)
    b.session.commit()
    b.ensure()
    assert b.q().count() == 0


def test_existing_tenant_template_is_preserved_without_new_examples(backend):
    b=backend
    local=b.Template(tenant_id=10,kind='user',name='Modified locally',subject='Tenant version',is_default=False)
    b.session.add(local);b.session.commit()
    b.ensure()
    assert b.q().count()==1
    assert b.q('user').one().name=='Modified locally'
    assert b.q('user').one().is_default is True
    assert b.state.values[(10,'notification_templates_bootstrapped_v2')]=='1'


def test_bootstrap_state_is_scoped_by_tenant(backend):
    b=backend
    b.ensure();b.state.tenant=20
    b.ensure()
    assert b.q().count()==3
    b.state.tenant=10
    assert b.q().count()==3
    b.session.delete(b.q('csirt').one());b.session.commit();b.ensure()
    assert b.q().count()==2
    b.state.tenant=20
    assert b.q().count()==3
