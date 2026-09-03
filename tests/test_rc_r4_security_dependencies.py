from pathlib import Path
import json

ROOT = Path(__file__).parents[1]


def test_r4_security_dependency_pins():
    req = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'pypdf==6.16.2' in req
    assert 'cryptography==50.0.1' in req
    assert 'pypdf==6.10.2' not in req
    assert 'cryptography==46.0.7' not in req


def test_r4_release_notes_document_security_update():
    for name in ('RELEASE_NOTES_0.9.0-1.md', 'RELEASE_NOTES_0.9.0-1_en.md'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert '6.16.2' in text
        assert '50.0.1' in text
        assert 'R4' in text


def test_r4_sbom_uses_security_fixed_direct_versions():
    sbom = json.loads((ROOT / 'SBOM_ROUND18.cdx.json').read_text(encoding='utf-8'))
    versions = {c['name'].lower(): c['version'] for c in sbom['components']}
    assert versions['pypdf'] == '6.16.2'
    assert versions['cryptography'] == '50.0.1'
