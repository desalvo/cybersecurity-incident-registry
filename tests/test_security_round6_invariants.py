from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')
MODELS = (ROOT / 'app' / 'models.py').read_text(encoding='utf-8')
APP_INIT = (ROOT / 'app' / '__init__.py').read_text(encoding='utf-8')
REQS = (ROOT / 'requirements.txt').read_text(encoding='utf-8')


def _function_block(source, name, next_name=None):
    start = source.index(f'def {name}(')
    if next_name:
        end = source.index(f'def {next_name}(', start)
    else:
        end = len(source)
    return source[start:end]


def test_full_import_database_rebuild_is_transactional():
    block = _function_block(ROUTES, 'rebuild_database_for_full_import', 'clear_database_rows_for_full_import')
    assert 'db.metadata.drop_all(bind=connection)' in block
    assert 'db.metadata.create_all(bind=connection)' in block
    assert 'db.session.commit()' not in block
    assert 'db.drop_all()' not in block
    assert 'db.create_all()' not in block


def test_full_import_filesystem_has_reversible_staging():
    assert 'class _FullImportFilesystemTransaction' in ROUTES
    assert 'fs_txn = _FullImportFilesystemTransaction(archive, data)' in ROUTES
    assert 'fs_txn.stage()' in ROUTES
    assert 'fs_txn.activate()' in ROUTES
    assert 'fs_txn.finalize()' in ROUTES
    assert 'fs_txn.rollback()' in ROUTES
    assert "os.replace(base, backup)" in ROUTES
    assert "os.replace(stage, base)" in ROUTES


def test_full_import_is_serialized_across_workers():
    assert 'pg_try_advisory_lock(:lock_id)' in ROUTES
    assert '_CIR_FULL_IMPORT_LOCK_ID' in ROUTES
    block = _function_block(ROUTES, 'import_full', '_stats_incidents_for_range')
    assert '_acquire_full_import_execution_lock()' in block
    assert '_release_full_import_execution_lock(import_lock)' in block


def test_import_payload_is_validated_before_restore():
    block = _function_block(ROUTES, 'validate_full_import_payload', 'validate_password_strength')
    assert "stored_name duplicato" in block
    assert "azione riferita a incidente inesistente" in block
    assert "allegato riferito ad azione inesistente" in block
    import_block = _function_block(ROUTES, 'import_full', '_stats_incidents_for_range')
    assert import_block.index('validate_full_import_payload(data)') < import_block.index('rebuild_database_for_full_import()')


def test_tenant_import_files_are_removed_on_db_failure():
    assert 'created_files=None' in ROUTES
    assert 'created_files.append(target)' in ROUTES
    block = _function_block(ROUTES, 'import_full', '_stats_incidents_for_range')
    assert 'tenant_created_files = []' in block
    assert 'Path(created_path).unlink(missing_ok=True)' in block


def test_child_ownership_constraints_are_strict_on_new_schema():
    assert "ForeignKey('incident.id', ondelete='CASCADE'),nullable=False" in MODELS
    assert "ForeignKey('action.id', ondelete='CASCADE'),nullable=False" in MODELS


def test_existing_postgres_schema_gets_safe_ownership_hardening():
    assert "ownership_fks = [" in APP_INIT
    assert "NULL/orphan rows require manual repair" in APP_INIT
    assert 'ALTER COLUMN \"{child_col}\" SET NOT NULL' in APP_INIT
    assert "ON DELETE CASCADE" in APP_INIT


def test_runtime_server_and_werkzeug_pins_are_supported_round6_versions():
    assert 'gunicorn==26.2.0' in REQS
    assert 'Werkzeug==3.1.8' in REQS


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_') and callable(value)]
    for test in tests:
        test()
        print('PASS', test.__name__)
