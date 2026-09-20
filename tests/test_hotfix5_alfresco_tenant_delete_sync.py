from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLIENT=(ROOT/'app/plugins/alfresco/client.py').read_text(encoding='utf-8')
ROUTES=(ROOT/'app/routes.py').read_text(encoding='utf-8')
MODELS=(ROOT/'app/models.py').read_text(encoding='utf-8')
INIT=(ROOT/'app/__init__.py').read_text(encoding='utf-8')
TPL=(ROOT/'app/templates/incident_detail.html').read_text(encoding='utf-8')
ADMIN=(ROOT/'app/plugins/alfresco/templates/alfresco_admin_plugins.html').read_text(encoding='utf-8')
README=(ROOT/'README.md').read_text(encoding='utf-8')

def test_alfresco_config_is_strictly_tenant_scoped():
    assert "def _tenant_alfresco_setting" in CLIENT
    assert "physical = f'tenant:{int(tid)}:{key}'" in CLIENT
    assert "if int(tid) == int(default_tenant().id)" in CLIENT

def test_document_has_remote_status_fields_and_migration():
    assert 'alfresco_status=db.Column' in MODELS
    assert 'alfresco_checked_at=db.Column' in MODELS
    assert "'alfresco_status': \"VARCHAR(20) DEFAULT 'not_linked' NOT NULL\"" in INIT

def test_client_supports_read_only_status_and_delete():
    assert 'def node_status(node_id):' in CLIENT
    assert 'def delete_file(node_id, permanent=False):' in CLIENT
    node_block=CLIENT[CLIENT.index('def node_status'):CLIENT.index('def delete_file')]
    assert 'requests.get' in node_block
    assert 'requests.post' not in node_block and 'requests.put' not in node_block and 'requests.delete' not in node_block

def test_incident_sync_does_not_upload():
    block=ROUTES[ROUTES.index('def sync_incident_alfresco_documents'):ROUTES.index("@bp.route('/document/<int:did>/delete'", ROUTES.index('def sync_incident_alfresco_documents'))]
    assert 'node_status' in block
    assert 'attach_document' not in block and 'upload_file' not in block
    assert "alfresco:incident_documents_sync" in block

def test_remote_delete_route_keeps_document_record():
    block=ROUTES[ROUTES.index('def delete_doc_from_alfresco'):ROUTES.index("@bp.route('/incident/<int:iid>/alfresco/sync-documents'", ROUTES.index('def delete_doc_from_alfresco'))]
    assert 'delete_file' in block
    assert 'db.session.delete(d)' not in block
    assert "d.alfresco_status = 'missing'" in block

def test_incident_documents_ui_has_sync_and_remote_delete():
    assert 'Sync Alfresco' in TPL
    assert 'delete_doc_from_alfresco' in TPL
    assert 'sync_incident_alfresco_documents' in TPL

def test_admin_docs_explain_tenant_scope_and_sync():
    assert 'Tenant configurato:' in ADMIN
    assert 'configurazione' in ADMIN.lower() and 'tenant' in ADMIN.lower()
    assert 'Sync Alfresco' in README
    assert 'sola lettura' in README.lower()
