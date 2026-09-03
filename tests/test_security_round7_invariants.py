from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')


def _function_block(source, name, next_name=None):
    start = source.index(f'def {name}(')
    end = source.index(f'def {next_name}(', start) if next_name else len(source)
    return source[start:end]


def test_db_backed_upload_names_are_revalidated_at_filesystem_boundary():
    block = _function_block(ROUTES, 'safe_upload_path', 'save_action_attachment_file')
    assert "safe = secure_filename(raw)" in block
    assert "Path(raw).name != raw" in block
    assert "path.parent != base" in block
    assert "path.exists()" in block and "path.is_file()" in block


def test_document_and_attachment_downloads_use_safe_upload_path():
    att = _function_block(ROUTES, 'download_action_attachment', 'del_action_attachment')
    doc = _function_block(ROUTES, 'download_doc', 'upload_doc_to_alfresco')
    assert 'send_file(safe_upload_path(att.stored_name)' in att
    assert 'send_file(safe_upload_path(d.stored_name)' in doc
    assert "os.path.join(current_app.config['UPLOAD_DIR']" not in att
    assert "os.path.join(current_app.config['UPLOAD_DIR']" not in doc


def test_attachment_and_document_deletes_cannot_follow_unsafe_db_paths():
    att = _function_block(ROUTES, 'del_action_attachment', 'upload')
    doc = _function_block(ROUTES, 'del_doc', 'update_document_notification_tags')
    assert 'safe_upload_path(att.stored_name).unlink()' in att
    assert 'safe_upload_path(d.stored_name).unlink()' in doc


def test_alfresco_upload_uses_same_safe_local_file_boundary():
    block = _function_block(ROUTES, 'attach_document_to_alfresco', 'make_notification_mail_pdf')
    assert 'safe_upload_path(doc.stored_name)' in block
