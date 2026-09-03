"""Validation helpers for administrator-configured outbound HTTP endpoints."""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'si', 'sì'}


def _private_host_allowlist():
    raw = os.getenv('CIR_OUTBOUND_PRIVATE_HOSTS', '')
    return {item.strip().lower().rstrip('.') for item in raw.split(',') if item.strip()}


def _resolved_addresses(hostname):
    try:
        return {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise ValueError(f'Host outbound non risolvibile: {hostname}') from exc


def validate_outbound_http_url(url, *, purpose='endpoint', allow_http=False):
    """Validate an outbound HTTP(S) URL and reject SSRF-prone destinations.

    Private, loopback, link-local, reserved and other non-public destinations are
    denied by default. Legitimate on-premise integrations must explicitly list
    their hostname in CIR_OUTBOUND_PRIVATE_HOSTS. HTTP is accepted only for an
    explicitly allowlisted private host or when CIR_OUTBOUND_ALLOW_HTTP=1.
    """
    value = str(url or '').strip()
    if not value:
        raise ValueError(f'{purpose}: URL mancante.')
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or not parsed.netloc:
        raise ValueError(f'{purpose}: usare un URL http(s) assoluto.')
    if parsed.username or parsed.password:
        raise ValueError(f'{purpose}: credenziali inline nell URL non consentite.')

    host = parsed.hostname.lower().rstrip('.')
    allowlisted_private = host in _private_host_allowlist()
    for raw_address in _resolved_addresses(host):
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            continue
        non_public = (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_multicast or address.is_reserved or address.is_unspecified
        )
        if non_public and not allowlisted_private:
            raise ValueError(
                f'{purpose}: destinazione di rete non pubblica bloccata; '
                'aggiungere esplicitamente l host a CIR_OUTBOUND_PRIVATE_HOSTS se previsto.'
            )

    if parsed.scheme != 'https' and not (
        allow_http or allowlisted_private or _truthy(os.getenv('CIR_OUTBOUND_ALLOW_HTTP'))
    ):
        raise ValueError(f'{purpose}: HTTPS obbligatorio per endpoint non allowlisted.')
    return value


def validate_outbound_host(hostname, *, purpose='endpoint TCP'):
    """Validate a configured TCP hostname against the outbound allowlist.

    This is used for non-HTTP protocols such as SMTP. Private/special
    destinations require explicit CIR_OUTBOUND_PRIVATE_HOSTS allowlisting.
    """
    host = str(hostname or '').strip().rstrip('.')
    if not host or any(ch in host for ch in '/\\@'):
        raise ValueError(f'{purpose}: host non valido.')
    allowlisted_private = host.lower() in _private_host_allowlist()
    for raw_address in _resolved_addresses(host):
        address = ipaddress.ip_address(raw_address)
        non_public = (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_multicast or address.is_reserved or address.is_unspecified
        )
        if non_public and not allowlisted_private:
            raise ValueError(
                f'{purpose}: destinazione di rete non pubblica bloccata; '
                'aggiungere esplicitamente l host a CIR_OUTBOUND_PRIVATE_HOSTS se previsto.'
            )
    return host


def validate_outbound_ldap_uri(uri, *, purpose='LDAP'):
    """Validate ldap:// or ldaps:// destinations with the same network policy."""
    value = str(uri or '').strip()
    parsed = urlparse(value)
    if parsed.scheme not in {'ldap', 'ldaps'} or not parsed.hostname or not parsed.netloc:
        raise ValueError(f'{purpose}: usare un URI ldap:// o ldaps:// assoluto.')
    if parsed.username or parsed.password:
        raise ValueError(f'{purpose}: credenziali inline nell URI non consentite.')
    validate_outbound_host(parsed.hostname, purpose=purpose)
    if parsed.scheme != 'ldaps' and not _truthy(os.getenv('CIR_OUTBOUND_ALLOW_PLAINTEXT_LDAP')):
        raise ValueError(f'{purpose}: LDAPS obbligatorio; impostare CIR_OUTBOUND_ALLOW_PLAINTEXT_LDAP=1 solo se necessario.')
    return value
