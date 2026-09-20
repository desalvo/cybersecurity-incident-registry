from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = (ROOT / 'app' / 'plugins' / 'alfresco' / 'client.py').read_text(encoding='utf-8')
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')
ADMIN = (ROOT / 'app' / 'plugins' / 'alfresco' / 'templates' / 'alfresco_admin_plugins.html').read_text(encoding='utf-8')
DOC = (ROOT / 'docs' / 'ADMIN_ALFRESCO.md').read_text(encoding='utf-8')


def test_incident_folder_uses_id_and_name():
    assert 'def incident_folder_name(incident_id, incident_name=None):' in CLIENT
    assert "return f'incident-{iid} - {raw}'" in CLIENT
    assert 'incident_folder_name(incident_id, incident_name)' in CLIENT


def test_document_upload_passes_current_incident_name():
    assert 'incident_name=(inc.name if inc else None)' in ROUTES


def test_report_filename_uses_incident_name():
    assert 'def incident_report_filename(incident_id, incident_name=None):' in CLIENT
    assert "incident_report_filename(inc.id, inc.name)" in ROUTES
    assert 'incident_name=inc.name' in ROUTES


def test_incident_name_is_sanitized_for_alfresco_path():
    assert "unicodedata.normalize('NFKC'" in CLIENT
    assert "re.sub(r'[\\\\/:*?\"<>|]+'" in CLIENT
    assert "raw[:110]" in CLIENT


def test_admin_docs_describe_readable_names():
    assert 'incident-42 - Phishing account amministratore' in ADMIN
    assert 'incident-42 - Phishing account amministratore - report.pdf' in DOC
