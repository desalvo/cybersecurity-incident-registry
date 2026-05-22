"""Security guards for AI chatbot outbound calls."""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

DEFAULT_ENDPOINTS = {
    'chatgpt': 'https://api.openai.com/v1/chat/completions',
    'claude': 'https://api.anthropic.com/v1/messages',
    'gemini': '',
    'ollama': 'http://localhost:11434/api/chat',
    'perplexity': 'https://api.perplexity.ai/chat/completions',
}
PUBLIC_ALLOWED_HOSTS = {
    'chatgpt': {'api.openai.com'},
    'claude': {'api.anthropic.com'},
    'gemini': {'generativelanguage.googleapis.com'},
    'perplexity': {'api.perplexity.ai'},
}
LOCAL_ALLOWED_HOSTS = {'localhost', '127.0.0.1', '::1'}


def _truthy(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'si', 'sì'}


def _hostname_is_private(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f'Endpoint AI non risolvibile: {hostname}') from exc
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return True
    return False


def validate_ai_endpoint(endpoint: str, engine: str) -> str:
    """Validate and normalize an AI endpoint before saving or calling it.

    Public SaaS engines are restricted to their vendor hostnames by default.
    Ollama may use localhost HTTP for on-host deployments. Custom/private
    endpoints can be enabled explicitly with CIR_AI_ALLOW_CUSTOM_ENDPOINTS=1,
    but private network targets remain blocked unless
    CIR_AI_ALLOW_PRIVATE_ENDPOINTS=1 is also set.
    """
    endpoint = (endpoint or '').strip()
    if not endpoint:
        return endpoint
    parsed = urlparse(endpoint)
    if parsed.scheme not in {'https', 'http'} or not parsed.netloc or not parsed.hostname:
        raise ValueError('Endpoint AI non valido: usare un URL http(s) assoluto.')
    host = parsed.hostname.lower()
    if parsed.username or parsed.password:
        raise ValueError('Endpoint AI non valido: credenziali inline non consentite.')
    engine = (engine or '').strip().lower()
    if engine == 'ollama' and host in LOCAL_ALLOWED_HOSTS and parsed.scheme == 'http':
        return endpoint
    allowed_hosts = PUBLIC_ALLOWED_HOSTS.get(engine, set())
    custom_allowed = _truthy(os.getenv('CIR_AI_ALLOW_CUSTOM_ENDPOINTS'))
    if allowed_hosts and host not in allowed_hosts and not custom_allowed:
        raise ValueError('Endpoint AI non consentito per il motore selezionato.')
    if parsed.scheme != 'https' and not custom_allowed:
        raise ValueError('Endpoint AI pubblico deve usare HTTPS.')
    if not _truthy(os.getenv('CIR_AI_ALLOW_PRIVATE_ENDPOINTS')) and _hostname_is_private(host):
        raise ValueError('Endpoint AI verso reti private/locali non consentito.')
    return endpoint
