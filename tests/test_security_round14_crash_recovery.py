from pathlib import Path

import pytest
from flask import Flask

from app import db, routes
from app.models import Setting


def _write_tree(base: Path, name: str, content: str):
    base.mkdir(parents=True, exist_ok=True)
    (base / name).write_text(content, encoding='utf-8')


def _app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'recovery.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        BACKUP_DIR=str(tmp_path / 'backups'),
    )
    db.init_app(app)
    return app


def _crash_ready_txn(monkeypatch, base: Path, *, had_original=True):
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: {'uploads': base})
    txn = routes._FullImportFilesystemTransaction(None, {})
    stage = txn._stage_path('uploads', base)
    _write_tree(stage, 'new.txt', 'new')
    txn.journal = {
        'version': routes._FULL_IMPORT_JOURNAL_VERSION,
        'token': txn.token,
        'created_at': '2026-09-02T00:00:00+00:00',
        'groups': {'uploads': {'had_original': had_original, 'state': 'staged'}},
    }
    txn._persist_journal()
    txn.activate()
    return txn


def test_startup_recovery_restores_old_volume_when_db_commit_was_not_completed(tmp_path, monkeypatch):
    app = _app(tmp_path)
    base = tmp_path / 'uploads'
    _write_tree(base, 'old.txt', 'old')

    with app.app_context():
        db.create_all()
        txn = _crash_ready_txn(monkeypatch, base)
        txn.mark_database_commit_pending()
        # A process/host crash before COMMIT makes the DB transaction disappear.
        db.session.rollback()

        assert (base / 'new.txt').read_text(encoding='utf-8') == 'new'
        assert list(tmp_path.glob('.cir-restore-backup-*'))
        assert routes._full_import_journal_path().exists()

        assert routes.recover_interrupted_full_import() is True
        assert (base / 'old.txt').read_text(encoding='utf-8') == 'old'
        assert not (base / 'new.txt').exists()
        assert not list(tmp_path.glob('.cir-restore-backup-*'))
        assert not routes._full_import_journal_path().exists()


def test_startup_recovery_finalizes_new_volume_when_db_commit_token_is_present(tmp_path, monkeypatch):
    app = _app(tmp_path)
    base = tmp_path / 'uploads'
    _write_tree(base, 'old.txt', 'old')

    with app.app_context():
        db.create_all()
        txn = _crash_ready_txn(monkeypatch, base)
        txn.mark_database_commit_pending()
        db.session.commit()

        assert db.session.get(Setting, routes._FULL_IMPORT_COMMIT_MARKER_KEY).value == txn.token
        assert (base / 'new.txt').read_text(encoding='utf-8') == 'new'
        assert list(tmp_path.glob('.cir-restore-backup-*'))

        assert routes.recover_interrupted_full_import() is True
        assert (base / 'new.txt').read_text(encoding='utf-8') == 'new'
        assert not (base / 'old.txt').exists()
        assert not list(tmp_path.glob('.cir-restore-backup-*'))
        assert db.session.get(Setting, routes._FULL_IMPORT_COMMIT_MARKER_KEY) is None
        assert not routes._full_import_journal_path().exists()


def test_startup_recovery_removes_new_directory_that_had_no_pre_restore_snapshot(tmp_path, monkeypatch):
    app = _app(tmp_path)
    base = tmp_path / 'uploads'

    with app.app_context():
        db.create_all()
        _crash_ready_txn(monkeypatch, base, had_original=False)
        assert (base / 'new.txt').exists()

        assert routes.recover_interrupted_full_import() is True
        assert not base.exists()
        assert not routes._full_import_journal_path().exists()


def test_invalid_recovery_journal_fails_closed_without_touching_live_volume(tmp_path, monkeypatch):
    app = _app(tmp_path)
    base = tmp_path / 'uploads'
    _write_tree(base, 'old.txt', 'old')
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: {'uploads': base})

    with app.app_context():
        db.create_all()
        journal = routes._full_import_journal_path()
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text('{"version":1,"token":"../../bad","groups":{}}', encoding='utf-8')

        with pytest.raises(RuntimeError, match='Journal Full Import non valido'):
            routes.recover_interrupted_full_import()
        assert (base / 'old.txt').read_text(encoding='utf-8') == 'old'


def test_create_app_runs_crash_recovery_before_bootstrap():
    source = Path(routes.__file__).with_name('__init__.py').read_text(encoding='utf-8')
    context = source[source.index('with app.app_context():'):source.index('start_deadline_notification_scheduler(app)')]
    assert context.index('recover_interrupted_full_import_serialized()') < context.index('bootstrap(app)')


def test_full_import_commit_marker_is_written_before_database_commit():
    source = Path(routes.__file__).read_text(encoding='utf-8')
    block = source[source.index('def import_full():'):source.index('def _stats_incidents_for_range')]
    marker = block.index('fs_txn.mark_database_commit_pending()')
    final_commit = block.index('db.session.commit()', marker)
    finalize = block.index('fs_txn.finalize()', final_commit)
    assert marker < final_commit < finalize


def test_startup_recovery_uses_full_import_advisory_lock_on_postgres():
    source = Path(routes.__file__).read_text(encoding='utf-8')
    block = source[source.index('def recover_interrupted_full_import_serialized():'):source.index('def execute_backup_job', source.index('def recover_interrupted_full_import_serialized():'))]
    assert "SELECT pg_advisory_lock(:lock_id)" in block
    assert "SELECT pg_advisory_unlock(:lock_id)" in block
    assert "{'lock_id': _CIR_FULL_IMPORT_LOCK_ID}" in block
