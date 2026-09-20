from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")
APP_INIT = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")


def _block(source, start, end):
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def test_full_sequence_alignment_flushes_pending_explicit_ids_first():
    block = _block(ROUTES, "def align_all_table_sequences():", "def is_duplicate_key_integrity_error")
    flush = block.index("db.session.flush()")
    loop = block.index("for table_name in sequence_managed_table_names()")
    assert flush < loop
    assert "if not _is_postgresql_database():" in block


def test_scheduler_advisory_lock_uses_dedicated_connection_handle():
    acquire = _block(ROUTES, "def _try_database_scheduler_lock(", "def _release_database_scheduler_lock")
    release = _block(ROUTES, "def _release_database_scheduler_lock", "def start_deadline_notification_scheduler")
    assert "conn = db.engine.connect()" in acquire
    assert "return ('postgresql-scheduler', conn" in acquire
    assert "db.session.execute" not in acquire
    assert "_release_all_postgresql_advisory_locks(conn)" in release


def test_lock_connections_commit_after_acquire_to_avoid_open_transactions():
    backup = _block(ROUTES, "def _acquire_backup_execution_lock", "def _release_all_postgresql_advisory_locks")
    full_import = _block(ROUTES, "def _acquire_full_import_execution_lock", "def _release_full_import_execution_lock")
    scheduler = _block(ROUTES, "def _try_database_scheduler_lock", "def _release_database_scheduler_lock")
    assert "conn.commit()" in backup
    assert "conn.commit()" in full_import
    assert "conn.commit()" in scheduler


def test_advisory_cleanup_uses_unlock_all_and_invalidates_on_failure():
    block = _block(ROUTES, "def _release_all_postgresql_advisory_locks", "def _release_backup_execution_lock")
    assert "pg_advisory_unlock_all()" in block
    assert "conn.invalidate()" in block
    assert "conn.close()" in block


def test_bootstrap_lock_is_not_bound_to_scoped_session():
    block = APP_INIT[APP_INIT.index("def bootstrap(app):"): ]
    assert "bootstrap_lock_conn = db.engine.connect()" in block
    assert "bootstrap_lock_conn.execute(text('SELECT pg_try_advisory_lock(7420171)'))" in block
    assert "SELECT pg_advisory_unlock_all()" in block
    assert "db.session.execute(text('SELECT pg_try_advisory_lock(7420171)'))" not in block
