from pathlib import Path
import pytest
from app.tenant_defaults_assets import _normalize_legacy_svg, _validate_svg


def test_legacy_svg_editor_metadata_removed():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><metadata><RDF><Work><format>image/svg+xml</format></Work></RDF></metadata><path d="M0 0 L1 1"/></svg>'
    result = _normalize_legacy_svg(svg)
    _validate_svg(result)
    assert b'RDF' not in result and b'path' in result


@pytest.mark.parametrize('extra', [
    '<script>alert(1)</script>',
    '<RDF><Work onload="evil()"/></RDF>',
    '<RDF><Work href="https://evil.test"/></RDF>',
])
def test_active_metadata_rejected(extra):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg"><metadata>'+extra+'</metadata></svg>').encode()
    with pytest.raises(ValueError):
        _normalize_legacy_svg(svg)


def test_no_metadata_keeps_original_bytes():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
    assert _normalize_legacy_svg(svg) == svg


def test_smoke_mode_is_not_distribution_mode():
    root = Path(__file__).resolve().parents[1]
    script = (root/'scripts/package_release.sh').read_text()
    assert 'CIR_SOURCE_PACKAGE_SMOKE' in script
    assert '--verify-installed-documentation' in script
    workflow = (root/'.github/workflows/ci-release.yml').read_text()
    assert "CIR_SOURCE_PACKAGE_SMOKE: '1'" in workflow
    assert 'Install verified documentation and package the current source' in workflow
