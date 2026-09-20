from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')
CLIENT = (ROOT / 'app/plugins/alfresco/client.py').read_text(encoding='utf-8')
DETAIL = (ROOT / 'app/templates/incident_detail.html').read_text(encoding='utf-8')
ADMIN = (ROOT / 'app/plugins/alfresco/templates/alfresco_admin_plugins.html').read_text(encoding='utf-8')


def _assignment_literal(source, name):
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return ast.literal_eval(node.value)


def test_zip_and_gzip_are_allowed_with_magic_validation():
    allowed = _assignment_literal(ROUTES, '_ALLOWED_UPLOAD_EXTENSIONS')
    magic = _assignment_literal(ROUTES, '_ALLOWED_UPLOAD_MAGIC')
    assert '.zip' in allowed and '.gz' in allowed
    assert b'PK\x03\x04' in magic['.zip']
    assert b'\x1f\x8b' in magic['.gz']


def test_document_upload_exposes_local_both_and_alfresco_only_modes():
    assert 'name="storage_mode"' in DETAIL
    assert 'value="local"' in DETAIL
    assert 'value="both"' in DETAIL
    assert 'value="alfresco"' in DETAIL
    assert "storage_mode in {'both', 'alfresco'}" in ROUTES
    assert "stored_name=None" in ROUTES
    assert 'cir-alfresco-upload-' in ROUTES


def test_remote_only_documents_fallback_to_alfresco_download_and_no_reupload_button():
    assert "if d.alfresco_node_id and alfresco_is_enabled_safe()" in ROUTES
    assert "download_doc_from_alfresco" in ROUTES
    assert "and d.stored_name" in DETAIL
    assert 'Solo Alfresco' in DETAIL


def test_alfresco_always_groups_by_incident_and_can_group_by_file_type():
    assert 'incident_folder_name(incident_id, incident_name)' in CLIENT
    assert "def _document_type_folder" in CLIENT
    assert "'archives'" in CLIENT
    assert "'.zip', '.gz'" in CLIENT
    assert "cfg.get('group_by_type')" in CLIENT
    assert 'alfresco_group_by_type' in ADMIN


def test_group_by_type_is_configurable_and_enabled_by_default():
    assert "'group_by_type': '1'" in CLIENT
    plugin_routes = (ROOT / 'app/plugins/alfresco/routes.py').read_text(encoding='utf-8')
    assert "alfresco_group_by_type" in plugin_routes
    assert "'alfresco_group_by_type'" in ROUTES
