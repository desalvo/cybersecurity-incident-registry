from pathlib import Path


def test_alfresco_plugin_files_and_registration_exist():
    init = Path('app/__init__.py').read_text(encoding='utf-8')
    assert 'register_alfresco_plugin' in init
    assert Path('app/plugins/alfresco/client.py').exists()
    assert Path('app/plugins/alfresco/routes.py').exists()
    assert Path('app/plugins/alfresco/templates/alfresco_admin_plugins.html').exists()


def test_alfresco_plugin_is_disabled_by_default_and_has_reset():
    client = Path('app/plugins/alfresco/client.py').read_text(encoding='utf-8')
    routes = Path('app/plugins/alfresco/routes.py').read_text(encoding='utf-8')
    template = Path('app/plugins/alfresco/templates/alfresco_admin_plugins.html').read_text(encoding='utf-8')
    assert "'enabled': '0'" in client
    assert 'def is_enabled' in client
    assert 'def upload_file' in client
    assert 'def download_file' in client
    assert 'reset_alfresco_defaults' in routes
    assert 'Reset configurazione Alfresco' in template
    assert 'Il valore reale non viene visualizzato' in template


def test_incident_documents_expose_alfresco_actions_only_when_enabled():
    detail = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    models = Path('app/models.py').read_text(encoding='utf-8')
    assert 'alfresco_plugin_enabled()' in detail
    assert 'Carica anche su Alfresco' in detail
    assert 'Download Alfresco' in detail
    assert 'Invia ad Alfresco' in detail
    assert 'def attach_document_to_alfresco' in routes
    assert 'def upload_doc_to_alfresco' in routes
    assert 'def download_doc_from_alfresco' in routes
    assert 'alfresco_node_id' in models
    assert 'alfresco_path' in models
    assert 'alfresco_uploaded_at' in models


def test_alfresco_password_is_secret_setting_and_documented():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    assert "'alfresco_password'" in routes
    assert 'Plugin Alfresco' in readme
    assert 'disabilitato per default' in readme
