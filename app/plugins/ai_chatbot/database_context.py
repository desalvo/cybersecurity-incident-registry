"""Sanitized database context for the AI Chatbot plugin.

This module intentionally lives inside the plugin and exposes only a redacted,
read-only view of the application database. Personal data, credentials, secrets,
binary payloads and free-text fields that may contain sensitive information are
excluded before any context is sent to an external AI engine.
"""
import json
from datetime import date, datetime, time
from decimal import Decimal
from flask import current_app
from sqlalchemy import func
from flask_login import current_user
from ...models import db
from ...routes import setting_value, current_tenant_id, is_superuser

# Tables entirely excluded because their content is inherently personal,
# credential-like, binary, or already injected through the dedicated chatbot KB.
EXCLUDED_TABLES = {
    'user',
    'mfa_totp_token',
    'external_recipient',
    'ai_chatbot_document',
    'form_template_binary',
}

# Columns excluded wherever they appear.
GLOBAL_EXCLUDED_COLUMN_NAMES = {
    'password', 'password_hash', 'secret', 'client_secret', 'api_key', 'token',
    'access_token', 'refresh_token', 'pdf_data', 'file_data', 'binary_data',
    'email', 'recipient_email', 'creator_email', 'cc_emails', 'last_recipients',
}

# Substrings that mark credential/sensitive columns.
GLOBAL_EXCLUDED_COLUMN_PARTS = (
    'password', 'secret', 'token', 'api_key', 'credential', 'certificate',
    'private_key', 'smtp_password', 'bind_password', 'client_secret',
)

# Table-specific personal/free text exclusions. The remaining fields are useful
# to understand application state/configuration without exposing personal data.
TABLE_COLUMN_DENYLIST = {
    'incident': {
        'name', 'reference', 'recipient', 'recipient_email', 'description',
        'data_volume', 'creator_name', 'creator_email',
    },
    'incident_template': {
        'incident_name', 'reference', 'recipient', 'recipient_email',
        'incident_description', 'data_volume',
    },
    'action': {'person_name', 'description', 'consequence_text'},
    'action_attachment': {'filename', 'stored_name'},
    'document': {'filename', 'stored_name'},
    'incident_reminder': {'message', 'cc_emails', 'last_error'},
    'audit_log': {'username', 'user_id', 'details'},
    'setting': set(),  # handled with key filtering below
}

# Settings that are operational and safe enough to expose to the AI model.
SAFE_SETTING_KEYS = {
    'application_timezone', 'interface_language', 'application_external_url',
    'notification_deadline_enabled', 'notification_deadline_schedule_mode',
    'notification_deadline_interval_hours', 'notification_deadline_interval_minutes',
    'notification_deadline_poll_seconds', 'notification_incident_reminder_poll_seconds',
    'audit_retention_months', 'audit_records_per_page', 'audit_max_records',
    'plugin_ai_chatbot_enabled', 'ai_chatbot_engine', 'recommendations_max_per_incident',
    'ssl_enabled', 'sso_enabled', 'sso_provider_name', 'sso_auto_create_users',
    'sso_default_role', 'ldap_uri', 'smtp_host', 'smtp_port', 'smtp_use_tls',
    'smtp_use_ssl', 'smtp_auth_enabled', 'documentation_location',
    'privacy_authority_non_notification_reason',
    'ai_chatbot_include_database_context',
}




def _tenant_filtered_statement(table, columns=None):
    stmt = db.select(*(columns or [table]))
    if 'tenant_id' in table.c and not is_superuser():
        stmt = stmt.where(table.c.tenant_id == current_tenant_id())
    return stmt

def _tenant_filtered_count(table):
    stmt = db.select(func.count()).select_from(table)
    if 'tenant_id' in table.c and not is_superuser():
        stmt = stmt.where(table.c.tenant_id == current_tenant_id())
    return db.session.execute(stmt).scalar() or 0

def _json_default(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _column_allowed(table_name, column_name):
    lowered = column_name.lower()
    if column_name in TABLE_COLUMN_DENYLIST.get(table_name, set()):
        return False
    if lowered in GLOBAL_EXCLUDED_COLUMN_NAMES:
        return False
    if any(part in lowered for part in GLOBAL_EXCLUDED_COLUMN_PARTS):
        return False
    return True


def _sanitize_setting_row(row):
    key = row.get('key')
    if key not in SAFE_SETTING_KEYS:
        return None
    return {'key': key, 'value': row.get('value', '')}


def _table_payload(table, row_limit):
    table_name = table.name
    total = _tenant_filtered_count(table)
    columns = [c for c in table.columns if _column_allowed(table_name, c.name)]
    rows = []
    if columns and row_limit > 0:
        stmt = _tenant_filtered_statement(table, columns).limit(row_limit)
        for raw in db.session.execute(stmt).mappings():
            row = dict(raw)
            if table_name == 'setting':
                row = _sanitize_setting_row(row)
                if row is None:
                    continue
            rows.append(row)
    return {
        'table': table_name,
        'total_rows': int(total),
        'included_columns': [c.name for c in columns],
        'rows': rows,
        'redaction': 'dati personali, segreti, credenziali, allegati binari e contenuti potenzialmente sensibili esclusi',
    }


def sanitized_database_context(max_chars=100000, row_limit_per_table=200):
    """Return a JSON database snapshot safe for AI context injection."""
    payload = {
        'description': (
            'Snapshot sanitizzato del database applicativo corrente. Sono stati esclusi dati personali, '
            'dati sensibili, credenziali, token, contenuti binari, indirizzi e-mail e testo libero che può '
            'contenere informazioni personali.'
        ),
        'tables': [],
    }
    try:
        db.metadata.reflect(bind=db.engine)
        for table in db.metadata.sorted_tables:
            if table.name in EXCLUDED_TABLES:
                payload['tables'].append({
                    'table': table.name,
                    'excluded': True,
                    'reason': 'tabella personale/sensibile/binaria o gestita da knowledge base dedicata',
                })
                continue
            try:
                payload['tables'].append(_table_payload(table, row_limit_per_table))
            except Exception as exc:
                current_app.logger.exception('Unable to add table %s to AI chatbot sanitized context', table.name)
                payload['tables'].append({'table': table.name, 'error': str(exc)[:200]})
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
        if len(text) > max_chars:
            text = text[:max_chars] + '\n... [snapshot sanitizzato troncato per limite contesto]'
        return text
    except Exception as exc:
        current_app.logger.exception('Unable to build AI chatbot database context')
        return json.dumps({'error': f'Contesto database non disponibile: {str(exc)[:200]}'}, ensure_ascii=False)


def database_context_enabled():
    try:
        return setting_value('ai_chatbot_include_database_context', '0') == '1'
    except Exception:
        return False
