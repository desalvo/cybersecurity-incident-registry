"""Opt-in startup/full-import upgrades against an isolated PostgreSQL schema."""
import importlib.util
import os
from pathlib import Path
import re
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


pytestmark = pytest.mark.postgres
_spec = importlib.util.spec_from_file_location(
    'cir_automatic_upgrade_support', Path(__file__).with_name('test_automatic_upgrade_integration.py'))
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)


@pytest.fixture
def postgres_upgrade_database(tmp_path):
    raw = (os.environ.get('CIR_POSTGRES_TEST_URL') or '').strip()
    if not raw:
        pytest.skip('CIR_POSTGRES_TEST_URL not configured')
    url = make_url(raw)
    if url.get_backend_name() != 'postgresql':
        pytest.fail('CIR_POSTGRES_TEST_URL must use PostgreSQL')
    if ('test' not in (url.database or '').lower()
            and os.environ.get('CIR_POSTGRES_TEST_ALLOW_NONTEST_DATABASE') != '1'):
        pytest.fail('Automatic upgrade tests require a disposable test database')
    # A private search_path prevents any rewrite of public/application tables.
    # A configured but unreachable service is a failure, not a skipped gate.
    schema = 'cir_upgrade_test_' + uuid.uuid4().hex[:16]
    assert re.fullmatch(r'cir_upgrade_test_[0-9a-f]{16}', schema)
    control = create_engine(url, pool_pre_ping=True)
    options = f'-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=30000'
    scoped_url = url.set(query={**url.query, 'options': options})
    engine = None
    with control.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        with support._configured_environment(tmp_path, scoped_url.render_as_string(hide_password=False)):
            engine = create_engine(scoped_url, pool_pre_ping=True)
            with engine.connect() as conn:
                assert conn.execute(text('SELECT current_schema()')).scalar_one() == schema
            yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def test_real_postgres_rc16_automatic_upgrade_and_restart(postgres_upgrade_database):
    support._upgrade_twice(postgres_upgrade_database)


def test_real_postgres_full_import_schema_rollback_preserves_ledger(postgres_upgrade_database):
    from app import create_app
    from app.models import Incident, db
    from app.routes import rebuild_database_for_full_import
    seed = support._seed_rc16(postgres_upgrade_database)
    current = create_app()
    before = support._snapshot(current, seed)
    with current.app_context():
        rebuild_database_for_full_import()
        assert db.session.query(Incident).count() == 0
        ledger_count = db.session.execute(text('SELECT COUNT(*) FROM cir_schema_migrations')).scalar_one()
        assert ledger_count == len(before['ledger'])
        db.session.rollback()
    assert support._snapshot(current, seed) == before
