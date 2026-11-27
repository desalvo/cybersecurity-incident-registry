"""SQLAlchemy/SQLite adapter regressions with real ORM transactions.

Runnable with unittest and no Flask or pytest import. A compatibility-runtime
run supplements, and never replaces, the pinned CI/real PostgreSQL gates.
"""
import importlib.util
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, event, inspect, text
from sqlalchemy.orm import Session, registry, scoped_session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cir_migration_manager_sqlalchemy", ROOT / "app" / "migration_manager.py")
manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = manager
SPEC.loader.exec_module(manager)

R1 = manager.SCHEMA_REVISIONS[0]
R2 = "20261201_01_example_followup"


class SQLAlchemyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cir-ledger-sa-")
        self.path = Path(self.directory.name) / "app.db"
        self.engine = create_engine("sqlite:///" + str(self.path))
        self.mapper = registry()
        self.metadata = self.mapper.metadata
        self.table = Table("bootstrap_record", self.metadata,
                           Column("id", Integer, primary_key=True),
                           Column("value", String(80), nullable=False))

        class Record:
            def __init__(self, value):
                self.value = value

        self.Record = Record
        self.mapper.map_imperatively(Record, self.table)

    def tearDown(self):
        self.mapper.dispose()
        self.engine.dispose()
        self.directory.cleanup()

    def _prepare(self):
        return manager.prepare_schema_upgrade(
            self.engine, {R1: lambda: self.metadata.create_all(self.engine)}, (R1,))

    def _bootstrap_once(self):
        completed = self._prepare()
        manager.validate_model_schema(self.engine, self.metadata)
        with Session(self.engine) as session:
            session.add(self.Record("initial seed"))
            manager.stage_schema_upgrade(session, completed)
            session.commit()
        return completed

    def test_first_bootstrap_commits_orm_data_and_ledger_together(self):
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).status, "no-ledger")
        completed = self._prepare()
        self.assertEqual(completed.completed_ids, (R1,))
        manager.validate_model_schema(self.engine, self.metadata)
        with Session(self.engine) as session:
            session.add(self.Record("new seed"))
            manager.stage_schema_upgrade(session, completed)
            session.flush()
            self.assertEqual(session.execute(text("SELECT COUNT(*) FROM cir_schema_migrations")).scalar_one(), 1)
            with closing(sqlite3.connect(self.path)) as observer:
                self.assertEqual(observer.execute("SELECT COUNT(*) FROM bootstrap_record").fetchone()[0], 0)
                self.assertFalse(manager.SQLiteLedgerStore(observer).read_snapshot().exists)
            session.commit()
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).status, "current")
        with Session(self.engine) as observer:
            self.assertEqual(observer.query(self.Record).one().value, "new seed")

    def test_second_start_skips_callbacks_and_current_staging_has_no_writes(self):
        self._bootstrap_once()

        def published_callback():
            self.fail("A current schema must not rerun its recorded callback")

        completed = manager.prepare_schema_upgrade(self.engine, {R1: published_callback}, (R1,))
        self.assertEqual(completed.completed_ids, ())
        manager.validate_model_schema(self.engine, self.metadata)
        statements = []

        def trace(_connection, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        with Session(self.engine) as session:
            row = session.query(self.Record).one()
            row.value = "bootstrap reconciliation still runs"
            event.listen(self.engine, "before_cursor_execute", trace)
            try:
                manager.stage_schema_upgrade(session, completed)
            finally:
                event.remove(self.engine, "before_cursor_execute", trace)
            self.assertFalse(any(sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE"))
                                 for sql in statements))
            session.commit()
        with Session(self.engine) as observer:
            self.assertEqual(observer.query(self.Record).one().value, "bootstrap reconciliation still runs")
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).applied_ids, (R1,))

    def test_rollback_discards_orm_seed_and_new_ledger_table(self):
        completed = self._prepare()
        with Session(self.engine) as session:
            session.add(self.Record("must rollback"))
            manager.stage_schema_upgrade(session, completed)
            session.flush()
            session.rollback()
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).status, "no-ledger")
        with Session(self.engine) as observer:
            self.assertEqual(observer.query(self.Record).count(), 0)

    def test_rollback_without_prior_dml_discards_staged_ledger_ddl(self):
        completed = self._prepare()
        with Session(self.engine) as session:
            manager.stage_schema_upgrade(session, completed)
            raw = session.connection().connection.driver_connection
            self.assertTrue(raw.in_transaction)
            session.rollback()
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).status, "no-ledger")

    def test_scoped_session_uses_same_transaction_as_orm_seed(self):
        completed = self._prepare()
        session = scoped_session(sessionmaker(bind=self.engine))
        try:
            session.add(self.Record("scoped pending seed"))
            manager.stage_schema_upgrade(session, completed)
            session.flush()
            session.rollback()
        finally:
            session.remove()
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).status, "no-ledger")
        with Session(self.engine) as observer:
            self.assertEqual(observer.query(self.Record).count(), 0)

    def test_followup_failure_preserves_existing_prefix_and_orm_data(self):
        self._bootstrap_once()
        calls = []
        completed = manager.prepare_schema_upgrade(self.engine,
            {R1: lambda: self.fail("Bridge callback reran"), R2: lambda: calls.append(R2)}, (R1, R2))
        self.assertEqual(calls, [R2])
        with Session(self.engine) as session:
            session.query(self.Record).one().value = "must rollback"
            manager.stage_schema_upgrade(session, completed)
            session.flush()
            session.rollback()
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1, R2)).applied_ids, (R1,))
        with Session(self.engine) as observer:
            self.assertEqual(observer.query(self.Record).one().value, "initial seed")

    def test_engine_read_connection_is_released_before_schema_callback(self):
        engine = create_engine("sqlite:///" + str(Path(self.directory.name) / "single-pool.db"),
                               pool_size=1, max_overflow=0, pool_timeout=0.1)
        try:
            completed = manager.prepare_schema_upgrade(engine,
                {R1: lambda: self.metadata.create_all(engine)}, (R1,))
            manager.validate_model_schema(engine, self.metadata)
            with Session(engine) as session:
                manager.stage_schema_upgrade(session, completed)
                session.commit()
            self.assertEqual(manager.assert_schema_supported(engine, (R1,)).status, "current")
        finally:
            engine.dispose()

    def test_ahead_schema_rejected_before_callback_and_without_database_changes(self):
        self._bootstrap_once()
        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO cir_schema_migrations VALUES "
                "(2, '20990101_01_future', '2099-01-01T00:00:00+00:00')"))
        calls = []
        with closing(sqlite3.connect(self.path)) as raw:
            before = tuple(raw.iterdump())
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.prepare_schema_upgrade(self.engine, {R1: lambda: calls.append(R1)}, (R1,))
        self.assertEqual(calls, [])
        with closing(sqlite3.connect(self.path)) as raw:
            self.assertEqual(tuple(raw.iterdump()), before)

    def test_model_validation_detects_missing_table_and_column_before_marker(self):
        with self.assertRaisesRegex(manager.SchemaCompatibilityError, "missing tables"):
            manager.validate_model_schema(self.engine, self.metadata)
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE bootstrap_record (id INTEGER PRIMARY KEY)"))
        with self.assertRaisesRegex(manager.SchemaCompatibilityError, "missing columns.*value"):
            manager.validate_model_schema(self.engine, self.metadata)
        self.assertNotIn(manager.LEDGER_TABLE, inspect(self.engine).get_table_names())

    def test_view_cannot_impersonate_schema_ledger(self):
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE VIEW cir_schema_migrations AS SELECT 1 AS position, "
                "'20261122_01_legacy_bridge' AS revision_id, 'now' AS applied_at"))
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.assert_schema_supported(self.engine, (R1,))

    def test_partial_ddl_callback_failure_is_retryable_without_marker(self):
        calls = []

        def fail_after_ddl():
            calls.append("failed")
            self.metadata.create_all(self.engine)
            raise RuntimeError("injected after committed DDL")

        with self.assertRaises(manager.MigrationExecutionError):
            manager.prepare_schema_upgrade(self.engine, {R1: fail_after_ddl}, (R1,))
        self.assertIn("bootstrap_record", inspect(self.engine).get_table_names())
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).status, "no-ledger")
        self._bootstrap_once()
        self.assertEqual(calls, ["failed"])
        self.assertEqual(manager.assert_schema_supported(self.engine, (R1,)).status, "current")

    @unittest.skipUnless(hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"), "requires sqlite3 Python 3.12 transaction API")
    def test_true_driver_autocommit_session_is_rejected_before_marker_write(self):
        engine = create_engine("sqlite:///" + str(Path(self.directory.name) / "autocommit.db"),
                               connect_args={"autocommit": True})
        try:
            completed = manager.prepare_schema_upgrade(engine, {R1: lambda: None}, (R1,))
            with Session(engine) as session:
                with self.assertRaises(manager.SchemaCompatibilityError):
                    manager.stage_schema_upgrade(session, completed)
            self.assertEqual(manager.assert_schema_supported(engine, (R1,)).status, "no-ledger")
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
