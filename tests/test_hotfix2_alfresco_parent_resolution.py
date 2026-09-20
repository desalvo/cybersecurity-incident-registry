from pathlib import Path
from types import SimpleNamespace

import pytest

from app.plugins.alfresco import client


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = {}

    def json(self):
        return self._payload


def cfg(**overrides):
    base = {
        'enabled': True,
        'base_url': 'https://alfresco.example.test',
        'username': 'cir-service',
        'password': 'secret',
        'site': '',
        'parent_node_id': '',
        'target_path': 'Cybersecurity Incident Registry',
        'verify_tls': True,
        'timeout': 30,
    }
    base.update(overrides)
    return base


def identity_validator(url, purpose=None):
    return url


def test_explicit_parent_node_id_has_precedence_and_never_uses_root(monkeypatch):
    monkeypatch.setattr(client, 'validate_outbound_http_url', identity_validator)
    monkeypatch.setattr(client.requests, 'get', lambda *args, **kwargs: pytest.fail('site lookup must not run'))
    value = client.resolve_parent_node_id(cfg(parent_node_id='12345678-abcd-4abc-8abc-1234567890ab', site='ignored-site'))
    assert value == '12345678-abcd-4abc-8abc-1234567890ab'
    source = Path(client.__file__).read_text(encoding='utf-8')
    assert "return '-root-/children'" not in source
    assert "f'-root-/children" not in source


def test_site_is_resolved_through_document_library_container(monkeypatch):
    monkeypatch.setattr(client, 'validate_outbound_http_url', identity_validator)
    seen = []

    def fake_get(url, **kwargs):
        seen.append((url, kwargs))
        return FakeResponse(payload={'entry': {'id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'}})

    monkeypatch.setattr(client.requests, 'get', fake_get)
    value = client.resolve_parent_node_id(cfg(site='cyber security'))
    assert value == 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
    assert seen[0][0].endswith('/sites/cyber%20security/containers/documentLibrary')
    assert seen[0][1]['allow_redirects'] is False


def test_missing_parent_and_site_fails_closed_without_root_alias(monkeypatch):
    monkeypatch.setattr(client, 'validate_outbound_http_url', identity_validator)
    with pytest.raises(RuntimeError, match='Parent Node ID oppure un Site'):
        client.resolve_parent_node_id(cfg())


def test_upload_posts_to_resolved_uuid_children_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(client, 'validate_outbound_http_url', identity_validator)
    monkeypatch.setattr(client, 'config', lambda: cfg(parent_node_id='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'))
    uploaded = tmp_path / 'report.pdf'
    uploaded.write_bytes(b'pdf')
    seen = {}

    def fake_post(url, **kwargs):
        seen['url'] = url
        seen['data'] = kwargs['data']
        seen['allow_redirects'] = kwargs['allow_redirects']
        return FakeResponse(payload={'entry': {'id': 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff', 'name': 'report.pdf'}})

    monkeypatch.setattr(client.requests, 'post', fake_post)
    result = client.upload_file(uploaded, 'report.pdf', incident_id=42, incident_name='Phishing account amministratore', mimetype='application/pdf')
    assert seen['url'].endswith('/nodes/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/children')
    assert '-root-' not in seen['url']
    assert seen['data']['relativePath'] == 'Cybersecurity Incident Registry/incident-42 - Phishing account amministratore'
    assert seen['allow_redirects'] is False
    assert result['node_id'] == 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff'


def test_test_destination_resolves_site_then_checks_real_node(monkeypatch):
    monkeypatch.setattr(client, 'validate_outbound_http_url', identity_validator)
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if '/sites/' in url:
            return FakeResponse(payload={'entry': {'id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'}})
        return FakeResponse(payload={'entry': {'id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', 'name': 'documentLibrary', 'nodeType': 'cm:folder'}})

    monkeypatch.setattr(client.requests, 'get', fake_get)
    info = client.test_destination(cfg(site='cybersecurity'))
    assert calls[0].endswith('/sites/cybersecurity/containers/documentLibrary')
    assert calls[1].endswith('/nodes/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee')
    assert info['name'] == 'documentLibrary'


def test_invalid_parent_node_id_is_rejected_before_http(monkeypatch):
    monkeypatch.setattr(client.requests, 'get', lambda *args, **kwargs: pytest.fail('HTTP must not run'))
    with pytest.raises(RuntimeError, match='Parent Node ID Alfresco non valido'):
        client.resolve_parent_node_id(cfg(parent_node_id='../../bad?node=1'))


def test_admin_ui_and_setup_wizard_expose_parent_node_id_and_test_action():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'app/plugins/alfresco/templates/alfresco_admin_plugins.html').read_text(encoding='utf-8')
    routes = (root / 'app/plugins/alfresco/routes.py').read_text(encoding='utf-8')
    main_routes = (root / 'app/routes.py').read_text(encoding='utf-8')
    assert 'alfresco_parent_node_id' in template
    assert 'test_alfresco_destination' in template
    assert "'parent_node_id'" in routes
    assert "'alfresco_parent_node_id'" in main_routes
