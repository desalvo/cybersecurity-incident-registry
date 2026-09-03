"""Environment parsing helpers used at application startup.

The helpers are intentionally small and dependency-free.  They centralize
normalization for secrets read from Docker Compose/Kubernetes environments,
where accidental surrounding quotes or CRLF line endings in .env files are a
common source of confusing bootstrap failures.
"""
import os


def clean_env_secret(value):
    """Return a secret-like environment value with transport artefacts removed.

    The function preserves intentional internal spaces and special characters,
    but removes surrounding CR/LF whitespace and one pair of matching surrounding
    quotes.  This makes values copied into Docker Compose .env files as
    ``PASSWORD="secret"`` or with Windows line endings behave as operators
    expect, without changing the configured secret itself.
    """
    if value is None:
        return None
    cleaned = str(value).strip('\r\n')
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1]
    return cleaned



def get_env_secret(name, default=None, *, max_bytes=65536):
    """Read a secret from ``NAME`` or ``NAME_FILE`` using Docker/Kubernetes convention.

    Empty values are treated as unset.  Supplying both forms is rejected to avoid
    ambiguous precedence.  Secret files are bounded to prevent accidentally
    reading a device or an unexpectedly large file.
    """
    inline = os.getenv(name)
    file_path = os.getenv(f"{name}_FILE")
    if inline is not None and not str(inline).strip():
        inline = None
    if file_path is not None and not str(file_path).strip():
        file_path = None
    if inline is not None and file_path is not None:
        raise RuntimeError(f"Configure only one of {name} or {name}_FILE")
    if file_path is not None:
        path = os.path.abspath(os.path.expanduser(str(file_path).strip()))
        try:
            with open(path, 'rb') as handle:
                raw = handle.read(max_bytes + 1)
        except OSError as exc:
            raise RuntimeError(f"Unable to read secret file for {name}: {path}") from exc
        if len(raw) > max_bytes:
            raise RuntimeError(f"Secret file for {name} exceeds {max_bytes} bytes")
        if b'\x00' in raw:
            raise RuntimeError(f"Secret file for {name} contains NUL bytes")
        try:
            inline = raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"Secret file for {name} is not valid UTF-8") from exc
    if inline is None:
        return default
    return clean_env_secret(inline)

def get_admin_initial_password():
    """Return the configured bootstrap password for the local admin account.

    ``ADMIN_INITIAL_PASSWORD`` is authoritative.  ``ADMIN_PASSWORD`` is accepted
    only as a compatibility alias for older deployments and should not be used
    in new configurations.
    """
    value = get_env_secret('ADMIN_INITIAL_PASSWORD')
    if value is None:
        value = get_env_secret('ADMIN_PASSWORD')
    return value
