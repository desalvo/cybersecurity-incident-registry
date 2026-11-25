"""Pre-Tenants Default full exports reconstruct a source with no category clones.

The archive deliberately lacks all shared-tenant fields and provenance tables,
just as an export from a CIR build before the feature was introduced.
"""
import io
import json
import tarfile


def _legacy_archive(payload):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        member = tarfile.TarInfo('export.json')
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


def test_pre_shared_tenant_full_restore_recreates_defaults_without_duplicate_categories(monkeypatch, tmp_path):
    from test_tenant_defaults_rc18 import _real_app, _superuser_client
    from app.models import db, ConfigLabel, Tenant, User
    from app.routes import _export_tables_payload
    from app.tenant_defaults import ensure_defaults_tenant, sync_defaults_configuration
    from app.tenant_defaults_models import TenantDefaultReplica, TenantDefaultSource
    from app.tenant_defaults_archive import validate_defaults_archive_tables

    app = _real_app(monkeypatch, tmp_path / 'old-export-destination')
    with app.app_context():
        operational = Tenant.query.filter_by(name='default').one()
        local = ConfigLabel.query.filter_by(tenant_id=operational.id, kind='category', value='SPAM').first()
        if local is None:
            local = ConfigLabel(tenant_id=operational.id, kind='category', value='SPAM',
                                description='Configurazione storica del tenant')
            db.session.add(local)
        local.description = 'Configurazione storica del tenant'
        db.session.commit()
        local_id, operational_id = local.id, operational.id
        current_tables = _export_tables_payload()
        old_tenant = next(row for row in current_tables['tenants'] if row['id'] == operational_id)
        old_tenant.pop('is_system_defaults', None)  # column absent in legacy schema
        old_labels = [row for row in current_tables['config_labels']
                      if row['tenant_id'] == operational_id and row['kind'] == 'category'
                      and row['value'] == 'SPAM']
        admin = next(row for row in current_tables['users'] if row['username'] == 'admin')
        old = {
            'format': 'cybersecurity-incident-registry-full-export',
            'version': 2,
            'tables': {'tenants': [old_tenant], 'users': [admin], 'config_labels': old_labels},
            'relations': {}, 'files': {},
        }
        assert validate_defaults_archive_tables(old['tables']) is True
        archive_bytes = _legacy_archive(old)
    response = _superuser_client(app).post('/import/full', data={
        'file': (io.BytesIO(archive_bytes), 'legacy-pre-defaults.tar.gz')
    })
    assert response.status_code == 302, response.get_data(as_text=True)
    with app.app_context():
        shared = Tenant.query.filter_by(is_system_defaults=True).one()
        assert shared.name == 'Tenants Default'
        restored_local = ConfigLabel.query.filter_by(tenant_id=operational_id,
                        kind='category', value='SPAM').one()
        assert restored_local.id == local_id
        assert restored_local.description == 'Configurazione storica del tenant'
        assert ConfigLabel.query.filter_by(tenant_id=operational_id, kind='category').count() == 1
        shared_label = ConfigLabel.query.filter_by(tenant_id=shared.id,
                        kind='category', value='SPAM').one()
        source = TenantDefaultSource.query.filter_by(source_type='config_label',
                                                     source_id=shared_label.id).one()
        replica = TenantDefaultReplica.query.filter_by(source_id=source.id,
                                                       tenant_id=operational_id).one()
        assert replica.local_id == local_id
        assert json.loads(replica.snapshot_json)['__cir_existing_tenant_category'] is True
        # Repeated startup synchronization must not multiply local records.
        assert ensure_defaults_tenant(seed_from_default=True).id == shared.id
        sync_defaults_configuration()
        db.session.commit()
        assert Tenant.query.filter_by(is_system_defaults=True).count() == 1
        assert ConfigLabel.query.filter_by(tenant_id=operational_id, kind='category').count() == 1
