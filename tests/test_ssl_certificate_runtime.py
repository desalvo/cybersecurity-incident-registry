from __future__ import annotations

import datetime as dt
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _write_expired_pair(cert_path: Path, key_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'expired.local')])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=10))
        .not_valid_after(now - dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def test_runtime_generates_self_signed_certificate_when_https_enabled_without_user_cert(monkeypatch, tmp_path):
    from app.ssl_certificates import certificate_pair_status, ensure_runtime_certificate

    monkeypatch.setenv('SSL_DIR', str(tmp_path))
    monkeypatch.delenv('SSL_CERT_FILE', raising=False)
    monkeypatch.delenv('SSL_KEY_FILE', raising=False)

    status = ensure_runtime_certificate()

    assert status['valid'] is True
    assert status['self_signed'] is True
    assert (tmp_path / 'current.crt').exists()
    assert (tmp_path / 'current.key').exists()
    assert (tmp_path / 'self_signed_generated').exists()
    assert certificate_pair_status()['valid'] is True


def test_runtime_regenerates_invalid_default_host_certificate(monkeypatch, tmp_path):
    from app.ssl_certificates import certificate_pair_status, ensure_runtime_certificate

    monkeypatch.setenv('SSL_DIR', str(tmp_path))
    monkeypatch.delenv('SSL_CERT_FILE', raising=False)
    monkeypatch.delenv('SSL_KEY_FILE', raising=False)
    cert_path = tmp_path / 'current.crt'
    key_path = tmp_path / 'current.key'
    _write_expired_pair(cert_path, key_path)
    assert certificate_pair_status()['valid'] is False

    status = ensure_runtime_certificate()

    assert status['valid'] is True
    assert status['self_signed'] is True
    assert (tmp_path / 'self_signed_generated').exists()


def test_runtime_never_overwrites_explicit_user_certificate_paths(monkeypatch, tmp_path):
    from app.ssl_certificates import ensure_runtime_certificate

    cert_path = tmp_path / 'external.crt'
    key_path = tmp_path / 'external.key'
    cert_path.write_text('not a certificate', encoding='utf-8')
    key_path.write_text('not a key', encoding='utf-8')
    before_cert = cert_path.read_text(encoding='utf-8')
    before_key = key_path.read_text(encoding='utf-8')
    monkeypatch.setenv('SSL_DIR', str(tmp_path / 'ssl'))
    monkeypatch.setenv('SSL_CERT_FILE', str(cert_path))
    monkeypatch.setenv('SSL_KEY_FILE', str(key_path))

    status = ensure_runtime_certificate()

    assert status['valid'] is False
    assert cert_path.read_text(encoding='utf-8') == before_cert
    assert key_path.read_text(encoding='utf-8') == before_key
    assert not (tmp_path / 'ssl' / 'current.crt').exists()


def test_web_uploaded_certificate_is_marked_user_managed(monkeypatch, tmp_path):
    from app.ssl_certificates import generate_self_signed_certificate, mark_user_managed_certificate, ensure_runtime_certificate

    monkeypatch.setenv('SSL_DIR', str(tmp_path))
    monkeypatch.delenv('SSL_CERT_FILE', raising=False)
    monkeypatch.delenv('SSL_KEY_FILE', raising=False)
    generate_self_signed_certificate()
    cert_path = tmp_path / 'current.crt'
    original = cert_path.read_bytes()
    mark_user_managed_certificate(True)

    status = ensure_runtime_certificate()

    assert status['valid'] is True
    assert cert_path.read_bytes() == original
    assert (tmp_path / 'user_provided').exists()


def test_docker_entrypoint_ensures_and_restarts_https_certificate():
    entrypoint = Path('docker-entrypoint.sh').read_text(encoding='utf-8')
    assert 'python -m app.ssl_certificates' in entrypoint
    assert 'certificate_state()' in entrypoint
    assert 'HTTPS certificate files changed; restarting HTTPS listener' in entrypoint


def test_lone_generic_ssl_cert_file_is_ignored_as_possible_ca_bundle(monkeypatch, tmp_path):
    from app.ssl_certificates import configured_certificate_paths, ensure_runtime_certificate, env_uses_explicit_certificate_paths

    ca_bundle = tmp_path / 'ca-certificates.crt'
    ca_bundle.write_text('CA bundle placeholder', encoding='utf-8')
    monkeypatch.setenv('SSL_DIR', str(tmp_path / 'ssl'))
    monkeypatch.setenv('SSL_CERT_FILE', str(ca_bundle))
    monkeypatch.delenv('SSL_KEY_FILE', raising=False)
    monkeypatch.delenv('CIR_SSL_CERT_FILE', raising=False)
    monkeypatch.delenv('CIR_SSL_KEY_FILE', raising=False)

    cert_path, key_path = configured_certificate_paths()
    assert env_uses_explicit_certificate_paths() is False
    assert cert_path == tmp_path / 'ssl' / 'current.crt'
    assert key_path == tmp_path / 'ssl' / 'current.key'
    assert ensure_runtime_certificate()['valid'] is True
    assert ca_bundle.read_text(encoding='utf-8') == 'CA bundle placeholder'
