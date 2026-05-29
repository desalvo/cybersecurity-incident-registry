from pathlib import Path


def test_description_required_uses_postgresql_boolean_default():
    source = Path('app/__init__.py').read_text()
    assert 'description_required BOOLEAN DEFAULT FALSE NOT NULL' in source
    assert 'description_required BOOLEAN DEFAULT 0 NOT NULL' not in source


def test_user_tenant_role_backfill_happens_after_user_tenant_id_migration():
    source = Path('app/__init__.py').read_text()
    add_column_pos = source.index('Prima di popolare user_tenant_role')
    backfill_pos = source.index('INSERT INTO user_tenant_role')
    assert add_column_pos < backfill_pos
    assert 'FROM "user" AS u' in source
    assert "tenant_expr = 'u.tenant_id'" in source
    assert 'SELECT id, COALESCE(tenant_id' not in source


def test_full_import_clears_bootstrap_rows_before_tenant_restore():
    source = Path('app/routes.py').read_text()
    assert 'def clear_database_rows_for_full_import()' in source
    assert 'TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE' in source
    assert source.count('clear_database_rows_for_full_import()') >= 2
    import_pos = source.index("for row in _deduplicated_tenant_rows(tables.get('tenants', []))")
    clear_pos = source.rindex('clear_database_rows_for_full_import()', 0, import_pos)
    assert clear_pos < import_pos


def test_full_import_deduplicates_default_tenant_and_legacy_memberships():
    source = Path('app/routes.py').read_text()
    assert 'def _deduplicated_tenant_rows(rows):' in source
    assert "key = name.lower()" in source
    assert "if key in seen_names" in source
    assert "out.append({'id': 1, 'name': 'default'" in source
    assert 'def _deduplicated_user_tenant_role_rows' in source
    assert "key = (coerced.get('user_id'), coerced.get('tenant_id'))" in source


def test_full_import_audit_purge_does_not_touch_current_user_after_session_reset():
    source = Path('app/routes.py').read_text()
    assert 'def _setting_value_without_request_user' in source
    assert 'def purge_audit_logs_without_request_user' in source
    import_block = source[source.index('def import_full():'):source.index('def _stats_incidents_for_range')]
    rebuild_pos = import_block.index('rebuild_database_for_full_import()')
    safe_purge_pos = import_block.index('purge_audit_logs_without_request_user(import_default_tenant_id)')
    assert rebuild_pos < safe_purge_pos
    after_rebuild = import_block[rebuild_pos:]
    assert 'purge_audit_logs()' not in after_rebuild
    helper_block = source[source.index('def _setting_value_without_request_user'):source.index('def purge_audit_logs(commit=False):')]
    assert 'getattr(current_user' not in helper_block
    assert 'current_user,' not in helper_block
    assert 'current_tenant_id(default' not in helper_block
    assert 'tenant_setting_key(' not in helper_block
    assert ' setting_value(' not in helper_block


def test_full_import_realigns_sequences_after_restore_commit():
    source = Path('app/routes.py').read_text()
    import_block = source[source.index('def import_full():'):source.index('def _stats_incidents_for_range')]
    commit_pos = import_block.index('db.session.commit()\n            # Dopo il restore con ID espliciti')
    align_pos = import_block.index('align_all_table_sequences()', commit_pos)
    assert commit_pos < align_pos
    assert 'prima operazione successiva, ad esempio la creazione di un tenant' in import_block


def test_tenant_clone_realigns_sequences_before_copying_configuration():
    source = Path('app/routes.py').read_text()
    tenant_create_block = source[source.index("if action == 'create':"):source.index("if action == 'update':")]
    assert 'align_all_table_sequences()' in tenant_create_block
    assert 'commit_with_sequence_retry([' in tenant_create_block
    clone_block = source[source.index('def clone_tenant_config('):source.index('@bp.route(\'/admin/tenants\'')]
    assert 'align_all_table_sequences()' in clone_block
    copy_label_block = source[source.index('def _copy_label_to_tenant('):source.index('def _copy_or_update_label_to_tenant(')]
    assert "align_table_sequence('config_label')" not in copy_label_block
    assert 'più volte nello stesso restore/clone prima del commit' in copy_label_block


def test_sequence_alignment_uses_current_session_connection():
    source = Path('app/routes.py').read_text()
    align_block = source[source.index('def align_table_sequence('):source.index('def sequence_managed_table_names(')]
    assert 'db.session.connection()' in align_block
    assert 'db.engine.begin()' not in align_block
    assert 'MAX(id)' in align_block
    assert 'già flushate ma non ancora committate' in align_block
