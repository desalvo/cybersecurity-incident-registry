"""Shared public About identity for runtime, manuals and training materials.

Release VERSION/BUILD remain owned by release_metadata.  This module deliberately
has no Flask/database dependency, so source and CI generators use the same data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PLATFORM_MANIFEST = Path('app/static/branding/platforms/manifest.json')


def _text(environ, key, default, limit):
    value = str(environ.get(key, default)).strip() or default
    if len(value) > limit or any(ord(char) < 32 for char in value):
        raise ValueError(f'{key} is not a valid public application identity')
    return value


def read_application_identity(root=ROOT, environ=None):
    """Return validated public identity and locally packaged platform artwork."""
    root = Path(root)
    env = os.environ if environ is None else environ
    project_url = _text(env, 'APP_PROJECT_URL',
                        'https://github.com/desalvo/cybersecurity-incident-registry', 2048)
    parsed = urlsplit(project_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('APP_PROJECT_URL must be an HTTP(S) project URL without credentials')
    manifest = json.loads((root / PLATFORM_MANIFEST).read_text(encoding='utf-8'))
    platforms = []
    for item in manifest['platforms']:
        logo = Path(item['logo'])
        if logo.is_absolute() or '..' in logo.parts or not str(logo).startswith('branding/platforms/'):
            raise ValueError('Platform logo must be a packaged local branding asset')
        platforms.append({key: item[key] for key in ('id', 'name', 'logo', 'url')})
    return {
        'name': _text(env, 'APP_NAME', 'Cybersecurity Incident Registry', 160),
        'author': _text(env, 'APP_AUTHOR', 'Alessandro De Salvo', 160),
        'author_email': _text(env, 'APP_AUTHOR_EMAIL', 'Alessandro.DeSalvo@roma1.infn.it', 254),
        'project_url': project_url,
        'platforms': platforms,
        'architectures': ['linux/amd64', 'linux/arm64'],
    }
