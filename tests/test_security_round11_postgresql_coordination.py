from pathlib import Path
from types import SimpleNamespace

import pytest

from app import routes


ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeConnection:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []
        self.closed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, dict(params or {})))
        return _ScalarResult(next(self.results, True))

    def close(self):
        self.closed = True


class _FakeEngine:
    def __init__(self, connection, dialect='postgresql'):
        self.connection = connection
        self.dialect = SimpleNamespace(name=dialect)

    def connect(self):
        return self.connection


class _FakeDB:
    def __init__(self, connection, dialect='postgresql'):
        self.engine = _FakeEngine(connection, dialect=dialect)


def _sql_calls(connection):
    return [sql for sql, _ in connection.calls]


def test_backup_takes_shared_maintenance_lock_and_namespaced_job_lock(monkeypatch):
    conn = _FakeConnection([True, True, True, True])
    monkeypatch.setattr(routes, 'db', _FakeDB(conn))

    handle = routes._acquire_backup_execution_lock(9999)
    assert handle[0] == 'postgresql-backup'
    calls = _sql_calls(conn)
    assert 'pg_try_advisory_lock_shared' in calls[0]
    assert 'pg_try_advisory_lock(:namespace, :job_id)' in calls[1]
    assert conn.calls[1][1] == {'namespace': routes._CIR_BACKUP_LOCK_NAMESPACE, 'job_id': 9999}

    routes._release_backup_execution_lock(handle)
    calls = _sql_calls(conn)
    assert 'pg_advisory_unlock(:namespace, :job_id)' in calls[2]
    assert 'pg_advisory_unlock_shared' in calls[3]
    assert conn.closed


def test_backup_releases_shared_lock_when_job_lock_is_busy(monkeypatch):
    conn = _FakeConnection([True, False, True])
    monkeypatch.setattr(routes, 'db', _FakeDB(conn))

    assert routes._acquire_backup_execution_lock(7) is None
    calls = _sql_calls(conn)
    assert 'pg_try_advisory_lock_shared' in calls[0]
    assert 'pg_try_advisory_lock(:namespace, :job_id)' in calls[1]
    assert 'pg_advisory_unlock_shared' in calls[2]
    assert conn.closed


def test_full_import_uses_exclusive_version_of_backup_maintenance_lock(monkeypatch):
    conn = _FakeConnection([True, True])
    monkeypatch.setattr(routes, 'db', _FakeDB(conn))

    handle = routes._acquire_full_import_execution_lock()
    assert handle[0] == 'postgresql-full-import'
    first_sql, first_params = conn.calls[0]
    assert 'pg_try_advisory_lock(:lock_id)' in first_sql
    assert first_params['lock_id'] == routes._CIR_FULL_IMPORT_LOCK_ID

    routes._release_full_import_execution_lock(handle)
    assert 'pg_advisory_unlock(:lock_id)' in conn.calls[1][0]
    assert conn.closed


def test_full_import_busy_lock_closes_dedicated_connection(monkeypatch):
    conn = _FakeConnection([False])
    monkeypatch.setattr(routes, 'db', _FakeDB(conn))

    assert routes._acquire_full_import_execution_lock() is None
    assert conn.closed


def test_lock_detection_uses_sqlalchemy_dialect_not_url_string():
    block = ROUTES[ROUTES.index('def _is_postgresql_database():'):ROUTES.index('def _acquire_backup_execution_lock')]
    assert "dialect', None" in block
    assert "== 'postgresql'" in block
    lock_block = ROUTES[ROUTES.index('def _acquire_backup_execution_lock'):ROUTES.index('def execute_backup_job(')]
    assert "str(db.engine.url).startswith('postgresql')" not in lock_block


def test_backup_job_lock_namespace_cannot_overlap_single_key_full_import_lock():
    assert 'pg_try_advisory_lock(:namespace, :job_id)' in ROUTES
    assert '_CIR_BACKUP_LOCK_NAMESPACE' in ROUTES
    assert 'pg_try_advisory_lock_shared(:lock_id)' in ROUTES
    assert 'pg_try_advisory_lock(:lock_id)' in ROUTES
