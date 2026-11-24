"""Only referenced managed images travel in defaults bundles; writes are owned."""
import base64
import copy
import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def assets_app(tmp_path):
    from flask import Flask
    from app.models import db
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///' + str(tmp_path / 'assets.db'),
                      SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      LOGO_DIR=str(tmp_path / 'logos'), SSO_LOGO_DIR=str(tmp_path / 'sso'))
    Path(app.config['LOGO_DIR']).mkdir()
    Path(app.config['SSO_LOGO_DIR']).mkdir()
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.info['cir_defaults_suspended'] = True
        yield app
        db.session.remove()


def _png():
    stream = io.BytesIO()
    Image.new('RGB', (8, 8), color='navy').save(stream, format='PNG')
    return stream.getvalue()


def _item(kind, source_ref, content=None):
    content = _png() if content is None else content
    return {'kind': kind, 'source_ref': source_ref, 'filename': Path(source_ref).name,
            'sha256': hashlib.sha256(content).hexdigest(), 'content_base64': base64.b64encode(content).decode('ascii')}


def _setting(key, value):
    return {'key': key, 'value': value, 'structured': isinstance(value, (dict, list)), 'redacted_paths': []}


def test_assets_export_only_explicit_managed_references(assets_app, tmp_path):
    from app.tenant_defaults_assets import export_defaults_assets
    logo = Path(assets_app.config['LOGO_DIR']) / 'company.png'
    logo.write_bytes(_png())
    sso = Path(assets_app.config['SSO_LOGO_DIR']) / 'identity.png'
    sso.write_bytes(_png())
    (sso.parent / 'unreferenced.png').write_bytes(_png())
    private = tmp_path / 'private-secret.key'
    private.write_text('PRIVATE KEY MUST NOT BE READ')
    settings = [_setting('logo_path', str(logo)),
                _setting('sso_profiles_json', [{'id': 'one', 'sso_logo_path': 'sso/identity.png'},
                                              {'id': 'two', 'sso_logo_path': 'sso/identity.png'}]),
                _setting('backup_local_path', str(private))]
    assets = export_defaults_assets(settings)
    assert len(assets) == 2
    assert {(a['kind'], a['source_ref']) for a in assets} == {('logo_path', str(logo)), ('sso_logo_path', 'sso/identity.png')}
    assert all(base64.b64decode(a['content_base64']) == _png() for a in assets)


def test_assets_builtin_static_svg_is_supported_but_active_svg_rejected(assets_app):
    from app.tenant_defaults_assets import validate_defaults_assets
    safe = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><path fill="#fff" d="M0 0h8v8H0z"/></svg>'
    settings = [_setting('sso_profiles_json', [{'sso_logo_path': 'sso/logo.svg'}])]
    assert validate_defaults_assets([_item('sso_logo_path', 'sso/logo.svg', safe)], settings)
    for unsafe in [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.test/x"/></svg>',
        b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg>&xxe;</svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><path style="fill:url(https://example.test/x)"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" xml:base="//example.test/x"><use href="#local"/></svg>',
        '<?xml version="1.0" encoding="UTF-16"?><?xml-stylesheet href="https://example.test/x"?><svg xmlns="http://www.w3.org/2000/svg"/>'.encode('utf-16'),
    ]:
        with pytest.raises(ValueError):
            validate_defaults_assets([_item('sso_logo_path', 'sso/logo.svg', unsafe)], settings)


@pytest.mark.parametrize('mode', ['missing', 'unreferenced', 'duplicate', 'digest', 'base64', 'fake_image', 'traversal', 'filename_mismatch'])
def test_assets_validate_complete_and_safe_manifest(assets_app, mode):
    from app.tenant_defaults_assets import validate_defaults_assets
    settings = [_setting('sso_profiles_json', [{'sso_logo_path': 'sso/logo.png'}])]
    assets = [_item('sso_logo_path', 'sso/logo.png')]
    if mode == 'missing':
        assets = []
    elif mode == 'unreferenced':
        assets.append(_item('sso_logo_path', 'sso/other.png'))
    elif mode == 'duplicate':
        assets.append(copy.deepcopy(assets[0]))
    elif mode == 'digest':
        assets[0]['sha256'] = '0' * 64
    elif mode == 'base64':
        assets[0]['content_base64'] = '%%%'
    elif mode == 'fake_image':
        assets = [_item('sso_logo_path', 'sso/logo.png', b'NOT AN IMAGE')]
    elif mode == 'traversal':
        assets[0]['source_ref'] = 'sso/../../outside.png'
    elif mode == 'filename_mismatch':
        assets[0]['filename'] = 'different.png'
    with pytest.raises(ValueError):
        validate_defaults_assets(assets, settings)


def test_assets_export_rejects_outside_directory_and_symlink(assets_app, tmp_path):
    from app.tenant_defaults_assets import export_defaults_assets
    outside = tmp_path / 'outside.png'
    outside.write_bytes(_png())
    with pytest.raises(ValueError, match='fuori'):
        export_defaults_assets([_setting('logo_path', str(outside))])
    link = Path(assets_app.config['LOGO_DIR']) / 'link.png'
    link.symlink_to(outside)
    with pytest.raises(ValueError, match='simbolico'):
        export_defaults_assets([_setting('logo_path', str(link))])


def test_assets_import_and_commit_uses_new_names_without_overwriting(assets_app):
    from app.models import db, Setting
    from app.tenant_defaults_assets import import_defaults_assets, remap_defaults_asset_references
    existing = Path(assets_app.config['SSO_LOGO_DIR']) / 'logo.png'
    existing.write_bytes(b'EXISTING')
    original = [{'id': 'corp', 'sso_logo_path': 'sso/logo.png'}]
    mapping = import_defaults_assets([_item('sso_logo_path', 'sso/logo.png')])
    remapped = remap_defaults_asset_references(original, 'sso_profiles_json', mapping)
    new_ref = remapped[0]['sso_logo_path']
    assert new_ref.startswith('sso/td_') and new_ref != 'sso/logo.png'
    new_path = existing.parent / Path(new_ref).name
    db.session.add(Setting(key='asset-test', value=new_ref))
    db.session.commit()
    assert new_path.read_bytes() == _png()
    assert existing.read_bytes() == b'EXISTING'
    assert original[0]['sso_logo_path'] == 'sso/logo.png'


@pytest.mark.parametrize('finish', ['rollback', 'close'])
def test_assets_rollback_or_session_close_removes_only_owned_new_files(assets_app, finish):
    from app.models import db
    from app.tenant_defaults_assets import import_defaults_assets, remap_defaults_asset_references
    existing = Path(assets_app.config['LOGO_DIR']) / 'logo.png'
    existing.write_bytes(b'KEEP ORIGINAL')
    source = '/different/source/logo.png'
    mapping = import_defaults_assets([_item('logo_path', source)])
    imported = Path(remap_defaults_asset_references(source, 'logo_path', mapping))
    assert imported.exists() and imported.parent == existing.parent
    if finish == 'rollback':
        db.session.rollback()
    else:
        db.session.close()
    assert not imported.exists()
    assert existing.read_bytes() == b'KEEP ORIGINAL'


def test_assets_unused_imports_are_removed_on_commit(assets_app):
    from app.models import db, Setting
    from app.tenant_defaults_assets import import_defaults_assets
    directory = Path(assets_app.config['SSO_LOGO_DIR'])
    import_defaults_assets([_item('sso_logo_path', 'sso/logo.png')])
    assert list(directory.iterdir())
    # E.g. bundle preserves a local setting: the incoming logo stays unreferenced.
    db.session.add(Setting(key='unrelated', value='unchanged'))
    db.session.commit()
    assert not list(directory.iterdir())


def test_assets_nested_commit_still_cleans_files_on_outer_rollback(assets_app):
    from app.models import db
    from app.tenant_defaults_assets import import_defaults_assets, remap_defaults_asset_references
    db.session.begin()
    with db.session.begin_nested():
        mapping = import_defaults_assets([_item('sso_logo_path', 'sso/logo.png')])
        reference = remap_defaults_asset_references('sso/logo.png', 'sso_logo_path', mapping)
    path = Path(assets_app.config['SSO_LOGO_DIR']) / Path(reference).name
    assert path.exists()
    db.session.rollback()
    assert not path.exists()


def test_assets_cleanup_does_not_remove_replaced_file(assets_app):
    from app.models import db
    from app.tenant_defaults_assets import import_defaults_assets, remap_defaults_asset_references
    mapping = import_defaults_assets([_item('sso_logo_path', 'sso/logo.png')])
    reference = remap_defaults_asset_references('sso/logo.png', 'sso_logo_path', mapping)
    path = Path(assets_app.config['SSO_LOGO_DIR']) / Path(reference).name
    path.unlink()
    path.write_bytes(b'DIFFERENT OWNER')
    db.session.rollback()
    assert path.read_bytes() == b'DIFFERENT OWNER'


def test_legacy_svg_static_fill_styles_are_normalized():
    from app.tenant_defaults_assets import _normalize_legacy_svg, _validate_svg
    raw = (b'<svg xmlns="http://www.w3.org/2000/svg">'
           b'<metadata><title>legacy</title></metadata>'
           b'<path style="fill:#4297b8;fill-opacity:1" d="M0 0"/>'
           b'<path style="fill:#162d4d;fill-opacity:1" d="M1 1"/>'
           b'</svg>')
    normalized = _normalize_legacy_svg(raw)
    assert b'style=' not in normalized
    assert b'fill="#4297b8"' in normalized
    assert b'fill="#162d4d"' in normalized
    assert b'fill-opacity="1"' in normalized
    _validate_svg(normalized)
    assert _normalize_legacy_svg(normalized) == normalized


import pytest

@pytest.mark.parametrize('css', [
    'fill:url(https://evil.test/x)', 'fill:url(#x)',
    'fill:red;stroke:url(https://evil.test/x)',
    'fill:#123456;fill:#abcdef', 'fill-opacity:2',
    'fill:expression(alert(1))', 'fill:#123456!important',
    'fill:#123456;opacity:0.5', 'fill:#123456;stroke:red',
])
def test_legacy_svg_rejects_unapproved_css(css):
    from app.tenant_defaults_assets import _normalize_legacy_svg
    raw = ('<svg xmlns="http://www.w3.org/2000/svg"><path style="'
           + css + '"/></svg>').encode()
    with pytest.raises(ValueError):
        _normalize_legacy_svg(raw)
