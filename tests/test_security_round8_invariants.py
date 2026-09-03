from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')


def _function_block(source, name, next_name=None):
    start = source.index(f'def {name}(')
    end = source.index(f'def {next_name}(', start) if next_name else len(source)
    return source[start:end]


def test_email_document_attachments_revalidate_db_stored_names():
    block = _function_block(ROUTES, 'send_notification_email', 'send_smtp_test_email')
    assert 'path = safe_upload_path(doc.stored_name)' in block
    assert "os.path.join(current_app.config['UPLOAD_DIR'], doc.stored_name" not in block


def test_full_backup_export_uses_safe_upload_boundary():
    block = _function_block(ROUTES, 'build_full_export_archive_for_backup', 'build_backup_archive')
    assert "src = safe_upload_path(doc['stored_name'])" in block
    assert "src = safe_upload_path(att['stored_name'])" in block
    assert "os.path.join(current_app.config['UPLOAD_DIR'], doc['stored_name'])" not in block
    assert "os.path.join(current_app.config['UPLOAD_DIR'], att['stored_name'])" not in block


def test_general_export_uses_safe_upload_boundary():
    block = _function_block(ROUTES, 'export_full', 'import_csv')
    assert "src = safe_upload_path(doc['stored_name'])" in block
    assert "src = safe_upload_path(att['stored_name'])" in block


def test_public_logo_is_confined_to_managed_logo_directory():
    helper = _function_block(ROUTES, 'safe_logo_path', 'save_action_attachment_file')
    route = _function_block(ROUTES, 'logo_image', 'admin_logo')
    assert "base = Path(current_app.config['LOGO_DIR']).resolve()" in helper
    assert 'path.parent != base' in helper
    assert "path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}" in helper
    assert 'safe_logo_path(setting.value if setting else' in route
    assert 'send_file(path)' in route


def test_logo_delete_and_exports_do_not_trust_setting_path_directly():
    admin = _function_block(ROUTES, 'admin_logo', 'mfa_verify')
    full = _function_block(ROUTES, 'build_full_export_archive_for_backup', 'build_backup_archive')
    export = _function_block(ROUTES, 'export_full', 'import_csv')
    assert 'path = safe_logo_path(setting.value)' in admin
    assert "os.remove(setting.value)" not in admin
    assert 'managed_logo = safe_logo_path' in full
    assert 'archive.add(logo_setting.value' not in full
    assert 'managed_logo = safe_logo_path' in export
    assert 'archive.add(logo_setting.value' not in export


def test_document_generation_errors_are_not_reflected_verbatim():
    assert "Errore generazione anteprima {template_name}: {exc}" not in ROUTES
    assert "Analisi del PDF fallita: {exc}" not in ROUTES
    assert "Salvataggio template fallito: {exc}" not in ROUTES
    assert 'Consultare i log amministrativi.' in ROUTES


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_') and callable(value)]
    for test in tests:
        test()
        print('PASS', test.__name__)
