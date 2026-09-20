import re
import unicodedata
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from ...routes import setting_value, current_tenant_id, default_tenant, decrypt_setting_value
from ...models import db, Setting
from ...outbound_security import validate_outbound_http_url

DEFAULTS = {
    'enabled': '0',
    'base_url': '',
    'username': '',
    'password': '',
    'site': '',
    'parent_node_id': '',
    'target_path': 'Cybersecurity Incident Registry',
    'group_by_type': '1',
    'verify_tls': '1',
    'timeout': '30',
}

_NODE_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$')


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'si', 'sì'}



def _tenant_alfresco_setting(key, default=''):
    """Read an Alfresco setting without cross-tenant legacy fallback.

    Existing unscoped legacy values are accepted only for the default tenant.
    Every other tenant must have its own tenant:<id>: key, preventing accidental
    credential/destination inheritance from the historical single-tenant setup.
    """
    tid = current_tenant_id()
    if not tid:
        return setting_value(key, default)
    physical = f'tenant:{int(tid)}:{key}'
    row = db.session.get(Setting, physical)
    if row is not None and row.value is not None:
        return decrypt_setting_value(key, row.value)
    try:
        if int(tid) == int(default_tenant().id):
            legacy = db.session.get(Setting, key)
            if legacy is not None and legacy.value is not None:
                return decrypt_setting_value(key, legacy.value)
    except Exception:
        pass
    return default

def is_enabled():
    try:
        return _truthy(_tenant_alfresco_setting('plugin_alfresco_enabled', DEFAULTS['enabled']))
    except Exception:
        return False


def config():
    return {
        'enabled': is_enabled(),
        'base_url': _tenant_alfresco_setting('alfresco_base_url', DEFAULTS['base_url']).rstrip('/'),
        'username': _tenant_alfresco_setting('alfresco_username', DEFAULTS['username']),
        'password': _tenant_alfresco_setting('alfresco_password', DEFAULTS['password']),
        'site': _tenant_alfresco_setting('alfresco_site', DEFAULTS['site']).strip(),
        'parent_node_id': _tenant_alfresco_setting('alfresco_parent_node_id', DEFAULTS['parent_node_id']).strip(),
        'target_path': _tenant_alfresco_setting('alfresco_target_path', DEFAULTS['target_path']).strip('/'),
        'group_by_type': _truthy(_tenant_alfresco_setting('alfresco_group_by_type', DEFAULTS['group_by_type'])),
        'verify_tls': _truthy(_tenant_alfresco_setting('alfresco_verify_tls', DEFAULTS['verify_tls'])),
        'timeout': int(_tenant_alfresco_setting('alfresco_timeout', DEFAULTS['timeout']) or DEFAULTS['timeout']),
    }


def reset_defaults(setter):
    setter('plugin_alfresco_enabled', DEFAULTS['enabled'])
    for key in ('base_url', 'username', 'password', 'site', 'parent_node_id', 'target_path', 'group_by_type', 'verify_tls', 'timeout'):
        setter(f'alfresco_{key}', DEFAULTS[key])


def _api_url(cfg, suffix):
    base = validate_outbound_http_url(cfg['base_url'], purpose='Alfresco base URL').rstrip('/') + '/'
    url = urljoin(base, 'alfresco/api/-default-/public/alfresco/versions/1/' + suffix.lstrip('/'))
    return validate_outbound_http_url(url, purpose='Alfresco API URL')


def _auth(cfg):
    if not cfg.get('username'):
        raise RuntimeError('Username Alfresco non configurato.')
    return (cfg.get('username') or '', cfg.get('password') or '')


def _request_options(cfg):
    return {
        'auth': _auth(cfg),
        'timeout': float(cfg.get('timeout') or 20),
        'verify': bool(cfg.get('verify_tls', True)),
        'allow_redirects': False,
    }


def _validate_node_id(value):
    node_id = str(value or '').strip()
    if not node_id or not _NODE_ID_RE.fullmatch(node_id):
        raise RuntimeError('Parent Node ID Alfresco non valido.')
    return node_id


def _resolve_site_document_library(cfg):
    site = str(cfg.get('site') or '').strip()
    if not site:
        return None
    url = _api_url(cfg, f'sites/{quote(site, safe="")}/containers/documentLibrary')
    response = requests.get(url, **_request_options(cfg))
    if response.status_code >= 400:
        raise RuntimeError(f'Impossibile risolvere la Document Library del site Alfresco {site!r}: HTTP {response.status_code}.')
    entry = (response.json() or {}).get('entry') or {}
    node_id = entry.get('id') or entry.get('folderId')
    if not node_id:
        raise RuntimeError(f'La risposta Alfresco per il site {site!r} non contiene il node id della Document Library.')
    return _validate_node_id(node_id)


def resolve_parent_node_id(cfg=None):
    cfg = cfg or config()
    explicit = str(cfg.get('parent_node_id') or '').strip()
    if explicit:
        return _validate_node_id(explicit)
    site_node = _resolve_site_document_library(cfg)
    if site_node:
        return site_node
    raise RuntimeError(
        'Destinazione Alfresco non configurata: impostare Parent Node ID oppure un Site Alfresco valido. '
        'Il plugin non usa piu il pseudo-nodo -root-, non supportato da alcune versioni/configurazioni Alfresco.'
    )


def test_destination(cfg=None):
    cfg = cfg or config()
    if not cfg.get('base_url'):
        raise RuntimeError('Endpoint Alfresco non configurato.')
    node_id = resolve_parent_node_id(cfg)
    url = _api_url(cfg, f'nodes/{quote(node_id, safe="")}')
    response = requests.get(url, **_request_options(cfg))
    if response.status_code >= 400:
        raise RuntimeError(f'Parent node Alfresco non accessibile: HTTP {response.status_code}.')
    entry = (response.json() or {}).get('entry') or {}
    return {
        'node_id': entry.get('id') or node_id,
        'name': entry.get('name') or '',
        'node_type': entry.get('nodeType') or '',
    }


def _incident_storage_basename(incident_id, incident_name=None):
    """Return a readable, Alfresco-safe and collision-resistant incident name."""
    iid = int(incident_id)
    raw = unicodedata.normalize('NFKC', str(incident_name or '').strip())
    # Alfresco paths cannot contain separators; also remove control characters
    # and characters that are problematic across common filesystems/clients.
    raw = ''.join(' ' if ord(ch) < 32 else ch for ch in raw)
    raw = re.sub(r'[\\/:*?"<>|]+', '-', raw)
    raw = re.sub(r'\s+', ' ', raw).strip(' .-')
    if not raw:
        raw = 'Incidente'
    # Keep the whole component at a conservative length while preserving the ID.
    raw = raw[:110].rstrip(' .-') or 'Incidente'
    return f'incident-{iid} - {raw}'


def incident_folder_name(incident_id, incident_name=None):
    return _incident_storage_basename(incident_id, incident_name)


def incident_report_filename(incident_id, incident_name=None):
    return f'{_incident_storage_basename(incident_id, incident_name)} - report.pdf'


def _document_type_folder(filename):
    ext = Path(filename or '').suffix.lower()
    if ext == '.pdf':
        return 'pdf'
    if ext in {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'}:
        return 'office'
    if ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.tif', '.tiff'}:
        return 'images'
    if ext in {'.zip', '.gz', '.tgz', '.tar', '.7z'}:
        return 'archives'
    if ext in {'.txt', '.csv', '.json', '.xml', '.md', '.log'}:
        return 'data'
    return 'other'


def upload_file(local_path, filename, incident_id=None, incident_name=None, mimetype=None, group_by_type=None):
    cfg = config()
    if not cfg['enabled']:
        raise RuntimeError('Plugin Alfresco non abilitato.')
    if not cfg['base_url']:
        raise RuntimeError('Endpoint Alfresco non configurato.')
    path = Path(local_path)
    if not path.exists():
        raise RuntimeError(f'File locale non trovato: {filename}')

    parent_node_id = resolve_parent_node_id(cfg)
    relative_path = cfg['target_path']
    if incident_id:
        relative_path = '/'.join(x for x in [relative_path, incident_folder_name(incident_id, incident_name)] if x)
    use_group_by_type = cfg.get('group_by_type') if group_by_type is None else bool(group_by_type)
    if use_group_by_type:
        relative_path = '/'.join(x for x in [relative_path, _document_type_folder(filename)] if x)
    url = _api_url(cfg, f'nodes/{quote(parent_node_id, safe="")}/children')
    data = {
        'name': filename,
        'nodeType': 'cm:content',
        'relativePath': relative_path,
        'overwrite': 'true',
    }
    with path.open('rb') as fh:
        files = {'filedata': (filename, fh, mimetype or 'application/octet-stream')}
        response = requests.post(url, data=data, files=files, **_request_options(cfg))
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


def upload_or_update_incident_report(local_path, filename, incident_id, incident_name=None, existing_node_id=None):
    """Create or replace the canonical PDF report for one incident."""
    cfg = config()
    if not cfg['enabled']:
        raise RuntimeError('Plugin Alfresco non abilitato.')
    if not cfg['base_url']:
        raise RuntimeError('Endpoint Alfresco non configurato.')
    path = Path(local_path)
    if not path.exists() or not path.is_file():
        raise RuntimeError('Report incidente locale non disponibile.')
    node_id = str(existing_node_id or '').strip()
    if node_id:
        node_id = _validate_node_id(node_id)
        url = _api_url(cfg, f'nodes/{quote(node_id, safe="")}/content')
        with path.open('rb') as fh:
            files = {'filedata': (filename, fh, 'application/pdf')}
            response = requests.put(url, files=files, **_request_options(cfg))
        if response.status_code < 400:
            relative_path = '/'.join(x for x in [cfg['target_path'], incident_folder_name(incident_id, incident_name), filename] if x)
            return {'node_id': node_id, 'name': filename, 'path': relative_path}
        if response.status_code not in {404, 410}:
            raise RuntimeError(f'Errore aggiornamento report Alfresco {response.status_code}: {response.text[:300]}')
    return upload_file(str(path), filename, incident_id=incident_id, incident_name=incident_name, mimetype='application/pdf', group_by_type=False)



def node_status(node_id):
    """Return present/missing for an Alfresco node without modifying it."""
    cfg = config()
    if not cfg['enabled']:
        raise RuntimeError('Plugin Alfresco non abilitato.')
    node_id = _validate_node_id(node_id)
    url = _api_url(cfg, f'nodes/{quote(node_id, safe="")}')
    response = requests.get(url, **_request_options(cfg))
    if response.status_code in {404, 410}:
        return {'status': 'missing', 'node_id': node_id}
    if response.status_code >= 400:
        raise RuntimeError(f'Errore verifica nodo Alfresco {response.status_code}: {response.text[:300]}')
    entry = (response.json() or {}).get('entry') or {}
    return {'status': 'present', 'node_id': entry.get('id') or node_id, 'name': entry.get('name') or '', 'node_type': entry.get('nodeType') or ''}


def delete_file(node_id, permanent=False):
    """Delete a node from Alfresco. By default Alfresco may retain it in its trashcan."""
    cfg = config()
    if not cfg['enabled']:
        raise RuntimeError('Plugin Alfresco non abilitato.')
    node_id = _validate_node_id(node_id)
    suffix = f'nodes/{quote(node_id, safe="")}'
    url = _api_url(cfg, suffix)
    response = requests.delete(url, params={'permanent': 'true' if permanent else 'false'}, **_request_options(cfg))
    if response.status_code in {404, 410}:
        return {'status': 'missing', 'node_id': node_id, 'already_missing': True}
    if response.status_code >= 400:
        raise RuntimeError(f'Errore cancellazione Alfresco {response.status_code}: {response.text[:300]}')
    return {'status': 'missing', 'node_id': node_id, 'already_missing': False}

def download_file(node_id):
    cfg = config()
    if not cfg['enabled']:
        raise RuntimeError('Plugin Alfresco non abilitato.')
    if not cfg['base_url']:
        raise RuntimeError('Endpoint Alfresco non configurato.')
    node_id = _validate_node_id(node_id)
    url = _api_url(cfg, f'nodes/{quote(node_id, safe="")}/content')
    response = requests.get(url, **_request_options(cfg))
    if response.status_code >= 400:
        raise RuntimeError(f'Errore download Alfresco {response.status_code}: {response.text[:300]}')
    return response.content, response.headers.get('Content-Type') or 'application/octet-stream'
