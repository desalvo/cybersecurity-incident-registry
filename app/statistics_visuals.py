"""Privacy-scoped, presentation-ready statistics and password-protected exports.

Callers MUST supply incidents that have already passed tenant permission checks.
This module deliberately has no database access or implicit elevated queries.
"""
from collections import Counter
from datetime import datetime
import base64
import csv
import io
import json
import os
import re
from xml.etree import ElementTree as ET

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

BUBBLE_MODES = ('tenant', 'category', 'tenant_category')
DEFAULT_BUBBLE_LIMIT = 30
MAX_BUBBLE_LIMIT = 100
EXPORT_FORMATS = ('json', 'xml', 'csv')
PBKDF2_ITERATIONS = 600_000
AAD = b'CIR:statistics-export:v1'


def bubble_limit(value):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError('Numero di bolle non valido.') from None
    if not 1 <= result <= MAX_BUBBLE_LIMIT:
        raise ValueError(f'Sono ammesse da 1 a {MAX_BUBBLE_LIMIT} bolle.')
    return result


def incident_aggregates(incidents, tenant_names, mode):
    """Distinct incident/category counts; multiple categories count in each applicable group."""
    if mode not in BUBBLE_MODES:
        raise ValueError('Tipo di aggregazione non valido.')
    counts = Counter()
    for inc in incidents:
        tenant = tenant_names.get(inc.tenant_id, 'Senza tenant')
        if mode == 'tenant':
            counts[(tenant, '', inc.tenant_id)] += 1
            continue
        categories = {str(label.value).strip() for label in inc.categories if str(label.value).strip()}
        for category in categories:
            key = (tenant, category, inc.tenant_id) if mode == 'tenant_category' else ('', category, None)
            counts[key] += 1
    return [
        {'tenant': tenant, 'category': category, 'tenant_id': tid,
         'label': (tenant + ' · ' + category if mode == 'tenant_category' else tenant if mode == 'tenant' else category),
         'count': count}
        for (tenant, category, tid), count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0][0].casefold(), item[0][1].casefold()))
    ]


def _guard_csv(value):
    text = str(value if value is not None else '')
    if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + text
    return text


def export_bytes(payload, fmt):
    """Serialize only aggregate counts, never individual incident PII."""
    if fmt not in EXPORT_FORMATS:
        raise ValueError('Formato export non valido.')
    if fmt == 'json':
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8'), 'application/json'
    if fmt == 'csv':
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        writer.writerow(['Aggregazione', 'Ambito', 'Tenant', 'Categoria', 'Incidenti'])
        for r in payload['rows']:
            writer.writerow([_guard_csv(payload['mode']), _guard_csv(payload['scope']),
                             _guard_csv(r['tenant']), _guard_csv(r['category']), r['count']])
        return ('\ufeff' + buffer.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8'
    root = ET.Element('incidentStatistics', {'schemaVersion': str(payload['schema_version'])})
    for key in ('generated_at', 'scope', 'mode', 'start', 'end', 'total_incidents'):
        ET.SubElement(root, key).text = str(payload.get(key) or '')
    entries = ET.SubElement(root, 'rows')
    for item in payload['rows']:
        entry = ET.SubElement(entries, 'row')
        for key in ('tenant_id', 'tenant', 'category', 'count'):
            ET.SubElement(entry, key).text = str(item.get(key) if item.get(key) is not None else '')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True), 'application/xml'


def encrypt_export(data, password):
    """Authenticated encryption, password-derived AES-256 key, random salt and nonce."""
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        raise ValueError('La password deve contenere da 12 a 1024 caratteri.')
    salt, nonce = os.urandom(16), os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    key = kdf.derive(password.encode('utf-8'))
    ciphertext = AESGCM(key).encrypt(nonce, data, AAD)
    envelope = {
        'format': 'cir-statistics-encrypted-v1', 'cipher': 'AES-256-GCM',
        'kdf': 'PBKDF2-HMAC-SHA256', 'iterations': PBKDF2_ITERATIONS,
        'salt': base64.b64encode(salt).decode('ascii'),
        'nonce': base64.b64encode(nonce).decode('ascii'),
        'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
    }
    return json.dumps(envelope, sort_keys=True, separators=(',', ':')).encode('utf-8')


def decrypt_export(envelope, password):
    """Used by regression tests and future offline connectors."""
    doc = json.loads(envelope)
    if doc['format'] != 'cir-statistics-encrypted-v1' or doc['iterations'] != PBKDF2_ITERATIONS:
        raise ValueError('Versione del contenitore cifrato non supportata.')
    salt = base64.b64decode(doc['salt'], validate=True)
    nonce = base64.b64decode(doc['nonce'], validate=True)
    if len(salt) != 16 or len(nonce) != 12:
        raise ValueError('Metadati di cifratura non validi.')
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=PBKDF2_ITERATIONS).derive(password.encode('utf-8'))
    return AESGCM(key).decrypt(nonce, base64.b64decode(doc['ciphertext'], validate=True), AAD)
