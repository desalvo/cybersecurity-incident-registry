"""Exercise the actual SQLite DDL with sqlite3, including refusal/rollback."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest


_path = Path(__file__).resolve().parents[1] / 'app' / 'tenant_defaults_migrations.py'
_spec = importlib.util.spec_from_file_location('cir_recipient_migration_under_test', _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
migrate = _module._sqlite_allow_recipient_copies


class RecipientIdentityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('CREATE TABLE tenant(id INTEGER PRIMARY KEY)')
        self.connection.executemany('INSERT INTO tenant VALUES (?)', [(1,), (2,)])
        self.connection.execute('''CREATE TABLE external_recipient (
            id INTEGER PRIMARY KEY, tenant_id INTEGER REFERENCES tenant(id),
            name VARCHAR(160) NOT NULL, email VARCHAR(255) NOT NULL, notes TEXT,
            created_at DATETIME, updated_at DATETIME,
            CONSTRAINT uq_external_recipient_tenant_email UNIQUE(tenant_id,email))''')
        self.connection.execute('CREATE INDEX recipient_custom_notes ON external_recipient(notes)')
        self.connection.execute("INSERT INTO external_recipient VALUES (41,1,'Local','desk@example.test','Preserve notes','2026-11-01','2026-11-02')")
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_preserves_existing_rows_keys_indexes_and_allows_independent_addresses(self):
        before = self.connection.execute('SELECT * FROM external_recipient').fetchall()
        self.assertTrue(migrate(self.connection))
        self.assertEqual(before, self.connection.execute('SELECT * FROM external_recipient').fetchall())
        self.connection.execute("INSERT INTO external_recipient(tenant_id,name,email) VALUES (1,'Shared','desk@example.test')")
        self.connection.commit()
        ids = [row[0] for row in self.connection.execute('SELECT id FROM external_recipient')]
        self.assertEqual(len(set(ids)), 2)
        self.assertIn(41, ids)
        self.assertIn('recipient_custom_notes', {row[1] for row in self.connection.execute('PRAGMA index_list(external_recipient)')})
        self.assertEqual([], self.connection.execute('PRAGMA foreign_key_check').fetchall())
        self.assertFalse(migrate(self.connection))

    def test_unknown_columns_are_rejected_before_any_change(self):
        self.connection.execute('ALTER TABLE external_recipient ADD COLUMN custom_value TEXT')
        self.connection.commit()
        with self.assertRaisesRegex(RuntimeError, 'Schema'):
            migrate(self.connection)
        self.assertEqual(1, self.connection.execute('SELECT count(*) FROM external_recipient').fetchone()[0])
        self.assertIn('custom_value', {row[1] for row in self.connection.execute('PRAGMA table_info(external_recipient)')})

    def test_trigger_is_not_silently_dropped(self):
        self.connection.execute('CREATE TRIGGER custom_recipient_trigger AFTER INSERT ON external_recipient BEGIN SELECT 1; END')
        self.connection.commit()
        with self.assertRaisesRegex(RuntimeError, 'Trigger'):
            migrate(self.connection)
        self.assertIsNotNone(self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='custom_recipient_trigger'").fetchone())

    def test_inbound_custom_foreign_key_blocks_rebuild(self):
        self.connection.execute('CREATE TABLE custom_reference(id INTEGER REFERENCES external_recipient(id))')
        self.connection.execute('INSERT INTO custom_reference VALUES (41)')
        self.connection.commit()
        with self.assertRaisesRegex(RuntimeError, 'Riferimenti'):
            migrate(self.connection)
        self.assertEqual([(41,)], self.connection.execute('SELECT id FROM custom_reference').fetchall())

    def test_ddl_error_rolls_back_without_dropping_original(self):
        self.connection.execute('CREATE TABLE __cir_recipient_identity_migration(sentinel TEXT)')
        self.connection.commit()
        with self.assertRaises(sqlite3.OperationalError):
            migrate(self.connection)
        self.assertEqual([(41,)], self.connection.execute('SELECT id FROM external_recipient').fetchall())
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO external_recipient(tenant_id,name,email) VALUES (1,'Duplicate','desk@example.test')")


if __name__ == '__main__':
    unittest.main()
