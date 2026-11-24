from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_login_brand_row_and_optional_custom_logo():
    page = (ROOT / "app/templates/ui/login_modern.html").read_text()
    assert 'class="cir-login-brand-row"' in page
    assert 'class="cir-login-app-logo"' in page
    assert 'class="cir-login-organization-logo"' in page
    assert 'data-cir-hide-on-error' in page
    row = page.split('<header class="cir-login-brand-row">', 1)[1].split('</header>', 1)[0]
    assert row.index('cir-login-app-logo') < row.index('cir-login-heading') < row.index('cir-login-organization-logo')
    assert page.count('class="cir-login-organization-logo"') == 1

def test_compact_responsive_layout():
    css = (ROOT / "app/static/ui/ui.css").read_text()
    assert '.cir-login-brand-row' in css
    assert 'height:100dvh' in css
    assert '@media(max-height:520px)' in css
