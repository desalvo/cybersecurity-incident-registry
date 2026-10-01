from pathlib import Path

from flask import Flask

from app import db, routes


def _app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'fresh.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        BACKUP_DIR=str(tmp_path / 'backups'),
    )
    db.init_app(app)
    return app


def test_fresh_database_recovery_does_not_query_setting_before_schema_exists(tmp_path, monkeypatch):
    app = _app(tmp_path)
    with app.app_context():
        monkeypatch.setattr(routes, '_setting_table_exists', lambda: False)

        def forbidden_get(*args, **kwargs):
            raise AssertionError('Setting must not be queried before bootstrap creates the schema')

        monkeypatch.setattr(db.session, 'get', forbidden_get)
        assert routes._clear_full_import_commit_marker() is True
        assert routes.recover_interrupted_full_import() is False


def test_mountpoint_activation_and_rollback_never_rename_mount_root(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config['BACKUP_DIR'] = str(tmp_path / 'backups')
    base = tmp_path / 'uploads'
    base.mkdir()
    (base / 'old.txt').write_text('old', encoding='utf-8')

    monkeypatch.setattr(
        routes,
        '_is_full_import_mountpoint',
        lambda path: Path(path) == base,
    )
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: {'uploads': base})

    with app.app_context():
        txn = routes._FullImportFilesystemTransaction(None, {})
        stage = txn._stage_path('uploads', base)
        assert stage.parent == base
        (stage / 'new.txt').write_text('new', encoding='utf-8')

        txn.activate()
        assert base.exists()
        assert (base / 'new.txt').read_text(encoding='utf-8') == 'new'
        assert not (base / 'old.txt').exists()
        backup = txn.backups['uploads']
        assert backup.parent == base
        assert (backup / 'old.txt').read_text(encoding='utf-8') == 'old'

        assert txn.rollback() == []
        assert base.exists()
        assert (base / 'old.txt').read_text(encoding='utf-8') == 'old'
        assert not (base / 'new.txt').exists()
        assert not list(base.glob('.cir-restore-stage-*'))
        assert not list(base.glob('.cir-restore-backup-*'))


def test_mountpoint_activation_finalize_keeps_new_contents(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config['BACKUP_DIR'] = str(tmp_path / 'backups')
    base = tmp_path / 'uploads'
    base.mkdir()
    (base / 'old.txt').write_text('old', encoding='utf-8')

    monkeypatch.setattr(
        routes,
        '_is_full_import_mountpoint',
        lambda path: Path(path) == base,
    )
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: {'uploads': base})

    with app.app_context():
        txn = routes._FullImportFilesystemTransaction(None, {})
        stage = txn._stage_path('uploads', base)
        (stage / 'new.txt').write_text('new', encoding='utf-8')
        txn.activate()
        assert txn.finalize() == []

        assert base.exists()
        assert (base / 'new.txt').read_text(encoding='utf-8') == 'new'
        assert not (base / 'old.txt').exists()
        assert not list(base.glob('.cir-restore-stage-*'))
        assert not list(base.glob('.cir-restore-backup-*'))


def test_mountpoint_crash_recovery_restores_previous_contents(tmp_path, monkeypatch):
    app = _app(tmp_path)
    base = tmp_path / 'uploads'
    base.mkdir()
    (base / 'old.txt').write_text('old', encoding='utf-8')

    monkeypatch.setattr(
        routes,
        '_is_full_import_mountpoint',
        lambda path: Path(path) == base,
    )
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: {'uploads': base})

    with app.app_context():
        db.create_all()
        txn = routes._FullImportFilesystemTransaction(None, {})
        stage = txn._stage_path('uploads', base)
        (stage / 'new.txt').write_text('new', encoding='utf-8')
        txn.journal = {
            'version': routes._FULL_IMPORT_JOURNAL_VERSION,
            'token': txn.token,
            'created_at': '2026-10-01T00:00:00+00:00',
            'groups': {'uploads': {'had_original': True, 'state': 'staged'}},
        }
        txn._persist_journal()
        txn.activate()

        assert (base / 'new.txt').exists()
        assert routes.recover_interrupted_full_import() is True
        assert (base / 'old.txt').read_text(encoding='utf-8') == 'old'
        assert not (base / 'new.txt').exists()
        assert not list(base.glob('.cir-restore-stage-*'))
        assert not list(base.glob('.cir-restore-backup-*'))


def test_mountpoint_activation_failure_restores_partial_backup(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config['BACKUP_DIR'] = str(tmp_path / 'backups')
    base = tmp_path / 'uploads'
    base.mkdir()
    (base / 'old-a.txt').write_text('a', encoding='utf-8')
    (base / 'old-b.txt').write_text('b', encoding='utf-8')

    monkeypatch.setattr(routes, '_is_full_import_mountpoint', lambda path: Path(path) == base)
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: {'uploads': base})

    with app.app_context():
        txn = routes._FullImportFilesystemTransaction(None, {})
        stage = txn._stage_path('uploads', base)
        (stage / 'new.txt').write_text('new', encoding='utf-8')

        real_replace = routes.os.replace
        moves_to_backup = {'count': 0}

        def fail_second_backup_move(src, dst):
            if Path(dst).parent.name.startswith('.cir-restore-backup-'):
                moves_to_backup['count'] += 1
                if moves_to_backup['count'] == 2:
                    raise OSError('injected mounted-volume backup failure')
            return real_replace(src, dst)

        monkeypatch.setattr(routes.os, 'replace', fail_second_backup_move)
        try:
            txn.activate()
            raise AssertionError('activation should have failed')
        except OSError as exc:
            assert 'injected mounted-volume backup failure' in str(exc)

        assert (base / 'old-a.txt').read_text(encoding='utf-8') == 'a'
        assert (base / 'old-b.txt').read_text(encoding='utf-8') == 'b'
        assert not (base / 'new.txt').exists()
        assert not list(base.glob('.cir-restore-backup-*'))


def test_mountpoint_recovery_merges_partial_backup_when_crash_happened_while_moving_old_data(tmp_path, monkeypatch):
    app = _app(tmp_path)
    base = tmp_path / 'uploads'
    base.mkdir()
    (base / 'old-unmoved.txt').write_text('unmoved', encoding='utf-8')

    monkeypatch.setattr(routes, '_is_full_import_mountpoint', lambda path: Path(path) == base)
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: {'uploads': base})

    with app.app_context():
        db.create_all()
        token = '1' * 32
        stage, backup = routes._full_import_artifact_paths(token, 'uploads', base)
        stage.mkdir()
        (stage / 'new.txt').write_text('new', encoding='utf-8')
        backup.mkdir()
        (backup / 'old-moved.txt').write_text('moved', encoding='utf-8')
        routes._write_full_import_journal({
            'version': routes._FULL_IMPORT_JOURNAL_VERSION,
            'token': token,
            'created_at': '2026-10-01T00:00:00+00:00',
            'groups': {'uploads': {'had_original': True, 'state': 'moving_backup'}},
        })

        assert routes.recover_interrupted_full_import() is True
        assert (base / 'old-unmoved.txt').read_text(encoding='utf-8') == 'unmoved'
        assert (base / 'old-moved.txt').read_text(encoding='utf-8') == 'moved'
        assert not (base / 'new.txt').exists()
        assert not list(base.glob('.cir-restore-stage-*'))
        assert not list(base.glob('.cir-restore-backup-*'))
