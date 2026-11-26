"""Full Flask HTTP regression for atomic notification type/template removal.

Requires application dependencies. Run by GitHub Actions, not the lightweight
SQLAlchemy-only local test environment.
"""
from test_tenant_defaults_http_and_ownership import ownership_app, _client


def test_admin_delete_type_cascades_templates_and_restores_shared_snapshot(ownership_app):
    from app.models import db, NotificationType, NotificationTemplate
    from app.tenant_defaults_models import TenantDefaultReplica
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        src = NotificationType(tenant_id=ids['shared'], code='rc79_test_notice',
                               label='Published tenant type')
        tmpl = NotificationTemplate(tenant_id=ids['shared'], kind='rc79_test_notice',
                                    name='Published notice', subject='Default text', body='Default body')
        db.session.add_all([src, tmpl])
        db.session.commit()
        local = NotificationType.query.filter_by(tenant_id=ids['own'], code='rc79_test_notice').one()
        local_id = local.id
        own_template = NotificationTemplate.query.filter_by(tenant_id=ids['own'],
                                                            kind='rc79_test_notice').one()
        own_template.subject = 'Local override'
        db.session.commit()
    response = _client(ownership_app).post('/notifiche/tipi', data={
        'action': 'delete', 'type_id': str(local_id)})
    assert response.status_code == 302
    with ownership_app.app_context():
        restored = NotificationType.query.filter_by(tenant_id=ids['own'], code='rc79_test_notice').all()
        templates = NotificationTemplate.query.filter_by(tenant_id=ids['own'], kind='rc79_test_notice').all()
        assert len(restored) == len(templates) == 1
        assert templates[0].name == 'Published notice' and templates[0].subject == 'Default text'
        assert NotificationType.query.filter_by(tenant_id=ids['shared'], code='rc79_test_notice').count() == 1
        assert NotificationTemplate.query.filter_by(tenant_id=ids['shared'], kind='rc79_test_notice').count() == 1
        assert NotificationTemplate.query.filter_by(tenant_id=ids['foreign'], kind='rc79_test_notice').count() == 1
        assert TenantDefaultReplica.query.filter_by(tenant_id=ids['own'], local_type='notification_type',
                                                     local_id=restored[0].id).count() == 1


def test_admin_cannot_delete_notification_type_of_another_tenant(ownership_app):
    from app.models import db, NotificationType
    ids = ownership_app.config['OWNERSHIP_IDS']
    with ownership_app.app_context():
        foreign = NotificationType(tenant_id=ids['foreign'], code='foreign_only_rc79', label='Private')
        db.session.add(foreign)
        db.session.commit()
        identifier = foreign.id
    response = _client(ownership_app).post('/notifiche/tipi', data={
        'action': 'delete', 'type_id': str(identifier)})
    assert response.status_code == 404
    with ownership_app.app_context():
        assert NotificationType.query.filter_by(id=identifier, tenant_id=ids['foreign']).count() == 1
