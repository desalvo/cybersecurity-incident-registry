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


@pytest.fixture
def postgres_defaults_app(postgres_url, tmp_path):
    """Use real PostgreSQL with a private schema, never rewrite public tables."""
    from pathlib import Path
    from app.models import Tenant
    from app.tenant_defaults import ensure_defaults_tenant, register_defaults_events

    schema = _unique_ident('cir_defaults_test')
    control = create_engine(postgres_url, pool_pre_ping=True,
                            connect_args={'options': '-clock_timeout=5000 -cstatement_timeout=30000'})
    with control.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    app = Flask('real_pg_defaults_' + schema)
    app.config.update(TESTING=True, SECRET_KEY='postgres-defaults-integration-only',
        SQLALCHEMY_DATABASE_URI=postgres_url, SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'connect_args': {'options': f'-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=30000'}},
        FORM_TEMPLATE_DIR=str(tmp_path / 'forms'))
    Path(app.config['FORM_TEMPLATE_DIR']).mkdir()
    db.init_app(app)
    try:
        with app.app_context():
            assert db.session.execute(text('SELECT current_schema()')).scalar_one() == schema
            db.create_all()
            db.session.info['cir_defaults_suspended'] = True
            first = Tenant(name='default')
            second = Tenant(name='pg-second-tenant')
            db.session.add_all([first, second])
            defaults = ensure_defaults_tenant()
            ids = {'defaults': defaults.id, 'first': first.id, 'second': second.id}
            db.session.commit()
            register_defaults_events()
            try:
                yield app, ids
            finally:
                db.session.rollback()
                db.session.remove()
                db.engine.dispose()
    finally:
        # This schema name is generated locally and validated by _unique_ident.
        with control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        control.dispose()


def test_real_postgres_recipient_identity_migration_preserves_data_and_other_constraints(postgres_defaults_app):
    from sqlalchemy import inspect
    from app.models import ExternalRecipient
    from app.tenant_defaults_migrations import migrate_recipient_configuration_identity

    _app, ids = postgres_defaults_app
    original = ExternalRecipient(tenant_id=ids['first'], name='Existing recipient',
                                 email='desk@example.test', notes='Preserve these notes')
    db.session.add(original)
    db.session.flush()
    original_id = original.id
    db.session.commit()
    # Recreate both legacy address constraints as an actual upgrade scenario.
    with db.engine.begin() as conn:
        conn.execute(text('ALTER TABLE external_recipient ADD CONSTRAINT legacy_recipient_email UNIQUE (email)'))
        conn.execute(text('ALTER TABLE external_recipient ADD CONSTRAINT legacy_recipient_tenant_email UNIQUE (tenant_id, email)'))
        conn.execute(text('ALTER TABLE external_recipient ADD CONSTRAINT unrelated_recipient_name UNIQUE (tenant_id, name)'))
        conn.execute(text('CREATE INDEX unrelated_recipient_notes ON external_recipient(notes)'))
    assert migrate_recipient_configuration_identity(db.engine) is True
    assert migrate_recipient_configuration_identity(db.engine) is False
    db.session.expire_all()
    restored = db.session.get(ExternalRecipient, original_id)
    assert restored.name == 'Existing recipient'
    assert restored.email == 'desk@example.test' and restored.notes == 'Preserve these notes'
    copy = ExternalRecipient(tenant_id=ids['first'], name='Independent shared recipient', email=restored.email)
    db.session.add(copy)
    db.session.commit()
    assert copy.id != original_id
    assert ExternalRecipient.query.filter_by(tenant_id=ids['first'], email='desk@example.test').count() == 2
    inspector = inspect(db.engine)
    unique_columns = {tuple(row['column_names']) for row in inspector.get_unique_constraints('external_recipient')}
    assert ('email',) not in unique_columns and ('tenant_id', 'email') not in unique_columns
    assert ('tenant_id', 'name') in unique_columns
    indexes = {row['name']: row for row in inspector.get_indexes('external_recipient')}
    assert 'unrelated_recipient_notes' in indexes
    assert indexes['ix_external_recipient_email']['unique'] is False


def test_real_postgres_defaults_publication_rolls_back_atomically_and_retains_in_use_replica(postgres_defaults_app):
    from app.models import ConfigLabel, Incident
    from app.tenant_defaults import sync_defaults_configuration
    from app.tenant_defaults_models import TenantDefaultSource, TenantDefaultReplica, TenantDefaultAlert

    _app, ids = postgres_defaults_app
    local = ConfigLabel(tenant_id=ids['first'], kind='severity', value='Critical', description='Local configuration')
    db.session.add(local)
    db.session.commit()
    local_id = local.id
    db.session.info.pop('cir_defaults_suspended', None)
    unpublished = ConfigLabel(tenant_id=ids['defaults'], kind='severity', value='Critical', description='Transient')
    db.session.add(unpublished)
    db.session.flush()
    unpublished_id = unpublished.id
    sync_defaults_configuration()
    assert TenantDefaultSource.query.count() == 1
    assert TenantDefaultReplica.query.count() == 2
    db.session.rollback()
    assert db.session.get(ConfigLabel, unpublished_id) is None
    assert TenantDefaultSource.query.count() == TenantDefaultReplica.query.count() == 0
    assert db.session.get(ConfigLabel, local_id).description == 'Local configuration'

    published = ConfigLabel(tenant_id=ids['defaults'], kind='severity', value='Critical', description='Published')
    db.session.add(published)
    db.session.commit()
    source = TenantDefaultSource.query.filter_by(source_type='config_label', source_id=published.id).one()
    replica = TenantDefaultReplica.query.filter_by(source_id=source.id, tenant_id=ids['first']).one()
    copied = db.session.get(ConfigLabel, replica.local_id)
    copied_id, source_id = copied.id, source.id
    assert copied.id not in {published.id, local_id}
    assert copied.value != local.value
    published.description = 'Updated before commit'
    db.session.flush()
    db.session.commit()
    assert db.session.get(ConfigLabel, copied_id).description == 'Updated before commit'

    incident = Incident(tenant_id=ids['first'], name='Uses shared severity', reference='PG-DEFAULTS', severity_id=copied_id)
    db.session.add(incident)
    db.session.commit()
    db.session.delete(published)
    db.session.commit()
    assert db.session.get(ConfigLabel, copied_id) is not None
    assert db.session.get(Incident, incident.id).severity_id == copied_id
    assert not db.session.get(TenantDefaultSource, source_id).active
    assert TenantDefaultReplica.query.filter_by(source_id=source_id).count() == 0
    assert TenantDefaultAlert.query.filter_by(source_id=source_id, tenant_id=ids['first'], local_id=copied_id).count() == 1
    assert db.session.get(ConfigLabel, local_id).description == 'Local configuration'


def test_real_postgres_catalog_repeated_copies_are_independent_and_rollback_is_complete(postgres_defaults_app):
    import json
    from app.models import (ConfigLabel, IncidentWorkflowStep, FormTemplateConfig,
                            FormTemplateBinary, Setting)
    from app.workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow, import_catalog_workflow
    from app.workflow_catalog_models import WorkflowCatalogInstallation

    _app, ids = postgres_defaults_app
    category = ConfigLabel(tenant_id=ids['first'], kind='category', value='Source workflow')
    action = ConfigLabel(tenant_id=ids['first'], kind='action_label', value='Investigate')
    db.session.add_all([category, action])
    db.session.flush()
    custom_type = 'x' * 20
    db.session.add_all([
        Setting(key=f'tenant:{ids["first"]}:workflow_step_types_json',
                value=json.dumps([{'code': custom_type, 'label': 'Custom task', 'description': 'PostgreSQL width test'}])),
        FormTemplateConfig(template_name='pg_workflow_form', owner_tenant_id=ids['first']),
        FormTemplateBinary(template_name='pg_workflow_form', filename='pg_workflow_form.pdf', pdf_data=b'%PDF-1.4\n%%EOF\n'),
        IncidentWorkflowStep(tenant_id=ids['first'], category_id=category.id, action_label_id=action.id,
            position=1, description='Initial catalog step', step_type=custom_type,
            document_generation_enabled=True, document_template_name='pg_workflow_form'),
    ])
    db.session.commit()
    entry = save_catalog_workflow(build_catalog_workflow_payload(ids['first'], category.id), 'Reusable PG workflow')
    db.session.commit()
    first = import_catalog_workflow(entry.id, ids['second'], copy_name='Response team A')
    db.session.commit()
    second = import_catalog_workflow(entry.id, ids['second'], copy_name='Response team B')
    db.session.commit()
    receipts = WorkflowCatalogInstallation.query.filter_by(entry_id=entry.id, tenant_id=ids['second'], entry_version=entry.version).all()
    assert len(receipts) == 2
    assert {row.copy_name for row in receipts} == {'Response team A', 'Response team B'}
    assert first['category_id'] != second['category_id'] and first['step_ids'] != second['step_ids']
    installed_a = db.session.get(IncidentWorkflowStep, first['step_ids'][0])
    installed_b = db.session.get(IncidentWorkflowStep, second['step_ids'][0])
    assert installed_a.tenant_id == installed_b.tenant_id == ids['second']
    assert len(installed_a.step_type) <= 20 and len(installed_b.step_type) <= 20
    assert installed_a.document_template_name != installed_b.document_template_name
    for row in (installed_a, installed_b):
        config = FormTemplateConfig.query.filter_by(template_name=row.document_template_name).one()
        assert config.owner_tenant_id == ids['second']
        assert db.session.get(ConfigLabel, row.action_label_id).tenant_id == ids['second']
    installed_a.description = 'Only team A changed this copy'
    db.session.commit()
    assert installed_b.description == 'Initial catalog step'
    before = (WorkflowCatalogInstallation.query.count(), ConfigLabel.query.count(),
              IncidentWorkflowStep.query.count(), FormTemplateConfig.query.count(), FormTemplateBinary.query.count())
    transient = import_catalog_workflow(entry.id, ids['second'], copy_name='Rolled back team C')
    assert transient['created'] == 1
    db.session.rollback()
    assert (WorkflowCatalogInstallation.query.count(), ConfigLabel.query.count(),
            IncidentWorkflowStep.query.count(), FormTemplateConfig.query.count(), FormTemplateBinary.query.count()) == before
    assert db.session.get(IncidentWorkflowStep, transient['step_ids'][0]) is None
    assert db.session.get(IncidentWorkflowStep, first['step_ids'][0]).description == 'Only team A changed this copy'
