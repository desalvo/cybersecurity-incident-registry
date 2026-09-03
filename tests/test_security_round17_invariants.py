from pathlib import Path
import json

import pytest

ROOT = Path(__file__).parents[1]


def _text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_patched_runtime_images_are_pinned():
    assert _text('Dockerfile').splitlines()[0].strip() == 'FROM python:3.12.14-slim-trixie AS python-deps'
    for path in ('docker-compose.yml', 'docker-compose.test.yml', 'k8s/postgresql.yaml'):
        text = _text(path)
        assert 'postgres:18.6' in text
        assert 'postgres:18.4' not in text


def test_container_root_fallback_is_fail_closed_and_umask_is_restrictive():
    assert 'CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE:-0' in _text('docker-compose.yml')
    assert 'CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE=0' in _text('.env.example')
    entrypoint = _text('docker-entrypoint.sh')
    assert 'umask 027' in entrypoint
    assert '${CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE:-0}' in entrypoint


def test_production_compose_enforces_runtime_hardening():
    text = _text('docker-compose.production.yml')
    assert 'CIR_PRODUCTION_IMAGE:?' in text
    assert 'read_only: true' in text
    assert 'no-new-privileges:true' in text
    assert 'cap_drop:' in text and '\n      - ALL' in text
    assert 'CIR_PRODUCTION: "1"' in text
    assert 'SESSION_COOKIE_SECURE: "1"' in text
    assert 'CIR_FORCE_HSTS: "1"' in text
    assert 'CIR_DISABLE_CSRF: "0"' in text
    assert 'CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE: "0"' in text


def test_kubernetes_workloads_are_hardened_and_secrets_are_external():
    deployment = _text('k8s/deployment.yaml')
    assert 'automountServiceAccountToken: false' in deployment
    assert 'readOnlyRootFilesystem: true' in deployment
    assert 'drop: ["ALL"]' in deployment
    assert 'type: RuntimeDefault' in deployment
    assert 'setting-encryption-key' in deployment
    assert 'mountPath: /tmp' in deployment
    assert 'cybersecurity-incident-registry:latest' not in deployment
    assert 'newTag: latest' not in _text('k8s/kustomization.yaml')

    postgres = _text('k8s/postgresql.yaml')
    assert 'kind: Secret' not in postgres
    assert 'CHANGE_ME' not in postgres
    assert 'cir-postgres-secret' in postgres
    assert '$POSTGRES_USER' in postgres and '$POSTGRES_DB' in postgres
    assert 'k8s/secrets.example.yaml' not in _text('k8s/kustomization.yaml')


def test_env_secret_file_support_and_conflict(monkeypatch, tmp_path):
    from app.env_utils import get_env_secret

    secret_file = tmp_path / 'secret'
    secret_file.write_text('from-file\n', encoding='utf-8')
    monkeypatch.delenv('ROUND17_SECRET', raising=False)
    monkeypatch.setenv('ROUND17_SECRET_FILE', str(secret_file))
    assert get_env_secret('ROUND17_SECRET') == 'from-file'

    monkeypatch.setenv('ROUND17_SECRET', 'inline')
    with pytest.raises(RuntimeError):
        get_env_secret('ROUND17_SECRET')


def test_rate_limit_ignores_spoofed_forwarded_for_without_trusted_proxy(monkeypatch):
    from flask import Flask
    from app.routes import _client_ip_for_rate_limit

    monkeypatch.delenv('CIR_TRUSTED_PROXY_CIDRS', raising=False)
    app = Flask(__name__)
    with app.test_request_context('/', environ_base={'REMOTE_ADDR': '203.0.113.10'}, headers={'X-Forwarded-For': '198.51.100.1'}):
        assert _client_ip_for_rate_limit() == '203.0.113.10'


def test_rate_limit_uses_first_untrusted_hop_from_trusted_proxy(monkeypatch):
    from flask import Flask
    from app.routes import _client_ip_for_rate_limit

    monkeypatch.setenv('CIR_TRUSTED_PROXY_CIDRS', '10.0.0.0/8')
    app = Flask(__name__)
    with app.test_request_context('/', environ_base={'REMOTE_ADDR': '10.2.2.2'}, headers={'X-Forwarded-For': '192.0.2.9, 198.51.100.7, 10.1.2.3'}):
        assert _client_ip_for_rate_limit() == '198.51.100.7'


def test_round17_sbom_is_transitive_and_contains_wheel_evidence():
    path = ROOT / 'SBOM_ROUND17.cdx.json'
    assert path.exists()
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['bomFormat'] == 'CycloneDX'
    assert data['specVersion'] == '1.6'
    components = {c['name'].lower(): c for c in data['components']}
    assert len(components) > 18
    assert 'flask' in components
    assert 'jinja2' in components
    flask_props = {p['name']: p['value'] for p in components['flask'].get('properties', [])}
    jinja_props = {p['name']: p['value'] for p in components['jinja2'].get('properties', [])}
    assert flask_props['cir:dependency-level'] == 'direct'
    assert jinja_props['cir:dependency-level'] == 'transitive'
    assert components['flask'].get('hashes')


def test_sca_gate_audits_locked_requirements():
    text = _text('scripts/run_sca.sh')
    assert 'pip_audit' in text
    assert '-r requirements.txt' in text
    assert 'SCA_PIP_AUDIT.json' in text
