"""RC75: wizard guidance reflects the server-side permission boundary."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_tenant_wizard_in_training_and_role_comparison():
    data = json.loads((ROOT / 'docs/presentation/visual_rc64_spec.json').read_text())
    by = {row['index']: row for row in data}
    for idx in (33, 35):
        text = ' '.join(by[idx]['bullets'])
        assert 'Wizard setup iniziale' in text
        assert 'super admin' in text
        assert 'admin del tenant' in text
    assert 'riservato al super admin' in ' '.join(by[33]['bullets'])


def test_tenant_wizard_current_permissions_in_backend():
    routes = (ROOT / 'app/routes.py').read_text()
    assert "def can_admin():\n    return user_role_for_tenant() in ['superuser','admin']" in routes
    assert re.search(r"def admin_setup_wizard\(\):\s*if not can_admin\(\):", routes)
    create = routes.split('def _save_setup_wizard_tenants(form):', 1)[1].split('\ndef ', 1)[0]
    assert 'if not is_superuser():' in create
    assert 'clone_tenant_config(source.id, tenant.id)' in create
    assert "def _save_setup_wizard_admin_password(form):" in routes
    template=(ROOT/'app/templates/admin_setup_wizard.html').read_text()
    assert 'name="action" value="skip"' in template
    assert 'name="action" value="finish"' in template


def test_tenant_wizard_is_captured_from_authenticated_browser_and_embedded():
    capture = (ROOT / 'scripts/capture_ui_screenshots.py').read_text()
    evidence = (ROOT / 'scripts/ui_documentation_evidence.py').read_text()
    builder = (ROOT / 'scripts/build_training_visual_rc64.js').read_text()
    verifier = (ROOT / 'scripts/verify_visual_training_rc64.py').read_text()
    for ident, selector in (('tenant-setup-wizard-desktop', '.setup-wizard-shell'),
                            ('tenant-setup-wizard-panel', '.setup-wizard-panel')):
        assert f'\"{ident}\"' in capture
        assert f'\"{ident}\"' in builder or f"'{ident}'" in builder
        assert f"'{ident}': '{selector}'" in evidence
        assert f"'{ident}': '/admin/setup-wizard'" in evidence
    assert 'login(limited_page, "demo-tenant-admin")' in capture
    assert 'go(limited_page, "/admin/setup-wizard")' in capture
    assert 'tenant_wizard_resume_and_restart_verified' in capture
    assert "d.index===33" in builder
    assert 'slide.addImage({path:wizard.path' in builder
    assert "(41, 'tenant-setup-wizard-panel')" in verifier
    assert 'linked_slide_image_digests(rich_archive, slide)' in verifier


def test_wizard_reentry_and_reset_are_backed_by_server_state():
    routes = (ROOT / 'app/routes.py').read_text()
    part = routes.split('def admin_setup_wizard():',1)[1].split('\n@bp.route(',1)[0]
    assert "action == 'reset'" in part
    assert "action == 'skip'" in part
    assert "action == 'finish'" in part
    assert '_save_setup_wizard_progress(progress)' in part
    assert '_setup_wizard_progress()' in part
    assert 'can_admin()' in part


def test_operational_deck_has_tenant_wizard_screenshot_chapter():
    content = json.loads((ROOT / "docs/presentation/content_it.json").read_text(encoding="utf8"))
    slides = content["slides"]
    chapter = slides[43]
    assert chapter["type"] == "screenshots"
    assert "Wizard di setup iniziale" in chapter["title"]
    assert chapter["screenshots"] == ["tenant-setup-wizard-desktop", "tenant-setup-wizard-panel"]
    assert "Riesegui da capo" in chapter["notes"]
    assert "Salta questo gruppo" in chapter["notes"]
