from pathlib import Path


def test_custom_general_fields_are_configurable_and_rendered_static():
    layout = Path('app/templates/admin_incident_form_fields.html').read_text(encoding='utf-8')
    admin = Path('app/templates/admin_incident_custom_fields.html').read_text(encoding='utf-8')
    base = Path('app/templates/base.html').read_text(encoding='utf-8')
    detail = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    models = Path('app/models.py').read_text(encoding='utf-8')

    assert 'Campi personalizzati nei Dati Generali' in admin
    assert 'custom_field_type' in admin
    assert 'Campo personalizzato' in layout
    assert 'admin_incident_custom_fields' in base
    assert 'Nascosto con mostra in chiaro' in routes
    assert 'custom_fields_json' in models
    assert 'custom_incident_fields' in detail
    assert 'visible_custom_incident_field_definitions()' in routes
    assert 'incident_detail_visibility_field_records()' in routes
    assert 'reveal-custom-secret' in detail
    assert 'update_incident_custom_field_values_from_form(inc)' in routes


def test_incident_title_shows_reference_and_top_icon_is_vertically_centered_static():
    detail = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    css = Path('app/static/style.css').read_text(encoding='utf-8')
    assert 'incident-reference-under-title' in detail
    assert 'Riferimento: <strong>{{ inc.reference' in detail
    assert 'top:50%' in css
    assert 'translateY(-50%)' in css


def test_release_version_uses_central_metadata_files():
    version = Path('VERSION').read_text(encoding='utf-8').strip()
    version_module = Path('app/version.py').read_text(encoding='utf-8')
    compose = Path('docker-compose.yml').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    assert 'DEFAULT_RELEASE_VERSION = _read_metadata_file("VERSION"' in version_module
    assert f'APP_VERSION: {version}' in compose
    assert f'Versione: {version}' in readme
