"""Real startup upgrades from the packaged RC16 ORM schema.

The fixture is the byte-for-byte historical models.py, not a current schema
with selected fields removed and not a production database dump. Its separate
SQLAlchemy metadata creates actual legacy SQLite/PostgreSQL tables; every
upgrade and restart then uses the current application's create_app().
"""
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, time
from functools import lru_cache
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/rc16_schema'
LEGACY_PASSWORD = 'RetainedRC16Admin123!'
NEXT_INITIAL_PASSWORD = 'MustNotReplaceExistingPassword123!'
STORAGE = ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
           'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR')


@lru_cache(maxsize=1)
def _legacy_metadata():
    provenance = json.loads((FIXTURE / 'PROVENANCE.json').read_text())
    source = FIXTURE / 'models.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == provenance['source_member_sha256']
    assert provenance['functional_version'] == '0.9.0-1'
    assert provenance['build'] == '20260902'
    # Only the utility relative import uses the current package. The historical
    # module owns a separate SQLAlchemy instance and its original metadata.
    name = 'app._rc16_upgrade_fixture'
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.db.metadata


@contextmanager
def _configured_environment(directory, url):
    with patch.dict(os.environ):
        values = {
            'DATABASE_URL': url, 'SECRET_KEY': 'upgrade-integration-' + 's' * 64,
            'SETTING_ENCRYPTION_KEY': 'upgrade-integration-' + 'e' * 64,
            'ADMIN_INITIAL_PASSWORD': NEXT_INITIAL_PASSWORD,
            'CIR_DISABLE_BACKGROUND_SCHEDULERS': '1', 'CIR_DISABLE_CSRF': '0',
            'SESSION_COOKIE_SECURE': '0', 'CIR_PRODUCTION': '0', 'FLASK_ENV': 'development',
            # A retained deployment can still carry old metadata overrides.
            # Current image VERSION/BUILD must win throughout the upgrade.
            'APP_VERSION': '0.9.0-1', 'APP_BUILD': '20260902',
        }
        for name in ('DATABASE_URL', 'SECRET_KEY', 'SETTING_ENCRYPTION_KEY', 'ADMIN_INITIAL_PASSWORD'):
            os.environ.pop(name + '_FILE', None)
        for name in STORAGE:
            path = directory / name.lower()
            path.mkdir(parents=True, exist_ok=True)
            values[name] = str(path)
        os.environ.update(values)
        yield


def _seed_rc16(engine, ui_mode=None):
    from app.auth import hash_password
    from pypdf import PdfWriter

    metadata = _legacy_metadata()
    metadata.create_all(engine)
    before = inspect(engine)
    assert 'is_system_defaults' not in {row['name'] for row in before.get_columns('tenant')}
    assert 'owner_tenant_id' not in {row['name'] for row in before.get_columns('form_template_config')}
    assert 'cir_schema_migrations' not in before.get_table_names()
    password_hash = hash_password(LEGACY_PASSWORD)
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(pdf)
    rows = {
        'tenant': [dict(id=5, name='default', description='Existing deployment'),
                   dict(id=9, name='retained-tenant', description='Keep tenant identity')],
        'user': [dict(id=7, username='admin', name='Existing Administrator',
                      email='existing-admin@example.invalid', role='superuser',
                      auth_provider='local', is_ldap=False, tenant_id=5,
                      password_hash=password_hash)],
        'user_tenant_role': [dict(id=81, user_id=7, tenant_id=5, role='superuser')],
        'config_label': [
            dict(id=11, tenant_id=5, kind='category', value='Retained incident type', description='Keep category'),
            dict(id=12, tenant_id=5, kind='severity', value='Retained custom severity', description='Keep severity'),
            dict(id=13, tenant_id=5, kind='action_label', value='08-conclusione',
                 description='Custom conclusion: no automatic close', automatic_operations='', default_exportable=False),
        ],
        'incident_workflow_step': [dict(id=17, tenant_id=5, category_id=11,
                                       action_label_id=13, position=1, required=True,
                                       description='Keep required custom conclusion', step_type='registration')],
        'notification_type': [dict(id=21, tenant_id=5, code='rc16_notice', label='Retained notice')],
        'form_template_config': [dict(id=31, template_name='rc16-retained-template',
                                     font_family='Times-Roman', font_size=12, notification_tags='rc16_notice')],
        'form_template_binary': [dict(id=32, template_name='rc16-retained-template',
                                     filename='rc16-retained-template.pdf', pdf_data=pdf.getvalue())],
        'notification_template': [dict(id=33, tenant_id=5, kind='rc16_notice', name='Retained notification',
                                       subject='Keep subject', body='Keep body', action_label_id=13,
                                       linked_form_template_name='rc16-retained-template')],
        'incident': [dict(id=51, tenant_id=5, creator_id=7, name='Retained RC16 incident', reference='RC16-51',
                          description='Retained operational data', severity_id=12, category_order='11',
                          start_date=date(2026, 10, 1), start_time=time(12, 30), status='aperto')],
        'action': [dict(id=61, incident_id=51, when_at=datetime(2026, 10, 1, 13),
                        person_name='Existing operator', description='Retained action', label_id=13)],
        'document': [dict(id=62, incident_id=51, filename='retained.txt', stored_name='retained-evidence.txt')],
        'setting': [dict(key='tenant:5:structure_name', value='Retained organization'),
                    dict(key='tenant:9:structure_name', value='Retained second tenant')],
        'incident_categories': [dict(incident_id=51, label_id=11)],
    }
    if ui_mode is not None:
        rows['setting'].append(dict(key='global_ui_mode', value=ui_mode))
    with engine.begin() as conn:
        for name, values in rows.items():
            for row in values:
                conn.execute(metadata.tables[name].insert(), row)
    evidence = Path(os.environ['UPLOAD_DIR']) / 'retained-evidence.txt'
    evidence.write_bytes(b'Existing incident evidence must survive an automatic upgrade.\n')
    return {'password_hash': password_hash, 'evidence': evidence.read_bytes(), 'pdf': pdf.getvalue()}


def _ledger_rows(engine):
    from app.migration_manager import LEDGER_TABLE
    if not inspect(engine).has_table(LEDGER_TABLE):
        return []
    with engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(
            'SELECT position, revision_id, applied_at FROM cir_schema_migrations ORDER BY position'))]


def _dispose_application(app):
    from app.models import db
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _snapshot(app, seed, expected_ui='modern'):
    from release_metadata import read_release_metadata
    from app.auth import verify_password
    from app.models import (ConfigLabel, Document, FormTemplateBinary, FormTemplateConfig,
                            Incident, IncidentWorkflowStep, NotificationTemplate, Setting, Tenant, User, db)
    from app.ui_settings import global_ui_mode
    from app.migration_manager import SCHEMA_REVISIONS
    release = read_release_metadata(ROOT)
    assert app.config['APP_INFO']['version'] == release.version
    assert app.config['APP_INFO']['build'] == release.build
    with app.app_context():
        admin = db.session.get(User, 7)
        assert admin.password_hash == seed['password_hash']
        assert verify_password(admin.password_hash, LEGACY_PASSWORD)
        assert not verify_password(admin.password_hash, NEXT_INITIAL_PASSWORD)
        assert admin.name == 'Existing Administrator'
        assert admin.email == 'existing-admin@example.invalid'
        assert db.session.get(Tenant, 5).name == 'default'
        assert db.session.get(Tenant, 9).name == 'retained-tenant'
        defaults = Tenant.query.filter_by(is_system_defaults=True).all()
        assert len(defaults) == 1
        assert defaults[0].id not in {5, 9}
        incident = db.session.get(Incident, 51)
        assert (incident.name, incident.reference, incident.severity_id) == ('Retained RC16 incident', 'RC16-51', 12)
        assert [label.id for label in incident.categories] == [11]
        assert [action.id for action in incident.actions] == [61]
        assert db.session.get(Document, 62).stored_name == 'retained-evidence.txt'
        assert db.session.get(ConfigLabel, 13).automatic_operations == ''
        assert db.session.get(IncidentWorkflowStep, 17).required is True
        assert db.session.get(NotificationTemplate, 33).action_label_id == 13
        assert db.session.get(FormTemplateConfig, 31).font_size == 12
        assert db.session.get(FormTemplateBinary, 32).pdf_data == seed['pdf']
        assert db.session.get(Setting, 'tenant:5:structure_name').value == 'Retained organization'
        assert db.session.get(Setting, 'tenant:9:structure_name').value == 'Retained second tenant'
        assert global_ui_mode() == expected_ui
        ledger = _ledger_rows(db.engine)
        assert [row[1] for row in ledger] == list(SCHEMA_REVISIONS)
        assert 'cir_schema_migrations' not in db.metadata.tables
        counts = {name: db.session.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one()
                  for name in ('tenant', 'user', 'config_label', 'incident_workflow_step', 'tenant_workflow')}
        snapshot = {'ledger': ledger, 'counts': counts, 'defaults_id': defaults[0].id}
        db.session.remove()
        db.engine.dispose()
    assert (Path(os.environ['UPLOAD_DIR']) / 'retained-evidence.txt').read_bytes() == seed['evidence']
    assert (Path(os.environ['FORM_TEMPLATE_DIR']) / 'rc16-retained-template.pdf').read_bytes() == seed['pdf']
    return snapshot


def _upgrade_twice(engine, ui_mode=None):
    import app as application
    seed = _seed_rc16(engine, ui_mode)
    first = application.create_app()
    snapshot = _snapshot(first, seed, ui_mode or 'modern')

    def already_applied(_app):
        raise AssertionError('An already stamped schema migration ran again on restart')

    with patch.object(application, 'run_schema_migrations', already_applied):
        restarted = application.create_app()
        assert _snapshot(restarted, seed, ui_mode or 'modern') == snapshot


class AutomaticUpgradeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='cir-upgrade-test-')))
        url = 'sqlite:///' + str(self.directory / 'rc16.sqlite')
        self.stack.enter_context(_configured_environment(self.directory, url))
        self.engine = create_engine(url)
        self.stack.callback(self.engine.dispose)

    def test_rc16_upgrade_and_restart_preserve_data_and_select_modern_without_saved_choice(self):
        _upgrade_twice(self.engine)

    def test_rc16_upgrade_and_restart_preserve_an_explicit_classic_choice(self):
        _upgrade_twice(self.engine, 'classic')

    def test_failed_bootstrap_does_not_stamp_schema_and_next_start_retries(self):
        import app as application
        from app import tenant_defaults
        seed = _seed_rc16(self.engine)

        def interrupted_bootstrap(*_args, **_kwargs):
            raise RuntimeError('Injected failure before final bootstrap commit')

        with patch.object(tenant_defaults, 'sync_defaults_configuration', interrupted_bootstrap):
            with self.assertRaisesRegex(RuntimeError, 'Injected failure'):
                application.create_app()
        self.assertEqual(_ledger_rows(self.engine), [])
        _snapshot(application.create_app(), seed)

    def test_ahead_schema_is_rejected_before_full_import_recovery(self):
        from app import create_app, routes
        from app.models import Setting, db
        from app.migration_manager import SchemaCompatibilityError
        _seed_rc16(self.engine)
        current = create_app()
        self.addCleanup(_dispose_application, current)
        token = 'a' * 32
        with current.app_context():
            ledger = _ledger_rows(db.engine)
            db.session.add(Setting(key=routes._FULL_IMPORT_COMMIT_MARKER_KEY, value=token))
            db.session.execute(text('INSERT INTO cir_schema_migrations (position, revision_id, applied_at) '
                                    'VALUES (:position, :revision, :applied)'),
                               {'position': ledger[-1][0] + 1, 'revision': '20990101_01_future_schema',
                                'applied': '2099-01-01T00:00:00+00:00'})
            db.session.commit()
            routes._write_full_import_journal({'version': routes._FULL_IMPORT_JOURNAL_VERSION,
                                               'token': token, 'created_at': '2026-11-22T00:00:00+00:00',
                                               'groups': {'uploads': {'had_original': True, 'state': 'promoted'}}})
        journal = Path(os.environ['BACKUP_DIR']) / '.cir-full-import-restore-journal.json'
        journal_before = journal.read_bytes()
        ledger_before = _ledger_rows(self.engine)
        with self.assertRaises(SchemaCompatibilityError):
            create_app()
        self.assertEqual(_ledger_rows(self.engine), ledger_before)
        self.assertEqual(journal.read_bytes(), journal_before)
        with self.engine.connect() as conn:
            marker = conn.execute(text('SELECT value FROM setting WHERE key = :key'),
                                  {'key': routes._FULL_IMPORT_COMMIT_MARKER_KEY}).scalar_one()
            self.assertEqual(marker, token)

    def test_stamped_schema_drift_is_not_silently_recreated(self):
        from app import create_app
        from app.models import FormTemplateConfig
        from app.migration_manager import SchemaCompatibilityError
        _seed_rc16(self.engine)
        current = create_app()
        self.addCleanup(_dispose_application, current)
        ledger = _ledger_rows(self.engine)
        FormTemplateConfig.__table__.drop(self.engine)
        with self.assertRaises(SchemaCompatibilityError):
            create_app()
        self.assertFalse(inspect(self.engine).has_table('form_template_config'))
        self.assertEqual(_ledger_rows(self.engine), ledger)

    def test_full_import_recreates_application_schema_without_losing_ledger(self):
        import app as application
        from app.models import Setting, db
        from app.routes import build_full_export_archive_for_backup
        seed = _seed_rc16(self.engine, 'classic')
        current = application.create_app()
        before = _snapshot(current, seed, 'classic')
        with current.app_context():
            archive = Path(build_full_export_archive_for_backup(prefix='upgrade-ledger-regression'))
            try:
                contents = archive.read_bytes()
            finally:
                archive.unlink(missing_ok=True)
            with tarfile.open(fileobj=io.BytesIO(contents), mode='r:gz') as exported:
                payload = json.load(exported.extractfile('export.json'))
            self.assertNotIn('cir_schema_migrations', payload['tables'])
            db.session.get(Setting, 'tenant:5:structure_name').value = 'Changed after backup'
            db.session.commit()
        client = current.test_client()
        login = client.get('/login')
        token = re.search(r'name="_csrf_token" value="([^"]+)"', login.get_data(as_text=True)).group(1)
        response = client.post('/login', data={'username': 'admin', 'password': LEGACY_PASSWORD, '_csrf_token': token})
        self.assertIn(response.status_code, {302, 303})
        form = client.get('/import/full')
        token = re.search(r'name="_csrf_token" value="([^"]+)"', form.get_data(as_text=True)).group(1)
        response = client.post('/import/full', data={'_csrf_token': token,
                               'file': (io.BytesIO(contents), 'rc16-upgraded-export.tar.gz')},
                               content_type='multipart/form-data')
        self.assertIn(response.status_code, {302, 303}, response.get_data(as_text=True))
        self.assertEqual(_snapshot(current, seed, 'classic'), before)

        def already_applied(_app):
            raise AssertionError('Full import incorrectly erased the installation migration ledger')

        with patch.object(application, 'run_schema_migrations', already_applied):
            self.assertEqual(_snapshot(application.create_app(), seed, 'classic'), before)


class AutomaticUpgradeEntrypointTests(unittest.TestCase):
    def test_container_migrates_after_privilege_drop_before_starting_gunicorn(self):
        entrypoint = (ROOT / 'docker-entrypoint.sh').read_text()
        command = re.search(r'(?m)^\s*(?:exec\s+)?python(?:3)?\s+-m\s+app\.migrate\b', entrypoint)
        self.assertIsNotNone(command, 'Container startup must invoke the automatic migration preflight')
        self.assertLess(entrypoint.index('exec gosu "${APP_USER}" "$0" --as-appuser'), command.start())
        listener_start = re.search(r'(?m)^start_http\s*$', entrypoint)
        self.assertIsNotNone(listener_start)
        self.assertLess(command.start(), listener_start.start())
        wait_block = entrypoint[command.end():listener_start.start()]
        self.assertIn('if wait "$MIGRATION_PID"; then', wait_block)
        self.assertIn('exit 1', wait_block)
        self.assertIn('set -eu', entrypoint[:100])


if __name__ == '__main__':
    unittest.main()
