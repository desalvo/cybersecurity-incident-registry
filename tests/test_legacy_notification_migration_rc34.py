"""RC34: legacy notification normalization is narrow, idempotent and atomic."""
import pytest
from flask import Flask
from sqlalchemy import select
from app.models import db, Tenant, NotificationType, NotificationTemplate
from app.legacy_notification_migration import normalize_legacy_notification_kinds


@pytest.fixture
def session():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield db.session
        db.session.remove()
        db.drop_all()


def seed(session, *, canonical=True, custom=False, conflict=False, second=False):
    for tenant_id in ([1, 2] if second else [1]):
        session.add(Tenant(id=tenant_id, name=f'legacy-{tenant_id}'))
        if canonical:
            session.add(NotificationType(tenant_id=tenant_id, code='internal', label='Notifica interna'))
        if custom:
            session.add(NotificationType(tenant_id=tenant_id, code='notifica_interna', label='Custom'))
        session.add(NotificationTemplate(tenant_id=tenant_id, kind='notifica_interna',
                                         name=f'notifica interna Roma{tenant_id}',
                                         subject='original subject', body='original body'))
        if conflict:
            session.add(NotificationTemplate(tenant_id=tenant_id, kind='internal',
                                             name=f'notifica interna Roma{tenant_id}'))
    session.flush()


def test_normalizes_only_verified_alias_and_is_idempotent(session):
    seed(session, second=True)
    assert normalize_legacy_notification_kinds(session) == 2
    assert normalize_legacy_notification_kinds(session) == 0
    assert all(x.kind == 'internal' for x in session.scalars(select(NotificationTemplate)).all())
    assert all(x.body == 'original body' for x in session.scalars(select(NotificationTemplate).where(NotificationTemplate.body == 'original body')).all())


def test_custom_defined_legacy_type_is_preserved(session):
    seed(session, custom=True)
    assert normalize_legacy_notification_kinds(session) == 0
    assert session.scalar(select(NotificationTemplate)).kind == 'notifica_interna'


def test_unknown_target_fails_closed(session):
    seed(session, canonical=False)
    with pytest.raises(ValueError, match='manual review'):
        normalize_legacy_notification_kinds(session)
    assert session.scalar(select(NotificationTemplate)).kind == 'notifica_interna'


def test_unique_key_conflict_fails_closed(session):
    seed(session, conflict=True)
    with pytest.raises(ValueError, match='conflicts'):
        normalize_legacy_notification_kinds(session)


def test_rollback_restores_legacy_rows_after_later_failure(session):
    seed(session)
    session.commit()
    assert normalize_legacy_notification_kinds(session) == 1
    session.rollback()
    session.expire_all()
    assert session.scalar(select(NotificationTemplate)).kind == 'notifica_interna'
