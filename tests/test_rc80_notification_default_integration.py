"""Full application regression: publish/retire shared notification types.

Runs in GitHub CI with Flask/Flask-SQLAlchemy; isolated SQLAlchemy coverage
is provided by test_rc80_notification_default_retirement.py.
"""
import pytest

pytest.importorskip('flask_sqlalchemy')
from flask import Flask


@pytest.fixture
def context(tmp_path):
    from app.models import db, Tenant
    from app.tenant_defaults import ensure_defaults_tenant, register_defaults_events

    app = Flask(__name__)
    app.config.update(
        TESTING=True, SECRET_KEY='rc80-inheritance-test',
        SQLALCHEMY_DATABASE_URI='sqlite:///' + str(tmp_path / 'rc80.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.info['cir_defaults_suspended'] = True
        defaults = ensure_defaults_tenant()
        lab1 = Tenant(name='Tutorial')
        lab2 = Tenant(name='Operations')
        db.session.add_all([lab1, lab2])
        db.session.commit()
        tenant_ids = (defaults.id, lab1.id, lab2.id)
        db.session.info.pop('cir_defaults_suspended', None)
        register_defaults_events()
        yield db, tenant_ids
        db.session.rollback()
        db.session.remove()


def _template_query(session, tenant_id):
    from sqlalchemy import select
    from app.models import NotificationTemplate
    return session.scalars(select(NotificationTemplate).where(
        NotificationTemplate.tenant_id == tenant_id,
        NotificationTemplate.kind == 'shared_security')).all()


def _type_query(session, tenant_id):
    from sqlalchemy import select
    from app.models import NotificationType
    return session.scalar(select(NotificationType).where(
        NotificationType.tenant_id == tenant_id,
        NotificationType.code == 'shared_security'))


def _create_shared(db, defaults_id):
    from app.models import NotificationType, NotificationTemplate
    shared_type = NotificationType(tenant_id=defaults_id, code='shared_security', label='Shared security')
    shared_template = NotificationTemplate(tenant_id=defaults_id, kind='shared_security', name='Notice',
                                           subject='Shared message', body='Shared body')
    db.session.add_all([shared_type, shared_template])
    db.session.commit()
    return shared_type.id, shared_template.id


def test_new_shared_type_propagates_to_existing_tenants_in_same_commit(context):
    db, (defaults, tutorial, operations) = context
    _create_shared(db, defaults)
    for tenant_id in (tutorial, operations):
        assert _type_query(db.session, tenant_id).label == 'Shared security'
        assert len(_template_query(db.session, tenant_id)) == 1


def test_removed_shared_type_keeps_tenant_customization_and_its_templates(context):
    db, (defaults, tutorial, operations) = context
    type_id, template_id = _create_shared(db, defaults)
    from app.models import NotificationType, NotificationTemplate
    tenant_type = _type_query(db.session, tutorial)
    tenant_template = _template_query(db.session, tutorial)[0]
    tenant_type.label = 'Tutorial-specific security'
    db.session.commit()
    db.session.delete(db.session.get(NotificationTemplate, template_id))
    db.session.delete(db.session.get(NotificationType, type_id))
    db.session.commit()
    assert _type_query(db.session, tutorial).label == 'Tutorial-specific security'
    assert _template_query(db.session, tutorial)[0].id == tenant_template.id
    assert _type_query(db.session, operations) is None
    assert _template_query(db.session, operations) == []


def test_template_override_keeps_type_even_without_tenant_type_edit(context):
    db, (defaults, tutorial, operations) = context
    type_id, template_id = _create_shared(db, defaults)
    from app.models import NotificationType, NotificationTemplate
    tenant_template = _template_query(db.session, tutorial)[0]
    tenant_template.subject = 'Custom Tutorial notice'
    db.session.commit()
    db.session.delete(db.session.get(NotificationTemplate, template_id))
    db.session.delete(db.session.get(NotificationType, type_id))
    db.session.commit()
    assert _type_query(db.session, tutorial) is not None
    assert _template_query(db.session, tutorial)[0].subject == 'Custom Tutorial notice'
    assert _type_query(db.session, operations) is None
