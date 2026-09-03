"""Opt-in integration tests against a real PostgreSQL server.

Set CIR_POSTGRES_TEST_URL to enable these tests. The default test suite skips
this module cleanly when PostgreSQL is not reachable/configured. Use
scripts/run_postgres_tests.sh to start the disposable Docker service. Round 15
also exercises real SIGKILL crash/restart recovery around the commit token.
"""
import os
import re
import threading
import uuid

import pytest
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.models import db

pytestmark = pytest.mark.postgres


def _postgres_url():
    return (os.environ.get('CIR_POSTGRES_TEST_URL') or '').strip()


def _require_disposable_test_database(url):
    database = (make_url(url).database or '').strip().lower()
    explicitly_allowed = os.environ.get('CIR_POSTGRES_TEST_ALLOW_NONTEST_DATABASE') == '1'
    if 'test' not in database and not explicitly_allowed:
        pytest.fail(
            'Rifiuto di eseguire la suite PostgreSQL su un database che non sembra di test: '
            f'{database or "<senza nome>"}. Usa un database dedicato con "test" nel nome oppure '
            'imposta CIR_POSTGRES_TEST_ALLOW_NONTEST_DATABASE=1 solo in un ambiente usa-e-getta.'
        )


@pytest.fixture(scope='module')
def postgres_url():
    url = _postgres_url()
    if not url:
        pytest.skip('CIR_POSTGRES_TEST_URL non impostata; test PostgreSQL reale disabilitato')
    _require_disposable_test_database(url)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            if conn.dialect.name != 'postgresql':
                pytest.skip('CIR_POSTGRES_TEST_URL non punta a PostgreSQL')
            conn.execute(text('SELECT 1'))
    except OperationalError as exc:
        pytest.skip(f'PostgreSQL di test non raggiungibile: {exc}')
    finally:
        engine.dispose()
    return url


@pytest.fixture
def postgres_app(postgres_url, tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=postgres_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_DIR=str(tmp_path / 'uploads'),
        LOGO_DIR=str(tmp_path / 'logo'),
        SSO_LOGO_DIR=str(tmp_path / 'sso'),
        FORM_TEMPLATE_DIR=str(tmp_path / 'forms'),
        BACKUP_DIR=str(tmp_path / 'backups'),
        AI_CHATBOT_DOC_DIR=str(tmp_path / 'ai_docs'),
    )
    db.init_app(app)
    with app.app_context():
        yield app
        db.session.rollback()
        db.session.remove()
        db.engine.dispose()


def _unique_ident(prefix):
    value = f'{prefix}_{uuid.uuid4().hex[:12]}'
    assert re.fullmatch(r'[a-z0-9_]+', value)
    return value


def test_real_postgres_backup_shared_lock_blocks_full_import(postgres_app):
    from app.routes import (
        _acquire_backup_execution_lock,
        _acquire_full_import_execution_lock,
        _release_backup_execution_lock,
        _release_full_import_execution_lock,
    )

    with postgres_app.app_context():
        backup_a = _acquire_backup_execution_lock(12001)
        backup_b = _acquire_backup_execution_lock(12002)
        assert backup_a and backup_a[0] == 'postgresql-backup'
        assert backup_b and backup_b[0] == 'postgresql-backup'
        try:
            assert _acquire_full_import_execution_lock() is None
        finally:
            _release_backup_execution_lock(backup_b)
            _release_backup_execution_lock(backup_a)

        full_import = _acquire_full_import_execution_lock()
        assert full_import and full_import[0] == 'postgresql-full-import'
        try:
            assert _acquire_backup_execution_lock(12003) is None
        finally:
            _release_full_import_execution_lock(full_import)


def test_real_postgres_same_backup_job_is_mutually_exclusive_across_threads(postgres_app):
    from app.routes import _acquire_backup_execution_lock, _release_backup_execution_lock

    started = threading.Event()
    release = threading.Event()
    result = {}

    def holder():
        with postgres_app.app_context():
            handle = _acquire_backup_execution_lock(13001)
            result['holder'] = bool(handle)
            started.set()
            release.wait(timeout=10)
            _release_backup_execution_lock(handle)

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert started.wait(timeout=10)
    assert result.get('holder') is True
    with postgres_app.app_context():
        assert _acquire_backup_execution_lock(13001) is None
    release.set()
    thread.join(timeout=10)
    assert not thread.is_alive()

    with postgres_app.app_context():
        handle = _acquire_backup_execution_lock(13001)
        assert handle
        _release_backup_execution_lock(handle)


def test_real_postgres_sequence_alignment_after_explicit_ids(postgres_app):
    from app.routes import align_table_sequence

    table = _unique_ident('cir_seq_r12')
    with postgres_app.app_context():
        try:
            db.session.execute(text(f'CREATE TABLE "{table}" (id SERIAL PRIMARY KEY, value TEXT)'))
            db.session.execute(text(f'INSERT INTO "{table}" (id, value) VALUES (50, \'explicit\')'))
            db.session.flush()
            align_table_sequence(table)
            generated = db.session.execute(
                text(f'INSERT INTO "{table}" (value) VALUES (\'generated\') RETURNING id')
            ).scalar_one()
            assert generated == 51
            db.session.rollback()
        finally:
            db.session.rollback()
            with db.engine.begin() as conn:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


def test_real_postgres_transactional_ddl_rollback_preserves_previous_state(postgres_app):
    """Exercise the PostgreSQL property relied on by destructive Full Import.

    DROP/CREATE plus row replacement are performed in one transaction. A
    rollback must restore both the previous table definition and its data.
    """
    table = _unique_ident('cir_restore_r12')
    with postgres_app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, value TEXT NOT NULL)'))
            conn.execute(text(f'INSERT INTO "{table}" VALUES (1, \'before\')'))

        connection = db.engine.connect()
        transaction = connection.begin()
        try:
            connection.execute(text(f'DROP TABLE "{table}"'))
            connection.execute(text(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, value TEXT NOT NULL)'))
            connection.execute(text(f'INSERT INTO "{table}" VALUES (2, \'after\')'))
            transaction.rollback()
        finally:
            connection.close()

        try:
            with db.engine.connect() as conn:
                rows = conn.execute(text(f'SELECT id, value FROM "{table}" ORDER BY id')).all()
            assert rows == [(1, 'before')]
        finally:
            with db.engine.begin() as conn:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


def test_real_postgres_advisory_lock_released_when_connection_closes(postgres_app):
    """Session advisory locks must not survive a crashed/closed worker connection."""
    lock_id = 4712999912
    with postgres_app.app_context():
        first = db.engine.connect()
        assert first.execute(text('SELECT pg_try_advisory_lock(:id)'), {'id': lock_id}).scalar() is True
        second = db.engine.connect()
        try:
            assert second.execute(text('SELECT pg_try_advisory_lock(:id)'), {'id': lock_id}).scalar() is False
            # invalidate() closes the physical DBAPI connection instead of merely
            # returning it to SQLAlchemy's pool, accurately modelling a worker
            # process losing its PostgreSQL session.
            first.invalidate()
            first.close()
            assert second.execute(text('SELECT pg_try_advisory_lock(:id)'), {'id': lock_id}).scalar() is True
            second.execute(text('SELECT pg_advisory_unlock(:id)'), {'id': lock_id})
        finally:
            if not first.closed:
                first.close()
            second.close()


@pytest.mark.parametrize('mode', ['precommit', 'postcommit'])
def test_real_postgres_sigkill_full_import_recovery(postgres_url, tmp_path, mode):
    """Kill an external restore worker and recover using a fresh DB session.

    Unlike exception injection, SIGKILL prevents Python cleanup/finally blocks
    from running. PostgreSQL must decide recovery solely from whether the commit
    token transaction became durable before the worker disappeared.
    """
    import json
    from pathlib import Path
    import signal
    import subprocess
    import sys
    import time

    if not hasattr(signal, 'SIGKILL'):
        pytest.skip('SIGKILL non disponibile su questa piattaforma')

    from app import routes
    from app.models import Setting

    root = tmp_path / f'pg-crash-{mode}'
    uploads = root / 'uploads'
    uploads.mkdir(parents=True)
    (uploads / 'old.txt').write_text('old', encoding='utf-8')
    ready = root / 'ready.json'
    helper = Path(__file__).parent / 'helpers' / 'full_import_crash_worker.py'
    project_root = str(Path(__file__).parents[1])
    env = os.environ.copy()
    env['PYTHONPATH'] = project_root + os.pathsep + env.get('PYTHONPATH', '')
    proc = subprocess.Popen(
        [
            sys.executable,
            str(helper),
            '--database-url', postgres_url,
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
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not ready.exists():
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            pytest.fail(f'worker terminato prima del checkpoint: {stdout}\n{stderr}')
        time.sleep(0.05)
    if not ready.exists():
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
        pytest.fail(f'checkpoint SIGKILL non raggiunto: {stdout}\n{stderr}')
    payload = json.loads(ready.read_text(encoding='utf-8'))
    assert payload['pid'] == proc.pid
    assert (uploads / 'new.txt').exists()

    os.kill(proc.pid, signal.SIGKILL)
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == -signal.SIGKILL, (stdout, stderr)

    recovery_app = Flask(__name__)
    recovery_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=postgres_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_DIR=str(root / 'uploads'),
        LOGO_DIR=str(root / 'logo'),
        SSO_LOGO_DIR=str(root / 'sso'),
        FORM_TEMPLATE_DIR=str(root / 'forms'),
        SSL_DIR=str(root / 'ssl'),
        BACKUP_DIR=str(root / 'backups'),
        AI_CHATBOT_DOC_DIR=str(root / 'ai_docs'),
    )
    db.init_app(recovery_app)
    with recovery_app.app_context():
        assert routes.recover_interrupted_full_import() is True
        assert db.session.get(Setting, routes._FULL_IMPORT_COMMIT_MARKER_KEY) is None
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
