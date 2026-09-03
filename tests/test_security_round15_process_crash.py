import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
from flask import Flask

from app import db, routes
from app.models import Setting


HELPER = Path(__file__).parent / 'helpers' / 'full_import_crash_worker.py'


def _app(database_url: str, root: Path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_DIR=str(root / 'uploads'),
        FORM_TEMPLATE_DIR=str(root / 'form_templates'),
        LOGO_DIR=str(root / 'logo'),
        SSO_LOGO_DIR=str(root / 'sso'),
        SSL_DIR=str(root / 'ssl'),
        AI_CHATBOT_DOC_DIR=str(root / 'ai_docs'),
        BACKUP_DIR=str(root / 'backups'),
    )
    db.init_app(app)
    return app


def _wait_for_ready(proc, ready: Path, timeout=None):
    if timeout is None:
        raw_timeout = os.environ.get('CIR_CRASH_TEST_CHECKPOINT_TIMEOUT', '30')
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            timeout = 30.0
        timeout = max(5.0, timeout)
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        if ready.exists():
            return json.loads(ready.read_text(encoding='utf-8'))
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            raise AssertionError(
                f'crash worker exited before checkpoint: rc={proc.returncode}\n'
                f'stdout={stdout}\nstderr={stderr}'
            )
        time.sleep(0.05)
    proc.terminate()
    stdout, stderr = proc.communicate(timeout=5)
    elapsed = time.monotonic() - started
    raise AssertionError(
        f'crash worker did not reach checkpoint after {elapsed:.1f}s ' 
        f'(timeout={timeout:.1f}s)\nstdout={stdout}\nstderr={stderr}'
    )


def exercise_sigkill_recovery(database_url: str, root: Path, mode: str):
    if not hasattr(signal, 'SIGKILL'):
        pytest.skip('SIGKILL non disponibile su questa piattaforma')

    uploads = root / 'uploads'
    uploads.mkdir(parents=True)
    (uploads / 'old.txt').write_text('old', encoding='utf-8')
    ready = root / f'{mode}.ready.json'
    env = os.environ.copy()
    project_root = str(Path(__file__).parents[1])
    env['PYTHONPATH'] = project_root + os.pathsep + env.get('PYTHONPATH', '')
    proc = subprocess.Popen(
        [
            sys.executable,
            str(HELPER),
            '--database-url', database_url,
            '--root', str(root),
            '--mode', mode,
            '--ready-file', str(ready),
        ],
        cwd=project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = _wait_for_ready(proc, ready)
    assert payload['pid'] == proc.pid
    assert (uploads / 'new.txt').read_text(encoding='utf-8') == 'new'
    assert list(root.glob('.cir-restore-backup-*'))
    assert (root / 'backups' / '.cir-full-import-restore-journal.json').exists()

    os.kill(proc.pid, signal.SIGKILL)
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == -signal.SIGKILL, (stdout, stderr)

    # Create a fresh Flask/SQLAlchemy context after the worker is gone. This is
    # intentionally not the context that performed the filesystem activation.
    app = _app(database_url, root)
    with app.app_context():
        assert routes.recover_interrupted_full_import() is True
        marker = db.session.get(Setting, routes._FULL_IMPORT_COMMIT_MARKER_KEY)
        assert marker is None
        db.session.remove()
        db.engine.dispose()

    assert not list(root.glob('.cir-restore-backup-*'))
    assert not (root / 'backups' / '.cir-full-import-restore-journal.json').exists()
    if mode == 'precommit':
        assert (uploads / 'old.txt').read_text(encoding='utf-8') == 'old'
        assert not (uploads / 'new.txt').exists()
    else:
        assert (uploads / 'new.txt').read_text(encoding='utf-8') == 'new'
        assert not (uploads / 'old.txt').exists()


def test_sigkill_before_db_commit_restores_previous_filesystem(tmp_path):
    db_path = tmp_path / 'crash-precommit.db'
    exercise_sigkill_recovery(f'sqlite:///{db_path}', tmp_path, 'precommit')


def test_sigkill_after_db_commit_keeps_promoted_filesystem(tmp_path):
    db_path = tmp_path / 'crash-postcommit.db'
    exercise_sigkill_recovery(f'sqlite:///{db_path}', tmp_path, 'postcommit')
