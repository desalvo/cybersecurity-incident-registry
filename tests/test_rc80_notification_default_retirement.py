"""RC80: shared notification publication and safe retirement of tenant overrides.

The isolated SQLite model executes the real tenant_defaults.py implementation
without requiring Flask. The full Flask listener/transaction integration is
covered by test_rc80_notification_default_http.py in the CI environment.
"""
from sqlalchemy import select
from test_rc78_notification_sqlalchemy_isolated import _mini_backend


def _new_published(b):
    st = b.NotificationType(tenant_id=1, code='security', label='Security from default')
    sn = b.NotificationTemplate(tenant_id=1, kind='security', name='Report',
                                subject='Original', body='Shared email', is_default=True)
    ts = b.publish('notification_type', st)
    ns = b.publish('notification_template', sn)
    for tid in (2, 3):
        b.sync(ts, st, tid)
        b.sync(ns, sn, tid)
    return st, sn, ts, ns


def _rows(b, model, tenant):
    return b.session.scalars(select(model).where(model.tenant_id == tenant)).all()


def _remove_defaults(b, type_source, template_source):
    # The production publisher retires higher-priority templates before types.
    b.env['_retire_source'](b.session, template_source)
    b.session.flush()
    b.env['_retire_source'](b.session, type_source)
    b.session.flush()


def test_new_shared_notification_type_and_templates_replicate_to_all_existing_tenants():
    b = _mini_backend()
    st, sn, ts, ns = _new_published(b)
    for tid in (2, 3):
        replica_t = b.replica(ts, tid)[1]
        replica_n = b.replica(ns, tid)[1]
        assert replica_t.code == replica_n.kind == 'security'
        assert replica_t.label == 'Security from default'
        assert replica_n.subject == 'Original'
        assert replica_t.id != st.id and replica_n.id != sn.id
    b.session.close()


def test_retiring_unused_unmodified_type_removes_type_and_its_templates_in_all_tenants():
    b = _mini_backend()
    _st, _sn, ts, ns = _new_published(b)
    _remove_defaults(b, ts, ns)
    for tid in (2, 3):
        assert _rows(b, b.NotificationType, tid) == []
        assert _rows(b, b.NotificationTemplate, tid) == []
    assert not ts.active and not ns.active
    b.session.close()


def test_edited_inherited_type_remains_with_its_templates_even_without_incidents():
    b = _mini_backend()
    st, _sn, ts, ns = _new_published(b)
    local_type = b.replica(ts, 2)[1]
    local_template = b.replica(ns, 2)[1]
    local_type.label = 'Security - customized by Tutorial admin'
    b.session.flush()
    # Simulate a later publication; the override must remain local.
    b.sync(ts, st, 2)
    assert b.env['_locally_owned_notification_replica'](b.replica(ts, 2)[0])
    _remove_defaults(b, ts, ns)
    assert b.session.get(b.NotificationType, local_type.id).label == 'Security - customized by Tutorial admin'
    assert b.session.get(b.NotificationTemplate, local_template.id).subject == 'Original'
    assert _rows(b, b.NotificationType, 3) == []
    assert _rows(b, b.NotificationTemplate, 3) == []
    assert all(r.tenant_id == 2 for r in _rows(b, b.NotificationType, 2))
    b.session.close()


def test_unsynced_last_moment_edit_is_preserved_when_source_is_removed():
    b = _mini_backend()
    _st, _sn, ts, ns = _new_published(b)
    local_type = b.replica(ts, 2)[1]
    local_type.description = 'Edited before deletion without an extra publication pass'
    b.session.flush()
    _remove_defaults(b, ts, ns)
    assert b.session.get(b.NotificationType, local_type.id).description.startswith('Edited before')
    assert len(_rows(b, b.NotificationTemplate, 2)) == 1
    b.session.close()


def test_tenant_owned_type_adopted_as_override_is_not_removed():
    b = _mini_backend()
    s = b.session
    local_type = b.NotificationType(tenant_id=2, code='security', label='Local before default')
    s.add(local_type)
    s.flush()
    st, sn, ts, ns = _new_published(b)
    # Re-publish for tenant 2 to adopt pre-existing canonical row.
    b.sync(ts, st, 2)
    assert b.replica(ts, 2)[1].id == local_type.id
    _remove_defaults(b, ts, ns)
    assert s.get(b.NotificationType, local_type.id).label == 'Local before default'
    assert len(_rows(b, b.NotificationTemplate, 2)) == 1
    b.session.close()


def test_customized_template_alone_keeps_parent_type_usable():
    b = _mini_backend()
    st, sn, ts, ns = _new_published(b)
    own_template = b.replica(ns, 2)[1]
    own_type = b.replica(ts, 2)[1]
    own_template.subject = 'Customized local subject'
    b.session.flush()
    b.sync(ns, sn, 2)
    _remove_defaults(b, ts, ns)
    assert b.session.get(b.NotificationTemplate, own_template.id).subject == 'Customized local subject'
    assert b.session.get(b.NotificationType, own_type.id).code == 'security'
    assert not _rows(b, b.NotificationType, 3)
    b.session.close()


def test_incident_usage_preserves_shared_type_and_template_when_retired():
    b = _mini_backend()
    _st, _sn, ts, ns = _new_published(b)
    keep_type = b.replica(ts, 2)[1]
    keep_template = b.replica(ns, 2)[1]
    b.env['configuration_reference_reason'] = (lambda kind, row, session:
        'incident notification history' if row.tenant_id == 2 else '')
    _remove_defaults(b, ts, ns)
    assert b.session.get(b.NotificationType, keep_type.id) is not None
    assert b.session.get(b.NotificationTemplate, keep_template.id) is not None
    assert _rows(b, b.NotificationType, 3) == []
    b.session.close()


def test_other_tenant_local_type_unaffected_by_shared_source_retirement():
    b = _mini_backend()
    _st, _sn, ts, ns = _new_published(b)
    s = b.session
    independent = b.NotificationType(tenant_id=3, code='custom', label='Only tenant 3')
    s.add(independent)
    s.flush()
    _remove_defaults(b, ts, ns)
    assert s.get(b.NotificationType, independent.id).label == 'Only tenant 3'
    b.session.close()
