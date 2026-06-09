"""Runtime helpers for the integrated HTTPS listener certificates.

The container entrypoint imports this module directly, so keep it independent
from Flask, SQLAlchemy and the rest of the application package.
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import os
import socket
from pathlib import Path
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

_TRUE_VALUES = {"1", "true", "yes", "on"}
_USER_MARKER = "user_provided"
_GENERATED_MARKER = "self_signed_generated"


def ssl_storage_dir() -> Path:
    path = Path(os.environ.get("SSL_DIR") or "/data/ssl")
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_certificate_paths() -> Tuple[Path, Path]:
    base = ssl_storage_dir()
    return base / "current.crt", base / "current.key"


def _explicit_cert_env() -> tuple[str | None, str | None]:
    """Return explicit listener certificate variables, avoiding CA-bundle collisions.

    Some runtimes export SSL_CERT_FILE as a CA trust bundle for outbound HTTPS.
    Treat the generic SSL_CERT_FILE/SSL_KEY_FILE pair as an integrated-listener
    certificate only when both are set, while supporting CIR_SSL_CERT_FILE and
    CIR_SSL_KEY_FILE as unambiguous aliases.
    """
    cir_cert = os.environ.get("CIR_SSL_CERT_FILE")
    cir_key = os.environ.get("CIR_SSL_KEY_FILE")
    if cir_cert or cir_key:
        return cir_cert, cir_key
    generic_cert = os.environ.get("SSL_CERT_FILE")
    generic_key = os.environ.get("SSL_KEY_FILE")
    if generic_cert and generic_key:
        return generic_cert, generic_key
    return None, None


def configured_certificate_paths() -> Tuple[Path, Path]:
    default_cert, default_key = default_certificate_paths()
    cert_env, key_env = _explicit_cert_env()
    return Path(cert_env or default_cert), Path(key_env or default_key)


def marker_path(name: str) -> Path:
    return ssl_storage_dir() / name


def env_uses_explicit_certificate_paths() -> bool:
    cert_env, key_env = _explicit_cert_env()
    return bool(cert_env or key_env)


def is_user_managed_certificate() -> bool:
    """Return True when the active certificate must not be auto-overwritten."""
    return env_uses_explicit_certificate_paths() or marker_path(_USER_MARKER).exists()


def mark_user_managed_certificate(enabled: bool = True) -> None:
    marker = marker_path(_USER_MARKER)
    if enabled:
        marker.write_text("user-provided certificate\n", encoding="utf-8")
        marker_path(_GENERATED_MARKER).unlink(missing_ok=True)
    else:
        marker.unlink(missing_ok=True)


def load_certificate(cert_path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(cert_path.read_bytes())


def load_private_key(key_path: Path):
    return serialization.load_pem_private_key(key_path.read_bytes(), password=None)


def _public_keys_match(certificate: x509.Certificate, private_key) -> bool:
    public_key = certificate.public_key()
    data = b"cir-certificate-validation"
    try:
        if isinstance(private_key, rsa.RSAPrivateKey):
            signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())
            public_key.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
            return True
        if isinstance(private_key, ec.EllipticCurvePrivateKey):
            signature = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
            public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
            return True
    except Exception:
        return False
    try:
        return public_key.public_numbers() == private_key.public_key().public_numbers()
    except Exception:
        return False


def certificate_pair_status(cert_path: Path | None = None, key_path: Path | None = None) -> dict:
    cert_path = Path(cert_path) if cert_path is not None else configured_certificate_paths()[0]
    key_path = Path(key_path) if key_path is not None else configured_certificate_paths()[1]
    status = {
        "cert_path": str(cert_path),
        "key_path": str(key_path),
        "cert_present": cert_path.exists() and cert_path.is_file(),
        "key_present": key_path.exists() and key_path.is_file(),
        "valid": False,
        "reason": "missing certificate or private key",
        "not_valid_before": None,
        "not_valid_after": None,
        "self_signed": False,
        "user_managed": is_user_managed_certificate(),
    }
    if not (status["cert_present"] and status["key_present"]):
        return status
    try:
        certificate = load_certificate(cert_path)
        private_key = load_private_key(key_path)
        now = _dt.datetime.now(_dt.timezone.utc)
        not_before = certificate.not_valid_before_utc
        not_after = certificate.not_valid_after_utc
        status["not_valid_before"] = not_before.isoformat()
        status["not_valid_after"] = not_after.isoformat()
        status["self_signed"] = certificate.issuer == certificate.subject
        if now < not_before:
            status["reason"] = "certificate is not valid yet"
            return status
        if now >= not_after:
            status["reason"] = "certificate is expired"
            return status
        if not _public_keys_match(certificate, private_key):
            status["reason"] = "certificate and private key do not match"
            return status
        status["valid"] = True
        status["reason"] = "valid"
        return status
    except Exception as exc:
        status["reason"] = f"invalid certificate or private key: {exc}"
        return status


def _hostname_candidates() -> list[str]:
    names = [
        os.environ.get("SSL_SELF_SIGNED_CN"),
        os.environ.get("SERVER_NAME"),
        os.environ.get("HOSTNAME"),
        socket.gethostname(),
        "localhost",
    ]
    result: list[str] = []
    for name in names:
        if not name:
            continue
        clean = str(name).split(":", 1)[0].strip()
        if clean and clean not in result:
            result.append(clean)
    return result or ["localhost"]


def generate_self_signed_certificate(cert_path: Path | None = None, key_path: Path | None = None, *, force: bool = False) -> dict:
    cert_path = Path(cert_path) if cert_path is not None else default_certificate_paths()[0]
    key_path = Path(key_path) if key_path is not None else default_certificate_paths()[1]
    if is_user_managed_certificate() and not force:
        return certificate_pair_status(cert_path, key_path)

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    common_name = _hostname_candidates()[0]
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IT"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Cybersecurity Incident Registry"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    alt_names: list[x509.GeneralName] = []
    for name in _hostname_candidates():
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            alt_names.append(x509.DNSName(name))
    for ip in ("127.0.0.1", "::1"):
        alt_names.append(x509.IPAddress(ipaddress.ip_address(ip)))

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=5))
        .not_valid_after(now + _dt.timedelta(days=int(os.environ.get("SSL_SELF_SIGNED_DAYS", "397"))))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, content_commitment=False, data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(private_key, hashes.SHA256())
    )
    key_path.write_bytes(private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    try:
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
    except OSError:
        pass
    marker_path(_GENERATED_MARKER).write_text("self-signed certificate generated by container runtime\n", encoding="utf-8")
    marker_path(_USER_MARKER).unlink(missing_ok=True)
    return certificate_pair_status(cert_path, key_path)


def ensure_runtime_certificate() -> dict:
    """Ensure the integrated HTTPS listener has a usable certificate.

    Explicit certificate paths or certificates marked as uploaded by the user are
    authoritative and are never replaced. Otherwise the default host certificate
    is generated, or regenerated when missing, expired, not yet valid, malformed
    or mismatched with the private key.
    """
    cert_path, key_path = configured_certificate_paths()
    status = certificate_pair_status(cert_path, key_path)
    if status["valid"] or is_user_managed_certificate():
        return status
    return generate_self_signed_certificate(cert_path, key_path)


def main() -> int:
    status = ensure_runtime_certificate()
    print(status["reason"])
    return 0 if status["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
