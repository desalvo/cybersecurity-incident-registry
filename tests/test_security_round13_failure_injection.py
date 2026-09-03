from pathlib import Path

import pytest
from flask import Flask

from app import routes


def _write_tree(base: Path, name: str, content: str):
    base.mkdir(parents=True, exist_ok=True)
    (base / name).write_text(content, encoding='utf-8')


def _txn(monkeypatch, paths):
    monkeypatch.setattr(routes, '_full_import_managed_paths', lambda: paths)
    return routes._FullImportFilesystemTransaction(None, {})


def test_failure_between_backup_and_stage_promotion_restores_live_directory(tmp_path, monkeypatch):
    app = Flask(__name__)
    base = tmp_path / 'uploads'
    _write_tree(base, 'old.txt', 'old')

    with app.app_context():
        txn = _txn(monkeypatch, {'uploads': base})
        stage = txn._stage_path('uploads', base)
        _write_tree(stage, 'new.txt', 'new')
        real_replace = routes.os.replace
        calls = {'count': 0}

        def fail_second_replace(src, dst):
            calls['count'] += 1
            if calls['count'] == 2:
                raise OSError('injected stage promotion failure')
            return real_replace(src, dst)

        monkeypatch.setattr(routes.os, 'replace', fail_second_replace)
        with pytest.raises(OSError, match='injected stage promotion failure'):
            txn.activate()

        assert (base / 'old.txt').read_text(encoding='utf-8') == 'old'
        assert not (base / 'new.txt').exists()
        assert not list(tmp_path.glob('.cir-restore-backup-*'))
        assert not list(tmp_path.glob('.cir-restore-stage-*'))
        assert txn.backups == {}
        assert txn.activated == []
        assert txn.moved_to_backup == []


def test_partial_multi_volume_activation_rolls_back_every_touched_group(tmp_path, monkeypatch):
    app = Flask(__name__)
    uploads = tmp_path / 'uploads'
    ssl = tmp_path / 'ssl'
    _write_tree(uploads, 'old-upload.txt', 'old-upload')
    _write_tree(ssl, 'old.crt', 'old-cert')

    with app.app_context():
        txn = _txn(monkeypatch, {'uploads': uploads, 'ssl': ssl})
        upload_stage = txn._stage_path('uploads', uploads)
        ssl_stage = txn._stage_path('ssl', ssl)
        _write_tree(upload_stage, 'new-upload.txt', 'new-upload')
        _write_tree(ssl_stage, 'new.crt', 'new-cert')
        real_replace = routes.os.replace
        calls = {'count': 0}

        def fail_fourth_replace(src, dst):
            calls['count'] += 1
            # uploads: backup + promote; ssl: backup + failed promote
            if calls['count'] == 4:
                raise OSError('injected second-volume promotion failure')
            return real_replace(src, dst)

        monkeypatch.setattr(routes.os, 'replace', fail_fourth_replace)
        with pytest.raises(OSError, match='injected second-volume promotion failure'):
            txn.activate()

        assert (uploads / 'old-upload.txt').read_text(encoding='utf-8') == 'old-upload'
        assert (ssl / 'old.crt').read_text(encoding='utf-8') == 'old-cert'
        assert not (uploads / 'new-upload.txt').exists()
        assert not (ssl / 'new.crt').exists()
        assert not list(tmp_path.glob('.cir-restore-backup-*'))


def test_failed_rollback_keeps_backup_state_for_retry(tmp_path, monkeypatch):
    app = Flask(__name__)
    base = tmp_path / 'uploads'
    _write_tree(base, 'old.txt', 'old')

    with app.app_context():
        txn = _txn(monkeypatch, {'uploads': base})
        stage = txn._stage_path('uploads', base)
        _write_tree(stage, 'new.txt', 'new')
        real_replace = routes.os.replace
        calls = {'count': 0}

        def fail_promotion_and_first_restore(src, dst):
            calls['count'] += 1
            if calls['count'] in {2, 3}:
                raise OSError('injected failure')
            return real_replace(src, dst)

        monkeypatch.setattr(routes.os, 'replace', fail_promotion_and_first_restore)
        with pytest.raises(RuntimeError, match='rollback filesystem incompleto'):
            txn.activate()

        backup = txn.backups['uploads']
        assert backup.exists()
        assert 'uploads' in txn.moved_to_backup
        assert not base.exists()

        monkeypatch.setattr(routes.os, 'replace', real_replace)
        assert txn.rollback() == []
        assert (base / 'old.txt').read_text(encoding='utf-8') == 'old'
        assert txn.backups == {}
        assert txn.moved_to_backup == []


def test_full_import_keeps_transaction_object_before_staging():
    source = Path(routes.__file__).read_text(encoding='utf-8')
    block = source[source.index('def import_full():'):source.index('def _stats_incidents_for_range')]
    create = block.index('fs_txn = _FullImportFilesystemTransaction(archive, data)')
    stage = block.index('fs_txn.stage()')
    rebuild = block.index('rebuild_database_for_full_import()')
    assert create < stage < rebuild
    assert 'filesystem_rollback_failures = fs_txn.rollback() if fs_txn else []' in block
