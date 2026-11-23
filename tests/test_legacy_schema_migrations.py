"""Execute the supported legacy DDL paths against real database engines.

These targeted transition schemas exercise pre-SSO identity, pre-split incident
dates and restart preservation. They are deliberately labelled transition
fixtures, not historical production dumps. Complete RC16 startup is covered by
test_automatic_upgrade_integration.py using the archived RC16 model.
"""
from contextlib import ExitStack, contextmanager
from datetime import datetime
import os
import re
import uuid

import tempfile
import unittest
from pathlib import Path
from flask import Flask
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app import run_schema_migrations
from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep, NotificationType, Tenant, db


@contextmanager
def _migration_database(backend, tmp_path):
    control = None
    schema = None
    if backend == "postgresql":
        url = (os.environ.get("CIR_POSTGRES_TEST_URL") or "").strip()
        if not url:
            raise unittest.SkipTest("CIR_POSTGRES_TEST_URL is required for the real PostgreSQL migration tests")
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql":
            raise AssertionError("CIR_POSTGRES_TEST_URL must point to PostgreSQL")
        if ("test" not in (parsed.database or "").lower()
                and os.environ.get("CIR_POSTGRES_TEST_ALLOW_NONTEST_DATABASE") != "1"):
            raise AssertionError("Refusing migration tests outside an explicitly disposable test database")
        control = create_engine(url, pool_pre_ping=True)
        schema = "cir_upgrade_" + uuid.uuid4().hex
        assert re.fullmatch(r"[a-z0-9_]+", schema)
        # A configured but unreachable PostgreSQL server is a failure, not a
        # silent skip of an explicitly requested production-database gate.
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine_options = {"connect_args": {"options": f"-csearch_path={schema}"}}
    else:
        url = "sqlite:///" + str(tmp_path / "legacy-transition.sqlite")
        engine_options = {}
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI=url,
                      SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      SQLALCHEMY_ENGINE_OPTIONS=engine_options)
    db.init_app(app)
    try:
        with app.app_context():
            # Other tests may already have registered the global propagation
            # listeners. These tests inspect migration SQL without publishing
            # partially constructed transition fixtures to shared defaults.
            db.session.info["cir_defaults_suspended"] = True
            try:
                yield app
            finally:
                db.session.rollback()
                db.session.remove()
                db.engine.dispose()
    finally:
        if control is not None:
            try:
                with control.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            finally:
                control.dispose()


def _legacy_users(provider_type=None, provider="local"):
    """A transition table preceding tenant and authentication-provider fields."""
    pk = "SERIAL PRIMARY KEY" if db.engine.dialect.name == "postgresql" else "INTEGER PRIMARY KEY"
    provider_column = f", auth_provider {provider_type}" if provider_type else ""
    with db.engine.begin() as connection:
        connection.execute(text(f'''CREATE TABLE "user" (
            id {pk}, username VARCHAR(160) NOT NULL,
            name VARCHAR(160), email VARCHAR(255), password_hash VARCHAR(255),
            is_ldap BOOLEAN NOT NULL DEFAULT FALSE, role VARCHAR(20) NOT NULL,
            created_at TIMESTAMP {provider_column})'''))
        connection.execute(text('CREATE UNIQUE INDEX legacy_user_username ON "user"(username)'))
        columns = ", auth_provider" if provider_type else ""
        values = ", :provider" if provider_type else ""
        connection.execute(text(f'''INSERT INTO "user"
            (id, username, name, password_hash, is_ldap, role, created_at{columns})
            VALUES (31, 'legacy-reader', 'Preserved user', 'preserved-password-hash',
                    FALSE, 'reader', '2026-09-02 10:20:30'{values})'''), {"provider": provider})
        if not provider_type:
            connection.execute(text('''INSERT INTO "user"
                (id, username, name, password_hash, is_ldap, role, created_at)
                VALUES (32, 'legacy-directory', 'Preserved LDAP user', NULL,
                        TRUE, 'writer', '2026-09-02 10:21:30')'''))
    # Existing user table is intentionally retained; all auxiliary current
    # tables are supplied exactly as bootstrap's create_all() supplies them.
    db.create_all()


def _rows(sql):
    with db.engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql)).all()]



class _MigrationTestCase(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix="cir-legacy-migration-test-"))
        self.app = stack.enter_context(_migration_database(self.backend, Path(temporary)))


class _CommonLegacyMigrationCases:
    def test_pre_sso_identity_and_tenant_upgrade_preserves_data_on_repeat(self):
        migration_app = self.app
        _legacy_users()
        # The default tenant may need an ID other than 1 after an older import.
        db.session.add(Tenant(id=1, name="existing-ordinary-tenant"))
        db.session.commit()
        if db.engine.dialect.name == "postgresql":
            # This direct migration test isolates the schema transition from the
            # separate PostgreSQL sequence-repair bootstrap operation.
            with db.engine.begin() as connection:
                connection.execute(text("SELECT setval(pg_get_serial_sequence('tenant', 'id'), 1, true)"))
        run_schema_migrations(migration_app)
        tenant_rows = _rows("SELECT id, name FROM tenant ORDER BY id")
        default_id = next(tid for tid, name in tenant_rows if name == "default")
        assert default_id != 1
        assert (1, "existing-ordinary-tenant") in tenant_rows
        users = _rows('SELECT id, username, name, password_hash, auth_provider, tenant_id, default_tenant_id FROM "user" ORDER BY id')
        assert users == [
            (31, "legacy-reader", "Preserved user", "preserved-password-hash", "local", default_id, default_id),
            (32, "legacy-directory", "Preserved LDAP user", None, "ldap", default_id, default_id),
        ]
        memberships = _rows("SELECT id, user_id, tenant_id, role FROM user_tenant_role ORDER BY id")
        assert {(row[1], row[2], row[3]) for row in memberships} == {
            (31, default_id, "reader"), (32, default_id, "writer"),
        }
        run_schema_migrations(migration_app)
        assert _rows('SELECT id, username, name, password_hash, auth_provider, tenant_id, default_tenant_id FROM "user" ORDER BY id') == users
        assert _rows("SELECT id, user_id, tenant_id, role FROM user_tenant_role ORDER BY id") == memberships
        assert _rows("SELECT id, name FROM tenant ORDER BY id") == tenant_rows


    def test_split_incident_dates_are_backfilled_during_first_migration(self):
        migration_app = self.app
        db.create_all()
        incident = Incident(name="Preserved incident", reference="KEEP-0041",
                            description="Preserved incident content",
                            created_at=datetime(2026, 9, 2, 10, 20, 30))
        db.session.add(incident)
        db.session.commit()
        incident_id = incident.id
        db.session.remove()
        with db.engine.begin() as connection:
            for column in ("start_date", "start_time", "end_date", "end_time"):
                connection.execute(text(f'ALTER TABLE incident DROP COLUMN "{column}"'))
            connection.execute(text("ALTER TABLE incident ADD COLUMN start_at TIMESTAMP"))
            connection.execute(text("ALTER TABLE incident ADD COLUMN end_at TIMESTAMP"))
            connection.execute(text("""UPDATE incident SET start_at='2026-09-01 08:15:00',
                                       end_at='2026-09-02 09:45:00' WHERE id=:id"""), {"id": incident_id})
        run_schema_migrations(migration_app)
        row = _rows("SELECT id, name, reference, description, start_date, start_time, end_date, end_time FROM incident")[0]
        assert row[:4] == (incident_id, "Preserved incident", "KEEP-0041", "Preserved incident content")
        assert tuple(str(value) for value in row[4:]) == ("2026-09-01", "08:15:00", "2026-09-02", "09:45:00")
        # A later operator correction must not be replaced by retained legacy
        # timestamp columns when another startup performs the idempotent bridge.
        with db.engine.begin() as connection:
            connection.execute(text("UPDATE incident SET start_date='2026-08-31', start_time='07:30:00' WHERE id=:id"),
                               {"id": incident_id})
        run_schema_migrations(migration_app)
        corrected = _rows("SELECT start_date, start_time, end_date, end_time FROM incident")[0]
        assert tuple(str(value) for value in corrected) == ("2026-08-31", "07:30:00", "2026-09-02", "09:45:00")


    def test_existing_workflow_flags_and_empty_automatic_operations_survive_restart(self):
        migration_app = self.app
        db.create_all()
        label = ConfigLabel(kind="action_label", value="Conclusione personalizzata",
                            description="Keep operator configuration", automatic_operations="",
                            default_exportable=True)
        db.session.add(label)
        db.session.flush()
        step = IncidentWorkflowStep(action_label_id=label.id, position=7, required=True,
                                    personal_data_only=False, conditions="")
        db.session.add(step)
        db.session.commit()
        label_id, step_id = label.id, step.id
        for _ in range(2):
            run_schema_migrations(migration_app)
            assert _rows(f"SELECT automatic_operations, description FROM config_label WHERE id={label_id}") == [
                ("", "Keep operator configuration"),
            ]
            row = _rows(f"SELECT required, personal_data_only, position FROM incident_workflow_step WHERE id={step_id}")[0]
            assert bool(row[0]) is True
            assert bool(row[1]) is False
            assert row[2] == 7


class SQLiteLegacySchemaMigrationTests(_CommonLegacyMigrationCases, _MigrationTestCase):
    backend = "sqlite"


class PostgreSQLLegacySchemaMigrationTests(_CommonLegacyMigrationCases, _MigrationTestCase):
    backend = "postgresql"

    def test_postgres_orphan_ownership_aborts_without_deletion_and_can_be_repaired(self):
        db.create_all()
        incident = Incident(name="Preserved parent incident", reference="PARENT-001")
        db.session.add(incident)
        db.session.flush()
        action = Action(incident_id=incident.id, when_at=datetime(2026, 9, 2, 10, 20),
                        person_name="Demonstration operator", description="Preserved child action")
        db.session.add(action)
        db.session.commit()
        incident_id, action_id = incident.id, action.id
        foreign_keys = inspect(db.engine).get_foreign_keys("action")
        quote = db.engine.dialect.identifier_preparer.quote
        with db.engine.begin() as connection:
            for foreign_key in foreign_keys:
                if foreign_key["constrained_columns"] == ["incident_id"]:
                    connection.execute(text(f'ALTER TABLE action DROP CONSTRAINT {quote(foreign_key["name"])}'))
            connection.execute(text("ALTER TABLE action ALTER COLUMN incident_id DROP NOT NULL"))
            connection.execute(text("UPDATE action SET incident_id=999999 WHERE id=:id"), {"id": action_id})
        before = _rows("SELECT id, incident_id, description FROM action")
        with self.assertRaisesRegex(RuntimeError, "NULL/orphan rows require manual repair"):
            run_schema_migrations(self.app)
        assert _rows("SELECT id, incident_id, description FROM action") == before
        assert _rows("SELECT id, name FROM incident") == [(incident_id, "Preserved parent incident")]
        with db.engine.begin() as connection:
            connection.execute(text("UPDATE action SET incident_id=:parent WHERE id=:id"),
                               {"parent": incident_id, "id": action_id})
        run_schema_migrations(self.app)
        column = next(column for column in inspect(db.engine).get_columns("action")
                      if column["name"] == "incident_id")
        assert column["nullable"] is False
        assert any(foreign_key["constrained_columns"] == ["incident_id"]
                   and foreign_key.get("options", {}).get("ondelete") == "CASCADE"
                   for foreign_key in inspect(db.engine).get_foreign_keys("action"))
        assert _rows("SELECT id, incident_id, description FROM action") == [
            (action_id, incident_id, "Preserved child action"),
        ]

    def test_postgres_bridge_realigns_stale_tenant_sequence_before_creating_default(self):
        from app import _schema_upgrade_callbacks
        _legacy_users()
        db.session.add(Tenant(id=1, name="existing-ordinary-tenant"))
        db.session.commit()
        with db.engine.begin() as connection:
            connection.execute(text("SELECT setval(pg_get_serial_sequence('tenant', 'id'), 1, false)"))
        _schema_upgrade_callbacks(self.app)["20261122_01_legacy_bridge"]()
        tenant_rows = _rows("SELECT id, name FROM tenant ORDER BY id")
        assert (1, "existing-ordinary-tenant") in tenant_rows
        assert any(tenant_id > 1 and name == "default" for tenant_id, name in tenant_rows)
        assert _rows('SELECT password_hash FROM "user" WHERE id=31') == [("preserved-password-hash",)]

    def test_postgres_legacy_username_index_becomes_provider_scoped(self):
        postgres_migration_app = self.app
        _legacy_users()
        run_schema_migrations(postgres_migration_app)
        with db.engine.begin() as connection:
            connection.execute(text('''INSERT INTO "user"
                (username, name, password_hash, is_ldap, role, auth_provider)
                VALUES ('legacy-reader', 'Separate SSO account', NULL, FALSE, 'reader', 'sso:fixture')'''))
        assert _rows('SELECT username, auth_provider FROM "user" WHERE username=\'legacy-reader\' ORDER BY auth_provider') == [
            ("legacy-reader", "local"), ("legacy-reader", "sso:fixture"),
        ]
        with self.assertRaises(IntegrityError):
            with db.engine.begin() as connection:
                connection.execute(text('''INSERT INTO "user"
                    (username, is_ldap, role, auth_provider)
                    VALUES ('legacy-reader', FALSE, 'reader', 'local')'''))
        assert _rows('SELECT password_hash FROM "user" WHERE id=31') == [("preserved-password-hash",)]


    def test_postgres_duplicate_configuration_fails_without_deleting_rows(self):
        postgres_migration_app = self.app
        db.create_all()
        tenant = Tenant(name="default")
        db.session.add(tenant)
        db.session.commit()
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE notification_type DROP CONSTRAINT uq_notification_type_tenant_code"))
        db.session.add_all([
            NotificationType(tenant_id=tenant.id, code="duplicate", label="First configuration"),
            NotificationType(tenant_id=tenant.id, code="duplicate", label="Second configuration"),
        ])
        db.session.commit()
        before = _rows("SELECT id, tenant_id, code, label FROM notification_type ORDER BY id")
        with self.assertRaisesRegex(RuntimeError, "Duplicate tenant configuration in notification_type"):
            run_schema_migrations(postgres_migration_app)
        assert _rows("SELECT id, tenant_id, code, label FROM notification_type ORDER BY id") == before


    def test_postgres_identity_ddl_failure_propagates_and_retry_keeps_existing_users(self):
        postgres_migration_app = self.app
        _legacy_users()

        def fail_identity_constraint(_connection, _cursor, statement, _parameters, _context, _executemany):
            if 'ADD CONSTRAINT uq_user_username_auth_provider' in statement:
                raise RuntimeError("injected identity constraint failure")

        event.listen(db.engine, "before_cursor_execute", fail_identity_constraint)
        try:
            with self.assertRaisesRegex(RuntimeError, "injected identity constraint failure"):
                run_schema_migrations(postgres_migration_app)
        finally:
            event.remove(db.engine, "before_cursor_execute", fail_identity_constraint)
        assert _rows('SELECT id, password_hash FROM "user" ORDER BY id') == [
            (31, "preserved-password-hash"), (32, None),
        ]
        # Dropping the legacy index and adding its replacement belong to the same
        # transaction: an unsuccessful replacement must leave uniqueness in place.
        assert any(index["name"] == "legacy_user_username" for index in inspect(db.engine).get_indexes("user"))
        run_schema_migrations(postgres_migration_app)
        assert not any(index["name"] == "legacy_user_username" for index in inspect(db.engine).get_indexes("user"))


    def test_postgres_auth_provider_widening_failure_is_not_hidden(self):
        postgres_migration_app = self.app
        _legacy_users(provider_type="VARCHAR(40)")

        def fail_widening(_connection, _cursor, statement, _parameters, _context, _executemany):
            if 'ALTER COLUMN auth_provider TYPE VARCHAR(80)' in statement:
                raise RuntimeError("injected provider widening failure")

        event.listen(db.engine, "before_cursor_execute", fail_widening)
        try:
            with self.assertRaisesRegex(RuntimeError, "injected provider widening failure"):
                run_schema_migrations(postgres_migration_app)
        finally:
            event.remove(db.engine, "before_cursor_execute", fail_widening)
        assert _rows('SELECT password_hash FROM "user" WHERE id=31') == [("preserved-password-hash",)]
        run_schema_migrations(postgres_migration_app)
        column = next(column for column in inspect(db.engine).get_columns("user") if column["name"] == "auth_provider")
        assert column["type"].length == 80


    def test_postgres_long_provider_identity_is_not_truncated(self):
        postgres_migration_app = self.app
        provider = "sso:" + "p" * 96
        _legacy_users(provider_type="VARCHAR(160)", provider=provider)
        run_schema_migrations(postgres_migration_app)
        assert _rows('SELECT auth_provider, password_hash FROM "user" WHERE id=31') == [
            (provider, "preserved-password-hash"),
        ]
        column = next(column for column in inspect(db.engine).get_columns("user") if column["name"] == "auth_provider")
        assert column["type"].length == 160


# unittest can execute these real SQLite tests with runtime dependencies only.
# In the complete CI suite pytest also selects the PostgreSQL class with -m postgres.
try:
    import pytest
except ImportError:
    pass
else:
    PostgreSQLLegacySchemaMigrationTests.pytestmark = pytest.mark.postgres


if __name__ == "__main__":
    unittest.main()
