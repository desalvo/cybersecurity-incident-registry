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


def get_admin_initial_password():
    """Return the configured bootstrap password for the local admin account.

    ``ADMIN_INITIAL_PASSWORD`` is authoritative.  ``ADMIN_PASSWORD`` is accepted
    only as a compatibility alias for older deployments and should not be used
    in new configurations.
    """
    value = os.getenv('ADMIN_INITIAL_PASSWORD')
    if value is None:
        value = os.getenv('ADMIN_PASSWORD')
    return clean_env_secret(value)
