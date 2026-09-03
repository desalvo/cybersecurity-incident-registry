"""Static regression checks for Round 5 hardening.

These checks intentionally avoid importing Flask so they can run in minimal
build environments before Python dependencies are installed.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')
REQS = (ROOT / 'requirements.txt').read_text(encoding='utf-8')


def test_backup_admin_is_tenant_scoped():
    assert "BackupJob.query.filter(BackupJob.tenant_id == tenant_id)" in ROUTES
    assert "target_dir = Path(_safe_backup_local_path(job))" in ROUTES
    assert "execute_backup_job_serialized(job" in ROUTES


def test_tenant_import_remaps_database_and_file_ids():
    assert "source.pop('id', None)" in ROUTES
    assert "incident_map.get(r.get('incident_id'))" in ROUTES
    assert "action_map.get(r.get('action_id'))" in ROUTES
    assert "r['stored_name'] = f'{uuid.uuid4().hex}{suffix}'" in ROUTES
    assert "with open(target, 'xb') as out:" in ROUTES


def test_admin_child_queries_are_tenant_scoped():
    assert "writable_notification_type_or_404(type_id)" in ROUTES
    assert "writable_notification_type_or_404(edit_id)" in ROUTES
    assert "tenant_query(ExternalRecipient).filter" in ROUTES
    assert "recipients_query = tenant_query(ExternalRecipient)" in ROUTES


def test_pillow_contains_eps_dos_fix():
    assert 'Pillow==12.3.0' in REQS


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('PASS', name)
