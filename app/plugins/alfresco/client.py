import os
from pathlib import Path
from urllib.parse import urljoin
import requests
from flask import current_app
from ...routes import setting_value

DEFAULTS = {
    'enabled': '0',
    'base_url': '',
    'username': '',
    'password': '',
    'site': '',
    'target_path': 'Cybersecurity Incident Registry',
    'verify_tls': '1',
    'timeout': '30',
}


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'si', 'sì'}


def is_enabled():
    try:
        return _truthy(setting_value('plugin_alfresco_enabled', DEFAULTS['enabled']))
    except Exception:
        return False


def config():
    return {
        'enabled': is_enabled(),
        'base_url': setting_value('alfresco_base_url', DEFAULTS['base_url']).rstrip('/'),
        'username': setting_value('alfresco_username', DEFAULTS['username']),
        'password': setting_value('alfresco_password', DEFAULTS['password']),
        'site': setting_value('alfresco_site', DEFAULTS['site']).strip(),
        'target_path': setting_value('alfresco_target_path', DEFAULTS['target_path']).strip('/'),
        'verify_tls': _truthy(setting_value('alfresco_verify_tls', DEFAULTS['verify_tls'])),
        'timeout': int(setting_value('alfresco_timeout', DEFAULTS['timeout']) or DEFAULTS['timeout']),
    }


def reset_defaults(setter):
    setter('plugin_alfresco_enabled', DEFAULTS['enabled'])
    for key in ('base_url', 'username', 'password', 'site', 'target_path', 'verify_tls', 'timeout'):
        setter(f'alfresco_{key}', DEFAULTS[key])


def _api_url(cfg, suffix):
    base = cfg['base_url'].rstrip('/') + '/'
    return urljoin(base, 'alfresco/api/-default-/public/alfresco/versions/1/' + suffix.lstrip('/'))


def _auth(cfg):
    if not cfg.get('username'):
        raise RuntimeError('Username Alfresco non configurato.')
    return (cfg.get('username') or '', cfg.get('password') or '')


def _parent_node_ref(cfg):
    site = cfg.get('site')
    if site:
        return f'-root-/children?relativePath=Sites/{site}/documentLibrary'
    return '-root-/children'


def upload_file(local_path, filename, incident_id=None, mimetype=None):
    cfg = config()
    if not cfg['enabled']:
        raise RuntimeError('Plugin Alfresco non abilitato.')
    if not cfg['base_url']:
        raise RuntimeError('Endpoint Alfresco non configurato.')
    path = Path(local_path)
    if not path.exists():
        raise RuntimeError(f'File locale non trovato: {filename}')
    relative_path = cfg['target_path']
    if incident_id:
        relative_path = '/'.join(x for x in [relative_path, f'incident-{incident_id}'] if x)
    url = _api_url(cfg, _parent_node_ref(cfg))
    data = {
        'name': filename,
        'nodeType': 'cm:content',
        'relativePath': relative_path,
        'overwrite': 'true',
    }
    request_timeout = float(cfg.get('timeout') or 20)
    verify_tls = bool(cfg.get('verify_tls', True))
    with path.open('rb') as fh:
        files = {'filedata': (filename, fh, mimetype or 'application/octet-stream')}
        response = requests.post(url, auth=_auth(cfg), data=data, files=files, timeout=request_timeout, verify=verify_tls)
    if response.status_code >= 400:
        raise RuntimeError(f'Errore upload Alfresco {response.status_code}: {response.text[:300]}')
    entry = (response.json() or {}).get('entry') or {}
    node_id = entry.get('id')
    if not node_id:
        raise RuntimeError('Risposta Alfresco priva di node id.')
    return {
        'node_id': node_id,
        'name': entry.get('name') or filename,
        'path': '/'.join(x for x in [relative_path, entry.get('name') or filename] if x),
    }


def download_file(node_id):
    cfg = config()
    if not cfg['enabled']:
        raise RuntimeError('Plugin Alfresco non abilitato.')
    if not cfg['base_url']:
        raise RuntimeError('Endpoint Alfresco non configurato.')
    if not node_id:
        raise RuntimeError('Node id Alfresco non disponibile per questo documento.')
    url = _api_url(cfg, f'nodes/{node_id}/content')
    request_timeout = float(cfg.get('timeout') or 20)
    verify_tls = bool(cfg.get('verify_tls', True))
    response = requests.get(url, auth=_auth(cfg), timeout=request_timeout, verify=verify_tls)
    if response.status_code >= 400:
        raise RuntimeError(f'Errore download Alfresco {response.status_code}: {response.text[:300]}')
    return response.content, response.headers.get('Content-Type') or 'application/octet-stream'
