"""Real SQLite ledger regressions runnable without importing Flask or SQLAlchemy.

Run directly with ``python tests/test_migration_manager_stdlib.py``. Pytest also
collects these unittest cases in the complete application suite. ORM/bootstrap
and real PostgreSQL coverage live in test_automatic_upgrade_integration.py.
"""
import importlib.util
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cir_migration_manager_stdlib", ROOT / "app" / "migration_manager.py")
manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = manager
SPEC.loader.exec_module(manager)

R1 = "20261122_01_legacy_bridge"
R2 = "20261201_01_add_optional_field"
R3 = "20261202_01_add_reference_index"
REVISIONS = (R1, R2, R3)
STAMP = "2026-11-22T12:00:00+00:00"


class MigrationManagerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cir-ledger-test-")
        self.path = Path(self.directory.name) / "ledger.db"
        self.connection = sqlite3.connect(self.path)
        self.store = manager.SQLiteLedgerStore(self.connection)

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def _callbacks(self, calls, revisions=REVISIONS):
        return {revision: lambda revision=revision: calls.append(revision)
                for revision in revisions}

    def _raw_ledger(self, rows):
        # Deliberately omit constraints/type affinity so corrupt real database
        # histories (duplicates, text ordinals, gaps) can be represented.
        self.connection.execute("DROP TABLE IF EXISTS cir_schema_migrations")
        self.connection.execute(
            "CREATE TABLE cir_schema_migrations (position, revision_id, applied_at)")
        self.connection.executemany(
            "INSERT INTO cir_schema_migrations VALUES (?, ?, ?)", rows)
        self.connection.commit()

    def _commit_prefix(self, count):
        ids = REVISIONS[:count]
        completed = manager.apply_upgrade(self.store, self._callbacks([], ids), ids)
        manager.stage_upgrade(self.store, completed)
        self.connection.commit()

    def test_empty_database_preflight_is_read_only(self):
        statements = []
        self.connection.set_trace_callback(statements.append)
        plan = manager.plan_upgrade(self.store)
        self.assertEqual(plan.status, "no-ledger")
        self.assertEqual(plan.applied_ids, ())
        self.assertEqual(plan.pending_ids, manager.SCHEMA_REVISIONS)
        self.assertFalse(self.connection.in_transaction)
        self.assertTrue(statements)
        self.assertFalse(any(sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "BEGIN"))
                             for sql in statements))

    def test_legacy_database_without_ledger_remains_supported_and_unchanged(self):
        self.connection.execute("CREATE TABLE tenant_data (id INTEGER PRIMARY KEY, value TEXT)")
        self.connection.execute("INSERT INTO tenant_data VALUES (1, 'preserve this value')")
        self.connection.commit()
        before = tuple(self.connection.iterdump())
        plan = manager.plan_upgrade(self.store)
        self.assertEqual(plan.status, "no-ledger")
        self.assertEqual(tuple(self.connection.iterdump()), before)

    def test_existing_empty_ledger_is_a_supported_baseline(self):
        self.store.begin_staging()
        self.store.create_ledger()
        self.connection.commit()
        plan = manager.plan_upgrade(self.store)
        self.assertEqual(plan.status, "baseline")
        self.assertEqual(plan.pending_ids, manager.SCHEMA_REVISIONS)

    def test_ordered_chain_only_becomes_current_after_staging_and_commit(self):
        calls = []
        completed = manager.apply_upgrade(self.store, self._callbacks(calls), REVISIONS)
        self.assertEqual(calls, list(REVISIONS))
        self.assertEqual(completed.completed_ids, REVISIONS)
        self.assertFalse(self.store.read_snapshot().exists)
        manager.stage_upgrade(self.store, completed)
        self.assertTrue(self.connection.in_transaction)
        with closing(sqlite3.connect(self.path)) as observer:
            self.assertEqual(manager.plan_upgrade(manager.SQLiteLedgerStore(observer), REVISIONS).status,
                             "no-ledger")
        self.connection.commit()
        self.assertEqual(manager.plan_upgrade(self.store, REVISIONS).status, "current")
        self.assertEqual([row[:2] for row in self.store.read_snapshot().rows],
                         list(enumerate(REVISIONS, start=1)))

    def test_restart_of_current_schema_calls_nothing_and_stages_no_writes(self):
        self._commit_prefix(3)
        statements, calls = [], []
        self.connection.set_trace_callback(statements.append)
        completed = manager.apply_upgrade(self.store, self._callbacks(calls), REVISIONS)
        manager.stage_upgrade(self.store, completed)
        self.assertEqual(calls, [])
        self.assertEqual(completed.completed_ids, ())
        self.assertFalse(self.connection.in_transaction)
        self.assertFalse(any(sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "BEGIN"))
                             for sql in statements))

    def test_prefix_runs_only_remaining_callbacks_in_registry_order(self):
        self._commit_prefix(1)
        calls = []
        plan = manager.plan_upgrade(self.store, REVISIONS)
        self.assertEqual(plan.status, "baseline")
        self.assertEqual(plan.applied_ids, (R1,))
        self.assertEqual(plan.pending_ids, (R2, R3))
        completed = manager.apply_upgrade(self.store, self._callbacks(calls), REVISIONS)
        self.assertEqual(calls, [R2, R3])
        manager.stage_upgrade(self.store, completed)
        self.connection.commit()
        self.assertEqual(manager.plan_upgrade(self.store, REVISIONS).applied_ids, REVISIONS)

    def test_same_functional_version_can_receive_a_new_schema_revision(self):
        self.connection.execute("CREATE TABLE deployment (functional_version TEXT)")
        self.connection.execute("INSERT INTO deployment VALUES ('0.9.0-1')")
        self.connection.commit()
        self._commit_prefix(1)
        calls = []

        def append_field():
            calls.append(R2)
            self.connection.execute("ALTER TABLE deployment ADD COLUMN detail TEXT")

        completed = manager.apply_upgrade(self.store,
            {R1: lambda: self.fail("The published bridge must not rerun"), R2: append_field}, (R1, R2))
        manager.stage_upgrade(self.store, completed)
        self.connection.commit()
        self.assertEqual(calls, [R2])
        self.assertEqual(self.connection.execute("SELECT functional_version FROM deployment").fetchone()[0],
                         "0.9.0-1")
        self.assertEqual(manager.plan_upgrade(self.store, (R1, R2)).status, "current")

    def test_unknown_future_gap_reordered_and_duplicate_histories_fail_before_callbacks(self):
        scenarios = {
            "unknown": [(1, "20990101_01_future", STAMP)],
            "ahead": [(1, R1, STAMP), (2, R2, STAMP), (3, R3, STAMP), (4, "20990101_01_future", STAMP)],
            "ordinal-gap": [(1, R1, STAMP), (3, R2, STAMP)],
            "missing-revision": [(1, R1, STAMP), (2, R3, STAMP)],
            "wrong-order": [(1, R2, STAMP), (2, R1, STAMP)],
            "duplicate-id": [(1, R1, STAMP), (2, R1, STAMP)],
            "duplicate-position": [(1, R1, STAMP), (1, R2, STAMP)],
            "zero-position": [(0, R1, STAMP)],
            "negative-position": [(-1, R1, STAMP)],
            "text-position": [("1", R1, STAMP)],
            "float-position": [(1.0, R1, STAMP)],
            "missing-timestamp": [(1, R1, "")],
            "nonstring-id": [(1, 42, STAMP)],
        }
        for scenario, rows in scenarios.items():
            with self.subTest(scenario=scenario):
                self._raw_ledger(rows)
                before, calls = tuple(self.connection.iterdump()), []
                with self.assertRaises(manager.SchemaCompatibilityError):
                    manager.apply_upgrade(self.store, self._callbacks(calls), REVISIONS)
                self.assertEqual(calls, [])
                self.assertEqual(tuple(self.connection.iterdump()), before)
                self.assertFalse(self.connection.in_transaction)

    def test_boolean_position_is_rejected_without_integer_coercion(self):
        class BooleanStore:
            def read_snapshot(self):
                return manager.LedgerSnapshot(True, ((True, R1, STAMP),))
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.plan_upgrade(BooleanStore(), (R1,))

    def test_older_application_rejects_known_newer_prefix_without_mutation(self):
        self._commit_prefix(2)
        before, calls = tuple(self.connection.iterdump()), []
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.apply_upgrade(self.store, self._callbacks(calls, (R1,)), (R1,))
        self.assertEqual(calls, [])
        self.assertEqual(tuple(self.connection.iterdump()), before)

    def test_missing_or_nonphysical_ledger_shape_fails_before_callback(self):
        self.connection.execute("CREATE TABLE cir_schema_migrations (revision_id TEXT)")
        calls = []
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.apply_upgrade(self.store, self._callbacks(calls, (R1,)))
        self.assertEqual(calls, [])
        self.connection.execute("DROP TABLE cir_schema_migrations")
        self.connection.execute("CREATE VIEW cir_schema_migrations AS SELECT 1 AS position")
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.apply_upgrade(self.store, self._callbacks(calls, (R1,)))
        self.assertEqual(calls, [])

    def test_noncanonical_ledger_name_is_not_mistaken_for_legacy_database(self):
        self.connection.execute("CREATE TABLE CIR_SCHEMA_MIGRATIONS (position, revision_id, applied_at)")
        self.connection.execute("INSERT INTO CIR_SCHEMA_MIGRATIONS VALUES (1, '20990101_01_future', ?)", (STAMP,))
        self.connection.commit()
        calls = []
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.apply_upgrade(self.store, self._callbacks(calls, (R1,)))
        self.assertEqual(calls, [])

    def test_partial_ddl_failure_has_no_success_marker_and_idempotent_retry_succeeds(self):
        calls = []
        fail = [True]

        def bridge():
            calls.append(R1)
            self.connection.execute("CREATE TABLE IF NOT EXISTS bridge_data (id INTEGER PRIMARY KEY)")
            # Emulate the existing bridge's individually committed DDL blocks.
            self.connection.commit()

        def later():
            calls.append(R2)
            if fail[0]:
                raise RuntimeError("injected DDL failure")
            self.connection.execute("CREATE INDEX IF NOT EXISTS bridge_index ON bridge_data(id)")
            self.connection.commit()

        callbacks = {R1: bridge, R2: later}
        with self.assertRaises(manager.MigrationExecutionError) as caught:
            manager.apply_upgrade(self.store, callbacks, (R1, R2))
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)
        self.assertFalse(self.store.read_snapshot().exists)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM bridge_data").fetchone()[0], 0)
        fail[0] = False
        completed = manager.apply_upgrade(self.store, callbacks, (R1, R2))
        manager.stage_upgrade(self.store, completed)
        self.connection.commit()
        self.assertEqual(calls, [R1, R2, R1, R2])
        self.assertEqual(manager.plan_upgrade(self.store, (R1, R2)).status, "current")

    def test_rollback_before_commit_removes_seed_data_and_all_staged_markers(self):
        self.connection.execute("CREATE TABLE bootstrap_data (value TEXT)")
        completed = manager.apply_upgrade(self.store, self._callbacks([], (R1,)), (R1,))
        self.connection.execute("INSERT INTO bootstrap_data VALUES ('pending seed')")
        manager.stage_upgrade(self.store, completed)
        self.assertEqual(manager.plan_upgrade(self.store, (R1,)).status, "current")
        with closing(sqlite3.connect(self.path)) as observer:
            self.assertEqual(observer.execute("SELECT COUNT(*) FROM bootstrap_data").fetchone()[0], 0)
            self.assertFalse(manager.SQLiteLedgerStore(observer).read_snapshot().exists)
        self.connection.rollback()
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM bootstrap_data").fetchone()[0], 0)
        self.assertFalse(self.store.read_snapshot().exists)

    def test_failed_later_bootstrap_preserves_previous_committed_prefix(self):
        self._commit_prefix(1)
        completed = manager.apply_upgrade(self.store, self._callbacks([], (R1, R2)), (R1, R2))
        manager.stage_upgrade(self.store, completed)
        self.assertEqual(manager.plan_upgrade(self.store, (R1, R2)).applied_ids, (R1, R2))
        self.connection.rollback()
        self.assertEqual(manager.plan_upgrade(self.store, (R1, R2)).applied_ids, (R1,))

    def test_sqlite_staging_explicitly_begins_before_ddl_even_with_no_seed_writes(self):
        self.connection.isolation_level = None
        completed = manager.apply_upgrade(self.store, self._callbacks([], (R1,)), (R1,))
        manager.stage_upgrade(self.store, completed)
        self.assertTrue(self.connection.in_transaction)
        self.connection.rollback()
        self.assertFalse(self.store.read_snapshot().exists)

    @unittest.skipUnless(hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"), "requires sqlite3 Python 3.12 transaction API")
    def test_true_driver_autocommit_cannot_publish_uncontrolled_markers(self):
        self.connection.close()
        self.connection = sqlite3.connect(self.path, autocommit=True)
        self.store = manager.SQLiteLedgerStore(self.connection)
        completed = manager.apply_upgrade(self.store, self._callbacks([], (R1,)), (R1,))
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.stage_upgrade(self.store, completed)
        self.assertFalse(self.store.read_snapshot().exists)

    def test_incomplete_or_changed_history_cannot_be_staged(self):
        completed = manager.apply_upgrade(self.store, self._callbacks([], (R1, R2)), (R1, R2))
        incomplete = manager.CompletedUpgrade(completed.plan, (R1,))
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.stage_upgrade(self.store, incomplete)
        self.assertFalse(self.store.read_snapshot().exists)
        self._commit_prefix(1)
        before = tuple(self.connection.iterdump())
        with self.assertRaises(manager.SchemaCompatibilityError):
            manager.stage_upgrade(self.store, completed)
        self.assertEqual(tuple(self.connection.iterdump()), before)

    def test_missing_callback_rejects_whole_plan_before_first_callback(self):
        calls = []
        with self.assertRaises(ValueError):
            manager.apply_upgrade(self.store, {R1: lambda: calls.append(R1)}, (R1, R2))
        self.assertEqual(calls, [])
        self.assertFalse(self.store.read_snapshot().exists)

    def test_invalid_or_unordered_registry_is_rejected_without_mutations(self):
        for ids in ((), R1, (R1, R1), (R1, "invalid id"), {R1, R2}):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                manager.plan_upgrade(self.store, ids)
        self.assertFalse(self.store.read_snapshot().exists)

    def test_model_shape_validation_detects_missing_tables_and_columns(self):
        manager.validate_schema_shape({"tenant": ("id", "name", "legacy_column")},
                                      {"tenant": ("id", "name")})
        with self.assertRaisesRegex(manager.SchemaCompatibilityError, "missing tables: user"):
            manager.validate_schema_shape({"tenant": ("id",)}, {"user": ("id",)})
        with self.assertRaisesRegex(manager.SchemaCompatibilityError, "tenant.*name"):
            manager.validate_schema_shape({"tenant": ("id",)}, {"tenant": ("id", "name")})


if __name__ == "__main__":
    unittest.main(verbosity=2)
