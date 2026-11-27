"""Regression contracts for documentary sample Support Tickets screenshot."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
NEW = 'support-ticket-new-tenant-admin'
SENT = 'support-ticket-submitted-tenant-admin'

def test_offline_editorial_screenshots_are_real_template_samples():
    prov = json.loads((ROOT/'docs/presentation/rc111_support_ticket_demo_provenance.json').read_text())
    assert prov['fixture'] == 'isolated-synthetic-sqlite'
    assert prov['contains_real_user_data'] is False
    assert prov['recipient'] == 'tenant_admin'
    for row in prov['screenshots']:
        asset = ROOT/row['file']
        assert asset.is_file()
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == row['sha256']

def test_source_slide_and_appendix_include_sample_ticket_evidence():
    from scripts.ui_documentation_evidence import REQUIRED_SCREENSHOTS
    from scripts.capture_ui_screenshots import REQUIRED_CAPTURES
    assert {NEW, SENT} <= REQUIRED_CAPTURES == REQUIRED_SCREENSHOTS
    source = (ROOT/'scripts/build_training_visual_rc64.js').read_text()
    assert 'function supportTicketsPanel' in source
    assert "ciById.get('support-ticket-new-tenant-admin')" in source
    assert "ciManifest.screenshots.filter" in source
    assert 'the Support Tickets slide requires' not in source  # actual message in native test
    for name in (NEW, SENT):
        assert name in source
        assert name in (ROOT/'scripts/ui_documentation_evidence.py').read_text()
    content=json.loads((ROOT/'docs/presentation/content_it.json').read_text())
    assert any(item.get('screenshots')==[NEW,SENT] for item in content['slides'])

def test_real_capture_performs_request_and_submission():
    src=(ROOT/'scripts/capture_ui_screenshots.py').read_text()
    assert 'go(reader_page, "/support/new")' in src
    assert 'select[name="assignee_level"]' in src
    assert "select_option('tenant_admin')" in src
    assert 'button.support-primary[type="submit"]' in src
    assert f'snap(reader_page, "{NEW}"' in src
    assert f'snap(reader_page, "{SENT}"' in src
