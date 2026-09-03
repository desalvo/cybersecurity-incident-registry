import os

import pytest

from app.outbound_security import validate_outbound_http_url


@pytest.mark.parametrize('url', [
    'http://127.0.0.1:8080/',
    'http://169.254.169.254/latest/meta-data/',
    'https://10.0.0.5/api',
    'https://[::1]/',
])
def test_private_and_special_destinations_are_blocked_by_default(monkeypatch, url):
    monkeypatch.delenv('CIR_OUTBOUND_PRIVATE_HOSTS', raising=False)
    with pytest.raises(ValueError):
        validate_outbound_http_url(url, purpose='test')


def test_private_destination_requires_explicit_hostname_allowlist(monkeypatch):
    monkeypatch.setenv('CIR_OUTBOUND_PRIVATE_HOSTS', '10.0.0.5')
    assert validate_outbound_http_url('http://10.0.0.5/api', purpose='test') == 'http://10.0.0.5/api'


def test_public_http_is_blocked_by_default(monkeypatch):
    monkeypatch.delenv('CIR_OUTBOUND_ALLOW_HTTP', raising=False)
    with pytest.raises(ValueError):
        validate_outbound_http_url('http://8.8.8.8/api', purpose='test')


def test_inline_url_credentials_are_blocked():
    with pytest.raises(ValueError):
        validate_outbound_http_url('https://user:password@8.8.8.8/api', purpose='test')
