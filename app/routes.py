import os, csv, io, json, tarfile, uuid, shutil, tempfile, smtplib, base64, secrets, re, sys, copy
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from . import APP_RELEASE_VERSION, APP_RELEASE_BUILD
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, send_from_directory, current_app, Response, abort, session, g, has_app_context, has_request_context, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from sqlalchemy import or_, and_, text, Table, MetaData, select, func, inspect
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError
from ldap3 import Server, Connection, ALL
from ldap3.utils.conv import escape_filter_chars
from urllib.parse import urlencode, parse_qsl
from cryptography.fernet import Fernet, InvalidToken
import hashlib
import requests
import threading, time
import pyotp
import qrcode
from .models import *
from .auth import verify_password, hash_password
from .reports import incident_pdf, statistics_pdf
from .form_generation import list_templates, available_incident_fields, FormFieldMapping, generate_pdf_from_template, analyze_pdf_template, save_template_pdf, get_template_config, save_template_config, missing_required_incident_fields_for_templates, format_missing_required_incident_fields, incident_measures
from .consequences import incident_consequence_list, configured_consequence_rules, serialize_consequence_rules_from_form
from .text_filters import strip_markdown_formatting
from .timeutils import utcnow
from . import restore_missing_default_config_labels, DEFAULT_CONFIG_LABELS
from .route_modules.tenancy import TENANT_SHARED_CONFIGURATION_KEYS, TENANT_SCOPED_ADMIN_AREAS, TENANT_SHARED_ADMIN_AREAS
from .route_modules.permissions import accessible_tenant_ids as _accessible_tenant_ids, is_builtin_admin_account, is_global_superuser, role_for_tenant as _role_for_tenant
from .route_modules.scheduler_lifecycle import background_schedulers_disabled as _background_schedulers_disabled_impl, stop_threads as _stop_scheduler_threads
bp=Blueprint('main',__name__)

GLOBAL_SETTING_KEYS = set(TENANT_SHARED_CONFIGURATION_KEYS)
TENANT_SCOPED_MODELS = ()  # populated lazily after models are imported

MAX_UPLOAD_SIZE_MB_SETTING = 'max_upload_size_mb'
DEFAULT_MAX_UPLOAD_SIZE_MB = 25
MAX_UPLOAD_SIZE_MB_MIN = 1
MAX_UPLOAD_SIZE_MB_MAX = 2048


def parse_max_upload_size_mb(value, default=DEFAULT_MAX_UPLOAD_SIZE_MB):
    try:
        text = str(value if value is not None else '').strip().replace(',', '.')
        if not text:
            raise ValueError
        number = float(text)
    except (TypeError, ValueError):
        number = float(default)
    if number < MAX_UPLOAD_SIZE_MB_MIN:
        number = float(MAX_UPLOAD_SIZE_MB_MIN)
    if number > MAX_UPLOAD_SIZE_MB_MAX:
        number = float(MAX_UPLOAD_SIZE_MB_MAX)
    return int(number)


def configured_max_upload_size_mb(default=DEFAULT_MAX_UPLOAD_SIZE_MB):
    try:
        return parse_max_upload_size_mb(setting_value(MAX_UPLOAD_SIZE_MB_SETTING, str(default)), default=default)
    except Exception:
        return parse_max_upload_size_mb(os.environ.get('MAX_CONTENT_LENGTH_MB') or os.environ.get('MAX_UPLOAD_SIZE_MB') or default, default=default)


def configured_max_upload_size_bytes(default=DEFAULT_MAX_UPLOAD_SIZE_MB):
    return configured_max_upload_size_mb(default=default) * 1024 * 1024


def apply_configured_max_upload_size(app=None):
    app = app or current_app
    size_bytes = configured_max_upload_size_bytes()
    app.config['MAX_CONTENT_LENGTH'] = size_bytes
    # Werkzeug/Flask 3.x applica anche un limite separato alla dimensione
    # dei campi form non-file (MAX_FORM_MEMORY_SIZE). Gli import workflow
    # usano una preview intermedia: senza questo allineamento un JSON da pochi
    # MB poteva ricevere 413 anche con MAX_CONTENT_LENGTH a 25 MB.
    app.config['MAX_FORM_MEMORY_SIZE'] = size_bytes
    return size_bytes



def _workflow_import_cache_dir():
    base = current_app.config.get('WORKFLOW_IMPORT_DIR') or os.path.join(current_app.instance_path, 'workflow_imports')
    os.makedirs(base, exist_ok=True)
    return base


def _workflow_import_cache_path(token):
    token = str(token or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', token):
        raise ValueError('Token import workflow non valido.')
    return os.path.join(_workflow_import_cache_dir(), token + '.json')


def store_workflow_import_payload(payload):
    token = secrets.token_urlsafe(32)
    path = _workflow_import_cache_path(token)
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    with open(path, 'wb') as handle:
        handle.write(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    session['workflow_import_token'] = token
    return token


def load_workflow_import_payload(token, remove=False):
    expected = session.get('workflow_import_token')
    if expected and token != expected:
        raise ValueError('Token import workflow non coerente con la sessione.')
    path = _workflow_import_cache_path(token)
    try:
        with open(path, 'rb') as handle:
            payload = json.loads(handle.read().decode('utf-8'))
    except FileNotFoundError as exc:
        raise ValueError('Anteprima import workflow scaduta o non trovata. Ricaricare il file JSON.') from exc
    if remove:
        try:
            os.remove(path)
        except OSError:
            pass
        if session.get('workflow_import_token') == token:
            session.pop('workflow_import_token', None)
    return payload


def cleanup_old_workflow_import_payloads(max_age_seconds=24 * 60 * 60):
    try:
        base = _workflow_import_cache_dir()
        now = time.time()
        for name in os.listdir(base):
            if not name.endswith('.json'):
                continue
            path = os.path.join(base, name)
            try:
                if now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
            except OSError:
                pass
    except Exception:
        pass


@bp.app_errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(exc):
    try:
        max_mb = configured_max_upload_size_mb()
    except Exception:
        max_mb = DEFAULT_MAX_UPLOAD_SIZE_MB
    message = f'Upload troppo grande. La dimensione massima configurata è {max_mb} MB. Puoi modificarla da Admin → Altre configurazioni.'
    wants_json = request.accept_mimetypes.best == 'application/json' or request.path.startswith('/api/')
    if wants_json:
        return jsonify({'error': message, 'max_upload_size_mb': max_mb}), 413
    target = request.referrer or url_for('main.admin_other_configurations')
    return (
        '<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Upload troppo grande</title></head>'
        '<body><h1>Upload troppo grande</h1>'
        f'<p>{message}</p><p><a href="{target}">Torna alla pagina precedente</a></p></body></html>'
    ), 413

def tenant_setting_key(key, tenant_id=None):
    """Return the physical Setting.key, keeping global settings shared."""
    key = str(key or '')
    if key in GLOBAL_SETTING_KEYS:
        return key
    tid = tenant_id if tenant_id is not None else current_tenant_id(default_to_default=True)
    if not tid:
        return key
    return f'tenant:{int(tid)}:{key}'


def is_builtin_admin_user(user=None):
    user = user or current_user
    return bool(getattr(user, 'is_authenticated', False) and is_builtin_admin_account(user))


def is_superuser(user=None):
    user = user or current_user
    return bool(getattr(user, 'is_authenticated', False) and is_global_superuser(user))


def user_role_for_tenant(user=None, tenant_id=None):
    user = user or current_user
    if not getattr(user, 'is_authenticated', False):
        return 'disabled'
    tid = tenant_id if tenant_id is not None else current_tenant_id(default_to_default=True)
    return _role_for_tenant(user, tid)


def user_accessible_tenant_ids(user=None, roles=None):
    user = user or current_user
    if not getattr(user, 'is_authenticated', False):
        return []
    return _accessible_tenant_ids(user, roles=roles)


def default_tenant():
    tenant = Tenant.query.filter_by(name='default').first()
    if tenant is None:
        tenant = Tenant(name='default', description='Tenant predefinito')
        db.session.add(tenant)
        db.session.flush()
    return tenant


def active_tenant_id(default_to_default=True):
    """Tenant operativo per dati e configurazioni tenant-specifiche.

    Il tenant attivo in sessione ha sempre precedenza. In assenza di scelta
    esplicita si usa il tenant attivo predefinito dell'utente; i vecchi campi
    ``User.tenant_id``/``User.role`` sono solo fallback di migrazione.
    """
    if getattr(current_user, 'is_authenticated', False):
        raw_tid = session.get('active_tenant_id')
        if raw_tid:
            try:
                tid = int(raw_tid)
                if db.session.get(Tenant, tid) and (is_superuser() or tid in (user_accessible_tenant_ids() or [])):
                    return tid
            except Exception:
                session.pop('active_tenant_id', None)
        ids = user_accessible_tenant_ids()
        default_tid = getattr(current_user, 'default_tenant_id', None)
        if default_tid and db.session.get(Tenant, int(default_tid)) and (is_superuser() or int(default_tid) in (ids or [])):
            return int(default_tid)
        ids = ids or []
        if ids:
            return ids[0]
        # Fallback esclusivamente per database/import legacy senza membership.
        legacy_tid = getattr(current_user, 'tenant_id', None)
        if legacy_tid and db.session.get(Tenant, int(legacy_tid)) and (is_superuser() or user_role_for_tenant(current_user, legacy_tid) != 'disabled'):
            return int(legacy_tid)
        if is_superuser():
            return default_tenant().id if default_to_default else None
    if default_to_default:
        try:
            return default_tenant().id
        except Exception:
            return None
    return None


def current_tenant_id(default_to_default=True):
    return active_tenant_id(default_to_default=default_to_default)


def current_tenant(default_to_default=True):
    tid = current_tenant_id(default_to_default=default_to_default)
    return db.session.get(Tenant, int(tid)) if tid else None


def tenant_query(model, include_all_for_superuser=False):
    q = model.query
    if hasattr(model, 'tenant_id'):
        if include_all_for_superuser and is_superuser():
            return q
        tid = current_tenant_id()
        if is_superuser():
            q = q.filter(or_(model.tenant_id == tid, model.tenant_id.is_(None)))
        else:
            q = q.filter(or_(model.tenant_id == tid, model.tenant_id.is_(None)))
    return q


def assign_current_tenant(obj, tenant_id=None):
    if hasattr(obj, 'tenant_id') and not getattr(obj, 'tenant_id', None):
        obj.tenant_id = tenant_id if tenant_id is not None else current_tenant_id()
    return obj




def sync_user_legacy_identity(user):
    """Mirror default-tenant membership into legacy fields for old code/imports.

    UI and authorization do not expose these fields anymore. They are kept in
    sync so old backups, tests and external scripts that still read User.role or
    User.tenant_id keep receiving a coherent value.
    """
    if not user:
        return
    if getattr(user, 'is_builtin_admin', False):
        user.role = 'superuser'
        user.tenant_id = getattr(user, 'tenant_id', None) or default_tenant().id
        user.default_tenant_id = None
        return
    memberships = [m for m in (user.tenant_roles or []) if m.normalized_role() != 'disabled']
    if any(m.normalized_role() == 'superuser' for m in memberships):
        user.role = 'superuser'
    else:
        default_tid = getattr(user, 'default_tenant_id', None)
        selected = next((m for m in memberships if m.tenant_id == default_tid), None)
        if selected is None:
            selected = memberships[0] if memberships else None
        if selected:
            if not default_tid:
                user.default_tenant_id = selected.tenant_id
            user.tenant_id = selected.tenant_id
            user.role = selected.normalized_role()
        else:
            user.tenant_id = None
            user.default_tenant_id = None
            user.role = 'disabled'

def upsert_user_tenant_role(user, tenant_id, role):
    if not user or not tenant_id:
        return None
    normalized = (role or 'disabled').strip().lower() or 'disabled'
    membership = UserTenantRole.query.filter_by(user_id=user.id, tenant_id=int(tenant_id)).first()
    if membership is None:
        membership = UserTenantRole(user_id=user.id, tenant_id=int(tenant_id), role=normalized)
        db.session.add(membership)
    else:
        membership.role = normalized
    if normalized != 'disabled' and not getattr(user, 'default_tenant_id', None):
        user.default_tenant_id = int(tenant_id)
    sync_user_legacy_identity(user)
    return membership


def remove_user_tenant_role(user, tenant_id):
    membership = UserTenantRole.query.filter_by(user_id=user.id, tenant_id=int(tenant_id)).first()
    if membership:
        db.session.delete(membership)
        db.session.flush()
        sync_user_legacy_identity(user)



def _copy_label_to_tenant(label, target_tenant_id):
    if label is None:
        return None
    existing = ConfigLabel.query.filter_by(tenant_id=target_tenant_id, kind=label.kind, value=label.value).first()
    if existing:
        return existing
    # Non riallineare la sequence qui: questa funzione può essere chiamata
    # più volte nello stesso restore/clone prima del commit. Riallineare da una
    # connessione separata tra due INSERT non vede le righe non ancora
    # committate e può riportare la sequence indietro, causando duplicate key
    # su config_label_pkey. Le sequence vengono riallineate una sola volta
    # all'inizio dei flussi di creazione/clonazione/import.
    clone = ConfigLabel(
        tenant_id=target_tenant_id,
        kind=label.kind,
        group=label.group,
        value=label.value,
        description=label.description,
        max_completion_hours=getattr(label, 'max_completion_hours', 0) or 0,
        default_exportable=getattr(label, 'default_exportable', True),
        description_required=getattr(label, 'description_required', False),
        automatic_operations=getattr(label, 'automatic_operations', '') or '',
    )
    db.session.add(clone)
    db.session.flush()
    return clone


def _copy_or_update_label_to_tenant(label, target_tenant_id):
    """Riusa una label equivalente nel tenant destinazione o la crea se assente.

    La chiave funzionale è tenant/kind/value: clonazioni ripetute di tenant o
    workflow non devono produrre duplicati.  Se la label esiste già, i metadati
    vengono riallineati ai valori sorgente senza cambiare l'identità usata da
    eventuali incidenti/template già presenti.
    """
    existing = _copy_label_to_tenant(label, target_tenant_id)
    if existing and label is not None:
        existing.group = label.group
        existing.description = label.description
        existing.max_completion_hours = getattr(label, 'max_completion_hours', 0) or 0
        existing.default_exportable = getattr(label, 'default_exportable', True)
        existing.description_required = getattr(label, 'description_required', False)
        existing.automatic_operations = getattr(label, 'automatic_operations', '') or ''
    return existing


def _remap_config_label_csv_ids(raw, label_id_map):
    values = []
    for item in (raw or '').split(','):
        item = (item or '').strip()
        if not item:
            continue
        try:
            mapped = int(label_id_map.get(int(item), int(item)))
        except Exception:
            continue
        text_value = str(mapped)
        if text_value not in values:
            values.append(text_value)
    return ','.join(values)


def _remap_config_label_condition_tokens(raw, label_id_map):
    values = []
    for token in (raw or '').split(','):
        token = (token or '').strip()
        if not token:
            continue
        negated = token.startswith('!')
        base = token[1:] if negated else token
        mapped_base = base
        if base.startswith('severity:') or base.startswith('data_type:'):
            prefix, raw_id = base.split(':', 1)
            try:
                mapped_base = f'{prefix}:{int(label_id_map.get(int(raw_id), int(raw_id)))}'
            except Exception:
                continue
        mapped = f'!{mapped_base}' if negated else mapped_base
        if mapped not in values:
            values.append(mapped)
    return ','.join(values)


def _merge_config_label_references(source_label_id, target_label_id):
    """Move all references from a duplicate ConfigLabel to the canonical row."""
    if not source_label_id or not target_label_id or int(source_label_id) == int(target_label_id):
        return
    source_label_id = int(source_label_id)
    target_label_id = int(target_label_id)
    label_id_map = {source_label_id: target_label_id}

    Incident.query.filter_by(severity_id=source_label_id).update({'severity_id': target_label_id}, synchronize_session=False)
    IncidentTemplate.query.filter_by(severity_id=source_label_id).update({'severity_id': target_label_id}, synchronize_session=False)
    IncidentWorkflowStep.query.filter_by(category_id=source_label_id).update({'category_id': target_label_id}, synchronize_session=False)
    IncidentWorkflowStep.query.filter_by(action_label_id=source_label_id).update({'action_label_id': target_label_id}, synchronize_session=False)
    NotificationTemplate.query.filter_by(action_label_id=source_label_id).update({'action_label_id': target_label_id}, synchronize_session=False)
    Action.query.filter_by(label_id=source_label_id).update({'label_id': target_label_id}, synchronize_session=False)

    for template in IncidentTemplate.query.filter(
        or_(IncidentTemplate.category_ids.like(f'%{source_label_id}%'), IncidentTemplate.data_type_ids.like(f'%{source_label_id}%'))
    ).all():
        template.category_ids = _remap_config_label_csv_ids(template.category_ids, label_id_map)
        template.data_type_ids = _remap_config_label_csv_ids(template.data_type_ids, label_id_map)

    for step in IncidentWorkflowStep.query.filter(IncidentWorkflowStep.conditions.like(f'%{source_label_id}%')).all():
        step.conditions = _remap_config_label_condition_tokens(step.conditions, label_id_map)

    # Many-to-many tables have composite primary keys.  Insert canonical links
    # only when missing, then remove the duplicate links to avoid PK conflicts.
    for table in (incident_categories, incident_data_types):
        rows = db.session.execute(select(table.c.incident_id).where(table.c.label_id == source_label_id)).fetchall()
        for row in rows:
            incident_id = row[0]
            existing = db.session.execute(
                select(table.c.incident_id).where(and_(table.c.incident_id == incident_id, table.c.label_id == target_label_id))
            ).first()
            if not existing:
                db.session.execute(table.insert().values(incident_id=incident_id, label_id=target_label_id))
        db.session.execute(table.delete().where(table.c.label_id == source_label_id))


def deduplicate_config_labels_for_tenant(tenant_id, include_legacy_global=False):
    """Ensure one label per tenant/kind/value and optionally absorb legacy global labels.

    Legacy imports can contain ConfigLabel rows with tenant_id NULL.  Those rows
    are useful as a compatibility fallback, but they must not appear as a second
    copy next to the tenant-specific label.  When include_legacy_global is true
    the rows are assigned to the tenant if no equivalent exists; otherwise their
    references are merged into the tenant-specific canonical row and the legacy
    duplicate is removed.
    """
    try:
        tenant_id = int(tenant_id)
    except Exception:
        return 0
    changed = 0
    if include_legacy_global:
        for global_label in ConfigLabel.query.filter(ConfigLabel.tenant_id.is_(None)).order_by(ConfigLabel.id).all():
            canonical = ConfigLabel.query.filter_by(tenant_id=tenant_id, kind=global_label.kind, value=global_label.value).order_by(ConfigLabel.id).first()
            if canonical:
                _merge_config_label_references(global_label.id, canonical.id)
                db.session.delete(global_label)
                changed += 1
            else:
                global_label.tenant_id = tenant_id
                changed += 1
        db.session.flush()

    rows = ConfigLabel.query.filter_by(tenant_id=tenant_id).order_by(ConfigLabel.kind, ConfigLabel.value, ConfigLabel.id).all()
    seen = {}
    for label in rows:
        key = ((label.kind or '').strip(), (label.value or '').strip())
        if key not in seen:
            seen[key] = label
            continue
        canonical = seen[key]
        # Preserve the richest metadata while keeping the oldest/canonical ID.
        if not canonical.description and label.description:
            canonical.description = label.description
        if not canonical.group and label.group:
            canonical.group = label.group
        canonical.max_completion_hours = max(getattr(canonical, 'max_completion_hours', 0) or 0, getattr(label, 'max_completion_hours', 0) or 0)
        canonical.default_exportable = bool(getattr(canonical, 'default_exportable', True) and getattr(label, 'default_exportable', True))
        canonical.description_required = bool(getattr(canonical, 'description_required', False) or getattr(label, 'description_required', False))
        ops = []
        for raw_ops in (getattr(canonical, 'automatic_operations', '') or '', getattr(label, 'automatic_operations', '') or ''):
            for op in raw_ops.split(','):
                op = op.strip()
                if op and op not in ops:
                    ops.append(op)
        canonical.automatic_operations = ','.join(ops)
        _merge_config_label_references(label.id, canonical.id)
        db.session.delete(label)
        changed += 1
    if changed:
        db.session.flush()
        align_table_sequence('config_label')
    return changed


def effective_config_labels_query(kind=None):
    """Labels visible in the active tenant, without duplicate legacy/global rows."""
    tid = current_tenant_id()
    q = ConfigLabel.query.filter(ConfigLabel.tenant_id == tid)
    if kind:
        q = q.filter(ConfigLabel.kind == kind)
    return q


def _copy_person_to_tenant(person, target_tenant_id):
    if person is None:
        return None
    q = Person.query.filter_by(tenant_id=target_tenant_id, name=person.name)
    if getattr(person, 'email', None):
        q = q.filter_by(email=person.email)
    existing = q.first()
    if existing:
        if getattr(person, 'group', None):
            existing.group = person.group
        return existing
    clone = Person(tenant_id=target_tenant_id, name=person.name, email=getattr(person, 'email', None), group=getattr(person, 'group', None) or 'personale')
    db.session.add(clone)
    db.session.flush()
    return clone


def _copy_recommendation_to_tenant(recommendation, target_tenant_id):
    if recommendation is None:
        return None
    existing = Recommendation.query.filter_by(tenant_id=target_tenant_id, text=recommendation.text).first()
    if existing:
        return existing
    clone = Recommendation(tenant_id=target_tenant_id, text=recommendation.text)
    db.session.add(clone)
    db.session.flush()
    return clone


def _copy_notification_type_to_tenant(src, target_tenant_id):
    if src is None:
        return None
    existing = NotificationType.query.filter_by(tenant_id=target_tenant_id, code=src.code).first()
    if existing:
        existing.label = src.label
        existing.description = src.description
        existing.recipient_mode = src.recipient_mode
        existing.recipient_setting_key = src.recipient_setting_key
        existing.cc_setting_key = src.cc_setting_key
        existing.enabled = src.enabled
        return existing
    clone = NotificationType(
        tenant_id=target_tenant_id, code=src.code, label=src.label, description=src.description,
        recipient_mode=src.recipient_mode, recipient_setting_key=src.recipient_setting_key,
        cc_setting_key=src.cc_setting_key, enabled=src.enabled,
    )
    db.session.add(clone)
    db.session.flush()
    return clone


def _copy_notification_template_to_tenant(src, target_tenant_id, label_map=None):
    if src is None:
        return None
    label_map = label_map or {}
    existing = NotificationTemplate.query.filter_by(tenant_id=target_tenant_id, kind=src.kind, name=src.name).first()
    values = dict(
        subject=src.subject, body=src.body, linked_form_template_name=src.linked_form_template_name,
        action_label_id=label_map.get(src.action_label_id), recipient_source=src.recipient_source,
        recipient_value=src.recipient_value, recipient_editable=src.recipient_editable,
        recipient_external_allowed=src.recipient_external_allowed, cc_source=src.cc_source,
        cc_value=src.cc_value, cc_editable=src.cc_editable,
        cc_external_allowed=src.cc_external_allowed, is_default=src.is_default,
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    clone = NotificationTemplate(tenant_id=target_tenant_id, kind=src.kind, name=src.name, **values)
    db.session.add(clone)
    db.session.flush()
    return clone


def _copy_external_recipient_to_tenant(src, target_tenant_id):
    if src is None:
        return None
    existing = ExternalRecipient.query.filter_by(tenant_id=target_tenant_id, email=src.email).first()
    if existing:
        existing.name = src.name
        existing.notes = src.notes
        return existing
    clone = ExternalRecipient(tenant_id=target_tenant_id, name=src.name, email=src.email, notes=src.notes)
    db.session.add(clone)
    db.session.flush()
    return clone


def _copy_backup_job_to_tenant(src, target_tenant_id):
    if src is None:
        return None
    existing = BackupJob.query.filter_by(tenant_id=target_tenant_id, name=src.name).first()
    values = dict(
        enabled=src.enabled, cron_expression=src.cron_expression, categories=src.categories, destination=src.destination,
        local_path=src.local_path, s3_endpoint_url=src.s3_endpoint_url, s3_bucket=src.s3_bucket,
        s3_prefix=src.s3_prefix, s3_access_key=src.s3_access_key, s3_secret_key=src.s3_secret_key,
        notify_admin=src.notify_admin,
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    clone = BackupJob(tenant_id=target_tenant_id, name=src.name, **values)
    db.session.add(clone)
    db.session.flush()
    return clone


def move_incident_to_tenant(inc, target_tenant_id):
    """Sposta un incidente preservando i riferimenti configurabili.

    Le entità correlate tenant-specifiche (etichette, persone, raccomandazioni)
    vengono riusate se esistono nel tenant destinazione o clonate quando
    assenti, evitando riferimenti cross-tenant dopo lo spostamento. L'ordine
    delle categorie viene mantenuto rimappando ``category_order`` dagli ID del
    tenant sorgente agli ID delle label equivalenti nel tenant destinazione.
    """
    target_tenant_id = int(target_tenant_id)
    if inc.tenant_id == target_tenant_id:
        return False

    ordered_source_categories = incident_ordered_categories(inc)
    source_category_order_ids = incident_category_order_ids(inc)
    if inc.severity:
        inc.severity = _copy_label_to_tenant(inc.severity, target_tenant_id)

    copied_categories = []
    category_id_map = {}
    for label in ordered_source_categories:
        copied = _copy_label_to_tenant(label, target_tenant_id)
        copied_categories.append(copied)
        if getattr(label, 'id', None) and getattr(copied, 'id', None):
            category_id_map[label.id] = copied.id

    # Include eventuali categorie non presenti in category_order mantenendo
    # comunque la relazione completa, senza alterare l'ordine esplicito sopra.
    seen_destination_ids = {getattr(label, 'id', None) for label in copied_categories}
    for label in list(inc.categories or []):
        if getattr(label, 'id', None) in category_id_map:
            continue
        copied = _copy_label_to_tenant(label, target_tenant_id)
        if getattr(copied, 'id', None) not in seen_destination_ids:
            copied_categories.append(copied)
            seen_destination_ids.add(getattr(copied, 'id', None))
        if getattr(label, 'id', None) and getattr(copied, 'id', None):
            category_id_map[label.id] = copied.id

    inc.categories = copied_categories
    inc.category_order = ','.join(str(category_id_map[old_id]) for old_id in source_category_order_ids if old_id in category_id_map) or _csv_ids_from_objects(copied_categories)
    inc.data_types = [_copy_label_to_tenant(label, target_tenant_id) for label in list(inc.data_types or [])]
    inc.people = [_copy_person_to_tenant(person, target_tenant_id) for person in list(inc.people or [])]
    inc.recommendations = [_copy_recommendation_to_tenant(rec, target_tenant_id) for rec in list(inc.recommendations or [])]
    for action in list(inc.actions or []):
        if action.label:
            action.label = _copy_label_to_tenant(action.label, target_tenant_id)
    inc.tenant_id = target_tenant_id
    return True


def user_membership_summary(user):
    memberships = []
    for membership in sorted(user.tenant_roles or [], key=lambda m: ((m.tenant.name if m.tenant else '') or '').lower()):
        memberships.append({
            'tenant_id': membership.tenant_id,
            'tenant_name': membership.tenant.name if membership.tenant else f'Tenant #{membership.tenant_id}',
            'role': membership.normalized_role(),
        })
    return memberships


def user_default_tenant_options(user):
    if not user:
        return []
    if getattr(user, 'is_builtin_admin', False):
        return []
    ids = []
    for membership in user.tenant_roles or []:
        if membership.normalized_role() != 'disabled' and membership.tenant_id not in ids:
            ids.append(membership.tenant_id)
    legacy_tid = user.default_tenant_id or user.tenant_id
    if legacy_tid and user_role_for_tenant(user, legacy_tid) != 'disabled' and legacy_tid not in ids:
        ids.append(legacy_tid)
    if not ids:
        return []
    return Tenant.query.filter(Tenant.id.in_(ids)).order_by(Tenant.name).all()


def set_user_default_tenant(user, tenant_id):
    if not user:
        return False
    if getattr(user, 'is_builtin_admin', False):
        user.default_tenant_id = None
        return True
    if not tenant_id:
        user.default_tenant_id = None
        return True
    tenant_id = int(tenant_id)
    tenant_or_404(tenant_id)
    if user_role_for_tenant(user, tenant_id) == 'disabled':
        return False
    user.default_tenant_id = tenant_id
    sync_user_legacy_identity(user)
    return True


def tenant_or_404(tenant_id):
    tenant = db.session.get(Tenant, int(tenant_id)) if tenant_id else None
    if tenant is None:
        abort(404)
    return tenant


def ensure_tenant_access(obj):
    if obj is None or not hasattr(obj, 'tenant_id') or is_superuser():
        return obj
    tid = getattr(obj, 'tenant_id', None)
    if tid != current_tenant_id() or user_role_for_tenant(current_user, tid) == 'disabled':
        abort(404)
    return obj


def model_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return ensure_tenant_access(obj)


def manageable_user_or_404(uid):
    """Return a user that the current administrator may manage.

    Superuser/global admin can manage every account. Tenant admins can manage
    only users that have an active membership in the current tenant; this is
    important now that one user can belong to more tenants with different
    roles and the legacy User.tenant_id is no longer authoritative.
    """
    user = db.session.get(User, int(uid))
    if user is None:
        abort(404)
    if is_superuser():
        return user
    tid = current_tenant_id()
    if user_role_for_tenant(current_user, tid) != 'admin':
        abort(403)
    if user_role_for_tenant(user, tid) == 'disabled':
        abort(404)
    return user


def manageable_user_query():
    q = User.query
    if is_superuser():
        return q
    tid = current_tenant_id()
    member_ids = db.session.query(UserTenantRole.user_id).filter(
        UserTenantRole.tenant_id == tid,
        UserTenantRole.role != 'disabled'
    )
    return q.filter(User.id.in_(member_ids))



SUPPORTED_LANGUAGES = {'it', 'en'}

# ---- AgID secure development hardening helpers ----
_COMMON_PASSWORDS = {
    'password','password1','password123','admin','admin123','administrator','changeme','change-me',
    'qwerty','qwerty123','123456','12345678','123456789','letmein','welcome','welcome1'
}
_PASSWORD_RE_UPPER = re.compile(r'[A-Z]')
_PASSWORD_RE_LOWER = re.compile(r'[a-z]')
_PASSWORD_RE_DIGIT = re.compile(r'\d')
_PASSWORD_RE_SPECIAL = re.compile(r'[^A-Za-z0-9]')
_SAFE_TEXT_RE = re.compile(r'^[\w\sÀ-ÖØ-öø-ÿ.,;:!?@#%&()\[\]{}+\-=\/\\\'"’`\n\r\t]*$')
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_ALLOWED_UPLOAD_EXTENSIONS = {'.pdf','.txt','.csv','.json','.xml','.docx','.xlsx','.png','.jpg','.jpeg','.gif','.webp'}
_ALLOWED_UPLOAD_MAGIC = {
    '.pdf': (b'%PDF',), '.png': (b'\x89PNG\r\n\x1a\n',), '.jpg': (b'\xff\xd8\xff',), '.jpeg': (b'\xff\xd8\xff'),
    '.gif': (b'GIF87a', b'GIF89a'), '.docx': (b'PK\x03\x04',), '.xlsx': (b'PK\x03\x04',)
}
_TEXT_UPLOAD_EXTENSIONS = {'.txt','.csv','.json','.xml'}



_SECRET_SETTING_KEYS = {
    'smtp_password', 'ldap_bind_password', 'sso_client_secret',
    'ai_chatbot_chatgpt_api_key', 'ai_chatbot_claude_api_key', 'ai_chatbot_gemini_api_key',
    'ai_chatbot_ollama_api_key', 'ai_chatbot_perplexity_api_key', 'alfresco_password', 'sso_profiles_json'
}
_ENC_PREFIX = 'enc:v1:'


def _fernet():
    raw = (os.getenv('SETTING_ENCRYPTION_KEY') or current_app.config.get('SECRET_KEY') or '').encode('utf-8')
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_setting_value(key, value):
    value = '' if value is None else str(value)
    if key not in _SECRET_SETTING_KEYS or not value or value.startswith(_ENC_PREFIX):
        return value
    return _ENC_PREFIX + _fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt_setting_value(key, value):
    value = '' if value is None else str(value)
    if key not in _SECRET_SETTING_KEYS or not value.startswith(_ENC_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_ENC_PREFIX):].encode('ascii')).decode('utf-8')
    except InvalidToken:
        current_app.logger.error('Impossibile decifrare il setting segreto %s', key)
        return ''


def store_setting_value(key, value):
    return encrypt_setting_value(key, value)


def validate_ldap_filter_template(template):
    template = (template or '(uid={uid})').strip()
    if '{uid}' not in template:
        raise ValueError('Il filtro LDAP deve contenere il placeholder {uid}.')
    if len(template) > 500 or any(ch in template for ch in ('\x00', '\n', '\r')):
        raise ValueError('Filtro LDAP non valido.')
    return template


def make_ldap_search_filter(template, username):
    return validate_ldap_filter_template(template).replace('{uid}', escape_filter_chars(username or ''))


def validate_full_import_archive(archive):
    members = archive.getmembers()
    max_files = int(os.getenv('FULL_IMPORT_MAX_FILES', '5000'))
    max_total = int(os.getenv('FULL_IMPORT_MAX_TOTAL_BYTES', str(250 * 1024 * 1024)))
    max_member = int(os.getenv('FULL_IMPORT_MAX_MEMBER_BYTES', str(50 * 1024 * 1024)))
    if len(members) > max_files:
        raise ValueError('Archivio troppo grande: troppi file.')
    total = 0
    names = set()
    for member in members:
        name = (member.name or '').replace('\\', '/')
        names.add(name)
        parts = Path(name).parts
        if member.isdir():
            continue
        if member.issym() or member.islnk() or member.isdev():
            raise ValueError(f'Archivio non sicuro: entry non regolare {name}.')
        if name.startswith('/') or '..' in parts or name.startswith('~'):
            raise ValueError(f'Archivio non sicuro: percorso non valido {name}.')
        if member.size < 0 or member.size > max_member:
            raise ValueError(f'Archivio non sicuro: file troppo grande {name}.')
        total += member.size
        if total > max_total:
            raise ValueError('Archivio troppo grande.')
    if 'export.json' not in names:
        raise ValueError('Archivio non valido: export.json mancante.')
    return True


def validate_password_strength(password, username='', email=''):
    value = password or ''
    errors = []
    if len(value) < 12:
        errors.append('almeno 12 caratteri')
    if not _PASSWORD_RE_UPPER.search(value):
        errors.append('una maiuscola')
    if not _PASSWORD_RE_LOWER.search(value):
        errors.append('una minuscola')
    if not _PASSWORD_RE_DIGIT.search(value):
        errors.append('una cifra')
    if not _PASSWORD_RE_SPECIAL.search(value):
        errors.append('un carattere speciale')
    lowered = value.lower()
    if lowered in _COMMON_PASSWORDS or 'password' in lowered or 'changeme' in lowered:
        errors.append('non deve essere una password comune o di default')
    for token in (username or '', email or ''):
        token = (token or '').split('@')[0].lower().strip()
        if token and len(token) >= 4 and token in lowered:
            errors.append('non deve contenere username o email')
            break
    if errors:
        raise ValueError('Password non conforme: richiede ' + ', '.join(dict.fromkeys(errors)) + '.')
    return True


def validate_text_field(value, field_name='campo', max_length=1000, required=False, allow_multiline=True):
    value = '' if value is None else str(value)
    if required and not value.strip():
        raise ValueError(f'{field_name} è obbligatorio.')
    if len(value) > max_length:
        raise ValueError(f'{field_name} supera la lunghezza massima di {max_length} caratteri.')
    if not allow_multiline and ('\n' in value or '\r' in value):
        raise ValueError(f'{field_name} non può contenere più righe.')
    if not _SAFE_TEXT_RE.match(value):
        raise ValueError(f'{field_name} contiene caratteri non ammessi.')
    return value


def validate_email_field(value, field_name='email', required=False):
    value = (value or '').strip()
    if required and not value:
        raise ValueError(f'{field_name} è obbligatoria.')
    if value and (len(value) > 255 or not _EMAIL_RE.match(value)):
        raise ValueError(f'{field_name} non valida.')
    return value


def validate_upload_file(file_storage, allowed_extensions=None, max_size=None):
    if not file_storage or not getattr(file_storage, 'filename', ''):
        raise ValueError('File mancante.')
    filename = secure_filename(file_storage.filename)
    if not filename:
        raise ValueError('Nome file non valido.')
    ext = Path(filename).suffix.lower()
    allowed = allowed_extensions or _ALLOWED_UPLOAD_EXTENSIONS
    if ext not in allowed:
        raise ValueError(f'Estensione file non consentita: {ext or "senza estensione"}.')
    pos = file_storage.stream.tell()
    head = file_storage.stream.read(8192)
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(pos)
    limit = max_size or int(current_app.config.get('MAX_CONTENT_LENGTH') or (25 * 1024 * 1024))
    if size > limit:
        raise ValueError('File troppo grande.')
    if ext in _ALLOWED_UPLOAD_MAGIC and not any(head.startswith(m) for m in _ALLOWED_UPLOAD_MAGIC[ext]):
        raise ValueError('Il contenuto del file non corrisponde all’estensione dichiarata.')
    if ext in _TEXT_UPLOAD_EXTENSIONS:
        sample = head.decode('utf-8', errors='ignore')
        if '\x00' in sample:
            raise ValueError('Il file testuale contiene byte non validi.')
    return filename


def save_validated_upload(file_storage, destination_dir, allowed_extensions=None):
    name = validate_upload_file(file_storage, allowed_extensions=allowed_extensions)
    stored = str(uuid.uuid4()) + '_' + name
    target = os.path.abspath(os.path.join(destination_dir, stored))
    base = os.path.abspath(destination_dir)
    if not target.startswith(base + os.sep):
        raise ValueError('Percorso file non valido.')
    file_storage.save(target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return name, stored


def _client_ip_for_rate_limit():
    # In deployment il proxy deve sanificare X-Forwarded-For; qui prendiamo il
    # primo valore per mantenere stabile la chiave anche dietro reverse proxy.
    return (request.headers.get('X-Forwarded-For', request.remote_addr or '')
            .split(',')[0].strip())[:64]


def login_rate_limit_key(username):
    ip = _client_ip_for_rate_limit()
    normalized_user = (username or '').strip().lower()[:160]
    digest = hashlib.sha256(f'{ip}:{normalized_user}'.encode('utf-8')).hexdigest()
    return digest


def _login_lockout_policy():
    threshold = _bounded_int(os.getenv('LOGIN_LOCKOUT_THRESHOLD'), 5, 2, 50)
    window_seconds = _bounded_int(os.getenv('LOGIN_LOCKOUT_WINDOW_SECONDS'), 900, 60, 86400)
    max_block_seconds = _bounded_int(os.getenv('LOGIN_LOCKOUT_MAX_SECONDS'), 900, 60, 86400)
    step_seconds = _bounded_int(os.getenv('LOGIN_LOCKOUT_STEP_SECONDS'), 60, 10, 3600)
    return threshold, window_seconds, max_block_seconds, step_seconds


def _prune_login_failures(now=None):
    now = now or utcnow()
    try:
        cutoff = now - timedelta(days=7)
        LoginFailure.query.filter(LoginFailure.last_failure_at < cutoff).delete(synchronize_session=False)
    except Exception:
        current_app.logger.debug('Cleanup login failure non completato', exc_info=True)


def login_is_blocked(username):
    entry = LoginFailure.query.filter_by(rate_key=login_rate_limit_key(username)).first()
    if not entry or not entry.blocked_until:
        return False, 0
    now = utcnow()
    if entry.blocked_until <= now:
        return False, 0
    return True, max(0, int((entry.blocked_until - now).total_seconds()))


def register_login_failure(username):
    key = login_rate_limit_key(username)
    now = utcnow()
    threshold, window_seconds, max_block_seconds, step_seconds = _login_lockout_policy()
    entry = LoginFailure.query.filter_by(rate_key=key).first()
    if not entry:
        entry = LoginFailure(rate_key=key, username=(username or '').strip()[:160], ip_address=_client_ip_for_rate_limit(), failure_count=0, first_failure_at=now)
        db.session.add(entry)
    if (now - (entry.first_failure_at or now)).total_seconds() > window_seconds:
        entry.failure_count = 0
        entry.first_failure_at = now
        entry.blocked_until = None
    entry.username = (username or '').strip()[:160]
    entry.ip_address = _client_ip_for_rate_limit()
    entry.failure_count = int(entry.failure_count or 0) + 1
    entry.last_failure_at = now
    if entry.failure_count >= threshold:
        seconds = min(max_block_seconds, step_seconds * (entry.failure_count - threshold + 1))
        entry.blocked_until = now + timedelta(seconds=seconds)
    try:
        _prune_login_failures(now)
        db.session.commit()
        audit_log('security:login_failure', {'username': username, 'path': request.path, 'count': entry.failure_count}, actor_type='anonymous', commit=True)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Registrazione server-side del login failure non completata')


def clear_login_failures(username):
    try:
        entry = LoginFailure.query.filter_by(rate_key=login_rate_limit_key(username)).first()
        if entry:
            db.session.delete(entry)
            db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Pulizia server-side login failure non completata')


def configured_language_mode():
    value = setting_value('interface_language', 'auto') if 'Setting' in globals() else 'auto'
    return value if value in {'auto','it','en'} else 'auto'

def detect_interface_language():
    mode = configured_language_mode()
    if mode in SUPPORTED_LANGUAGES:
        return mode
    best = request.accept_languages.best_match(['it', 'en'])
    # Italiano solo per locale italiano; inglese per tutto il resto.
    return 'it' if best == 'it' else 'en'



def _bounded_int(value, default, minimum=0, maximum=100000):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))

def audit_retention_parts():
    """Restituisce la retention audit configurata in mesi, giorni, ore e minuti.

    Il valore storico audit_retention_months resta supportato come fallback per
    compatibilità con export/import precedenti; le nuove configurazioni usano
    quattro chiavi distinte.
    """
    legacy_months = setting_value('audit_retention_months', '6') or '6'
    months = _bounded_int(setting_value('audit_retention_months_part', legacy_months) or legacy_months, 6, 0, 120)
    days = _bounded_int(setting_value('audit_retention_days_part', '0') or '0', 0, 0, 3650)
    hours = _bounded_int(setting_value('audit_retention_hours_part', '0') or '0', 0, 0, 23)
    minutes = _bounded_int(setting_value('audit_retention_minutes_part', '0') or '0', 0, 0, 59)
    if months == 0 and days == 0 and hours == 0 and minutes == 0:
        months = 6
    return {'months': months, 'days': days, 'hours': hours, 'minutes': minutes}

def audit_retention_delta():
    parts = audit_retention_parts()
    return timedelta(days=(parts['months'] * 30) + parts['days'], hours=parts['hours'], minutes=parts['minutes'])

def audit_retention_label():
    parts = audit_retention_parts()
    labels = []
    if parts['months']:
        labels.append(f"{parts['months']} mes{'e' if parts['months'] == 1 else 'i'}")
    if parts['days']:
        labels.append(f"{parts['days']} giorn{'o' if parts['days'] == 1 else 'i'}")
    if parts['hours']:
        labels.append(f"{parts['hours']} or{'a' if parts['hours'] == 1 else 'e'}")
    if parts['minutes']:
        labels.append(f"{parts['minutes']} minut{'o' if parts['minutes'] == 1 else 'i'}")
    return ', '.join(labels) or '6 mesi'

def audit_cutoff_datetime():
    return utcnow() - audit_retention_delta()

def audit_max_records(default=10000):
    """Numero massimo di righe audit da mantenere.

    Il limite è espresso in record fisici della tabella, non in occorrenze
    collassate nel campo repeat_count. Il default è 10000 record.
    """
    return _bounded_int(setting_value('audit_max_records', str(default)) or str(default), default, 100, 1000000)


def _setting_value_without_request_user(key, default='', tenant_id=None):
    """Legge una Setting durante restore/migrazioni senza consultare current_user.

    Dopo ``db.session.remove()`` usato dal Full import distruttivo, l'oggetto
    Flask-Login ``current_user`` puo' essere detached. Le normali funzioni
    tenant-aware attraversano ``current_tenant_id()`` e quindi possono causare
    ``DetachedInstanceError``. Questa variante usa solo il tenant esplicito.
    """
    key = str(key or '')
    physical_key = key if key in GLOBAL_SETTING_KEYS else (f'tenant:{int(tenant_id)}:{key}' if tenant_id else key)
    setting = db.session.get(Setting, physical_key)
    if not setting and physical_key != key:
        setting = db.session.get(Setting, key)
    return decrypt_setting_value(key, setting.value) if setting and setting.value is not None else default


def _audit_retention_parts_without_request_user(tenant_id=None):
    legacy_months = _setting_value_without_request_user('audit_retention_months', '6', tenant_id) or '6'
    months = _bounded_int(_setting_value_without_request_user('audit_retention_months_part', legacy_months, tenant_id) or legacy_months, 6, 0, 120)
    days = _bounded_int(_setting_value_without_request_user('audit_retention_days_part', '0', tenant_id) or '0', 0, 0, 3650)
    hours = _bounded_int(_setting_value_without_request_user('audit_retention_hours_part', '0', tenant_id) or '0', 0, 0, 23)
    minutes = _bounded_int(_setting_value_without_request_user('audit_retention_minutes_part', '0', tenant_id) or '0', 0, 0, 59)
    if months == 0 and days == 0 and hours == 0 and minutes == 0:
        months = 6
    return {'months': months, 'days': days, 'hours': hours, 'minutes': minutes}


def purge_audit_logs_without_request_user(tenant_id=None, commit=False):
    """Purge audit sicuro per Full import dopo drop/create della sessione.

    Non usa ``setting_value()``, ``current_tenant_id()`` o ``current_user``.
    """
    parts = _audit_retention_parts_without_request_user(tenant_id)
    delta = timedelta(days=(parts['months'] * 30) + parts['days'], hours=parts['hours'], minutes=parts['minutes'])
    deleted = AuditLog.query.filter(AuditLog.occurred_at < (utcnow() - delta)).delete(synchronize_session=False)
    max_records = _bounded_int(_setting_value_without_request_user('audit_max_records', '10000', tenant_id) or '10000', 10000, 100, 1000000)
    total = AuditLog.query.count()
    if total > max_records:
        overflow = total - max_records
        old_ids = [row.id for row in AuditLog.query.order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc()).with_entities(AuditLog.id).limit(overflow).all()]
        if old_ids:
            deleted += AuditLog.query.filter(AuditLog.id.in_(old_ids)).delete(synchronize_session=False)
    if commit:
        db.session.commit()
    return deleted

def purge_audit_logs(commit=False):
    """Elimina i record audit oltre la retention e oltre il numero massimo.

    Prima applica il periodo di ritenzione configurato, poi se il numero di
    record resta superiore al limite massimo configurato mantiene i record più
    recenti ed elimina i più vecchi.
    """
    deleted = AuditLog.query.filter(AuditLog.occurred_at < audit_cutoff_datetime()).delete(synchronize_session=False)
    max_records = audit_max_records()
    total = AuditLog.query.count()
    if total > max_records:
        overflow = total - max_records
        old_ids = [row.id for row in AuditLog.query.order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc()).with_entities(AuditLog.id).limit(overflow).all()]
        if old_ids:
            deleted += AuditLog.query.filter(AuditLog.id.in_(old_ids)).delete(synchronize_session=False)
    if commit:
        db.session.commit()
    return deleted

def purge_audit_keep_latest(keep_count, commit=False):
    """Purge manuale: conserva solo gli ultimi keep_count record audit."""
    keep_count = _bounded_int(keep_count, audit_max_records(), 0, 1000000)
    total = AuditLog.query.count()
    if total <= keep_count:
        return 0
    old_ids = [row.id for row in AuditLog.query.order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc()).with_entities(AuditLog.id).limit(total - keep_count).all()]
    deleted = AuditLog.query.filter(AuditLog.id.in_(old_ids)).delete(synchronize_session=False) if old_ids else 0
    if commit:
        db.session.commit()
    return deleted

def purge_audit_older_than(cutoff_dt, commit=False):
    """Purge manuale: elimina i record audit più vecchi della data indicata."""
    deleted = AuditLog.query.filter(AuditLog.occurred_at < cutoff_dt).delete(synchronize_session=False)
    if commit:
        db.session.commit()
    return deleted

def audit_actor(default_actor_type='system'):
    try:
        if getattr(current_user, 'is_authenticated', False):
            return current_user.id, (current_user.username or current_user.email or current_user.name or 'utente'), 'user'
    except Exception:
        pass
    return None, 'system', default_actor_type



def audit_detail_summary(operation_type, details):
    """Restituisce dettagli audit sintetici, leggibili e privi di payload estesi.

    I record di audit devono aiutare a capire cosa è successo senza salvare
    copie complete di form, risultati o messaggi lunghi.
    """
    op = operation_type or 'operazione'
    raw = details or ''
    data = None
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except Exception:
            data = None
    def short(value, limit=180):
        if value is None:
            return ''
        if isinstance(value, (list, tuple, set)):
            text = ', '.join(short(v, 60) for v in list(value)[:6])
            if len(value) > 6:
                text += f' (+{len(value)-6})'
        elif isinstance(value, dict):
            text = ', '.join(f'{k}={short(v, 40)}' for k, v in list(value.items())[:6])
            if len(value) > 6:
                text += f' (+{len(value)-6} campi)'
        else:
            text = str(value)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:limit-1] + '…' if len(text) > limit else text
    if isinstance(data, dict):
        if op.startswith('incident_reminder:create'):
            return f"Promemoria incidente creato: incidente #{data.get('incident_id','-')}, promemoria #{data.get('reminder_id','-')}, invio {short(data.get('scheduled_at')) or '-'}"
        if op.startswith('incident_reminder:update'):
            reset = ' sì' if data.get('reset_sent') else ' no'
            return f"Promemoria incidente aggiornato: incidente #{data.get('incident_id','-')}, promemoria #{data.get('reminder_id','-')}, invio {short(data.get('scheduled_at')) or '-'}, reinvio:{reset}"
        if op.startswith('incident_reminder:delete'):
            return f"Promemoria incidente eliminato: incidente #{data.get('incident_id','-')}, promemoria #{data.get('reminder_id','-')}"
        if op == 'scheduler:incident_reminder_sent':
            return f"Scheduler: inviato promemoria incidente #{data.get('incident_id','-')} / promemoria #{data.get('reminder_id','-')} ({short(data.get('scheduled_at')) or '-'})"
        if op == 'scheduler:incident_reminder_skipped':
            reminder_when = data.get('reminder_scheduled_at') or data.get('scheduled_at') or '-'
            return f"Scheduler: saltato promemoria incidente #{data.get('incident_id','-')} / promemoria #{data.get('reminder_id','-')} ({short(reminder_when) or '-'}): {short(data.get('reason')) or '-'}"
        if op == 'scheduler:incident_reminder_check':
            return f"Scheduler: controllo promemoria specifici, scaduti {data.get('due',0)}, inviati {data.get('sent',0)}, saltati {data.get('skipped',0)}, errori {len(data.get('errors') or [])}"
        if op == 'scheduler:deadline_notification_check':
            sent = data.get('sent') or data.get('sent_count') or 0
            due = data.get('due') or data.get('due_count') or data.get('incidents_with_pending') or 0
            slot = short(data.get('schedule_slot')) or '-'
            return f"Scheduler: controllo notifiche task in scadenza, slot {slot}, elementi in scadenza {due}, notifiche inviate {sent}, sorgente {short(data.get('source')) or '-'}"
        if op == 'scheduler:deadline_notification_sent':
            return f"Scheduler: notifica task in scadenza inviata. {short(raw, 220)}"
        if op == 'scheduler:deadline_notification_skipped':
            return f"Scheduler: saltata notifica task incidente #{data.get('incident_id','-')}: {short(data.get('reason')) or '-'}"
        if op == 'admin:audit_purge_manual':
            if data.get('mode') == 'keep_count':
                return f"Purge manuale audit: conservati al massimo {data.get('keep_count','-')} record, eliminati {data.get('deleted',0)} record"
            if data.get('mode') == 'older_than':
                return f"Purge manuale audit: eliminati record più vecchi di {short(data.get('older_than')) or '-'}, eliminati {data.get('deleted',0)} record"
        if op == 'admin:audit_config_update':
            return f"Configurazione audit aggiornata: massimo {data.get('audit_max_records','-')} record, {data.get('audit_records_per_page','-')} record per pagina"
        if 'endpoint' in data or 'path' in data:
            return f"Richiesta {short(data.get('method')) or '-'} {short(data.get('path')) or '-'} completata con stato {data.get('status_code','-')}"
        if 'incident_id' in data:
            return f"Operazione su incidente #{data.get('incident_id')}: {short(data)}"
        keys = list(data.keys())
        shown = ', '.join(f"{k}: {short(data.get(k), 80)}" for k in keys[:5])
        if len(keys) > 5:
            shown += f" (+{len(keys)-5} altri campi)"
        return shown or 'Operazione registrata'
    if raw:
        return short(raw, 300)
    return 'Operazione registrata'

def audit_log(operation_type, details='', actor_type='system', commit=False):
    """Registra un evento audit evitando flooding da record consecutivi uguali.

    Se l'ultimo record audit ha lo stesso tipo, utente, origine e dettagli
    sintetici, viene incrementato repeat_count invece di inserire una nuova
    riga. Ogni blocco viene comunque chiuso a 100 occorrenze: la 101-esima
    occorrenza crea una nuova riga e riparte da 1.

    La INSERT viene forzata con ``flush()`` dentro questa funzione: così un
    eventuale disallineamento della sequence PostgreSQL di ``audit_log`` viene
    intercettato subito, riallineato e ritentato qui, invece di esplodere più
    tardi al ``commit()`` del chiamante, come accadeva col pulsante manuale
    "Esegui controllo ora".
    """
    user_id, username, resolved_actor_type = audit_actor(actor_type)
    op = (operation_type or 'operazione')[:120]
    summarized_details = audit_detail_summary(operation_type, details)[:1000]
    now = utcnow()
    try:
        # Evita che una precedente riga AuditLog ancora pendente venga
        # autoflushata dalla SELECT prima del riallineamento della sequence.
        with db.session.no_autoflush:
            last = tenant_query(AuditLog).order_by(AuditLog.id.desc()).first()
        if (last and last.operation_type == op and last.username == username
                and last.actor_type == resolved_actor_type
                and (last.details or '') == summarized_details
                and int(getattr(last, 'repeat_count', 1) or 1) < 100):
            last.repeat_count = int(getattr(last, 'repeat_count', 1) or 1) + 1
            last.occurred_at = now
            if user_id is not None:
                last.user_id = user_id
            if commit:
                db.session.commit()
            return last
    except Exception:
        current_app.logger.exception('Collasso audit non completato; inserisco un nuovo record')

    def _new_log():
        return AuditLog(
            tenant_id=current_tenant_id(default_to_default=True),
            occurred_at=now,
            operation_type=op,
            username=username,
            user_id=user_id,
            actor_type=resolved_actor_type,
            details=summarized_details,
            repeat_count=1,
        )

    try:
        align_table_sequence('audit_log')
    except Exception:
        current_app.logger.exception('Riallineamento sequenza audit non completato')
    log = _new_log()
    db.session.add(log)
    try:
        db.session.flush([log])
    except IntegrityError as exc:
        if 'audit_log_pkey' not in str(exc):
            raise
        db.session.rollback()
        current_app.logger.warning('Sequence audit_log disallineata; riallineo e reinserisco il record audit')
        align_table_sequence('audit_log')
        log = _new_log()
        db.session.add(log)
        db.session.flush([log])
    if commit:
        db.session.commit()
    return log

def audit_operation_name():
    endpoint = request.endpoint or 'unknown'
    action = request.form.get('action') if request.form else ''
    if action:
        return f'{endpoint}:{action}'[:120]
    return endpoint[:120]

def section_flash(message, section, category='error'):
    flash(message, f'section:{section}:{category}')

def section_messages(section, messages):
    prefix = f'section:{section}:'
    out = []
    for category, message in messages:
        if category.startswith(prefix):
            out.append((category[len(prefix):] or 'info', message))
    return out

def global_messages(messages):
    return [(category, message) for category, message in messages if not category.startswith('section:')]


def rebuild_database_for_full_import():
    """Distrugge e ricrea completamente lo schema DB per il Full import.

    Il full import deve sostituire lo stato persistente del database, non solo
    svuotare le tabelle applicative. Ricreare lo schema elimina anche vincoli,
    sequenze e tabelle di relazione nello stato corrente. Alcuni ambienti,
    soprattutto PostgreSQL con bootstrap/migrazioni eseguiti prima del restore,
    possono comunque lasciare o ricreare righe di servizio come il tenant
    ``default``: per questo, subito dopo la ricreazione, viene eseguito anche
    uno svuotamento esplicito di tutte le tabelle applicative.
    """
    current_app.logger.warning('Full import: distruzione e ricreazione completa del database applicativo')
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        db.session.remove()
    except Exception:
        pass
    db.drop_all()
    db.create_all()
    db.session.commit()
    clear_database_rows_for_full_import()


def clear_database_rows_for_full_import():
    """Svuota tutte le tabelle dopo la ricreazione dello schema.

    Protegge il full import da residui o righe bootstrap create tra
    ``create_all`` e il ripristino del dump, in particolare il tenant
    ``default`` che su PostgreSQL causa violazioni dell'indice univoco
    ``ix_tenant_name`` quando un backup storico contiene a sua volta il tenant
    default. L'operazione e' idempotente e sicura anche su DB gia' vuoti.
    """
    try:
        db.session.rollback()
    except Exception:
        pass
    tables = list(reversed(db.metadata.sorted_tables))
    if not tables:
        return
    if str(db.engine.url).startswith('postgresql'):
        table_names = [table.name for table in tables]
        quoted = ', '.join(f'"{name}"' for name in table_names)
        with db.engine.begin() as conn:
            conn.execute(text(f'TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE'))  # nosec: B608 - table names come only from SQLAlchemy metadata
    else:
        with db.engine.begin() as conn:
            dialect = db.engine.dialect.name
            if dialect == 'sqlite':
                conn.execute(text('PRAGMA foreign_keys=OFF'))
            for table in tables:
                conn.execute(table.delete())
            if dialect == 'sqlite':
                conn.execute(text('PRAGMA foreign_keys=ON'))


def _deduplicated_tenant_rows(rows):
    """Normalizza i tenant letti da export storici evitando duplicati per nome.

    Alcuni export legacy possono contenere il tenant ``default`` gia' presente
    nel database di destinazione o righe tenant duplicate/non complete. Il full
    import globale deve essere ripristinabile senza fermarsi su ``ix_tenant_name``.
    """
    out = []
    seen_names = set()
    seen_ids = set()
    for row in rows or []:
        coerced = _coerce_row_for_model(Tenant, row)
        name = (coerced.get('name') or '').strip() or 'default'
        key = name.lower()
        tenant_id = coerced.get('id')
        if key in seen_names or (tenant_id is not None and tenant_id in seen_ids):
            continue
        coerced['name'] = name
        if name == 'default' and not (coerced.get('description') or '').strip():
            coerced['description'] = 'Tenant predefinito'
        out.append(coerced)
        seen_names.add(key)
        if tenant_id is not None:
            seen_ids.add(tenant_id)
    if not out:
        out.append({'id': 1, 'name': 'default', 'description': 'Tenant predefinito'})
    elif not any((row.get('name') or '').strip().lower() == 'default' for row in out):
        out.insert(0, {'id': 1, 'name': 'default', 'description': 'Tenant predefinito'})
    return out


def _legacy_default_tenant_id():
    tenant = Tenant.query.filter_by(name='default').first()
    return tenant.id if tenant else None

def _coerce_row_for_full_import(model, row, default_tenant_id=None):
    coerced = _coerce_row_for_model(model, row)
    if default_tenant_id and hasattr(model, 'tenant_id') and not coerced.get('tenant_id'):
        coerced['tenant_id'] = default_tenant_id
    return coerced


def _deduplicated_user_tenant_role_rows(rows, default_tenant_id=None):
    out = []
    seen = set()
    for row in rows or []:
        coerced = _coerce_row_for_full_import(UserTenantRole, row, default_tenant_id)
        key = (coerced.get('user_id'), coerced.get('tenant_id'))
        if not key[0] or not key[1] or key in seen:
            continue
        role = (coerced.get('role') or 'disabled').strip().lower()
        coerced['role'] = role
        out.append(coerced)
        seen.add(key)
    return out


def align_table_sequence(table_name):
    """Riallinea una sequenza PostgreSQL prima di INSERT critici.

    Usa la stessa connessione della sessione corrente così il calcolo di
    ``MAX(id)`` vede anche le righe già flushate ma non ancora committate nel
    clone/import in corso. Questo evita il caso PostgreSQL in cui un
    riallineamento ripetuto da una connessione separata non vede gli INSERT
    precedenti della transazione e riporta la sequence a un valore già usato.
    Le sequence PostgreSQL non sono transazionali, quindi il ``setval`` resta
    efficace anche se la transazione applicativa venisse annullata.
    """
    if not str(db.engine.url).startswith('postgresql'):
        return
    safe_table = re.sub(r'[^a-zA-Z0-9_]', '', table_name or '')
    if not safe_table:
        return
    with db.session.no_autoflush:
        conn = db.session.connection()
        metadata = MetaData()
        reflected = Table(safe_table, metadata, autoload_with=conn)
        max_value = conn.execute(select(func.max(reflected.c.id))).scalar() or 0
        quoted_table = f'"{safe_table}"'
        seq_name = conn.execute(
            text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
            {'table_name': quoted_table},
        ).scalar()
        if not seq_name:
            return
        current_value = max(int(max_value), 1)
        conn.execute(
            text("SELECT setval(CAST(:seq_name AS regclass), :current_value, :is_called)"),
            {
                "seq_name": seq_name,
                "current_value": current_value,
                "is_called": bool(max_value),
            },
        )


def sequence_managed_table_names():
    """Restituisce tutte le tabelle con colonna ``id`` intera da riallineare.

    La lista viene ricavata dai metadati SQLAlchemy, così nuove tabelle con PK
    autoincrementale saranno protette senza dover ricordare di aggiungerle a
    mano a una mappa parziale. Le tabelle associative senza colonna ``id`` sono
    escluse perché non hanno sequence dedicate.
    """
    names = []
    for table in db.metadata.sorted_tables:
        column = table.c.get('id')
        if column is None:
            continue
        try:
            is_integer = column.type.python_type is int
        except NotImplementedError:
            is_integer = False
        if is_integer:
            names.append(table.name)
    return names


def align_all_table_sequences():
    """Riallinea tutte le sequence PostgreSQL delle PK applicative.

    Da usare dopo full import/restore e come recupero generalizzato quando una
    qualsiasi INSERT segnala ``duplicate key value violates unique constraint``.
    """
    if not str(db.engine.url).startswith('postgresql'):
        return
    for table_name in sequence_managed_table_names():
        align_table_sequence(table_name)


def is_duplicate_key_integrity_error(exc):
    return 'duplicate key value violates unique constraint' in str(exc)


NON_EXPORTABLE_ACTION_KEYWORDS = (
    'notifica',
    'comunicazione',
    'informazione iniziale',
    'analisi',
    'conclusione',
)


def action_exportable_default(label=None, description=None):
    """Default exportability for new actions.

    Per le azioni con label configurata, il default deriva dal nuovo campo
    ``ConfigLabel.default_exportable`` impostabile in Admin -> Liste
    configurabili -> Label azioni. Per compatibilità con vecchi database o
    azioni senza label, resta il fallback basato sulle parole chiave storiche.
    Il flag rimane sempre modificabile nel dettaglio incidente.
    """
    if label is not None and getattr(label, 'kind', None) == 'action_label' and getattr(label, 'default_exportable', None) is not None:
        return bool(label.default_exportable)
    text = ' '.join([
        getattr(label, 'value', '') or '',
        getattr(label, 'description', '') or '',
        description or '',
    ]).lower().replace('’', "'")
    return not any(keyword in text for keyword in NON_EXPORTABLE_ACTION_KEYWORDS)




def application_timezone_name():
    """Restituisce il fuso orario applicativo configurato.

    Il valore è usato per precompilare data e ora delle nuove azioni nella
    scheda incidente. Se la configurazione è vuota o non valida, viene usato
    il default Europe/Rome.
    """
    value = (setting_value('application_timezone', 'Europe/Rome') or 'Europe/Rome').strip()
    try:
        ZoneInfo(value)
        return value
    except ZoneInfoNotFoundError:
        return 'Europe/Rome'


def application_now():
    """Ora corrente nel fuso orario applicativo, resa naive per i campi HTML/DB."""
    return datetime.now(ZoneInfo(application_timezone_name())).replace(tzinfo=None, second=0, microsecond=0)


def datetime_local_value(value=None):
    """Formatta un datetime per input HTML datetime-local."""
    value = value or application_now()
    return value.replace(second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M')


def format_application_datetime(value, include_timezone=True):
    """Formatta date/ore delle notifiche nel fuso orario applicativo configurato.

    I timestamp applicativi sono memorizzati come datetime naive già riferiti
    al fuso configurato; per le notifiche si esplicita sempre il nome del fuso
    per evitare ambiguità operative.
    """
    if not value:
        return 'non disponibile'
    value = value.replace(second=0, microsecond=0)
    suffix = f' {application_timezone_name()}' if include_timezone else ''
    return value.strftime('%d/%m/%Y %H:%M') + suffix


def utc_to_application_datetime(value):
    """Converte un datetime naive UTC nel fuso applicativo configurato.

    I record audit sono registrati con utcnow() naive. La pagina Audit
    espone però sempre data e ora nel fuso configurato in Admin -> Altre
    configurazioni.
    """
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo('UTC'))
    return value.astimezone(ZoneInfo(application_timezone_name())).replace(tzinfo=None)


def application_to_utc_datetime(value):
    """Converte un datetime naive del fuso applicativo in UTC naive.

    Serve per applicare correttamente i filtri e i purge inseriti dalla UI
    Audit, dove l'utente lavora nella timezone applicativa.
    """
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(application_timezone_name()))
    return value.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)


def format_audit_datetime(value, include_timezone=True):
    local_value = utc_to_application_datetime(value)
    if not local_value:
        return ''
    suffix = f' {application_timezone_name()}' if include_timezone else ''
    return local_value.strftime('%Y-%m-%d %H:%M:%S') + suffix


AUTOMATIC_ACTION_OPERATIONS = {
    'close_without_warnings': 'Chiusura del task in assenza di avvisi procedurali',
    'end_breach': 'Fine violazione',
    'global_check': 'Controllo globale',
}


def action_automatic_operation_list(label=None):
    if not label or getattr(label, 'kind', None) != 'action_label':
        return []
    values = []
    label_to_code = {text: code for code, text in AUTOMATIC_ACTION_OPERATIONS.items()}
    for item in (getattr(label, 'automatic_operations', '') or '').split(','):
        item = item.strip()
        code = item if item in AUTOMATIC_ACTION_OPERATIONS else label_to_code.get(item, '')
        if code and code not in values:
            values.append(code)
    return values


def action_has_automatic_operation(label=None, code=''):
    return (code or '').strip() in action_automatic_operation_list(label)


def apply_action_automatic_operations(incident_id, action):
    """Applica le operazioni automatiche configurate sulla label azione.

    Le operazioni non dipendono più dal nome testuale della label: sono tag
    configurabili da Admin -> Liste configurabili -> Label azioni. Questo rende
    estendibile il comportamento anche per task personalizzati.
    """
    label = getattr(action, 'label', None) or (db.session.get(ConfigLabel, action.label_id) if action.label_id else None)
    operations = action_automatic_operation_list(label)
    if not operations:
        return False
    inc = db.session.get(Incident, incident_id)
    if not inc:
        return False
    db.session.flush()
    state = inspect(inc)
    if state.persistent:
        db.session.expire(inc, ['actions'])
    now = application_now()
    changed = False
    if 'end_breach' in operations:
        inc.end_at = now
        inc.end_date = now.date()
        inc.end_time = now.time().replace(second=0, microsecond=0)
        changed = True
    if 'close_without_warnings' in operations:
        if incident_procedural_status(inc)['has_warnings']:
            setattr(inc, '_closure_blocked_by_procedural_warnings', True)
        else:
            setattr(inc, '_closure_blocked_by_procedural_warnings', False)
            inc.status = 'chiuso'
            inc.end_at = now
            inc.end_date = now.date()
            inc.end_time = now.time().replace(second=0, microsecond=0)
            changed = True
    return changed


# Compatibilità con le chiamate storiche: il comportamento è ora guidato dai
# tag automatici della label, non dal nome "Conclusione".
def close_incident_from_conclusion_action(incident_id, action):
    return apply_action_automatic_operations(incident_id, action)


def incident_procedural_status(inc):
    """Calcola gli avvisi procedurali dagli step workflow richiesti e mancanti.

    Gli avvisi procedurali non sono più hard-coded sui singoli tipi di notifica:
    derivano dagli step applicabili al singolo incidente che l'amministratore ha
    marcato come richiesti nella definizione del workflow. Ogni avviso mostra la
    descrizione operativa dello step, quando presente, altrimenti la descrizione
    o il nome del task/label azione.
    """
    workflow = incident_workflow_status(inc)
    missing_required = [
        step for step in workflow.get('steps', [])
        if step.get('required', True) and not step.get('done')
    ]
    warnings = [step.get('warning_text') or step.get('label') or step.get('task_name') for step in missing_required]
    missing_any = [step for step in workflow.get('steps', []) if not step.get('done')]
    open_incomplete = ((getattr(inc, 'status', '') or '').strip().lower() == 'aperto' and bool(missing_any))
    status = {
        'warnings': warnings,
        'warning_steps': missing_required,
        'missing_steps': missing_any,
        'has_warnings': bool(warnings),
        'has_open_incomplete_workflow': open_incomplete,
        # Compatibilità con template/route storici: i nuovi avvisi non dipendono
        # più da questi flag specifici, ma li manteniamo veri quando non esiste
        # un avviso esplicito della relativa famiglia.
        'has_csirt_notification': not any('csirt' in (w or '').lower() for w in warnings),
        'has_dpo_notification': not any('dpo' in (w or '').lower() for w in warnings),
        'has_privacy_authority_notification': not any(('garante' in (w or '').lower() or 'privacy' in (w or '').lower()) for w in warnings),
        'has_user_notification': not any('utente' in (w or '').lower() for w in warnings),
    }
    return status

def annotate_procedural_status(incidents):
    """Aggiunge attributi transienti usati dalla lista principale.

    La lista incidenti distingue tre stati operativi del workflow:
    warning, se esistono avvisi procedurali attivi; finalizzato, se non ci
    sono avvisi attivi ma l'incidente non è ancora chiuso; ok, se non ci sono
    avvisi attivi e l'incidente è chiuso.
    """
    for inc in incidents:
        status = incident_procedural_status(inc)
        pending_steps = list(status.get('missing_steps', []) or [])
        inc.procedural_pending_steps = pending_steps
        inc.procedural_warnings = status['warnings'] or [step.get('warning_text') or step.get('label') or step.get('task_name') for step in pending_steps]
        has_active_warnings = bool(status.get('has_warnings'))
        inc.has_procedural_warnings = has_active_warnings
        inc.workflow_list_state = 'warning' if has_active_warnings else ('ok' if (getattr(inc, 'status', '') or '').strip().lower() == 'chiuso' else 'finalized')
    return incidents

def unique_int_list(field_name):
    """Restituisce una lista di interi univoci preservando l'ordine del form.

    I campi drag & drop possono inviare lo stesso ID più volte. Se gli stessi
    ID vengono assegnati direttamente alle relazioni many-to-many, SQLAlchemy
    può tentare di inserire doppioni nelle tabelle associative e PostgreSQL
    restituisce ``duplicate key value violates unique constraint``.
    """
    out = []
    seen = set()
    for raw in request.form.getlist(field_name):
        if raw in (None, ''):
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def labels_from_form(kind, field_name):
    ids = unique_int_list(field_name)
    if not ids:
        return []
    rows = tenant_query(ConfigLabel).filter(ConfigLabel.kind == kind, ConfigLabel.id.in_(ids)).all()
    order = {value: idx for idx, value in enumerate(ids)}
    return sorted(rows, key=lambda item: order.get(item.id, 10**9))


def people_from_form(field_name='people'):
    ids = unique_int_list(field_name)
    if not ids:
        return []
    rows = tenant_query(Person).filter(Person.id.in_(ids)).all()
    order = {value: idx for idx, value in enumerate(ids)}
    return sorted(rows, key=lambda item: order.get(item.id, 10**9))


def commit_with_sequence_retry(sequence_tables=None):
    """Commit robusto contro sequence PostgreSQL disallineate.

    In caso di ``duplicate key value violates unique constraint`` riallinea
    tutte le sequence note, oppure quelle richieste dal chiamante, e ritenta
    una sola volta. Se il rollback ha annullato oggetti pending non più
    riutilizzabili, l'eccezione viene rilanciata con log esplicito.
    """
    sequence_tables = sequence_tables or []
    try:
        db.session.commit()
        return
    except IntegrityError as exc:
        db.session.rollback()
        if not is_duplicate_key_integrity_error(exc):
            raise
        current_app.logger.warning('Duplicate key rilevata; riallineo le sequence PostgreSQL e ritento il commit')
        try:
            if sequence_tables:
                for table in sequence_tables:
                    align_table_sequence(table)
            else:
                align_all_table_sequences()
        except Exception:
            current_app.logger.exception('Riallineamento sequence fallito dopo duplicate key')
            raise
        try:
            db.session.commit()
            return
        except IntegrityError:
            current_app.logger.exception('Duplicate key persistente dopo riallineamento sequence')
            db.session.rollback()
            raise

def add_notification_action_safely(inc, label, description):
    """Crea l'azione automatica senza assegnare manualmente la PK.

    In caso di sequenza PostgreSQL disallineata, riallinea e ritenta una sola
    volta per evitare duplicate key durante l'invio notifiche.
    """
    align_table_sequence('action')
    action = Action(
        incident_id=inc.id,
        when_at=application_now(),
        person_name=current_user.name or current_user.username,
        description=description,
        label_id=label.id if label else None,
        exportable=action_exportable_default(label, description),
    )
    db.session.add(action)
    try:
        db.session.flush()
        close_incident_from_conclusion_action(inc.id, action)
        return action
    except IntegrityError as exc:
        db.session.rollback()
        if 'duplicate key value violates unique constraint' not in str(exc):
            raise
        align_table_sequence('action')
        action = Action(
            incident_id=inc.id,
            when_at=application_now(),
            person_name=current_user.name or current_user.username,
            description=description,
            label_id=label.id if label else None,
            exportable=action_exportable_default(label, description),
        )
        db.session.add(action)
        db.session.flush()
        close_incident_from_conclusion_action(inc.id, action)
        return action


def save_action_attachment_file(file_storage, action):
    """Salva un file allegato a una azione e registra il metadato."""
    if not file_storage or not file_storage.filename:
        return None
    name, stored = save_validated_upload(file_storage, current_app.config['UPLOAD_DIR'])
    att = ActionAttachment(action_id=action.id, filename=name, stored_name=stored)
    db.session.add(att)
    return att


def alfresco_is_enabled_safe():
    try:
        from .plugins.alfresco.client import is_enabled as _alfresco_enabled
        return _alfresco_enabled()
    except Exception:
        return False


def attach_document_to_alfresco(doc):
    """Upload an incident document to Alfresco when the plugin is enabled."""
    from .plugins.alfresco.client import upload_file
    if not doc or not doc.stored_name:
        raise RuntimeError('Documento locale non valido per upload Alfresco.')
    local_path = os.path.join(current_app.config['UPLOAD_DIR'], doc.stored_name)
    info = upload_file(local_path, doc.filename or doc.stored_name, incident_id=doc.incident_id)
    doc.alfresco_node_id = info.get('node_id')
    doc.alfresco_path = info.get('path')
    doc.alfresco_uploaded_at = application_now()
    return info


def make_notification_mail_pdf(inc, title, subject, body, sender, recipient, cc):
    """Genera un PDF con il testo della mail inviata, da allegare all'azione automatica."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table as RLTable, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from xml.sax.saxutils import escape

    stored = str(uuid.uuid4()) + f'_notifica-{inc.id}.pdf'
    path = os.path.join(current_app.config['UPLOAD_DIR'], stored)
    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['BodyText'], fontSize=8, leading=10)
    normal = ParagraphStyle('normal_wrap', parent=styles['BodyText'], fontSize=9, leading=12)
    story = [Paragraph(escape(f'Testo mail inviata - {title}'), styles['Title']), Spacer(1, 0.25*cm)]
    meta = [
        ['Incidente', inc.name or ''],
        ['Riferimento', inc.reference or ''],
        ['Destinatario incidente', inc.recipient or inc.reference or ''],
        ['Mittente', sender or ''],
        ['Destinatario mail', recipient or ''],
        ['CC', cc or ''],
        ['Oggetto', subject or ''],
        ['Data generazione', utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')],
    ]
    table = RLTable([[Paragraph(escape(str(a)), small), Paragraph(escape(str(b)), small)] for a,b in meta], colWidths=[4*cm, 12*cm])
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey),('BACKGROUND',(0,0),(0,-1),colors.whitesmoke),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]))
    story += [table, Spacer(1, 0.4*cm), Paragraph('Corpo della mail', styles['Heading2'])]
    for line in (body or '').splitlines() or ['']:
        story.append(Paragraph(escape(line) if line else '&nbsp;', normal))
    doc.build(story)
    return path, stored, f'testo-mail-notifica-{inc.id}-{utcnow().strftime("%Y%m%d%H%M%S")}.pdf'


def labels(kind): return tenant_query(ConfigLabel).filter_by(kind=kind).order_by(ConfigLabel.group,ConfigLabel.value).all()


def workflow_step_key(step):
    return (
        int(step.action_label_id or 0),
        (step.description or '').strip().lower(),
        bool(getattr(step, 'personal_data_only', False)),
        bool(getattr(step, 'requires_notification', False)),
        (getattr(step, 'required_notification_type', None) or '').strip(),
        bool(getattr(step, 'document_generation_enabled', False)),
        (getattr(step, 'document_template_name', None) or '').strip(),
        (getattr(step, 'section_target', None) or '').strip(),
        tuple(step.condition_tokens() if hasattr(step, 'condition_tokens') else []),
    )


def workflow_condition_token_label(token):
    token=(token or '').strip()
    negated = token.startswith('!')
    base = token[1:] if negated else token
    prefix = 'NON ' if negated else ''
    if base == 'personal_data':
        return prefix + 'Rischio per diritti e libertà'
    if base.startswith('severity:'):
        try:
            lab=db.session.get(ConfigLabel, int(base.split(':',1)[1]))
            return prefix + (f"Gravità: {lab.value}" if lab else f"Gravità #{base.split(':',1)[1]}")
        except Exception:
            return prefix + 'Gravità non valida'
    if base.startswith('data_type:'):
        try:
            lab=db.session.get(ConfigLabel, int(base.split(':',1)[1]))
            return prefix + (f"Dati interessati: {lab.value}" if lab else f"Dato interessato #{base.split(':',1)[1]}")
        except Exception:
            return prefix + 'Dato interessato non valido'
    return token

def workflow_condition_tokens_from_form(prefix='conditions'):
    base_allowed={'personal_data'}
    base_allowed.update(f'severity:{x.id}' for x in labels('severity'))
    base_allowed.update(f'data_type:{x.id}' for x in labels('data_type'))
    allowed=set(base_allowed) | {f'!{x}' for x in base_allowed}
    out=[]
    for token in request.form.getlist(prefix):
        token=(token or '').strip()
        if token in allowed and token not in out:
            out.append(token)
    return out

def workflow_document_template_names():
    return {getattr(t, 'name', '') for t in list_templates() if getattr(t, 'name', '')}

def workflow_document_template_from_form(field_name):
    value = (request.form.get(field_name) or '').strip()
    return value if value in workflow_document_template_names() else None

def workflow_update_section_target_from_form(field_name):
    value = (request.form.get(field_name) or '').strip()
    allowed = {code for code, _label in INCIDENT_DETAIL_SECTIONS}
    return value if value in allowed else None

def workflow_step_condition_status(step, inc):
    tokens = step.condition_tokens() if hasattr(step, 'condition_tokens') else []
    if not tokens:
        return True, []
    incident_data_type_ids={int(x.id) for x in (inc.data_types or [])}
    details=[]
    ok=True
    for token in tokens:
        negated = token.startswith('!')
        base = token[1:] if negated else token
        passed=False
        if base == 'personal_data':
            passed=bool(getattr(inc, 'personal_data', False))
        elif base.startswith('severity:'):
            try:
                passed=int(base.split(':',1)[1]) == int(inc.severity_id or 0)
            except Exception:
                passed=False
        elif base.startswith('data_type:'):
            try:
                passed=int(base.split(':',1)[1]) in incident_data_type_ids
            except Exception:
                passed=False
        else:
            passed=False
        if negated:
            passed = not passed
        ok = ok and passed
        details.append({'token': token, 'label': workflow_condition_token_label(token), 'passed': passed})
    return ok, details

def notification_action_label_ids(kind):
    """Return action label IDs that prove a manual notification of this type was sent."""
    ids = set()
    if not kind:
        return ids
    for tmpl in NotificationTemplate.query.filter_by(kind=kind).all():
        if tmpl.action_label_id:
            ids.add(int(tmpl.action_label_id))
    fallback = ConfigLabel.query.filter_by(kind='action_label', value=notification_label_value(kind)).first()
    if fallback:
        ids.add(int(fallback.id))
    return ids

def incident_has_notification_action(inc, kind):
    ids = notification_action_label_ids(kind)
    if not ids:
        return False
    return any((a.label_id in ids) for a in (inc.actions or []))

def default_notification_template_for_kind(kind):
    return get_notification_template(kind, None)

def workflow_notification_document_status(inc, kind):
    """Return whether the documents expected by the notification are already available.

    A notification may be linked to a PDF form template. In that case, when no
    generated/tagged document is available yet, the workflow click must guide the
    operator to document generation/tagging before opening the send form.
    """
    if not kind:
        return {'required': False, 'ready': True, 'section': 'incident-documents', 'message': ''}
    tmpl = default_notification_template_for_kind(kind)
    linked = getattr(tmpl, 'linked_form_template_name', None)
    if linked:
        docs = auto_selected_notification_documents(inc, tmpl, kind)
        if not docs:
            return {
                'required': True,
                'ready': False,
                'section': 'incident-forms',
                'message': f'La notifica richiede documenti generati dal template "{linked}" o documenti taggati per il tipo notifica. Generare o taggare i documenti prima dell’invio.',
            }
    if notification_needs_documents(kind, tmpl.id) and not inc.documents:
        return {
            'required': True,
            'ready': False,
            'section': 'incident-documents',
            'message': 'La notifica richiede documenti allegati, ma l’incidente non contiene ancora documenti. Caricare o generare un documento prima dell’invio.',
        }
    return {'required': bool(linked or notification_needs_documents(kind, tmpl.id)), 'ready': True, 'section': 'incident-documents', 'message': ''}

def incident_category_order_ids(inc):
    available = {c.id for c in (getattr(inc, 'categories', None) or []) if getattr(c, 'id', None)}
    ordered = []
    for raw in (getattr(inc, 'category_order', '') or '').split(','):
        try:
            value = int(raw.strip())
        except (TypeError, ValueError):
            continue
        if value in available and value not in ordered:
            ordered.append(value)
    for cat in (getattr(inc, 'categories', None) or []):
        if getattr(cat, 'id', None) in available and cat.id not in ordered:
            ordered.append(cat.id)
    return ordered

def incident_ordered_categories(inc):
    order = {cid: idx for idx, cid in enumerate(incident_category_order_ids(inc))}
    return sorted(list(getattr(inc, 'categories', None) or []), key=lambda item: order.get(getattr(item, 'id', None), 10**9))

def workflow_steps_for_incident(inc):
    category_ids = incident_category_order_ids(inc)
    rows = []
    if category_ids:
        rows = workflow_step_scope_query(category_ids[0], getattr(inc, 'tenant_id', None)).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    if not rows:
        rows = workflow_step_scope_query(None, getattr(inc, 'tenant_id', None)).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    seen = set()
    deduped = []
    for row in rows:
        conditions_ok, _condition_details = workflow_step_condition_status(row, inc)
        if not conditions_ok:
            continue
        key = workflow_step_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped

def incident_workflow_actions(inc):
    """Return fresh actions for workflow/procedural warning evaluation.

    Some callers evaluate warnings after a manual action has just been flushed,
    while the ``inc.actions`` relationship may already have been loaded earlier
    in the same request by notification/global-check guards. Querying the table
    explicitly keeps automatic operations, such as closure without warnings,
    aligned with the current unit of work and avoids stale relationship caches.
    """
    if not inc or not getattr(inc, 'id', None):
        return list(getattr(inc, 'actions', None) or [])
    return Action.query.filter_by(incident_id=inc.id).order_by(Action.when_at.asc(), Action.id.asc()).all()



DEFAULT_WORKFLOW_STEP_TYPES = [
    {'code': 'registration', 'label': 'Registrazione', 'description': 'Premi per registrare', 'protected': True},
    {'code': 'execution', 'label': 'Esecuzione', 'description': 'Premi per eseguire', 'protected': True},
    {'code': 'update_section', 'label': 'Aggiorna sezione', 'description': 'Aggiorna dati', 'protected': True},
    {'code': 'operation', 'label': 'Operazione', 'description': 'Effettua operazione', 'protected': True},
]
WORKFLOW_STEP_TYPES_JSON_SETTING = 'workflow_step_types_json'
REGISTRATION_STEP_TYPE = 'registration'
LEGACY_REGISTRATION_STEP_TYPE = bytes.fromhex('636f6e6669726d').decode('ascii')
UPDATE_SECTION_STEP_TYPE = 'update_section'
OPERATION_STEP_TYPE = 'operation'
WORKFLOW_UPDATE_SECTION_SCOPE = 'workflow_update_section'
LEGACY_UPDATE_SECTION_STEP_TYPE = bytes.fromhex('73686f775f73656374696f6e').decode('ascii')
LEGACY_WORKFLOW_UPDATE_SECTION_SCOPE = bytes.fromhex('776f726b666c6f775f73656374696f6e').decode('ascii')


def _workflow_update_section_legacy_value(value, *, scope=False):
    text_value = (value or '').strip().lower()
    if scope:
        return WORKFLOW_UPDATE_SECTION_SCOPE if text_value == LEGACY_WORKFLOW_UPDATE_SECTION_SCOPE else text_value
    if text_value == LEGACY_REGISTRATION_STEP_TYPE:
        return REGISTRATION_STEP_TYPE
    return UPDATE_SECTION_STEP_TYPE if text_value == LEGACY_UPDATE_SECTION_STEP_TYPE else text_value


def _workflow_step_type_code_from_label(label, existing=None):
    base = re.sub(r'[^a-z0-9]+', '_', (label or '').strip().lower()).strip('_')
    if not base:
        base = 'step'
    if base in {LEGACY_REGISTRATION_STEP_TYPE, REGISTRATION_STEP_TYPE, 'execution', UPDATE_SECTION_STEP_TYPE, OPERATION_STEP_TYPE}:
        base = f'custom_{base}'
    code = base[:40].strip('_') or 'step'
    existing = set(existing or [])
    candidate = code
    idx = 2
    while candidate in existing:
        suffix = f'_{idx}'
        candidate = f'{code[:40-len(suffix)]}{suffix}'.strip('_')
        idx += 1
    return candidate


def workflow_step_type_records():
    """Restituisce le tipologie di step workflow configurate.

    Le tipologie standard sono sempre presenti e non eliminabili; le loro
    descrizioni restano modificabili. Le tipologie custom sono memorizzate in
    JSON nei setting per evitare una migrazione di schema invasiva.
    """
    if has_request_context():
        cached = getattr(g, '_cir_workflow_step_type_records', None)
        if cached is not None:
            return [dict(item) for item in cached]
    raw = setting_value(WORKFLOW_STEP_TYPES_JSON_SETTING, '')
    configured = []
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                configured = data
        except (TypeError, ValueError):
            configured = []

    by_code = {}
    order = []
    for default in DEFAULT_WORKFLOW_STEP_TYPES:
        code = default['code']
        desc = setting_value(f'workflow_step_type_{code}_description', default['description']) or default['description']
        rec = {**default, 'description': desc, 'protected': True}
        by_code[code] = rec
        order.append(code)

    for item in configured:
        if not isinstance(item, dict):
            continue
        code = re.sub(r'[^a-z0-9_]+', '_', (item.get('code') or '').strip().lower()).strip('_')
        code = _workflow_update_section_legacy_value(code)
        if not code:
            continue
        if code in by_code:
            if item.get('description'):
                by_code[code]['description'] = str(item.get('description') or '').strip()[:120] or by_code[code]['description']
            continue
        label = str(item.get('label') or code.replace('_', ' ').title()).strip()[:80]
        description = str(item.get('description') or label).strip()[:120] or label
        by_code[code] = {'code': code, 'label': label, 'description': description, 'protected': False}
        order.append(code)
    records = [by_code[code] for code in order if code in by_code]
    if has_request_context():
        g._cir_workflow_step_type_records = [dict(item) for item in records]
    return records


def save_workflow_step_type_records(records):
    cleaned = []
    default_by_code = {item['code']: item for item in DEFAULT_WORKFLOW_STEP_TYPES}
    existing = set()
    for item in records or []:
        code = re.sub(r'[^a-z0-9_]+', '_', (item.get('code') or '').strip().lower()).strip('_')
        code = _workflow_update_section_legacy_value(code)
        if not code or code in existing:
            continue
        if code in default_by_code:
            default = default_by_code[code]
            label = default['label']
            protected = True
        else:
            label = str(item.get('label') or code.replace('_', ' ').title()).strip()[:80]
            protected = False
        description = str(item.get('description') or label).strip()[:120] or label
        cleaned.append({'code': code, 'label': label, 'description': description, 'protected': protected})
        existing.add(code)
    for default in DEFAULT_WORKFLOW_STEP_TYPES:
        if default['code'] not in existing:
            cleaned.insert(len([r for r in cleaned if r.get('protected')]), dict(default))
            existing.add(default['code'])
    by_code = {item['code']: item for item in cleaned}
    for default in DEFAULT_WORKFLOW_STEP_TYPES:
        set_setting_value(f"workflow_step_type_{default['code']}_description", by_code[default['code']]['description'])
    set_setting_value(WORKFLOW_STEP_TYPES_JSON_SETTING, json.dumps(cleaned, ensure_ascii=False))


def workflow_step_type_pairs():
    return [(item['code'], item['label']) for item in workflow_step_type_records()]


def workflow_step_type_codes():
    return {item['code'] for item in workflow_step_type_records()}


def normalize_workflow_step_type(value):
    value = _workflow_update_section_legacy_value(value or REGISTRATION_STEP_TYPE)
    return value if value in workflow_step_type_codes() else REGISTRATION_STEP_TYPE

def workflow_step_type_uses_section_target(value):
    return normalize_workflow_step_type(value) in {UPDATE_SECTION_STEP_TYPE, OPERATION_STEP_TYPE}


def parse_workflow_scope_value(value):
    raw = (value or 'default').strip()
    if raw in {'', 'default'}:
        return None
    if raw.startswith('category:'):
        raw = raw.split(':', 1)[1]
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        return None
    return cid if tenant_query(ConfigLabel).filter_by(id=cid).first() else None

def workflow_scope_display_name(category_id):
    if not category_id:
        return 'Flusso di default'
    lab = db.session.get(ConfigLabel, int(category_id))
    return f"Categoria: {lab.value}" if lab else f"Categoria: {category_id}"


def workflow_step_base_query(tenant_id=None):
    """Return workflow steps scoped to a single tenant.

    Workflow definitions are tenant-specific.  Keeping every query scoped avoids
    showing or editing flows cloned for another tenant and prevents the
    creation of apparent duplicate/spurious flows after tenant cloning.
    """
    tid = tenant_id if tenant_id is not None else current_tenant_id(default_to_default=True)
    q = IncidentWorkflowStep.query
    try:
        default_id = default_tenant().id
    except Exception:
        default_id = None
    if default_id and int(tid or 0) == int(default_id):
        # Legacy backups/tests may contain pre-multitenancy workflow rows with
        # NULL tenant_id.  Treat them as belonging to the default tenant only;
        # never expose NULL rows in cloned/non-default tenants.
        return q.filter(or_(IncidentWorkflowStep.tenant_id == tid, IncidentWorkflowStep.tenant_id.is_(None)))
    return q.filter(IncidentWorkflowStep.tenant_id == tid)


def workflow_step_scope_query(category_id=None, tenant_id=None):
    q = workflow_step_base_query(tenant_id)
    if category_id:
        return q.filter(IncidentWorkflowStep.category_id == int(category_id))
    return q.filter(IncidentWorkflowStep.category_id.is_(None))


def delete_workflow_steps(category_id=None, tenant_id=None):
    rows = workflow_step_scope_query(category_id, tenant_id).all()
    for row in rows:
        db.session.delete(row)
    return len(rows)


def workflow_scope_options(category_map=None, tenant_id=None):
    tid = tenant_id if tenant_id is not None else current_tenant_id(default_to_default=True)
    if category_map is None:
        cats = ConfigLabel.query.filter_by(tenant_id=tid, kind='category').order_by(ConfigLabel.value).all()
    elif isinstance(category_map, dict):
        cats = category_map.values()
    else:
        cats = category_map
    counts = {
        (cid or 0): count
        for cid, count in db.session.query(IncidentWorkflowStep.category_id, func.count(IncidentWorkflowStep.id))
        .filter(IncidentWorkflowStep.tenant_id == tid)
        .group_by(IncidentWorkflowStep.category_id).all()
    }
    opts = [{'value':'default','label':'Flusso di default','has_workflow': counts.get(0,0)>0}]
    for c in sorted(cats, key=lambda x: (x.value or '').lower()):
        opts.append({'value': f'category:{c.id}', 'label': f'Categoria: {c.value}', 'has_workflow': counts.get(c.id,0)>0})
    return opts


def workflow_scope_options_by_tenant(tenants=None):
    tenant_rows = tenants if tenants is not None else Tenant.query.order_by(Tenant.name).all()
    grouped = []
    for tenant in tenant_rows:
        options = workflow_scope_options(tenant_id=tenant.id)
        grouped.append({
            'tenant': tenant,
            'options': options,
            'source_options': [opt for opt in options if opt.get('has_workflow')],
            'destination_options': [opt for opt in options if opt.get('has_workflow')],
        })
    return grouped




def _unique_config_label_value(kind, base_value, tenant_id):
    base = (base_value or 'Workflow clonato').strip()[:120] or 'Workflow clonato'
    existing_values = {
        row.value for row in ConfigLabel.query.filter_by(tenant_id=tenant_id, kind=kind).all()
    }
    if base not in existing_values:
        return base
    for idx in range(2, 1000):
        suffix = f" (copia {idx})"
        candidate = (base[: max(1, 120 - len(suffix))] + suffix).strip()
        if candidate not in existing_values:
            return candidate
    return f"{base[:100]} ({datetime.utcnow().strftime('%Y%m%d%H%M%S')})"[:120]


def create_new_workflow_destination_for_clone(source_category_id, source_tenant_id, dest_tenant_id):
    """Materialize the synthetic "Nuovo workflow" destination.

    Cloning must be idempotent: when the destination tenant already contains an
    equivalent category label, it is reused instead of creating a duplicate.
    """
    if source_category_id:
        source_category = ConfigLabel.query.filter_by(id=int(source_category_id), tenant_id=source_tenant_id, kind='category').first()
        if not source_category:
            return None, 'Categoria sorgente non trovata nel tenant selezionato.'
        dest_category = _copy_or_update_label_to_tenant(source_category, dest_tenant_id)
        return dest_category.id, None

    # A cloned default workflow needs a category-specific scope in the target
    # tenant.  Reuse the same synthetic category if a previous clone already
    # created it, so repeated operations do not proliferate labels.
    existing = ConfigLabel.query.filter_by(
        tenant_id=dest_tenant_id,
        kind='category',
        value='Flusso di default clonato',
    ).first()
    if existing:
        return existing.id, None
    align_table_sequence('config_label')
    clone = ConfigLabel(
        tenant_id=dest_tenant_id,
        kind='category',
        group='',
        value='Flusso di default clonato',
        description='Workflow creato clonando il flusso di default di un altro tenant.',
        max_completion_hours=0,
        default_exportable=True,
        description_required=False,
        automatic_operations='',
    )
    db.session.add(clone)
    db.session.flush()
    return clone.id, None


def parse_workflow_scope_value_for_tenant(value, tenant_id):
    raw = (value or 'default').strip()
    if raw in {'', 'default'}:
        return None
    if raw.startswith('category:'):
        raw = raw.split(':', 1)[1]
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        return None
    return cid if ConfigLabel.query.filter_by(id=cid, tenant_id=tenant_id, kind='category').first() else None


def workflow_scope_value_valid_for_tenant(value, tenant_id):
    raw = (value or 'default').strip()
    if raw in {'', 'default'}:
        return True
    if raw.startswith('category:'):
        raw = raw.split(':', 1)[1]
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        return False
    return ConfigLabel.query.filter_by(id=cid, tenant_id=tenant_id, kind='category').first() is not None


def _workflow_scope_name_for_tenant(category_id, tenant_id):
    if not category_id:
        return 'Flusso di default'
    lab = ConfigLabel.query.filter_by(id=int(category_id), tenant_id=tenant_id, kind='category').first()
    return f"Categoria: {lab.value}" if lab else f"Categoria: {category_id}"


def _map_workflow_condition_tokens_to_tenant(tokens, target_tenant_id):
    mapped = []
    for token in tokens or []:
        raw = (token or '').strip()
        if not raw:
            continue
        negated = raw.startswith('!')
        base = raw[1:] if negated else raw
        mapped_base = base
        if base.startswith('severity:') or base.startswith('data_type:'):
            prefix, raw_id = base.split(':', 1)
            try:
                source_label = db.session.get(ConfigLabel, int(raw_id))
            except Exception:
                source_label = None
            if not source_label:
                continue
            target_label = _copy_label_to_tenant(source_label, target_tenant_id)
            mapped_base = f'{prefix}:{target_label.id}'
        elif base != 'personal_data':
            mapped_base = base
        mapped_token = f'!{mapped_base}' if negated else mapped_base
        if mapped_token not in mapped:
            mapped.append(mapped_token)
    return mapped


def clone_workflow_steps(source_category_id, destination_category_id, overwrite=False, source_tenant_id=None, destination_tenant_id=None):
    source_tid = source_tenant_id if source_tenant_id is not None else current_tenant_id(default_to_default=True)
    dest_tid = destination_tenant_id if destination_tenant_id is not None else source_tid
    source_steps = workflow_step_scope_query(source_category_id, source_tid).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    if not source_steps:
        return {'ok': False, 'message': 'Il workflow sorgente non contiene step da clonare.'}
    existing = workflow_step_scope_query(destination_category_id, dest_tid).count()
    if existing and not overwrite:
        return {'ok': False, 'message': f'Il workflow destinazione contiene già {existing} step: confermare la sovrascrittura usando Sovrascrivi prima di clonare.'}
    if existing and overwrite:
        delete_workflow_steps(destination_category_id, dest_tid)
        db.session.flush()
    copied = 0
    cross_tenant = int(source_tid or 0) != int(dest_tid or 0)
    for src in source_steps:
        if cross_tenant:
            target_action = _copy_label_to_tenant(src.action_label, dest_tid)
            if not target_action:
                continue
            action_label_id = target_action.id
            mapped_conditions = _map_workflow_condition_tokens_to_tenant(src.condition_tokens(), dest_tid)
        else:
            action_label_id = src.action_label_id
            mapped_conditions = src.condition_tokens()
        clone = IncidentWorkflowStep(tenant_id=dest_tid, category_id=destination_category_id, action_label_id=action_label_id, description=src.description or '', step_type=normalize_workflow_step_type(getattr(src, 'step_type', REGISTRATION_STEP_TYPE)), personal_data_only=('personal_data' in mapped_conditions), conditions=','.join(mapped_conditions), required=bool(src.required), requires_notification=bool(getattr(src, 'requires_notification', False)), required_notification_type=getattr(src, 'required_notification_type', None), document_generation_enabled=bool(getattr(src, 'document_generation_enabled', False)), document_template_name=getattr(src, 'document_template_name', None), section_target=getattr(src, 'section_target', None), position=src.position)
        db.session.add(clone)
        copied += 1
    db.session.commit()
    if source_tid == dest_tid:
        source_name = workflow_scope_display_name(source_category_id)
        dest_name = workflow_scope_display_name(destination_category_id)
    else:
        source_tenant = db.session.get(Tenant, int(source_tid))
        dest_tenant = db.session.get(Tenant, int(dest_tid))
        source_name = f"{getattr(source_tenant, 'name', source_tid)} / {_workflow_scope_name_for_tenant(source_category_id, source_tid)}"
        dest_name = f"{getattr(dest_tenant, 'name', dest_tid)} / {_workflow_scope_name_for_tenant(destination_category_id, dest_tid)}"
    return {'ok': True, 'message': f'Workflow clonato da {source_name} a {dest_name}: {copied} step copiati.'}


def workflow_step_type_description(step_type):
    code = normalize_workflow_step_type(step_type)
    for item in workflow_step_type_records():
        if item['code'] == code:
            return item.get('description') or item.get('label') or 'Premi per registrare'
    return 'Premi per registrare'


def workflow_step_type_label(step_type):
    code = normalize_workflow_step_type(step_type)
    for item in workflow_step_type_records():
        if item['code'] == code:
            return item.get('label') or code
    return 'Registrazione'

def incident_workflow_status(inc):
    steps = workflow_steps_for_incident(inc)
    action_counts = {}
    for action in incident_workflow_actions(inc):
        if action.label_id:
            action_counts[action.label_id] = action_counts.get(action.label_id, 0) + 1
    used_counts = {}
    items = []
    first_missing_found = False
    start = first_initial_information_at(inc)
    now = application_now()
    for step in steps:
        label_id = step.action_label_id
        step_type = normalize_workflow_step_type(getattr(step, 'step_type', REGISTRATION_STEP_TYPE))
        used = used_counts.get(label_id, 0)
        total = action_counts.get(label_id, 0)
        done = used < total
        if done:
            used_counts[label_id] = used + 1
        label = step.action_label
        max_hours = int(getattr(label, 'max_completion_hours', 0) or 0) if label else 0
        due_at = None
        remaining_text = ''
        expired = False
        if max_hours > 0 and start:
            due_at = start + timedelta(hours=max_hours)
            remaining = due_at - now
            total_seconds = int(remaining.total_seconds())
            sign = '' if total_seconds >= 0 else '-'
            total_seconds = abs(total_seconds)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            remaining_text = f'{sign}{hours}h {minutes:02d}m'
            expired = remaining.total_seconds() <= 0
        requires_notification = bool(getattr(step, 'requires_notification', False))
        required_notification_type = (getattr(step, 'required_notification_type', None) or '').strip()
        notification_done = incident_has_notification_action(inc, required_notification_type) if requires_notification else True
        doc_status = workflow_notification_document_status(inc, required_notification_type) if requires_notification and not notification_done else {'required': False, 'ready': True, 'section': 'incident-documents', 'message': ''}
        ntype = get_notification_type(required_notification_type) if required_notification_type else None
        document_generation_enabled = bool(getattr(step, 'document_generation_enabled', False))
        document_template_name = (getattr(step, 'document_template_name', None) or '').strip()
        first_incomplete = (not done and not first_missing_found)
        if first_incomplete:
            first_missing_found = True
        items.append({
            'id': step.id,
            'action_label_id': label_id,
            'label': (label.description or label.value) if label else '',
            'task_name': label.value if label else '',
            'task_description': (label.description or '') if label else '',
            'description': step.description or '',
            'flow_description': step.description or '',
            'description_required': bool(getattr(label, 'description_required', False)) if label else False,
            'step_type': step_type,
            'step_type_label': workflow_step_type_label(getattr(step, 'step_type', REGISTRATION_STEP_TYPE)), 
            'step_type_description': workflow_step_type_description(getattr(step, 'step_type', REGISTRATION_STEP_TYPE)),
            'personal_data_only': bool(getattr(step, 'personal_data_only', False)),
            'conditions': [workflow_condition_token_label(t) for t in (step.condition_tokens() if hasattr(step, 'condition_tokens') else [])],
            'required': bool(getattr(step, 'required', True)),
            'warning_text': (step.description or ((label.description or label.value) if label else '')),
            'requires_notification': requires_notification,
            'required_notification_type': required_notification_type,
            'required_notification_label': ntype.label if ntype else required_notification_type,
            'notification_done': notification_done,
            'notification_url': url_for('main.notify_preview', iid=inc.id, kind=required_notification_type) if required_notification_type else '',
            'notification_docs_required': bool(doc_status.get('required')),
            'notification_docs_ready': bool(doc_status.get('ready')),
            'notification_docs_section': doc_status.get('section') or 'incident-documents',
            'notification_docs_message': doc_status.get('message') or '',
            'document_generation_enabled': document_generation_enabled,
            'document_template_name': document_template_name,
            'document_generation_url': url_for('main.workflow_step_generate_document', iid=inc.id, sid=step.id) if document_generation_enabled and document_template_name else '',
            'section_target': getattr(step, 'section_target', '') or '',
            'section_target_url': ('#' + getattr(step, 'section_target', '')) if workflow_step_type_uses_section_target(step_type) and getattr(step, 'section_target', None) else '',
            'position': step.position,
            'done': done,
            'missing': not done,
            'first_incomplete': first_incomplete,
            'max_completion_hours': max_hours,
            'due_at': due_at,
            'due_at_text': format_application_datetime(due_at) if due_at else '',
            'remaining_text': remaining_text,
            'expired': expired,
        })
    return {'steps': items, 'completed': sum(1 for x in items if x['done']), 'total': len(items), 'all_done': bool(items) and all(x['done'] for x in items), 'ordered': len(items) > 1 and any((x.get('position') or 0) != 0 for x in items)}
def can_write():
    return user_role_for_tenant() in ['superuser','admin','writer']

def can_admin():
    return user_role_for_tenant() in ['superuser','admin']

def can_manage_external_recipients_from_settings():
    return current_user.is_authenticated and user_role_for_tenant() == 'writer'


def user_has_any_active_role(user):
    if not user:
        return False
    if getattr(user, 'is_builtin_admin', False) or getattr(user, 'is_global_superuser', False):
        return True
    return bool(user_accessible_tenant_ids(user) or [])


def mfa_required_for(user):
    return bool(user and getattr(user, 'mfa_enabled', False) and getattr(user, 'auth_provider', 'local') in ['local','ldap'] and MfaTotpToken.query.filter_by(user_id=user.id).filter(MfaTotpToken.verified_at.isnot(None)).first())

def complete_login_or_mfa(user):
    clear_login_failures(user.username)
    if mfa_required_for(user):
        session['mfa_user_id'] = user.id
        session['mfa_next'] = request.args.get('next') or url_for('main.index')
        return redirect(url_for('main.mfa_verify'))
    session.clear()
    login_user(user)
    session.permanent = True
    selected_tid = active_tenant_id(default_to_default=True)
    if selected_tid:
        session['active_tenant_id'] = int(selected_tid)
        session['active_tenant_scope_enabled'] = True
    session['last_activity'] = time.time()
    audit_log('security:login_success', {'username': user.username, 'auth_provider': user.auth_provider}, actor_type='user', commit=True)
    return redirect(request.args.get('next') or url_for('main.index'))

def visible(q):
    if hasattr(Incident, 'tenant_id'):
        tid = current_tenant_id()
        if tid:
            # Il tenant attivo deve sempre determinare il perimetro operativo,
            # anche per superuser/admin globali. Le funzioni di export globale
            # usano percorsi dedicati e non questa query di visibilità UI.
            q = q.filter(or_(Incident.tenant_id == tid, Incident.tenant_id.is_(None)))
    role = user_role_for_tenant()
    if role in ['superuser','admin','reader','writer']:
        return q
    if role=='operator':
        return q.filter(Incident.creator_id==current_user.id)
    return q.filter(False)
@bp.before_request
def block_disabled():
    g.lang = detect_interface_language()
    if getattr(current_user, 'is_authenticated', False) and is_superuser():
        raw_tid = session.get('active_tenant_id')
        try:
            if raw_tid and not db.session.get(Tenant, int(raw_tid)):
                session.pop('active_tenant_id', None)
        except Exception:
            session.pop('active_tenant_id', None)
    if current_user.is_authenticated:
        now = time.time()
        timeout_config = current_app.config.get('PERMANENT_SESSION_LIFETIME') or 1800
        try:
            timeout = int(timeout_config.total_seconds())
        except AttributeError:
            timeout = int(timeout_config)
        last = float(session.get('last_activity') or now)
        if now - last > timeout:
            audit_log('security:session_timeout', {'username': current_user.username}, actor_type='user', commit=True)
            logout_user(); session.clear(); flash('Sessione scaduta per inattività.', 'warning'); return redirect(url_for('main.login'))
        session['last_activity'] = now
    if session.get('mfa_user_id') and request.endpoint not in ['main.mfa_verify','main.login','main.logout','static']:
        return redirect(url_for('main.mfa_verify'))
    if current_user.is_authenticated and not user_has_any_active_role(current_user) and request.endpoint not in ['main.logout','main.login','main.sso_login','main.sso_callback','main.admin_tenant_activate']:
        logout_user(); flash('Utente disabilitato. Contattare un amministratore.','error'); return redirect(url_for('main.login'))


def setting_map():
    tid = current_tenant_id(default_to_default=True)
    data = {}
    # Global/shared settings first, then tenant-scoped overrides.
    for row in Setting.query.all():
        key = row.key or ''
        if key.startswith('tenant:'):
            continue
        data[key] = decrypt_setting_value(key, row.value)
    if tid:
        prefix = f'tenant:{int(tid)}:'
        for row in Setting.query.filter(Setting.key.startswith(prefix)).all():
            logical = row.key[len(prefix):]
            data[logical] = decrypt_setting_value(logical, row.value)
    return data

def bool_setting(cfg, key, default=False):
    value = str(cfg.get(key, '1' if default else '') or '').strip().lower()
    return value in {'1', 'true', 'yes', 'on', 'si', 'sì'}

def sso_legacy_settings():
    cfg = setting_map()
    return {
        'id': 'legacy',
        'sso_enabled': cfg.get('sso_enabled', '0'),
        'sso_provider_name': cfg.get('sso_provider_name', 'SSO'),
        'sso_authorization_url': cfg.get('sso_authorization_url', ''),
        'sso_token_url': cfg.get('sso_token_url', ''),
        'sso_userinfo_url': cfg.get('sso_userinfo_url', ''),
        'sso_client_id': cfg.get('sso_client_id', ''),
        'sso_client_secret': cfg.get('sso_client_secret', ''),
        'sso_scopes': cfg.get('sso_scopes', 'openid email profile'),
        'sso_username_claim': cfg.get('sso_username_claim', 'preferred_username'),
        'sso_email_claim': cfg.get('sso_email_claim', 'email'),
        'sso_name_claim': cfg.get('sso_name_claim', 'name'),
        'sso_subject_claim': cfg.get('sso_subject_claim', 'sub'),
        'sso_auto_create_users': cfg.get('sso_auto_create_users', '1'),
        'sso_default_role': cfg.get('sso_default_role', 'disabled'),
    }


def _normalize_sso_profile(profile, fallback_id=None):
    profile = dict(profile or {})
    raw_id = str(profile.get('id') or fallback_id or profile.get('sso_provider_name') or 'sso').strip().lower()
    profile_id = re.sub(r'[^a-z0-9_-]+', '-', raw_id).strip('-') or 'sso'
    return {
        'id': profile_id[:80],
        'sso_enabled': '1' if bool_setting(profile, 'sso_enabled') else '0',
        'sso_provider_name': str(profile.get('sso_provider_name') or profile.get('name') or 'SSO').strip() or 'SSO',
        'sso_authorization_url': str(profile.get('sso_authorization_url') or '').strip(),
        'sso_token_url': str(profile.get('sso_token_url') or '').strip(),
        'sso_userinfo_url': str(profile.get('sso_userinfo_url') or '').strip(),
        'sso_client_id': str(profile.get('sso_client_id') or '').strip(),
        'sso_client_secret': str(profile.get('sso_client_secret') or ''),
        'sso_scopes': str(profile.get('sso_scopes') or 'openid email profile').strip() or 'openid email profile',
        'sso_username_claim': str(profile.get('sso_username_claim') or 'preferred_username').strip() or 'preferred_username',
        'sso_email_claim': str(profile.get('sso_email_claim') or 'email').strip() or 'email',
        'sso_name_claim': str(profile.get('sso_name_claim') or 'name').strip() or 'name',
        'sso_subject_claim': str(profile.get('sso_subject_claim') or 'sub').strip() or 'sub',
        'sso_auto_create_users': '1' if bool_setting(profile, 'sso_auto_create_users', True) else '0',
        'sso_default_role': str(profile.get('sso_default_role') or 'disabled').strip() or 'disabled',
        'sso_logo_path': str(profile.get('sso_logo_path') or '').strip(),
    }


def sso_profiles(include_legacy=True):
    cfg = setting_map()
    raw = cfg.get('sso_profiles_json', '')
    profiles = []
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                seen = set()
                for idx, item in enumerate(data):
                    if isinstance(item, dict):
                        prof = _normalize_sso_profile(item, f'sso-{idx+1}')
                        base = prof['id']; n = 2
                        while prof['id'] in seen:
                            prof['id'] = f'{base}-{n}'; n += 1
                        seen.add(prof['id'])
                        profiles.append(prof)
        except Exception:
            current_app.logger.exception('Unable to parse sso_profiles_json')
    if not profiles and include_legacy:
        legacy = sso_legacy_settings()
        if bool_setting(legacy, 'sso_enabled') or legacy.get('sso_client_id') or legacy.get('sso_authorization_url'):
            profiles.append(_normalize_sso_profile(legacy, 'legacy'))
    return profiles


def save_sso_profiles(profiles):
    normalized = [_normalize_sso_profile(p, f'sso-{i+1}') for i, p in enumerate(profiles or [])]
    s = db.session.get(Setting, 'sso_profiles_json') or Setting(key='sso_profiles_json')
    s.value = store_setting_value('sso_profiles_json', json.dumps(normalized, ensure_ascii=False, indent=2))
    db.session.merge(s)


def sso_settings(profile_id=None):
    profiles = sso_profiles()
    if profile_id:
        for profile in profiles:
            if profile.get('id') == profile_id:
                return profile
    if profiles:
        return profiles[0]
    return _normalize_sso_profile({}, 'sso')


def active_sso_profiles():
    return [p for p in sso_profiles() if sso_is_enabled(p)]


def sso_is_enabled(cfg=None):
    cfg = cfg or sso_settings()
    return bool_setting(cfg, 'sso_enabled') and bool(cfg.get('sso_authorization_url')) and bool(cfg.get('sso_token_url')) and bool(cfg.get('sso_client_id'))


def sso_callback_url():
    """Return the OAuth2 callback URL using HTTPS.

    Identity Providers generally require secure redirect URIs in production.
    The application therefore always displays and uses an https:// callback
    URL for SSO/OAuth2 profiles, even when Flask receives an internal HTTP
    request behind a reverse proxy or in a container network.
    """
    try:
        return url_for('main.sso_callback', _external=True, _scheme='https')
    except Exception:
        url = url_for('main.sso_callback', _external=True)
        if url.startswith('http://'):
            return 'https://' + url[len('http://'):]
        return url


def generic_sso_profile():
    return {
        'id': 'generic-sso',
        'sso_enabled': '0',
        'sso_provider_name': 'Generic SSO',
        'sso_authorization_url': '',
        'sso_token_url': '',
        'sso_userinfo_url': '',
        'sso_client_id': '',
        'sso_client_secret': '',
        'sso_scopes': 'openid email profile',
        'sso_username_claim': 'preferred_username',
        'sso_email_claim': 'email',
        'sso_name_claim': 'name',
        'sso_subject_claim': 'sub',
        'sso_auto_create_users': '1',
        'sso_default_role': 'disabled',
        'sso_logo_path': '',
    }


def google_sso_example_profile():
    return {
        'id': 'google',
        'sso_enabled': '0',
        'sso_provider_name': 'Google',
        'sso_authorization_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'sso_token_url': 'https://oauth2.googleapis.com/token',
        'sso_userinfo_url': 'https://openidconnect.googleapis.com/v1/userinfo',
        'sso_client_id': '',
        'sso_client_secret': '',
        'sso_scopes': 'openid email profile',
        'sso_username_claim': 'email',
        'sso_email_claim': 'email',
        'sso_name_claim': 'name',
        'sso_subject_claim': 'sub',
        'sso_auto_create_users': '1',
        'sso_default_role': 'disabled',
        'sso_logo_path': 'sso/google-logo.svg',
    }


def sso_logo_storage_dir():
    """Directory persistente dei loghi SSO, condivisa tra profili e full export.

    La directory è configurabile tramite SSO_LOGO_DIR all'avvio del container
    ed è pensata per essere montata su volume persistente, fuori dall'area
    statica effimera dell'immagine applicativa.
    """
    target_dir = Path(current_app.config.get('SSO_LOGO_DIR') or os.getenv('SSO_LOGO_DIR') or '/data/sso_logos')
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def list_sso_logo_assets():
    """Restituisce i loghi SSO disponibili nello storage condiviso."""
    allowed = {'.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
    items = []
    target_dir = sso_logo_storage_dir()
    for path in sorted(target_dir.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and path.suffix.lower() in allowed:
            items.append({
                'name': path.name,
                'relative_path': f'sso/{path.name}',
                'size': path.stat().st_size,
            })
    return items


def save_sso_logo_upload(file_storage):
    """Aggiunge un logo allo storage SSO condiviso.

    Il file viene salvato nella directory persistente configurata con
    SSO_LOGO_DIR e poi può essere associato a uno o più profili dalla
    configurazione del profilo.
    """
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return ''
    filename = secure_filename(file_storage.filename)
    ext = Path(filename).suffix.lower()
    if ext not in {'.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        raise ValueError('Formato logo SSO non supportato. Usare SVG, PNG, JPG, GIF o WEBP.')
    stem = re.sub(r'[^a-zA-Z0-9_-]+', '-', Path(filename).stem).strip('-') or 'sso-logo'
    target_dir = sso_logo_storage_dir()
    target_name = f'{stem}{ext}'
    target = target_dir / target_name
    n = 2
    while target.exists():
        target_name = f'{stem}-{n}{ext}'
        target = target_dir / target_name
        n += 1
    validate_upload_file(file_storage, allowed_extensions={'.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp'}, max_size=2 * 1024 * 1024)
    file_storage.save(target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return f'sso/{target_name}'




def delete_sso_logo_asset(relative_path):
    """Rimuove un logo dallo storage condiviso e lo sgancia dai profili SSO.

    La rimozione è limitata alla directory SSO_LOGO_DIR per evitare path traversal.
    Restituisce il numero di profili aggiornati.
    """
    rel = str(relative_path or '').strip().replace('\\', '/')
    if not rel.startswith('sso/') or '/' in rel[4:]:
        raise ValueError('Logo SSO non valido.')
    target = sso_logo_storage_dir() / Path(rel).name
    if not target.exists() or not target.is_file():
        raise ValueError('Logo SSO non trovato nello storage.')
    target.unlink()
    profiles = sso_profiles(include_legacy=True)
    changed = 0
    for prof in profiles:
        if prof.get('sso_logo_path') == rel:
            prof['sso_logo_path'] = ''
            changed += 1
    if changed:
        save_sso_profiles(profiles)
    return changed

def sso_test_configuration(cfg):
    """Esegue controlli non distruttivi sulla configurazione OAuth2/SSO.

    Il test non completa un login reale perché il flusso OAuth2 richiede
    interazione dell'utente con il provider. Verifica però la presenza dei
    parametri obbligatori, la raggiungibilità degli endpoint e costruisce la
    URL di autorizzazione che verrà usata dal pulsante di login.
    """
    checks = []

    def add(name, ok, message, detail=''):
        checks.append({'name': name, 'ok': bool(ok), 'message': message, 'detail': detail})

    required = {
        'Authorization endpoint': cfg.get('sso_authorization_url'),
        'Token endpoint': cfg.get('sso_token_url'),
        'Client ID': cfg.get('sso_client_id'),
    }
    missing = [name for name, value in required.items() if not value]
    add('Parametri obbligatori', not missing, 'Tutti i parametri obbligatori sono presenti' if not missing else 'Parametri mancanti: ' + ', '.join(missing))
    add('UserInfo endpoint', bool(cfg.get('sso_userinfo_url')), 'Endpoint UserInfo configurato' if cfg.get('sso_userinfo_url') else 'Endpoint UserInfo non configurato: necessario per ottenere i claim utente')
    add('Scope', bool((cfg.get('sso_scopes') or '').strip()), 'Scope configurati: ' + (cfg.get('sso_scopes') or '') if (cfg.get('sso_scopes') or '').strip() else 'Nessuno scope configurato')
    add('Claim utente', bool(cfg.get('sso_subject_claim') and cfg.get('sso_username_claim')), 'Claim principali configurati' if cfg.get('sso_subject_claim') and cfg.get('sso_username_claim') else 'Configurare almeno claim soggetto e username')

    timeout = 10
    headers = {'Accept': 'application/json, text/html;q=0.9, */*;q=0.8'}
    for label, url, method in [
        ('Authorization endpoint', cfg.get('sso_authorization_url'), 'GET'),
        ('Token endpoint', cfg.get('sso_token_url'), 'OPTIONS'),
        ('UserInfo endpoint', cfg.get('sso_userinfo_url'), 'GET'),
    ]:
        if not url:
            continue
        try:
            if label == 'Authorization endpoint':
                params = {
                    'response_type': 'code',
                    'client_id': cfg.get('sso_client_id') or 'test-client-id',
                    'redirect_uri': sso_callback_url(),
                    'scope': cfg.get('sso_scopes') or 'openid email profile',
                    'state': 'configuration-test',
                }
                response = requests.get(url, params=params, headers=headers, timeout=timeout, allow_redirects=False)
                ok = response.status_code < 500
                add(label, ok, f'Endpoint raggiungibile, HTTP {response.status_code}' if ok else f'Errore server HTTP {response.status_code}', response.headers.get('location',''))
            elif label == 'Token endpoint':
                response = requests.options(url, headers=headers, timeout=timeout, allow_redirects=False)
                if response.status_code in (404, 405, 501):
                    response = requests.post(url, data={'grant_type': 'authorization_code', 'code': 'configuration-test', 'redirect_uri': sso_callback_url(), 'client_id': cfg.get('sso_client_id') or 'configuration-test'}, headers={'Accept': 'application/json'}, timeout=timeout, allow_redirects=False)
                ok = response.status_code < 500
                add(label, ok, f'Endpoint raggiungibile, HTTP {response.status_code}' if ok else f'Errore server HTTP {response.status_code}')
            else:
                response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False)
                ok = response.status_code in (200, 400, 401, 403) or response.status_code < 500
                msg = 'Endpoint raggiungibile; una risposta 401/403 è normale senza access token' if ok else f'Errore server HTTP {response.status_code}'
                add(label, ok, f'{msg} (HTTP {response.status_code})')
        except Exception as exc:
            add(label, False, f'Errore di connessione: {exc}')

    auth_preview = ''
    if cfg.get('sso_authorization_url'):
        params = {
            'response_type': 'code',
            'client_id': cfg.get('sso_client_id') or '',
            'redirect_uri': sso_callback_url(),
            'scope': cfg.get('sso_scopes') or 'openid email profile',
            'state': 'generated-during-test',
        }
        auth_preview = cfg.get('sso_authorization_url') + ('&' if '?' in cfg.get('sso_authorization_url') else '?') + urlencode(params)
    success = all(item['ok'] for item in checks)
    return {'checks': checks, 'success': success, 'authorization_preview': auth_preview}


def sso_user_from_claims(claims, cfg):
    subject_claim = cfg.get('sso_subject_claim') or 'sub'
    username_claim = cfg.get('sso_username_claim') or 'preferred_username'
    email_claim = cfg.get('sso_email_claim') or 'email'
    name_claim = cfg.get('sso_name_claim') or 'name'
    subject = str(claims.get(subject_claim) or claims.get('sub') or '').strip()
    username = str(claims.get(username_claim) or claims.get('preferred_username') or claims.get(email_claim) or subject).strip()
    email = str(claims.get(email_claim) or claims.get('email') or '').strip()
    name = str(claims.get(name_claim) or claims.get('name') or username).strip()
    if not username:
        raise ValueError('Il provider SSO non ha restituito un identificativo utente utilizzabile')
    profile_id = cfg.get('id') or 'sso'
    provider_key = f"sso:{profile_id}"
    external_subject = f"{profile_id}:{subject}" if subject else None
    user = None
    if external_subject:
        user = User.query.filter_by(auth_provider=provider_key, external_id=external_subject).first()
    if not user:
        user = User.query.filter_by(username=username, auth_provider=provider_key).first()
    created_auto = False
    if not user:
        if not bool_setting(cfg, 'sso_auto_create_users', True):
            raise ValueError('Utente SSO non registrato e creazione automatica disabilitata')
        try:
            align_table_sequence('user')
        except Exception:
            current_app.logger.exception('Riallineamento sequenza user non completato prima della creazione utente SSO')
        default_role = cfg.get('sso_default_role') or 'disabled'
        default_tid = current_tenant_id()
        user = User(username=username, name=name, email=email, role='disabled', tenant_id=default_tid, default_tenant_id=default_tid, is_ldap=False, auth_provider=provider_key, external_id=external_subject, password_hash=None)
        db.session.add(user)
        db.session.flush()
        upsert_user_tenant_role(user, default_tid, default_role)
        created_auto = True
    else:
        user.name = name or user.name
        user.email = email or user.email
        user.auth_provider = provider_key
        if external_subject:
            user.external_id = external_subject
        user.is_ldap = False
    db.session.commit()
    if created_auto and not user_has_any_active_role(user):
        notify_admin_disabled_user_created(user, source='SSO/OAuth2')
    return user

def ldap_auth(username,password):
    cfg=setting_map()
    uri=cfg.get('ldap_uri'); base=cfg.get('ldap_base_dn'); filt=cfg.get('ldap_user_filter') or '(uid={uid})'
    if not uri or not base: return None
    search_filter=make_ldap_search_filter(filt, username)
    try:
        srv=Server(uri,get_info=ALL); bind_dn=cfg.get('ldap_bind_dn') or None; bind_pw=cfg.get('ldap_bind_password') or None
        with Connection(srv, user=bind_dn, password=bind_pw, auto_bind=True) as c:
            c.search(base, search_filter, attributes=['uid','cn','mail'])
            if not c.entries: return None
            entry=c.entries[0]; dn=entry.entry_dn
        with Connection(srv, user=dn, password=password, auto_bind=True): pass
        name=str(getattr(entry,'cn',username)); email=str(getattr(entry,'mail',''))
        return {'username':username,'name':name,'email':email}
    except Exception as e:
        current_app.logger.warning('LDAP login failed for %s: %s', username, e); return None
@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form['username'].strip(); p=request.form['password']
        blocked, remaining = login_is_blocked(u)
        if blocked:
            audit_log('security:login_blocked', {'username': u, 'remaining_seconds': remaining}, actor_type='anonymous', commit=True)
            flash(f'Troppi tentativi falliti. Riprovare tra {remaining} secondi.', 'error')
            return render_template('login.html', sso=sso_settings(), sso_enabled=sso_is_enabled(), sso_profiles=active_sso_profiles())
        user=User.query.filter_by(username=u, auth_provider='local').first()
        if user and not user.is_ldap and verify_password(user.password_hash,p): return complete_login_or_mfa(user)
        info=ldap_auth(u,p)
        if info:
            user=User.query.filter_by(username=u, auth_provider='ldap').first()
            if not user:
                try:
                    align_table_sequence('user')
                except Exception:
                    current_app.logger.exception('Riallineamento sequenza user non completato prima della creazione utente LDAP')
                default_tid = current_tenant_id()
                user=User(username=u,is_ldap=True,auth_provider='ldap',name=info['name'],email=info['email'],role='disabled',tenant_id=default_tid,default_tenant_id=default_tid); db.session.add(user); db.session.flush(); upsert_user_tenant_role(user, default_tid, 'disabled'); db.session.commit(); notify_admin_disabled_user_created(user, source='LDAP')
            else:
                user.name=info['name']; user.email=info['email']; user.is_ldap=True; user.auth_provider='ldap'; db.session.commit()
            if not user_has_any_active_role(user): flash('Utente LDAP registrato ma disabilitato.','error'); return render_template('login.html', sso=sso_settings(), sso_enabled=sso_is_enabled())
            return complete_login_or_mfa(user)
        register_login_failure(u)
        current_app.logger.warning('Errore password/login per utente %s',u); flash('Credenziali non valide.','error')
    profiles = active_sso_profiles()
    return render_template('login.html', sso=sso_settings(), sso_enabled=bool(profiles), sso_profiles=profiles)

@bp.route('/sso/login')
@bp.route('/sso/login/<profile_id>')
def sso_login(profile_id=None):
    profiles = active_sso_profiles()
    if not profiles:
        flash('Login SSO non configurato o non abilitato.', 'error')
        return redirect(url_for('main.login'))
    requested_profile = profile_id or request.args.get('profile')
    cfg = sso_settings(requested_profile) if requested_profile else profiles[0]
    if not sso_is_enabled(cfg):
        flash('Profilo SSO non configurato o non abilitato.', 'error')
        return redirect(url_for('main.login'))
    state = secrets.token_urlsafe(32)
    session['sso_state'] = state
    session['sso_profile_id'] = cfg.get('id')
    params = {
        'response_type': 'code',
        'client_id': cfg.get('sso_client_id'),
        'redirect_uri': sso_callback_url(),
        'scope': cfg.get('sso_scopes') or 'openid email profile',
        'state': state,
    }
    return redirect(cfg.get('sso_authorization_url') + ('&' if '?' in cfg.get('sso_authorization_url') else '?') + urlencode(params))

@bp.route('/sso/callback')
def sso_callback():
    cfg = sso_settings(session.get('sso_profile_id'))
    if not sso_is_enabled(cfg):
        flash('Login SSO non configurato o non abilitato.', 'error')
        return redirect(url_for('main.login'))
    if request.args.get('error'):
        flash('Login SSO annullato o rifiutato: ' + request.args.get('error_description', request.args.get('error')), 'error')
        return redirect(url_for('main.login'))
    if not request.args.get('state') or request.args.get('state') != session.pop('sso_state', None):
        flash('Stato SSO non valido. Riprovare il login.', 'error')
        return redirect(url_for('main.login'))
    session.pop('sso_profile_id', None)
    code = request.args.get('code')
    if not code:
        flash('Codice OAuth2 mancante nella risposta SSO.', 'error')
        return redirect(url_for('main.login'))
    try:
        token_response = requests.post(
            cfg.get('sso_token_url'),
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': sso_callback_url(),
                'client_id': cfg.get('sso_client_id'),
                'client_secret': cfg.get('sso_client_secret') or '',
            },
            headers={'Accept': 'application/json'},
            timeout=15,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data.get('access_token')
        if not access_token:
            raise ValueError('Access token non presente nella risposta OAuth2')
        userinfo_url = cfg.get('sso_userinfo_url')
        if not userinfo_url:
            raise ValueError('Endpoint UserInfo non configurato')
        userinfo_response = requests.get(userinfo_url, headers={'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'}, timeout=15)
        userinfo_response.raise_for_status()
        claims = userinfo_response.json()
        user = sso_user_from_claims(claims, cfg)
        if not user_has_any_active_role(user):
            flash('Utente SSO registrato ma disabilitato. Contattare un amministratore.', 'error')
            return redirect(url_for('main.login'))
        return complete_login_or_mfa(user)
    except Exception as exc:
        current_app.logger.exception('SSO login failed')
        flash(f'Login SSO fallito: {exc}', 'error')
        return redirect(url_for('main.login'))

@bp.route('/logout')
def logout():
    if current_user.is_authenticated:
        audit_log('security:logout', {'username': current_user.username}, actor_type='user', commit=True)
    logout_user(); session.clear(); return redirect(url_for('main.login'))

@bp.route('/info/applicazione')
@login_required
def app_info():
    return render_template('app_info.html')
@bp.route('/')
@login_required
def index():
    q = visible(Incident.query)
    kw = request.args.get('q', '')
    label = request.args.get('label', '')
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    sort = request.args.get('sort', 'start_at')
    direction = request.args.get('dir', 'desc')
    reverse = direction != 'asc'
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get('per_page', 20))
    except (TypeError, ValueError):
        per_page = 20
    if per_page < 1:
        per_page = 20
    per_page = min(per_page, 100)

    if kw:
        q = q.filter(or_(
            Incident.name.ilike(f'%{kw}%'),
            Incident.description.ilike(f'%{kw}%'),
            Incident.reference.ilike(f'%{kw}%'),
            Incident.creator_name.ilike(f'%{kw}%')
        ))
    if start:
        start_dt = datetime.fromisoformat(start)
        q = q.filter(or_(
            Incident.start_date > start_dt.date(),
            and_(Incident.start_date == start_dt.date(), Incident.start_time >= start_dt.time())
        ))
    if end:
        end_dt = datetime.fromisoformat(end)
        q = q.filter(or_(
            Incident.start_date < end_dt.date(),
            and_(Incident.start_date == end_dt.date(), Incident.start_time <= end_dt.time())
        ))
    if label:
        q = q.join(Incident.actions).join(Action.label).filter(ConfigLabel.value.ilike(f'%{label}%'))

    total = q.count()
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    # Ordinamento su tutte le colonne mostrate nella home.
    # Le colonne semplici vengono ordinate e paginate in SQL; quelle calcolate
    # o multi-valore vengono ordinate in Python e poi affettate.
    sql_sort_map = {
        'name': Incident.name,
        'reference': Incident.reference,
        'creator_name': Incident.creator_name,
        'status': Incident.status,
    }
    if sort in sql_sort_map:
        col = sql_sort_map[sort]
        incidents = q.order_by(col.asc() if direction == 'asc' else col.desc()).offset(offset).limit(per_page).all()
    else:
        incidents_all = q.all()
        def duration_seconds(inc):
            return inc.effective_duration_seconds or 0
        def people_names(inc):
            return ', '.join(sorted([p.name or '' for p in inc.people]))
        sort_key_map = {
            'people': people_names,
            'duration': duration_seconds,
        }
        incidents_all = sorted(incidents_all, key=sort_key_map.get(sort, lambda inc: inc.start_at or datetime.min), reverse=reverse)
        incidents = incidents_all[offset:offset + per_page]

    annotate_procedural_status(incidents)

    query_args = request.args.to_dict(flat=True)
    query_args['per_page'] = str(per_page)
    query_args['page'] = str(page)

    return render_template(
        'index.html',
        incidents=incidents,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        page_start=(offset + 1 if total else 0),
        page_end=min(offset + len(incidents), total),
        per_page_options=[20, 50, 100],
        query_args=query_args,
        labels=labels('action_label'),
        sort=sort,
        direction=direction,
        incident_move_tenants=Tenant.query.order_by(Tenant.name).all() if is_superuser() else [],
        current_tenant_id=current_tenant_id(),
    )


def combine_incident_date_time(prefix, fallback_field=None, default_now=False):
    """Combina i nuovi campi separati data/ora, con fallback al vecchio datetime-local."""
    date_value = (request.form.get(f'{prefix}_date') or '').strip()
    time_value = (request.form.get(f'{prefix}_time') or '').strip()
    legacy_value = (request.form.get(fallback_field or f'{prefix}_at') or '').strip()
    if date_value:
        if not time_value:
            time_value = '00:00'
        return datetime.fromisoformat(f'{date_value}T{time_value}')
    if legacy_value:
        return datetime.fromisoformat(legacy_value)
    if default_now:
        return application_now()
    return None

def sync_incident_split_datetime(inc):
    """Mantiene allineati i campi separati con i datetime storici usati dal codice esistente."""
    if inc.start_at:
        inc.start_date = inc.start_at.date()
        inc.start_time = inc.start_at.time().replace(second=0, microsecond=0)
    if inc.end_at:
        inc.end_date = inc.end_at.date()
        inc.end_time = inc.end_at.time().replace(second=0, microsecond=0)
    else:
        inc.end_date = None
        inc.end_time = None



def incident_detail_redirect(iid, default_anchor=''):
    """Redirect alla pagina incidente conservando la sezione di provenienza del form."""
    anchor = (request.form.get('scroll_anchor') or default_anchor or '').strip().lstrip('#')
    target = url_for('main.incident_detail', iid=iid)
    return redirect(f'{target}#{anchor}' if anchor else target)


def incident_absolute_url(inc_or_id):
    """Restituisce il link diretto assoluto alla pagina dettaglio incidente."""
    incident_id = getattr(inc_or_id, 'id', inc_or_id)
    base = (setting_value('application_external_url', 'http://localhost:8000') or 'http://localhost:8000').rstrip('/')
    return f'{base}/incident/{incident_id}'


def _csv_ids_from_objects(objects):
    return ','.join(str(x.id) for x in (objects or []) if getattr(x, 'id', None))

def _csv_ids_from_form(field_name):
    seen=[]
    for raw in request.form.getlist(field_name):
        try:
            value=int(raw)
        except (TypeError, ValueError):
            continue
        if value not in seen:
            seen.append(value)
    return ','.join(str(x) for x in seen)

def _objects_by_ids(model, ids):
    clean=[]
    for x in ids or []:
        try:
            clean.append(int(x))
        except (TypeError, ValueError):
            pass
    return tenant_query(model).filter(model.id.in_(clean)).all() if clean else []


def _objects_by_ids_preserving_order(model, ids):
    """Return objects in the exact order supplied by the caller/form."""
    clean=[]
    for x in ids or []:
        try:
            value = int(x)
        except (TypeError, ValueError):
            continue
        if value not in clean:
            clean.append(value)
    if not clean:
        return []
    by_id = {obj.id: obj for obj in tenant_query(model).filter(model.id.in_(clean)).all()}
    return [by_id[x] for x in clean if x in by_id]

def incident_template_form_payload():
    return dict(
        name=(request.form.get('template_name') or request.form.get('name') or '').strip(),
        description=request.form.get('template_description') or '',
        incident_name=request.form.get('incident_name') or request.form.get('source_incident_name') or '',
        reference=request.form.get('reference') or None,
        recipient=request.form.get('recipient') or None,
        recipient_email=request.form.get('recipient_email') or None,
        incident_description=request.form.get('incident_description') or request.form.get('description') or '',
        severity_id=request.form.get('severity_id') or None,
        personal_data=bool(request.form.get('personal_data')),
        data_subjects_count=request.form.get('data_subjects_count') or None,
        data_volume=request.form.get('data_volume') or None,
        status=request.form.get('status') or 'aperto',
        category_ids=_csv_ids_from_form('categories'),
        data_type_ids=_csv_ids_from_form('data_types'),
        people_ids=_csv_ids_from_form('people'),
        recommendation_ids=_csv_ids_from_form('recommendations'),
    )

def incident_template_from_incident(inc, name=None, description=''):
    return IncidentTemplate(
        tenant_id=getattr(inc, 'tenant_id', None) or current_tenant_id(),
        name=name or f'Modello da {inc.name}',
        description=description or '',
        incident_name=inc.name or '',
        reference=inc.reference,
        recipient=inc.recipient,
        recipient_email=getattr(inc, 'recipient_email', None),
        incident_description=inc.description or '',
        severity_id=inc.severity_id,
        personal_data=bool(inc.personal_data),
        data_subjects_count=inc.data_subjects_count,
        data_volume=inc.data_volume,
        status=inc.status or 'aperto',
        category_ids=_csv_ids_from_objects(inc.categories),
        data_type_ids=_csv_ids_from_objects(inc.data_types),
        people_ids=_csv_ids_from_objects(inc.people),
        recommendation_ids=_csv_ids_from_objects(inc.recommendations),
    )



def incident_template_client_payload(template):
    """Return a sanitized payload used by the UI to apply a template client-side."""
    if template is None:
        return {}
    return {
        'id': template.id,
        'name': template.name or '',
        'description': template.description or '',
        'incident_name': template.incident_name or '',
        'reference': template.reference or '',
        'recipient': template.recipient or '',
        'recipient_email': template.recipient_email or '',
        'incident_description': template.incident_description or '',
        'severity_id': str(template.severity_id or ''),
        'personal_data': bool(template.personal_data),
        'data_subjects_count': template.data_subjects_count or '',
        'data_volume': template.data_volume or '',
        'status': template.status or 'aperto',
        'category_ids': [str(x) for x in template.category_id_list()],
        'data_type_ids': [str(x) for x in template.data_type_id_list()],
        'people_ids': [str(x) for x in template.people_id_list()],
        'recommendation_ids': [str(x) for x in template.recommendation_id_list()],
    }

def incident_template_client_payloads():
    return [incident_template_client_payload(t) for t in tenant_query(IncidentTemplate).order_by(IncidentTemplate.name).all()]

def incident_template_context(template=None):
    return dict(
        template=template,
        selected_template=template,
        selected_template_categories=_objects_by_ids_preserving_order(ConfigLabel, template.category_id_list()) if template else [],
        selected_template_data_types=_objects_by_ids_preserving_order(ConfigLabel, template.data_type_id_list()) if template else [],
        selected_template_people=_objects_by_ids_preserving_order(Person, template.people_id_list()) if template else [],
        selected_template_recommendations=_objects_by_ids_preserving_order(Recommendation, template.recommendation_id_list()) if template else [],
        severities=labels('severity'),
        categories=labels('category'),
        data_types=labels('data_type'),
        people=tenant_query(Person).order_by(Person.name).all(),
        recommendations=tenant_query(Recommendation).order_by(Recommendation.text).all(),
        recommendations_max_per_incident=recommendations_limit(),
        external_recipients=get_external_recipients(),
        incident_form_visible_fields=incident_form_visible_fields(),
        incident_detail_visible_fields=incident_detail_general_visible_fields(),
        incident_ldap_lookup_enabled=incident_ldap_lookup_enabled(),
        document_download_rule_templates=document_download_rule_templates(),
    )


@bp.route('/admin/incident-form-fields', methods=['GET','POST'])
@login_required
def admin_incident_form_fields():
    if not can_admin(): return redirect(url_for('main.index'))
    new_all_codes = [code for code, _label, _required in INCIDENT_FORM_FIELDS]
    detail_all_codes = [code for code, _label, _required in incident_detail_visibility_field_records()]
    if request.method == 'POST':
        selected_new = [code for code in request.form.getlist('new_visible_field') if code in new_all_codes]
        selected_new = list(dict.fromkeys(selected_new + list(incident_form_required_field_codes())))
        selected_detail = [code for code in request.form.getlist('detail_visible_field') if code in detail_all_codes]
        selected_detail = list(dict.fromkeys(selected_detail))
        set_setting_value('incident_form_default_visible_fields', ','.join(selected_new))
        set_setting_value('incident_detail_general_visible_fields', ','.join(selected_detail))
        db.session.commit()
        flash('Configurazione layout campi incidenti salvata.', 'success')
        return redirect(url_for('main.admin_incident_form_fields'))
    return render_template(
        'admin_incident_form_fields.html',
        incident_form_fields=INCIDENT_FORM_FIELDS,
        incident_detail_fields=incident_detail_visibility_field_records(),
        visible_fields=incident_form_visible_fields(),
        detail_visible_fields=incident_detail_general_visible_fields(),
    )

@bp.route('/admin/incident-custom-fields', methods=['GET','POST'])
@login_required
def admin_incident_custom_fields():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method == 'POST':
        before_codes = {field['code'] for field in incident_custom_field_definitions()}
        save_incident_custom_field_definitions_from_form()
        # Keep newly created personal fields visible by default in the detail layout,
        # preserving the previous behavior where active custom fields appeared immediately.
        after_fields = incident_custom_field_definitions()
        setting = db.session.get(Setting, 'incident_detail_general_visible_fields')
        if setting is not None:
            current = incident_detail_general_visible_fields()
            for field in after_fields:
                if field.get('enabled', True) and field['code'] not in before_codes:
                    current.add(f"custom:{field['code']}")
            allowed = {code for code, _label, _required in incident_detail_visibility_field_records()}
            set_setting_value('incident_detail_general_visible_fields', ','.join([code for code in allowed if code in current]))
        db.session.commit()
        flash('Campi personalizzati nei Dati Generali salvati.', 'success')
        return redirect(url_for('main.admin_incident_custom_fields'))
    return render_template(
        'admin_incident_custom_fields.html',
        custom_field_types=CUSTOM_INCIDENT_FIELD_TYPES,
        custom_incident_fields=incident_custom_field_definitions(),
    )

@bp.route('/admin/incident-templates',methods=['GET','POST'])
@login_required
def admin_incident_templates():
    if not can_admin(): return redirect(url_for('main.index'))
    editing=None
    edit_id=request.args.get('edit', type=int)
    if edit_id:
        editing=model_or_404(IncidentTemplate, edit_id)
    if request.method=='POST':
        action=request.form.get('action') or 'save'
        if action=='delete':
            tmpl=model_or_404(IncidentTemplate, request.form.get('id', type=int))
            db.session.delete(tmpl); db.session.commit(); flash('Modello incidente cancellato.'); return redirect(url_for('main.admin_incident_templates'))
        if action=='create_from_incident':
            inc=model_or_404(Incident, request.form.get('incident_id', type=int))
            tmpl=incident_template_from_incident(inc, request.form.get('template_name') or f'Modello da {inc.name}', request.form.get('template_description') or '')
            db.session.add(tmpl); db.session.commit(); flash('Modello creato dall’incidente esistente, senza azioni e documenti.'); return redirect(url_for('main.admin_incident_templates'))
        payload=incident_template_form_payload()
        if not payload['name']:
            flash('Il nome del modello è obbligatorio.', 'error')
            return redirect(url_for('main.admin_incident_templates'))
        recipient_email_error = validate_incident_recipient_email_fields(payload.get('reference'), payload.get('recipient'), payload.get('recipient_email'))
        if recipient_email_error:
            flash(recipient_email_error, 'error')
            return redirect(url_for('main.admin_incident_templates', edit=request.form.get('id', type=int)) if request.form.get('id') else url_for('main.admin_incident_templates'))
        tid=request.form.get('id', type=int)
        tmpl=model_or_404(IncidentTemplate, tid) if tid else None
        if tmpl is None:
            tmpl=IncidentTemplate(tenant_id=current_tenant_id()); db.session.add(tmpl)
        for k,v in payload.items(): setattr(tmpl,k,v)
        try:
            db.session.commit(); flash('Modello incidente salvato.')
        except IntegrityError:
            db.session.rollback(); flash('Esiste già un modello con questo nome.', 'error')
        return redirect(url_for('main.admin_incident_templates'))
    return render_template('admin_incident_templates.html', templates=tenant_query(IncidentTemplate).order_by(IncidentTemplate.name).all(), editing=editing, incidents=tenant_query(Incident, include_all_for_superuser=True).order_by(Incident.created_at.desc()).limit(200).all(), **incident_template_context(editing))

@bp.route('/incident/<int:iid>/create-template',methods=['POST'])
@login_required
def incident_create_template(iid):
    if not can_admin(): return redirect(url_for('main.index'))
    inc=model_or_404(Incident, iid)
    name=(request.form.get('template_name') or f'Modello da {inc.name}').strip()
    tmpl=incident_template_from_incident(inc, name, request.form.get('template_description') or '')
    db.session.add(tmpl)
    try:
        db.session.commit(); flash('Modello creato dall’incidente corrente, senza azioni e documenti.')
    except IntegrityError:
        db.session.rollback(); flash('Esiste già un modello con questo nome.', 'error')
    return incident_detail_redirect(iid, 'incident-main')

@bp.route('/incident/new',methods=['GET','POST'])
@login_required
def incident_new():
    if not can_write(): flash('Permessi insufficienti','error'); return redirect(url_for('main.index'))
    selected_template = model_or_404(IncidentTemplate, request.args.get('template_id', type=int)) if request.args.get('template_id') else None
    if request.method=='POST':
        reference_value = (request.form.get('reference') or '').strip()
        if not reference_value:
            flash('Il campo Riferimento è obbligatorio per ogni incidente.', 'error')
            now_dt = application_now()
            return render_template('incident_form.html',inc=None,severities=labels('severity'),categories=labels('category'),data_types=labels('data_type'),people=tenant_query(Person).order_by(Person.name).all(), recommendations=tenant_query(Recommendation).order_by(Recommendation.text).all(), recommendations_max_per_incident=recommendations_limit(), incident_templates=tenant_query(IncidentTemplate).order_by(IncidentTemplate.name).all(), selected_template=selected_template, incident_template_payloads=incident_template_client_payloads(), default_start_date=now_dt.date().isoformat(), default_start_time=now_dt.strftime('%H:%M'), application_timezone=application_timezone_name(), external_recipients=get_external_recipients(), incident_form_visible_fields=incident_form_visible_fields(), incident_ldap_lookup_enabled=incident_ldap_lookup_enabled())
        recipient_value = (request.form.get('recipient') or '').strip()
        recipient_email_value = (request.form.get('recipient_email') or '').strip()
        recipient_email_error = validate_incident_recipient_email_fields(reference_value, recipient_value, recipient_email_value)
        if recipient_email_error:
            flash(recipient_email_error, 'error')
            now_dt = application_now()
            return render_template('incident_form.html',inc=None,severities=labels('severity'),categories=labels('category'),data_types=labels('data_type'),people=tenant_query(Person).order_by(Person.name).all(), recommendations=tenant_query(Recommendation).order_by(Recommendation.text).all(), recommendations_max_per_incident=recommendations_limit(), incident_templates=tenant_query(IncidentTemplate).order_by(IncidentTemplate.name).all(), selected_template=selected_template, incident_template_payloads=incident_template_client_payloads(), default_start_date=now_dt.date().isoformat(), default_start_time=now_dt.strftime('%H:%M'), application_timezone=application_timezone_name(), external_recipients=get_external_recipients(), incident_form_visible_fields=incident_form_visible_fields(), incident_ldap_lookup_enabled=incident_ldap_lookup_enabled())
        start_at = combine_incident_date_time('start', 'start_at', default_now=True)
        end_at = combine_incident_date_time('end', 'end_at')
        inc=Incident(tenant_id=current_tenant_id(),creator_id=current_user.id,creator_name=current_user.name,creator_email=current_user.email,name=request.form['name'],reference=reference_value,recipient=recipient_value or None,recipient_email=recipient_email_value or None,description=request.form.get('description'),severity_id=request.form.get('severity_id') or None,personal_data=bool(request.form.get('personal_data')),data_subjects_count=request.form.get('data_subjects_count') or None,data_volume=request.form.get('data_volume') or None,start_at=start_at,end_at=end_at,status=request.form.get('status','aperto'))
        sync_incident_split_datetime(inc)
        inc.categories = labels_from_form('category', 'categories')
        inc.category_order = _csv_ids_from_form('categories')
        inc.data_types = labels_from_form('data_type', 'data_types')
        inc.people = people_from_form('people')
        inc.recommendations = recommendations_from_form('recommendations')
        align_table_sequence('incident')
        db.session.add(inc)
        try:
            add_automatic_button_action(inc, 'incident_update')
            db.session.commit()
            return redirect(url_for('main.incident_detail', iid=inc.id))
        except IntegrityError as exc:
            db.session.rollback()
            current_app.logger.exception('Errore durante la creazione del nuovo incidente')
            if 'duplicate key value violates unique constraint' in str(exc):
                align_table_sequence('incident')
                flash('Errore di sequenza del database corretto. Riprovare la creazione dell\'incidente.', 'error')
            else:
                flash(f'Errore durante la creazione dell\'incidente: {exc}', 'error')
    now_dt = application_now()
    return render_template('incident_form.html',inc=None,severities=labels('severity'),categories=labels('category'),data_types=labels('data_type'),people=tenant_query(Person).order_by(Person.name).all(), recommendations=tenant_query(Recommendation).order_by(Recommendation.text).all(), recommendations_max_per_incident=recommendations_limit(), incident_templates=tenant_query(IncidentTemplate).order_by(IncidentTemplate.name).all(), selected_template=selected_template, incident_template_payloads=incident_template_client_payloads(), default_start_date=now_dt.date().isoformat(), default_start_time=now_dt.strftime('%H:%M'), application_timezone=application_timezone_name(), external_recipients=get_external_recipients(), incident_form_visible_fields=incident_form_visible_fields(), incident_ldap_lookup_enabled=incident_ldap_lookup_enabled())
@bp.route('/incident/<int:iid>',methods=['GET','POST'])
@login_required
def incident_detail(iid):
    inc=visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if request.method=='POST':
        if not can_write(): flash('Permessi insufficienti','error'); return redirect(url_for('main.incident_detail',iid=iid))
        requested_status = request.form.get('status')
        reference_value = (request.form.get('reference') or '').strip()
        if not reference_value:
            section_flash('Il campo Riferimento è obbligatorio per ogni incidente.', 'incident-main', 'danger')
            return incident_detail_redirect(iid, 'incident-main')
        recipient_value = (request.form.get('recipient') or '').strip()
        recipient_email_value = (request.form.get('recipient_email') or '').strip()
        recipient_email_error = validate_incident_recipient_email_fields(reference_value, recipient_value, recipient_email_value)
        if recipient_email_error:
            section_flash(recipient_email_error, 'incident-main', 'danger')
            return incident_detail_redirect(iid, 'incident-main')
        inc.name=request.form['name']; inc.reference=reference_value; inc.recipient=recipient_value or None; inc.recipient_email=recipient_email_value or None; inc.description=request.form.get('description'); inc.severity_id=request.form.get('severity_id') or None; inc.personal_data=bool(request.form.get('personal_data')); inc.data_subjects_count=request.form.get('data_subjects_count') or None; inc.data_volume=request.form.get('data_volume') or None; inc.deadline_notifications_muted=bool(request.form.get('deadline_notifications_muted')); inc.start_at=combine_incident_date_time('start', 'start_at', default_now=True); inc.end_at=combine_incident_date_time('end', 'end_at'); sync_incident_split_datetime(inc)
        if requested_status == 'chiuso' and incident_procedural_status(inc)['has_warnings']:
            section_flash('Impossibile chiudere l’incidente: sono ancora presenti avvisi procedurali attivi.', 'incident-main', 'danger')
        else:
            inc.status=requested_status
        inc.categories = labels_from_form('category', 'categories')
        inc.category_order = _csv_ids_from_form('categories')
        inc.data_types = labels_from_form('data_type', 'data_types')
        inc.people = people_from_form('people')
        inc.recommendations = recommendations_from_form('recommendations')
        update_incident_custom_field_values_from_form(inc)
        try:
            add_automatic_button_action(inc, 'incident_update')
            db.session.commit()
            section_flash('Incidente aggiornato', 'incident-main', 'success')
        except IntegrityError as exc:
            db.session.rollback()
            current_app.logger.exception('Errore durante l\'aggiornamento dell\'incidente')
            flash(f'Errore durante l\'aggiornamento dell\'incidente: {exc}', 'error')
        return incident_detail_redirect(iid, 'incident-main')
    procedural_status = incident_procedural_status(inc)
    selected_categories = incident_ordered_categories(inc)
    active_workflow_document_template = current_workflow_document_template(inc)
    return render_template(
        'incident_detail.html',
        inc=inc,
        selected_categories=selected_categories,
        severities=labels('severity'),
        categories=labels('category'),
        data_types=labels('data_type'),
        people=tenant_query(Person).order_by(Person.name).all(),
        action_labels=labels('action_label'),
        has_csirt_notification=procedural_status['has_csirt_notification'],
        has_dpo_notification=procedural_status['has_dpo_notification'],
        has_privacy_authority_notification=procedural_status['has_privacy_authority_notification'],
        has_user_notification=procedural_status['has_user_notification'],
        procedural_warnings=procedural_status['warnings'],
        procedural_warning_steps=procedural_status['warning_steps'],
        notification_types=notification_type_records(),
        form_templates=list_templates(),
        recommendations=tenant_query(Recommendation).order_by(Recommendation.text).all(),
        recommendations_max_per_incident=recommendations_limit(),
        owner_name=setting_value('security_owner_name'),
        owner_role=setting_value('security_owner_role'),
        owner_email=setting_value('security_owner_email'),
        structure_name=setting_value('structure_name'),
        responsible_name=setting_value('security_responsible_name'),
        responsible_email=setting_value('security_responsible_email'),
        responsible_phone=setting_value('security_responsible_phone','-'),
        responsible_function=setting_value('security_responsible_function'),
        consequences=incident_consequences(inc),
        measures=incident_measures(inc),
        default_action_when=datetime_local_value(),
        workflow_status=incident_workflow_status(inc),
        application_timezone=application_timezone_name(),
        section_messages=section_messages,
        global_messages=global_messages,
        split_email_list=_split_email_list,
        external_recipients=get_external_recipients(),
        incident_form_visible_fields=incident_form_visible_fields(),
        incident_detail_visible_fields=incident_detail_general_visible_fields(),
        incident_ldap_lookup_enabled=incident_ldap_lookup_enabled(),
        document_download_rule_templates=document_download_rule_templates(),
        active_workflow_document_template=active_workflow_document_template,
        template_stem=lambda value: Path(str(value or '').strip()).stem,
        custom_incident_fields=visible_custom_incident_field_definitions(),
        custom_incident_values=incident_custom_field_values(inc),
    )

@bp.route('/incident/<int:iid>/move-tenant', methods=['POST'])
@login_required
def incident_move_tenant(iid):
    if not is_superuser():
        flash('Solo gli utenti superuser e l’utente admin possono spostare incidenti tra tenant.', 'danger')
        return redirect(url_for('main.index'))
    inc = db.session.get(Incident, iid)
    if inc is None:
        abort(404)
    source_tenant_id = inc.tenant_id
    target_tenant = tenant_or_404(request.form.get('target_tenant_id', type=int))
    try:
        moved = move_incident_to_tenant(inc, target_tenant.id)
        db.session.flush()
        session['active_tenant_id'] = target_tenant.id
        session['active_tenant_scope_enabled'] = True
        session.modified = True
        audit_log('incident:move_tenant', {'incident_id': inc.id, 'from_tenant_id': source_tenant_id, 'to_tenant_id': target_tenant.id, 'target_tenant_name': target_tenant.name}, actor_type='user')
        db.session.commit()
        if moved:
            flash(f'Incidente spostato nel tenant {target_tenant.name}.', 'success')
        else:
            flash(f'L’incidente era già nel tenant {target_tenant.name}.', 'info')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Spostamento incidente tra tenant fallito')
        flash(f'Spostamento incidente tra tenant fallito: {exc}', 'danger')
    next_url = (request.form.get('next') or url_for('main.index')).strip()
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('main.index')
    return redirect(next_url)


def _incident_ids_from_form():
    ids=[]
    for raw in request.form.getlist('incident_ids'):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value not in ids:
            ids.append(value)
    return ids


def _safe_next_url(default_endpoint='main.index'):
    next_url = (request.form.get('next') or request.referrer or url_for(default_endpoint)).strip()
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for(default_endpoint)
    return next_url


@bp.route('/incidents/bulk/move-tenant', methods=['POST'])
@login_required
def incidents_bulk_move_tenant():
    if not is_superuser():
        flash('Solo gli utenti superuser e l’utente admin possono spostare incidenti tra tenant.', 'danger')
        return redirect(url_for('main.index'))
    ids = _incident_ids_from_form()
    if not ids:
        flash('Selezionare almeno un incidente da spostare.', 'warning')
        return redirect(_safe_next_url())
    target_tenant = tenant_or_404(request.form.get('target_tenant_id', type=int))
    incidents = visible(Incident.query).filter(Incident.id.in_(ids)).order_by(Incident.id).all()
    if not incidents:
        flash('Nessun incidente selezionato risulta visibile nel tenant attivo.', 'warning')
        return redirect(_safe_next_url())
    moved_count = 0
    source_ids = {}
    try:
        for inc in incidents:
            source_ids[inc.id] = inc.tenant_id
            if move_incident_to_tenant(inc, target_tenant.id):
                moved_count += 1
        db.session.flush()
        session['active_tenant_id'] = target_tenant.id
        session['active_tenant_scope_enabled'] = True
        session.modified = True
        audit_log('incident:bulk_move_tenant', {
            'incident_ids': [inc.id for inc in incidents],
            'from_tenant_ids': source_ids,
            'to_tenant_id': target_tenant.id,
            'target_tenant_name': target_tenant.name,
            'moved_count': moved_count,
        }, actor_type='user')
        db.session.commit()
        flash(f'{moved_count} incidenti spostati nel tenant {target_tenant.name}.', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Spostamento massivo incidenti tra tenant fallito')
        flash(f'Spostamento massivo incidenti fallito: {exc}', 'danger')
    return redirect(_safe_next_url())


@bp.route('/incidents/bulk/delete', methods=['POST'])
@login_required
def incidents_bulk_delete():
    if not can_write():
        flash('Permessi insufficienti per cancellare incidenti.', 'danger')
        return redirect(url_for('main.index'))
    ids = _incident_ids_from_form()
    if not ids:
        flash('Selezionare almeno un incidente da cancellare.', 'warning')
        return redirect(_safe_next_url())
    incidents = visible(Incident.query).filter(Incident.id.in_(ids)).all()
    if not incidents:
        flash('Nessun incidente selezionato risulta visibile nel tenant attivo.', 'warning')
        return redirect(_safe_next_url())
    deleted_ids = [inc.id for inc in incidents]
    try:
        for inc in incidents:
            delete_incident_with_related_state(inc)
        audit_log('incident:bulk_delete', {'incident_ids': deleted_ids, 'deleted_count': len(deleted_ids), 'tenant_id': current_tenant_id()}, actor_type='user')
        db.session.commit()
        flash(f'{len(deleted_ids)} incidenti cancellati.', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Cancellazione massiva incidenti fallita')
        flash(f'Cancellazione massiva incidenti fallita: {exc}', 'danger')
    return redirect(_safe_next_url())


@bp.route('/incident/<int:iid>/reminder/add',methods=['POST'])
@login_required
def add_incident_reminder(iid):
    inc=visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if not can_write():
        section_flash('Permessi insufficienti','incident-reminders','error')
        return incident_detail_redirect(iid, 'incident-reminders')
    try:
        scheduled_at = datetime.fromisoformat((request.form.get('scheduled_at') or '').strip())
    except Exception:
        section_flash('Data e ora del promemoria non valide','incident-reminders','error')
        return incident_detail_redirect(iid, 'incident-reminders')
    message = (request.form.get('message') or '').strip()
    if not message:
        section_flash('Il messaggio del promemoria è obbligatorio','incident-reminders','error')
        return incident_detail_redirect(iid, 'incident-reminders')
    rem=IncidentReminder(incident_id=inc.id, scheduled_at=scheduled_at, message=message, cc_emails=request.form.get('cc_emails') or '', created_by_id=current_user.id, created_by_name=current_user.name or current_user.username)
    db.session.add(rem)
    db.session.flush()
    audit_log('incident_reminder:create', json.dumps({'reminder_id': rem.id, 'incident_id': inc.id, 'scheduled_at': scheduled_at.isoformat(timespec='seconds')}, ensure_ascii=False))
    add_automatic_button_action(inc, 'reminder_add')
    db.session.commit()
    section_flash('Promemoria aggiunto','incident-reminders','success')
    return incident_detail_redirect(iid, 'incident-reminders')

@bp.route('/incident/reminder/<int:rid>/update',methods=['POST'])
@login_required
def update_incident_reminder(rid):
    rem=model_or_404(IncidentReminder, rid)
    inc=visible(Incident.query).filter(Incident.id == rem.incident_id).first_or_404()
    if not can_write():
        section_flash('Permessi insufficienti','incident-reminders','error')
        return incident_detail_redirect(inc.id, 'incident-reminders')
    try:
        scheduled_at = datetime.fromisoformat((request.form.get('scheduled_at') or '').strip())
    except Exception:
        section_flash('Data e ora del promemoria non valide','incident-reminders','error')
        return incident_detail_redirect(inc.id, 'incident-reminders')
    message = (request.form.get('message') or '').strip()
    if not message:
        section_flash('Il messaggio del promemoria è obbligatorio','incident-reminders','error')
        return incident_detail_redirect(inc.id, 'incident-reminders')
    rem.scheduled_at=scheduled_at; rem.message=message; rem.cc_emails=request.form.get('cc_emails') or ''; rem.updated_at=utcnow()
    if request.form.get('reset_sent'):
        rem.sent_at=None; rem.last_error=''
    audit_log('incident_reminder:update', json.dumps({'reminder_id': rem.id, 'incident_id': inc.id, 'scheduled_at': scheduled_at.isoformat(timespec='seconds'), 'reset_sent': bool(request.form.get('reset_sent'))}, ensure_ascii=False))
    add_automatic_button_action(inc, 'reminder_update')
    db.session.commit()
    section_flash('Promemoria aggiornato','incident-reminders','success')
    return incident_detail_redirect(inc.id, 'incident-reminders')

@bp.route('/incident/reminder/<int:rid>/delete',methods=['POST'])
@login_required
def delete_incident_reminder(rid):
    rem=model_or_404(IncidentReminder, rid)
    iid=rem.incident_id
    visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if not can_write():
        section_flash('Permessi insufficienti','incident-reminders','error')
        return incident_detail_redirect(iid, 'incident-reminders')
    audit_log('incident_reminder:delete', json.dumps({'reminder_id': rem.id, 'incident_id': iid, 'scheduled_at': rem.scheduled_at.isoformat(timespec='seconds') if rem.scheduled_at else None}, ensure_ascii=False))
    db.session.delete(rem)
    db.session.commit()
    section_flash('Promemoria cancellato','incident-reminders','success')
    return incident_detail_redirect(iid, 'incident-reminders')

def delete_incident_with_related_state(incident):
    """Elimina un incidente includendo gli stati procedurali collegati non coperti dalle cascade storiche.

    Alcuni database esistenti possono avere il vincolo FK di
    deadline_notification_state.incident_id senza ON DELETE CASCADE, perché la
    tabella è stata creata da versioni precedenti. La cancellazione esplicita
    evita l'errore PostgreSQL `deadline_notification_state_incident_id_fkey`
    anche dopo Full import/restore o aggiornamenti incrementali.
    """
    if incident is None:
        return
    DeadlineNotificationState.query.filter_by(incident_id=incident.id).delete(synchronize_session=False)
    db.session.delete(incident)

@bp.route('/incident/<int:iid>/delete',methods=['POST'])
@login_required
def incident_delete(iid):
    if can_write():
        inc = model_or_404(Incident, iid)
        delete_incident_with_related_state(inc)
        db.session.commit()
        flash('Incidente cancellato.', 'success')
    return redirect(url_for('main.index'))
@bp.route('/incident/<int:iid>/clone')
@login_required
def clone(iid):
    if not can_write(): return redirect(url_for('main.index'))
    src=model_or_404(Incident, iid); inc=Incident(tenant_id=current_tenant_id(),creator_id=current_user.id,creator_name=current_user.name,creator_email=current_user.email,name='Copia di '+src.name,reference=(src.reference or f'Incidente #{src.id}'),recipient=src.recipient,recipient_email=getattr(src, 'recipient_email', None),description=src.description,severity_id=src.severity_id,personal_data=src.personal_data,data_subjects_count=src.data_subjects_count,data_volume=src.data_volume,start_at=utcnow(),status='aperto',custom_fields_json=getattr(src, 'custom_fields_json', '') or '')
    sync_incident_split_datetime(inc); inc.categories=list(src.categories); inc.category_order=getattr(src, 'category_order', '') or _csv_ids_from_objects(src.categories); inc.data_types=list(src.data_types); inc.people=list(src.people); inc.recommendations=list(src.recommendations); db.session.add(inc); db.session.commit(); return redirect(url_for('main.incident_detail',iid=inc.id))

def workflow_notification_blocking_message(inc, label_id):
    if not label_id:
        return ''
    try:
        selected_label_id = int(label_id)
    except Exception:
        return ''
    for step in workflow_steps_for_incident(inc):
        if int(step.action_label_id or 0) != selected_label_id:
            continue
        if not getattr(step, 'requires_notification', False):
            continue
        kind = (getattr(step, 'required_notification_type', None) or '').strip()
        if kind and not incident_has_notification_action(inc, kind):
            ntype = get_notification_type(kind)
            label = ntype.label if ntype else kind
            return f'Impossibile inserire questa azione: lo step richiede prima l’invio della notifica "{label}". Cliccare lo step nelle Operazioni previste per aprire il percorso guidato.'
    return ''

def workflow_global_check_blocking_message(inc, label_id):
    """Blocca un task con operazione automatica controllo globale.

    Il controllo è attivo solo se la label selezionata contiene il tag
    ``global_check``. In quel caso viene individuato il prossimo step del
    workflow applicabile associato alla stessa label e si verifica che tutti
    gli step procedurali precedenti risultino completati. Questo impedisce di
    saltare fasi obbligate del workflow dopo Full import/restore o con flussi
    personalizzati, lasciando comunque modificabile la definizione del flusso.
    """
    if not inc or not label_id:
        return ''
    try:
        selected_label_id = int(label_id)
    except Exception:
        return ''
    label = db.session.get(ConfigLabel, selected_label_id)
    if not action_has_automatic_operation(label, 'global_check'):
        return ''
    workflow = incident_workflow_status(inc)
    steps = workflow.get('steps', [])
    target_index = None
    for idx, step in enumerate(steps):
        if int(step.get('action_label_id') or 0) == selected_label_id and not step.get('done'):
            target_index = idx
            break
    if target_index is None:
        for idx, step in enumerate(steps):
            if int(step.get('action_label_id') or 0) == selected_label_id:
                target_index = idx
                break
    if target_index is None:
        return ''
    missing_previous = [
        step for step in steps[:target_index]
        if not step.get('done')
    ]
    if not missing_previous:
        return ''
    missing_text = ', '.join(
        (step.get('description') or step.get('label') or step.get('task_name') or 'step precedente')
        for step in missing_previous[:5]
    )
    if len(missing_previous) > 5:
        missing_text += ', ...'
    return 'Impossibile inserire questa azione: la label richiede il controllo globale e gli step procedurali precedenti non sono ancora stati completati: ' + missing_text + '.'

def create_manual_action_safely(iid):
    """Crea una nuova azione manuale senza assegnare ID espliciti.

    Alcuni database aggiornati/importati possono avere la sequence PostgreSQL
    della tabella action rimasta indietro rispetto al valore massimo già
    presente. In quel caso l'INSERT fallisce con duplicate key. Qui
    riallineiamo prima dell'INSERT e ritentiamo una volta se necessario.
    """
    align_table_sequence('action')
    label_id = request.form.get('label_id') or None
    label = db.session.get(ConfigLabel, label_id) if label_id else None
    inc = db.session.get(Incident, iid)
    blocking = workflow_notification_blocking_message(inc, label_id) if inc else ''
    if not blocking and inc:
        blocking = workflow_global_check_blocking_message(inc, label_id)
    if blocking:
        raise ValueError(blocking)
    description = (request.form.get('description') or '').strip() or None
    if label and getattr(label, 'description_required', False) and not description:
        raise ValueError('La Descrizione operazioni compiute è obbligatoria per il task selezionato.')
    payload = dict(
        incident_id=iid,
        when_at=datetime.fromisoformat(request.form['when_at']),
        person_name=request.form.get('person_name') or current_user.name,
        description=description,
        consequence_text=request.form.get('consequence_text') or None,
        label_id=label_id,
        exportable=action_exportable_default(label, description),
    )
    action = Action(**payload)
    db.session.add(action)
    try:
        db.session.flush()
        close_incident_from_conclusion_action(iid, action)
        return action
    except IntegrityError as exc:
        db.session.rollback()
        if 'duplicate key value violates unique constraint' not in str(exc):
            raise
        align_table_sequence('action')
        action = Action(**payload)
        db.session.add(action)
        db.session.flush()
        close_incident_from_conclusion_action(iid, action)
        return action

@bp.route('/incident/<int:iid>/action',methods=['POST'])
@login_required
def add_action(iid):
    if can_write():
        try:
            action = create_manual_action_safely(iid)
            if getattr(db.session.get(Incident, iid), '_closure_blocked_by_procedural_warnings', False):
                section_flash('Incidente non chiuso: sono ancora presenti avvisi procedurali attivi.', 'incident-actions', 'warning')
            for f in request.files.getlist('action_files'):
                save_action_attachment_file(f, action)
            add_automatic_button_action(db.session.get(Incident, iid), 'action_add')
            db.session.commit()
            section_flash('Azione aggiunta correttamente', 'incident-actions', 'success')
        except IntegrityError:
            db.session.rollback()
            current_app.logger.exception('Errore duplicate key durante inserimento azione manuale')
            section_flash('Errore durante l’inserimento dell’azione: chiave duplicata. Le sequenze del database sono state riallineate, riprovare.', 'incident-actions', 'danger')
        except ValueError as exc:
            db.session.rollback()
            section_flash(str(exc), 'incident-actions', 'warning')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Errore durante inserimento azione manuale')
            section_flash('Errore durante l’inserimento dell’azione.', 'incident-actions', 'danger')
    return incident_detail_redirect(iid, 'incident-actions')
@bp.route('/action/<int:aid>/update',methods=['POST'])
@login_required
def update_action(aid):
    a=model_or_404(Action, aid); iid=a.incident_id
    if can_write():
        when_value = (request.form.get('when_at') or '').strip()
        if when_value:
            try:
                a.when_at = datetime.fromisoformat(when_value)
            except ValueError:
                section_flash('Data e ora azione non valida.', 'incident-actions', 'error')
                return incident_detail_redirect(iid, 'incident-actions')
        a.person_name=request.form.get('person_name') or a.person_name
        label_id=request.form.get('label_id') or None
        label = db.session.get(ConfigLabel, label_id) if label_id else None
        description = (request.form.get('description') or '').strip() or None
        if label and getattr(label, 'description_required', False) and not description:
            section_flash('La Descrizione operazioni compiute è obbligatoria per il task selezionato.', 'incident-actions', 'warning')
            return incident_detail_redirect(iid, 'incident-actions')
        a.description=description
        a.consequence_text=request.form.get('consequence_text') or None
        a.label_id=label_id
        a.exportable=bool(request.form.get('exportable'))
        close_incident_from_conclusion_action(iid, a)
        inc_for_button = db.session.get(Incident, iid)
        add_automatic_button_action(inc_for_button, 'action_update')
        if getattr(db.session.get(Incident, iid), '_closure_blocked_by_procedural_warnings', False):
            section_flash('Incidente non chiuso: sono ancora presenti avvisi procedurali attivi.', 'incident-actions', 'warning')
        try:
            db.session.commit(); section_flash('Azione aggiornata', 'incident-actions', 'success')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore aggiornamento azione'); section_flash(f'Errore aggiornamento azione: {exc}', 'incident-actions', 'error')
    return incident_detail_redirect(iid, 'incident-actions')

@bp.route('/action/<int:aid>/delete',methods=['POST'])
@login_required
def del_action(aid):
    a=model_or_404(Action, aid); iid=a.incident_id
    if can_write(): db.session.delete(a); db.session.commit()
    return incident_detail_redirect(iid, 'incident-actions')
@bp.route('/action/<int:aid>/exportable',methods=['POST'])
@login_required
def update_action_exportable(aid):
    a=model_or_404(Action, aid); iid=a.incident_id
    visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if can_write():
        a.exportable = bool(request.form.get('exportable'))
        db.session.commit()
        section_flash('Flag exportable aggiornato', 'incident-actions', 'success')
    return incident_detail_redirect(iid, 'incident-actions')

@bp.route('/action-attachment/<int:att_id>/download')
@login_required
def download_action_attachment(att_id):
    att=model_or_404(ActionAttachment, att_id)
    action=model_or_404(Action, att.action_id)
    visible(Incident.query).filter(Incident.id == action.incident_id).first_or_404()
    return send_file(os.path.join(current_app.config['UPLOAD_DIR'],att.stored_name),download_name=att.filename,as_attachment=True)

@bp.route('/action-attachment/<int:att_id>/delete',methods=['POST'])
@login_required
def del_action_attachment(att_id):
    att=model_or_404(ActionAttachment, att_id)
    action=model_or_404(Action, att.action_id)
    iid=action.incident_id
    if can_write():
        try: os.remove(os.path.join(current_app.config['UPLOAD_DIR'],att.stored_name))
        except OSError: pass
        db.session.delete(att); db.session.commit()
    return incident_detail_redirect(iid, 'incident-actions')

@bp.route('/incident/<int:iid>/upload',methods=['POST'])
@login_required
def upload(iid):
    if can_write():
        try:
            saved = 0
            alfresco_saved = 0
            alfresco_errors = []
            upload_to_alfresco = request.form.get('upload_to_alfresco') == '1' and alfresco_is_enabled_safe()
            saved_docs = []
            for f in request.files.getlist('files'):
                if f.filename:
                    name, stored = save_validated_upload(f, current_app.config['UPLOAD_DIR'])
                    doc = Document(incident_id=iid,filename=name,stored_name=stored)
                    db.session.add(doc)
                    db.session.flush()
                    saved_docs.append(doc)
                    saved += 1
                    if upload_to_alfresco:
                        try:
                            attach_document_to_alfresco(doc)
                            alfresco_saved += 1
                        except Exception as exc:
                            current_app.logger.exception('Upload Alfresco fallito per %s', name)
                            alfresco_errors.append(f'{name}: {exc}')
            add_automatic_button_action(db.session.get(Incident, iid), 'document_upload', description=f'Azione automatica da pulsante: Upload documenti ({saved} file).', context_documents=saved_docs)
            db.session.commit()
            if upload_to_alfresco:
                section_flash(f'Documenti caricati: {saved}; inviati ad Alfresco: {alfresco_saved}', 'incident-documents', 'success')
                if alfresco_errors:
                    section_flash('Errori Alfresco: ' + '; '.join(alfresco_errors[:3]), 'incident-documents', 'warning')
            else:
                section_flash(f'Documenti caricati: {saved}', 'incident-documents', 'success')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore upload documenti'); section_flash(f'Errore upload documenti: {exc}', 'incident-documents', 'error')
    return incident_detail_redirect(iid, 'incident-documents')
@bp.route('/document/<int:did>/download')
@login_required
def download_doc(did):
    d = model_or_404(Document, did)
    inc = visible(Incident.query).filter(Incident.id == d.incident_id).first_or_404()
    try:
        action = add_automatic_button_action(
            inc,
            'document_download',
            description=f'Azione automatica da pulsante: Scarica documento {d.filename}.',
            context_template=d.generated_template_name,
        )
        if action:
            db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Errore registrazione azione automatica download documento %s', d.id)
    return send_file(os.path.join(current_app.config['UPLOAD_DIR'], d.stored_name), download_name=d.filename, as_attachment=True)

@bp.route('/document/<int:did>/alfresco/upload', methods=['POST'])
@login_required
def upload_doc_to_alfresco(did):
    d=model_or_404(Document, did); visible(Incident.query).filter(Incident.id == d.incident_id).first_or_404()
    if can_write():
        if not alfresco_is_enabled_safe():
            section_flash('Plugin Alfresco non abilitato.', 'incident-documents', 'warning')
        else:
            try:
                attach_document_to_alfresco(d)
                db.session.commit()
                section_flash(f'Documento {d.filename} caricato su Alfresco.', 'incident-documents', 'success')
            except Exception as exc:
                db.session.rollback(); current_app.logger.exception('Upload documento Alfresco fallito'); section_flash(f'Errore upload Alfresco: {exc}', 'incident-documents', 'error')
    return incident_detail_redirect(d.incident_id, 'incident-documents')

@bp.route('/document/<int:did>/alfresco/download')
@login_required
def download_doc_from_alfresco(did):
    d=model_or_404(Document, did); visible(Incident.query).filter(Incident.id == d.incident_id).first_or_404()
    if not alfresco_is_enabled_safe():
        section_flash('Plugin Alfresco non abilitato.', 'incident-documents', 'warning')
        return incident_detail_redirect(d.incident_id, 'incident-documents')
    try:
        from .plugins.alfresco.client import download_file
        content, mimetype = download_file(d.alfresco_node_id)
        return Response(content, mimetype=mimetype, headers={'Content-Disposition': f'attachment; filename="{d.filename or "alfresco-document"}"'})
    except Exception as exc:
        current_app.logger.exception('Download documento Alfresco fallito')
        section_flash(f'Errore download Alfresco: {exc}', 'incident-documents', 'error')
        return incident_detail_redirect(d.incident_id, 'incident-documents')
@bp.route('/document/<int:did>/delete',methods=['POST'])
@login_required
def del_doc(did):
    d=model_or_404(Document, did); iid=d.incident_id
    if can_write():
        try:
            try: os.remove(os.path.join(current_app.config['UPLOAD_DIR'],d.stored_name))
            except OSError: pass
            db.session.delete(d); db.session.commit(); section_flash('Documento eliminato', 'incident-documents', 'info')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore cancellazione documento'); section_flash(f'Errore cancellazione documento: {exc}', 'incident-documents', 'error')
    return incident_detail_redirect(iid, 'incident-documents')

@bp.route('/document/<int:did>/notification-tags', methods=['POST'])
@login_required
def update_document_notification_tags(did):
    d = model_or_404(Document, did)
    visible(Incident.query).filter(Incident.id == d.incident_id).first_or_404()
    if not can_write():
        section_flash('Permessi insufficienti', 'incident-documents', 'error')
        return incident_detail_redirect(d.incident_id, 'incident-documents')
    valid = {t.code for t in notification_type_records(enabled_only=False)}
    requested = request.form.getlist('notification_tags')
    tags = [code for code in requested if code in valid]
    d.set_notification_tags(tags)
    inc = db.session.get(Incident, d.incident_id)
    add_automatic_button_action(
        inc,
        'document_tags_save',
        description=f"Azione automatica da pulsante: Salva tag documento {d.filename}.",
        context_tags=tags,
    )
    db.session.commit()
    section_flash(f'Tag notifiche aggiornati per {d.filename}', 'incident-documents', 'success')
    return incident_detail_redirect(d.incident_id, 'incident-documents')



def _workflow_scope_label(category_id):
    if category_id:
        lab = db.session.get(ConfigLabel, category_id)
        return lab.value if lab else str(category_id)
    return 'default'


def _workflow_label_payload(label):
    if not label:
        return None
    return {
        'kind': label.kind,
        'group': label.group or 'default',
        'value': label.value,
        'description': label.description or '',
        'max_completion_hours': label.max_completion_hours or 0,
        'default_exportable': bool(label.default_exportable),
        'automatic_operations': label.automatic_operations or '',
    }


def _workflow_notification_type_payload(nt):
    if not nt:
        return None
    return {
        'code': nt.code,
        'label': nt.label,
        'description': nt.description or '',
        'enabled': bool(nt.enabled),
    }


def _workflow_template_payload(tpl):
    if not tpl:
        return None
    return {
        'kind': tpl.kind,
        'name': tpl.name,
        'subject': tpl.subject or '',
        'body': tpl.body or '',
        'linked_form_template_name': tpl.linked_form_template_name or '',
        'action_label': _workflow_label_payload(tpl.action_label),
        'recipient_source': tpl.recipient_source or 'type_default',
        'recipient_value': tpl.recipient_value or '',
        'recipient_editable': bool(tpl.recipient_editable),
        'recipient_external_allowed': bool(tpl.recipient_external_allowed),
        'cc_source': tpl.cc_source or 'type_default',
        'cc_value': tpl.cc_value or '',
        'cc_editable': bool(tpl.cc_editable),
        'cc_external_allowed': bool(tpl.cc_external_allowed),
        'is_default': bool(tpl.is_default),
    }


def _workflow_form_template_payload(template_name):
    if not template_name:
        return None
    cfg = FormTemplateConfig.query.filter_by(template_name=template_name).first()
    binary = FormTemplateBinary.query.filter_by(template_name=template_name).first()
    payload = {'template_name': template_name}
    if cfg:
        payload.update({
            'font_family': cfg.font_family,
            'font_size': cfg.font_size,
            'notification_tags': cfg.notification_tag_list,
        })
    if binary and binary.pdf_data:
        payload['binary'] = {
            'filename': binary.filename,
            'pdf_base64': base64.b64encode(binary.pdf_data).decode('ascii'),
        }
    return payload


def build_workflow_export_payload(category_id=None):
    category_id = int(category_id) if category_id else None
    steps = workflow_step_scope_query(category_id).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    label_map = {}
    notification_type_map = {}
    template_map = {}
    form_template_map = {}

    def add_label(label):
        data = _workflow_label_payload(label)
        if data:
            label_map[f"{data['kind']}::{data['value']}"] = data

    category_label = db.session.get(ConfigLabel, category_id) if category_id else None
    add_label(category_label)
    exported_steps = []
    for step in steps:
        step_type = normalize_workflow_step_type(getattr(step, 'step_type', REGISTRATION_STEP_TYPE))
        add_label(step.action_label)
        for token in step.condition_tokens():
            base_token = token[1:] if str(token).startswith('!') else token
            if ':' in base_token:
                kind, sid = base_token.split(':', 1)
                if kind in {'severity', 'data_type'}:
                    lab = db.session.get(ConfigLabel, int(sid)) if sid.isdigit() else None
                    add_label(lab)
        nt = tenant_query(NotificationType).filter_by(code=step.required_notification_type).first() if step.required_notification_type else None
        if nt:
            notification_type_map[nt.code] = _workflow_notification_type_payload(nt)
            templates = tenant_query(NotificationTemplate).filter_by(kind=nt.code).order_by(NotificationTemplate.name).all()
            for tpl in templates:
                template_map[f"{tpl.kind}::{tpl.name}"] = _workflow_template_payload(tpl)
                if tpl.action_label:
                    add_label(tpl.action_label)
                if tpl.linked_form_template_name:
                    ft = _workflow_form_template_payload(tpl.linked_form_template_name)
                    if ft:
                        form_template_map[tpl.linked_form_template_name] = ft
        exported_steps.append({
            'position': step.position,
            'action_label': _workflow_label_payload(step.action_label),
            'description': step.description or '',
            'step_type': step_type,
            'conditions': step.condition_tokens(),
            'required': bool(step.required),
            'requires_notification': bool(step.requires_notification),
            'required_notification_type': step.required_notification_type or '',
            'document_generation_enabled': bool(getattr(step, 'document_generation_enabled', False)),
            'document_template_name': getattr(step, 'document_template_name', None) or '',
            'section_target': getattr(step, 'section_target', '') or '',
        })
    return {
        'format': 'cybersecurity-incident-registry.workflow.v1',
        'exported_at': utcnow().isoformat() + 'Z',
        'application': {'name': APP_NAME if 'APP_NAME' in globals() else 'Cybersecurity Incident Registry', 'version': APP_VERSION if 'APP_VERSION' in globals() else ''},
        'workflow': {
            'scope': 'category' if category_label else 'default',
            'category': _workflow_label_payload(category_label),
            'steps': exported_steps,
        },
        'dependencies': {
            'labels': list(label_map.values()),
            'notification_types': list(notification_type_map.values()),
            'notification_templates': list(template_map.values()),
            'form_templates': list(form_template_map.values()),
        },
    }


def _payload_label_name(data):
    return f"{data.get('kind','')}::{data.get('value','')}"


def workflow_import_diff(payload):
    diffs = []
    labels_data = (payload.get('dependencies') or {}).get('labels') or []
    for lab in labels_data:
        cur = ConfigLabel.query.filter_by(kind=lab.get('kind'), value=lab.get('value')).first()
        if cur:
            changes = {}
            for field in ['group','description','max_completion_hours','default_exportable','automatic_operations']:
                old = getattr(cur, field)
                new = lab.get(field)
                if field == 'default_exportable': old = bool(old); new = bool(new)
                if field == 'max_completion_hours': old = old or 0; new = new or 0
                if old != new:
                    changes[field] = {'old': old, 'new': new}
            if changes:
                diffs.append({'key': f"label::{lab.get('kind')}::{lab.get('value')}", 'type': 'label', 'title': f"Label {lab.get('kind')} / {lab.get('value')}", 'changes': changes})
    for nt in (payload.get('dependencies') or {}).get('notification_types') or []:
        cur = tenant_query(NotificationType).filter_by(code=nt.get('code')).first()
        if cur:
            changes={}
            for field in ['label','description','enabled']:
                old=getattr(cur, field); new=nt.get(field)
                if field=='enabled': old=bool(old); new=bool(new)
                if old != new: changes[field]={'old':old,'new':new}
            if changes:
                diffs.append({'key': f"notification_type::{nt.get('code')}", 'type':'notification_type', 'title': f"Tipo notifica {nt.get('code')}", 'changes': changes})
    for ft in (payload.get('dependencies') or {}).get('form_templates') or []:
        cur = FormTemplateConfig.query.filter_by(template_name=ft.get('template_name')).first()
        if cur:
            changes = {}
            incoming_tags = ','.join(ft.get('notification_tags') or [])
            comparable = {'font_family': cur.font_family, 'font_size': cur.font_size, 'notification_tags': ','.join(cur.notification_tag_list)}
            incoming = {'font_family': FormTemplateConfig.normalize_font_family(ft.get('font_family')), 'font_size': FormTemplateConfig.normalize_font_size(ft.get('font_size')), 'notification_tags': incoming_tags}
            for field, new_value in incoming.items():
                if comparable[field] != new_value:
                    changes[field] = {'old': comparable[field], 'new': new_value}
            existing_binary = FormTemplateBinary.query.filter_by(template_name=ft.get('template_name')).first()
            incoming_binary = ft.get('binary') or {}
            incoming_pdf_b64 = incoming_binary.get('pdf_base64')
            if incoming_pdf_b64:
                try:
                    incoming_pdf = base64.b64decode(incoming_pdf_b64)
                except Exception:
                    incoming_pdf = None
                incoming_filename = incoming_binary.get('filename') or ft.get('template_name')
                if not existing_binary:
                    changes.setdefault('binary_pdf', {'old': '', 'new': incoming_filename})
                elif existing_binary.filename != incoming_filename or existing_binary.pdf_data != incoming_pdf:
                    changes.setdefault('binary_pdf', {'old': existing_binary.filename, 'new': incoming_filename})
            if changes:
                diffs.append({'key': f"form_template::{ft.get('template_name')}", 'type': 'form_template', 'title': f"Template modulo {ft.get('template_name')}", 'changes': changes})
    for tpl in (payload.get('dependencies') or {}).get('notification_templates') or []:
        cur = tenant_query(NotificationTemplate).filter_by(kind=tpl.get('kind'), name=tpl.get('name')).first()
        if cur:
            changes={}
            for field in ['subject','body','linked_form_template_name','recipient_source','recipient_value','recipient_editable','recipient_external_allowed','cc_source','cc_value','cc_editable','cc_external_allowed','is_default']:
                old=getattr(cur, field); new=tpl.get(field)
                if field.endswith('_editable') or field.endswith('_allowed') or field=='is_default': old=bool(old); new=bool(new)
                if (old or '') != (new or ''):
                    changes[field]={'old': old, 'new': new}
            if changes:
                diffs.append({'key': f"notification_template::{tpl.get('kind')}::{tpl.get('name')}", 'type':'notification_template', 'title': f"Template notifica {tpl.get('kind')} / {tpl.get('name')}", 'changes': changes})
    wf = payload.get('workflow') or {}
    cat = wf.get('category') or None
    category_id = None
    if cat:
        existing_cat = tenant_query(ConfigLabel).filter_by(kind=cat.get('kind'), value=cat.get('value')).first()
        category_id = existing_cat.id if existing_cat else None
    existing_steps = workflow_step_scope_query(category_id).all() if (wf.get('scope') == 'default' or category_id) else []
    existing_map = {}
    for st in existing_steps:
        key = f"{st.position}::{st.action_label.value if st.action_label else st.action_label_id}"
        existing_map[key] = st
    for st in wf.get('steps') or []:
        al = st.get('action_label') or {}
        key = f"{st.get('position',0)}::{al.get('value','')}"
        cur = existing_map.get(key)
        if cur:
            changes={}
            comparable = {
                'description': cur.description or '',
                'step_type': normalize_workflow_step_type(getattr(cur, 'step_type', REGISTRATION_STEP_TYPE)),
                'conditions': ','.join(cur.condition_tokens()),
                'required': bool(cur.required),
                'requires_notification': bool(cur.requires_notification),
                'required_notification_type': cur.required_notification_type or '',
                'document_generation_enabled': bool(getattr(cur, 'document_generation_enabled', False)),
                'document_template_name': getattr(cur, 'document_template_name', None) or '',
                'section_target': getattr(cur, 'section_target', '') or '',
            }
            incoming = {
                'description': st.get('description') or '',
                'step_type': normalize_workflow_step_type(st.get('step_type')),
                'conditions': ','.join(st.get('conditions') or []),
                'required': bool(st.get('required')),
                'requires_notification': bool(st.get('requires_notification')),
                'required_notification_type': st.get('required_notification_type') or '',
                'document_generation_enabled': bool(st.get('document_generation_enabled')),
                'document_template_name': st.get('document_template_name') or '',
                'section_target': st.get('section_target') or '',
            }
            for k,v in incoming.items():
                if comparable[k] != v:
                    changes[k]={'old': comparable[k], 'new': v}
            if changes:
                diffs.append({'key': f"workflow_step::{key}", 'type':'workflow_step', 'title': f"Step {st.get('position')} / {al.get('value','')}", 'changes': changes})
    return diffs


def _upsert_config_label(data, allow_overwrite):
    lab = ConfigLabel.query.filter_by(kind=data.get('kind'), value=data.get('value')).first()
    if not lab:
        lab = ConfigLabel(kind=data.get('kind'), value=data.get('value'))
        db.session.add(lab)
    elif not allow_overwrite:
        return lab
    lab.group = data.get('group') or 'default'
    lab.description = data.get('description') or ''
    lab.max_completion_hours = int(data.get('max_completion_hours') or 0)
    lab.default_exportable = bool(data.get('default_exportable'))
    lab.automatic_operations = data.get('automatic_operations') or ''
    return lab


def apply_workflow_import(payload, overwrite_keys):
    """Importa un workflow evitando duplicati identici.

    Gli elementi gia' presenti e identici al payload vengono lasciati invariati:
    non sono aggiornati, non richiedono conferma di sovrascrittura e sono
    conteggiati come ``unchanged``. Solo gli elementi esistenti con valori
    diversi possono essere aggiornati, e soltanto quando la relativa chiave e'
    stata selezionata esplicitamente nella preview.
    """
    overwrite_keys = set(overwrite_keys or [])
    changed_keys = {diff.get('key') for diff in workflow_import_diff(payload)}
    created = updated = skipped = unchanged = 0
    label_cache = {}

    for lab_data in (payload.get('dependencies') or {}).get('labels') or []:
        key = f"label::{lab_data.get('kind')}::{lab_data.get('value')}"
        exists = ConfigLabel.query.filter_by(kind=lab_data.get('kind'), value=lab_data.get('value')).first()
        if exists and key not in changed_keys:
            label_cache[(exists.kind, exists.value)] = exists
            unchanged += 1
            continue
        if exists and key not in overwrite_keys:
            label_cache[(exists.kind, exists.value)] = exists
            skipped += 1
            continue
        lab = _upsert_config_label(lab_data, True)
        label_cache[(lab.kind, lab.value)] = lab
        if exists:
            updated += 1
        else:
            created += 1
    db.session.flush()

    for nt in (payload.get('dependencies') or {}).get('notification_types') or []:
        key = f"notification_type::{nt.get('code')}"
        obj = tenant_query(NotificationType).filter_by(code=nt.get('code')).first()
        exists = bool(obj)
        if exists and key not in changed_keys:
            unchanged += 1
            continue
        if exists and key not in overwrite_keys:
            skipped += 1
            continue
        if not obj:
            obj = NotificationType(code=nt.get('code'))
            db.session.add(obj)
        obj.label = nt.get('label') or nt.get('code')
        obj.description = nt.get('description') or default_notification_type_description(obj.label, obj.code)
        obj.enabled = bool(nt.get('enabled'))
        created += 0 if exists else 1
        updated += 1 if exists else 0
    db.session.flush()

    for ft in (payload.get('dependencies') or {}).get('form_templates') or []:
        name = ft.get('template_name')
        if not name:
            continue
        key = f"form_template::{name}"
        cfg = FormTemplateConfig.query.filter_by(template_name=name).first()
        exists = bool(cfg)
        if exists and key not in changed_keys:
            unchanged += 1
            continue
        if exists and key not in overwrite_keys:
            skipped += 1
            continue
        if not cfg:
            cfg = FormTemplateConfig(template_name=name)
            db.session.add(cfg)
        cfg.font_family = FormTemplateConfig.normalize_font_family(ft.get('font_family'))
        cfg.font_size = FormTemplateConfig.normalize_font_size(ft.get('font_size'))
        cfg.set_notification_tags(ft.get('notification_tags') or [])
        bin_data = ft.get('binary') or {}
        if bin_data.get('pdf_base64'):
            binary = FormTemplateBinary.query.filter_by(template_name=name).first()
            if not binary:
                binary = FormTemplateBinary(template_name=name, filename=bin_data.get('filename') or name)
                db.session.add(binary)
            binary.filename = bin_data.get('filename') or binary.filename
            binary.pdf_data = base64.b64decode(bin_data.get('pdf_base64'))
        created += 0 if exists else 1
        updated += 1 if exists else 0
    db.session.flush()

    for tpl in (payload.get('dependencies') or {}).get('notification_templates') or []:
        key = f"notification_template::{tpl.get('kind')}::{tpl.get('name')}"
        obj = tenant_query(NotificationTemplate).filter_by(kind=tpl.get('kind'), name=tpl.get('name')).first()
        exists = bool(obj)
        if exists and key not in changed_keys:
            unchanged += 1
            continue
        if exists and key not in overwrite_keys:
            skipped += 1
            continue
        if not obj:
            obj = NotificationTemplate(kind=tpl.get('kind'), name=tpl.get('name'))
            db.session.add(obj)
        obj.subject = tpl.get('subject') or ''
        obj.body = tpl.get('body') or ''
        obj.linked_form_template_name = tpl.get('linked_form_template_name') or None
        obj.recipient_source = tpl.get('recipient_source') or 'manual'
        obj.recipient_value = tpl.get('recipient_value') or ''
        obj.recipient_editable = bool(tpl.get('recipient_editable'))
        obj.recipient_external_allowed = bool(tpl.get('recipient_external_allowed'))
        obj.cc_source = tpl.get('cc_source') or 'manual'
        obj.cc_value = tpl.get('cc_value') or ''
        obj.cc_editable = bool(tpl.get('cc_editable'))
        obj.cc_external_allowed = bool(tpl.get('cc_external_allowed'))
        obj.is_default = bool(tpl.get('is_default'))
        al = tpl.get('action_label') or {}
        if al.get('kind') and al.get('value'):
            label = tenant_query(ConfigLabel).filter_by(kind=al.get('kind'), value=al.get('value')).first()
            obj.action_label_id = label.id if label else None
        created += 0 if exists else 1
        updated += 1 if exists else 0
    db.session.flush()

    wf = payload.get('workflow') or {}
    cat = wf.get('category') or None
    category_id = None
    if cat:
        category = tenant_query(ConfigLabel).filter_by(kind=cat.get('kind'), value=cat.get('value')).first()
        category_id = category.id if category else None
    existing = workflow_step_scope_query(category_id).all()
    existing_map = {f"{st.position}::{st.action_label.value if st.action_label else st.action_label_id}": st for st in existing}
    for st in wf.get('steps') or []:
        al = st.get('action_label') or {}
        label = tenant_query(ConfigLabel).filter_by(kind=al.get('kind'), value=al.get('value')).first()
        if not label:
            continue
        key_short = f"{st.get('position',0)}::{al.get('value','')}"
        key = f"workflow_step::{key_short}"
        obj = existing_map.get(key_short)
        exists = bool(obj)
        if exists and key not in changed_keys:
            unchanged += 1
            continue
        if exists and key not in overwrite_keys:
            skipped += 1
            continue
        if not obj:
            obj = IncidentWorkflowStep(tenant_id=current_tenant_id(default_to_default=True), category_id=category_id, action_label_id=label.id, position=int(st.get('position') or 0))
            db.session.add(obj)
        obj.action_label_id = label.id
        obj.description = st.get('description') or ''
        obj.step_type = normalize_workflow_step_type(st.get('step_type'))
        obj.set_condition_tokens(st.get('conditions') or [])
        obj.required = bool(st.get('required'))
        obj.requires_notification = bool(st.get('requires_notification'))
        obj.required_notification_type = st.get('required_notification_type') or None
        obj.document_generation_enabled = bool(st.get('document_generation_enabled'))
        obj.document_template_name = (st.get('document_template_name') or '').strip() or None
        obj.section_target = (st.get('section_target') or None) if workflow_step_type_uses_section_target(st.get('step_type')) else None
        created += 0 if exists else 1
        updated += 1 if exists else 0
    db.session.commit()
    return {'created': created, 'updated': updated, 'skipped': skipped, 'unchanged': unchanged}

@bp.route('/admin/incident-workflows',methods=['GET','POST'])
@login_required
def admin_incident_workflows():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        action = request.form.get('action') or 'add'
        if action == 'add_step_type':
            records = workflow_step_type_records()
            existing = {item['code'] for item in records}
            label = (request.form.get('new_step_type_label') or '').strip()[:80]
            description = (request.form.get('new_step_type_description') or '').strip()[:120]
            if not label:
                flash('Inserire il nome della nuova tipologia di step','error')
            else:
                code = _workflow_step_type_code_from_label(label, existing)
                records.append({'code': code, 'label': label, 'description': description or label, 'protected': False})
                save_workflow_step_type_records(records)
                flash('Tipologia di step aggiunta','success')
        elif action == 'save_step_types':
            current = {item['code']: item for item in workflow_step_type_records()}
            records = []
            for code in request.form.getlist('step_type_code'):
                item = current.get(code)
                if not item:
                    continue
                if item.get('protected'):
                    label = item['label']
                else:
                    label = (request.form.get(f'step_type_label_{code}') or item['label']).strip()[:80]
                description = (request.form.get(f'step_type_description_{code}') or label).strip()[:120]
                records.append({'code': code, 'label': label, 'description': description or label, 'protected': bool(item.get('protected'))})
            save_workflow_step_type_records(records)
            flash('Tipologie di step aggiornate','success')
        elif action == 'delete_step_type':
            code = normalize_workflow_step_type(request.form.get('step_type_code'))
            records = workflow_step_type_records()
            selected = next((item for item in records if item['code'] == code), None)
            if not selected:
                flash('Tipologia di step non trovata','error')
            elif selected.get('protected'):
                flash('Le tipologie di default non possono essere eliminate','error')
            else:
                workflow_step_base_query().filter_by(step_type=code).update({'step_type': REGISTRATION_STEP_TYPE}, synchronize_session=False)
                save_workflow_step_type_records([item for item in records if item['code'] != code])
                db.session.commit()
                flash('Tipologia di step eliminata; gli step associati sono stati riassegnati a Registrazione','info')
        elif action == 'clone_workflow':
            source_category_id = parse_workflow_scope_value(request.form.get('clone_source'))
            destination_category_id = parse_workflow_scope_value(request.form.get('clone_destination'))
            overwrite = bool(request.form.get('clone_overwrite_confirm'))
            if source_category_id == destination_category_id:
                flash('Sorgente e destinazione devono essere diverse per clonare un workflow','error')
            else:
                result = clone_workflow_steps(source_category_id, destination_category_id, overwrite=overwrite)
                flash(result['message'], 'success' if result.get('ok') else 'error')
        elif action == 'clone_workflow_cross_tenant':
            if not is_superuser():
                flash('Solo i superuser possono clonare workflow tra tenant diversi','error')
            else:
                source_tid = request.form.get('clone_source_tenant_id', type=int)
                dest_tid = request.form.get('clone_destination_tenant_id', type=int)
                source_tenant = db.session.get(Tenant, source_tid) if source_tid else None
                dest_tenant = db.session.get(Tenant, dest_tid) if dest_tid else None
                source_scope_raw = request.form.get('clone_cross_source')
                dest_scope_raw = request.form.get('clone_cross_destination')
                source_valid = workflow_scope_value_valid_for_tenant(source_scope_raw, source_tid) if source_tenant else False
                source_category_id = parse_workflow_scope_value_for_tenant(source_scope_raw, source_tid) if source_valid else None
                source_has_steps = bool(source_valid and workflow_step_scope_query(source_category_id, source_tid).count())
                create_new_destination = (dest_scope_raw or '').strip() == '__new__'
                dest_valid = create_new_destination or (workflow_scope_value_valid_for_tenant(dest_scope_raw, dest_tid) if dest_tenant else False)
                destination_category_id = None if create_new_destination else (parse_workflow_scope_value_for_tenant(dest_scope_raw, dest_tid) if dest_valid else None)
                overwrite = bool(request.form.get('clone_cross_overwrite_confirm'))
                if not source_tenant or not dest_tenant:
                    flash('Tenant sorgente o destinazione non valido','error')
                elif not source_valid or not source_has_steps:
                    flash('Il workflow sorgente non è valido o non contiene step nel tenant selezionato','error')
                elif not dest_valid:
                    flash('Workflow destinazione non valido per il tenant selezionato','error')
                elif source_tid == dest_tid and not create_new_destination and source_category_id == destination_category_id:
                    flash('Sorgente e destinazione devono essere diverse per clonare un workflow','error')
                else:
                    if create_new_destination:
                        destination_category_id, err = create_new_workflow_destination_for_clone(source_category_id, source_tid, dest_tid)
                        if err:
                            flash(err, 'error')
                            return redirect(url_for('main.admin_incident_workflows'))
                        overwrite = False
                    result = clone_workflow_steps(source_category_id, destination_category_id, overwrite=overwrite, source_tenant_id=source_tid, destination_tenant_id=dest_tid)
                    flash(result['message'], 'success' if result.get('ok') else 'error')
        elif action == 'delete_workflow':
            category_id = parse_workflow_scope_value(request.form.get('delete_scope'))
            removed = delete_workflow_steps(category_id)
            db.session.commit()
            flash(f'Flusso eliminato per {workflow_scope_display_name(category_id)}: {removed} step rimossi.', 'info')
            return redirect(url_for('main.admin_incident_workflows'))
        elif action == 'renumber_workflow':
            category_id = parse_workflow_scope_value(request.form.get('renumber_scope'))
            rows = workflow_step_scope_query(category_id).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
            for idx, row in enumerate(rows, start=1):
                row.position = idx * 10
            db.session.commit()
            flash(f'Ordine workflow risistemato per {workflow_scope_display_name(category_id)}', 'success')
            return redirect(url_for('main.admin_incident_workflows') + '#' + (request.form.get('return_anchor') or ''))
        elif action == 'add':
            scope = request.form.get('scope') or 'default'
            category_id = request.form.get('category_id', type=int) if scope == 'category' else None
            action_label_id = request.form.get('action_label_id', type=int)
            description = (request.form.get('description') or '').strip()[:500]
            step_type = normalize_workflow_step_type(request.form.get('step_type'))
            section_target = workflow_update_section_target_from_form('section_target') if workflow_step_type_uses_section_target(step_type) else ''
            condition_tokens = workflow_condition_tokens_from_form('conditions')
            personal_data_only = ('personal_data' in condition_tokens)
            required = bool(request.form.get('required'))
            requires_notification = bool(request.form.get('requires_notification'))
            required_notification_type = (request.form.get('required_notification_type') or '').strip() or None
            document_generation_enabled = bool(request.form.get('document_generation_enabled'))
            document_template_name = workflow_document_template_from_form('document_template_name') if document_generation_enabled else None
            position = request.form.get('position', type=int)
            if not action_label_id:
                flash('Selezionare una azione del flusso','error')
            elif document_generation_enabled and not document_template_name:
                flash('Selezionare un modello template valido per lo step di generazione documento','error')
            elif workflow_step_type_uses_section_target(step_type) and not section_target:
                flash('Selezionare la sezione da aggiornare per lo step selezionato','error')
            else:
                if position is None:
                    q = workflow_step_scope_query(category_id)
                    last = q.order_by(IncidentWorkflowStep.position.desc()).first()
                    position = (last.position + 10) if last else 10
                align_table_sequence('incident_workflow_step')
                step = IncidentWorkflowStep(tenant_id=current_tenant_id(default_to_default=True), category_id=category_id, action_label_id=action_label_id, description=description, step_type=step_type, personal_data_only=personal_data_only, conditions=','.join(condition_tokens), required=required, requires_notification=requires_notification, required_notification_type=required_notification_type, document_generation_enabled=document_generation_enabled, document_template_name=document_template_name, section_target=section_target, position=position)
                db.session.add(step)
                try:
                    db.session.commit()
                except IntegrityError as exc:
                    db.session.rollback()
                    if not is_duplicate_key_integrity_error(exc):
                        raise
                    current_app.logger.warning('Duplicate key su incident_workflow_step; riallineo la sequence e ritento inserimento step workflow')
                    align_table_sequence('incident_workflow_step')
                    step = IncidentWorkflowStep(tenant_id=current_tenant_id(default_to_default=True), category_id=category_id, action_label_id=action_label_id, description=description, step_type=step_type, personal_data_only=personal_data_only, conditions=','.join(condition_tokens), required=required, requires_notification=requires_notification, required_notification_type=required_notification_type, document_generation_enabled=document_generation_enabled, document_template_name=document_template_name, section_target=section_target, position=position)
                    db.session.add(step)
                    db.session.commit()
                flash('Passo del flusso aggiunto','success')
        elif action == 'save':
            ids = request.form.getlist('step_id')
            for sid in ids:
                step = db.session.get(IncidentWorkflowStep, int(sid))
                if not step or step.tenant_id != current_tenant_id(default_to_default=True): continue
                step.position = request.form.get(f'position_{sid}', type=int) or 0
                step.description = (request.form.get(f'description_{sid}') or '').strip()[:500]
                step.step_type = normalize_workflow_step_type(request.form.get(f'step_type_{sid}'))
                if workflow_step_type_uses_section_target(step.step_type):
                    step.section_target = workflow_update_section_target_from_form(f'section_target_{sid}') or None
                else:
                    step.section_target = None
                condition_tokens = workflow_condition_tokens_from_form(f'conditions_{sid}')
                step.set_condition_tokens(condition_tokens)
                step.required = bool(request.form.get(f'required_{sid}'))
                step.requires_notification = bool(request.form.get(f'requires_notification_{sid}'))
                step.required_notification_type = (request.form.get(f'required_notification_type_{sid}') or '').strip() or None
                step.document_generation_enabled = bool(request.form.get(f'document_generation_enabled_{sid}'))
                step.document_template_name = workflow_document_template_from_form(f'document_template_name_{sid}') if step.document_generation_enabled else None
                new_label = request.form.get(f'action_label_id_{sid}', type=int)
                if new_label: step.action_label_id = new_label
            db.session.commit(); flash('Flussi aggiornati','success')
            return redirect(url_for('main.admin_incident_workflows') + '#' + (request.form.get('return_anchor') or ''))
        return redirect(url_for('main.admin_incident_workflows'))
    steps = workflow_step_base_query().order_by(IncidentWorkflowStep.category_id, IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    grouped = {}
    for step in steps:
        grouped.setdefault(step.category_id or 0, []).append(step)
    step_type_records = workflow_step_type_records()
    category_list = labels('category')
    workflow_tenants = Tenant.query.order_by(Tenant.name).all() if is_superuser() else []
    return render_template('admin_incident_workflows.html', categories=category_list, action_labels=labels('action_label'), notification_types=notification_type_records(enabled_only=False), document_tag_options=notification_type_tag_options(enabled_only=False), form_templates=list_templates(), severities=labels('severity'), data_types=labels('data_type'), grouped=grouped, workflow_scope_options=workflow_scope_options(category_list), workflow_tenant_scope_options=workflow_scope_options_by_tenant(workflow_tenants), workflow_step_types=workflow_step_type_pairs(), workflow_step_type_records=step_type_records, workflow_step_type_descriptions={item['code']: item['description'] for item in step_type_records}, incident_sections=INCIDENT_DETAIL_SECTIONS)

@bp.route('/admin/incident-workflows/<int:sid>/delete',methods=['POST'])
@login_required
def admin_incident_workflow_delete(sid):
    if not can_admin(): return redirect(url_for('main.index'))
    step=model_or_404(IncidentWorkflowStep, sid)
    db.session.delete(step); db.session.commit(); flash('Passo del flusso eliminato','info')
    return redirect(url_for('main.admin_incident_workflows'))


@bp.route('/admin/incident-workflows/export/preview', methods=['POST'])
@login_required
def admin_incident_workflow_export_preview():
    if not can_admin(): return redirect(url_for('main.index'))
    category_id = request.form.get('category_id', type=int)
    payload = build_workflow_export_payload(category_id)
    return render_template('admin_workflow_export_preview.html', payload=payload, payload_json=json.dumps(payload, ensure_ascii=False, indent=2), category_id=category_id)

@bp.route('/admin/incident-workflows/export/download', methods=['POST'])
@login_required
def admin_incident_workflow_export_download():
    if not can_admin(): return redirect(url_for('main.index'))
    category_id = request.form.get('category_id', type=int)
    payload = build_workflow_export_payload(category_id)
    name = _workflow_scope_label(category_id).replace(' ', '_').replace('/', '_')
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    return send_file(io.BytesIO(data), as_attachment=True, download_name=f'workflow_{name}.json', mimetype='application/json')

@bp.route('/admin/incident-workflows/import/preview', methods=['POST'])
@login_required
def admin_incident_workflow_import_preview():
    if not can_admin(): return redirect(url_for('main.index'))
    uploaded = request.files.get('workflow_file')
    if not uploaded or not uploaded.filename:
        flash('Selezionare un file JSON di workflow da importare', 'error')
        return redirect(url_for('main.admin_incident_workflows'))
    try:
        raw = uploaded.read()
        payload = json.loads(raw.decode('utf-8'))
    except Exception as exc:
        flash(f'File workflow non valido: {exc}', 'error')
        return redirect(url_for('main.admin_incident_workflows'))
    if payload.get('format') != 'cybersecurity-incident-registry.workflow.v1':
        flash('Formato export workflow non riconosciuto', 'error')
        return redirect(url_for('main.admin_incident_workflows'))
    diffs = workflow_import_diff(payload)
    cleanup_old_workflow_import_payloads()
    import_token = store_workflow_import_payload(payload)
    return render_template('admin_workflow_import_preview.html', payload=payload, payload_json=json.dumps(payload, ensure_ascii=False, indent=2), import_token=import_token, diffs=diffs)

@bp.route('/admin/incident-workflows/import/apply', methods=['POST'])
@login_required
def admin_incident_workflow_import_apply():
    if not can_admin(): return redirect(url_for('main.index'))
    try:
        token = request.form.get('import_token')
        if token:
            payload = load_workflow_import_payload(token, remove=True)
        else:
            # Compatibilita' con eventuali pagine di preview generate da versioni precedenti.
            payload = json.loads(base64.b64decode(request.form.get('payload_b64') or '').decode('utf-8'))
    except Exception as exc:
        flash(f'Payload import workflow non valido: {exc}', 'error')
        return redirect(url_for('main.admin_incident_workflows'))
    overwrite_keys = request.form.getlist('overwrite_key')
    result = apply_workflow_import(payload, overwrite_keys)
    flash(f"Workflow importato. Creati: {result['created']}; aggiornati: {result['updated']}; ignorati: {result['skipped']}; identici non importati: {result.get('unchanged', 0)}.", 'success')
    return redirect(url_for('main.admin_incident_workflows'))


@bp.route('/admin/incident-button-actions', methods=['GET','POST'])
@login_required
def admin_incident_button_actions():
    if not can_admin():
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        config = {}
        for code, _label in INCIDENT_BUTTON_ACTIONS:
            if code == 'document_tags_save':
                rules = []
                try:
                    rule_count = int(request.form.get('document_tags_save_rule_count') or 0)
                except (TypeError, ValueError):
                    rule_count = 0
                for idx in range(max(rule_count, 0)):
                    value = request.form.get(f'action_label_id_{code}_{idx}') or ''
                    scope = request.form.get(f'action_scope_{code}_{idx}') or 'always'
                    tags = request.form.getlist(f'notification_tags_{code}_{idx}')
                    if value:
                        rules.append({'label_id': value, 'scope': scope, 'notification_tags': tags})
                if rules:
                    config[code] = rules
                continue
            if code in {'document_upload', 'document_download'}:
                rules = []
                try:
                    rule_count = int(request.form.get(f'{code}_rule_count') or 0)
                except (TypeError, ValueError):
                    rule_count = 0
                for idx in range(max(rule_count, 0)):
                    value = request.form.get(f'action_label_id_{code}_{idx}') or ''
                    scope = request.form.get(f'action_scope_{code}_{idx}') or 'always'
                    template_name = request.form.get(f'action_template_name_{code}_{idx}') or ''
                    if value:
                        rule = {'label_id': value, 'scope': scope, 'template_name': template_name}
                        if code == 'document_upload':
                            rule['notification_tags'] = request.form.getlist(f'notification_tags_{code}_{idx}')
                        rules.append(rule)
                if rules:
                    config[code] = rules
                continue
            if code == 'incident_update':
                rules = []
                generic_value = request.form.get('action_label_id_incident_update_generic') or request.form.get('action_label_id_incident_update') or ''
                if generic_value:
                    rules.append({'label_id': generic_value, 'scope': 'always'})
                try:
                    rule_count = int(request.form.get('incident_update_workflow_rule_count') or 0)
                except (TypeError, ValueError):
                    rule_count = 0
                for idx in range(max(rule_count, 0)):
                    value = request.form.get(f'action_label_id_incident_update_workflow_{idx}') or ''
                    if value:
                        rules.append({'label_id': value, 'scope': WORKFLOW_UPDATE_SECTION_SCOPE})
                if rules:
                    config[code] = rules
                continue
            value = request.form.get(f'action_label_id_{code}') or ''
            scope = request.form.get(f'action_scope_{code}') or 'always'
            if value:
                config[code] = {'label_id': value, 'scope': scope}
        save_button_action_config(config)
        db.session.commit()
        flash('Configurazione azioni automatiche dei pulsanti salvata', 'success')
        return redirect(url_for('main.admin_incident_button_actions'))
    return render_template(
        'admin_incident_button_actions.html',
        button_actions=INCIDENT_BUTTON_ACTIONS,
        action_labels=labels('action_label'),
        config=button_action_config(),
        notification_types=notification_type_records(enabled_only=False),
        form_templates=list_templates(),
    )

@bp.route('/admin/labels',methods=['GET','POST'])
@login_required
def admin_labels():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        kind=request.form.get('kind','').strip()
        group=request.form.get('group','').strip() or kind
        value=request.form.get('value','').strip()
        description=request.form.get('description','').strip()
        if not kind or not value:
            flash('Indicare il nome della label','error')
        else:
            existing=effective_config_labels_query(kind).filter_by(value=value).first()
            max_hours=request.form.get('max_completion_hours', type=int)
            default_exportable = bool(request.form.get('default_exportable')) if kind == 'action_label' else True
            description_required = bool(request.form.get('description_required')) if kind == 'action_label' else False
            automatic_operations = ','.join([op for op in request.form.getlist('automatic_operations') if op in AUTOMATIC_ACTION_OPERATIONS]) if kind == 'action_label' else ''
            if existing:
                existing.group=group; existing.description=description
                if kind == 'action_label':
                    existing.max_completion_hours = max_hours if max_hours is not None and max_hours >= 0 else 0
                    existing.default_exportable = default_exportable
                    existing.description_required = description_required
                    existing.automatic_operations = automatic_operations
                flash('Label già presente: gruppo e descrizione aggiornati','info')
            else:
                db.session.add(ConfigLabel(tenant_id=current_tenant_id(), kind=kind,group=group,value=value,description=description,max_completion_hours=(max_hours if kind=='action_label' and max_hours is not None and max_hours >= 0 else 0),default_exportable=default_exportable,description_required=description_required,automatic_operations=automatic_operations))
            try:
                db.session.commit()
            except Exception as exc:
                current_app.logger.exception('Errore durante il salvataggio della label')
                db.session.rollback(); flash(f'Errore salvataggio label: {exc}','error')
    return render_template('admin_labels.html',items=effective_config_labels_query().order_by(ConfigLabel.kind,ConfigLabel.group,ConfigLabel.value).all(), automatic_action_operations=AUTOMATIC_ACTION_OPERATIONS, default_config_labels=DEFAULT_CONFIG_LABELS)

@bp.route('/admin/labels/restore-defaults', methods=['POST'])
@login_required
def admin_labels_restore_defaults():
    if not can_admin():
        return redirect(url_for('main.index'))
    try:
        added = restore_missing_default_config_labels()
        db.session.commit()
    except Exception as exc:
        current_app.logger.exception('Errore durante il ripristino delle label predefinite')
        db.session.rollback()
        flash(f'Errore ripristino valori predefiniti: {exc}', 'error')
        return redirect(url_for('main.admin_labels'))
    if added:
        names = ', '.join(value for _kind, value in added[:12])
        suffix = '…' if len(added) > 12 else ''
        flash(f'Valori predefiniti mancanti reinseriti: {len(added)} ({names}{suffix})', 'success')
    else:
        flash('Tutti i valori predefiniti sono già presenti: nessuna label aggiunta.', 'info')
    return redirect(url_for('main.admin_labels'))

@bp.route('/admin/labels/<int:lid>/update',methods=['POST'])
@login_required
def admin_label_update(lid):
    if not can_admin():
        return redirect(url_for('main.index'))
    lab=model_or_404(ConfigLabel, lid)
    value=(request.form.get('value') or '').strip()
    description=(request.form.get('description') or '').strip()
    if not value:
        flash('Il nome della label non può essere vuoto','error')
    else:
        lab.value=value
        lab.description=description
        if lab.kind == 'action_label':
            mh = request.form.get('max_completion_hours', type=int)
            lab.max_completion_hours = mh if mh is not None and mh >= 0 else 0
            lab.default_exportable = bool(request.form.get('default_exportable'))
            lab.description_required = bool(request.form.get('description_required'))
            lab.automatic_operations = ','.join([op for op in request.form.getlist('automatic_operations') if op in AUTOMATIC_ACTION_OPERATIONS])
        try:
            db.session.commit(); flash('Label aggiornata','success')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore aggiornamento label'); flash(f'Errore aggiornamento label: {exc}','error')
    return redirect(url_for('main.admin_labels'))

@bp.route('/admin/labels/<int:lid>/delete',methods=['POST'])
@login_required
def admin_label_delete(lid):
    if can_admin():
        lab=effective_config_labels_query().filter_by(id=lid).first() or abort(404)
        # Rimuove la label da tutti gli incidenti e dalle azioni prima della cancellazione,
        # così non restano foreign key pendenti e la cancellazione è coerente con la UI.
        for inc in tenant_query(Incident).all():
            if lab in inc.categories: inc.categories.remove(lab)
            if lab in inc.data_types: inc.data_types.remove(lab)
            if inc.severity_id==lab.id: inc.severity_id=None
        for action in Action.query.filter_by(label_id=lab.id).all():
            action.label_id=None
        db.session.delete(lab)
        try:
            db.session.commit(); flash('Label cancellata e rimossa dagli incidenti','info')
        except Exception as exc:
            current_app.logger.exception('Errore durante la cancellazione della label')
            db.session.rollback(); flash(f'Errore cancellazione label: {exc}','error')
    return redirect(url_for('main.admin_labels'))
@bp.route('/admin/people',methods=['GET','POST'])
@login_required
def admin_people():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        name=(request.form.get('name') or '').strip()
        email=(request.form.get('email') or '').strip()
        if not name:
            flash('Indicare il nome della persona','error')
        else:
            existing=tenant_query(Person).filter_by(name=name).first()
            if existing:
                existing.email=email
                flash('Persona già presente: email aggiornata','info')
            else:
                # Il personale non usa più Categoria/Gruppo: l'unico input richiesto è nome + email.
                db.session.add(Person(tenant_id=current_tenant_id(), name=name,email=email,group='personale'))
            try:
                db.session.commit()
            except Exception as exc:
                current_app.logger.exception('Errore durante il salvataggio del personale')
                db.session.rollback(); flash(f'Errore salvataggio personale: {exc}','error')
    return render_template('admin_people.html',people=tenant_query(Person).order_by(Person.name).all())

@bp.route('/admin/people/<int:pid>/delete',methods=['POST'])
@login_required
def admin_people_delete(pid):
    if not can_admin(): return redirect(url_for('main.index'))
    person=model_or_404(Person, pid)
    for inc in tenant_query(Incident).all():
        if person in inc.people:
            inc.people.remove(person)
    db.session.delete(person)
    try:
        db.session.commit(); flash('Persona cancellata e rimossa dagli incidenti','info')
    except Exception as exc:
        current_app.logger.exception('Errore durante la cancellazione del personale')
        db.session.rollback(); flash(f'Errore cancellazione personale: {exc}','error')
    return redirect(url_for('main.admin_people'))


@bp.route('/admin/security-owner',methods=['GET','POST'])
@login_required
def admin_security_owner():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        set_setting_value('security_owner_name', request.form.get('security_owner_name','').strip())
        set_setting_value('security_owner_role', request.form.get('security_owner_role','').strip())
        set_setting_value('security_owner_email', request.form.get('security_owner_email','').strip())
        db.session.commit(); flash('Dati titolare salvati','success')
        return redirect(url_for('main.admin_security_owner'))
    return render_template('admin_security_owner.html', owner_name=setting_value('security_owner_name'), owner_role=setting_value('security_owner_role'), owner_email=setting_value('security_owner_email'))

@bp.route('/admin/structure',methods=['GET','POST'])
@login_required
def admin_structure():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        set_setting_value('structure_name', request.form.get('structure_name','').strip())
        db.session.commit(); flash('Dati struttura salvati','success')
        return redirect(url_for('main.admin_structure'))
    return render_template('admin_structure.html', structure_name=setting_value('structure_name'))

@bp.route('/admin/security-responsible',methods=['GET','POST'])
@login_required
def admin_security_responsible():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        set_setting_value('security_responsible_name', request.form.get('security_responsible_name','').strip())
        set_setting_value('security_responsible_email', request.form.get('security_responsible_email','').strip())
        set_setting_value('security_responsible_phone', request.form.get('security_responsible_phone','-').strip() or '-')
        set_setting_value('security_responsible_function', request.form.get('security_responsible_function','').strip())
        db.session.commit(); flash('Dati responsabile salvati','success')
        return redirect(url_for('main.admin_security_responsible'))
    return render_template('admin_security_responsible.html',
        responsible_name=setting_value('security_responsible_name'),
        responsible_email=setting_value('security_responsible_email'),
        responsible_phone=setting_value('security_responsible_phone','-'),
        responsible_function=setting_value('security_responsible_function'))

@bp.route('/admin/recommendations',methods=['GET','POST'])
@login_required
def admin_recommendations():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        action = request.form.get('action') or ''
        if action == 'save_config':
            max_selected = _bounded_int(request.form.get('recommendations_max_per_incident', '3'), 3, 1, 999)
            set_setting_value('recommendations_max_per_incident', str(max_selected))
            audit_log('admin:recommendations_config_update', {'recommendations_max_per_incident': max_selected}, actor_type='user')
            try:
                db.session.commit(); flash('Configurazione raccomandazioni aggiornata','success')
            except Exception as exc:
                db.session.rollback(); flash(f'Errore: {exc}','error')
        else:
            text=(request.form.get('text') or '').strip()
            rid=request.form.get('id')
            if not text:
                flash('Indicare il testo della raccomandazione','error')
            elif rid:
                rec=model_or_404(Recommendation, int(rid)); rec.text=text
                try: db.session.commit(); flash('Raccomandazione aggiornata','success')
                except Exception as exc: db.session.rollback(); flash(f'Errore: {exc}','error')
            elif tenant_query(Recommendation).filter_by(text=text).first():
                flash('Raccomandazione già presente','info')
            else:
                db.session.add(Recommendation(tenant_id=current_tenant_id(), text=text))
                try: db.session.commit(); flash('Raccomandazione aggiunta','success')
                except Exception as exc: db.session.rollback(); flash(f'Errore: {exc}','error')
    return render_template('admin_recommendations.html', recommendations=tenant_query(Recommendation).order_by(Recommendation.text).all(), recommendations_max_per_incident=recommendations_limit())

@bp.route('/admin/recommendations/<int:rid>/delete',methods=['POST'])
@login_required
def admin_recommendation_delete(rid):
    if not can_admin(): return redirect(url_for('main.index'))
    rec=model_or_404(Recommendation, rid)
    for inc in tenant_query(Incident).all():
        if rec in inc.recommendations:
            inc.recommendations.remove(rec)
    db.session.delete(rec)
    db.session.commit(); flash('Raccomandazione cancellata e rimossa dagli incidenti','info')
    return redirect(url_for('main.admin_recommendations'))

@bp.route('/logo')
def logo_image():
    setting=db.session.get(Setting, 'logo_path')
    path=setting.value if setting and setting.value else ''
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path)

@bp.route('/admin/logo',methods=['GET','POST'])
@login_required
def admin_logo():
    if not can_admin(): return redirect(url_for('main.index'))
    setting=db.session.get(Setting, 'logo_path') or Setting(key='logo_path',value='')
    if request.method=='POST':
        action=request.form.get('action')
        if action=='delete':
            if setting.value and os.path.exists(setting.value):
                try: os.remove(setting.value)
                except OSError: current_app.logger.warning('Impossibile rimuovere il logo %s', setting.value)
            setting.value=''
            db.session.merge(setting); db.session.commit(); flash('Logo cancellato','info')
            return redirect(url_for('main.admin_logo'))
        f=request.files.get('logo')
        if not f or not f.filename:
            flash('Selezionare un file logo','error')
        else:
            try:
                filename = validate_upload_file(f, allowed_extensions={'.png','.jpg','.jpeg','.gif','.webp','.svg'}, max_size=2 * 1024 * 1024)
                ext=os.path.splitext(filename)[1].lower() or '.img'
                os.makedirs(current_app.config['LOGO_DIR'],exist_ok=True)
                path=os.path.join(current_app.config['LOGO_DIR'],f'logo{ext}')
                f.save(path)
                try: os.chmod(path, 0o600)
                except OSError: pass
                # rimuove eventuali vecchi logo con estensione diversa
                for old in Path(current_app.config['LOGO_DIR']).glob('logo.*'):
                    if str(old)!=path:
                        try: old.unlink()
                        except OSError: pass
                setting.value=path
                db.session.merge(setting); db.session.commit(); flash('Logo aggiornato','info')
                return redirect(url_for('main.admin_logo'))
            except ValueError as exc:
                audit_log('security:invalid_upload', {'area': 'admin_logo', 'error': str(exc)}, commit=True)
                flash(str(exc),'error')
    return render_template('admin_logo.html')


@bp.route('/mfa/verify', methods=['GET','POST'])
def mfa_verify():
    uid = session.get('mfa_user_id')
    if not uid:
        return redirect(url_for('main.login'))
    user = db.session.get(User, uid)
    if not user or not user_has_any_active_role(user):
        session.pop('mfa_user_id', None); session.pop('mfa_next', None)
        flash('Sessione MFA non valida.', 'error')
        return redirect(url_for('main.login'))
    if request.method == 'POST':
        code = (request.form.get('code') or '').replace(' ', '').strip()
        for token in MfaTotpToken.query.filter_by(user_id=user.id).all():
            if pyotp.TOTP(token.secret).verify(code, valid_window=1):
                token.last_used_at = utcnow(); db.session.commit()
                session.pop('mfa_user_id', None)
                next_url = session.pop('mfa_next', None) or url_for('main.index')
                login_user(user)
                return redirect(next_url)
        flash('Codice MFA non valido.', 'error')
    return render_template('mfa_verify.html', user=user)

@bp.route('/settings/mfa', methods=['GET','POST'])
@login_required
def mfa_settings():
    pending_token = session.get('pending_mfa_token')
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'toggle':
            enable = bool(request.form.get('mfa_enabled'))
            verified_exists = MfaTotpToken.query.filter_by(user_id=current_user.id).filter(MfaTotpToken.verified_at.isnot(None)).first()
            if enable and not verified_exists:
                flash('Per attivare la MFA devi prima creare e verificare almeno un token TOTP.', 'error')
            else:
                current_user.mfa_enabled = enable
                db.session.commit(); flash('Impostazione MFA aggiornata.')
        elif action == 'prepare':
            secret = pyotp.random_base32()
            session['pending_mfa_token'] = {'name': request.form.get('name') or 'Token TOTP', 'secret': secret, 'created_at': utcnow().isoformat()}
            flash('Token generato. Scansiona il QR Code o copia la stringa, poi inserisci il codice TOTP per verificarlo e salvarlo.')
        elif action == 'verify_new':
            pending_token = session.get('pending_mfa_token')
            code = (request.form.get('code') or '').replace(' ', '').strip()
            if not pending_token:
                flash('Nessun token in verifica. Crea un nuovo token TOTP.', 'error')
            elif pyotp.TOTP(pending_token['secret']).verify(code, valid_window=1):
                token = MfaTotpToken(user_id=current_user.id, name=pending_token.get('name') or 'Token TOTP', secret=pending_token['secret'], verified_at=utcnow())
                db.session.add(token); db.session.commit()
                session.pop('pending_mfa_token', None)
                flash('Token MFA verificato e salvato correttamente.')
            else:
                flash('Codice TOTP non valido: il token non è stato salvato.', 'error')
        elif action == 'cancel_pending':
            session.pop('pending_mfa_token', None)
            flash('Creazione token annullata.')
        elif action == 'delete':
            token = MfaTotpToken.query.filter_by(id=request.form.get('token_id'), user_id=current_user.id).first_or_404()
            db.session.delete(token)
            remaining_verified = MfaTotpToken.query.filter(MfaTotpToken.user_id==current_user.id, MfaTotpToken.id!=token.id, MfaTotpToken.verified_at.isnot(None)).first()
            if not remaining_verified:
                current_user.mfa_enabled = False
            db.session.commit(); flash('Token MFA eliminato.')
        return redirect(url_for('main.mfa_settings'))
    pending_token = session.get('pending_mfa_token')
    qr_data_uri = None; provisioning_uri = None
    if pending_token:
        issuer = 'Cybersecurity Incident Registry'
        provisioning_uri = pyotp.TOTP(pending_token['secret']).provisioning_uri(name=current_user.email or current_user.username, issuer_name=issuer)
        img = qrcode.make(provisioning_uri)
        buf = io.BytesIO(); img.save(buf, format='PNG')
        qr_data_uri = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    verified_count = MfaTotpToken.query.filter_by(user_id=current_user.id).filter(MfaTotpToken.verified_at.isnot(None)).count()
    return render_template('mfa_settings.html', tokens=MfaTotpToken.query.filter_by(user_id=current_user.id).order_by(MfaTotpToken.created_at.desc()).all(), pending_token=pending_token, qr_data_uri=qr_data_uri, provisioning_uri=provisioning_uri, verified_count=verified_count)

@bp.route('/admin/user/<int:uid>/mfa', methods=['GET','POST'])
@login_required
def admin_user_mfa(uid):
    if not can_admin(): return redirect(url_for('main.index'))
    user = model_or_404(User, uid)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'toggle':
            enable = bool(request.form.get('mfa_enabled'))
            verified_exists = MfaTotpToken.query.filter_by(user_id=user.id).filter(MfaTotpToken.verified_at.isnot(None)).first()
            if enable and not verified_exists:
                flash('Per attivare la MFA dell’utente deve esistere almeno un token TOTP verificato.', 'error')
            else:
                user.mfa_enabled = enable
                db.session.commit(); flash('Impostazione MFA utente aggiornata.')
        elif action == 'delete':
            token = MfaTotpToken.query.filter_by(id=request.form.get('token_id'), user_id=user.id).first_or_404()
            db.session.delete(token)
            remaining_verified = MfaTotpToken.query.filter(MfaTotpToken.user_id==user.id, MfaTotpToken.id!=token.id, MfaTotpToken.verified_at.isnot(None)).first()
            if not remaining_verified:
                user.mfa_enabled = False
            db.session.commit(); flash('Token MFA rimosso.')
        elif action == 'delete_all':
            MfaTotpToken.query.filter_by(user_id=user.id).delete(); user.mfa_enabled = False; db.session.commit(); flash('Tutti i token MFA dell’utente sono stati rimossi e la MFA è stata disattivata.')
        return redirect(url_for('main.admin_user_mfa', uid=user.id))
    return render_template('admin_user_mfa.html', target_user=user, tokens=MfaTotpToken.query.filter_by(user_id=user.id).order_by(MfaTotpToken.created_at.desc()).all())

def user_auth_provider_labels():
    """Return human-readable labels for login backends shown in Admin → Users.

    SSO backends are stored as sso:<profile id>; administrators need the
    provider display name as well as the technical profile id to distinguish
    users that share the same username across different SSO providers.
    """
    labels = {'local': 'Locale', 'ldap': 'LDAP'}
    for profile in sso_profiles(include_legacy=True):
        pid = (profile.get('id') or '').strip()
        if not pid:
            continue
        name = (profile.get('sso_provider_name') or profile.get('name') or pid).strip() or pid
        labels[f'sso:{pid}'] = f'SSO/OAuth2 · {name} ({pid})'
    return labels


def user_auth_provider_display(auth_provider):
    provider = (auth_provider or 'local').strip()
    labels = user_auth_provider_labels()
    if provider in labels:
        return labels[provider]
    if provider.startswith('sso:'):
        pid = provider.split(':', 1)[1] or 'sconosciuto'
        return f'SSO/OAuth2 · profilo non configurato ({pid})'
    return provider



def _external_recipients_page(endpoint_name, audit_prefix, title='Destinatari esterni', settings_mode=False):
    editing = None
    edit_id = request.args.get('edit', type=int)
    search_query = (request.values.get('q') or '').strip()
    if edit_id:
        editing = model_or_404(ExternalRecipient, edit_id)
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        rid = request.form.get('recipient_id', type=int)
        if action == 'delete':
            rec = model_or_404(ExternalRecipient, rid)
            db.session.delete(rec); db.session.commit()
            audit_log(f'{audit_prefix}:external_recipient_delete', {'recipient_id': rid}, actor_type='user', commit=True)
            flash('Destinatario esterno cancellato.')
            return redirect(url_for(endpoint_name, q=search_query) if search_query else url_for(endpoint_name))
        if action == 'delete_all':
            recipients_to_delete = tenant_query(ExternalRecipient).all()
            count = len(recipients_to_delete)
            deleted_ids = [r.id for r in recipients_to_delete]
            for rec in recipients_to_delete:
                db.session.delete(rec)
            db.session.commit()
            audit_log(f'{audit_prefix}:external_recipient_delete_all', {'count': count, 'recipient_ids': deleted_ids}, actor_type='user', commit=True)
            flash(f'Rimossi {count} destinatari esterni dalla rubrica.')
            return redirect(url_for(endpoint_name))
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip()
        notes = request.form.get('notes') or ''
        if not name or not email:
            flash('Nome ed email sono obbligatori.', 'error')
            params = {'edit': rid} if rid else {}
            if search_query:
                params['q'] = search_query
            return redirect(url_for(endpoint_name, **params))
        duplicate = ExternalRecipient.query.filter(db.func.lower(ExternalRecipient.email) == email.lower())
        if rid:
            duplicate = duplicate.filter(ExternalRecipient.id != rid)
        if duplicate.first():
            flash('Esiste già un destinatario esterno con questa email.', 'error')
            params = {'edit': rid} if rid else {}
            if search_query:
                params['q'] = search_query
            return redirect(url_for(endpoint_name, **params))
        rec = db.session.get(ExternalRecipient, rid) if rid else assign_current_tenant(ExternalRecipient())
        rec.name = name; rec.email = email; rec.notes = notes
        db.session.add(rec); db.session.commit()
        audit_log(f'{audit_prefix}:external_recipient_save', {'recipient_id': rec.id, 'email': rec.email}, actor_type='user', commit=True)
        flash('Destinatario esterno salvato.')
        return redirect(url_for(endpoint_name, q=search_query) if search_query else url_for(endpoint_name))
    recipients_query = ExternalRecipient.query
    if search_query:
        like = f'%{search_query}%'
        recipients_query = recipients_query.filter(db.or_(
            ExternalRecipient.name.ilike(like),
            ExternalRecipient.email.ilike(like),
            ExternalRecipient.notes.ilike(like),
        ))
    recipients = recipients_query.order_by(ExternalRecipient.name, ExternalRecipient.email).all()
    return render_template('admin_external_recipients.html', recipients=recipients, editing=editing, endpoint_name=endpoint_name, page_title=title, settings_mode=settings_mode, search_query=search_query)


@bp.route('/admin/external-recipients', methods=['GET','POST'])
@login_required
def admin_external_recipients():
    if not can_admin(): return redirect(url_for('main.index'))
    return _external_recipients_page('main.admin_external_recipients', 'admin', title='Destinatari esterni', settings_mode=False)


@bp.route('/settings/external-recipients', methods=['GET','POST'])
@login_required
def settings_external_recipients():
    if not can_manage_external_recipients_from_settings(): return redirect(url_for('main.index'))
    return _external_recipients_page('main.settings_external_recipients', 'settings', title='Destinatari esterni', settings_mode=True)


def _ldap_attr_list(raw, fallback='uid,cn,mail,displayName'):
    values=[]
    for item in (raw or fallback).split(','):
        item=item.strip()
        if item and re.match(r'^[A-Za-z][A-Za-z0-9._-]{0,63}$', item) and item not in values:
            values.append(item)
    return values or _ldap_attr_list(fallback, '')


def make_incident_ldap_filter(cfg, query):
    q=escape_filter_chars(query or '')
    template=(cfg.get('ldap_incident_search_filter') or '').strip()
    if template:
        if '{q}' not in template:
            raise ValueError('Il filtro ricerca incidenti LDAP deve contenere il placeholder {q}.')
        filt=template.replace('{q}', q)
        if not (filt.startswith('(') and filt.endswith(')')):
            raise ValueError('Filtro ricerca incidenti LDAP non valido.')
        return filt
    attrs=_ldap_attr_list(cfg.get('ldap_incident_search_attributes'))
    return '(|' + ''.join(f'({attr}=*{q}*)' for attr in attrs) + ')'


@bp.route('/ldap/incident-recipient-search')
@login_required
def ldap_incident_recipient_search():
    if not can_write():
        return jsonify({'ok': False, 'error': 'Permessi insufficienti'}), 403
    q=(request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'ok': True, 'entries': []})
    cfg=setting_map()
    try:
        display_attrs=_ldap_attr_list(cfg.get('ldap_incident_search_attributes'))
        attrs=list(display_attrs)
        configured_ref=(cfg.get('ldap_incident_reference_attribute') or '').strip()
        configured_email=(cfg.get('ldap_incident_email_attribute') or '').strip()
        ref_attr=configured_ref or (display_attrs[0] if display_attrs else 'uid')
        email_attr=configured_email or ('mail' if 'mail' in display_attrs else '')
        for extra in [configured_ref, configured_email]:
            if extra and extra not in attrs:
                attrs.append(extra)
        filt=make_incident_ldap_filter(cfg, q)
        srv=Server(cfg.get('ldap_uri'),get_info=ALL,connect_timeout=5)
        bind_dn=cfg.get('ldap_bind_dn') or None; bind_pw=cfg.get('ldap_bind_password') or None
        entries=[]
        with Connection(srv,user=bind_dn,password=bind_pw,auto_bind=True) as c:
            c.search(cfg.get('ldap_base_dn'),filt,attributes=attrs,size_limit=10)
            for e in c.entries:
                def aval(name):
                    if not name or not hasattr(e, name): return ''
                    v=getattr(e, name)
                    if hasattr(v, 'values') and v.values: return str(v.values[0])
                    return str(v) if str(v) != '[]' else ''
                reference=aval(ref_attr)
                if not reference:
                    for candidate in display_attrs:
                        reference = aval(candidate)
                        if reference:
                            break
                email=aval(email_attr) if email_attr else ''
                attr_values = {attr: aval(attr) for attr in display_attrs}
                entries.append({'dn': e.entry_dn, 'reference': reference or e.entry_dn, 'recipient': reference or e.entry_dn, 'email': email, 'attributes': attr_values})
        attrs = display_attrs
        return jsonify({'ok': True, 'entries': entries, 'attribute_order': attrs})
    except Exception as exc:
        current_app.logger.exception('Ricerca LDAP destinatario incidente fallita')
        return jsonify({'ok': False, 'error': str(exc)}), 400



def clone_tenant_config(source_tenant_id, dest_tenant_id):
    """Clone tenant-specific configuration from one tenant to another.

    The operation is idempotent: tenant-local objects are matched by their
    natural key before creation, so repeated tenant creation/cloning or later
    re-cloning does not duplicate labels, recipients, notification templates,
    workflow dependencies or other configuration elements already present in
    the destination tenant.
    """
    source_tenant_id = int(source_tenant_id)
    dest_tenant_id = int(dest_tenant_id)
    # I backup legacy ripristinati con ID espliciti possono lasciare indietro
    # le sequence PostgreSQL. Prima di creare qualunque record clonato
    # riallineiamo tutte le PK intere: l'operazione e' idempotente e previene
    # duplicate key su config_label_pkey e sulle altre tabelle clonate.
    align_all_table_sequences()
    # Normalizza eventuali label legacy/globali e duplicati preesistenti prima
    # di leggere la sorgente o creare record nel tenant destinazione.
    deduplicate_config_labels_for_tenant(source_tenant_id, include_legacy_global=(source_tenant_id == default_tenant().id))
    deduplicate_config_labels_for_tenant(dest_tenant_id)
    prefix = f'tenant:{source_tenant_id}:'
    source_settings = {}
    # Plain keys are legacy/default tenant values; keep the globally shared
    # settings unscoped and clone the remaining settings as tenant-specific.
    for row in Setting.query.all():
        key = row.key or ''
        if key.startswith(prefix):
            logical_key = key[len(prefix):]
            if logical_key not in GLOBAL_SETTING_KEYS:
                source_settings[logical_key] = row.value
        elif not key.startswith('tenant:') and key not in GLOBAL_SETTING_KEYS:
            source_settings.setdefault(key, row.value)
    for logical_key, value in source_settings.items():
        target_key = f'tenant:{dest_tenant_id}:{logical_key}'
        target = db.session.get(Setting, target_key)
        if target:
            target.value = value
        else:
            db.session.add(Setting(key=target_key, value=value))

    label_map = {}
    for src in ConfigLabel.query.filter_by(tenant_id=source_tenant_id).order_by(ConfigLabel.id).all():
        dst = _copy_or_update_label_to_tenant(src, dest_tenant_id)
        if dst:
            label_map[src.id] = dst.id

    person_map = {}
    for src in Person.query.filter_by(tenant_id=source_tenant_id).order_by(Person.id).all():
        dst = _copy_person_to_tenant(src, dest_tenant_id)
        if dst:
            person_map[src.id] = dst.id

    rec_map = {}
    for src in Recommendation.query.filter_by(tenant_id=source_tenant_id).order_by(Recommendation.id).all():
        dst = _copy_recommendation_to_tenant(src, dest_tenant_id)
        if dst:
            rec_map[src.id] = dst.id

    def remap_csv(raw, mapping):
        vals = []
        for item in (raw or '').split(','):
            try:
                old = int(item.strip())
            except Exception:
                continue
            new = mapping.get(old)
            if new and str(new) not in vals:
                vals.append(str(new))
        return ','.join(vals)

    def remap_condition_tokens(raw):
        mapped = []
        for token in (raw or '').split(','):
            token = (token or '').strip()
            if not token:
                continue
            negated = token.startswith('!')
            base = token[1:] if negated else token
            mapped_base = base
            if base.startswith('severity:') or base.startswith('data_type:'):
                prefix_name, raw_id = base.split(':', 1)
                try:
                    new_id = label_map.get(int(raw_id))
                except Exception:
                    new_id = None
                if not new_id:
                    continue
                mapped_base = f'{prefix_name}:{new_id}'
            mapped_token = f'!{mapped_base}' if negated else mapped_base
            if mapped_token not in mapped:
                mapped.append(mapped_token)
        return ','.join(mapped)

    for src in IncidentWorkflowStep.query.filter_by(tenant_id=source_tenant_id).order_by(IncidentWorkflowStep.position, IncidentWorkflowStep.id).all():
        dest_category_id = label_map.get(src.category_id) if src.category_id else None
        dest_action_label_id = label_map.get(src.action_label_id)
        if not dest_action_label_id:
            continue
        dest_conditions = remap_condition_tokens(src.conditions)
        existing = IncidentWorkflowStep.query.filter_by(
            tenant_id=dest_tenant_id,
            category_id=dest_category_id,
            action_label_id=dest_action_label_id,
            position=src.position,
            step_type=src.step_type,
            description=src.description,
        ).first()
        if existing:
            existing.personal_data_only = src.personal_data_only
            existing.required = src.required
            existing.requires_notification = src.requires_notification
            existing.required_notification_type = src.required_notification_type
            existing.document_generation_enabled = src.document_generation_enabled
            existing.document_template_name = src.document_template_name
            existing.conditions = dest_conditions
        else:
            db.session.add(IncidentWorkflowStep(
                tenant_id=dest_tenant_id,
                category_id=dest_category_id,
                action_label_id=dest_action_label_id,
                position=src.position, description=src.description, personal_data_only=src.personal_data_only,
                required=src.required, requires_notification=src.requires_notification,
                required_notification_type=src.required_notification_type,
                document_generation_enabled=src.document_generation_enabled,
                document_template_name=src.document_template_name,
                conditions=dest_conditions, step_type=src.step_type,
            ))

    for src in NotificationType.query.filter_by(tenant_id=source_tenant_id).order_by(NotificationType.id).all():
        _copy_notification_type_to_tenant(src, dest_tenant_id)

    for src in NotificationTemplate.query.filter_by(tenant_id=source_tenant_id).order_by(NotificationTemplate.id).all():
        _copy_notification_template_to_tenant(src, dest_tenant_id, label_map)

    for src in IncidentTemplate.query.filter_by(tenant_id=source_tenant_id).order_by(IncidentTemplate.id).all():
        values = dict(
            description=src.description, incident_name=src.incident_name, reference=src.reference, recipient=src.recipient,
            recipient_email=src.recipient_email, incident_description=src.incident_description,
            severity_id=label_map.get(src.severity_id), personal_data=src.personal_data,
            data_subjects_count=src.data_subjects_count, data_volume=src.data_volume,
            status=src.status, category_ids=remap_csv(src.category_ids, label_map),
            data_type_ids=remap_csv(src.data_type_ids, label_map), people_ids=remap_csv(src.people_ids, person_map),
            recommendation_ids=remap_csv(src.recommendation_ids, rec_map),
        )
        existing = IncidentTemplate.query.filter_by(tenant_id=dest_tenant_id, name=src.name).first()
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.session.add(IncidentTemplate(tenant_id=dest_tenant_id, name=src.name, **values))

    for src in ExternalRecipient.query.filter_by(tenant_id=source_tenant_id).order_by(ExternalRecipient.id).all():
        _copy_external_recipient_to_tenant(src, dest_tenant_id)

    for src in BackupJob.query.filter_by(tenant_id=source_tenant_id).order_by(BackupJob.id).all():
        _copy_backup_job_to_tenant(src, dest_tenant_id)

    deduplicate_config_labels_for_tenant(dest_tenant_id)



@bp.route('/admin/tenants', methods=['GET', 'POST'])
@login_required
def admin_tenants():
    if not is_superuser():
        flash('La gestione dei tenant è riservata ai superuser.', 'danger')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        action = request.form.get('action') or 'create'
        if action == 'create':
            name = validate_text_field((request.form.get('name') or '').strip(), 'Nome tenant', 80, required=True, allow_multiline=False)
            description = validate_text_field(request.form.get('description') or '', 'Descrizione tenant', 2000)
            if name.strip().lower() == 'default':
                flash('Il tenant default esiste già.', 'warning')
                return redirect(url_for('main.admin_tenants'))
            source_id = request.form.get('clone_from_tenant_id', type=int) or current_tenant_id() or default_tenant().id
            source = tenant_or_404(source_id)
            # Protegge anche la PK tenant quando il DB deriva da un restore
            # legacy con sequence non allineate.
            align_all_table_sequences()
            tenant = Tenant(name=name, description=description)
            db.session.add(tenant); db.session.flush()
            clone_tenant_config(source.id, tenant.id)
            audit_log('admin:tenant_create', {'tenant_id': tenant.id, 'name': tenant.name, 'cloned_from': source.id}, actor_type='user')
            commit_with_sequence_retry(['tenant', 'config_label', 'person', 'recommendation', 'incident_workflow_step', 'notification_type', 'notification_template', 'incident_template', 'external_recipient', 'backup_job', 'audit_log'])
            flash('Tenant creato e configurazione clonata.', 'success')
            return redirect(url_for('main.admin_tenants'))
        if action == 'update':
            tenant = tenant_or_404(request.form.get('tenant_id', type=int))
            if tenant.is_default:
                tenant.description = validate_text_field(request.form.get('description') or '', 'Descrizione tenant', 2000)
            else:
                tenant.name = validate_text_field((request.form.get('name') or '').strip(), 'Nome tenant', 80, required=True, allow_multiline=False)
                tenant.description = validate_text_field(request.form.get('description') or '', 'Descrizione tenant', 2000)
            audit_log('admin:tenant_update', {'tenant_id': tenant.id, 'name': tenant.name}, actor_type='user')
            db.session.commit(); flash('Tenant aggiornato.', 'success')
            return redirect(url_for('main.admin_tenants'))
        if action == 'delete':
            tenant = tenant_or_404(request.form.get('tenant_id', type=int))
            if tenant.is_default:
                flash('Il tenant default non può essere eliminato.', 'danger')
                return redirect(url_for('main.admin_tenants'))
            if UserTenantRole.query.filter_by(tenant_id=tenant.id).first() or User.query.filter_by(tenant_id=tenant.id).first() or Incident.query.filter_by(tenant_id=tenant.id).first():
                flash('Impossibile eliminare un tenant con utenti, membership o incidenti associati.', 'danger')
                return redirect(url_for('main.admin_tenants'))
            deleted_tenant_id = tenant.id
            name = tenant.name
            if session.get('active_tenant_id') == deleted_tenant_id:
                session['active_tenant_id'] = default_tenant().id
            audit_log('admin:tenant_delete', {'tenant_id': deleted_tenant_id, 'name': name}, actor_type='user')
            fallback_tenant_id = default_tenant().id
            User.query.filter(User.default_tenant_id == deleted_tenant_id).update({'default_tenant_id': fallback_tenant_id}, synchronize_session=False)
            User.query.filter(User.tenant_id == deleted_tenant_id).update({'tenant_id': fallback_tenant_id}, synchronize_session=False)
            # Delete dependent rows before ConfigLabel: templates, workflow steps and
            # notification templates contain foreign keys to tenant-local labels.
            for model in [IncidentTemplate, IncidentWorkflowStep, NotificationTemplate, NotificationType, Person, Recommendation, ExternalRecipient, BackupJob, AIChatbotDocument, AuditLog, ConfigLabel]:
                model.query.filter_by(tenant_id=deleted_tenant_id).delete(synchronize_session=False)
            Setting.query.filter(Setting.key.startswith(f'tenant:{deleted_tenant_id}:')).delete(synchronize_session=False)
            db.session.delete(tenant)
            db.session.commit(); flash('Tenant eliminato.', 'success')
            return redirect(url_for('main.admin_tenants'))
    tenants = Tenant.query.order_by(Tenant.name).all()
    return render_template('admin_tenants.html', tenants=tenants, active_tenant_id=current_tenant_id(), tenant_scoped_admin_areas=TENANT_SCOPED_ADMIN_AREAS, tenant_shared_admin_areas=TENANT_SHARED_ADMIN_AREAS)

@bp.route('/admin/tenants/active', methods=['POST'])
@login_required
def admin_tenant_activate():
    tenant = tenant_or_404(request.form.get('active_tenant_id', type=int))
    accessible = user_accessible_tenant_ids()
    if accessible is not None and tenant.id not in accessible:
        flash('Tenant non disponibile per l’utente corrente.', 'danger')
        return redirect(url_for('main.index'))
    session['active_tenant_id'] = int(tenant.id)
    session['active_tenant_scope_enabled'] = True
    session.modified = True
    # Lo switch è una scelta di sessione, non un aggiornamento del default
    # persistente. Tutte le query UI leggono current_tenant_id(), quindi dopo
    # il redirect la vista mostra immediatamente il tenant selezionato.
    audit_log('admin:tenant_activate', {'tenant_id': tenant.id, 'name': tenant.name}, actor_type='user', commit=True)
    flash(f'Tenant attivo impostato su {tenant.name}.', 'success')
    next_url = request.form.get('next') or request.referrer or url_for('main.index')
    if not str(next_url).startswith('/') or str(next_url).startswith('//'):
        next_url = url_for('main.index')
    return redirect(next_url, code=303)

def _admin_users_redirect(open_user_id=None, status_code=303):
    """Redirect back to Admin → Utenti preserving filters, scroll and open card."""
    raw_query = request.form.get('return_query') if request.method == 'POST' else request.query_string.decode('utf-8', errors='ignore')
    params = {}
    for key, value in parse_qsl(raw_query or '', keep_blank_values=False):
        if key not in {'open_user'}:
            params[key] = value
    if open_user_id:
        params['open_user'] = str(int(open_user_id))
    target = url_for('main.admin_users', **params)
    if open_user_id:
        target += f'#user-card-{int(open_user_id)}'
    return redirect(target, code=status_code)


@bp.route('/admin/users',methods=['GET','POST'])
@login_required
def admin_users():
    if not can_admin(): return redirect(url_for('main.index'))
    auth_provider_labels = user_auth_provider_labels()
    valid_backends = set(auth_provider_labels.keys())
    if request.method=='POST':
        backend=(request.form.get('auth_provider') or 'local').strip()
        if backend not in valid_backends:
            flash('Backend di autenticazione non valido o profilo SSO non più configurato.', 'error')
            return _admin_users_redirect()
        is_ldap = backend == 'ldap'
        username = validate_text_field(request.form['username'].strip(), 'Username', 80, required=True, allow_multiline=False)
        email = validate_email_field(request.form.get('email'), 'Email')
        name = validate_text_field(request.form.get('name') or '', 'Nome', 160, allow_multiline=False)
        role = request.form.get('role')
        allowed_roles = ['admin','operator','reader','writer','disabled'] + (['superuser'] if is_superuser() else [])
        if role not in allowed_roles:
            role = 'disabled'
        tenant_id = request.form.get('tenant_id', type=int) if is_superuser() else current_tenant_id()
        if not tenant_id:
            tenant_id = current_tenant_id()
        tenant_or_404(tenant_id)
        password = request.form.get('password') or ''
        if backend == 'local':
            try:
                validate_password_strength(password, username=username, email=email)
            except ValueError as exc:
                flash(str(exc), 'error')
                return _admin_users_redirect()
        if User.query.filter_by(username=username, auth_provider=backend).first():
            flash('Esiste già un utente con la stessa combinazione username + backend.', 'error')
            return _admin_users_redirect()
        try:
            align_table_sequence('user')
        except Exception:
            current_app.logger.exception('Riallineamento sequenza user non completato prima della creazione utente')
        u=User(username=username,name=name,email=email,role='disabled',tenant_id=tenant_id,default_tenant_id=tenant_id,is_ldap=is_ldap,auth_provider=backend,password_hash=hash_password(password) if backend == 'local' else None)
        db.session.add(u)
        db.session.flush()
        upsert_user_tenant_role(u, tenant_id, role)
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            if 'user_pkey' not in str(exc):
                raise
            current_app.logger.warning('Sequence user disallineata; riallineo e riprovo la creazione utente')
            align_table_sequence('user')
            u=User(username=username,name=name,email=email,role='disabled',tenant_id=tenant_id,default_tenant_id=tenant_id,is_ldap=is_ldap,auth_provider=backend,password_hash=hash_password(password) if backend == 'local' else None)
            db.session.add(u)
            db.session.flush()
            upsert_user_tenant_role(u, tenant_id, role)
            db.session.commit()
        sync_user_legacy_identity(u)
        audit_log('admin:user_create', {'user_id': u.id, 'username': u.username, 'role': user_role_for_tenant(u, tenant_id), 'tenant_id': tenant_id, 'auth_provider': u.auth_provider}, actor_type='user', commit=True)
        flash('Utente aggiunto.')
    search_query=(request.args.get('q') or '').strip()  # compatibilita' con vecchia ricerca unica
    user_search_username=(request.args.get('username') or '').strip()
    user_search_name=(request.args.get('name') or '').strip()
    user_search_email=(request.args.get('email') or '').strip()
    user_search_auth_provider=(request.args.get('auth_provider') or '').strip()
    user_search_role=(request.args.get('role') or '').strip()
    user_search_tenant_id = request.args.get('tenant_id', type=int)
    tenants = Tenant.query.order_by(Tenant.name).all()
    searchable_tenants = tenants if is_superuser() else [t for t in tenants if t.id == current_tenant_id()]
    role_options=(['superuser','admin','operator','reader','writer','disabled'] if is_superuser() else ['admin','operator','reader','writer','disabled'])
    if user_search_auth_provider and user_search_auth_provider not in valid_backends:
        user_search_auth_provider = ''
    if user_search_role and user_search_role not in role_options:
        user_search_role = ''
    if not is_superuser() and user_search_tenant_id and user_search_tenant_id != current_tenant_id():
        user_search_tenant_id = current_tenant_id()
    q=manageable_user_query()
    if search_query:
        pattern=f'%{search_query}%'
        q=q.filter(or_(User.username.ilike(pattern), User.name.ilike(pattern), User.email.ilike(pattern), User.auth_provider.ilike(pattern)))
    if user_search_username:
        q=q.filter(User.username.ilike(f'%{user_search_username}%'))
    if user_search_name:
        q=q.filter(User.name.ilike(f'%{user_search_name}%'))
    if user_search_email:
        q=q.filter(User.email.ilike(f'%{user_search_email}%'))
    if user_search_auth_provider:
        q=q.filter(User.auth_provider == user_search_auth_provider)
    if user_search_tenant_id:
        tenant_or_404(user_search_tenant_id)
    if user_search_tenant_id or user_search_role:
        member_filters=[]
        if user_search_tenant_id:
            member_filters.append(UserTenantRole.tenant_id == user_search_tenant_id)
        if user_search_role:
            member_filters.append(UserTenantRole.role == user_search_role)
        elif user_search_tenant_id:
            member_filters.append(UserTenantRole.role != 'disabled')
        member_ids = db.session.query(UserTenantRole.user_id).filter(*member_filters)
        if user_search_role == 'superuser' and not user_search_tenant_id:
            q = q.filter(or_(User.id.in_(member_ids), User.role == 'superuser', and_(User.username == 'admin', User.auth_provider == 'local')))
        elif user_search_role and not user_search_tenant_id:
            q = q.filter(or_(User.id.in_(member_ids), User.role == user_search_role))
        else:
            q = q.filter(User.id.in_(member_ids))
    users = q.order_by(User.username, User.auth_provider).all()
    user_search_filters = {
        'q': search_query,
        'username': user_search_username,
        'name': user_search_name,
        'email': user_search_email,
        'auth_provider': user_search_auth_provider,
        'role': user_search_role,
        'tenant_id': user_search_tenant_id,
    }
    user_search_active = any(v for v in user_search_filters.values())
    return render_template('admin_users.html', users=users, auth_provider_labels=auth_provider_labels, auth_provider_display=user_auth_provider_display, search_query=search_query, user_search_filters=user_search_filters, user_search_active=user_search_active, open_user_id=request.args.get('open_user', type=int), user_search_tenant_id=user_search_tenant_id, searchable_tenants=searchable_tenants, tenants=tenants, role_options=role_options, current_tenant_id=current_tenant_id(), user_membership_summary=user_membership_summary, user_default_tenant_options=user_default_tenant_options, user_role_for_tenant=user_role_for_tenant)
@bp.route('/admin/user/<int:uid>/role',methods=['POST'])
@login_required
def user_role(uid):
    if not can_admin():
        return redirect(url_for('main.index'))
    u=manageable_user_or_404(uid)
    u.email = validate_email_field(request.form.get('email'), 'Email')
    requested_default_tenant_id = request.form.get('default_tenant_id', type=int)
    if requested_default_tenant_id and not is_superuser() and requested_default_tenant_id != current_tenant_id():
        abort(403)
    if u.is_builtin_admin:
        # L'account locale admin è sempre superuser globale e non ha ruoli o
        # tenant modificabili dalla gestione utenti. Consentiamo solo la
        # manutenzione dei dati non autorizzativi, come l'email.
        u.role = 'superuser'
        u.default_tenant_id = None
        if not u.tenant_id:
            u.tenant_id = default_tenant().id
        db.session.commit()
        audit_log('admin:user_update', {'user_id': u.id, 'username': u.username, 'role': u.role, 'locked_builtin_admin': True}, actor_type='user', commit=True)
        flash('Dati account aggiornati. L’utente admin resta superuser globale.')
        return _admin_users_redirect(u.id)
    if requested_default_tenant_id:
        if not set_user_default_tenant(u, requested_default_tenant_id):
            flash('Tenant attivo predefinito non valido per le membership dell’utente.', 'error')
            return _admin_users_redirect(u.id)
    elif not getattr(u, 'default_tenant_id', None):
        active_membership = next((m for m in (u.tenant_roles or []) if m.normalized_role() != 'disabled'), None)
        if active_membership:
            u.default_tenant_id = active_membership.tenant_id
    sync_user_legacy_identity(u)
    db.session.commit()
    audit_log('admin:user_update', {'user_id': u.id, 'username': u.username, 'default_tenant_id': u.default_tenant_id, 'effective_role': user_role_for_tenant(u, u.default_tenant_id)}, actor_type='user', commit=True)
    flash('Utente aggiornato.')
    return _admin_users_redirect(u.id)

@bp.route('/admin/user/<int:uid>/tenant-role', methods=['POST'])
@login_required
def admin_user_tenant_role(uid):
    if not can_admin():
        return redirect(url_for('main.index'))
    user = manageable_user_or_404(uid) if not is_superuser() else (db.session.get(User, uid) or abort(404))
    if user.is_builtin_admin:
        flash('L’utente admin è sempre superuser globale: tenant e ruoli tenant-specifici non sono modificabili.', 'warning')
        return _admin_users_redirect()
    role = request.form.get('tenant_role') or 'disabled'
    allowed_roles = ['admin','operator','reader','writer','disabled'] + (['superuser'] if is_superuser() else [])
    if role not in allowed_roles:
        role = 'disabled'
    tenant_id = request.form.get('membership_tenant_id', type=int) if is_superuser() else current_tenant_id()
    tenant_or_404(tenant_id)
    if not is_superuser() and user_role_for_tenant(current_user, tenant_id) != 'admin':
        abort(403)
    upsert_user_tenant_role(user, tenant_id, role)
    if role != 'disabled' and not getattr(user, 'default_tenant_id', None):
        user.default_tenant_id = tenant_id
    if role == 'disabled' and getattr(user, 'default_tenant_id', None) == tenant_id:
        user.default_tenant_id = None
    db.session.commit()
    audit_log('admin:user_tenant_role_update', {'user_id': user.id, 'username': user.username, 'tenant_id': tenant_id, 'role': role}, actor_type='user', commit=True)
    flash('Ruolo tenant aggiornato.')
    return _admin_users_redirect(user.id)


@bp.route('/admin/user/<int:uid>/tenant-role/delete', methods=['POST'])
@login_required
def admin_user_tenant_role_delete(uid):
    if not can_admin():
        return redirect(url_for('main.index'))
    user = manageable_user_or_404(uid) if not is_superuser() else (db.session.get(User, uid) or abort(404))
    tenant_id = request.form.get('membership_tenant_id', type=int) if is_superuser() else current_tenant_id()
    tenant_or_404(tenant_id)
    if user.id == current_user.id and not is_superuser():
        flash('Non è possibile rimuovere la propria membership amministrativa nel tenant attivo.', 'error')
        return _admin_users_redirect()
    if user.is_builtin_admin:
        flash('L’utente admin è sempre superuser globale: tenant e ruoli tenant-specifici non sono rimovibili.', 'warning')
        return _admin_users_redirect()
    remove_user_tenant_role(user, tenant_id)
    if getattr(user, 'default_tenant_id', None) == tenant_id:
        remaining_active = [m for m in user.tenant_roles if m.tenant_id != tenant_id and m.normalized_role() != 'disabled']
        user.default_tenant_id = remaining_active[0].tenant_id if remaining_active else None
    sync_user_legacy_identity(user)
    db.session.commit()
    audit_log('admin:user_tenant_role_delete', {'user_id': user.id, 'username': user.username, 'tenant_id': tenant_id}, actor_type='user', commit=True)
    flash('Membership tenant rimossa.')
    return _admin_users_redirect(user.id)


@bp.route('/admin/user/<int:uid>/password', methods=['POST'])
@login_required
def admin_user_password(uid):
    if not is_superuser():
        abort(403)
    user = db.session.get(User, uid) or abort(404)
    provider = user.auth_provider or ('ldap' if user.is_ldap else 'local')
    if user.is_ldap or provider != 'local':
        flash('La password può essere modificata solo per utenti con login locale.', 'error')
        return _admin_users_redirect(user.id)
    new_password = request.form.get('new_password') or ''
    new_password2 = request.form.get('new_password2') or ''
    if new_password != new_password2:
        flash('Le password non coincidono.', 'error')
        return _admin_users_redirect(user.id)
    try:
        validate_password_strength(new_password, username=user.username, email=user.email)
    except ValueError as exc:
        flash(str(exc), 'error')
        return _admin_users_redirect(user.id)
    user.password_hash = hash_password(new_password)
    db.session.commit()
    audit_log('admin:user_password_change', {'user_id': user.id, 'username': user.username, 'by': current_user.username}, actor_type='user', commit=True)
    flash(f'Password locale aggiornata per {user.username}.')
    return _admin_users_redirect(user.id)


@bp.route('/admin/user/<int:uid>/delete',methods=['POST'])
@login_required
def admin_user_delete(uid):
    if not can_admin(): return redirect(url_for('main.index'))
    user=manageable_user_or_404(uid)
    if user.id == current_user.id:
        flash('Non è possibile rimuovere il proprio utente amministratore durante la sessione corrente.', 'error')
        return _admin_users_redirect()
    if is_superuser():
        remaining_admins=[candidate for candidate in User.query.filter(User.id!=user.id).all() if candidate.is_global_superuser]
        if user.is_global_superuser and not remaining_admins:
            flash('Non è possibile rimuovere l’ultimo superuser dell’applicazione.', 'error')
            return _admin_users_redirect()
    else:
        tid = current_tenant_id()
        remaining_admins = UserTenantRole.query.filter(UserTenantRole.tenant_id == tid, UserTenantRole.role == 'admin', UserTenantRole.user_id != user.id).count()
        if user_role_for_tenant(user, tid) == 'admin' and remaining_admins < 1:
            flash('Non è possibile rimuovere l’ultimo admin del tenant attivo.', 'error')
            return _admin_users_redirect()
    username=user.username
    auth_provider=user.auth_provider or ('ldap' if user.is_ldap else 'local')
    # Conserva la storia operativa: incidenti, promemoria e audit restano presenti,
    # ma i riferimenti FK all’account rimosso vengono svincolati prima della delete.
    Incident.query.filter_by(creator_id=user.id).update({'creator_id': None}, synchronize_session=False)
    IncidentReminder.query.filter_by(created_by_id=user.id).update({'created_by_id': None}, synchronize_session=False)
    AuditLog.query.filter_by(user_id=user.id).update({'user_id': None}, synchronize_session=False)
    UserTenantRole.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.delete(user)
    db.session.commit()
    audit_log('admin:user_delete', {'deleted_user_id': uid, 'username': username}, actor_type='user', commit=True)
    flash(f'Utente {username} ({auth_provider}) rimosso. La cronologia degli incidenti e dell’audit è stata conservata.')
    return _admin_users_redirect()
@bp.route('/settings/password',methods=['GET','POST'])
@login_required
def change_password():
    if current_user.is_ldap or getattr(current_user, 'auth_provider', 'local') != 'local': flash('Cambio password disponibile solo per utenti con login locale','error'); return redirect(url_for('main.index'))
    if request.method=='POST':
        if request.form['new_password']!=request.form['new_password2']: flash('Le password non coincidono','error')
        elif not verify_password(current_user.password_hash,request.form['old_password']): flash('Password attuale errata','error')
        else:
            try:
                validate_password_strength(request.form['new_password'], username=current_user.username, email=current_user.email)
            except ValueError as exc:
                flash(str(exc), 'error')
                return render_template('change_password.html')
            current_user.password_hash=hash_password(request.form['new_password']); db.session.commit(); audit_log('security:password_change', {'username': current_user.username}, actor_type='user', commit=True); flash('Password aggiornata')
    return render_template('change_password.html')

@bp.route('/sso-logos/<path:filename>')
def sso_logo_asset(filename):
    """Serve i loghi SSO dallo storage persistente configurabile."""
    name = secure_filename(Path(filename).name)
    if not name or name != filename or Path(name).suffix.lower() not in {'.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        abort(404)
    return send_from_directory(sso_logo_storage_dir(), name)


def sso_logo_url(relative_path):
    """URL pubblico per un logo SSO salvato come relative_path sso/<file>."""
    rel = str(relative_path or '').strip().replace('\\', '/')
    if not rel.startswith('sso/') or '/' in rel[4:]:
        return ''
    return url_for('main.sso_logo_asset', filename=Path(rel).name)


@bp.route('/admin/sso',methods=['GET','POST'])
@login_required
def sso_settings_admin():
    if not can_admin(): return redirect(url_for('main.index'))
    profiles = sso_profiles(include_legacy=True)
    test_result = None
    selected_id = request.values.get('profile') or request.form.get('profile_id') or (profiles[0]['id'] if profiles else 'google')
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        profiles = sso_profiles(include_legacy=True)
        if action in ('add_google_example', 'add_generic_profile'):
            example = google_sso_example_profile() if action == 'add_google_example' else generic_sso_profile()
            ids = {p['id'] for p in profiles}
            base = example['id']; n = 2
            while example['id'] in ids:
                example['id'] = f'{base}-{n}'; n += 1
            profiles.append(example)
            save_sso_profiles(profiles); db.session.commit()
            if action == 'add_google_example':
                flash('Profilo SSO Google di esempio aggiunto. Compilare Client ID e Client secret prima di abilitarlo.')
            else:
                flash('Profilo SSO generico aggiunto. Compilare endpoint, Client ID e Client secret prima di abilitarlo.')
            return redirect(url_for('main.sso_settings_admin', profile=example['id']))
        if action == 'upload_sso_logo':
            try:
                uploaded_logo_path = save_sso_logo_upload(request.files.get('sso_logo_upload'))
                if uploaded_logo_path:
                    flash('Logo SSO caricato nello storage condiviso')
                else:
                    flash('Selezionare un file logo da caricare', 'error')
            except ValueError as exc:
                flash(str(exc), 'error')
            return redirect(url_for('main.sso_settings_admin', profile=selected_id))
        if action == 'delete_sso_logo':
            logo_path = request.form.get('sso_logo_path_to_delete', '')
            try:
                changed = delete_sso_logo_asset(logo_path)
                db.session.commit()
                if changed:
                    flash(f'Logo SSO rimosso dallo storage e sganciato da {changed} profili associati.')
                else:
                    flash('Logo SSO rimosso dallo storage.')
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), 'error')
            return redirect(url_for('main.sso_settings_admin', profile=selected_id))
        if action == 'delete_profile':
            delete_id = request.form.get('profile_id') or selected_id
            profiles = [p for p in profiles if p.get('id') != delete_id]
            save_sso_profiles(profiles); db.session.commit()
            flash('Profilo SSO eliminato')
            return redirect(url_for('main.sso_settings_admin'))
        posted = {
            'id': request.form.get('profile_id') or selected_id,
            'sso_enabled': '1' if request.form.get('sso_enabled') else '0',
            'sso_provider_name': request.form.get('sso_provider_name','SSO'),
            'sso_authorization_url': request.form.get('sso_authorization_url',''),
            'sso_token_url': request.form.get('sso_token_url',''),
            'sso_userinfo_url': request.form.get('sso_userinfo_url',''),
            'sso_client_id': request.form.get('sso_client_id',''),
            'sso_client_secret': request.form.get('sso_client_secret',''),
            'sso_scopes': request.form.get('sso_scopes','openid email profile'),
            'sso_username_claim': request.form.get('sso_username_claim','preferred_username'),
            'sso_email_claim': request.form.get('sso_email_claim','email'),
            'sso_name_claim': request.form.get('sso_name_claim','name'),
            'sso_subject_claim': request.form.get('sso_subject_claim','sub'),
            'sso_auto_create_users': '1' if request.form.get('sso_auto_create_users') else '0',
            'sso_default_role': request.form.get('sso_default_role','disabled'),
            'sso_logo_path': request.form.get('sso_logo_path') or request.form.get('existing_sso_logo_path',''),
        }
        posted = _normalize_sso_profile(posted, selected_id)
        if request.form.get('remove_sso_logo'):
            posted['sso_logo_path'] = ''

        selected_id = posted['id']
        replaced = False
        new_profiles = []
        for prof in profiles:
            if prof.get('id') == (request.form.get('original_profile_id') or posted['id']):
                new_profiles.append(posted); replaced = True
            else:
                new_profiles.append(prof)
        if not replaced:
            new_profiles.append(posted)
        profiles = new_profiles
        if test_result is not None and not test_result.get('success', True):
            pass
        elif action == 'test_connection':
            test_result = sso_test_configuration(posted)
            if test_result['success']:
                flash('Test configurazione SSO completato senza errori bloccanti')
            else:
                flash('Test configurazione SSO completato con criticità: verificare i dettagli', 'warning')
        else:
            save_sso_profiles(profiles); db.session.commit()
            flash('Profilo SSO salvato')
            return redirect(url_for('main.sso_settings_admin', profile=selected_id))
    profiles = sso_profiles(include_legacy=True)
    selected = None
    for prof in profiles:
        if prof.get('id') == selected_id:
            selected = prof; break
    if not selected:
        selected = google_sso_example_profile() if not profiles else profiles[0]
        selected_id = selected['id']
    return render_template('sso.html', settings=selected, profiles=profiles, callback_url=sso_callback_url(), test_result=test_result, google_example=google_sso_example_profile(), generic_example=generic_sso_profile(), sso_logos=list_sso_logo_assets())

@bp.route('/admin/ldap',methods=['GET','POST'])
@login_required
def ldap_settings():
    if not can_admin(): return redirect(url_for('main.index'))
    settings=setting_map()
    result=None
    def form_cfg():
        cfg=dict(settings)
        for k in ['ldap_uri','ldap_base_dn','ldap_bind_dn','ldap_bind_password','ldap_user_filter','ldap_incident_search_filter','ldap_incident_search_attributes','ldap_incident_reference_attribute','ldap_incident_email_attribute']:
            cfg[k]=request.form.get(k,cfg.get(k,''))
        return cfg
    if request.method=='POST':
        action=request.form.get('action','save')
        cfg=form_cfg()
        if action=='save':
            for k in ['ldap_uri','ldap_base_dn','ldap_bind_dn','ldap_bind_password','ldap_user_filter','ldap_incident_search_filter','ldap_incident_search_attributes','ldap_incident_reference_attribute','ldap_incident_email_attribute']:
                s=db.session.get(Setting, k) or Setting(key=k); s.value=store_setting_value(k, cfg.get(k,'')); db.session.merge(s)
            db.session.commit(); settings=cfg; flash('Parametri LDAP salvati')
        elif action=='test_connection':
            try:
                srv=Server(cfg.get('ldap_uri'),get_info=ALL,connect_timeout=5)
                bind_dn=cfg.get('ldap_bind_dn') or None; bind_pw=cfg.get('ldap_bind_password') or None
                with Connection(srv,user=bind_dn,password=bind_pw,auto_bind=True) as c:
                    result={'ok':True,'title':'Comunicazione LDAP riuscita','details':{'server':cfg.get('ldap_uri'),'bound':str(c.bound)}}
                flash('Test comunicazione LDAP riuscito','info')
            except Exception as exc:
                current_app.logger.exception('Test comunicazione LDAP fallito')
                result={'ok':False,'title':'Comunicazione LDAP fallita','error':str(exc)}
                flash(f'Test comunicazione LDAP fallito: {exc}','error')
            settings=cfg
        elif action=='search_uid':
            uid=request.form.get('test_uid','').strip()
            if not uid:
                flash('Inserire una uid da cercare','error'); result={'ok':False,'title':'Ricerca utente LDAP','error':'uid mancante'}
            else:
                try:
                    filt=make_ldap_search_filter(cfg.get('ldap_user_filter') or '(uid={uid})', uid)
                    srv=Server(cfg.get('ldap_uri'),get_info=ALL,connect_timeout=5)
                    bind_dn=cfg.get('ldap_bind_dn') or None; bind_pw=cfg.get('ldap_bind_password') or None
                    with Connection(srv,user=bind_dn,password=bind_pw,auto_bind=True) as c:
                        c.search(cfg.get('ldap_base_dn'),filt,attributes=['uid','cn','mail','displayName','givenName','sn'])
                        entries=[]
                        for e in c.entries:
                            attrs={}
                            for a in ['uid','cn','mail','displayName','givenName','sn']:
                                if hasattr(e,a): attrs[a]=str(getattr(e,a))
                            entries.append({'dn':e.entry_dn,'attributes':attrs})
                    result={'ok':True,'title':f'Risultati ricerca uid {uid}','filter':filt,'entries':entries}
                    if entries: flash(f'Trovati {len(entries)} utenti LDAP','info')
                    else: flash('Nessun utente LDAP trovato','error')
                except Exception as exc:
                    current_app.logger.exception('Ricerca uid LDAP fallita')
                    result={'ok':False,'title':'Ricerca utente LDAP fallita','error':str(exc)}
                    flash(f'Ricerca utente LDAP fallita: {exc}','error')
            settings=cfg
    return render_template('ldap.html',settings=settings,result=result)


NOTIFICATION_FIELDS = [
    ('%DATA%', 'Tipo di dati interessati nell’incidente'),
    ('%CATEGORIES%', 'Categorie dell’incidente'),
    ('%RISK_RIGHTS_FREEDOM%', 'Frase esplicativa sul rischio per diritti e libertà'),
    ('%REPORT%', 'Allega il report PDF aggiornato e inserisce un riferimento nel testo'),
    ('%STATISTICS%', 'Allega alla notifica il Report con le statistiche in formato PDF'),
    ('%NAME%', 'Nome dell’incidente'),
    ('%OPERATOR%', 'Nome dell’utente che invia la mail'),
    ('%START%', 'Data e ora di inizio dell’incidente'),
    ('%END%', 'Data e ora di fine dell’incidente, se disponibile'),
    ('%DESCRIPTION%', 'Descrizione dell’incidente'),
    ('%REFERENCE%', 'Campo riferimento dell’incidente'),
    ('%CREATOR%', 'Creatore dell’incidente'),
    ('%CREATOR_EMAIL%', 'Email del creatore dell’incidente'),
    ('%DOCUMENTS%', 'Documenti allegati all’incidente; richiede la selezione dei file da inviare'),
    ('%ACTIONS%', 'Lista cronologica delle azioni finora intraprese, con data e ora'),
    ('%STATUS%', 'Stato dell’incidente'),
    ('%EXTERNAL_URL%', 'URL esterna dell’applicazione configurata in Admin → Altre configurazioni'),
    ('%INCIDENT_URL%', 'Link diretto all’incidente'),
    ('%MEASURES_ADOPTED%', 'lista delle contromisure adottate finora nell’incidente'),
    ('%RECOMMENDATIONS%', 'lista delle raccomandazioni da fornire agli interessati, stesso valore del campo recommendations dei moduli'),
    ('%APP_INFO%', 'nome dell’applicazione e versione'),
    ('%SITE%', 'nome della struttura dove si è verificato l’incidente'),
    ('%RESP%', 'Nome responsabile configurato in Admin → Dati responsabile'),
    ('%RESP_EMAIL%', 'Email responsabile configurata in Admin → Dati responsabile'),
    ('%DIRECTOR%', 'Nome del titolare configurato in Admin → Dati titolare'),
    ('%DIRECTOR_ROLE%', 'Ruolo del titolare configurato in Admin → Dati titolare'),
]

DEFAULT_NOTIFICATION_SUBJECTS = {
    'user': 'Notifica incidente informatico: %NAME%',
    'csirt': 'Notifica CSIRT - Incidente: %NAME%',
    'dpo': 'Notifica DPO - Incidente: %NAME%',
}
DEFAULT_NOTIFICATION_BODIES = {
    'user': """Buongiorno,
si comunica che è stato registrato un incidente informatico relativo a: %NAME%.

Riferimento: %REFERENCE%
Stato: %STATUS%
Data e ora di inizio: %START%
Data e ora di fine: %END%
Dati interessati: %DATA%
Categorie: %CATEGORIES%
Rischio per diritti e libertà: %RISK_RIGHTS_FREEDOM%

Descrizione:
%DESCRIPTION%

Azioni finora intraprese:
%ACTIONS%

Link diretto incidente: %INCIDENT_URL%

Operatore: %OPERATOR%

Cordiali saluti""",
    'csirt': """Buongiorno,
si invia notifica allo CSIRT relativa al seguente incidente informatico.

Nome: %NAME%
Riferimento: %REFERENCE%
Stato: %STATUS%
Creatore: %CREATOR% <%CREATOR_EMAIL%>
Data e ora di inizio: %START%
Data e ora di fine: %END%
Dati interessati: %DATA%
Categorie: %CATEGORIES%
Rischio per diritti e libertà: %RISK_RIGHTS_FREEDOM%

Descrizione:
%DESCRIPTION%

Azioni finora intraprese:
%ACTIONS%

Report aggiornato: %REPORT%
Documenti allegati: %DOCUMENTS%

Link diretto incidente: %INCIDENT_URL%

Notifica inviata da: %OPERATOR%""",
    'dpo': """Buongiorno,
si invia notifica al DPO relativa al seguente incidente informatico.

Nome: %NAME%
Riferimento: %REFERENCE%
Stato: %STATUS%
Creatore: %CREATOR% <%CREATOR_EMAIL%>
Data e ora di inizio: %START%
Data e ora di fine: %END%
Dati interessati: %DATA%
Categorie: %CATEGORIES%
Rischio per diritti e libertà: %RISK_RIGHTS_FREEDOM%

Descrizione:
%DESCRIPTION%

Azioni finora intraprese:
%ACTIONS%

Report aggiornato: %REPORT%
Documenti allegati: %DOCUMENTS%

Link diretto incidente: %INCIDENT_URL%

Notifica inviata da: %OPERATOR%""",
}

DEFAULT_TEMPLATE_NAMES = {'user':'Esempio notifica utente','csirt':'Esempio notifica CSIRT','dpo':'Esempio notifica DPO'}

def default_notification_type_description(label, code=None):
    code = (code or '').strip().lower()
    defaults = {
        'csirt': 'Notifiche destinate allo CSIRT.',
        'dpo': 'Notifiche destinate al DPO.',
        'user': 'Notifiche formali ad utenti a seguito di gravi violazioni su diritti e libertà',
    }
    if code in defaults:
        return defaults[code]
    label = (label or code or 'tipo di notifica').strip()
    return f'Tag di notifica {label}: associa documenti, template e workflow collegati a questo tipo di comunicazione.'


def notification_type_records(enabled_only=True):
    q = tenant_query(NotificationType)
    if enabled_only:
        q = q.filter_by(enabled=True)
    return q.order_by(NotificationType.label).all()

def notification_type_map(enabled_only=True):
    rows = notification_type_records(enabled_only=enabled_only)
    if not rows:
        return {'user':'Notifica utente','csirt':'Notifica CSIRT','dpo':'Notifica DPO'}
    return {t.code: t.label for t in rows}

def get_notification_type(kind):
    t = tenant_query(NotificationType).filter_by(code=kind).first()
    if t:
        return t
    # fallback compatibile con database precedenti
    fallback = {
        'user': ('Notifica utente','manual','',''),
        'csirt': ('Notifica CSIRT','manual','',''),
        'dpo': ('Notifica DPO','manual','',''),
    }
    label, mode, recip_key, cc_key = fallback.get(kind, (kind, 'manual', '', ''))
    t = NotificationType(code=kind, label=label, description=default_notification_type_description(label, kind), recipient_mode=mode, recipient_setting_key=recip_key, cc_setting_key=cc_key, enabled=True)
    db.session.add(t); db.session.commit()
    return t


INCIDENT_DETAIL_SECTIONS = [
    ('incident-main', 'Dati generali incidente'),
    ('incident-workflow', 'Fasi procedurali'),
    ('incident-procedural-alerts', 'Avvisi procedurali'),
    ('incident-actions', 'Azioni'),
    ('incident-reminders', 'Promemoria'),
    ('incident-documents', 'Documenti'),
    ('incident-forms', 'Moduli'),
    ('incident-notifications', 'Notifiche'),
]

INCIDENT_BUTTON_ACTIONS = [
    ('incident_update', 'Salva dati incidente'),
    ('action_add', 'Salva nuova azione'),
    ('action_update', 'Salva modifiche azione'),
    ('reminder_add', 'Aggiungi promemoria'),
    ('reminder_update', 'Salva promemoria'),
    ('document_upload', 'Upload documenti'),
    ('forms_confirm', 'Conferma generazione documenti'),
    ('document_tags_save', 'Salva tag'),
    ('document_download', 'Scarica documenti'),
]
BUTTON_ACTIONS_SETTING = 'incident_button_action_labels_json'

INCIDENT_FORM_FIELDS = [
    ('template', 'Modello predefinito', False),
    ('name', 'Nome', True),
    ('external_recipient_lookup', 'Ricerca destinatari esterni', False),
    ('ldap_recipient_lookup', 'Ricerca utente via LDAP', False),
    ('reference', 'Riferimento', True),
    ('recipient', 'Destinatario', False),
    ('recipient_email', 'E-mail destinatario', False),
    ('description', 'Descrizione', False),
    ('severity', 'Gravità', False),
    ('status', 'Stato', False),
    ('start_date', 'Data inizio', True),
    ('start_time', 'Ora inizio', True),
    ('end_date', 'Data fine', False),
    ('end_time', 'Ora fine', False),
    ('personal_data', 'Rischio per diritti e libertà', False),
    ('data_subjects_count', 'Numero di interessati', False),
    ('data_volume', 'Volume dati', False),
    ('dnd_fields', 'Label, personale e raccomandazioni', False),
]

INCIDENT_DETAIL_VISIBILITY_FIELDS = [
    ('external_recipient_lookup', 'Ricerca destinatari esterni nella sezione Dati generali', False),
    ('ldap_recipient_lookup', 'Ricerca utente via LDAP nella sezione Dati generali', False),
    ('action_label', 'Label nella sezione Azioni', False),
]

_LEGACY_INCIDENT_FIELD_ALIASES = {
    'external_recipients': {'external_recipient_lookup', 'ldap_recipient_lookup'},
}


def incident_form_required_field_codes():
    return {code for code, _label, required in INCIDENT_FORM_FIELDS if required}


def _expand_incident_field_codes(raw, allowed_codes):
    visible = set()
    for item in (raw or '').split(','):
        code = item.strip()
        if code in allowed_codes:
            visible.add(code)
        elif code in _LEGACY_INCIDENT_FIELD_ALIASES:
            visible.update(_LEGACY_INCIDENT_FIELD_ALIASES[code] & set(allowed_codes))
    return visible


def incident_form_visible_fields():
    raw = setting_value('incident_form_default_visible_fields', '')
    all_codes = [code for code, _label, _required in INCIDENT_FORM_FIELDS]
    if not raw:
        return set(all_codes)
    visible = _expand_incident_field_codes(raw, all_codes)
    return visible | incident_form_required_field_codes()


def incident_detail_visibility_field_records():
    records = list(INCIDENT_DETAIL_VISIBILITY_FIELDS)
    for field in incident_custom_field_definitions():
        if field.get('enabled', True):
            records.append((f"custom:{field['code']}", f"Campo personalizzato: {field['label']}", False))
    return records


def incident_detail_general_visible_fields():
    setting = db.session.get(Setting, 'incident_detail_general_visible_fields')
    all_codes = [code for code, _label, _required in incident_detail_visibility_field_records()]
    if setting is None:
        return {code for code in all_codes if code != 'action_label'}
    raw = decrypt_setting_value('incident_detail_general_visible_fields', setting.value) if setting.value is not None else ''
    return _expand_incident_field_codes(raw, all_codes)


def visible_custom_incident_field_definitions():
    visible = incident_detail_general_visible_fields()
    return [field for field in incident_custom_field_definitions() if field.get('enabled', True) and f"custom:{field['code']}" in visible]




CUSTOM_INCIDENT_FIELDS_SETTING = 'incident_general_custom_fields_json'
CUSTOM_INCIDENT_FIELD_TYPES = [
    ('text', 'Testo'),
    ('datetime', 'Data/ora'),
    ('secret', 'Nascosto con mostra in chiaro'),
    ('checkbox', 'Checkbox con descrizione'),
]


def _custom_incident_field_code(label, fallback='campo'):
    base = re.sub(r'[^a-z0-9_]+', '_', str(label or '').strip().lower()).strip('_') or fallback
    return base[:60]


def incident_custom_field_definitions():
    raw = setting_value(CUSTOM_INCIDENT_FIELDS_SETTING, '')
    try:
        data = json.loads(raw) if raw else []
    except Exception:
        data = []
    fields = []
    seen = set()
    for idx, item in enumerate(data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        label = str(item.get('label') or '').strip()
        if not label:
            continue
        code = _custom_incident_field_code(item.get('code') or label, f'campo_{idx+1}')
        base = code
        n = 2
        while code in seen:
            code = f'{base}_{n}'[:64]
            n += 1
        seen.add(code)
        field_type = str(item.get('type') or 'text').strip()
        if field_type not in {t[0] for t in CUSTOM_INCIDENT_FIELD_TYPES}:
            field_type = 'text'
        fields.append({
            'code': code,
            'label': label[:160],
            'type': field_type,
            'description': str(item.get('description') or '').strip()[:500],
            'enabled': bool(item.get('enabled', True)),
        })
    return fields


def save_incident_custom_field_definitions_from_form():
    labels = request.form.getlist('custom_field_label')
    types = request.form.getlist('custom_field_type')
    descriptions = request.form.getlist('custom_field_description')
    enabled_flags = request.form.getlist('custom_field_enabled')
    fields = []
    seen = set()
    allowed_types = {t[0] for t in CUSTOM_INCIDENT_FIELD_TYPES}
    for idx, label in enumerate(labels):
        label = (label or '').strip()
        if not label:
            continue
        field_type = (types[idx] if idx < len(types) else 'text') or 'text'
        if field_type not in allowed_types:
            field_type = 'text'
        desc = (descriptions[idx] if idx < len(descriptions) else '').strip()
        code = _custom_incident_field_code(label, f'campo_{idx+1}')
        base = code
        n = 2
        while code in seen:
            code = f'{base}_{n}'[:64]
            n += 1
        seen.add(code)
        fields.append({'code': code, 'label': label[:160], 'type': field_type, 'description': desc[:500], 'enabled': (not enabled_flags) or (str(idx) in enabled_flags)})
    set_setting_value(CUSTOM_INCIDENT_FIELDS_SETTING, json.dumps(fields, ensure_ascii=False))


def incident_custom_field_values(inc):
    raw = getattr(inc, 'custom_fields_json', '') or ''
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def update_incident_custom_field_values_from_form(inc):
    values = incident_custom_field_values(inc)
    for field in incident_custom_field_definitions():
        if not field.get('enabled', True):
            continue
        code = field['code']
        key = f'custom_{code}'
        if field['type'] == 'checkbox':
            values[code] = '1' if request.form.get(key) else ''
        else:
            values[code] = (request.form.get(key) or '').strip()
    inc.custom_fields_json = json.dumps(values, ensure_ascii=False)


def incident_ldap_lookup_enabled():
    return bool(setting_value('ldap_uri') and setting_value('ldap_base_dn'))

def app_info_label():
    info = current_app.config.get('APP_INFO', {}) if has_app_context() else {}
    name = info.get('name') or 'Cybersecurity Incident Registry'
    version = info.get('version') or ''
    build = info.get('build') or ''
    suffix = f" {version}" if version else ''
    if build:
        suffix += f" (build {build})"
    return f"{name}{suffix}"


def _valid_notification_tag_codes():
    return {nt.code for nt in notification_type_records(enabled_only=False)}


def _clean_button_action_tags(raw_tags):
    valid = _valid_notification_tag_codes()
    cleaned = []
    for tag in raw_tags or []:
        code = str(tag or '').strip()
        if code in valid and code not in cleaned:
            cleaned.append(code)
    return cleaned


def _valid_form_template_names():
    try:
        return {template.name for template in list_templates()}
    except Exception:
        current_app.logger.warning('Impossibile leggere la lista dei template per le azioni automatiche download documenti', exc_info=True)
        return set()


def _clean_button_action_template_name(value):
    template_name = Path(str(value or '').strip()).stem
    if not template_name:
        return ''
    valid = _valid_form_template_names()
    return template_name if template_name in valid else ''


def _normalise_button_action_entry(value, include_tags=False, include_template=False):
    scope = 'always'
    raw_label_id = value
    raw_tags = []
    raw_template_name = ''
    if isinstance(value, dict):
        raw_label_id = value.get('label_id')
        scope = _workflow_update_section_legacy_value(value.get('scope') or 'always', scope=True)
        raw_tags = value.get('notification_tags') or value.get('tags') or []
        raw_template_name = value.get('template_name') or value.get('generated_template_name') or ''
    try:
        label_id = int(raw_label_id)
    except (TypeError, ValueError):
        return None
    if scope not in {'always', WORKFLOW_UPDATE_SECTION_SCOPE}:
        scope = 'always'
    if not tenant_query(ConfigLabel).filter_by(id=label_id, kind='action_label').first():
        return None
    entry = {'label_id': label_id, 'scope': scope}
    if include_tags:
        entry['notification_tags'] = _clean_button_action_tags(raw_tags)
    if include_template:
        entry['template_name'] = _clean_button_action_template_name(raw_template_name)
    return entry


def _button_action_rule_key(entry):
    tags = tuple(sorted(entry.get('notification_tags') or []))
    return tags


def button_action_config():
    raw = setting_value(BUTTON_ACTIONS_SETTING, '{}')
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {}
    config = {}
    allowed = {code for code, _label in INCIDENT_BUTTON_ACTIONS}
    for code, value in (data or {}).items():
        if code not in allowed:
            continue
        if code == 'document_tags_save':
            raw_rules = value if isinstance(value, list) else [value]
            rules = []
            seen = set()
            used_tags = set()
            for raw_rule in raw_rules:
                entry = _normalise_button_action_entry(raw_rule, include_tags=True)
                if not entry or not entry.get('notification_tags'):
                    continue
                unique_tags = []
                for tag in entry.get('notification_tags') or []:
                    if tag in used_tags:
                        continue
                    unique_tags.append(tag)
                    used_tags.add(tag)
                entry['notification_tags'] = unique_tags
                if not entry['notification_tags']:
                    continue
                key = _button_action_rule_key(entry)
                if key in seen:
                    continue
                seen.add(key)
                rules.append(entry)
            if rules:
                config[code] = rules
            continue
        if code in {'document_upload', 'document_download'}:
            raw_rules = value if isinstance(value, list) else [value]
            rules = []
            seen = set()
            for raw_rule in raw_rules:
                entry = _normalise_button_action_entry(raw_rule, include_tags=(code == 'document_upload'), include_template=True)
                if not entry:
                    continue
                key = (entry.get('label_id'), entry.get('scope') or 'always', entry.get('template_name') or '', tuple(entry.get('notification_tags') or []))
                if key in seen:
                    continue
                seen.add(key)
                rules.append(entry)
            if rules:
                config[code] = rules
            continue
        if code == 'incident_update':
            raw_rules = value if isinstance(value, list) else [value]
            rules = []
            generic_added = False
            seen_workflow = set()
            for raw_rule in raw_rules:
                entry = _normalise_button_action_entry(raw_rule, include_tags=False, include_template=False)
                if not entry:
                    continue
                if (entry.get('scope') or 'always') == WORKFLOW_UPDATE_SECTION_SCOPE:
                    key = entry.get('label_id')
                    if key in seen_workflow:
                        continue
                    seen_workflow.add(key)
                    rules.append(entry)
                elif not generic_added:
                    entry['scope'] = 'always'
                    rules.insert(0, entry)
                    generic_added = True
            if rules:
                config[code] = rules if any((r.get('scope') == WORKFLOW_UPDATE_SECTION_SCOPE) for r in rules) else rules[0]
            continue
        entry = _normalise_button_action_entry(value, include_tags=False, include_template=False)
        if entry:
            config[code] = entry
    return config


def save_button_action_config(config):
    cleaned = {}
    allowed = {code for code, _label in INCIDENT_BUTTON_ACTIONS}
    for code, value in (config or {}).items():
        if code not in allowed:
            continue
        if code == 'document_tags_save':
            raw_rules = value if isinstance(value, list) else [value]
            rules = []
            seen = set()
            used_tags = set()
            for raw_rule in raw_rules:
                entry = _normalise_button_action_entry(raw_rule, include_tags=True)
                if not entry or not entry.get('notification_tags'):
                    continue
                unique_tags = []
                for tag in entry.get('notification_tags') or []:
                    if tag in used_tags:
                        continue
                    unique_tags.append(tag)
                    used_tags.add(tag)
                entry['notification_tags'] = unique_tags
                if not entry['notification_tags']:
                    continue
                key = _button_action_rule_key(entry)
                if key in seen:
                    continue
                seen.add(key)
                rules.append(entry)
            if rules:
                cleaned[code] = rules
            continue
        if code in {'document_upload', 'document_download'}:
            raw_rules = value if isinstance(value, list) else [value]
            rules = []
            seen = set()
            for raw_rule in raw_rules:
                entry = _normalise_button_action_entry(raw_rule, include_tags=(code == 'document_upload'), include_template=True)
                if not entry:
                    continue
                key = (entry.get('label_id'), entry.get('scope') or 'always', entry.get('template_name') or '', tuple(entry.get('notification_tags') or []))
                if key in seen:
                    continue
                seen.add(key)
                rules.append(entry)
            if rules:
                cleaned[code] = rules
            continue
        if code == 'incident_update':
            raw_rules = value if isinstance(value, list) else [value]
            rules = []
            generic_added = False
            seen_workflow = set()
            for raw_rule in raw_rules:
                entry = _normalise_button_action_entry(raw_rule, include_tags=False, include_template=False)
                if not entry:
                    continue
                if (entry.get('scope') or 'always') == WORKFLOW_UPDATE_SECTION_SCOPE:
                    key = entry.get('label_id')
                    if key in seen_workflow:
                        continue
                    seen_workflow.add(key)
                    rules.append(entry)
                elif not generic_added:
                    entry['scope'] = 'always'
                    rules.insert(0, entry)
                    generic_added = True
            if rules:
                cleaned[code] = rules if any((r.get('scope') == WORKFLOW_UPDATE_SECTION_SCOPE) for r in rules) else rules[0]
            continue
        entry = _normalise_button_action_entry(value, include_tags=False, include_template=False)
        if entry:
            cleaned[code] = entry
    set_setting_value(BUTTON_ACTIONS_SETTING, json.dumps(cleaned, ensure_ascii=False))


def automatic_button_action_allowed(config_entry):
    if not config_entry:
        return False
    scope = config_entry.get('scope') if isinstance(config_entry, dict) else 'always'
    if scope != WORKFLOW_UPDATE_SECTION_SCOPE:
        return True
    if not has_request_context():
        return False
    return (request.values.get('workflow_update_section_redirect') or '').strip() == '1'


def current_workflow_update_section_target():
    if not has_request_context():
        return ''
    if (request.values.get('workflow_update_section_redirect') or '').strip() != '1':
        return ''
    return (request.values.get('workflow_update_section_target') or '').strip()


def current_workflow_step_action_label_id():
    if not has_request_context():
        return None
    raw = (request.values.get('workflow_step_action_label_id') or '').strip()
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def workflow_document_download_template_constraints(inc):
    """Return workflow-enforced generated-template filters for document downloads.

    When an active workflow step is of type "Aggiorna sezione", targets the
    Documents section and is marked as a document-generation step with a specific
    template, that template is more specific than the generic automatic button
    action configuration.  In that case document-download automatic actions may
    run only for documents generated by one of those templates.
    """
    if not inc or not getattr(inc, 'id', None):
        return []
    templates = []
    for step in workflow_steps_for_incident(inc):
        if not workflow_step_type_uses_section_target(getattr(step, 'step_type', REGISTRATION_STEP_TYPE)):
            continue
        if (getattr(step, 'section_target', '') or '').strip() != 'incident-documents':
            continue
        if not bool(getattr(step, 'document_generation_enabled', False)):
            continue
        template_name = Path(str(getattr(step, 'document_template_name', '') or '').strip()).stem
        if template_name and template_name not in templates:
            templates.append(template_name)
    return templates


def current_workflow_document_template(inc):
    if not has_request_context():
        return ''
    if (request.values.get('workflow_update_section_redirect') or '').strip() != '1':
        return ''
    if (request.values.get('workflow_update_section_target') or '').strip() != 'incident-documents':
        return ''
    requested_template = Path(str(request.values.get('workflow_document_template') or '').strip()).stem
    if not requested_template:
        return ''
    return requested_template if requested_template in workflow_document_download_template_constraints(inc) else ''


def current_workflow_document_download_template(inc):
    return current_workflow_document_template(inc)


def document_button_action_rules(button_code):
    entry = button_action_config().get(button_code) or []
    return entry if isinstance(entry, list) else ([entry] if entry else [])


def document_download_action_rules():
    return document_button_action_rules('document_download')


def document_upload_action_rules():
    return document_button_action_rules('document_upload')


def document_download_rule_templates():
    return [Path(str(rule.get('template_name') or '').strip()).stem for rule in document_download_action_rules() if isinstance(rule, dict) and Path(str(rule.get('template_name') or '').strip()).stem]


def _matching_button_action_entries(button_code, context_tags=None, context_template=None, inc=None):
    config_entry = button_action_config().get(button_code)
    if not config_entry:
        return []
    if button_code in {'document_upload', 'document_download'}:
        current_template = Path(str(context_template or '').strip()).stem
        rules = config_entry if isinstance(config_entry, list) else [config_entry]
        workflow_template = current_workflow_document_template(inc)
        if workflow_template:
            if button_code == 'document_download' and current_template != workflow_template:
                return []
            for entry in rules:
                configured_template = Path(str((entry or {}).get('template_name') or '').strip()).stem
                if configured_template == workflow_template and automatic_button_action_allowed(entry):
                    return [entry]
            return []
        for entry in rules:
            if not Path(str((entry or {}).get('template_name') or '').strip()).stem and automatic_button_action_allowed(entry):
                return [entry]
        return []
    if button_code == 'incident_update':
        entries = config_entry if isinstance(config_entry, list) else [config_entry]
        from_workflow_general = current_workflow_update_section_target() == 'incident-main'
        if from_workflow_general:
            step_label_id = current_workflow_step_action_label_id()
            if not step_label_id:
                return []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if (entry.get('scope') or 'always') != WORKFLOW_UPDATE_SECTION_SCOPE:
                    continue
                try:
                    entry_label_id = int(entry.get('label_id') or 0)
                except (TypeError, ValueError):
                    entry_label_id = 0
                if entry_label_id == step_label_id and automatic_button_action_allowed(entry):
                    return [entry]
            return []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if (entry.get('scope') or 'always') != WORKFLOW_UPDATE_SECTION_SCOPE and automatic_button_action_allowed(entry):
                return [entry]
        return []
    if button_code != 'document_tags_save':
        return [config_entry] if automatic_button_action_allowed(config_entry) else []
    current_tags = set(context_tags or [])
    matches = []
    for entry in config_entry if isinstance(config_entry, list) else [config_entry]:
        if not automatic_button_action_allowed(entry):
            continue
        configured_tags = set((entry or {}).get('notification_tags') or [])
        if configured_tags and (configured_tags & current_tags):
            matches.append(entry)
    return matches


def _create_automatic_button_action(inc, button_code, config_entry, description=None):
    label_id = config_entry.get('label_id') if isinstance(config_entry, dict) else config_entry
    if not label_id:
        return None
    label = tenant_query(ConfigLabel).filter_by(id=label_id, kind='action_label').first()
    if not label:
        return None
    align_table_sequence('action')
    button_label = dict(INCIDENT_BUTTON_ACTIONS).get(button_code, button_code)
    action = Action(
        incident_id=inc.id,
        when_at=application_now(),
        person_name=getattr(current_user, 'name', None) or getattr(current_user, 'username', '') or 'Sistema',
        description=description or f"Azione automatica da pulsante: {button_label}.",
        consequence_text=None,
        label_id=label.id,
        exportable=action_exportable_default(label, description or button_label),
    )
    db.session.add(action)
    db.session.flush()
    close_incident_from_conclusion_action(inc.id, action)
    return action


def _apply_document_upload_rule_tags(config_entry, documents):
    if not documents or not config_entry or not current_workflow_document_template(getattr(documents[0], 'incident', None) or db.session.get(Incident, documents[0].incident_id)):
        return
    tags = [str(x or '').strip() for x in (config_entry.get('notification_tags') or []) if str(x or '').strip()]
    if not tags:
        return
    for doc in documents:
        current = list(getattr(doc, 'notification_tag_list', []) or [])
        changed = False
        for tag in tags:
            if tag not in current:
                current.append(tag); changed = True
        if changed:
            doc.set_notification_tags(current)


def add_automatic_button_action(inc, button_code, description=None, context_tags=None, context_template=None, context_documents=None):
    if not inc or not getattr(inc, 'id', None):
        return None
    matches = _matching_button_action_entries(button_code, context_tags=context_tags, context_template=context_template, inc=inc)
    if not matches:
        return None
    if button_code == 'document_upload':
        _apply_document_upload_rule_tags(matches[0], context_documents or [])
    actions = [_create_automatic_button_action(inc, button_code, entry, description=description) for entry in matches]
    actions = [action for action in actions if action is not None]
    if button_code == 'document_tags_save':
        return actions
    return actions[0] if actions else None

def notification_label_value(kind):
    if kind == 'csirt':
        return '04-comunicazione allo CSIRT'
    if kind == 'dpo':
        return '05-comunicazione al DPO'
    return '07-notifica all’utente'

def ensure_default_notification_templates():
    """Garantisce la presenza degli esempi predefiniti senza cancellare template utente.

    La funzione è intenzionalmente conservativa: non elimina mai template
    esistenti e non sovrascrive quelli creati/modificati dall'utente. A ogni
    avvio o accesso al menu verifica solo se manca il template di esempio per
    ciascun tipo di notifica; se manca lo crea. Se per un tipo non esiste alcun
    default, marca come default il template di esempio o, in mancanza, il primo
    template disponibile. Questo evita che i template aggiuntivi spariscano al
    riavvio del container.
    """
    for kind in ['user','csirt','dpo']:
        try:
            action_label = ConfigLabel.query.filter_by(kind='action_label', value=notification_label_value(kind)).first()
            tmpl = NotificationTemplate.query.filter_by(kind=kind, name=DEFAULT_TEMPLATE_NAMES[kind]).first()
            if not tmpl:
                tmpl = NotificationTemplate(
                    kind=kind,
                    name=DEFAULT_TEMPLATE_NAMES[kind],
                    subject=DEFAULT_NOTIFICATION_SUBJECTS[kind],
                    body=DEFAULT_NOTIFICATION_BODIES[kind],
                    action_label_id=action_label.id if action_label else None,
                    recipient_source='incident_recipient_email' if kind == 'user' else 'empty',
                    recipient_editable=True,
                    recipient_external_allowed=True,
                    cc_source='empty',
                    cc_editable=True,
                    cc_external_allowed=True,
                    is_default=False,
                )
                db.session.add(tmpl)
                db.session.flush()
            if not NotificationTemplate.query.filter_by(kind=kind, is_default=True).first():
                tmpl.is_default = True
        except IntegrityError:
            db.session.rollback()
            current_app.logger.info('Template di notifica predefinito già presente per kind=%s', kind)
        except (ProgrammingError, OperationalError):
            db.session.rollback()
            current_app.logger.exception('Tabella NotificationTemplate non disponibile o schema non aggiornato')
            raise

def get_notification_template(kind, template_id=None):
    q = NotificationTemplate.query.filter_by(kind=kind)
    if template_id:
        t = q.filter_by(id=template_id).first()
        if t:
            return t
    t = q.filter_by(is_default=True).first() or q.order_by(NotificationTemplate.id).first()
    if not t:
        action_label = ConfigLabel.query.filter_by(kind='action_label', value=notification_label_value(kind)).first()
        t = NotificationTemplate(kind=kind, name=DEFAULT_TEMPLATE_NAMES.get(kind, 'Template '+kind), subject=DEFAULT_NOTIFICATION_SUBJECTS.get(kind, 'Notifica incidente %NAME%'), body=DEFAULT_NOTIFICATION_BODIES.get(kind, DEFAULT_NOTIFICATION_BODIES['user']), action_label_id=action_label.id if action_label else None, recipient_source='incident_recipient_email' if kind == 'user' else 'empty', recipient_editable=True, recipient_external_allowed=True, cc_source='empty', cc_editable=True, cc_external_allowed=True, is_default=True)
        db.session.add(t); db.session.commit()
    return t

def _notification_placeholder_text(value):
    """Restituisce sempre testo sicuro per la sostituzione dei placeholder.

    Alcuni helper applicativi, come incident_measures(), restituiscono liste di
    righe perché gli stessi valori vengono usati anche per la compilazione dei
    moduli PDF. I template di notifica, invece, usano str.replace() e quindi
    richiedono sempre stringhe. Questa normalizzazione evita TypeError quando
    un placeholder è valorizzato con liste, tuple, set o altri tipi non testuali.
    """
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return '\n'.join(_notification_placeholder_text(item) for item in value if item is not None)
    return str(value)

def render_notification_text(template, inc, selected_documents=None):
    data_types = ', '.join([x.value for x in inc.data_types]) or 'nessun tipo di dato indicato'
    categories = ', '.join([x.value for x in inc.categories]) or 'nessuna categoria indicata'
    start = inc.start_at.strftime('%d/%m/%Y %H:%M') if inc.start_at else ''
    end = inc.end_at.strftime('%d/%m/%Y %H:%M') if inc.end_at else 'non disponibile'
    personal = 'È presente un rischio per diritti e libertà degli interessati.' if inc.personal_data else 'Non risulta un rischio per diritti e libertà degli interessati.'
    docs = selected_documents if selected_documents is not None else list(inc.documents)
    documents = ', '.join([d.filename for d in docs]) or '[nessun documento selezionato]'
    actions_rows = sorted(list(inc.actions), key=lambda a: (a.when_at or datetime.min, a.id or 0))
    if actions_rows:
        actions = '\n'.join([
            f'- {a.when_at.strftime("%d/%m/%Y %H:%M") if a.when_at else "data non disponibile"} - '
            f'{a.label.value if a.label else "senza label"}'
            f'{" - " + a.person_name if a.person_name else ""}'
            f'{" - " + a.description if a.description else ""}'
            for a in actions_rows
        ])
    else:
        actions = '[nessuna azione registrata]'
    replacements = {
        '%DATA%': data_types,
        '%CATEGORIES%': categories,
        '%RISK_RIGHTS_FREEDOM%': personal,
        '%REPORT%': '[report PDF allegato]',
        '%NAME%': inc.name or '',
        '%OPERATOR%': current_user.name or current_user.username or '',
        '%START%': start,
        '%END%': end,
        '%DESCRIPTION%': inc.description or '',
        '%REFERENCE%': inc.reference or '',
        '%RECIPIENT%': inc.recipient or inc.reference or '',
        '%CREATOR%': inc.creator_name or '',
        '%CREATOR_EMAIL%': inc.creator_email or '',
        '%DOCUMENTS%': documents,
        '%ACTIONS%': actions,
        '%STATUS%': inc.status or '',
        '%MEASURES_ADOPTED%': incident_measures(inc) or '[nessuna misura adottata registrata]',
        '%RECOMMENDATIONS%': '\n'.join([r.text for r in inc.recommendations]) or '[nessuna raccomandazione selezionata]',
        '%APP_INFO%': app_info_label(),
        '%SITE%': setting_value('structure_name', '') or '',
        '%RESP%': setting_value('security_responsible_name', '') or '',
        '%RESP_EMAIL%': setting_value('security_responsible_email', '') or '',
        '%DIRECTOR%': setting_value('security_owner_name', '') or '',
        '%DIRECTOR_ROLE%': setting_value('security_owner_role', '') or '',
        '%STATISTICS%': '[report statistiche allegato]',
        '%EXTERNAL_URL%': setting_value('application_external_url', 'http://localhost:8000') or 'http://localhost:8000',
        '%INCIDENT_URL%': incident_absolute_url(inc),
    }
    text = template or ''
    for key, value in replacements.items():
        text = text.replace(key, _notification_placeholder_text(value))
    return text

def notification_subject(kind, inc, template_id=None):
    tmpl = get_notification_template(kind, template_id)
    return render_notification_text(tmpl.subject, inc)

def notification_body_template(kind, template_id=None):
    return get_notification_template(kind, template_id).body

def notification_body(kind, inc, selected_documents=None, template_id=None):
    # Per le notifiche manuali/non schedulate il link diretto all'incidente
    # viene inserito solo se il template contiene esplicitamente %INCIDENT_URL%.
    return render_notification_text(notification_body_template(kind, template_id), inc, selected_documents=selected_documents)

def notification_needs_report(kind, template_id=None):
    template_text = ((get_notification_template(kind, template_id).subject or '') + '\n' + (notification_body_template(kind, template_id) or ''))
    return '%REPORT%' in template_text

def notification_needs_statistics(kind, template_id=None):
    template_text = ((get_notification_template(kind, template_id).subject or '') + '\n' + (notification_body_template(kind, template_id) or ''))
    return '%STATISTICS%' in template_text

def _statistics_pdf_for_notification():
    _, raw_periods = _build_stats_rows(include_search=False)
    from .reports import _period_statistics
    periods = [_period_statistics(p['name'], p['incidents'], p.get('start'), p.get('end')) for p in raw_periods]
    return statistics_pdf(periods)

def notification_needs_documents(kind, template_id=None):
    return '%DOCUMENTS%' in (notification_body_template(kind, template_id) or '')



def notification_type_tag_options(enabled_only=False):
    """Return notification-type tags available for document/form-template mapping.

    Tags are stored by notification type code for stability, while the UI shows
    the human-readable notification type name/label.
    """
    return notification_type_records(enabled_only=enabled_only)


def notification_tags_for_form_template_config(template_name):
    """Return the configured default notification-type tags for a form template."""
    if not template_name:
        return []
    cfg = FormTemplateConfig.query.filter_by(template_name=Path(template_name).stem).first()
    if cfg:
        valid = {t.code for t in notification_type_tag_options(enabled_only=False)}
        return [code for code in cfg.notification_tag_list if code in valid]
    return []


def notification_tags_for_generated_form_template(template_name):
    """Return default notification tags for a generated PDF form document.

    Generated documents inherit only the tags explicitly associated with the PDF
    form template in Admin -> Moduli. Notification-template links are not used as
    implicit tags anymore, so each form template controls its own document tags.
    """
    return notification_tags_for_form_template_config(template_name)

def documents_generated_from_template(inc, template_name):
    if not template_name:
        return []
    return Document.query.filter_by(incident_id=inc.id, generated_template_name=template_name).order_by(Document.uploaded_at.desc(), Document.filename).all()

def documents_tagged_for_notification(inc, kind):
    if not kind:
        return []
    docs = []
    for doc in sorted(list(inc.documents or []), key=lambda d: (d.uploaded_at or datetime.min, d.filename or '')):
        if kind in getattr(doc, 'notification_tag_list', []):
            docs.append(doc)
    return docs

def auto_selected_notification_documents(inc, template, kind=None):
    selected = []
    seen = set()
    for doc in documents_tagged_for_notification(inc, kind):
        if doc.id not in seen:
            selected.append(doc); seen.add(doc.id)
    # Generated documents linked to the notification template are not selected
    # implicitly anymore: they must carry the notification tag matching this
    # notification kind. This avoids attaching generated forms for the wrong
    # communication type.
    return selected

def get_external_recipients():
    return tenant_query(ExternalRecipient).order_by(ExternalRecipient.name, ExternalRecipient.email).all()

def split_addresses(value):
    if not value:
        return []
    return [x.strip() for x in value.replace(';', ',').split(',') if x.strip()]


def is_valid_email_address(value):
    """Validate a single mailbox address for notification delivery fields.

    The application accepts plain e-mail addresses in recipient/CC fields;
    display-name forms are intentionally not accepted in manual notification
    delivery fields so that SMTP envelope validation remains predictable.
    """
    email = (value or '').strip()
    if not email or any(ch.isspace() for ch in email):
        return False
    return re.match(r'^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$', email) is not None


def invalid_email_addresses(value):
    return [addr for addr in split_addresses(value) if not is_valid_email_address(addr)]


def validate_incident_recipient_email_fields(reference_value, recipient_value, recipient_email):
    """Validate the incident default recipient e-mail fields.

    The recipient e-mail can be used by manual notification templates as the
    default delivery address. It is validated independently from the external
    recipient address book, which is updated only through explicit management
    pages or imports.
    """
    email = (recipient_email or '').strip()
    if email and not is_valid_email_address(email):
        return 'Il campo E-mail Destinatario deve contenere un indirizzo e-mail valido.'
    if email and not ((reference_value or '').strip() or (recipient_value or '').strip()):
        return 'Se viene indicata l’E-mail Destinatario è obbligatorio compilare anche Riferimento o Destinatario.'
    return ''


def notification_template_address_sources():
    return [
        ('type_default', 'Compatibilità: e-mail del Destinatario o compilatore'),
        ('incident_recipient_email', 'E-mail del Destinatario dell’incidente'),
        ('incident_creator_email', 'E-mail del compilatore dell’incidente'),
        ('fixed', 'Valore fisso configurato nel template'),
        ('empty', 'Vuoto / compilazione manuale'),
    ]

def _normalize_template_address_source(value):
    allowed = {code for code, _ in notification_template_address_sources()}
    value = (value or 'type_default').strip()
    return value if value in allowed else 'type_default'

def apply_notification_template_address_form(tmpl):
    tmpl.recipient_source = _normalize_template_address_source(request.form.get('recipient_source'))
    tmpl.recipient_value = (request.form.get('recipient_value') or '').strip()
    tmpl.recipient_editable = bool(request.form.get('recipient_editable'))
    tmpl.recipient_external_allowed = bool(request.form.get('recipient_external_allowed'))
    tmpl.cc_source = _normalize_template_address_source(request.form.get('cc_source'))
    tmpl.cc_value = (request.form.get('cc_value') or '').strip()
    tmpl.cc_editable = bool(request.form.get('cc_editable'))
    tmpl.cc_external_allowed = bool(request.form.get('cc_external_allowed'))

def _template_configured_address(template, kind, inc, ntype, field):
    source = _normalize_template_address_source(getattr(template, f'{field}_source', 'type_default'))
    value = (getattr(template, f'{field}_value', '') or '').strip()
    if source == 'fixed':
        return value
    if source == 'incident_recipient_email':
        return (getattr(inc, 'recipient_email', '') or '').strip()
    if source == 'incident_creator_email':
        return (getattr(inc, 'creator_email', '') or '').strip()
    if source == 'empty':
        return ''
    if source == 'type_default':
        # Compatibilità con template creati prima dello spostamento completo
        # della configurazione destinatari/CC nei template: non legge più
        # impostazioni globali CSIRT/DPO, ma usa solo dati dell'incidente.
        if field == 'recipient':
            return (getattr(inc, 'recipient_email', '') or getattr(inc, 'creator_email', '') or '').strip()
        return ''
    return ''

def resolve_template_notification_addresses(template, kind, inc, ntype, form=None, args=None):
    form = form or {}
    args = args or {}
    recipient_editable = bool(getattr(template, 'recipient_editable', True))
    cc_editable = bool(getattr(template, 'cc_editable', True))

    def _cc_enabled_in_submit():
        # La checkbox dell'anteprima invia cc_enabled_present per distinguere
        # un submit reale dalla semplice apertura GET. Se la checkbox viene
        # deselezionata, il CC non deve essere considerato anche se il template
        # ha un valore predefinito.
        if not hasattr(form, 'get') or form.get('cc_enabled_present') is None:
            return True
        if hasattr(form, 'getlist'):
            return '1' in form.getlist('cc_enabled')
        return form.get('cc_enabled') == '1'

    def _submitted_value(field):
        # Nei submit di invio/conferma la preview può contenere valori digitati
        # manualmente non ancora ricalcolati. Questi campi hanno priorità sui
        # valori hidden generati all'apertura dell'anteprima.
        manual_field = f'manual_{field}'
        if hasattr(form, 'get') and form.get(manual_field) is not None:
            return form.get(manual_field)
        if hasattr(form, 'get') and form.get(field) is not None:
            return form.get(field)
        if hasattr(args, 'get') and args.get(field) is not None:
            return args.get(field)
        return None

    if recipient_editable:
        recipient = _submitted_value('recipient')
        if recipient is None:
            recipient = _template_configured_address(template, kind, inc, ntype, 'recipient')
    else:
        recipient = _template_configured_address(template, kind, inc, ntype, 'recipient')
    if not _cc_enabled_in_submit():
        cc = ''
    elif cc_editable:
        cc = _submitted_value('cc')
        if cc is None:
            cc = _template_configured_address(template, kind, inc, ntype, 'cc')
    else:
        cc = _template_configured_address(template, kind, inc, ntype, 'cc')
    return (recipient or '').strip(), (cc or '').strip()

def smtp_sender_address():
    """Determina il mittente effettivo delle mail.

    Se l'autenticazione SMTP è abilitata, il mittente SMTP predefinito è
    obbligatorio e viene usato per tutte le notifiche e per le mail di test,
    incluso l'utente locale admin. Senza autenticazione resta possibile usare
    il mittente predefinito oppure l'email dell'utente collegato.
    """
    auth_enabled = setting_value('smtp_auth_enabled', '0') == '1'
    default_sender = setting_value('smtp_default_sender', '').strip()
    username = setting_value('smtp_username', '').strip()
    if auth_enabled:
        if not default_sender:
            raise RuntimeError('Autenticazione SMTP abilitata: configurare il mittente SMTP predefinito')
        return default_sender
    
    try:
        user_email = (current_user.email or '').strip() if getattr(current_user, 'is_authenticated', False) else ''
    except Exception:
        user_email = ''
    return default_sender or user_email or username or 'admin@localhost.localdomain'


def notify_admin_disabled_user_created(user, source='auto'):
    """Invia una mail all'admin quando viene creato automaticamente un utente disabled.

    La notifica è best-effort: eventuali problemi SMTP non devono impedire login,
    provisioning o creazione dell'utente.
    """
    try:
        if not user or getattr(user, 'role', None) != 'disabled':
            return False, 'utente non disabled'
        admin = User.query.filter_by(username='admin', auth_provider='local').first() or User.query.filter_by(role='admin').order_by(User.id).first()
        admin_email = (getattr(admin, 'email', '') or '').strip()
        if not admin_email:
            return False, 'email admin non configurata'
        host = setting_value('smtp_host')
        if not host:
            return False, 'SMTP non configurato'
        base = (setting_value('application_external_url', 'http://localhost:8000') or 'http://localhost:8000').rstrip('/')
        users_url = f'{base}/admin/users'
        msg = EmailMessage()
        msg['From'] = smtp_sender_address()
        msg['To'] = admin_email
        msg['Subject'] = 'Nuovo utente creato automaticamente in stato disabled'
        msg.set_content(
            'È stato creato automaticamente un nuovo utente con ruolo disabled.\n\n'
            f'Username: {user.username or "-"}\n'
            f'Backend: {user.auth_provider or "-"}\n'
            f'Nome: {user.name or "-"}\n'
            f'Email: {user.email or "-"}\n'
            f'Origine: {source}\n\n'
            'Per abilitarlo o modificarne il ruolo aprire direttamente la gestione utenti:\n'
            f'{users_url}\n'
        )
        try:
            port = int(setting_value('smtp_port', '587') or '587')
        except ValueError:
            return False, 'porta SMTP non valida'
        smtp_cls = smtplib.SMTP_SSL if setting_value('smtp_use_ssl', '0') == '1' else smtplib.SMTP
        with smtp_cls(host, port, timeout=20) as smtp:
            if setting_value('smtp_use_tls', '1') == '1' and setting_value('smtp_use_ssl', '0') != '1':
                smtp.starttls()
            if setting_value('smtp_auth_enabled', '0') == '1':
                username = setting_value('smtp_username')
                if not username:
                    return False, 'autenticazione SMTP abilitata senza username'
                smtp.login(username, setting_value('smtp_password') or '')
            smtp.send_message(msg)
        audit_log('users:auto_disabled_admin_notification_sent', {'user_id': user.id, 'username': user.username, 'backend': user.auth_provider, 'admin_email': admin_email}, actor_type='system', commit=True)
        return True, admin_email
    except Exception as exc:
        current_app.logger.exception('Invio notifica admin per utente disabled non riuscito')
        return False, str(exc)


def send_notification_email(kind, inc, recipient, cc, subject, body, attach_report, selected_documents=None, attach_statistics=False):
    sender = smtp_sender_address()
    if not recipient:
        raise RuntimeError('Email destinatario non configurata')
    host = setting_value('smtp_host')
    if not host:
        raise RuntimeError('SMTP host non configurato')
    try:
        port = int(setting_value('smtp_port', '587') or '587')
    except ValueError:
        raise RuntimeError('Porta SMTP non valida')
    username = setting_value('smtp_username')
    password = setting_value('smtp_password')
    use_tls = setting_value('smtp_use_tls', '1') == '1'
    use_ssl = setting_value('smtp_use_ssl', '0') == '1'
    auth_enabled = setting_value('smtp_auth_enabled', '0') == '1'
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = recipient
    if cc:
        msg['Cc'] = cc
    msg['Subject'] = subject
    # Non aggiunge automaticamente il link incidente: nelle notifiche manuali
    # il link compare solo se il template contiene %INCIDENT_URL%.
    msg.set_content(body or '')
    if attach_report:
        _email_add_pdf_attachment_from_path_or_buffer(msg, incident_pdf(inc), f'incident-{inc.id}-report.pdf')
    if attach_statistics:
        _email_add_pdf_attachment_from_path_or_buffer(msg, _statistics_pdf_for_notification(), 'statistiche-incidenti.pdf')
    for doc in selected_documents or []:
        path = os.path.join(current_app.config['UPLOAD_DIR'], doc.stored_name or '')
        if not os.path.isfile(path):
            raise RuntimeError(f'Documento non trovato sul filesystem: {doc.filename}')
        with open(path, 'rb') as fh:
            data = fh.read()
        msg.add_attachment(data, maintype='application', subtype='octet-stream', filename=doc.filename)
    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    current_app.logger.info('Invio notifica %s incidente %s via SMTP host=%s port=%s ssl=%s starttls=%s auth=%s from=%s to=%s cc=%s attach_report=%s attach_statistics=%s documents=%s', kind, inc.id, host, port, use_ssl, use_tls and not use_ssl, auth_enabled, sender, recipient, cc or '', attach_report, attach_statistics, len(selected_documents or []))
    with smtp_cls(host, port, timeout=20) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if auth_enabled:
            if not username:
                raise RuntimeError('Autenticazione SMTP abilitata ma username non configurato')
            smtp.login(username, password or '')
        smtp.send_message(msg)
    return {'sender': sender, 'recipient': recipient, 'cc': cc or '', 'attach_report': attach_report, 'attach_statistics': attach_statistics, 'documents': [d.filename for d in (selected_documents or [])]}


def send_smtp_test_email(test_recipient):
    sender = smtp_sender_address()
    if not test_recipient:
        raise RuntimeError('Specificare un indirizzo destinatario per la mail di prova')
    host = setting_value('smtp_host')
    if not host:
        raise RuntimeError('SMTP host non configurato')
    try:
        port = int(setting_value('smtp_port', '587') or '587')
    except ValueError:
        raise RuntimeError('Porta SMTP non valida')
    username = setting_value('smtp_username')
    password = setting_value('smtp_password')
    use_tls = setting_value('smtp_use_tls', '1') == '1'
    use_ssl = setting_value('smtp_use_ssl', '0') == '1'
    auth_enabled = setting_value('smtp_auth_enabled', '0') == '1'

    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = test_recipient
    msg['Subject'] = 'Cybersecurity Incident Registry - mail di prova SMTP'
    msg.set_content(
        'Questa è una mail di prova inviata da Cybersecurity Incident Registry.\n\n'
        f'Utente: {current_user.name} <{current_user.email}>\n'
        f'Server SMTP: {host}:{port}\n'
        f'SSL/TLS diretto: {"sì" if use_ssl else "no"}\n'
        f'STARTTLS: {"sì" if (use_tls and not use_ssl) else "no"}\n'
        f'Autenticazione: {"sì" if auth_enabled else "no"}\n'
    )

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    current_app.logger.info(
        'Invio mail di prova SMTP host=%s port=%s ssl=%s starttls=%s auth=%s from=%s to=%s',
        host, port, use_ssl, use_tls and not use_ssl, auth_enabled, sender, test_recipient
    )
    with smtp_cls(host, port, timeout=20) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if auth_enabled:
            if not username:
                raise RuntimeError('Autenticazione SMTP abilitata ma username non configurato')
            smtp.login(username, password or '')
        smtp.send_message(msg)




def parse_positive_int(value, default=0):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return default


def raw_deadline_interval_minutes():
    hours = parse_positive_int(setting_value('notification_deadline_interval_hours', '24'))
    minutes = parse_positive_int(setting_value('notification_deadline_interval_minutes', '0'))
    return hours * 60 + minutes


def deadline_interval_minutes():
    total = raw_deadline_interval_minutes()
    return total if total > 0 else 24 * 60


def deadline_schedule_mode():
    """Modalità di pianificazione delle notifiche task in scadenza.

    Valori supportati:
    - interval: intervallo regolare calcolato dalla mezzanotte locale;
    - cron: elenco di orari giornalieri specifici più eventuale intervallo.
    """
    value = (setting_value('notification_deadline_schedule_mode', 'interval') or 'interval').strip().lower()
    return value if value in {'interval', 'cron'} else 'interval'


def parse_deadline_cron_times(value=None):
    """Restituisce gli orari giornalieri configurati in minuti da mezzanotte.

    Accetta valori separati da virgola, punto e virgola, spazio o nuova riga,
    nel formato HH:MM. Gli orari non validi sono ignorati per rendere la
    configurazione tollerante e non bloccare lo scheduler.
    """
    raw = setting_value('notification_deadline_cron_times', '') if value is None else (value or '')
    out = set()
    for token in re.split(r'[,;\s]+', raw):
        token = token.strip()
        if not token:
            continue
        m = re.fullmatch(r'(\d{1,2}):(\d{2})', token)
        if not m:
            continue
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            out.add(hour * 60 + minute)
    return sorted(out)


def format_minutes_as_hhmm(total_minutes):
    total_minutes = int(total_minutes) % (24 * 60)
    return f'{total_minutes // 60:02d}:{total_minutes % 60:02d}'


def deadline_schedule_reference_midnight(now=None):
    """Mezzanotte del giorno corrente nel fuso orario applicativo."""
    now = now or application_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def deadline_schedule_slots_for_day(now=None):
    """Slot schedulati del giorno corrente, in minuti dalla mezzanotte.

    In modalità cron possono coesistere orari specifici e intervalli. Gli
    intervalli restano sempre ancorati alla mezzanotte locale, quindi un
    intervallo di 4 ore produce 00:00, 04:00, 08:00, 12:00, ...
    """
    mode = deadline_schedule_mode()
    interval = raw_deadline_interval_minutes()
    if interval <= 0 and mode == 'interval':
        interval = 24 * 60
    slots = set(range(0, 24 * 60, interval)) if interval > 0 else set()
    if mode == 'cron':
        slots.update(parse_deadline_cron_times())
    if not slots:
        slots.add(0)
    return sorted(slots)


def current_deadline_schedule_slot(now=None):
    """Ultimo slot schedulato calcolato dalla pianificazione cron/intervallo."""
    now = now or application_now()
    midnight = deadline_schedule_reference_midnight(now)
    elapsed_minutes = max(0, int((now - midnight).total_seconds() // 60))
    slots = [m for m in deadline_schedule_slots_for_day(now) if m <= elapsed_minutes]
    slot_minutes = slots[-1] if slots else deadline_schedule_slots_for_day(now)[-1] - 24 * 60
    return midnight + timedelta(minutes=slot_minutes)


def next_deadline_notification_at(now=None):
    """Prossimo invio stimato secondo la pianificazione cron/intervallo.

    Il calcolo non dipende dall'ora di avvio del processo applicativo. In
    modalità cron considera gli orari specifici configurati e gli eventuali
    intervalli regolari, sempre ancorati alla mezzanotte locale.
    """
    now = now or application_now()
    midnight = deadline_schedule_reference_midnight(now)
    elapsed_minutes = max(0, int((now - midnight).total_seconds() // 60))
    for slot in deadline_schedule_slots_for_day(now):
        if slot > elapsed_minutes:
            return midnight + timedelta(minutes=slot)
    return midnight + timedelta(days=1, minutes=deadline_schedule_slots_for_day(now)[0])



def deadline_schedule_window(now=None):
    """Restituisce lo slot corrente e il successivo per le notifiche deadline.

    La finestra [slot_corrente, slot_successivo) rappresenta l'intervallo di
    pausa tra due schedule successive: all'interno di questa finestra una
    stessa notifica con deadline non deve essere inviata più volte.
    """
    now = now or application_now()
    current_slot = current_deadline_schedule_slot(now)
    next_slot = next_deadline_notification_at(now)
    if next_slot <= current_slot:
        next_slot = current_slot + timedelta(minutes=max(1, raw_deadline_interval_minutes() or deadline_interval_minutes() or 1440))
    return current_slot, next_slot


def _deadline_notification_key(incident_id, notification_type='deadline_summary'):
    return f'{notification_type}:incident:{int(incident_id)}'


def _deadline_state_for_incident(incident_id):
    key = _deadline_notification_key(incident_id)
    return DeadlineNotificationState.query.filter_by(notification_key=key).first()


def _deadline_notification_sent_in_current_window(incident_id, schedule_slot, next_slot):
    """True se la stessa notifica è già stata presa in carico nello stesso intervallo.

    La tabella persistente viene usata sia per gli invii riusciti sia come
    *claim* preventivo dello slot. In questo modo, anche con più worker o più
    repliche senza lock PostgreSQL efficace, un secondo ciclo dello scheduler
    non può inviare la stessa notifica mentre il primo invio è in corso.
    """
    if not incident_id or not schedule_slot:
        return False
    state = _deadline_state_for_incident(incident_id)
    if state:
        if state.last_schedule_slot and state.last_schedule_slot == schedule_slot:
            return True
        if state.last_success_at:
            last = state.last_success_at
            if last >= schedule_slot and (not next_slot or last < next_slot):
                return True
    return _deadline_notification_already_sent_for_slot(incident_id, schedule_slot)


def _claim_deadline_notification_slot(incident_id, schedule_slot, source='scheduler'):
    """Riserva in modo persistente lo slot di notifica per un incidente.

    Il claim viene scritto e committato prima dell'invio e sfrutta la chiave
    unica ``notification_key``. Se due scheduler tentano di inviare nello
    stesso intervallo, uno dei due trova già lo slot riservato oppure riceve
    una IntegrityError e salta l'invio, evitando mail flooding.
    """
    if not incident_id or not schedule_slot:
        return False
    key = _deadline_notification_key(incident_id)
    now = application_now()
    try:
        state = DeadlineNotificationState.query.filter_by(notification_key=key).first()
        if not state:
            state = DeadlineNotificationState(
                notification_key=key,
                notification_type='deadline_summary',
                incident_id=incident_id,
                last_success_at=now,
                last_schedule_slot=schedule_slot,
                last_recipients='',
                last_details=f'invio in corso; sorgente {source}',
                send_count=0,
            )
            db.session.add(state)
            db.session.commit()
            return True
        updated = DeadlineNotificationState.query.filter(
            DeadlineNotificationState.notification_key == key,
            db.or_(
                DeadlineNotificationState.last_schedule_slot.is_(None),
                DeadlineNotificationState.last_schedule_slot != schedule_slot,
            ),
        ).update({
            DeadlineNotificationState.notification_type: 'deadline_summary',
            DeadlineNotificationState.incident_id: incident_id,
            DeadlineNotificationState.last_success_at: now,
            DeadlineNotificationState.last_schedule_slot: schedule_slot,
            DeadlineNotificationState.last_recipients: '',
            DeadlineNotificationState.last_details: f'invio in corso; sorgente {source}',
            DeadlineNotificationState.updated_at: utcnow(),
        }, synchronize_session=False)
        if not updated:
            db.session.rollback()
            return False
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Claim slot notifica deadline non completato per incidente %s', incident_id)
        return False


def _record_deadline_notification_success(incident_id, schedule_slot, recipients, details=''):
    """Aggiorna lo stato dell'ultimo invio riuscito di una notifica deadline.

    I destinatari vengono conservati nello stato persistente perché la sezione
    "Prossime notifiche schedulate" mostra anche gli esiti recenti. Se il
    chiamante non passa una stringa valorizzata, vengono ricalcolati
    dall'incidente prima di salvare lo stato.
    """
    key = _deadline_notification_key(incident_id)
    now = application_now()
    recipients = (recipients or '').strip()
    if not recipients:
        recipients = _deadline_recipients_text_for_incident(db.session.get(Incident, incident_id))
    state = DeadlineNotificationState.query.filter_by(notification_key=key).first()
    if not state:
        state = DeadlineNotificationState(
            notification_key=key,
            notification_type='deadline_summary',
            incident_id=incident_id,
            last_success_at=now,
            last_schedule_slot=schedule_slot,
            last_recipients=recipients or '',
            last_details=details or '',
            send_count=1,
        )
        db.session.add(state)
    else:
        state.notification_type = 'deadline_summary'
        state.incident_id = incident_id
        state.last_success_at = now
        state.last_schedule_slot = schedule_slot
        state.last_recipients = recipients or ''
        state.last_details = details or ''
        state.send_count = max(1, int(state.send_count or 0) + 1)
        state.updated_at = utcnow()
    return state


def _record_deadline_notification_failure(incident_id, schedule_slot, details=''):
    """Registra l'esito negativo mantenendo il claim dello slot corrente."""
    state = _deadline_state_for_incident(incident_id)
    if state:
        state.last_schedule_slot = schedule_slot
        state.last_details = details or 'invio non riuscito'
        state.updated_at = utcnow()
    return state


def cleanup_stale_deadline_notification_states():
    """Rimuove stati scheduler riferiti a incidenti non più esistenti.

    Viene eseguito ad ogni ciclo dello scheduler per eliminare rimanenze di
    vecchi incidenti cancellati, anche su database esistenti o importati prima
    dell'introduzione del cascade.
    """
    try:
        stale = DeadlineNotificationState.query.outerjoin(Incident, DeadlineNotificationState.incident_id == Incident.id).filter(
            DeadlineNotificationState.incident_id.isnot(None),
            Incident.id.is_(None),
        ).all()
        for row in stale:
            db.session.delete(row)
        if stale:
            db.session.commit()
        return len(stale)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Cleanup stati notifiche deadline orfani non completato')
        return 0

def _deadline_slot_label(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec='minutes')
    return str(value or '')




def upcoming_scheduled_notifications(hours=24, limit=200):
    """Riepilogo delle prossime notifiche schedulate visibile in Impostazioni → Notifiche.

    Include i promemoria puntuali degli incidenti e gli slot futuri delle notifiche
    automatiche sui task in scadenza. Le date sono calcolate nel fuso applicativo
    e i record già inviati nello slot corrente/futuro non vengono riproposti.
    """
    now = application_now()
    horizon = now + timedelta(hours=hours)
    rows = []

    # Promemoria puntuali sui singoli incidenti: include quelli futuri e
    # quelli appena inviati/falliti, così la pagina aggiorna lo stato dopo il
    # ciclo scheduler senza far sparire immediatamente la riga operativa.
    recent_start = now - timedelta(hours=hours)
    reminders = IncidentReminder.query.filter(
        IncidentReminder.scheduled_at >= recent_start,
        IncidentReminder.scheduled_at <= horizon,
    ).order_by(IncidentReminder.scheduled_at.asc(), IncidentReminder.id.asc()).limit(limit).all()
    for rem in reminders:
        inc = rem.incident
        people_recipients = sorted({(p.email or '').strip() for p in (inc.people or []) if (p.email or '').strip()}) if inc else []
        cc = _split_email_list(rem.cc_emails)
        status = 'inviata' if rem.sent_at else ('errore: ' + rem.last_error if rem.last_error else 'programmata')
        rows.append({
            'scheduled_at': rem.scheduled_at,
            'scheduled_at_text': format_application_datetime(rem.scheduled_at, include_timezone=True),
            'type': 'Promemoria incidente',
            'recipients': ', '.join(people_recipients + cc) or 'nessun destinatario disponibile',
            'incident': inc,
            'incident_label': f'#{inc.id} - {inc.name}' if inc else f'#{rem.incident_id}',
            'source': 'promemoria',
            'status': status,
            'status_at_text': format_application_datetime(rem.sent_at, include_timezone=True) if rem.sent_at else '',
        })

    # Slot futuri del riepilogo task in scadenza. Per ogni slot si mostrano gli
    # incidenti che, allo stato attuale, hanno operazioni pendenti con tempo massimo.
    if setting_value('notification_deadline_enabled', '0') == '1':
        slot_cursor = now
        seen_slots = set()
        while len(rows) < limit:
            slot = next_deadline_notification_at(slot_cursor)
            if slot > horizon:
                break
            if slot in seen_slots:
                break
            seen_slots.add(slot)
            next_slot = next_deadline_notification_at(slot + timedelta(minutes=1))
            for inc in Incident.query.filter(Incident.status != 'chiuso', Incident.deadline_notifications_muted.is_(False)).order_by(Incident.id.asc()).all():
                if not pending_deadline_actions_for_incident(inc, now=now):
                    continue
                if _deadline_notification_sent_in_current_window(inc.id, slot, next_slot):
                    continue
                recipients_text = _deadline_recipients_text_for_incident(inc)
                rows.append({
                    'scheduled_at': slot,
                    'scheduled_at_text': format_application_datetime(slot, include_timezone=True),
                    'type': 'Task in scadenza',
                    'recipients': recipients_text or 'nessun destinatario disponibile',
                    'incident': inc,
                    'incident_label': f'#{inc.id} - {inc.name}',
                    'source': 'deadline',
                    'status': 'programmata',
                    'status_at_text': '',
                })
                if len(rows) >= limit:
                    break
            slot_cursor = slot + timedelta(minutes=1)

    # Aggiunge gli esiti recenti delle notifiche deadline già inviate o fallite,
    # usando il registro persistente anti-flooding.
    recent_states = DeadlineNotificationState.query.filter(
        DeadlineNotificationState.notification_type == 'deadline_summary',
        DeadlineNotificationState.last_schedule_slot >= recent_start,
        DeadlineNotificationState.last_schedule_slot <= now,
    ).order_by(DeadlineNotificationState.last_schedule_slot.desc()).limit(limit).all()
    existing_keys = {(r.get('source'), getattr(r.get('incident'), 'id', None), r.get('scheduled_at')) for r in rows}
    for state in recent_states:
        inc = state.incident if hasattr(state, 'incident') else db.session.get(Incident, state.incident_id)
        key = ('deadline', state.incident_id, state.last_schedule_slot)
        if key in existing_keys:
            continue
        recipients_text = (state.last_recipients or '').strip()
        if not recipients_text and int(state.send_count or 0) > 0:
            recipients_text = _deadline_recipients_text_for_incident(inc)
        rows.append({
            'scheduled_at': state.last_schedule_slot or state.last_success_at or now,
            'scheduled_at_text': format_application_datetime(state.last_schedule_slot or state.last_success_at or now, include_timezone=True),
            'type': 'Task in scadenza',
            'recipients': recipients_text or 'nessun destinatario disponibile',
            'incident': inc,
            'incident_label': f'#{inc.id} - {inc.name}' if inc else f'#{state.incident_id}',
            'source': 'deadline',
            'status': 'inviata' if int(state.send_count or 0) > 0 else ('errore' if state.last_details else 'in corso'),
            'status_at_text': format_application_datetime(state.last_success_at, include_timezone=True) if state.last_success_at else '',
        })
    rows.sort(key=lambda r: (r['scheduled_at'], r['type'], r['incident_label']))
    return rows[:limit]


def format_deadline_schedule_info():
    next_at = next_deadline_notification_at()
    current_slot = current_deadline_schedule_slot()
    last_raw = setting_value('notification_deadline_last_run_at', '')
    last_label = 'mai eseguito automaticamente'
    if last_raw:
        try:
            last_label = format_application_datetime(datetime.fromisoformat(last_raw), include_timezone=True)
        except ValueError:
            last_label = last_raw
    mode = deadline_schedule_mode()
    slots = deadline_schedule_slots_for_day()
    return {
        'enabled': setting_value('notification_deadline_enabled', '0') == '1',
        'email_enabled': setting_value('notification_deadline_email_enabled', '1') == '1',
        'schedule_mode': mode,
        'schedule_mode_label': 'cron / orari specifici' if mode == 'cron' else 'intervallo regolare',
        'cron_times': ', '.join(format_minutes_as_hhmm(m) for m in parse_deadline_cron_times()) or '-',
        'interval_minutes': raw_deadline_interval_minutes() if deadline_schedule_mode() == 'cron' else deadline_interval_minutes(),
        'configured_slots': ', '.join(format_minutes_as_hhmm(m) for m in slots[:24]) + ('…' if len(slots) > 24 else ''),
        'timezone': application_timezone_name(),
        'reference_midnight': format_application_datetime(deadline_schedule_reference_midnight(), include_timezone=True),
        'current_slot': format_application_datetime(current_slot, include_timezone=True),
        'next_at': format_application_datetime(next_at, include_timezone=True),
        'last_run_at': last_label,
    }

def first_initial_information_at(inc):
    candidates = []
    for action in inc.actions or []:
        txt = ' '.join([getattr(action.label, 'value', '') or '', action.description or '']).lower()
        if 'informazione iniziale' in txt and action.when_at:
            candidates.append(action.when_at)
    if candidates:
        return min(candidates)
    return inc.first_action_at


def pending_deadline_actions_for_incident(inc, now=None):
    now = now or application_now()
    start = first_initial_information_at(inc)
    if getattr(inc, 'deadline_notifications_muted', False):
        return []
    # La presenza di personale non deve influire sulla ricerca delle azioni
    # mancanti: i task in scadenza devono essere rilevati e conteggiati anche
    # quando l'invio email verrà poi saltato per assenza di destinatari.
    #
    # La lista dei placeholder %pending_actions% e %pending_actions_count%
    # deve rispettare il workflow effettivamente applicabile all'incidente:
    # gli step con condizioni non soddisfatte, ad esempio rischio per diritti
    # e libertà, gravità o dati interessati, non devono essere notificati.
    if not start:
        return []
    action_counts = {}
    for action in (inc.actions or []):
        if action.label_id:
            action_counts[action.label_id] = action_counts.get(action.label_id, 0) + 1
    used_counts = {}
    rows = []
    for step in workflow_steps_for_incident(inc):
        lab = step.action_label
        if not lab:
            continue
        max_hours = int(getattr(lab, 'max_completion_hours', 0) or 0)
        if max_hours <= 0:
            continue
        label_id = int(lab.id)
        used = used_counts.get(label_id, 0)
        total = action_counts.get(label_id, 0)
        done = used < total
        if done:
            used_counts[label_id] = used + 1
            continue
        due_at = start + timedelta(hours=max_hours)
        remaining = due_at - now
        total_seconds = int(remaining.total_seconds())
        sign = '' if total_seconds >= 0 else '-'
        total_seconds = abs(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        rows.append({
            'label': lab,
            'step': step,
            'step_id': step.id,
            'task_name': lab.value,
            'workflow_description': step.description or '',
            'due_at': due_at,
            'remaining_text': f'{sign}{hours}h {minutes:02d}m',
            'expired': remaining.total_seconds() < 0,
        })
    return rows

DEADLINE_NOTIFICATION_PLACEHOLDERS = [
    ('%incident_id%', 'ID interno dell’incidente'),
    ('%incident_name%', 'Nome dell’incidente'),
    ('%incident_reference%', 'Riferimento dell’incidente'),
    ('%incident_status%', 'Stato corrente dell’incidente'),
    ('%incident_description%', 'Descrizione dell’incidente'),
    ('%initial_information_at%', 'Data e ora della prima informazione iniziale'),
    ('%recipients%', 'Destinatari della notifica'),
    ('%pending_actions%', 'Elenco puntato degli step workflow applicabili mancanti con scadenza e tempo rimanente'),
    ('%pending_actions_count%', 'Numero di step workflow applicabili mancanti soggetti a tempo massimo'),
    ('%generated_at%', 'Data e ora di generazione del messaggio'),
    ('%application_name%', 'Nome dell’applicazione'),
    ('%external_url%', 'URL esterna dell’applicazione configurata in Admin → Altre configurazioni'),
    ('%incident_url%', 'Link diretto alla pagina dell’incidente'),
    ('%report%', 'Richiede allegato PDF del report dell’incidente generato al momento dell’invio'),
    ('%statistics%', 'Richiede allegato PDF delle statistiche incidenti generato al momento dell’invio'),
]


def default_deadline_subject_template():
    return 'Promemoria scadenze azioni - Incidente %incident_name%'


def default_deadline_body_template():
    return (
        'Promemoria automatico delle azioni previste non ancora registrate.\n\n'
        'Incidente: %incident_name%\n'
        'Riferimento: %incident_reference%\n'
        'Stato: %incident_status%\n'
        'Informazione iniziale: %initial_information_at%\n\n'
        'Azioni mancanti con tempo massimo configurato:\n'
        '%pending_actions%\n\n'
        'Destinatari: %recipients%\n\n'
        'Questa mail è stata generata automaticamente da %application_name% il %generated_at%.\n'
        'Link incidente: %incident_url%\n'
        'Accesso applicazione: %external_url%'
    )


def build_deadline_pending_actions_text(pending_rows):
    lines = []
    for row in pending_rows or []:
        lab = row['label']
        step = row.get('step')
        label_text = (row.get('workflow_description') or (lab.description or lab.value))
        task_name = row.get('task_name') or lab.value
        if step and label_text != task_name:
            label_text = f'{label_text} ({task_name})'
        lines.append(f'- {label_text} | scadenza {format_application_datetime(row["due_at"])} | tempo rimanente {row["remaining_text"]}')
    return '\n'.join(lines) if lines else '- Nessuna azione mancante'


def render_deadline_template(template, inc, pending_rows, recipients, now=None):
    now = now or application_now()
    initial_at = first_initial_information_at(inc)
    values = {
        '%incident_id%': str(inc.id or ''),
        '%incident_name%': inc.name or '',
        '%incident_reference%': inc.reference or '-',
        '%incident_status%': inc.status or '-',
        '%incident_description%': inc.description or '',
        '%initial_information_at%': format_application_datetime(initial_at) if initial_at else 'non disponibile',
        '%recipients%': ', '.join(recipients or []),
        '%pending_actions%': build_deadline_pending_actions_text(pending_rows),
        '%pending_actions_count%': str(len(pending_rows or [])),
        '%generated_at%': format_application_datetime(now),
        '%application_name%': 'Cybersecurity Incident Registry',
        '%external_url%': setting_value('application_external_url', 'http://localhost:8000') or 'http://localhost:8000',
        '%incident_url%': incident_absolute_url(inc),
        '%report%': '[report incidente allegato]',
        '%statistics%': '[report statistiche allegato]',
    }
    rendered = template or ''
    for key, value in values.items():
        rendered = rendered.replace(key, value)
    return rendered


def deadline_template_unknown_placeholders(subject_template, body_template):
    allowed = {p for p, _ in DEADLINE_NOTIFICATION_PLACEHOLDERS}
    found = set(re.findall(r'%[^%]+%', (subject_template or '') + '\n' + (body_template or '')))
    return sorted(found - allowed)


def build_deadline_email_content(inc, pending_rows, recipients, now=None):
    subject_template = setting_value('notification_deadline_subject_template', default_deadline_subject_template()) or default_deadline_subject_template()
    body_template = setting_value('notification_deadline_body_template', default_deadline_body_template()) or default_deadline_body_template()
    subject = strip_markdown_formatting(render_deadline_template(subject_template, inc, pending_rows, recipients, now=now)).strip() or default_deadline_subject_template().replace('%incident_name%', inc.name or '')
    body = strip_markdown_formatting(render_deadline_template(body_template, inc, pending_rows, recipients, now=now))
    link = incident_absolute_url(inc)
    if link not in body:
        body = body.rstrip() + f'\n\nLink diretto incidente: {link}'
    return subject, body


def sample_deadline_preview():
    class Obj: pass
    inc = Obj()
    inc.id = 123
    inc.name = 'Esempio incidente ransomware'
    inc.reference = 'INC-2026-001'
    inc.status = 'aperto'
    inc.description = 'Esempio di incidente usato per il preview del template.'
    inc.actions = []
    inc.first_action_at = application_now() - timedelta(hours=2)
    recipients = ['mario.rossi@example.org', 'laura.bianchi@example.org']
    lab1 = Obj(); lab1.value = 'Comunicazione CSIRT'; lab1.description = 'Inviare comunicazione al CSIRT'
    lab2 = Obj(); lab2.value = 'Valutazione Garante'; lab2.description = 'Valutare necessità di comunicazione al Garante'
    now = application_now()
    rows = [
        {'label': lab1, 'due_at': now + timedelta(hours=2, minutes=30), 'remaining_text': '2h 30m', 'expired': False},
        {'label': lab2, 'due_at': now - timedelta(hours=1), 'remaining_text': '-1h 00m', 'expired': True},
    ]
    subject_template = setting_value('notification_deadline_subject_template', default_deadline_subject_template()) or default_deadline_subject_template()
    body_template = setting_value('notification_deadline_body_template', default_deadline_body_template()) or default_deadline_body_template()
    subject = render_deadline_template(subject_template, inc, rows, recipients, now=now)
    body = render_deadline_template(body_template, inc, rows, recipients, now=now)
    text = (subject_template + '\n' + body_template).lower()
    attachments = []
    if '%report%' in text:
        attachments.append('incident-123-report.pdf')
    if '%statistics%' in text:
        attachments.append('statistiche-incidenti.pdf')
    if attachments:
        body += '\n\n[Anteprima allegati generati dal template: ' + ', '.join(attachments) + ']'
    return subject, body



def _email_add_pdf_attachment_from_path_or_buffer(msg, pdf_file, filename):
    """Aggiunge un PDF a un messaggio e rimuove eventuali file temporanei."""
    try:
        if isinstance(pdf_file, (str, os.PathLike)):
            with open(pdf_file, 'rb') as fh:
                pdf_bytes = fh.read()
        else:
            pdf_bytes = pdf_file.getvalue() if hasattr(pdf_file, 'getvalue') else pdf_file.read()
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=filename)
    finally:
        if isinstance(pdf_file, (str, os.PathLike)) and os.path.exists(pdf_file):
            try:
                os.remove(pdf_file)
            except OSError:
                pass


def _deadline_template_flags():
    subject_template = setting_value('notification_deadline_subject_template', default_deadline_subject_template()) or default_deadline_subject_template()
    body_template = setting_value('notification_deadline_body_template', default_deadline_body_template()) or default_deadline_body_template()
    text = (subject_template + '\n' + body_template).lower()
    return {
        'attach_report': '%report%' in text,
        'attach_statistics': '%statistics%' in text,
    }


def _statistics_pdf_for_deadline_notification():
    _, raw_periods = _build_stats_rows(include_search=False)
    from .reports import _period_statistics
    periods = [_period_statistics(p['name'], p['incidents'], p.get('start'), p.get('end')) for p in raw_periods]
    return statistics_pdf(periods)

def _deadline_notification_already_sent_for_slot(incident_id, schedule_slot):
    """Evita reinvii multipli dello stesso riepilogo nello stesso slot.

    Lo scheduler di background può eseguire più poll all'interno dello stesso
    slot cron/intervallo. La deduplica è quindi per incidente e slot, non più
    sul solo ultimo controllo globale: se al primo poll non erano ancora
    presenti task pendenti, un poll successivo nello stesso slot li può ancora
    rilevare e inviare.
    """
    if not incident_id or not schedule_slot:
        return False
    slot_label = _deadline_slot_label(schedule_slot)
    marker = f'Incidente {int(incident_id)}; slot {slot_label}'
    return AuditLog.query.filter(
        AuditLog.operation_type == 'scheduler:deadline_notification_sent',
        AuditLog.details.contains(marker),
    ).first() is not None




def _deadline_notification_check_already_audited_for_slot(schedule_slot):
    """Evita record audit diagnostici ripetuti per lo stesso slot pianificato.

    Il thread di background effettua poll frequenti: il record
    scheduler:deadline_notification_check deve essere scritto una sola volta
    per slot quando non ci sono invii, oppure in occasione di un invio reale.
    """
    if not schedule_slot:
        return False
    slot_label = _deadline_slot_label(schedule_slot)
    marker_json = f'"schedule_slot": "{slot_label}"'
    marker_text = f'slot {slot_label}'
    return AuditLog.query.filter(
        AuditLog.operation_type == 'scheduler:deadline_notification_check',
        db.or_(AuditLog.details.contains(marker_json), AuditLog.details.contains(marker_text)),
    ).first() is not None

def send_deadline_summary_email(inc, pending_rows):
    recipients = _deadline_recipients_for_incident(inc)
    if not recipients:
        return False, 'nessun indirizzo email nel personale coinvolto'
    host = setting_value('smtp_host')
    if not host:
        return False, 'SMTP non configurato'
    sender = smtp_sender_address()
    subject, body = build_deadline_email_content(inc, pending_rows, recipients)
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    msg.set_content(body)
    flags = _deadline_template_flags()
    if flags['attach_report']:
        _email_add_pdf_attachment_from_path_or_buffer(msg, incident_pdf(inc), f'incident-{inc.id}-report.pdf')
    if flags['attach_statistics']:
        _email_add_pdf_attachment_from_path_or_buffer(msg, _statistics_pdf_for_deadline_notification(), 'statistiche-incidenti.pdf')
    try:
        port = int(setting_value('smtp_port', '587') or '587')
    except ValueError:
        return False, 'porta SMTP non valida'
    smtp_cls = smtplib.SMTP_SSL if setting_value('smtp_use_ssl', '0') == '1' else smtplib.SMTP
    with _scheduler_mail_send_lock:
        with smtp_cls(host, port, timeout=20) as smtp:
            if setting_value('smtp_use_tls', '1') == '1' and setting_value('smtp_use_ssl', '0') != '1':
                smtp.starttls()
            if setting_value('smtp_auth_enabled', '0') == '1':
                username = setting_value('smtp_username')
                if not username:
                    return False, 'autenticazione SMTP abilitata senza username'
                smtp.login(username, setting_value('smtp_password') or '')
            smtp.send_message(msg)
    return True, ', '.join(recipients)




def _split_email_list(value):
    if not value:
        return []
    parts = re.split(r'[,;\n]+', value)
    return [p.strip() for p in parts if p and p.strip()]

def _reminder_subject(reminder):
    inc = reminder.incident
    return f'Promemoria incidente: {inc.name if inc else reminder.incident_id}'

def _reminder_body(reminder, now=None):
    inc = reminder.incident
    when_text = format_application_datetime(reminder.scheduled_at) if reminder.scheduled_at else '-'
    generated_at = format_application_datetime(now or application_now())
    return (
        f'Promemoria specifico per incidente.\n\n'
        f'Incidente: {inc.name if inc else reminder.incident_id}\n'
        f'Riferimento: {(inc.reference if inc else "") or "-"}\n'
        f'Data e ora promemoria: {when_text}\n\n'
        f'Messaggio:\n{strip_markdown_formatting(reminder.message or "")}\n\n'
        f'Link diretto incidente: {incident_absolute_url(inc) if inc else "-"}\n\n'
        f'Questa mail è stata generata automaticamente da Cybersecurity Incident Registry il {generated_at}.\n'
        f'Accesso applicazione: {setting_value("application_external_url", "http://localhost:8000") or "http://localhost:8000"}'
    )

def send_incident_reminder_email(reminder):
    inc = reminder.incident
    recipients = _incident_reminder_recipients(reminder)
    if not recipients:
        return False, 'nessun indirizzo email nel personale associato all incidente'
    host = setting_value('smtp_host')
    if not host:
        return False, 'SMTP non configurato'
    sender = smtp_sender_address()
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    cc_list = _split_email_list(reminder.cc_emails)
    if cc_list:
        msg['Cc'] = ', '.join(cc_list)
    msg['Subject'] = _reminder_subject(reminder)
    msg.set_content(_reminder_body(reminder))
    try:
        port = int(setting_value('smtp_port', '587') or '587')
    except ValueError:
        return False, 'porta SMTP non valida'
    smtp_cls = smtplib.SMTP_SSL if setting_value('smtp_use_ssl', '0') == '1' else smtplib.SMTP
    with _scheduler_mail_send_lock:
        with smtp_cls(host, port, timeout=20) as smtp:
            if setting_value('smtp_use_tls', '1') == '1' and setting_value('smtp_use_ssl', '0') != '1':
                smtp.starttls()
            if setting_value('smtp_auth_enabled', '0') == '1':
                username = setting_value('smtp_username')
                if not username:
                    return False, 'autenticazione SMTP abilitata senza username'
                smtp.login(username, setting_value('smtp_password') or '')
            smtp.send_message(msg)
    return True, ', '.join(recipients + cc_list)

def _incident_reminder_notification_key(reminder_id):
    return f'incident_reminder:{int(reminder_id)}'

def _incident_reminder_recipients(reminder):
    """Restituisce i destinatari effettivi di un promemoria specifico.

    IncidentReminder non persiste una colonna ``recipient_emails``: i
    destinatari sono ricavati dal personale associato all'incidente, mentre i
    CC sono memorizzati nel promemoria. Questa funzione centralizza la logica
    usata sia per l'invio sia per gli audit, evitando accessi ad attributi non
    presenti nel modello.
    """
    inc = reminder.incident if reminder else None
    return sorted({(p.email or '').strip() for p in (inc.people or []) if (p.email or '').strip()}) if inc else []


def _reminder_audit_details(reminder):
    """Dettagli stabili del promemoria specifico per audit e diagnostica."""
    if not reminder:
        return {}
    message = (reminder.message or '').strip()
    if len(message) > 240:
        message = message[:237] + '...'
    recipients = _incident_reminder_recipients(reminder)
    return {
        'reminder_id': reminder.id,
        'reminder_scheduled_at': reminder.scheduled_at.isoformat(timespec='seconds') if reminder.scheduled_at else None,
        'reminder_sent_at': reminder.sent_at.isoformat(timespec='seconds') if reminder.sent_at else None,
        'reminder_message': message,
        'reminder_recipient_emails': ', '.join(recipients),
        'reminder_cc_emails': reminder.cc_emails or '',
        'reminder_last_error': reminder.last_error or '',
    }

def _reminder_skip_label(reminder, reason):
    """Testo leggibile per il risultato del controllo manuale promemoria."""
    if not reminder:
        return reason or 'promemoria non disponibile'
    inc = reminder.incident
    when_text = format_application_datetime(reminder.scheduled_at, include_timezone=True) if reminder.scheduled_at else '-'
    message = (reminder.message or '').strip().replace('\n', ' ')
    if len(message) > 120:
        message = message[:117] + '...'
    inc_label = f"incidente #{reminder.incident_id}"
    if inc and inc.name:
        inc_label += f" - {inc.name}"
    parts = [f"Promemoria #{reminder.id}", inc_label, f"programmato {when_text}"]
    if message:
        parts.append(f"messaggio: {message}")
    parts.append(f"motivo: {reason or 'notifica saltata'}")
    return ' | '.join(parts)

def _deadline_recipients_for_incident(inc):
    """Destinatari effettivi delle notifiche task in scadenza."""
    return sorted({(p.email or '').strip() for p in (inc.people or []) if (p.email or '').strip()}) if inc else []

def _deadline_recipients_text_for_incident(inc):
    return ', '.join(_deadline_recipients_for_incident(inc))

def _audit_scheduler_notification_skip(operation_type, incident=None, incident_id=None, reason='', reason_code='', source='scheduler', **extra):
    """Registra in audit il motivo per cui lo scheduler salta una notifica.

    Ogni record include sempre l'incidente interessato, quando disponibile, e
    una motivazione leggibile. Il dettaglio è volutamente sintetico per restare
    compatibile con il meccanismo anti-flooding dell'audit log.
    """
    resolved_incident_id = incident_id or getattr(incident, 'id', None)
    payload = {
        'incident_id': resolved_incident_id,
        'incident_name': getattr(incident, 'name', None),
        'incident_reference': getattr(incident, 'reference', None),
        'reason_code': reason_code or '',
        'reason': reason or reason_code or 'notifica saltata dallo scheduler',
        'source': source,
    }
    payload.update({k: v for k, v in extra.items() if v is not None})
    audit_log(operation_type, json.dumps(payload, ensure_ascii=False), actor_type='scheduler')


def _claim_incident_reminder(reminder, source='scheduler'):
    """Blocca atomicamente il record del promemoria e verifica solo ``sent_at``.

    Per i promemoria specifici non esiste più un blocco funzionale basato su
    claim, slot, finestra o "presa in carico". L'unica condizione che impedisce
    l'invio è ``IncidentReminder.sent_at`` già valorizzato.

    Su PostgreSQL viene acquisito un lock di riga sul promemoria: un eventuale
    ciclo concorrente attende il completamento dell'invio in corso e poi
    rivaluta ``sent_at``. In questo modo il promemoria viene spedito una sola
    volta senza saltarlo perché risulta già preso in carico. La tabella
    ``deadline_notification_state`` viene aggiornata solo come diagnostica e
    non partecipa alla decisione di invio.
    """
    if not reminder or not reminder.id:
        return False
    try:
        locked = IncidentReminder.query.filter_by(id=reminder.id).with_for_update().first()
        if not locked or locked.sent_at:
            if locked and locked is not reminder:
                reminder.sent_at = locked.sent_at
            return False
        # Stato puramente diagnostico: nessun errore o race su questa tabella
        # deve bloccare l'invio del promemoria.
        try:
            key = _incident_reminder_notification_key(reminder.id)
            state = DeadlineNotificationState.query.filter_by(notification_key=key).first()
            if not state:
                state = DeadlineNotificationState(
                    notification_key=key,
                    notification_type='incident_reminder',
                    incident_id=reminder.incident_id,
                    last_schedule_slot=None,
                    send_count=0,
                )
                db.session.add(state)
            state.notification_type = 'incident_reminder'
            state.incident_id = reminder.incident_id
            state.last_success_at = application_now()
            state.last_schedule_slot = None
            state.last_recipients = ''
            state.last_details = f'promemoria in invio; sorgente {source}'
            state.send_count = 0
            state.updated_at = utcnow()
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            # Dopo rollback il lock è stato rilasciato: riacquisirlo e
            # rivalutare soltanto sent_at, senza trattare il claim come blocco.
            locked = IncidentReminder.query.filter_by(id=reminder.id).with_for_update().first()
            return bool(locked and not locked.sent_at)
        except Exception:
            current_app.logger.exception('Aggiornamento diagnostico claim promemoria non completato per promemoria %s', getattr(reminder, 'id', '-'))
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Lock promemoria incidente non completato per promemoria %s', getattr(reminder, 'id', '-'))
        return False

def _record_incident_reminder_claim_result(reminder, ok, info=''):
    if not reminder or not reminder.id:
        return
    state = DeadlineNotificationState.query.filter_by(notification_key=_incident_reminder_notification_key(reminder.id)).first()
    if state:
        state.notification_type = 'incident_reminder'
        state.incident_id = reminder.incident_id
        state.last_success_at = application_now()
        state.last_schedule_slot = None
        state.last_recipients = info if ok else ''
        state.last_details = ('Promemoria inviato' if ok else f'Promemoria non inviato: {info}')
        state.send_count = 1 if ok else 0
        state.updated_at = utcnow()

def _audit_has_reminder_sent(reminder_id):
    pattern = f'"reminder_id": {int(reminder_id)}'
    return AuditLog.query.filter(AuditLog.operation_type=='scheduler:incident_reminder_sent', AuditLog.details.contains(pattern)).first() is not None


def _scheduler_json_setting(key, default=None):
    raw = setting_value(key, '')
    if not raw:
        return default if default is not None else {}
    try:
        return json.loads(raw)
    except Exception:
        return default if default is not None else {}


def _record_scheduler_cycle(kind, result=None, started_at=None, ended_at=None, status='ok', error=''):
    """Persist a compact diagnostic snapshot for Admin -> Stato."""
    started_at = started_at or application_now()
    ended_at = ended_at or application_now()
    result = result or {}
    key = f'scheduler_status_{kind}'
    previous = _scheduler_json_setting(key, {})
    cycles = int(previous.get('cycles') or 0) + 1
    failed_cycles = int(previous.get('failed_cycles') or 0) + (1 if status != 'ok' else 0)
    payload = {
        'kind': kind,
        'status': status,
        'error': str(error or ''),
        'cycles': cycles,
        'failed_cycles': failed_cycles,
        'started_at': started_at.isoformat(timespec='minutes'),
        'ended_at': ended_at.isoformat(timespec='minutes'),
        'last_result': result,
        'source': result.get('source') or 'background_scheduler',
    }
    set_setting_value(key, json.dumps(payload, ensure_ascii=False))
    set_setting_value('scheduler_last_heartbeat_at', ended_at.isoformat(timespec='minutes'))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Aggiornamento stato scheduler non completato per %s', kind)


def run_scheduler_services_cycle(source='background_scheduler'):
    """Esegue il solo controllo delle notifiche periodiche task.

    I promemoria specifici sono gestiti da un thread separato, con intervallo
    configurabile dalle impostazioni notifiche, per rendere visibile e
    indipendente il loro ciclo operativo.
    """
    started = application_now()
    try:
        result = run_deadline_notification_check(force=False, source=source)
        _record_scheduler_cycle('deadline_notifications', result=result, started_at=started, ended_at=application_now(), status='ok')
        return {'deadline_notifications': result}
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Ciclo scheduler deadline_notifications non completato')
        result = {'source': source, 'errors': [str(exc)], 'executed': False}
        _record_scheduler_cycle('deadline_notifications', result=result, started_at=started, ended_at=application_now(), status='error', error=str(exc))
        return {'deadline_notifications': result}


def scheduler_service_status():
    """Return diagnostic info for the admin status page."""
    now = application_now()
    poll_seconds = deadline_scheduler_poll_seconds()
    due_reminders = IncidentReminder.query.filter(IncidentReminder.sent_at.is_(None), IncidentReminder.scheduled_at <= now).count()
    future_reminders = IncidentReminder.query.filter(IncidentReminder.sent_at.is_(None), IncidentReminder.scheduled_at > now).count()
    sent_reminders = IncidentReminder.query.filter(IncidentReminder.sent_at.isnot(None)).count()
    open_incidents = Incident.query.filter(Incident.status != 'chiuso').count()
    pending_deadline_incidents = 0
    for inc in Incident.query.filter(Incident.status != 'chiuso', Incident.deadline_notifications_muted.is_(False)).all():
        if pending_deadline_actions_for_incident(inc, now=now):
            pending_deadline_incidents += 1
    backup_jobs = BackupJob.query.order_by(BackupJob.id).all()
    return {
        'now': format_application_datetime(now, include_timezone=True),
        'timezone': application_timezone_name(),
        'thread_started': _deadline_scheduler_started,
        'thread_active': bool(_deadline_scheduler_thread and _deadline_scheduler_thread.is_alive()),
        'thread_name': 'cir-deadline-notification-scheduler',
        'reminder_thread_started': _incident_reminder_scheduler_started,
        'reminder_thread_active': bool(_incident_reminder_scheduler_thread and _incident_reminder_scheduler_thread.is_alive()),
        'reminder_thread_name': 'cir-incident-reminder-scheduler',
        'reminder_poll_seconds': incident_reminder_poll_seconds(),
        'enabled_by_env': os.getenv('CIR_ENABLE_DEADLINE_SCHEDULER', '1').lower() not in {'0', 'false', 'no'},
        'poll_seconds': poll_seconds,
        'last_heartbeat_at': setting_value('scheduler_last_heartbeat_at', '-'),
        'deadline': _scheduler_json_setting('scheduler_status_deadline_notifications', {}),
        'reminders': _scheduler_json_setting('scheduler_status_incident_reminders', {}),
        'last_incident_reminder_check_at': (_scheduler_json_setting('scheduler_status_incident_reminders', {}) or {}).get('ended_at') or '-',
        'deadline_schedule': format_deadline_schedule_info(),
        'backup': {
            'thread_started': _backup_scheduler_started,
            'thread_active': bool(_backup_scheduler_thread and _backup_scheduler_thread.is_alive()) if '_backup_scheduler_thread' in globals() else False,
            'enabled_jobs': sum(1 for j in backup_jobs if j.enabled),
            'jobs': [
                {
                    'name': j.name,
                    'enabled': j.enabled,
                    'cron_expression': j.cron_expression,
                    'destination': j.destination,
                    'last_run_at': format_application_datetime(j.last_run_at, include_timezone=True) if j.last_run_at else '-',
                    'last_status': j.last_status or 'never',
                    'last_message': j.last_message or '',
                } for j in backup_jobs
            ],
        },
        'counts': {
            'open_incidents': open_incidents,
            'pending_deadline_incidents': pending_deadline_incidents,
            'due_reminders': due_reminders,
            'future_reminders': future_reminders,
            'sent_reminders': sent_reminders,
        },
    }

def process_due_incident_reminders(source='background_scheduler'):
    now = application_now()
    due = IncidentReminder.query.filter(IncidentReminder.sent_at.is_(None), IncidentReminder.scheduled_at <= now).order_by(IncidentReminder.scheduled_at.asc(), IncidentReminder.id.asc()).all()
    sent = skipped = 0
    errors = []
    skipped_details = []
    for reminder in due:
        # Per i promemoria specifici il criterio funzionale è esclusivamente
        # incident_reminder.sent_at: un record viene inviato solo se non è già
        # marcato come inviato. Audit e stati tecnici non sostituiscono questo
        # flag, ma servono solo per tracciamento e claim anti-concorrenza.
        if reminder.sent_at:
            skipped += 1
            reason_text = 'promemoria già marcato come inviato tramite sent_at'
            skipped_details.append(_reminder_skip_label(reminder, reason_text))
            _audit_scheduler_notification_skip(
                'scheduler:incident_reminder_skipped',
                incident=reminder.incident,
                incident_id=reminder.incident_id,
                **_reminder_audit_details(reminder),
                reason_code='already_sent',
                reason=reason_text,
                source=source,
            )
            continue
        if not _claim_incident_reminder(reminder, source=source):
            # Il lock di riga non è un criterio di salto: se qui arriviamo, il
            # promemoria non è inviabile solo perché risulta già marcato come
            # inviato dopo la rivalutazione atomica di sent_at oppure per un
            # errore tecnico di lock. Non viene mai riportato come “preso in
            # carico” da un altro ciclo.
            skipped += 1
            if reminder.sent_at:
                reason_code = 'already_sent'
                reason_text = 'promemoria già marcato come inviato tramite sent_at'
            else:
                reason_code = 'lock_error'
                reason_text = 'impossibile acquisire il lock tecnico del promemoria'
                errors.append(f'Promemoria {reminder.id}: {reason_text}')
            skipped_details.append(_reminder_skip_label(reminder, reason_text))
            _audit_scheduler_notification_skip(
                'scheduler:incident_reminder_skipped',
                incident=reminder.incident,
                incident_id=reminder.incident_id,
                **_reminder_audit_details(reminder),
                reason_code=reason_code,
                reason=reason_text,
                source=source,
            )
            continue
        ok, info = send_incident_reminder_email(reminder)
        if ok:
            reminder.sent_at = now
            reminder.last_error = ''
            sent += 1
            _record_incident_reminder_claim_result(reminder, True, info)
            audit_log('scheduler:incident_reminder_sent', json.dumps({'reminder_id': reminder.id, 'incident_id': reminder.incident_id, 'scheduled_at': reminder.scheduled_at.isoformat(timespec='seconds'), 'recipients': info, 'source': source}, ensure_ascii=False), actor_type='scheduler')
            db.session.commit()
        else:
            reminder.last_error = info
            skipped += 1
            skipped_details.append(_reminder_skip_label(reminder, info))
            _record_incident_reminder_claim_result(reminder, False, info)
            _audit_scheduler_notification_skip(
                'scheduler:incident_reminder_skipped',
                incident=reminder.incident,
                incident_id=reminder.incident_id,
                **_reminder_audit_details(reminder),
                reason_code='send_failed',
                reason=info,
                source=source,
            )
            errors.append(f'Promemoria {reminder.id}: {info}')
            db.session.commit()
    result = {'source': source, 'due': len(due), 'sent': sent, 'skipped': skipped, 'errors': errors, 'skipped_details': skipped_details, 'executed': True}
    audit_log('scheduler:incident_reminder_check', json.dumps({**result, 'errors': errors[:10], 'skipped_details': skipped_details[:20]}, ensure_ascii=False), actor_type='scheduler')
    purge_audit_logs()
    db.session.commit()
    return result

def run_deadline_notification_check(force=False, source='request'):
    """Controlla e invia le notifiche periodiche dei task in scadenza.

    La pianificazione cron/intervallo decide quando eseguire il controllo, ma
    la deduplica dell'invio è per incidente e slot. Il record audit globale
    viene scritto solo quando lo slot pianificato è effettivamente dovuto
    oppure quando vengono inviate notifiche, evitando rumore dai poll tecnici.
    """
    now = application_now()
    if force or source == 'manual_button':
        try:
            align_all_table_sequences()
        except Exception:
            current_app.logger.exception('Riallineamento sequence prima del controllo scadenze non completato')
    schedule_slot, next_schedule_slot = deadline_schedule_window(now)
    stale_states_removed = cleanup_stale_deadline_notification_states()

    if setting_value('notification_deadline_enabled', '0') != '1' and not force:
        return {'sent': 0, 'skipped': 0, 'errors': [], 'executed': False, 'reason': 'disabled'}
    if setting_value('notification_deadline_email_enabled', '1') != '1':
        result = {
            'sent': 0, 'skipped': 0,
            'errors': ['Invio email per task in scadenza disabilitato nelle impostazioni notifiche'],
            'executed': True, 'source': source,
            'schedule_slot': schedule_slot.isoformat(timespec='minutes'),
            'next_run_at': next_schedule_slot.isoformat(timespec='minutes'),
        }
        if force or not _deadline_notification_check_already_audited_for_slot(schedule_slot):
            audit_log('scheduler:deadline_notification_check', json.dumps(result, ensure_ascii=False), actor_type='scheduler')
            db.session.commit()
            if str(db.engine.url).startswith('postgresql'):
                try:
                    align_all_table_sequences()
                except Exception:
                    current_app.logger.exception('Riallineamento generale sequence post-import fallito')
            purge_audit_logs()
            db.session.commit()
        return result

    # Se la modalità cron prevede solo slot futuri nella giornata corrente,
    # current_deadline_schedule_slot restituisce l'ultimo slot del giorno
    # precedente. In quel caso il controllo automatico deve attendere il primo
    # slot odierno; il pulsante manuale resta sempre disponibile.
    if not force and schedule_slot.date() < now.date():
        return {
            'sent': 0, 'skipped': 0, 'errors': [], 'executed': False,
            'reason': 'waiting_for_first_scheduled_slot',
            'next_run_at': next_schedule_slot.isoformat(timespec='minutes'),
        }

    sent = skipped = 0
    errors = []
    incidents_checked = 0
    incidents_with_pending = 0
    incidents_already_sent = 0
    incidents_without_recipients = 0
    incidents = Incident.query.filter(Incident.status != 'chiuso', Incident.deadline_notifications_muted.is_(False)).all()
    for inc in incidents:
        incidents_checked += 1
        rows = pending_deadline_actions_for_incident(inc, now=now)
        if not rows:
            continue
        incidents_with_pending += 1
        if _deadline_notification_sent_in_current_window(inc.id, schedule_slot, next_schedule_slot):
            incidents_already_sent += 1
            skipped += 1
            _audit_scheduler_notification_skip(
                'scheduler:deadline_notification_skipped',
                incident=inc,
                schedule_slot=schedule_slot.isoformat(timespec='minutes'),
                schedule_window_end=next_schedule_slot.isoformat(timespec='minutes') if next_schedule_slot else None,
                pending_actions=len(rows),
                reason_code='already_sent_in_window',
                reason='notifica dello stesso tipo già inviata o già presa in carico nello slot corrente',
                source=source,
            )
            continue
        if not _claim_deadline_notification_slot(inc.id, schedule_slot, source=source):
            incidents_already_sent += 1
            skipped += 1
            _audit_scheduler_notification_skip(
                'scheduler:deadline_notification_skipped',
                incident=inc,
                schedule_slot=schedule_slot.isoformat(timespec='minutes'),
                schedule_window_end=next_schedule_slot.isoformat(timespec='minutes') if next_schedule_slot else None,
                pending_actions=len(rows),
                reason_code='claim_not_acquired',
                reason='notifica già presa in carico da un altro ciclo scheduler o invio concorrente',
                source=source,
            )
            continue
        try:
            ok, info = send_deadline_summary_email(inc, rows)
            if ok:
                sent += 1
                _record_deadline_notification_success(
                    inc.id,
                    schedule_slot,
                    info,
                    details=f'Notifica task in scadenza inviata; slot {_deadline_slot_label(schedule_slot)}; sorgente {source}',
                )
                audit_log(
                    'scheduler:deadline_notification_sent',
                    f'Incidente {inc.id}; slot {_deadline_slot_label(schedule_slot)}; destinatari {info}; sorgente {source}',
                    actor_type='scheduler',
                )
                db.session.commit()
            else:
                skipped += 1
                if 'nessun indirizzo email' in info or 'personale' in info:
                    incidents_without_recipients += 1
                _record_deadline_notification_failure(inc.id, schedule_slot, info)
                _audit_scheduler_notification_skip(
                    'scheduler:deadline_notification_skipped',
                    incident=inc,
                    schedule_slot=schedule_slot.isoformat(timespec='minutes'),
                    schedule_window_end=next_schedule_slot.isoformat(timespec='minutes') if next_schedule_slot else None,
                    pending_actions=len(rows),
                    reason_code='send_failed',
                    reason=info,
                    source=source,
                )
                errors.append(f'Incidente {inc.id}: {info}')
                db.session.commit()
        except Exception as exc:
            current_app.logger.exception('Errore notifica scadenze incidente %s', inc.id)
            skipped += 1
            _record_deadline_notification_failure(inc.id, schedule_slot, str(exc))
            _audit_scheduler_notification_skip(
                'scheduler:deadline_notification_skipped',
                incident=inc,
                schedule_slot=schedule_slot.isoformat(timespec='minutes'),
                schedule_window_end=next_schedule_slot.isoformat(timespec='minutes') if next_schedule_slot else None,
                pending_actions=len(rows),
                reason_code='exception',
                reason=str(exc),
                source=source,
            )
            errors.append(f'Incidente {inc.id}: {exc}')
            db.session.commit()

    if not force:
        # Campo informativo per la pagina Notifiche: non viene più usato come
        # blocco globale dello slot, perché la deduplica avviene per incidente.
        set_setting_value('notification_deadline_last_run_at', schedule_slot.isoformat(timespec='minutes'))
    result = {
        'sent': sent,
        'skipped': skipped,
        'errors': errors,
        'executed': True,
        'source': source,
        'interval_minutes': raw_deadline_interval_minutes() if deadline_schedule_mode() == 'cron' else deadline_interval_minutes(),
        'schedule_mode': deadline_schedule_mode(),
        'cron_times': ','.join(format_minutes_as_hhmm(m) for m in parse_deadline_cron_times()),
        'schedule_slot': schedule_slot.isoformat(timespec='minutes'),
        'schedule_window_end': next_schedule_slot.isoformat(timespec='minutes'),
        'next_run_at': next_schedule_slot.isoformat(timespec='minutes'),
        'incidents_checked': incidents_checked,
        'incidents_with_pending': incidents_with_pending,
        'incidents_already_sent': incidents_already_sent,
        'incidents_without_recipients': incidents_without_recipients,
        'stale_states_removed': stale_states_removed,
    }
    should_audit_check = force or sent > 0 or not _deadline_notification_check_already_audited_for_slot(schedule_slot)
    if should_audit_check:
        audit_log('scheduler:deadline_notification_check', json.dumps({**result, 'errors': errors[:10]}, ensure_ascii=False), actor_type='scheduler')
        purge_audit_logs()
        db.session.commit()
    else:
        db.session.commit()
    return result


@bp.before_app_request
def maybe_run_deadline_notification_check():
    # Lo scheduler automatico non viene più eseguito dalle richieste HTTP.
    # In passato l'hook opportunistico poteva sovrapporsi al thread di
    # background o moltiplicarsi su più worker, producendo invii simultanei.
    # Le mail schedulate sono ora gestite solo dal thread dedicato avviato in
    # start_deadline_notification_scheduler(); il pulsante manuale resta
    # disponibile dalla pagina Admin → Notifiche.
    return



_deadline_scheduler_started = False
_incident_reminder_scheduler_started = False
_deadline_scheduler_thread = None
_incident_reminder_scheduler_thread = None
_deadline_scheduler_lock = threading.Lock()
_incident_reminder_scheduler_lock = threading.Lock()
_deadline_scheduler_stop_event = threading.Event()
_incident_reminder_scheduler_stop_event = threading.Event()
_scheduler_mail_send_lock = threading.Lock()
_CIR_SCHEDULER_LOCK_ID = 47110021
_CIR_REMINDER_SCHEDULER_LOCK_ID = 47110022


def _background_schedulers_disabled(app=None):
    """Return True when in-process background schedulers must not start."""
    return _background_schedulers_disabled_impl(app)


def stop_background_schedulers(timeout=2.0):
    """Ask all in-process scheduler threads to stop and wait briefly."""
    global _deadline_scheduler_started, _incident_reminder_scheduler_started, _backup_scheduler_started
    events = [_deadline_scheduler_stop_event, _incident_reminder_scheduler_stop_event]
    backup_event = globals().get('_backup_scheduler_stop_event')
    if backup_event is not None:
        events.append(backup_event)
    threads = [_deadline_scheduler_thread, _incident_reminder_scheduler_thread, globals().get('_backup_scheduler_thread')]
    alive = _stop_scheduler_threads(events, threads, timeout=timeout)
    if not (_deadline_scheduler_thread and _deadline_scheduler_thread.is_alive()):
        _deadline_scheduler_started = False
    if not (_incident_reminder_scheduler_thread and _incident_reminder_scheduler_thread.is_alive()):
        _incident_reminder_scheduler_started = False
    if not (globals().get('_backup_scheduler_thread') and globals().get('_backup_scheduler_thread').is_alive()):
        _backup_scheduler_started = False
    if alive and has_app_context():
        current_app.logger.warning('Scheduler thread ancora attivi dopo stop: %s', ', '.join(alive))

def _scheduler_poll_seconds_setting(key, default=60):
    """Legge un intervallo scheduler solo quando esiste un app context.

    I thread di background non devono accedere a ``Setting.query`` o ad altri
    proxy Flask-SQLAlchemy fuori da ``app.app_context()``: in caso contrario
    Werkzeug solleva ``RuntimeError: Working outside of application context``.
    Il fallback consente anche a chiamate diagnostiche fuori contesto di non
    interrompere il thread.
    """
    try:
        if has_app_context():
            value = int(setting_value(key, str(default)) or str(default))
        else:
            value = int(os.getenv(key.upper(), str(default)) or str(default))
    except (TypeError, ValueError, RuntimeError):
        value = default
    return max(10, value)


def incident_reminder_poll_seconds():
    """Intervallo configurabile del thread dei promemoria specifici."""
    return _scheduler_poll_seconds_setting('notification_incident_reminder_poll_seconds', 60)


def deadline_scheduler_poll_seconds():
    """Intervallo configurabile del thread dei task in scadenza."""
    return _scheduler_poll_seconds_setting('notification_deadline_poll_seconds', 60)

def _try_database_scheduler_lock(lock_id=_CIR_SCHEDULER_LOCK_ID):
    """Acquire a PostgreSQL advisory lock for multi-replica deployments.

    Gunicorn workers and Kubernetes replicas can all start the in-process
    scheduler. The existing Python lock protects only a single process; this
    advisory lock makes every poll mutually exclusive across all processes that
    share the same PostgreSQL database. Non-PostgreSQL deployments keep using
    the local lock only.
    """
    if not str(db.engine.url).startswith('postgresql'):
        return True
    try:
        return bool(db.session.execute(text('SELECT pg_try_advisory_lock(:lock_id)'), {'lock_id': lock_id}).scalar())
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Impossibile acquisire il lock PostgreSQL dello scheduler')
        return False

def _release_database_scheduler_lock(lock_id=_CIR_SCHEDULER_LOCK_ID):
    if not str(db.engine.url).startswith('postgresql'):
        return
    try:
        db.session.execute(text('SELECT pg_advisory_unlock(:lock_id)'), {'lock_id': lock_id})
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Impossibile rilasciare il lock PostgreSQL dello scheduler')

def start_deadline_notification_scheduler(app):
    """Avvia il controllo periodico automatico delle notifiche in scadenza.

    Le notifiche schedulate vengono gestite esclusivamente da questo thread
    interno, indipendente dal traffico web. La funzione resta idempotente per
    evitare avvii duplicati nello stesso processo; nei deployment PostgreSQL
    il lock advisory serializza l'esecuzione fra worker o repliche.
    """
    global _deadline_scheduler_started, _deadline_scheduler_thread
    if _deadline_scheduler_started:
        return
    if _background_schedulers_disabled(app):
        app.logger.info('Scheduler notifiche task in scadenza non avviato nel contesto corrente')
        return
    if os.getenv('CIR_ENABLE_DEADLINE_SCHEDULER', '1').lower() in {'0', 'false', 'no'}:
        app.logger.info('Scheduler notifiche task in scadenza disabilitato da CIR_ENABLE_DEADLINE_SCHEDULER')
        return
    # Evita il doppio thread quando si usa il reloader di Flask in sviluppo.
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return
    _deadline_scheduler_stop_event.clear()
    _deadline_scheduler_started = True

    def loop():
        with app.app_context():
            poll_seconds = deadline_scheduler_poll_seconds()
        app.logger.info('Scheduler notifiche task in scadenza avviato con poll=%ss', poll_seconds)
        while not _deadline_scheduler_stop_event.is_set():
            with app.app_context():
                poll_seconds = deadline_scheduler_poll_seconds()
            if not _deadline_scheduler_lock.acquire(blocking=False):
                if _deadline_scheduler_stop_event.wait(poll_seconds):
                    break
                continue
            db_lock_acquired = False
            try:
                with app.app_context():
                    db_lock_acquired = _try_database_scheduler_lock()
                    if db_lock_acquired:
                        run_scheduler_services_cycle(source='background_scheduler')
            except Exception:
                try:
                    with app.app_context():
                        db.session.rollback()
                        app.logger.exception('Scheduler notifiche task in scadenza non completato')
                except Exception:
                    app.logger.exception('Scheduler notifiche task in scadenza non completato')
            finally:
                if db_lock_acquired:
                    try:
                        with app.app_context():
                            _release_database_scheduler_lock()
                    except Exception:
                        app.logger.exception('Rilascio lock scheduler non completato')
                _deadline_scheduler_lock.release()
            if _deadline_scheduler_stop_event.wait(poll_seconds):
                break

    t = threading.Thread(target=loop, name='cir-deadline-notification-scheduler', daemon=True)
    _deadline_scheduler_thread = t
    t.start()


def start_incident_reminder_scheduler(app):
    """Avvia il thread dedicato ai promemoria specifici degli incidenti."""
    global _incident_reminder_scheduler_started, _incident_reminder_scheduler_thread
    if _incident_reminder_scheduler_started:
        return
    if _background_schedulers_disabled(app):
        app.logger.info('Scheduler promemoria specifici non avviato nel contesto corrente')
        return
    if os.getenv('CIR_ENABLE_DEADLINE_SCHEDULER', '1').lower() in {'0', 'false', 'no'}:
        app.logger.info('Scheduler promemoria specifici disabilitato da CIR_ENABLE_DEADLINE_SCHEDULER')
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return
    _incident_reminder_scheduler_stop_event.clear()
    _incident_reminder_scheduler_started = True

    def loop():
        app.logger.info('Scheduler promemoria specifici avviato')
        while not _incident_reminder_scheduler_stop_event.is_set():
            with app.app_context():
                poll_seconds = incident_reminder_poll_seconds()
            if not _incident_reminder_scheduler_lock.acquire(blocking=False):
                if _incident_reminder_scheduler_stop_event.wait(poll_seconds):
                    break
                continue
            db_lock_acquired = False
            started = None
            try:
                with app.app_context():
                    started = application_now()
                    db_lock_acquired = _try_database_scheduler_lock(_CIR_REMINDER_SCHEDULER_LOCK_ID)
                    if db_lock_acquired:
                        result = process_due_incident_reminders(source='background_reminder_scheduler')
                        _record_scheduler_cycle('incident_reminders', result=result, started_at=started, ended_at=application_now(), status='ok')
            except Exception as exc:
                try:
                    with app.app_context():
                        db.session.rollback()
                        app.logger.exception('Scheduler promemoria specifici non completato')
                        _record_scheduler_cycle('incident_reminders', result={'source': 'background_reminder_scheduler', 'errors': [str(exc)], 'executed': False}, started_at=started or application_now(), ended_at=application_now(), status='error', error=str(exc))
                except Exception:
                    app.logger.exception('Aggiornamento stato scheduler promemoria non completato')
            finally:
                if db_lock_acquired:
                    try:
                        with app.app_context():
                            _release_database_scheduler_lock(_CIR_REMINDER_SCHEDULER_LOCK_ID)
                    except Exception:
                        app.logger.exception('Rilascio lock scheduler promemoria non completato')
                _incident_reminder_scheduler_lock.release()
            if _incident_reminder_scheduler_stop_event.wait(poll_seconds):
                break

    t = threading.Thread(target=loop, name='cir-incident-reminder-scheduler', daemon=True)
    _incident_reminder_scheduler_thread = t
    t.start()


@bp.before_app_request
def mark_auditable_request():
    g.audit_started_at = utcnow()

@bp.after_app_request
def record_auditable_request(response):
    try:
        if request.endpoint and request.endpoint.startswith('static'):
            return response
        if request.method not in {'POST','PUT','PATCH','DELETE'}:
            return response
        if response.status_code >= 400:
            return response
        details = json.dumps({
            'method': request.method,
            'path': request.path,
            'endpoint': request.endpoint,
            'status_code': response.status_code,
            'anchor': request.form.get('scroll_anchor') if request.form else None,
        }, ensure_ascii=False)
        audit_log(audit_operation_name(), details, actor_type='user')
        # Pulizia opportunistica della retention configurata.
        purge_audit_logs()
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Registrazione audit non completata')
    return response

@bp.route('/notifiche/tipi', methods=['GET','POST'])
@login_required
def notification_types():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method == 'POST':
        action = request.form.get('action','save')
        type_id = request.form.get('type_id', type=int)
        if action == 'delete':
            t = model_or_404(NotificationType, type_id)
            if NotificationTemplate.query.filter_by(kind=t.code).first():
                flash('Impossibile cancellare il tipo: esistono template associati. Cancellare o spostare prima i template.', 'error')
            elif t.code in ['user','csirt','dpo']:
                flash('I tipi predefiniti non possono essere cancellati.', 'error')
            else:
                db.session.delete(t); db.session.commit(); flash('Tipo di notifica cancellato')
            return redirect(url_for('main.notification_types'))
        code = (request.form.get('code') or '').strip().lower().replace(' ','_')
        label = (request.form.get('label') or '').strip()
        description = (request.form.get('description') or '').strip() or default_notification_type_description(label, code)
        mode = request.form.get('recipient_mode') or 'manual'
        enabled = bool(request.form.get('enabled'))
        if not code or not label:
            flash('Codice e nome del tipo sono obbligatori.', 'error')
        else:
            t = db.session.get(NotificationType, type_id) if type_id else NotificationType()
            if t.id and t.code in ['user','csirt','dpo'] and code != t.code:
                flash('Il codice dei tipi predefiniti non può essere modificato.', 'error')
            else:
                t.code=code; t.label=label; t.description=description; t.recipient_mode='manual'; t.recipient_setting_key=''; t.cc_setting_key=''; t.enabled=enabled
                db.session.add(t)
                try:
                    db.session.commit(); flash('Tipo di notifica salvato')
                except IntegrityError:
                    db.session.rollback(); flash('Esiste già un tipo di notifica con lo stesso codice.', 'error')
        return redirect(url_for('main.notification_types'))
    edit_id=request.args.get('edit', type=int)
    editing=db.session.get(NotificationType, edit_id) if edit_id else None
    return render_template('notification_types.html', types=notification_type_records(enabled_only=False), editing=editing)


@bp.route('/admin/stato')
@login_required
def admin_status():
    if not can_admin():
        return redirect(url_for('main.index'))
    return render_template('admin_status.html', status=scheduler_service_status())

@bp.route('/notifiche/impostazioni', methods=['GET','POST'])
@login_required
def notification_settings():
    if not can_admin(): return redirect(url_for('main.index'))
    keys = ['smtp_host','smtp_port','smtp_use_tls','smtp_use_ssl','smtp_auth_enabled','smtp_username','smtp_password','smtp_default_sender','notification_deadline_enabled','notification_deadline_email_enabled','notification_deadline_schedule_mode','notification_deadline_cron_times','notification_deadline_interval_hours','notification_deadline_interval_minutes','notification_deadline_poll_seconds','notification_deadline_subject_template','notification_deadline_body_template','notification_incident_reminder_poll_seconds']
    checkbox_keys = {'smtp_use_tls','smtp_use_ssl','smtp_auth_enabled','notification_deadline_enabled','notification_deadline_email_enabled'}
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        if action == 'test_smtp':
            test_email = request.form.get('test_email', '').strip()
            try:
                send_smtp_test_email(test_email)
                flash(f'Mail di prova inviata a {test_email}')
            except Exception as exc:
                current_app.logger.exception('Errore durante invio mail di prova SMTP')
                flash(f'Errore invio mail di prova: {exc}', 'error')
        elif action == 'run_deadline_check':
            try:
                result = run_deadline_notification_check(force=True, source='manual_button')
                msg = f"Controllo scadenze completato: {result['sent']} email inviate, {result['skipped']} incidenti saltati."
                if result.get('errors'):
                    msg += ' Dettagli: ' + '; '.join(result['errors'][:5])
                flash(msg, 'success' if not result.get('errors') else 'warning')
            except Exception as exc:
                current_app.logger.exception('Errore controllo scadenze azioni')
                flash(f'Errore controllo scadenze: {exc}', 'error')
        elif action == 'run_incident_reminder_check':
            try:
                result = process_due_incident_reminders(source='manual_button')
                msg = f"Controllo promemoria specifici completato: {result['sent']} email inviate, {result['skipped']} promemoria saltati, {result['due']} promemoria scaduti verificati."
                if result.get('errors'):
                    msg += ' Errori: ' + '; '.join(result['errors'][:5])
                if result.get('skipped_details'):
                    msg += ' Promemoria saltati: ' + '; '.join(result['skipped_details'][:10])
                flash(msg, 'success' if not result.get('errors') and not result.get('skipped_details') else 'warning')
            except Exception as exc:
                current_app.logger.exception('Errore controllo promemoria specifici')
                flash(f'Errore controllo promemoria specifici: {exc}', 'error')
        elif action == 'preview_deadline_template':
            # Salva temporaneamente il template inserito nella form e mostra
            # l'anteprima renderizzata con dati dimostrativi.
            for k in ['notification_deadline_subject_template','notification_deadline_body_template']:
                set_setting_value(k, request.form.get(k, ''))
            db.session.commit()
            unknown = deadline_template_unknown_placeholders(
                request.form.get('notification_deadline_subject_template', ''),
                request.form.get('notification_deadline_body_template', '')
            )
            if unknown:
                flash('Placeholder non riconosciuti nel template: ' + ', '.join(unknown), 'warning')
            flash('Anteprima template aggiornata con dati dimostrativi.', 'success')
        else:
            auth_enabled = bool(request.form.get('smtp_auth_enabled'))
            default_sender = request.form.get('smtp_default_sender', '').strip()
            if auth_enabled and not default_sender:
                flash('Il mittente SMTP predefinito è obbligatorio quando l’autenticazione SMTP è abilitata.', 'error')
            else:
                for k in keys:
                    if k in checkbox_keys:
                        set_setting_value(k, '1' if request.form.get(k) else '0')
                    else:
                        set_setting_value(k, request.form.get(k, ''))
                db.session.commit(); flash('Impostazioni notifiche salvate')
    defaults = {
        'smtp_port':'587','smtp_use_tls':'1','smtp_use_ssl':'0','smtp_auth_enabled':'0',
        'notification_deadline_enabled':'0','notification_deadline_email_enabled':'1',
        'notification_deadline_schedule_mode':'interval','notification_deadline_cron_times':'','notification_deadline_interval_hours':'24','notification_deadline_interval_minutes':'0','notification_deadline_poll_seconds':'60',
        'notification_deadline_subject_template': default_deadline_subject_template(),
        'notification_deadline_body_template': default_deadline_body_template(),
        'notification_incident_reminder_poll_seconds': '60',
    }
    settings = {k: setting_value(k, defaults.get(k,'')) for k in keys}
    preview_subject, preview_body = sample_deadline_preview()
    schedule_info = format_deadline_schedule_info()
    return render_template('notification_settings.html', settings=settings, deadline_placeholders=DEADLINE_NOTIFICATION_PLACEHOLDERS, preview_subject=preview_subject, preview_body=preview_body, schedule_info=schedule_info, upcoming_notifications=upcoming_scheduled_notifications())

@bp.route('/notifiche/template/nuovo', methods=['GET','POST'])
@login_required
def notification_template_new():
    if not can_admin(): return redirect(url_for('main.index'))
    ensure_default_notification_templates(); db.session.commit()
    kinds = notification_type_map()
    kind = request.values.get('kind', 'user')
    if kind not in kinds: kind = next(iter(kinds), 'user')
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        kind = request.form.get('kind','user')
        if kind not in kinds: kind = next(iter(kinds), 'user')
        if not name:
            flash('Nome template obbligatorio','error')
            return redirect(url_for('main.notification_template_new', kind=kind))
        tmpl = NotificationTemplate(kind=kind)
        tmpl.name = name
        tmpl.subject = request.form.get('subject','')
        tmpl.body = request.form.get('body','')
        tmpl.linked_form_template_name = request.form.get('linked_form_template_name') or None
        apply_notification_template_address_form(tmpl)
        action_label_id = request.form.get('action_label_id', type=int)
        tmpl.action_label_id = action_label_id or None
        if request.form.get('is_default'):
            NotificationTemplate.query.filter_by(kind=kind).update({'is_default': False})
            tmpl.is_default = True
        db.session.add(tmpl); db.session.commit(); flash('Template di notifica aggiunto')
        return redirect(url_for('main.notification_template', kind=kind))
    return render_template('notification_template.html', kind=kind, title='Nuovo template', fields=NOTIFICATION_FIELDS, templates=[], editing=None, adding=True, kinds=kinds, action_labels=labels('action_label'), form_templates=list_templates(), address_sources=notification_template_address_sources())

@bp.route('/notifiche/template/<kind>', methods=['GET','POST'])
@login_required
def notification_template(kind):
    if not can_admin(): return redirect(url_for('main.index'))
    kinds = notification_type_map()
    if kind not in kinds: abort(404)
    title = kinds[kind]
    ensure_default_notification_templates(); db.session.commit()
    edit_id = request.args.get('edit', type=int)
    editing = NotificationTemplate.query.filter_by(id=edit_id, kind=kind).first() if edit_id else None
    if request.method == 'POST':
        action = request.form.get('action','save')
        template_id = request.form.get('template_id', type=int)
        if action == 'delete':
            tmpl = NotificationTemplate.query.filter_by(id=template_id, kind=kind).first_or_404()
            db.session.delete(tmpl); db.session.commit(); flash(f'Template {title} cancellato')
            return redirect(url_for('main.notification_template', kind=kind))
        if action == 'clone':
            source = NotificationTemplate.query.filter_by(id=template_id, kind=kind).first_or_404()
            base_name = f'{source.name} - copia'
            candidate = base_name
            idx = 2
            while NotificationTemplate.query.filter_by(kind=kind, name=candidate).first():
                candidate = f'{base_name} {idx}'
                idx += 1
            clone = NotificationTemplate(
                kind=source.kind,
                name=candidate,
                subject=source.subject,
                body=source.body,
                linked_form_template_name=source.linked_form_template_name,
                action_label_id=source.action_label_id,
                recipient_source=source.recipient_source,
                recipient_value=source.recipient_value,
                recipient_editable=source.recipient_editable,
                recipient_external_allowed=source.recipient_external_allowed,
                cc_source=source.cc_source,
                cc_value=source.cc_value,
                cc_editable=source.cc_editable,
                cc_external_allowed=source.cc_external_allowed,
                is_default=False,
            )
            db.session.add(clone)
            db.session.commit()
            flash(f'Template "{source.name}" clonato come "{clone.name}"')
            return redirect(url_for('main.notification_template', kind=kind, edit=clone.id))
        if action == 'set_default':
            tmpl = NotificationTemplate.query.filter_by(id=template_id, kind=kind).first_or_404()
            NotificationTemplate.query.filter_by(kind=kind).update({'is_default': False})
            tmpl.is_default = True; db.session.commit(); flash(f'Template {tmpl.name} impostato come predefinito')
            return redirect(url_for('main.notification_template', kind=kind))
        if not template_id:
            flash('Usare la voce Notifiche → Aggiungi template per creare nuovi template.','error')
            return redirect(url_for('main.notification_template', kind=kind))
        name = request.form.get('name','').strip()
        if not name:
            flash('Nome template obbligatorio','error')
            return redirect(url_for('main.notification_template', kind=kind, edit=template_id))
        tmpl = NotificationTemplate.query.filter_by(id=template_id, kind=kind).first_or_404()
        tmpl.name = name
        tmpl.subject = request.form.get('subject','')
        tmpl.body = request.form.get('body','')
        tmpl.linked_form_template_name = request.form.get('linked_form_template_name') or None
        apply_notification_template_address_form(tmpl)
        action_label_id = request.form.get('action_label_id', type=int)
        tmpl.action_label_id = action_label_id or None
        if request.form.get('is_default'):
            NotificationTemplate.query.filter_by(kind=kind).update({'is_default': False})
            tmpl.is_default = True
        db.session.add(tmpl); db.session.commit(); flash(f'Template {title} salvato')
        return redirect(url_for('main.notification_template', kind=kind))
    templates = NotificationTemplate.query.filter_by(kind=kind).order_by(NotificationTemplate.is_default.desc(), NotificationTemplate.name).all()
    return render_template('notification_template.html', kind=kind, title=title, fields=NOTIFICATION_FIELDS, templates=templates, editing=editing, adding=False, action_labels=labels('action_label'), form_templates=list_templates(), address_sources=notification_template_address_sources())

@bp.route('/incident/<int:iid>/notify/<kind>/preview')
@login_required
def notify_preview(iid, kind):
    if kind not in notification_type_map(): abort(404)
    ntype = get_notification_type(kind)
    inc = visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if not can_write():
        flash('Permessi insufficienti per inviare notifiche','error')
        return redirect(url_for('main.incident_detail', iid=iid))
    admin_send_blocked = is_builtin_admin_user()
    if admin_send_blocked:
        flash('L’utente admin non può inviare notifiche dalla pagina degli incidenti. Accedere con un altro utente autorizzato.', 'error')
    ensure_default_notification_templates(); db.session.commit()
    template_id = request.args.get('template_id', type=int)
    tmpl = get_notification_template(kind, template_id)
    recipient, cc = resolve_template_notification_addresses(tmpl, kind, inc, ntype, args=request.args)
    recipient_locked = not bool(getattr(tmpl, 'recipient_editable', True))
    cc_locked = not bool(getattr(tmpl, 'cc_editable', True))
    # L'anteprima mostra il CC predefinito del template, se configurato.
    # Al submit, però, il campo manuale presente nella form ha priorità: se
    # l'operatore lo svuota esplicitamente viene inviato senza CC.
    address_editable = not recipient_locked or not cc_locked
    subject = notification_subject(kind, inc, tmpl.id)
    needs_documents = notification_needs_documents(kind, tmpl.id)
    attach_report = notification_needs_report(kind, tmpl.id)
    attach_statistics = notification_needs_statistics(kind, tmpl.id)
    body = notification_body(kind, inc, template_id=tmpl.id)
    title = ntype.label
    templates = NotificationTemplate.query.filter_by(kind=kind).order_by(NotificationTemplate.is_default.desc(), NotificationTemplate.name).all()
    auto_documents = auto_selected_notification_documents(inc, tmpl, kind)
    auto_document_ids = {d.id for d in auto_documents}
    linked_template_missing_warning = bool(tmpl.linked_form_template_name and not auto_documents)
    if linked_template_missing_warning:
        flash(f'Warning: non è presente nell’incidente alcun documento generato dal template associato "{tmpl.linked_form_template_name}" con tag notifica "{kind}". I documenti generati non taggati non vengono preselezionati automaticamente.', 'warning')
    if needs_documents and not inc.documents:
        flash('Il template contiene %DOCUMENTS%, ma non sono presenti documenti allegati all’incidente. Invio bloccato.', 'error')
    external_recipients = get_external_recipients() if address_editable and (getattr(tmpl, 'recipient_external_allowed', True) or getattr(tmpl, 'cc_external_allowed', True)) else []
    return render_template('notification_preview.html', inc=inc, kind=kind, title=title, sender=current_user.email or '', recipient=recipient, cc=cc, subject=subject, body=body, attach_report=attach_report, attach_statistics=attach_statistics, needs_documents=needs_documents, template=tmpl, templates=templates, recipient_locked=recipient_locked, cc_locked=cc_locked, address_editable=address_editable, auto_document_ids=auto_document_ids, linked_template_missing_warning=linked_template_missing_warning, external_recipients=external_recipients, admin_send_blocked=admin_send_blocked)

@bp.route('/incident/<int:iid>/notify/<kind>/send', methods=['POST'])
@login_required
def notify_send(iid, kind):
    if kind not in notification_type_map(): abort(404)
    ntype = get_notification_type(kind)
    inc = visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if not can_write():
        flash('Permessi insufficienti per inviare notifiche','error')
        return redirect(url_for('main.incident_detail', iid=iid))
    send_mode = (request.form.get('send_mode') or 'send').strip()
    confirm_without_send = send_mode == 'confirm_without_send'
    if is_builtin_admin_user() and not confirm_without_send:
        flash('L’utente admin non può inviare notifiche dalla pagina degli incidenti. Accedere con un altro utente autorizzato.', 'error')
        return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=request.form.get('template_id', type=int)))
    if confirm_without_send and request.form.get('confirm_without_send_confirmed') != '1':
        flash('Confermare esplicitamente l’operazione senza invio prima di registrare la notifica.', 'warning')
        return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=request.form.get('template_id', type=int)))
    template_id = request.form.get('template_id', type=int)
    tmpl = get_notification_template(kind, template_id)
    recipient, cc = resolve_template_notification_addresses(tmpl, kind, inc, ntype, form=request.form)
    if not split_addresses(recipient):
        flash('Invio bloccato: specificare almeno un destinatario per questa notifica.', 'error')
        return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id, recipient=recipient, cc=cc))
    invalid_recipients = invalid_email_addresses(recipient)
    if invalid_recipients:
        flash('Invio bloccato: destinatario non valido: ' + ', '.join(invalid_recipients), 'error')
        return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id, recipient=recipient, cc=cc))
    invalid_cc = invalid_email_addresses(cc)
    if invalid_cc:
        flash('Invio bloccato: indirizzo CC non valido: ' + ', '.join(invalid_cc), 'error')
        return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id, recipient=recipient, cc=cc))
    if (bool(getattr(tmpl, 'recipient_editable', True)) or bool(getattr(tmpl, 'cc_editable', True))) and request.form.get('recipient_confirmed') != '1':
        flash('Confermare destinatario e CC prima di completare la notifica.', 'warning')
        return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id, recipient=recipient, cc=cc))
    subject = notification_subject(kind, inc, tmpl.id)
    title = ntype.label
    attach_report = notification_needs_report(kind, tmpl.id)
    attach_statistics = notification_needs_statistics(kind, tmpl.id)
    needs_documents = notification_needs_documents(kind, tmpl.id)
    selected_ids = [int(x) for x in request.form.getlist('document_ids') if x.isdigit()]
    selected_documents = []
    if selected_ids:
        selected_documents = Document.query.filter(Document.incident_id == inc.id, Document.id.in_(selected_ids)).all()
        if len(selected_documents) != len(set(selected_ids)):
            flash('Invio bloccato: uno o più documenti selezionati non appartengono a questo incidente.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id))
    if needs_documents:
        if not inc.documents:
            flash('Invio bloccato: il template contiene %DOCUMENTS%, ma l’incidente non ha documenti allegati.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id))
        if not selected_ids:
            flash('Invio bloccato: selezionare almeno un documento da allegare perché il template contiene %DOCUMENTS%.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id))
    body = notification_body(kind, inc, selected_documents=selected_documents if selected_documents else None, template_id=tmpl.id)
    try:
        if confirm_without_send:
            try:
                simulated_sender = smtp_sender_address()
            except Exception:
                simulated_sender = (current_user.email or setting_value('smtp_default_sender', '') or setting_value('smtp_username', '') or 'admin@localhost.localdomain')
            send_info = {
                'sender': simulated_sender,
                'recipient': recipient,
                'cc': cc or '',
                'attach_report': attach_report,
                'attach_statistics': attach_statistics,
                'documents': [d.filename for d in (selected_documents or [])],
                'suppressed_send': True,
            }
        else:
            send_info = send_notification_email(kind, inc, recipient, cc, subject, body, attach_report, selected_documents=selected_documents, attach_statistics=attach_statistics)
        label = tmpl.action_label or ConfigLabel.query.filter_by(kind='action_label', value=notification_label_value(kind)).first()
        if not label:
            label = ConfigLabel(kind='action_label', group='azioni', value=notification_label_value(kind))
            db.session.add(label); db.session.flush()
        docs_text = ', '.join(send_info.get('documents') or []) or 'nessuno'
        if confirm_without_send:
            desc = f'Conferma senza invio {title.lower()} con template "{tmpl.name}". Nessuna email è stata trasmessa. Mittente previsto: {send_info["sender"]}; Destinatario previsto: {send_info["recipient"]}; CC previsto: {send_info["cc"] or "nessuno"}; Report PDF previsto: {"sì" if send_info["attach_report"] else "no"}; Report statistiche previsto: {"sì" if send_info.get("attach_statistics") else "no"}; Documenti previsti: {docs_text}.'
        else:
            desc = f'Invio {title.lower()} con template "{tmpl.name}". Mittente: {send_info["sender"]}; Destinatario: {send_info["recipient"]}; CC: {send_info["cc"] or "nessuno"}; Report PDF allegato: {"sì" if send_info["attach_report"] else "no"}; Report statistiche allegato: {"sì" if send_info.get("attach_statistics") else "no"}; Documenti allegati: {docs_text}.'
        action = add_notification_action_safely(inc, label, desc)
        pdf_path = None
        try:
            pdf_path, stored_pdf, pdf_name = make_notification_mail_pdf(inc, title, subject, body, send_info["sender"], send_info["recipient"], send_info["cc"])
            align_table_sequence('action_attachment')
            db.session.add(ActionAttachment(action_id=action.id, filename=pdf_name, stored_name=stored_pdf))
        except Exception:
            current_app.logger.exception('Errore nella generazione del PDF con il testo della mail inviata')
            raise
        db.session.commit()
        if confirm_without_send:
            flash('Notifica confermata senza invio: operazioni completate e azione registrata')
        else:
            flash('Notifica inviata e azione registrata')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Errore invio notifica %s incidente %s', kind, iid)
        flash(f'Errore invio notifica: {exc}', 'error')
    return redirect(url_for('main.incident_detail', iid=iid))

@bp.route('/aiuto')
@login_required
def help_page():
    return render_template('help_en.html' if getattr(g, 'lang', 'it') == 'en' else 'help.html')




@bp.route('/aiuto/note-rilascio')
@login_required
def release_notes():
    changelog_path = Path(current_app.root_path).parent / 'CHANGELOG.txt'
    changelog = changelog_path.read_text(encoding='utf-8') if changelog_path.exists() else ''
    return render_template('release_notes_en.html' if getattr(g, 'lang', 'it') == 'en' else 'release_notes.html', changelog=changelog)


@bp.route('/aiuto/note-rilascio/pdf')
@login_required
def release_notes_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from xml.sax.saxutils import escape
    buf = io.BytesIO()
    lang = getattr(g, 'lang', 'it')
    title = 'Release notes' if lang == 'en' else 'Note di rilascio'
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=1.6*cm, leftMargin=1.6*cm, topMargin=1.6*cm, bottomMargin=1.6*cm, title=title)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('release_h1', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#0f172a'), spaceAfter=12)
    normal = ParagraphStyle('release_normal', parent=styles['BodyText'], fontSize=9.2, leading=12.5, spaceAfter=4)
    story = [Paragraph(title, h1), Paragraph('Cybersecurity Incident Registry', normal), Spacer(1, .25*cm)]
    changelog_path = Path(current_app.root_path).parent / 'CHANGELOG.txt'
    lines = changelog_path.read_text(encoding='utf-8').splitlines() if changelog_path.exists() else []
    for line in lines:
        clean = line.strip()
        if not clean:
            story.append(Spacer(1, .12*cm)); continue
        story.append(Paragraph(escape(clean), normal))
    def page_canvas(canvas, doc_obj):
        canvas.saveState(); canvas.setFont('Helvetica', 8); canvas.drawRightString(A4[0]-1.6*cm, .8*cm, f'Pagina {doc_obj.page}' if lang != 'en' else f'Page {doc_obj.page}'); canvas.restoreState()
    doc.build(story, onFirstPage=page_canvas, onLaterPages=page_canvas)
    buf.seek(0)
    filename = 'cybersecurity-incident-registry-note-rilascio.pdf' if lang != 'en' else 'cybersecurity-incident-registry-release-notes.pdf'
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=filename)


@bp.route('/aiuto/amministrazione')
@login_required
def admin_help_page():
    """Pagina online ricercabile della documentazione amministrativa."""
    return render_template('admin_help_en.html' if getattr(g, 'lang', 'it') == 'en' else 'admin_help.html')


@bp.route('/aiuto/amministrazione/pdf')
@login_required
def admin_help_pdf():
    """Scarica una versione professionale della documentazione amministrativa in PDF."""
    import re
    from html import unescape
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, KeepTogether
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib import colors
    from xml.sax.saxutils import escape

    static_dir = Path(current_app.static_folder)
    logo_path = static_dir / 'help' / 'app-logo.png'
    visual_paths_by_chapter = {
        '1': [('Figura 1 - Flusso amministrativo consigliato', static_dir / 'help' / 'admin-flow.png')],
        '4': [('Figura 2 - Configurazione SSO e controllo connessione', static_dir / 'help' / 'admin-screenshot-sso.png')],
        '11': [('Figura 3 - Configurazione template PDF e mapping', static_dir / 'help' / 'admin-screenshot-modules.png')],
        '16': [('Figura 4 - Mappa delle aree di governance amministrativa', static_dir / 'help' / 'admin-chart-governance.png')],
    }

    html = render_template('admin_help_en.html' if getattr(g, 'lang', 'it') == 'en' else 'admin_help.html')
    html = re.sub(r'<(script|style|figure)[\s\S]*?</\1>', ' ', html, flags=re.I)
    html = re.sub(r'<nav[\s\S]*?</nav>', ' ', html, flags=re.I)
    html = re.sub(r'<li[^>]*>', '\n• ', html, flags=re.I)
    html = re.sub(r'</(p|h1|h2|h3|tr|section|div)>', '\n', html, flags=re.I)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    text = unescape(re.sub(r'<[^>]+>', ' ', html))
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    def is_pdf_noise(line):
        if not line:
            return True
        exact_noise = {'Salta al contenuto principale', 'Menu', '☰ Menu', 'n Menu', 'Alex', 'Logout', 'Scarica PDF', 'Scarica PDF amministrativo', 'Vai all’indice', 'Digita una parola per filtrare i capitoli.', 'Search administrator documentation', 'Type a word to filter chapters.'}
        if line in exact_noise:
            return True
        noise_fragments = (
            'Salta al contenuto principale',
            'Apri o chiudi menu',
            'Cerca nella documentazione',
            'Nessun capitolo contiene il testo cercato',
            'No chapter contains the searched text',
            'Vai all’indice',
            'Scarica PDF',
            'Logout',
            'Il logo presente in questa guida',
            'Questa guida riorganizza le funzioni amministrative',
            'Questa guida descrive lo stato operativo corrente',
            'AlBot anche Alex',
            'Helpdesk applicativo',
            'Ciao, sono AlBot',
            'Domanda per AlBot',
            'Invia',
        )
        if any(fragment in line for fragment in noise_fragments):
            return True
        if re.fullmatch(r'[A-Za-z0-9_.@ -]{2,80} · Logout', line):
            return True
        return False
    lines = [line for line in lines if not is_pdf_noise(line)]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.55*cm,
        leftMargin=1.55*cm,
        topMargin=1.65*cm,
        bottomMargin=1.55*cm,
        title='Cybersecurity Incident Registry - Administrator documentation' if getattr(g, 'lang', 'it') == 'en' else 'Cybersecurity Incident Registry - Documentazione amministrativa'
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle('admin_doc_normal', parent=styles['BodyText'], fontSize=9.1, leading=12.4, alignment=TA_LEFT, spaceAfter=4)
    bullet = ParagraphStyle('admin_doc_bullet', parent=normal, leftIndent=13, firstLineIndent=-8)
    h1 = ParagraphStyle('admin_doc_h1', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#0f172a'), spaceAfter=12, alignment=TA_CENTER)
    h2 = ParagraphStyle('admin_doc_h2', parent=styles['Heading2'], fontSize=13.5, leading=17, textColor=colors.HexColor('#1d4ed8'), spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle('admin_doc_h3', parent=styles['Heading3'], fontSize=11.2, leading=14, textColor=colors.HexColor('#334155'), spaceBefore=8, spaceAfter=4)
    caption = ParagraphStyle('admin_caption', parent=normal, fontSize=8.3, leading=10.5, textColor=colors.HexColor('#64748b'), alignment=TA_CENTER)
    callout = ParagraphStyle('admin_callout', parent=normal, backColor=colors.HexColor('#eef4ff'), borderColor=colors.HexColor('#bfdbfe'), borderWidth=0.7, borderPadding=7, spaceBefore=4, spaceAfter=8)

    def fitted_doc_image(path, max_width=16.3*cm, max_height=7.6*cm):
        try:
            iw, ih = ImageReader(str(path)).getSize()
            ratio = min(max_width / iw, max_height / ih)
            img = Image(str(path), width=iw * ratio, height=ih * ratio)
        except Exception:
            img = Image(str(path), width=max_width, height=max_height)
        img.hAlign = 'CENTER'
        return img

    info = current_app.config.get('APP_INFO', {})
    story = []
    if logo_path.exists():
        story.append(Image(str(logo_path), width=3.0*cm, height=3.0*cm)); story[-1].hAlign = 'CENTER'
    story.append(Paragraph('Cybersecurity Incident Registry', h1))
    story.append(Paragraph('Documentazione amministrativa completa', ParagraphStyle('admin_subtitle', parent=normal, alignment=TA_CENTER, fontSize=12, leading=15, textColor=colors.HexColor('#475569'))))
    story.append(Spacer(1, .2*cm))
    meta_rows = [
        ['Applicazione', info.get('name','Cybersecurity Incident Registry')],
        ['Versione', info.get('version','')],
        ['Build', info.get('build','')],
        ['Autore', f"{info.get('author','')} <{info.get('author_email','')}>"],
    ]
    meta = Table([[Paragraph(escape(a), normal), Paragraph(escape(str(b)), normal)] for a,b in meta_rows], colWidths=[4.1*cm, 11.5*cm])
    meta.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#dbeafe')),('BACKGROUND',(1,0),(1,-1),colors.HexColor('#f8fafc')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#cbd5e1')),('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor('#cbd5e1')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(meta)
    story.append(Spacer(1, .25*cm))
    story.append(Paragraph('Questa guida descrive l’amministrazione completa dell’applicazione: ruoli, utenti, LDAP, OAuth2/SSO, liste, categorie, notifiche, moduli PDF, documentazione, export, import, backup e controlli periodici.', callout))
    story.append(PageBreak())

    chapters = [line for line in lines if re.match(r'^\d+\.\s+', line)]
    if chapters:
        story.append(Paragraph('Indice', h2))
        tbl = [[Paragraph(escape(c), normal)] for c in chapters]
        t = Table(tbl, colWidths=[17.0*cm])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f8fafc')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e2e8f0')),('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor('#e2e8f0')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(t); story.append(PageBreak())

    def line_to_admin_flowable(line):
        if line.startswith('• '):
            return Paragraph(escape(line), bullet)
        if len(line) < 90 and (line.startswith('Esempio') or line.startswith('Configurazione') or line.startswith('Procedura') or line in {'Buone pratiche','Campi database incidenti','Misure adottate','Sostituzione template','Backup consigliato','Checklist mensile','SSO non funziona','Modulo PDF incompleto','Export o import non coerente'}):
            return Paragraph(escape(line), h3)
        return Paragraph(escape(line), normal)

    def admin_visual_flowables(chapter_number, inserted_visuals):
        flows = []
        for label, path in visual_paths_by_chapter.get(chapter_number, []):
            if path.exists() and label not in inserted_visuals:
                flows.extend([fitted_doc_image(path), Paragraph(escape(label), caption), Spacer(1, .2*cm)])
                inserted_visuals.add(label)
        return flows

    chapter_chunks = []
    current_number = None
    current_title = None
    current_body = []
    for line in lines:
        if line.startswith('Documentazione amministrativa') or line.startswith('Cybersecurity Incident Registry'):
            continue
        chapter_match = re.match(r'^(\d+)\.\s+', line)
        if chapter_match:
            if current_title and current_number:
                chapter_chunks.append((current_number, current_title, current_body))
            current_number = chapter_match.group(1)
            current_title = line
            current_body = []
        elif current_title:
            current_body.append(line)
        else:
            story.append(line_to_admin_flowable(line))
    if current_title and current_number:
        chapter_chunks.append((current_number, current_title, current_body))

    inserted_visuals = set()
    for chapter_number, chapter_title, body_lines in chapter_chunks:
        heading_flow = Paragraph(escape(chapter_title), h2)
        visual_flows = admin_visual_flowables(chapter_number, inserted_visuals)
        first_flows = []
        remaining_lines = list(body_lines)
        while remaining_lines and len(first_flows) < 2:
            candidate = remaining_lines.pop(0)
            first_flows.append(line_to_admin_flowable(candidate))
            if candidate.startswith('• '):
                break
        story.append(KeepTogether([heading_flow] + visual_flows + first_flows))
        i = 0
        while i < len(remaining_lines):
            line = remaining_lines[i]
            is_subheading = (
                re.match(r'^\d+[a-z]?\.\s+', line, flags=re.I)
                or (len(line) < 90 and (line.startswith('Esempio') or line.startswith('Configurazione') or line.startswith('Procedura') or line in {'Buone pratiche','Campi database incidenti','Misure adottate','Sostituzione template','Backup consigliato','Checklist mensile','SSO non funziona','Modulo PDF incompleto','Export o import non coerente'}))
            )
            if is_subheading and i + 1 < len(remaining_lines):
                story.append(KeepTogether([line_to_admin_flowable(line), line_to_admin_flowable(remaining_lines[i + 1])]))
                i += 2
            else:
                story.append(line_to_admin_flowable(line))
                i += 1

    def page_canvas(canvas, doc_obj):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#1d4ed8'))
        canvas.rect(0, A4[1]-0.65*cm, A4[0], 0.65*cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawString(1.55*cm, A4[1]-0.42*cm, 'Cybersecurity Incident Registry - Documentazione amministrativa')
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(A4[0]-1.55*cm, 0.8*cm, f'Pagina {doc_obj.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=page_canvas, onLaterPages=page_canvas)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name='cybersecurity-incident-registry-documentazione-amministrativa.pdf')

@bp.route('/aiuto/pdf')
@login_required
def help_pdf():
    """Scarica una versione professionale della documentazione utente in PDF."""
    import re
    from html import unescape
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, KeepTogether
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib import colors
    from xml.sax.saxutils import escape

    static_dir = Path(current_app.static_folder)
    logo_path = static_dir / 'help' / 'app-logo.png'
    visual_paths_by_chapter = {
        '1': [('Figura 1 - Flusso consigliato di gestione incidente', static_dir / 'help' / 'flow-incident-lifecycle.png')],
        '3': [('Figura 2 - Pagina principale con avvisi procedurali', static_dir / 'help' / 'screenshot-dashboard.png')],
        '5': [('Figura 3 - Dettaglio incidente e timeline azioni', static_dir / 'help' / 'screenshot-incident-detail.png')],
        '10': [
            ('Figura 4 - Configurazione moduli PDF e mapping', static_dir / 'help' / 'screenshot-modules.png'),
            ('Figura 5 - Esempi di grafici di reportistica', static_dir / 'help' / 'charts-reporting.png'),
        ],
    }

    html = render_template('help_en.html' if getattr(g, 'lang', 'it') == 'en' else 'help.html')
    html = re.sub(r'<(script|style|figure)[\s\S]*?</\1>', ' ', html, flags=re.I)
    html = re.sub(r'<nav[\s\S]*?</nav>', ' ', html, flags=re.I)
    html = re.sub(r'<li[^>]*>', '\n• ', html, flags=re.I)
    html = re.sub(r'</(p|h1|h2|h3|tr|section|div)>', '\n', html, flags=re.I)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    text = unescape(re.sub(r'<[^>]+>', ' ', html))
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    def is_pdf_noise(line):
        if not line:
            return True
        exact_noise = {'Salta al contenuto principale', 'Menu', '☰ Menu', 'n Menu', 'Alex', 'Logout', 'Scarica PDF', 'Scarica PDF amministrativo', 'Vai all’indice', 'Digita una parola per filtrare i capitoli.', 'Search administrator documentation', 'Type a word to filter chapters.'}
        if line in exact_noise:
            return True
        noise_fragments = (
            'Salta al contenuto principale',
            'Apri o chiudi menu',
            'Cerca nella documentazione',
            'Nessun capitolo contiene il testo cercato',
            'No chapter contains the searched text',
            'Vai all’indice',
            'Scarica PDF',
            'Logout',
            'Il logo presente in questa guida',
            'Questa guida riorganizza le funzioni amministrative',
            'Questa guida descrive lo stato operativo corrente',
            'AlBot anche Alex',
            'Helpdesk applicativo',
            'Ciao, sono AlBot',
            'Domanda per AlBot',
            'Invia',
        )
        if any(fragment in line for fragment in noise_fragments):
            return True
        if re.fullmatch(r'[A-Za-z0-9_.@ -]{2,80} · Logout', line):
            return True
        return False
    lines = [line for line in lines if not is_pdf_noise(line)]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.55*cm,
        leftMargin=1.55*cm,
        topMargin=1.65*cm,
        bottomMargin=1.55*cm,
        title='Cybersecurity Incident Registry - User documentation' if getattr(g, 'lang', 'it') == 'en' else 'Cybersecurity Incident Registry - Documentazione utente'
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle('doc_normal', parent=styles['BodyText'], fontSize=9.2, leading=12.5, alignment=TA_LEFT, spaceAfter=4)
    bullet = ParagraphStyle('doc_bullet', parent=normal, leftIndent=13, firstLineIndent=-8)
    h1 = ParagraphStyle('doc_h1', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#0f172a'), spaceAfter=12, alignment=TA_CENTER)
    h2 = ParagraphStyle('doc_h2', parent=styles['Heading2'], fontSize=13.5, leading=17, textColor=colors.HexColor('#1d4ed8'), spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle('doc_h3', parent=styles['Heading3'], fontSize=11.2, leading=14, textColor=colors.HexColor('#334155'), spaceBefore=8, spaceAfter=4)
    caption = ParagraphStyle('caption', parent=normal, fontSize=8.3, leading=10.5, textColor=colors.HexColor('#64748b'), alignment=TA_CENTER)
    callout = ParagraphStyle('callout', parent=normal, backColor=colors.HexColor('#eef4ff'), borderColor=colors.HexColor('#bfdbfe'), borderWidth=0.7, borderPadding=7, spaceBefore=4, spaceAfter=8)

    def fitted_doc_image(path, max_width=16.3*cm, max_height=7.6*cm):
        try:
            iw, ih = ImageReader(str(path)).getSize()
            ratio = min(max_width / iw, max_height / ih)
            img = Image(str(path), width=iw * ratio, height=ih * ratio)
        except Exception:
            img = Image(str(path), width=max_width, height=max_height)
        img.hAlign = 'CENTER'
        return img

    story = []
    if logo_path.exists():
        story.append(Image(str(logo_path), width=3.0*cm, height=3.0*cm))
        story[-1].hAlign = 'CENTER'
    story.append(Paragraph('Cybersecurity Incident Registry', h1))
    story.append(Paragraph('Documentazione utente completa', ParagraphStyle('subtitle', parent=normal, alignment=TA_CENTER, fontSize=12, leading=15, textColor=colors.HexColor('#475569'))))
    story.append(Spacer(1, .35*cm))
    story.append(Paragraph('La documentazione descrive funzionalità, flussi operativi, ruoli, incidenti, azioni, notifiche, moduli PDF, report ed export/import.', callout))
    story.append(PageBreak())

    # Indice sintetico professionale
    chapters = [line for line in lines if re.match(r'^\d+\.\s+', line)]
    if chapters:
        story.append(Paragraph('Indice', h2))
        tbl = [[Paragraph(escape(c), normal)] for c in chapters]
        t = Table(tbl, colWidths=[17.0*cm])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f8fafc')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e2e8f0')),('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor('#e2e8f0')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(t); story.append(PageBreak())

    inserted_visuals = set()
    for line in lines:
        if line.startswith('Documentazione utente') or line.startswith('Cybersecurity Incident Registry'):
            continue
        chapter_match = re.match(r'^(\d+)\.\s+', line)
        if chapter_match:
            story.append(Paragraph(escape(line), h2))
            for label, path in visual_paths_by_chapter.get(chapter_match.group(1), []):
                if path.exists() and label not in inserted_visuals:
                    img = fitted_doc_image(path)
                    story.append(KeepTogether([img, Paragraph(escape(label), caption), Spacer(1, .2*cm)]))
                    inserted_visuals.add(label)
            continue
        if line.startswith('• '):
            story.append(Paragraph(escape(line), bullet)); continue
        if len(line) < 85 and (line.startswith('Esempio') or line in {'Accessibilità','Checklist finale per un incidente','Full export','Full import','Statistiche','Report PDF incidente','SSO / OAuth2 / OpenID Connect','Logo custom e logo applicativo','SMTP e notifiche'}):
            story.append(Paragraph(escape(line), h3)); continue
        story.append(Paragraph(escape(line), normal))

    def page_canvas(canvas, doc_obj):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#1d4ed8'))
        canvas.rect(0, A4[1]-0.65*cm, A4[0], 0.65*cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawString(1.55*cm, A4[1]-0.42*cm, 'Cybersecurity Incident Registry - Documentazione utente')
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(A4[0]-1.55*cm, 0.8*cm, f'Pagina {doc_obj.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=page_canvas, onLaterPages=page_canvas)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name='cybersecurity-incident-registry-documentazione.pdf')


BACKUP_CATEGORY_KEYS = ['incidents', 'database', 'templates', 'logos', 'uploads']
BACKUP_CATEGORY_LABELS = {
    'incidents': 'Incidenti in CSV',
    'database': 'Database applicativo',
    'templates': 'Template moduli',
    'logos': 'Loghi',
    'uploads': 'Uploads e allegati',
}


def _backup_categories_from_form():
    values = request.form.getlist('categories') or BACKUP_CATEGORY_KEYS[:]
    return [v for v in values if v in BACKUP_CATEGORY_KEYS]


def _cron_field_matches(field, value):
    field = (field or '*').strip()
    if field == '*':
        return True
    for part in field.split(','):
        part = part.strip()
        if not part:
            continue
        if part.startswith('*/'):
            try:
                step = int(part[2:])
                if step > 0 and value % step == 0:
                    return True
            except ValueError:
                pass
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                pass
    return False


def cron_matches_now(expr, dt):
    """Matcher cron-like minimale: minuto ora giorno-mese mese giorno-settimana."""
    parts = (expr or '').split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    py_dow = (dt.weekday() + 1) % 7  # domenica=0
    return (_cron_field_matches(minute, dt.minute) and _cron_field_matches(hour, dt.hour)
            and _cron_field_matches(dom, dt.day) and _cron_field_matches(month, dt.month)
            and _cron_field_matches(dow, py_dow))


def _add_path_to_tar(archive, src, arc_prefix):
    src_path = Path(src)
    if not src_path.exists():
        return
    if src_path.is_file():
        archive.add(str(src_path), arcname=f'{arc_prefix}/{src_path.name}')
        return
    for item in src_path.rglob('*'):
        if item.is_file():
            archive.add(str(item), arcname=f'{arc_prefix}/{item.relative_to(src_path)}')




def _safe_relative_file_entries(base_path, archive_prefix):
    """Restituisce i file di una directory persistente in forma ripristinabile.

    Il full export deve poter ricostruire anche eventuali file operativi non piu
    referenziati direttamente da record specifici, per esempio template caricati,
    loghi, allegati generati o residui necessari alla diagnostica. I percorsi
    relativi vengono normalizzati e non possono uscire dalla directory base.
    """
    base = Path(base_path or '')
    entries = []
    if not base.exists() or not base.is_dir():
        return entries
    for item in sorted(base.rglob('*'), key=lambda x: str(x).lower()):
        if not item.is_file():
            continue
        try:
            rel = item.relative_to(base)
        except ValueError:
            continue
        if rel.is_absolute() or '..' in rel.parts:
            continue
        rel_text = str(rel).replace('\\', '/')
        entries.append({
            'relative_path': rel_text,
            'archive_path': f'{archive_prefix}/{rel_text}',
            'size': item.stat().st_size,
        })
    return entries

def _full_export_persistent_file_manifest():
    """Snapshot completo dei volumi persistenti operativi dell'applicazione."""
    groups = {
        'uploads': current_app.config.get('UPLOAD_DIR'),
        'form_templates': current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates',
        'custom_logos': current_app.config.get('LOGO_DIR') or '/data/logo',
        'sso_logos': str(sso_logo_storage_dir()),
        'ssl': str(ssl_storage_dir()),
        'ai_chatbot_docs': current_app.config.get('AI_CHATBOT_DOC_DIR') or '/data/ai_chatbot_docs',
    }
    return {
        name: _safe_relative_file_entries(path, f'files/persistent/{name}')
        for name, path in groups.items()
    }

def _add_persistent_files_to_archive(archive, persistent_manifest):
    base_paths = {
        'uploads': current_app.config.get('UPLOAD_DIR'),
        'form_templates': current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates',
        'custom_logos': current_app.config.get('LOGO_DIR') or '/data/logo',
        'sso_logos': str(sso_logo_storage_dir()),
        'ssl': str(ssl_storage_dir()),
        'ai_chatbot_docs': current_app.config.get('AI_CHATBOT_DOC_DIR') or '/data/ai_chatbot_docs',
    }
    added = set()
    for group, files in (persistent_manifest or {}).items():
        base = Path(base_paths.get(group) or '')
        if not base.exists():
            continue
        for item in files or []:
            rel = Path(item.get('relative_path') or '')
            arcname = item.get('archive_path') or ''
            if not arcname or rel.is_absolute() or '..' in rel.parts:
                continue
            src = base / rel
            if src.exists() and src.is_file() and arcname not in added:
                archive.add(str(src), arcname=arcname)
                added.add(arcname)

def _restore_persistent_files_from_archive(archive, persistent_manifest):
    base_paths = {
        'uploads': current_app.config.get('UPLOAD_DIR'),
        'form_templates': current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates',
        'custom_logos': current_app.config.get('LOGO_DIR') or '/data/logo',
        'sso_logos': str(sso_logo_storage_dir()),
        'ssl': str(ssl_storage_dir()),
        'ai_chatbot_docs': current_app.config.get('AI_CHATBOT_DOC_DIR') or '/data/ai_chatbot_docs',
    }
    restored = 0
    for group, files in (persistent_manifest or {}).items():
        base = Path(base_paths.get(group) or '')
        if not base:
            continue
        base.mkdir(parents=True, exist_ok=True)
        for item in files or []:
            rel = Path(item.get('relative_path') or '')
            arcname = item.get('archive_path') or ''
            if not arcname or rel.is_absolute() or '..' in rel.parts:
                current_app.logger.warning('File persistente ignorato per path non sicuro: %s', rel)
                continue
            try:
                src = archive.extractfile(archive.getmember(arcname))
            except KeyError:
                current_app.logger.warning('File persistente indicato nel manifest ma mancante: %s', arcname)
                continue
            dst = base / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, 'wb') as out:
                shutil.copyfileobj(src, out)
            if group == 'ssl' and dst.name.endswith('.key'):
                try:
                    os.chmod(dst, 0o600)
                except OSError:
                    pass
            restored += 1
    return restored

def build_full_export_archive_for_backup(prefix='cir-full-backup'):
    fd, path = tempfile.mkstemp(prefix=f'{prefix}-', suffix='.tar.gz')
    os.close(fd)
    now = utcnow().isoformat()
    payload = {
        'format': 'cybersecurity-incident-registry-full-export',
        'version': 4,
        'created_at': now,
        'schema': _export_schema_payload(),
        'scope': 'global',
        'scope_tenant_id': None,
        'tables': _export_tables_payload(),
        'relations': _export_relations_payload(),
        'files': {
            'documents': [{'document_id': d.id, 'filename': d.filename, 'stored_name': d.stored_name, 'archive_path': f'files/documents/{d.stored_name}'} for d in Document.query.order_by(Document.id).all() if d.stored_name],
            'action_attachments': [{'attachment_id': a.id, 'filename': a.filename, 'stored_name': a.stored_name, 'archive_path': f'files/action_attachments/{a.stored_name}'} for a in ActionAttachment.query.order_by(ActionAttachment.id).all() if a.stored_name],
            'logo': None, 'application_logos': [], 'ssl_certificates': {}, 'sso_logos': [],
            'form_templates': [{'name': t.path.name, 'template_name': t.path.stem, 'archive_path': f'files/form_templates/{t.path.name}', 'fields': list(getattr(t, 'fields', []) or []), 'source': 'pdf_acroform'} for t in list_templates() if t.path and t.path.exists() and t.path.suffix.lower() == '.pdf'],
            'persistent_files': {},
        },
    }
    payload['files']['persistent_files'] = _full_export_persistent_file_manifest()
    logo_setting = db.session.get(Setting, 'logo_path')
    if logo_setting and logo_setting.value and os.path.exists(logo_setting.value):
        payload['files']['logo'] = {'path': logo_setting.value, 'archive_path': f'files/logo/{os.path.basename(logo_setting.value)}'}
    sso_dir = sso_logo_storage_dir()
    if sso_dir.exists():
        for logo_file in sorted(sso_dir.iterdir(), key=lambda p: p.name.lower()):
            if logo_file.is_file() and logo_file.suffix.lower() in {'.svg','.png','.jpg','.jpeg','.gif','.webp'}:
                payload['files']['sso_logos'].append({'relative_path': f'sso/{logo_file.name}', 'archive_path': f'files/sso_logos/{logo_file.name}'})
    cert = ssl_cert_path(); key = ssl_key_path()
    if cert.exists() and cert.is_file(): payload['files']['ssl_certificates']['certificate'] = {'archive_path': 'files/ssl/current.crt', 'path': str(cert)}
    if key.exists() and key.is_file(): payload['files']['ssl_certificates']['private_key'] = {'archive_path': 'files/ssl/current.key', 'path': str(key)}
    static_logo_candidates = [Path(current_app.static_folder or '') / 'cir-application-logo.svg', Path(current_app.static_folder or '') / 'help' / 'app-logo.png']
    for logo_path in static_logo_candidates:
        if logo_path.exists() and logo_path.is_file():
            payload['files']['application_logos'].append({'name': logo_path.name, 'relative_path': str(logo_path.relative_to(current_app.static_folder)), 'archive_path': f'files/application_logos/{logo_path.relative_to(current_app.static_folder)}'})
    with tarfile.open(path, 'w:gz') as archive:
        manifest = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
        info = tarfile.TarInfo('export.json'); info.size = len(manifest); archive.addfile(info, io.BytesIO(manifest))
        for doc in payload['files']['documents']:
            src = os.path.join(current_app.config['UPLOAD_DIR'], doc['stored_name'])
            if os.path.exists(src): archive.add(src, arcname=doc['archive_path'])
        for att in payload['files']['action_attachments']:
            src = os.path.join(current_app.config['UPLOAD_DIR'], att['stored_name'])
            if os.path.exists(src): archive.add(src, arcname=att['archive_path'])
        if payload['files']['logo']: archive.add(logo_setting.value, arcname=payload['files']['logo']['archive_path'])
        for ssl_item in payload['files'].get('ssl_certificates', {}).values():
            src = ssl_item.get('path')
            if src and os.path.exists(src): archive.add(src, arcname=ssl_item['archive_path'])
        for sso_logo in payload['files'].get('sso_logos', []):
            src = sso_logo_storage_dir() / Path(sso_logo['relative_path']).name
            if src.exists(): archive.add(src, arcname=sso_logo['archive_path'])
        for app_logo in payload['files'].get('application_logos', []):
            src = Path(current_app.static_folder or '') / app_logo.get('relative_path', '')
            if src.exists(): archive.add(src, arcname=app_logo['archive_path'])
        for tmpl in payload['files'].get('form_templates', []):
            src = os.path.join(current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates', tmpl['name'])
            if os.path.exists(src): archive.add(src, arcname=tmpl['archive_path'])
        _add_persistent_files_to_archive(archive, payload['files'].get('persistent_files', {}))
    return path

def build_backup_archive(categories, prefix='cir-backup'):
    categories = [c for c in (categories or BACKUP_CATEGORY_KEYS) if c in BACKUP_CATEGORY_KEYS]
    if not categories:
        categories = BACKUP_CATEGORY_KEYS[:]
    if set(categories) == set(BACKUP_CATEGORY_KEYS):
        return build_full_export_archive_for_backup(prefix)
    fd, path = tempfile.mkstemp(prefix=f'{prefix}-', suffix='.tar.gz')
    os.close(fd)
    created_at = utcnow().isoformat()
    manifest = {
        'format': 'cybersecurity-incident-registry-backup',
        'version': 1,
        'created_at': created_at,
        'categories': categories,
        'full': set(categories) == set(BACKUP_CATEGORY_KEYS),
    }
    with tarfile.open(path, 'w:gz') as archive:
        data = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
        info = tarfile.TarInfo('backup.json')
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
        if 'incidents' in categories:
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(['id','nome','riferimento','destinatario','stato','gravita','data_inizio','ora_inizio','data_fine','ora_fine','categorie','dati_interessati','descrizione'])
            for inc in Incident.query.order_by(Incident.id).all():
                writer.writerow([
                    inc.id, inc.name or '', inc.reference or '', inc.recipient or '', inc.status or '',
                    inc.severity.value if inc.severity else '',
                    inc.start_date.isoformat() if inc.start_date else '', inc.start_time.strftime('%H:%M') if inc.start_time else '',
                    inc.end_date.isoformat() if inc.end_date else '', inc.end_time.strftime('%H:%M') if inc.end_time else '',
                    '; '.join(c.value for c in inc.categories), '; '.join(d.value for d in inc.data_types), inc.description or ''
                ])
            b = csv_buf.getvalue().encode('utf-8')
            info = tarfile.TarInfo('incidents/incidents.csv')
            info.size = len(b)
            archive.addfile(info, io.BytesIO(b))
        if 'database' in categories or set(categories) == set(BACKUP_CATEGORY_KEYS):
            payload = {
                'format': 'cybersecurity-incident-registry-full-export',
                'version': 4,
                'created_at': created_at,
                'schema': _export_schema_payload(),
                'tables': _export_tables_payload(),
                'relations': _export_relations_payload(),
            }
            b = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
            info = tarfile.TarInfo('database/export.json')
            info.size = len(b)
            archive.addfile(info, io.BytesIO(b))
        if 'templates' in categories:
            _add_path_to_tar(archive, current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates', 'templates')
        if 'logos' in categories:
            _add_path_to_tar(archive, current_app.config.get('LOGO_DIR') or '/data/logo', 'logos/application')
            _add_path_to_tar(archive, current_app.config.get('SSO_LOGO_DIR') or '/data/sso_logos', 'logos/sso')
        if 'uploads' in categories or set(categories) == set(BACKUP_CATEGORY_KEYS):
            _add_path_to_tar(archive, current_app.config['UPLOAD_DIR'], 'uploads')
    return path


def _send_backup_admin_email(job, status, message, filename=''):
    if not getattr(job, 'notify_admin', False):
        return
    admin = User.query.filter_by(role='admin').filter(User.email.isnot(None)).order_by(User.id).first()
    if not admin or not admin.email:
        return
    host = setting_value('smtp_host')
    if not host:
        return
    sender = smtp_sender_address()
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = admin.email
    msg['Subject'] = f'Backup Cybersecurity Incident Registry: {status}'
    msg.set_content(f'Backup: {job.name}\nEsito: {status}\nFile: {filename}\nMessaggio: {message}\n')
    port = int(setting_value('smtp_port', '587') or '587')
    smtp_cls = smtplib.SMTP_SSL if setting_value('smtp_use_ssl', '0') == '1' else smtplib.SMTP
    with smtp_cls(host, port, timeout=20) as smtp:
        if setting_value('smtp_use_tls', '1') == '1' and setting_value('smtp_use_ssl', '0') != '1':
            smtp.starttls()
        if setting_value('smtp_auth_enabled', '0') == '1':
            smtp.login(setting_value('smtp_username'), setting_value('smtp_password') or '')
        smtp.send_message(msg)


def execute_backup_job(job, allow_download=False):
    categories = job.category_list() or BACKUP_CATEGORY_KEYS[:]
    path = build_backup_archive(categories)
    timestamp = utcnow().strftime('%Y%m%d-%H%M%S')
    filename = f'backup-cir-{timestamp}.tar.gz'
    try:
        if job.destination == 's3':
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError('boto3 non installato: installare la dipendenza per usare destinazioni S3/compatibili') from exc
            client = boto3.client('s3', endpoint_url=job.s3_endpoint_url or None,
                                  aws_access_key_id=job.s3_access_key or None,
                                  aws_secret_access_key=job.s3_secret_key or None)
            key = '/'.join(x.strip('/') for x in [job.s3_prefix or '', filename] if x.strip('/'))
            client.upload_file(path, job.s3_bucket, key)
            result = f's3://{job.s3_bucket}/{key}'
        elif job.destination == 'download' and allow_download:
            result = path
        else:
            target_dir = Path(job.local_path or current_app.config.get('BACKUP_DIR') or '/data/backups')
            target_dir.mkdir(parents=True, exist_ok=True)
            dst = target_dir / filename
            shutil.copyfile(path, dst)
            result = str(dst)
        job.last_run_at = utcnow()
        job.last_status = 'ok'
        job.last_message = result
        audit_log('backup_execute', f'Backup {job.name}: {result}')
        try: _send_backup_admin_email(job, 'ok', 'Backup completato', result)
        except Exception: current_app.logger.exception('Invio notifica backup fallito')
        db.session.commit()
        return result, path
    except Exception as exc:
        job.last_run_at = utcnow()
        job.last_status = 'error'
        job.last_message = str(exc)
        db.session.commit()
        try: _send_backup_admin_email(job, 'errore', str(exc))
        except Exception: current_app.logger.exception('Invio notifica errore backup fallito')
        raise


@bp.route('/admin/backups', methods=['GET','POST'])
@login_required
def admin_backups():
    if not can_admin():
        flash('Permessi insufficienti','error'); return redirect(url_for('main.index'))
    job = BackupJob.query.order_by(BackupJob.id).first()
    if not job:
        job = BackupJob(name='Backup schedulato principale', enabled=False, cron_expression='0 2 * * *', categories=','.join(BACKUP_CATEGORY_KEYS), destination='local', local_path=current_app.config.get('BACKUP_DIR','/data/backups'))
        db.session.add(job); db.session.commit()
    if request.method == 'POST':
        action = request.form.get('action')
        if action in ['save','run']:
            job.name = request.form.get('name','Backup schedulato principale').strip() or 'Backup schedulato principale'
            job.enabled = bool(request.form.get('enabled'))
            job.cron_expression = request.form.get('cron_expression','0 2 * * *').strip() or '0 2 * * *'
            job.categories = ','.join(_backup_categories_from_form())
            job.destination = request.form.get('destination','local')
            job.local_path = request.form.get('local_path','').strip() or current_app.config.get('BACKUP_DIR','/data/backups')
            job.s3_endpoint_url = request.form.get('s3_endpoint_url','').strip()
            job.s3_bucket = request.form.get('s3_bucket','').strip()
            job.s3_prefix = request.form.get('s3_prefix','').strip()
            job.s3_access_key = request.form.get('s3_access_key','').strip()
            secret = request.form.get('s3_secret_key','')
            if secret:
                job.s3_secret_key = secret
            job.notify_admin = bool(request.form.get('notify_admin'))
            db.session.commit()
            if action == 'run':
                try:
                    result, tmp_path = execute_backup_job(job, allow_download=(job.destination == 'download'))
                    if job.destination == 'download':
                        return send_file(tmp_path, download_name=os.path.basename(result) if result != tmp_path else f'backup-cir-{utcnow().strftime("%Y%m%d-%H%M%S")}.tar.gz', as_attachment=True)
                    flash(f'Backup completato: {result}', 'success')
                except Exception as exc:
                    current_app.logger.exception('Backup on-demand fallito')
                    flash(f'Backup fallito: {exc}', 'error')
            else:
                flash('Configurazione backup salvata.', 'success')
        elif action == 'restore':
            f = request.files.get('restore_file')
            if not f or not f.filename:
                flash('Selezionare un file di backup da ripristinare.', 'error')
            else:
                tmp_file = tempfile.NamedTemporaryFile(prefix='cir-restore-', suffix='.tar.gz', delete=False)
                tmp = tmp_file.name
                tmp_file.close()
                f.save(tmp)
                try:
                    # I full backup sono compatibili con l’import completo: richiedono export.json.
                    with tarfile.open(tmp, 'r:gz') as archive:
                        names = archive.getnames()
                    if 'export.json' in names:
                        flash('Backup completo caricato. Per sicurezza usare la funzione Full import esistente con lo stesso file.', 'warning')
                    elif 'database/export.json' in names:
                        flash('Backup parziale verificato. Il restore automatico dei backup parziali non sostituisce il full import: estrarre e ripristinare manualmente le categorie incluse.', 'warning')
                    else:
                        flash('Archivio backup riconosciuto come backup di file; estrarre e ripristinare manualmente sulle directory persistenti corrispondenti.', 'warning')
                except Exception as exc:
                    flash(f'Backup non valido: {exc}', 'error')
                finally:
                    try: os.remove(tmp)
                    except OSError: pass
    return render_template('admin_backups.html', job=job, category_keys=BACKUP_CATEGORY_KEYS, category_labels=BACKUP_CATEGORY_LABELS, selected=set(job.category_list() or BACKUP_CATEGORY_KEYS))


_backup_scheduler_started = False
_backup_scheduler_thread = None
_backup_scheduler_stop_event = threading.Event()

def start_backup_scheduler(app):
    global _backup_scheduler_started, _backup_scheduler_thread
    if _backup_scheduler_started:
        return
    if _background_schedulers_disabled(app):
        app.logger.info('Scheduler backup non avviato nel contesto corrente')
        return
    _backup_scheduler_stop_event.clear()
    _backup_scheduler_started = True
    def loop():
        last_minute = None
        while not _backup_scheduler_stop_event.is_set():
            try:
                with app.app_context():
                    now = application_now().replace(second=0, microsecond=0)
                    marker = now.strftime('%Y%m%d%H%M')
                    if marker != last_minute:
                        last_minute = marker
                        for job in BackupJob.query.filter_by(enabled=True).all():
                            if cron_matches_now(job.cron_expression, now):
                                try:
                                    execute_backup_job(job, allow_download=False)
                                except Exception:
                                    app.logger.exception('Backup schedulato fallito: %s', job.name)
            except Exception:
                app.logger.exception('Scheduler backup fallito')
            if _backup_scheduler_stop_event.wait(30):
                break
    t = threading.Thread(target=loop, name='cir-backup-scheduler', daemon=True)
    _backup_scheduler_thread = t
    t.start()

@bp.route('/export/csv')
@login_required
def export_csv():
    out=io.StringIO(); w=csv.writer(out); w.writerow(['nome','riferimento','destinatario','periodo','compilatore','personale','stato','durata'])
    for i in visible(Incident.query).all(): w.writerow([i.name, i.reference or '', i.recipient or i.reference or '', f'{i.start_at} - {i.end_at or ""}', i.creator_name, ', '.join(p.name for p in i.people), i.status, duration(i)])
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=incidenti.csv'})
def duration(i):
    value = i.effective_duration
    return str(value) if value is not None else ''
@bp.route('/incident/<int:iid>/pdf')
@login_required
def pdf(iid):
    inc=visible(Incident.query).filter(Incident.id == iid).first_or_404(); return send_file(incident_pdf(inc),download_name=f'incident-{iid}.pdf',as_attachment=True)


def _dt(v):
    if isinstance(v, (bytes, bytearray)):
        return {'__binary_base64__': base64.b64encode(bytes(v)).decode('ascii')}
    return v.isoformat() if hasattr(v, 'isoformat') else v

def _decode_binary_value(v):
    if isinstance(v, dict) and '__binary_base64__' in v:
        return base64.b64decode(v.get('__binary_base64__') or '')
    return v

def _time_minutes(v):
    if not v:
        return None
    try:
        return v.replace(second=0, microsecond=0).isoformat(timespec='minutes')
    except TypeError:
        return v.replace(second=0, microsecond=0).isoformat()

def _incident_temporal_export_fields(inc):
    """Campi temporali dell'incidente sempre presenti nel full export.

    I campi ``start_date``, ``start_time``, ``end_date`` ed ``end_time`` sono
    colonne reali del modello corrente, ma in archivi aggiornati da versioni
    precedenti possono essere valorizzati indirettamente tramite gli alias
    storici ``start_at``/``end_at``. Il full export deve quindi serializzarli
    esplicitamente e con un formato stabile, così non vengono persi nei backup
    o negli import successivi.
    """
    start_at = getattr(inc, 'start_at', None)
    end_at = getattr(inc, 'end_at', None)
    start_date = getattr(inc, 'start_date', None) or (start_at.date() if start_at else None)
    start_time = getattr(inc, 'start_time', None) or (start_at.time() if start_at else None)
    end_date = getattr(inc, 'end_date', None) or (end_at.date() if end_at else None)
    end_time = getattr(inc, 'end_time', None) or (end_at.time() if end_at else None)
    return {
        'start_date': _dt(start_date),
        'start_time': _time_minutes(start_time),
        'end_date': _dt(end_date),
        'end_time': _time_minutes(end_time),
        # Campi di compatibilità: non sono colonne del modello corrente, ma
        # rendono l'export leggibile anche da script/istanze che conoscono il
        # precedente formato con datetime aggregati.
        'start_at': _dt(start_at),
        'end_at': _dt(end_at),
    }

def _row(obj):
    # Esporta sempre tutte le colonne reali della tabella SQLAlchemy.
    # In questo modo il full export resta completo anche quando vengono
    # aggiunti nuovi campi ai modelli applicativi.
    data = {c.name: _dt(getattr(obj, c.name)) for c in obj.__table__.columns}
    if isinstance(obj, Incident):
        data.update(_incident_temporal_export_fields(obj))
    return data

def _table_row(row):
    return {k: _dt(v) for k, v in dict(row).items()}

def _table_rows(table):
    order_cols = list(table.primary_key.columns) or list(table.columns)
    stmt = table.select().order_by(*order_cols)
    return [_table_row(row) for row in db.session.execute(stmt).mappings().all()]

FULL_EXPORT_MODELS = [
    Tenant, Setting, User, UserTenantRole, MfaTotpToken, ConfigLabel, IncidentWorkflowStep, Person, Recommendation,
    AIChatbotDocument, NotificationType, NotificationTemplate, FormTemplateConfig,
    FormTemplateBinary, FormFieldMapping, IncidentTemplate, Incident, Action, Document,
    ActionAttachment, IncidentReminder, DeadlineNotificationState, ExternalRecipient, BackupJob, AuditLog,
]

FULL_EXPORT_TABLES = {
    'tenants': Tenant,
    'settings': Setting,
    'users': User,
    'user_tenant_roles': UserTenantRole,
    'mfa_totp_tokens': MfaTotpToken,
    'config_labels': ConfigLabel,
    'people': Person,
    'recommendations': Recommendation,
    'ai_chatbot_documents': AIChatbotDocument,
    'notification_types': NotificationType,
    'incident_workflow_steps': IncidentWorkflowStep,
    'notification_templates': NotificationTemplate,
    'incident_templates': IncidentTemplate,
    'form_template_configs': FormTemplateConfig,
    'form_template_binaries': FormTemplateBinary,
    'form_field_mappings': FormFieldMapping,
    'incidents': Incident,
    'actions': Action,
    'documents': Document,
    'action_attachments': ActionAttachment,
    'incident_reminders': IncidentReminder,
    'deadline_notification_states': DeadlineNotificationState,
    'external_recipients': ExternalRecipient,
    'backup_jobs': BackupJob,
    'audit_logs': AuditLog,
}

FULL_EXPORT_RELATION_TABLES = {
    'incident_people': incident_people,
    'incident_categories': incident_categories,
    'incident_data_types': incident_data_types,
    'incident_recommendations': incident_recommendations,
}

def _export_incident_ids_for_scope(scope_tenant_id=None):
    if not scope_tenant_id:
        return None
    return [row[0] for row in db.session.query(Incident.id).filter(Incident.tenant_id == int(scope_tenant_id)).all()]


def _export_user_ids_for_scope(scope_tenant_id=None):
    if not scope_tenant_id:
        return None
    ids = {row[0] for row in db.session.query(UserTenantRole.user_id).filter(UserTenantRole.tenant_id == int(scope_tenant_id)).all()}
    ids.update(row[0] for row in db.session.query(User.id).filter(User.tenant_id == int(scope_tenant_id)).all())
    return sorted(ids)


def _export_query_for_model(name, model, scope_tenant_id=None):
    q = model.query
    if not scope_tenant_id:
        return q
    tid = int(scope_tenant_id)
    incident_ids = _export_incident_ids_for_scope(tid) or []
    user_ids = _export_user_ids_for_scope(tid) or []
    if model is Tenant:
        return q.filter(Tenant.id == tid)
    if model is Setting:
        prefix = f'tenant:{tid}:%'
        return q.filter(or_(Setting.key.in_(GLOBAL_SETTING_KEYS), Setting.key.like(prefix), ~Setting.key.like('tenant:%')) )
    if model is User:
        return q.filter(User.id.in_(user_ids or [-1]))
    if model is UserTenantRole:
        return q.filter(UserTenantRole.tenant_id == tid)
    if model is MfaTotpToken:
        return q.filter(MfaTotpToken.user_id.in_(user_ids or [-1]))
    if model in (Action, Document, IncidentReminder, DeadlineNotificationState):
        return q.filter(getattr(model, 'incident_id').in_(incident_ids or [-1]))
    if model is ActionAttachment:
        action_ids = [row[0] for row in db.session.query(Action.id).filter(Action.incident_id.in_(incident_ids or [-1])).all()]
        return q.filter(ActionAttachment.action_id.in_(action_ids or [-1]))
    if hasattr(model, 'tenant_id'):
        return q.filter(model.tenant_id == tid)
    return q


def _export_tables_payload(scope_tenant_id=None):
    return {
        name: [_row(x) for x in _export_query_for_model(name, model, scope_tenant_id).order_by(*model.__table__.primary_key.columns).all()]
        for name, model in FULL_EXPORT_TABLES.items()
    }


def _export_relations_payload(scope_tenant_id=None):
    if not scope_tenant_id:
        return {name: _table_rows(table) for name, table in FULL_EXPORT_RELATION_TABLES.items()}
    incident_ids = set(_export_incident_ids_for_scope(scope_tenant_id) or [])
    payload = {}
    for name, table in FULL_EXPORT_RELATION_TABLES.items():
        rows = _table_rows(table)
        payload[name] = [row for row in rows if row.get('incident_id') in incident_ids]
    return payload


def can_global_export_import():
    return is_superuser() or is_builtin_admin_user()

def _export_schema_payload():
    schema = {
        name: [column.name for column in model.__table__.columns]
        for name, model in FULL_EXPORT_TABLES.items()
    }
    # Nel payload incidenti vengono aggiunti anche start_at/end_at come alias
    # di compatibilità; i quattro campi separati restano sempre esplicitati.
    for field in ['start_date', 'start_time', 'end_date', 'end_time', 'start_at', 'end_at']:
        if field not in schema.get('incidents', []):
            schema.setdefault('incidents', []).append(field)
    schema['_coverage'] = {
        'database_tables': sorted(FULL_EXPORT_TABLES.keys()),
        'relation_tables': sorted(FULL_EXPORT_RELATION_TABLES.keys()),
        'file_groups': ['documents', 'action_attachments', 'form_templates', 'custom_logo', 'application_logos', 'sso_logos', 'ssl_certificates', 'persistent_files'],
    }
    return schema

def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)

def _parse_date(value):
    if not value:
        return None
    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day') and not isinstance(value, str):
        return value
    return datetime.fromisoformat(str(value)).date()

def _parse_time(value):
    if not value:
        return None
    if hasattr(value, 'hour') and hasattr(value, 'minute') and not isinstance(value, str):
        return value
    return datetime.strptime(str(value)[:5], '%H:%M').time()


def _coerce_row_for_model(model, row):
    """Filtra e converte una riga JSON sui campi reali del modello.

    L'import accetta export completi prodotti da versioni diverse: i campi
    sconosciuti vengono ignorati, mentre date/ore/datetime vengono ricostruiti
    in base al tipo effettivo della colonna.
    """
    row = dict(row or {})
    if model is Incident:
        # Compatibilità con vecchi export che contenevano start_at/end_at
        # derivati, prima della separazione in data e ora.
        start_at = _parse_dt(row.get('start_at')) if row.get('start_at') else None
        end_at = _parse_dt(row.get('end_at')) if row.get('end_at') else None
        if not row.get('start_date') and start_at:
            row['start_date'] = start_at.date().isoformat()
        if not row.get('start_time') and start_at:
            row['start_time'] = start_at.time().replace(second=0, microsecond=0).isoformat(timespec='minutes')
        if not row.get('end_date') and end_at:
            row['end_date'] = end_at.date().isoformat()
        if not row.get('end_time') and end_at:
            row['end_time'] = end_at.time().replace(second=0, microsecond=0).isoformat(timespec='minutes')

    converted = {}
    for column in model.__table__.columns:
        if column.name not in row:
            continue
        value = _decode_binary_value(row.get(column.name))
        if value is None:
            converted[column.name] = None
            continue
        try:
            py_type = column.type.python_type
        except Exception:
            py_type = None
        if py_type is datetime:
            value = _parse_dt(value)
        elif py_type and py_type.__name__ == 'date':
            value = _parse_date(value)
        elif py_type and py_type.__name__ == 'time':
            value = _parse_time(value)
        converted[column.name] = value
    return converted

def _relation_row_for_table(table, row):
    allowed = {column.name for column in table.columns}
    return {k: v for k, v in dict(row or {}).items() if k in allowed}

@bp.route('/export/full')
@login_required
def export_full():
    """Export completo e ripristinabile dell'intera applicazione.

    L'archivio contiene:
    - dump JSON di tutte le tabelle applicative e di tutte le colonne reali;
    - schema dei campi esportati per tabella e manifest di copertura;
    - tabelle di relazione many-to-many;
    - utenti locali/LDAP/SSO, token MFA TOTP verificati/non verificati e ruoli;
    - configurazioni LDAP/SSO/app/notifiche e label configurabili;
    - incidenti completi, azioni, personale, documenti e allegati azione;
    - file fisici dei documenti caricati e dei moduli generati allegati agli incidenti;
    - template PDF dei moduli sia come file sia come copia binaria DB;
    - logo custom configurato e loghi applicativi statici.
    """
    if not can_admin():
        flash('Permessi insufficienti per esportare i dati applicativi','error')
        return redirect(url_for('main.index'))
    scope_tenant_id = None if can_global_export_import() else current_tenant_id()

    fd, path = tempfile.mkstemp(prefix='cir-full-export-', suffix='.tar.gz')
    os.close(fd)
    now = utcnow().isoformat()

    payload = {
        'format': 'cybersecurity-incident-registry-full-export',
        'version': 4,
        'created_at': now,
        'schema': _export_schema_payload(),
        'scope': 'global' if scope_tenant_id is None else 'tenant',
        'scope_tenant_id': scope_tenant_id,
        'tables': _export_tables_payload(scope_tenant_id),
        'relations': _export_relations_payload(scope_tenant_id),
        'files': {
            'documents': [
                {
                    'document_id': d.id,
                    'filename': d.filename,
                    'stored_name': d.stored_name,
                    'archive_path': f'files/documents/{d.stored_name}'
                }
                for d in Document.query.order_by(Document.id).all()
                if d.stored_name
            ],
            'action_attachments': [
                {
                    'attachment_id': a.id,
                    'filename': a.filename,
                    'stored_name': a.stored_name,
                    'archive_path': f'files/action_attachments/{a.stored_name}'
                }
                for a in ActionAttachment.query.order_by(ActionAttachment.id).all()
                if a.stored_name
            ],
            'logo': None,
            'application_logos': [],
            'ssl_certificates': {},
            'sso_logos': [],
            # Template moduli PDF: il full export deve essere autosufficiente.
            # Oltre al file PDF originario vengono riportati anche i nomi campo
            # rilevati nel modello; le mappature sono esportate nella tabella
            # form_field_mappings.
            'form_templates': [
                {
                    'name': path.name,
                    'template_name': path.stem,
                    'archive_path': f'files/form_templates/{path.name}',
                    'fields': list(getattr(tmpl, 'fields', []) or []),
                    'source': 'pdf_acroform',
                }
                for tmpl in list_templates()
                for path in [tmpl.path]
                if path and path.exists() and path.suffix.lower() == '.pdf'
            ],
            'persistent_files': {},
        },
    }
    if scope_tenant_id is not None:
        scoped_incident_ids = set(_export_incident_ids_for_scope(scope_tenant_id) or [])
        scoped_action_ids = {row[0] for row in db.session.query(Action.id).filter(Action.incident_id.in_(scoped_incident_ids or [-1])).all()}
        payload['files']['documents'] = [
            item for item in payload['files']['documents']
            if (db.session.get(Document, item.get('document_id')) and db.session.get(Document, item.get('document_id')).incident_id in scoped_incident_ids)
        ]
        payload['files']['action_attachments'] = [
            item for item in payload['files']['action_attachments']
            if (db.session.get(ActionAttachment, item.get('attachment_id')) and db.session.get(ActionAttachment, item.get('attachment_id')).action_id in scoped_action_ids)
        ]
    payload['files']['persistent_files'] = _full_export_persistent_file_manifest()

    logo_setting = db.session.get(Setting, 'logo_path')
    if logo_setting and logo_setting.value and os.path.exists(logo_setting.value):
        payload['files']['logo'] = {
            'path': logo_setting.value,
            'archive_path': f'files/logo/{os.path.basename(logo_setting.value)}'
        }



    # Loghi SSO/OAuth2: il full export include tutto lo storage condiviso
    # persistente SSO_LOGO_DIR, compresi i loghi predefiniti e quelli caricati da GUI.
    sso_dir = sso_logo_storage_dir()
    if sso_dir.exists():
        for logo_file in sorted(sso_dir.iterdir(), key=lambda p: p.name.lower()):
            if logo_file.is_file() and logo_file.suffix.lower() in {'.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                rel = f'sso/{logo_file.name}'
                payload['files']['sso_logos'].append({
                    'relative_path': rel,
                    'archive_path': f'files/sso_logos/{logo_file.name}',
                })

    ssl_files = {}
    cert = ssl_cert_path()
    key = ssl_key_path()
    if cert.exists() and cert.is_file():
        ssl_files['certificate'] = {'archive_path': 'files/ssl/current.crt', 'path': str(cert)}
    if key.exists() and key.is_file():
        ssl_files['private_key'] = {'archive_path': 'files/ssl/current.key', 'path': str(key)}
    payload['files']['ssl_certificates'] = ssl_files

    static_logo_candidates = [
        Path(current_app.static_folder or '') / 'cir-application-logo.svg',
        Path(current_app.static_folder or '') / 'help' / 'app-logo.png',
    ]
    for logo_path in static_logo_candidates:
        if logo_path.exists() and logo_path.is_file():
            payload['files']['application_logos'].append({
                'name': logo_path.name,
                'relative_path': str(logo_path.relative_to(current_app.static_folder)),
                'archive_path': f"files/application_logos/{logo_path.relative_to(current_app.static_folder)}",
            })

    with tarfile.open(path, 'w:gz') as archive:
        manifest = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
        info = tarfile.TarInfo('export.json')
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))

        for doc in payload['files']['documents']:
            src = os.path.join(current_app.config['UPLOAD_DIR'], doc['stored_name'])
            if os.path.exists(src):
                archive.add(src, arcname=doc['archive_path'])
        for att in payload['files'].get('action_attachments', []):
            src = os.path.join(current_app.config['UPLOAD_DIR'], att['stored_name'])
            if os.path.exists(src):
                archive.add(src, arcname=att['archive_path'])

        if payload['files']['logo']:
            archive.add(logo_setting.value, arcname=payload['files']['logo']['archive_path'])
        for ssl_item in payload['files'].get('ssl_certificates', {}).values():
            src = ssl_item.get('path')
            if src and os.path.exists(src):
                archive.add(src, arcname=ssl_item['archive_path'])

        for sso_logo in payload['files'].get('sso_logos', []):
            rel = str(sso_logo.get('relative_path', '')).replace('\\', '/')
            if not rel.startswith('sso/') or '/' in rel[4:]:
                continue
            src = sso_logo_storage_dir() / Path(rel).name
            if src.exists() and src.is_file():
                archive.add(src, arcname=sso_logo['archive_path'])

        for app_logo in payload['files'].get('application_logos', []):
            src = Path(current_app.static_folder or '') / app_logo.get('relative_path', '')
            if src.exists() and src.is_file():
                archive.add(src, arcname=app_logo['archive_path'])
        for tmpl in payload['files'].get('form_templates', []):
            src = os.path.join(current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates', tmpl['name'])
            if os.path.exists(src):
                archive.add(src, arcname=tmpl['archive_path'])
            else:
                row = FormTemplateBinary.query.filter_by(template_name=Path(tmpl['name']).stem).first()
                if row and row.pdf_data:
                    info = tarfile.TarInfo(tmpl['archive_path'])
                    info.size = len(row.pdf_data)
                    archive.addfile(info, io.BytesIO(row.pdf_data))
        _add_persistent_files_to_archive(archive, payload['files'].get('persistent_files', {}))

    return send_file(path, download_name=f'export-completo-{utcnow().strftime("%Y%m%d-%H%M%S")}.tar.gz', as_attachment=True)

@bp.route('/import/csv', methods=['GET','POST'])
@login_required
def import_csv():
    if not can_write():
        flash('Permessi insufficienti','error'); return redirect(url_for('main.index'))
    if request.method == 'POST':
        f = request.files.get('file')
        if not f or not f.filename:
            flash('Selezionare un file CSV da importare','error'); return render_template('import_csv.html')
        try:
            text = f.stream.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(text))
            created = 0
            for row in reader:
                name = (row.get('nome') or row.get('name') or '').strip()
                if not name:
                    continue
                periodo = row.get('periodo') or ''
                start_at = utcnow()
                end_at = None
                if ' - ' in periodo:
                    a,b = periodo.split(' - ',1)
                    try: start_at = datetime.fromisoformat(a.strip())
                    except Exception: pass
                    try: end_at = datetime.fromisoformat(b.strip()) if b.strip() else None
                    except Exception: pass
                tenant_id = current_tenant_id()
                inc = Incident(
                    tenant_id=tenant_id,
                    creator_id=current_user.id,
                    creator_name=current_user.name or current_user.username,
                    creator_email=current_user.email,
                    name=name,
                    reference=((row.get('riferimento') or row.get('reference') or '').strip() or f'Incidente importato {name}'),
                    recipient=row.get('destinatario') or row.get('recipient') or None,
                    description=row.get('descrizione') or row.get('description') or '',
                    start_at=start_at,
                    end_at=end_at,
                    status=(row.get('stato') or 'aperto').strip() or 'aperto'
                )
                people_text = row.get('personale') or ''
                for pname in [p.strip() for p in people_text.split(',') if p.strip()]:
                    person = Person.query.filter_by(tenant_id=tenant_id, name=pname).first()
                    if not person:
                        person = Person(tenant_id=tenant_id, name=pname, group='import')
                        db.session.add(person); db.session.flush()
                    inc.people.append(person)
                sync_incident_split_datetime(inc)
                db.session.add(inc); created += 1
            db.session.commit(); flash(f'Import CSV completato: {created} incidenti importati','info')
            return redirect(url_for('main.index'))
        except Exception as exc:
            current_app.logger.exception('Import CSV fallito')
            db.session.rollback(); flash(f'Import CSV fallito: {exc}','error')
    return render_template('import_csv.html')


def _tenant_import_delete_existing_scope(tenant_id):
    """Delete data owned by one tenant without touching global/shared records."""
    tenant_id = int(tenant_id)
    incident_ids = [row[0] for row in db.session.query(Incident.id).filter(Incident.tenant_id == tenant_id).all()]
    action_ids = [row[0] for row in db.session.query(Action.id).filter(Action.incident_id.in_(incident_ids or [-1])).all()]
    if incident_ids:
        for table in [incident_people, incident_categories, incident_data_types, incident_recommendations]:
            db.session.execute(table.delete().where(table.c.incident_id.in_(incident_ids)))
    if action_ids:
        ActionAttachment.query.filter(ActionAttachment.action_id.in_(action_ids)).delete(synchronize_session=False)
    if incident_ids:
        Document.query.filter(Document.incident_id.in_(incident_ids)).delete(synchronize_session=False)
        IncidentReminder.query.filter(IncidentReminder.incident_id.in_(incident_ids)).delete(synchronize_session=False)
        DeadlineNotificationState.query.filter(DeadlineNotificationState.incident_id.in_(incident_ids)).delete(synchronize_session=False)
        Action.query.filter(Action.incident_id.in_(incident_ids)).delete(synchronize_session=False)
        Incident.query.filter(Incident.id.in_(incident_ids)).delete(synchronize_session=False)
    for model in [ConfigLabel, IncidentWorkflowStep, Person, Recommendation, NotificationType, NotificationTemplate, IncidentTemplate, ExternalRecipient, BackupJob, AIChatbotDocument, AuditLog]:
        if hasattr(model, 'tenant_id'):
            model.query.filter(model.tenant_id == tenant_id).delete(synchronize_session=False)
    Setting.query.filter(Setting.key.startswith(f'tenant:{tenant_id}:')).delete(synchronize_session=False)
    db.session.flush()


def _tenant_scoped_rows(tables, name, tenant_id):
    rows = []
    for row in tables.get(name, []) or []:
        row = dict(row or {})
        if row.get('tenant_id') is not None:
            row['tenant_id'] = int(tenant_id)
        rows.append(row)
    return rows


def _ensure_incident_creator_exists(row):
    creator_id = row.get('creator_id')
    if creator_id and db.session.get(User, int(creator_id)):
        return row
    row['creator_id'] = current_user.id
    row['creator_name'] = current_user.name or current_user.username
    row['creator_email'] = current_user.email
    return row


def _import_tenant_scoped_archive(data, archive, target_tenant_id):
    """Import a tenant-scoped archive into exactly one tenant.

    This path is for tenant administrators. It is intentionally non-global: it
    never rebuilds the database, never imports global users/MFA, never changes
    other tenants, and refuses archives that were not produced as tenant scoped.
    """
    if data.get('scope') != 'tenant' or not data.get('scope_tenant_id'):
        raise ValueError('Gli admin di tenant possono importare solo archivi esportati in modalità tenant.')
    target_tenant_id = int(target_tenant_id)
    if user_role_for_tenant(current_user, target_tenant_id) != 'admin':
        raise ValueError('L’utente corrente non è admin del tenant di destinazione.')
    tables = data.get('tables', {}) or {}
    relations = data.get('relations', {}) or {}

    _tenant_import_delete_existing_scope(target_tenant_id)

    # Settings tenant-specifiche: rimappo sempre la chiave sul tenant di destinazione.
    source_tid = str(data.get('scope_tenant_id'))
    for row in tables.get('settings', []) or []:
        key = str(row.get('key') or '')
        if key in GLOBAL_SETTING_KEYS or not key.startswith('tenant:'):
            continue
        parts = key.split(':', 2)
        if len(parts) == 3 and parts[1] == source_tid:
            row = dict(row)
            row['key'] = f'tenant:{target_tenant_id}:{parts[2]}'
            db.session.merge(Setting(**_coerce_row_for_model(Setting, row)))

    # Utenti e ruoli globali non vengono importati da admin tenant. Se un record
    # incidente punta a un utente non presente, viene assegnato all'admin corrente.
    import_order = [
        ('config_labels', ConfigLabel), ('people', Person), ('recommendations', Recommendation),
        ('ai_chatbot_documents', AIChatbotDocument), ('incident_templates', IncidentTemplate),
        ('incident_workflow_steps', IncidentWorkflowStep), ('notification_types', NotificationType),
        ('notification_templates', NotificationTemplate), ('external_recipients', ExternalRecipient),
        ('backup_jobs', BackupJob), ('audit_logs', AuditLog),
    ]
    for table_name, model in import_order:
        for row in _tenant_scoped_rows(tables, table_name, target_tenant_id):
            db.session.add(model(**_coerce_row_for_model(model, row)))
    db.session.flush()

    for row in _tenant_scoped_rows(tables, 'incidents', target_tenant_id):
        coerced = _coerce_row_for_model(Incident, row)
        coerced = _ensure_incident_creator_exists(coerced)
        if not (coerced.get('reference') or '').strip():
            coerced['reference'] = f"Incidente #{coerced.get('id') or coerced.get('name') or 'importato'}"
        db.session.add(Incident(**coerced))
    db.session.flush()

    for table_name, model in [('actions', Action), ('documents', Document), ('action_attachments', ActionAttachment), ('incident_reminders', IncidentReminder), ('deadline_notification_states', DeadlineNotificationState)]:
        for row in tables.get(table_name, []) or []:
            db.session.add(model(**_coerce_row_for_model(model, row)))
    db.session.flush()

    for rel_name, table in FULL_EXPORT_RELATION_TABLES.items():
        for row in relations.get(rel_name, []) or []:
            db.session.execute(table.insert().values(**_relation_row_for_table(table, row)))

    os.makedirs(current_app.config['UPLOAD_DIR'], exist_ok=True)
    for group in ['documents', 'action_attachments']:
        for item in data.get('files', {}).get(group, []) or []:
            arcname = item.get('archive_path')
            stored = secure_filename(item.get('stored_name') or '')
            if not arcname or not stored:
                continue
            try:
                src = archive.extractfile(archive.getmember(arcname))
            except KeyError:
                current_app.logger.warning('File %s mancante nell export tenant: %s', group, arcname)
                continue
            with open(os.path.join(current_app.config['UPLOAD_DIR'], stored), 'wb') as out:
                shutil.copyfileobj(src, out)

@bp.route('/import/full', methods=['GET','POST'])
@login_required
def import_full():
    if not can_admin():
        flash('Permessi insufficienti','error')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        f = request.files.get('file')
        if not f or not f.filename:
            flash('Selezionare un export completo tar.gz da importare','error')
            return render_template('import_full.html')

        tmp_file = tempfile.NamedTemporaryFile(prefix='cir-import-', suffix='.tar.gz', delete=False)
        tmp = tmp_file.name
        tmp_file.close()
        f.save(tmp)
        try:
            with tarfile.open(tmp, 'r:gz') as archive:
                validate_full_import_archive(archive)
                member = archive.getmember('export.json')
                data = json.load(archive.extractfile(member))
                if data.get('format') != 'cybersecurity-incident-registry-full-export':
                    raise ValueError('Formato export completo non riconosciuto')
                if not can_global_export_import():
                    target_tenant_id = current_tenant_id()
                    _import_tenant_scoped_archive(data, archive, target_tenant_id)
                    purge_audit_logs()
                    db.session.commit()
                    flash('Import tenant completato: sono stati sostituiti solo dati e configurazioni del tenant attivo. Utenti globali, altri tenant e configurazioni condivise non sono stati modificati.', 'info')
                    return redirect(url_for('main.index'))
                tables = data.get('tables', {})
                relations = data.get('relations', {})

                # Full import distruttivo: dopo aver validato l'archivio, lo schema
                # database viene eliminato e ricreato completamente. In questo modo
                # vengono rimossi residui, vincoli e sequence non allineate prima del
                # ripristino con ID espliciti contenuti nell'export.
                rebuild_database_for_full_import()

                # Anche dopo drop/create possono esistere righe bootstrap create
                # da hook o migrazioni. Svuotiamo esplicitamente e ripristiniamo
                # tenant deduplicati per evitare ix_tenant_name su default.
                clear_database_rows_for_full_import()

                for row in _deduplicated_tenant_rows(tables.get('tenants', [])):
                    db.session.add(Tenant(**row))
                db.session.flush()
                import_default_tenant_id = _legacy_default_tenant_id()

                for row in tables.get('settings', []):
                    db.session.add(Setting(**_coerce_row_for_model(Setting, row)))
                for row in tables.get('users', []):
                    db.session.add(User(**_coerce_row_for_full_import(User, row, import_default_tenant_id)))
                db.session.flush()
                for user in User.query.all():
                    if getattr(user, 'is_builtin_admin', False) or user.username == 'admin':
                        user.role = 'superuser'
                        user.default_tenant_id = None
                    elif not getattr(user, 'default_tenant_id', None):
                        user.default_tenant_id = user.tenant_id or import_default_tenant_id
                db.session.flush()

                for row in _deduplicated_user_tenant_role_rows(tables.get('user_tenant_roles', []), import_default_tenant_id):
                    db.session.add(UserTenantRole(**row))
                if not tables.get('user_tenant_roles'):
                    for user in User.query.all():
                        role = 'superuser' if getattr(user, 'is_builtin_admin', False) or user.username == 'admin' else (user.role or 'disabled')
                        db.session.add(UserTenantRole(user_id=user.id, tenant_id=user.tenant_id or import_default_tenant_id, role=role))
                db.session.flush()

                for row in tables.get('mfa_totp_tokens', []):
                    db.session.add(MfaTotpToken(**_coerce_row_for_model(MfaTotpToken, row)))
                for row in tables.get('audit_logs', []):
                    db.session.add(AuditLog(**_coerce_row_for_full_import(AuditLog, row, import_default_tenant_id)))
                db.session.flush()

                for row in tables.get('config_labels', []):
                    db.session.add(ConfigLabel(**_coerce_row_for_full_import(ConfigLabel, row, import_default_tenant_id)))
                for row in tables.get('people', []):
                    db.session.add(Person(**_coerce_row_for_full_import(Person, row, import_default_tenant_id)))
                for row in tables.get('recommendations', []):
                    db.session.add(Recommendation(**_coerce_row_for_full_import(Recommendation, row, import_default_tenant_id)))
                for row in tables.get('ai_chatbot_documents', []):
                    db.session.add(AIChatbotDocument(**_coerce_row_for_full_import(AIChatbotDocument, row, import_default_tenant_id)))
                db.session.flush()

                for row in tables.get('incident_templates', []):
                    db.session.add(IncidentTemplate(**_coerce_row_for_full_import(IncidentTemplate, row, import_default_tenant_id)))
                for row in tables.get('incident_workflow_steps', []):
                    db.session.add(IncidentWorkflowStep(**_coerce_row_for_full_import(IncidentWorkflowStep, row, import_default_tenant_id)))

                for row in tables.get('notification_types', []):
                    db.session.add(NotificationType(**_coerce_row_for_full_import(NotificationType, row, import_default_tenant_id)))
                db.session.flush()

                for row in tables.get('notification_templates', []):
                    db.session.add(NotificationTemplate(**_coerce_row_for_full_import(NotificationTemplate, row, import_default_tenant_id)))
                db.session.flush()

                for row in tables.get('external_recipients', []):
                    db.session.add(ExternalRecipient(**_coerce_row_for_full_import(ExternalRecipient, row, import_default_tenant_id)))
                for row in tables.get('backup_jobs', []):
                    db.session.add(BackupJob(**_coerce_row_for_full_import(BackupJob, row, import_default_tenant_id)))
                db.session.flush()

                for row in tables.get('form_field_mappings', []):
                    db.session.add(FormFieldMapping(**_coerce_row_for_model(FormFieldMapping, row)))
                db.session.flush()

                for row in tables.get('form_template_configs', []):
                    row = _coerce_row_for_model(FormTemplateConfig, row)
                    row['font_family'] = FormTemplateConfig.normalize_font_family(row.get('font_family'))
                    row['font_size'] = FormTemplateConfig.normalize_font_size(row.get('font_size'))
                    db.session.add(FormTemplateConfig(**row))
                for row in tables.get('form_template_binaries', []):
                    db.session.add(FormTemplateBinary(**_coerce_row_for_model(FormTemplateBinary, row)))
                db.session.flush()

                for row in tables.get('incidents', []):
                    coerced = _coerce_row_for_full_import(Incident, row, import_default_tenant_id)
                    if not (coerced.get('reference') or '').strip():
                        coerced['reference'] = f"Incidente #{coerced.get('id') or coerced.get('name') or 'importato'}"
                    db.session.add(Incident(**coerced))
                db.session.flush()

                for row in tables.get('actions', []):
                    db.session.add(Action(**_coerce_row_for_model(Action, row)))
                for row in tables.get('documents', []):
                    db.session.add(Document(**_coerce_row_for_model(Document, row)))
                for row in tables.get('action_attachments', []):
                    db.session.add(ActionAttachment(**_coerce_row_for_model(ActionAttachment, row)))
                for row in tables.get('incident_reminders', []):
                    db.session.add(IncidentReminder(**_coerce_row_for_model(IncidentReminder, row)))
                for row in tables.get('deadline_notification_states', []):
                    db.session.add(DeadlineNotificationState(**_coerce_row_for_model(DeadlineNotificationState, row)))
                db.session.flush()

                for row in relations.get('incident_people', []):
                    db.session.execute(incident_people.insert().values(**_relation_row_for_table(incident_people, row)))
                for row in relations.get('incident_categories', []):
                    db.session.execute(incident_categories.insert().values(**_relation_row_for_table(incident_categories, row)))
                for row in relations.get('incident_data_types', []):
                    db.session.execute(incident_data_types.insert().values(**_relation_row_for_table(incident_data_types, row)))
                for row in relations.get('incident_recommendations', []):
                    db.session.execute(incident_recommendations.insert().values(**_relation_row_for_table(incident_recommendations, row)))

                # Ripristino file documenti e logo.
                os.makedirs(current_app.config['UPLOAD_DIR'], exist_ok=True)
                os.makedirs(current_app.config['LOGO_DIR'], exist_ok=True)
                for doc in data.get('files', {}).get('documents', []):
                    arcname = doc.get('archive_path')
                    stored = secure_filename(doc.get('stored_name') or '')
                    if not arcname or not stored:
                        continue
                    try:
                        src = archive.extractfile(archive.getmember(arcname))
                    except KeyError:
                        current_app.logger.warning('File documento mancante nell export: %s', arcname)
                        continue
                    with open(os.path.join(current_app.config['UPLOAD_DIR'], stored), 'wb') as out:
                        shutil.copyfileobj(src, out)
                for att in data.get('files', {}).get('action_attachments', []):
                    arcname = att.get('archive_path')
                    stored = secure_filename(att.get('stored_name') or '')
                    if not arcname or not stored:
                        continue
                    try:
                        src = archive.extractfile(archive.getmember(arcname))
                    except KeyError:
                        current_app.logger.warning('File allegato azione mancante nell export: %s', arcname)
                        continue
                    with open(os.path.join(current_app.config['UPLOAD_DIR'], stored), 'wb') as out:
                        shutil.copyfileobj(src, out)

                logo = data.get('files', {}).get('logo')
                if logo and logo.get('archive_path'):
                    try:
                        src = archive.extractfile(archive.getmember(logo['archive_path']))
                        ext = os.path.splitext(secure_filename(os.path.basename(logo['archive_path'])))[1] or '.img'
                        dst = os.path.join(current_app.config['LOGO_DIR'], f'logo{ext}')
                        with open(dst, 'wb') as out:
                            shutil.copyfileobj(src, out)
                        setting = db.session.get(Setting, 'logo_path') or Setting(key='logo_path')
                        setting.value = dst
                        db.session.merge(setting)
                    except KeyError:
                        current_app.logger.warning('Logo indicato nel manifest ma non presente nell archivio')

                ssl_manifest = data.get('files', {}).get('ssl_certificates', {}) or {}
                ssl_storage_dir().mkdir(parents=True, exist_ok=True)
                cert_manifest = ssl_manifest.get('certificate')
                if cert_manifest and cert_manifest.get('archive_path'):
                    try:
                        src = archive.extractfile(archive.getmember(cert_manifest['archive_path']))
                        with open(ssl_cert_path(), 'wb') as out:
                            shutil.copyfileobj(src, out)
                    except KeyError:
                        current_app.logger.warning('Certificato SSL indicato nel manifest ma non presente nell archivio')
                key_manifest = ssl_manifest.get('private_key')
                if key_manifest and key_manifest.get('archive_path'):
                    try:
                        src = archive.extractfile(archive.getmember(key_manifest['archive_path']))
                        with open(ssl_key_path(), 'wb') as out:
                            shutil.copyfileobj(src, out)
                        try:
                            os.chmod(ssl_key_path(), 0o600)
                        except OSError:
                            pass
                    except KeyError:
                        current_app.logger.warning('Chiave SSL indicata nel manifest ma non presente nell archivio')
                if setting_value('ssl_enabled', '0') == '1':
                    write_ssl_enabled_marker(True)
                else:
                    write_ssl_enabled_marker(False)

                for sso_logo in data.get('files', {}).get('sso_logos', []) or []:
                    arcname = sso_logo.get('archive_path')
                    rel = sso_logo.get('relative_path') or ''
                    if not arcname or not rel:
                        continue
                    safe_rel = Path(rel)
                    if safe_rel.is_absolute() or '..' in safe_rel.parts:
                        current_app.logger.warning('Logo SSO ignorato per path non sicuro: %s', rel)
                        continue
                    try:
                        src = archive.extractfile(archive.getmember(arcname))
                    except KeyError:
                        current_app.logger.warning('Logo SSO indicato nel manifest ma non presente nell archivio: %s', arcname)
                        continue
                    if safe_rel.parts[0] != 'sso' or len(safe_rel.parts) != 2:
                        current_app.logger.warning('Logo SSO ignorato per path non ammesso: %s', rel)
                        continue
                    dst = sso_logo_storage_dir() / safe_rel.name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    with open(dst, 'wb') as out:
                        shutil.copyfileobj(src, out)

                os.makedirs(current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates', exist_ok=True)
                for tmpl in data.get('files', {}).get('form_templates', []):
                    arcname = tmpl.get('archive_path')
                    name = secure_filename(tmpl.get('name') or '')
                    if not arcname or not name or not name.endswith('.pdf'):
                        continue
                    try:
                        src = archive.extractfile(archive.getmember(arcname))
                    except KeyError:
                        current_app.logger.warning('Template PDF mancante nell export: %s', arcname)
                        continue
                    with open(os.path.join(current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates', name), 'wb') as out:
                        shutil.copyfileobj(src, out)

                _restore_persistent_files_from_archive(archive, data.get('files', {}).get('persistent_files', {}))

            # Garantisce che anche gli archivi storici precedenti alla regola del campo obbligatorio
            # producano incidenti sempre completi dopo il Full import.
            db.session.execute(text("UPDATE incident SET reference = 'Incidente #' || CAST(id AS VARCHAR) WHERE reference IS NULL OR TRIM(reference) = ''"))
            purge_audit_logs_without_request_user(import_default_tenant_id)
            db.session.commit()
            # Dopo il restore con ID espliciti, riallineiamo tutte le sequence in
            # una nuova transazione visibile a PostgreSQL. Questo evita che la
            # prima operazione successiva, ad esempio la creazione di un tenant
            # clonato, generi duplicate key su config_label_pkey o altre PK.
            align_all_table_sequences()
            flash('Import completo completato: database distrutto e ricreato, configurazioni, audit log, utenti, MFA, notifiche, logo, documenti, allegati e template moduli PDF ripristinati. I record audit oltre retention sono stati eliminati.','info')
            return redirect(url_for('main.index'))
        except Exception as exc:
            current_app.logger.exception('Import completo fallito')
            db.session.rollback()
            flash(f'Import completo fallito: {exc}','error')
        finally:
            try: os.remove(tmp)
            except OSError: pass
    return render_template('import_full.html')

def _stats_incidents_for_range(start=None, end=None):
    q = visible(Incident.query)
    if start:
        q = q.filter(or_(
            Incident.start_date > start.date(),
            and_(Incident.start_date == start.date(), Incident.start_time >= start.time())
        ))
    if end:
        q = q.filter(or_(
            Incident.start_date < end.date(),
            and_(Incident.start_date == end.date(), Incident.start_time <= end.time())
        ))
    return q.order_by(Incident.start_date.desc(), Incident.start_time.desc()).all()

def _build_stats_rows(include_search=True):
    now = utcnow()
    periods = []
    start_arg = request.args.get('start', '').strip()
    end_arg = request.args.get('end', '').strip()
    search_start = datetime.fromisoformat(start_arg) if start_arg else None
    search_end = datetime.fromisoformat(end_arg) if end_arg else None
    if include_search and (search_start or search_end):
        periods.append(('Finestra ricercata', search_start, search_end))
    periods.extend([
        ('Ultima settimana', now - timedelta(days=7), now),
        ('Ultimo mese', now - timedelta(days=30), now),
        ('Ultimi 3 mesi', now - timedelta(days=90), now),
        ('Ultimi 6 mesi', now - timedelta(days=180), now),
        ('Ultimo anno', now - timedelta(days=365), now),
    ])

    def count_labels(incidents, attr_name):
        counts = {}
        for incident in incidents:
            for label in getattr(incident, attr_name):
                counts[label.value] = counts.get(label.value, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))

    rows = []
    pdf_periods = []
    for name, start, end in periods:
        incs = _stats_incidents_for_range(start, end)
        durations = [
            incident.effective_duration_seconds / 3600
            for incident in incs
            if incident.effective_duration_seconds is not None
        ]
        categories = count_labels(incs, 'categories')
        data_types = count_labels(incs, 'data_types')
        rows.append({
            'name': name,
            'count': len(incs),
            'avg_duration': (sum(durations) / len(durations)) if durations else 0,
            'categories': categories,
            'data_types': data_types,
            'max_category': max([value for _, value in categories] or [1]),
            'max_data_type': max([value for _, value in data_types] or [1]),
        })
        pdf_periods.append({'name': name, 'start': start, 'end': end, 'incidents': incs})
    return rows, pdf_periods

@bp.route('/reports/stats')
@login_required
def stats():
    rows, _ = _build_stats_rows()
    return render_template('stats.html', rows=rows)

@bp.route('/reports/stats.pdf')
@login_required
def stats_pdf():
    _, raw_periods = _build_stats_rows()
    # Arricchimento demandato a reports.statistics_pdf per mantenere il PDF coerente
    from .reports import _period_statistics
    periods = [_period_statistics(p['name'], p['incidents'], p.get('start'), p.get('end')) for p in raw_periods]
    path = statistics_pdf(periods)
    return send_file(path, as_attachment=True, download_name='statistiche-incidenti.pdf', mimetype='application/pdf')


@bp.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@bp.route('/modules/configuration', methods=['GET','POST'])
@login_required
def modules_configuration():
    if not can_admin():
        return redirect(url_for('main.index'))
    templates = list_templates()
    notification_type_tags = notification_type_tag_options(enabled_only=False)
    preview = None
    if request.method == 'POST':
        action = request.form.get('action', 'save_mapping')

        if action == 'preview_pdf_template':
            uploaded = request.files.get('pdf_template')
            if not uploaded or not uploaded.filename:
                flash('Caricare un file PDF da analizzare', 'error')
                return redirect(url_for('main.modules_configuration'))
            if not uploaded.filename.lower().endswith('.pdf'):
                flash('Il file caricato deve essere in formato .pdf', 'error')
                return redirect(url_for('main.modules_configuration'))
            tmp_dir = tempfile.mkdtemp(prefix='cir-pdf-template-')
            try:
                src_name = secure_filename(uploaded.filename)
                tmp_path = os.path.join(tmp_dir, src_name)
                uploaded.save(tmp_path)
                fields, elements, visual_html, field_meta = analyze_pdf_template(tmp_path, Path(src_name).stem)
                with open(tmp_path, 'rb') as _fh:
                    source_pdf_b64 = base64.b64encode(_fh.read()).decode('ascii')
                preview = {
                    'source_name': src_name,
                    'suggested_name': Path(src_name).stem,
                    'fields': fields,
                    'elements': elements,
                    'visual_html': visual_html,
                    'field_meta': field_meta,
                    'source_pdf_b64': source_pdf_b64,
                }
                selected = request.args.get('template') or (templates[0].name if templates else '')
                current_mappings = {m.template_field:m.db_field for m in FormFieldMapping.query.filter_by(template_name=selected).all()} if selected else {}
                return render_template('modules_configuration.html', templates=templates, selected=selected, db_fields=available_incident_fields(), mappings=current_mappings, template_configs={t.name:get_template_config(t.name) for t in templates}, notification_type_tags=notification_type_tags, preview=preview)
            except Exception as exc:
                current_app.logger.exception('Analisi PDF template fallita')
                flash(f'Analisi del PDF fallita: {exc}', 'error')
                return redirect(url_for('main.modules_configuration'))
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        if action == 'save_pdf_template':
            template_name = request.form.get('new_template_name', '').strip()
            source_pdf_b64 = request.form.get('source_pdf_b64','').strip()
            if not template_name or not source_pdf_b64:
                flash('Specificare il nome del template e confermare il PDF sorgente', 'error')
                return redirect(url_for('main.modules_configuration'))
            try:
                source_pdf_bytes = base64.b64decode(source_pdf_b64)
                saved = save_template_pdf(template_name, source_pdf_bytes)
                flash(f'Template PDF {saved.stem} registrato correttamente', 'success')
                return redirect(url_for('main.modules_configuration', template=saved.stem))
            except Exception as exc:
                current_app.logger.exception('Salvataggio template PDF fallito')
                flash(f'Salvataggio template fallito: {exc}', 'error')
                return redirect(url_for('main.modules_configuration'))

        if action == 'replace_pdf_template':
            template_name = request.form.get('template_name','').strip()
            uploaded = request.files.get('replacement_pdf_template')
            if not template_name:
                flash('Selezionare il template da sostituire', 'error')
                return redirect(url_for('main.modules_configuration'))
            if not uploaded or not uploaded.filename:
                flash('Caricare il nuovo file PDF del template', 'error')
                return redirect(url_for('main.modules_configuration', template=template_name))
            if not uploaded.filename.lower().endswith('.pdf'):
                flash('Il file sostitutivo deve essere in formato .pdf', 'error')
                return redirect(url_for('main.modules_configuration', template=template_name))
            safe_name = Path(template_name).stem
            try:
                current = next((t for t in templates if t.name == safe_name), None)
                if not current:
                    flash('Template da sostituire non trovato', 'error')
                    return redirect(url_for('main.modules_configuration'))
                tmp_dir = tempfile.mkdtemp(prefix='cir-pdf-template-replace-')
                try:
                    src_name = secure_filename(uploaded.filename) or f'{safe_name}.pdf'
                    tmp_path = os.path.join(tmp_dir, src_name)
                    uploaded.save(tmp_path)
                    new_fields, _elements, _visual_html, _field_meta = analyze_pdf_template(tmp_path, safe_name)
                    old_fields = set(current.fields or [])
                    replacement_fields = set(new_fields or [])
                    missing = sorted(old_fields - replacement_fields)
                    extra = sorted(replacement_fields - old_fields)
                    if missing or extra:
                        details = []
                        if missing:
                            details.append('campi mancanti: ' + ', '.join(missing))
                        if extra:
                            details.append('campi aggiuntivi: ' + ', '.join(extra))
                        flash('Sostituzione annullata: il nuovo PDF non ha gli stessi campi compilabili (' + '; '.join(details) + ').', 'error')
                        return redirect(url_for('main.modules_configuration', template=safe_name))
                    with open(tmp_path, 'rb') as fh:
                        source_pdf_bytes = fh.read()
                    saved = save_template_pdf(safe_name, source_pdf_bytes)
                    flash(f'Template PDF {saved.stem} sostituito mantenendo mappature e impostazioni esistenti', 'success')
                    return redirect(url_for('main.modules_configuration', template=safe_name))
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception as exc:
                current_app.logger.exception('Sostituzione template PDF fallita')
                flash(f'Sostituzione template fallita: {exc}', 'error')
                return redirect(url_for('main.modules_configuration', template=safe_name))

        if action == 'rename_template':
            old_name = Path(request.form.get('template_name','').strip()).stem
            new_name = Path(request.form.get('new_template_name','').strip()).stem
            if not old_name or not new_name:
                flash('Specificare nome template attuale e nuovo nome', 'error')
                return redirect(url_for('main.modules_configuration', template=old_name or None))
            if old_name == new_name:
                flash('Il nome del template è invariato', 'info')
                return redirect(url_for('main.modules_configuration', template=old_name))
            template_path = Path(current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates')
            old_file = template_path / f'{old_name}.pdf'
            new_file = template_path / f'{new_name}.pdf'
            if not old_file.exists():
                flash('Template da rinominare non trovato', 'error')
                return redirect(url_for('main.modules_configuration'))
            if new_file.exists():
                flash('Esiste già un template con il nuovo nome', 'error')
                return redirect(url_for('main.modules_configuration', template=old_name))
            try:
                old_file.rename(new_file)
                FormFieldMapping.query.filter_by(template_name=old_name).update({'template_name': new_name})
                FormTemplateConfig.query.filter_by(template_name=old_name).update({'template_name': new_name})
                FormTemplateBinary.query.filter_by(template_name=old_name).update({'template_name': new_name, 'filename': f'{new_name}.pdf'})
                db.session.commit()
                flash(f'Template rinominato da {old_name} a {new_name}', 'success')
                return redirect(url_for('main.modules_configuration', template=new_name))
            except Exception as exc:
                db.session.rollback(); current_app.logger.exception('Rinomina template fallita'); flash(f'Rinomina template fallita: {exc}', 'error')
                return redirect(url_for('main.modules_configuration', template=old_name))

        if action == 'delete_template':
            template_name = request.form.get('template_name','').strip()
            if not template_name:
                flash('Selezionare il template da cancellare', 'error')
                return redirect(url_for('main.modules_configuration'))
            safe_name = Path(template_name).stem
            template_path = (current_app.config.get('FORM_TEMPLATE_DIR') or '/data/form_templates')
            template_file = Path(template_path) / f'{safe_name}.pdf'
            try:
                if template_file.exists():
                    template_file.unlink()
                template_docx = Path(template_path) / f'{safe_name}.docx'
                if template_docx.exists():
                    template_docx.unlink()
                template_pdf = Path(template_path) / f'{safe_name}.pdf'
                if template_pdf.exists():
                    template_pdf.unlink()
                FormFieldMapping.query.filter_by(template_name=safe_name).delete()
                FormTemplateConfig.query.filter_by(template_name=safe_name).delete()
                FormTemplateBinary.query.filter_by(template_name=safe_name).delete()
                db.session.commit()
                flash(f'Template {safe_name} cancellato', 'success')
            except Exception as exc:
                db.session.rollback()
                current_app.logger.exception('Cancellazione template modulo fallita')
                flash(f'Cancellazione template fallita: {exc}', 'error')
            return redirect(url_for('main.modules_configuration'))

        template_name = request.form.get('template_name','').strip()
        if not template_name:
            flash('Selezionare un template','error')
            return redirect(url_for('main.modules_configuration'))
        try:
            tmpl = next(t for t in templates if t.name == template_name)
        except StopIteration:
            flash('Template non trovato','error')
            return redirect(url_for('main.modules_configuration'))
        cfg = save_template_config(
            template_name,
            request.form.get('font_family', 'Helvetica'),
            request.form.get('font_size', 10),
        )
        valid_template_tags = {t.code for t in notification_type_tag_options(enabled_only=False)}
        cfg.set_notification_tags([code for code in request.form.getlist('template_notification_tags') if code in valid_template_tags])
        db.session.add(cfg)
        FormFieldMapping.query.filter_by(template_name=template_name).delete()
        allowed_db_fields = {name for name, _ in available_incident_fields()}
        for field in tmpl.fields:
            db_field = request.form.get(f'map__{field}', '').strip()
            if db_field and db_field in allowed_db_fields:
                db.session.add(FormFieldMapping(template_name=template_name, template_field=field, db_field=db_field))
        try:
            db.session.commit(); flash('Configurazione template salvata','success')
        except IntegrityError as exc:
            db.session.rollback(); current_app.logger.exception('Errore salvataggio mapping moduli'); flash(f'Errore configurazione: {exc}','error')
        return redirect(url_for('main.modules_configuration', template=template_name))
    selected = request.args.get('template') or (templates[0].name if templates else '')
    current_mappings = {}
    if selected:
        current_mappings = {m.template_field:m.db_field for m in FormFieldMapping.query.filter_by(template_name=selected).all()}
    return render_template('modules_configuration.html', templates=templates, selected=selected, db_fields=available_incident_fields(), mappings=current_mappings, template_configs={t.name:get_template_config(t.name) for t in templates}, notification_type_tags=notification_type_tags, preview=preview)

def add_workflow_document_action(inc, step, saved_documents):
    if not inc or not step or not saved_documents:
        return None
    label = step.action_label
    names = ', '.join(doc.filename for doc in saved_documents[:5])
    if len(saved_documents) > 5:
        names += ', ...'
    description = (
        f"Generazione documento da workflow: template '{step.document_template_name}'. "
        f"Documenti allegati: {names}."
    )
    align_table_sequence('action')
    action = Action(
        incident_id=inc.id,
        when_at=application_now(),
        person_name=getattr(current_user, 'name', None) or getattr(current_user, 'username', '') or 'Utente',
        description=description,
        consequence_text=None,
        label_id=step.action_label_id,
        exportable=action_exportable_default(label, description),
    )
    db.session.add(action)
    db.session.flush()
    close_incident_from_conclusion_action(inc.id, action)
    return action

@bp.route('/incident/<int:iid>/workflow-step/<int:sid>/document')
@login_required
def workflow_step_generate_document(iid, sid):
    inc = visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if not can_write():
        section_flash('Permessi insufficienti', 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    step = db.session.get(IncidentWorkflowStep, sid)
    if not step or step not in workflow_steps_for_incident(inc):
        section_flash('Step workflow non applicabile a questo incidente.', 'incident-workflow', 'error')
        return incident_detail_redirect(iid, 'incident-workflow')
    if not getattr(step, 'document_generation_enabled', False) or not (step.document_template_name or '').strip():
        section_flash('Lo step selezionato non è configurato per la generazione documento.', 'incident-workflow', 'error')
        return incident_detail_redirect(iid, 'incident-workflow')
    template_name = step.document_template_name.strip()
    missing_fields = missing_required_incident_fields_for_templates(inc, [template_name])
    if missing_fields:
        section_flash(format_missing_required_incident_fields(missing_fields), 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    upload_dir = Path(current_app.config['UPLOAD_DIR'])
    try:
        pdf_path = generate_pdf_from_template(inc, template_name, upload_dir)
    except Exception as exc:
        current_app.logger.exception('Errore anteprima generazione modulo workflow %s', template_name)
        section_flash(f'Errore generazione anteprima {template_name}: {exc}', 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    previews = [{
        'template': template_name,
        'pdf_stored': pdf_path.name,
        'suggested_name': f"{template_name}-{inc.id}",
    }]
    return render_template('generated_forms_preview.html', inc=inc, previews=previews, workflow_step=step)

@bp.route('/incident/<int:iid>/forms/generate', methods=['POST'])
@login_required
def generate_incident_forms(iid):
    inc = visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if not can_write():
        section_flash('Permessi insufficienti', 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    selected = request.form.getlist('templates')
    if not selected:
        section_flash('Selezionare almeno un template', 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    missing_fields = missing_required_incident_fields_for_templates(inc, selected)
    if missing_fields:
        section_flash(format_missing_required_incident_fields(missing_fields), 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    upload_dir = Path(current_app.config['UPLOAD_DIR'])
    previews = []
    for template_name in selected:
        try:
            pdf_path = generate_pdf_from_template(inc, template_name, upload_dir)
            previews.append({
                'template': template_name,
                'pdf_stored': pdf_path.name,
                'suggested_name': f"{template_name}-{inc.id}",
            })
        except Exception as exc:
            current_app.logger.exception('Errore anteprima generazione modulo %s', template_name)
            section_flash(f'Errore generazione anteprima {template_name}: {exc}', 'incident-forms', 'error')
    if not previews:
        return incident_detail_redirect(iid, 'incident-forms')
    return render_template('generated_forms_preview.html', inc=inc, previews=previews)

@bp.route('/incident/<int:iid>/forms/preview-file/<path:stored_name>')
@login_required
def preview_generated_form_file(iid, stored_name):
    visible(Incident.query).filter(Incident.id == iid).first_or_404()
    safe = Path(stored_name).name
    path = Path(current_app.config['UPLOAD_DIR']) / safe
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=False)

@bp.route('/incident/<int:iid>/forms/confirm', methods=['POST'])
@login_required
def confirm_generated_forms(iid):
    inc = visible(Incident.query).filter(Incident.id == iid).first_or_404()
    if not can_write():
        section_flash('Permessi insufficienti', 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    upload_dir = Path(current_app.config['UPLOAD_DIR'])
    action = request.form.get('decision','reject')
    pdf_files = request.form.getlist('pdf_stored')
    names = request.form.getlist('document_name')
    workflow_step_id = request.form.get('workflow_step_id', type=int)
    workflow_step = db.session.get(IncidentWorkflowStep, workflow_step_id) if workflow_step_id else None
    if workflow_step and workflow_step not in workflow_steps_for_incident(inc):
        workflow_step = None
    if action != 'accept':
        for stored in pdf_files:
            try:
                (upload_dir / Path(stored).name).unlink(missing_ok=True)
            except Exception:
                pass
        section_flash('Generazione rifiutata: i file temporanei sono stati eliminati.', 'incident-forms', 'info')
        return incident_detail_redirect(iid, 'incident-forms')
    saved = 0
    saved_docs = []
    for pdf_stored, name in zip(pdf_files, names):
        base = secure_filename(name.strip()) if name and name.strip() else Path(pdf_stored).stem
        if not base:
            base = Path(pdf_stored).stem
        src = upload_dir / Path(pdf_stored).name
        if not src.exists():
            continue
        final_name = f"{base}.pdf"
        final_path = upload_dir / final_name
        if final_path.exists() and final_path.name != src.name:
            final_name = f"{base}-{uuid.uuid4().hex[:6]}.pdf"
            final_path = upload_dir / final_name
        if src.name != final_path.name:
            src.rename(final_path)
        generated_template = request.form.get('template_name_' + Path(pdf_stored).name) or None
        doc = Document(
            incident_id=inc.id,
            filename=final_path.name,
            stored_name=final_path.name,
            generated_template_name=generated_template,
        )
        tags = notification_tags_for_generated_form_template(generated_template)
        doc.set_notification_tags(tags)
        db.session.add(doc)
        saved_docs.append(doc)
        saved += 1
    try:
        if workflow_step and saved_docs:
            add_workflow_document_action(inc, workflow_step, saved_docs)
        add_automatic_button_action(inc, 'forms_confirm')
        db.session.commit()
        msg = f'Documenti generati e allegati: {saved}'
        if workflow_step and saved_docs:
            msg += '. Azione workflow inserita automaticamente.'
        section_flash(msg, 'incident-forms', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Errore salvataggio documenti generati dopo anteprima')
        section_flash(f'Errore salvataggio documenti generati: {exc}', 'incident-forms', 'error')
    return incident_detail_redirect(iid, 'incident-forms')




def ssl_storage_dir():
    path = Path(os.environ.get('SSL_DIR') or '/data/ssl')
    path.mkdir(parents=True, exist_ok=True)
    return path

def ssl_marker_path():
    return ssl_storage_dir() / 'enabled'

def ssl_cert_path():
    configured = os.environ.get('SSL_CERT_FILE')
    return Path(configured) if configured else ssl_storage_dir() / 'current.crt'

def ssl_key_path():
    configured = os.environ.get('SSL_KEY_FILE')
    return Path(configured) if configured else ssl_storage_dir() / 'current.key'

def ssl_config_status():
    cert = ssl_cert_path()
    key = ssl_key_path()
    env_enabled = (os.environ.get('SSL_ENABLED') or '0').lower() in {'1','true','yes','on'}
    ui_enabled = setting_value('ssl_enabled', '0') == '1' or ssl_marker_path().exists()
    cert_present = cert.exists() and cert.is_file()
    key_present = key.exists() and key.is_file()
    https_ready = (env_enabled or ui_enabled) and cert_present and key_present
    return {
        'env_enabled': env_enabled,
        'ui_enabled': ui_enabled,
        'enabled': env_enabled or ui_enabled,
        'cert_present': cert_present,
        'key_present': key_present,
        'https_ready': https_ready,
        'cert_path': str(cert),
        'key_path': str(key),
        'port': os.environ.get('SSL_PORT') or '8443',
    }

def write_ssl_enabled_marker(enabled):
    marker = ssl_marker_path()
    if enabled:
        marker.write_text('enabled\n', encoding='utf-8')
    else:
        marker.unlink(missing_ok=True)

def recommendations_limit():
    return _bounded_int(setting_value('recommendations_max_per_incident', '3') or '3', 3, 1, 999)

def recommendations_from_form(field='recommendations'):
    ids=unique_int_list(field)
    limit = recommendations_limit()
    if limit and len(ids) > limit:
        section_flash(f'Selezionare al massimo {limit} raccomandazioni per incidente.', 'incident-main', 'danger')
        ids = ids[:limit]
    if not ids:
        return []
    return tenant_query(Recommendation).filter(Recommendation.id.in_(ids)).order_by(Recommendation.text).all()

def _setting_cache():
    if not has_request_context():
        return None
    cache = getattr(g, '_cir_setting_cache', None)
    if cache is None:
        cache = {}
        g._cir_setting_cache = cache
    return cache

def setting_value(key, default=''):
    physical_key = tenant_setting_key(key)
    cache = _setting_cache()
    cache_key = (physical_key, key)
    if cache is not None and cache_key in cache:
        cached = cache[cache_key]
        return cached if cached is not None else default
    s=db.session.get(Setting, physical_key)
    if not s and physical_key != key:
        s=db.session.get(Setting, key)
    value = decrypt_setting_value(key, s.value) if s and s.value is not None else None
    if cache is not None:
        cache[cache_key] = value
    return value if value is not None else default

def set_setting_value(key, value):
    physical_key = tenant_setting_key(key)
    if has_request_context():
        cache = getattr(g, '_cir_setting_cache', None)
        if cache is not None:
            cache.clear()
        if key == WORKFLOW_STEP_TYPES_JSON_SETTING or str(key).startswith('workflow_step_type_'):
            g.pop('_cir_workflow_step_type_records', None)
    s=db.session.get(Setting, physical_key)
    encrypted = store_setting_value(key, value or '')
    if not s:
        s=Setting(key=physical_key,value=encrypted)
        db.session.add(s)
    else:
        s.value=encrypted
    try:
        if physical_key != key and current_tenant_id() == default_tenant().id:
            legacy = db.session.get(Setting, key)
            if legacy is not None:
                legacy.value = encrypted
    except Exception:
        pass
    return s


def _audit_filtered_query_from_request():
    q = AuditLog.query
    search = (request.values.get('q') or '').strip()
    operation_type = (request.values.get('operation_type') or '').strip()
    username = (request.values.get('username') or '').strip()
    actor_type = (request.values.get('actor_type') or '').strip()
    start_value = (request.values.get('start') or '').strip()
    end_value = (request.values.get('end') or '').strip()
    if search:
        pattern = f'%{search}%'
        q = q.filter(or_(
            AuditLog.operation_type.ilike(pattern),
            AuditLog.username.ilike(pattern),
            AuditLog.actor_type.ilike(pattern),
            AuditLog.details.ilike(pattern),
        ))
    if operation_type:
        q = q.filter(AuditLog.operation_type.ilike(f'%{operation_type}%'))
    if username:
        q = q.filter(AuditLog.username.ilike(f'%{username}%'))
    if actor_type:
        q = q.filter(AuditLog.actor_type == actor_type)
    if start_value:
        try:
            q = q.filter(AuditLog.occurred_at >= application_to_utc_datetime(datetime.fromisoformat(start_value)))
        except ValueError:
            flash('Data inizio ricerca audit non valida', 'error')
    if end_value:
        try:
            q = q.filter(AuditLog.occurred_at <= application_to_utc_datetime(datetime.fromisoformat(end_value)))
        except ValueError:
            flash('Data fine ricerca audit non valida', 'error')
    return q, {
        'search': search,
        'operation_type': operation_type,
        'username': username,
        'actor_type': actor_type,
        'start': start_value,
        'end': end_value,
    }

@bp.route('/admin/audit', methods=['GET','POST'])
@login_required
def admin_audit():
    if not can_admin():
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        action = request.form.get('action') or ''
        if action == 'save_audit_config':
            audit_records_per_page = _bounded_int(request.form.get('audit_records_per_page', '20'), 20, 1, 100)
            max_records = _bounded_int(request.form.get('audit_max_records', '10000'), 10000, 100, 1000000)
            set_setting_value('audit_records_per_page', str(audit_records_per_page))
            set_setting_value('audit_max_records', str(max_records))
            audit_log('admin:audit_config_update', {'audit_records_per_page': audit_records_per_page, 'audit_max_records': max_records}, actor_type='user')
            db.session.commit()
            flash('Configurazione audit aggiornata', 'success')
            return redirect(url_for('main.admin_audit'))
        if action == 'purge_keep_count':
            keep_count = _bounded_int(request.form.get('purge_keep_count', '10000'), 10000, 0, 1000000)
            deleted = purge_audit_keep_latest(keep_count, commit=False)
            audit_log('admin:audit_purge_manual', {'mode': 'keep_count', 'keep_count': keep_count, 'deleted': deleted}, actor_type='user')
            db.session.commit()
            flash(f'Purge audit completato: eliminati {deleted} record, conservati al massimo {keep_count} record.', 'success')
            return redirect(url_for('main.admin_audit'))
        if action == 'purge_older_than':
            raw_date = (request.form.get('purge_older_than') or '').strip()
            try:
                cutoff_dt = application_to_utc_datetime(datetime.fromisoformat(raw_date))
            except ValueError:
                flash('Data di purge non valida', 'error')
                return redirect(url_for('main.admin_audit'))
            deleted = purge_audit_older_than(cutoff_dt, commit=False)
            audit_log('admin:audit_purge_manual', {'mode': 'older_than', 'older_than': raw_date, 'deleted': deleted}, actor_type='user')
            db.session.commit()
            flash(f'Purge audit completato: eliminati {deleted} record più vecchi di {raw_date}.', 'success')
            return redirect(url_for('main.admin_audit'))
    purge_audit_logs()
    db.session.commit()
    q, filters = _audit_filtered_query_from_request()
    total_records = AuditLog.query.count()
    configured_page_size = _bounded_int(setting_value('audit_records_per_page', '20') or '20', 20, 1, 100)
    page_size = _bounded_int(request.args.get('per_page') or configured_page_size, configured_page_size, 1, 100)
    page = _bounded_int(request.args.get('page') or '1', 1, 1, 10**9)
    filtered_count = q.count()
    max_page = max(1, (filtered_count + page_size - 1) // page_size)
    page = min(page, max_page)
    offset = (page - 1) * page_size
    logs = q.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).offset(offset).limit(page_size).all()
    for log in logs:
        log.display_details = audit_detail_summary(log.operation_type, log.details)
        log.local_occurred_at = format_audit_datetime(log.occurred_at, include_timezone=False)
    selected_from = offset + 1 if filtered_count else 0
    selected_to = min(offset + page_size, filtered_count)
    return render_template(
        'admin_audit.html',
        logs=logs,
        search=filters['search'],
        operation_type=filters['operation_type'],
        username=filters['username'],
        actor_type=filters['actor_type'],
        start=filters['start'],
        end=filters['end'],
        retention_label=audit_retention_label(),
        retention_parts=audit_retention_parts(),
        cutoff=utc_to_application_datetime(audit_cutoff_datetime()),
        audit_timezone=application_timezone_name(),
        total_records=total_records,
        filtered_count=filtered_count,
        page=page,
        page_size=page_size,
        configured_page_size=configured_page_size,
        max_page=max_page,
        selected_from=selected_from,
        selected_to=selected_to,
        audit_max_records=audit_max_records(),
    )

@bp.route('/admin/audit/export.csv')
@login_required
def admin_audit_export_csv():
    if not can_admin():
        return redirect(url_for('main.index'))
    q, _filters = _audit_filtered_query_from_request()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id','occurred_at','timezone','operation_type','username','actor_type','occurrences','details'])
    for log in q.order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc()).all():
        writer.writerow([
            log.id,
            format_audit_datetime(log.occurred_at, include_timezone=False),
            application_timezone_name(),
            log.operation_type or '',
            log.username or '',
            log.actor_type or '',
            log.repeat_count or 1,
            audit_detail_summary(log.operation_type, log.details),
        ])
    filename = f"audit_export_{utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={filename}'})


@bp.route('/admin/ssl', methods=['GET','POST'])
@login_required
def admin_ssl():
    if not can_admin():
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        if action == 'save':
            enabled = request.form.get('ssl_enabled') == '1'
            set_setting_value('ssl_enabled', '1' if enabled else '0')
            write_ssl_enabled_marker(enabled)
            cert_file = request.files.get('ssl_cert_file')
            key_file = request.files.get('ssl_key_file')
            saved = []
            if cert_file and cert_file.filename:
                data = cert_file.read()
                if b'BEGIN CERTIFICATE' not in data[:4096]:
                    flash('Il certificato caricato non sembra essere in formato PEM valido.', 'error')
                    return redirect(url_for('main.admin_ssl'))
                ssl_cert_path().parent.mkdir(parents=True, exist_ok=True)
                ssl_cert_path().write_bytes(data)
                saved.append('certificato')
            if key_file and key_file.filename:
                data = key_file.read()
                if b'PRIVATE KEY' not in data[:4096]:
                    flash('La chiave privata caricata non sembra essere in formato PEM valido.', 'error')
                    return redirect(url_for('main.admin_ssl'))
                ssl_key_path().parent.mkdir(parents=True, exist_ok=True)
                ssl_key_path().write_bytes(data)
                try:
                    os.chmod(ssl_key_path(), 0o600)
                except OSError:
                    pass
                saved.append('chiave privata')
            audit_log('admin:ssl_config_update', {'enabled': enabled, 'uploaded': saved}, actor_type='user')
            db.session.commit()
            if enabled and not (ssl_cert_path().exists() and ssl_key_path().exists()):
                flash('Configurazione salvata. HTTPS resterà inattivo finché certificato e chiave privata non saranno disponibili; HTTP su 8000 resta attivo.', 'warning')
            else:
                flash('Configurazione SSL/HTTPS aggiornata. Il listener HTTPS viene avviato/arrestato automaticamente dal container entro pochi secondi.', 'success')
            return redirect(url_for('main.admin_ssl'))
        if action == 'delete_certificates':
            ssl_cert_path().unlink(missing_ok=True)
            ssl_key_path().unlink(missing_ok=True)
            audit_log('admin:ssl_certificates_delete', {'certificates_removed': True}, actor_type='user')
            db.session.commit()
            flash('Certificati SSL rimossi. HTTP su 8000 resta attivo.', 'success')
            return redirect(url_for('main.admin_ssl'))
    return render_template('admin_ssl.html', status=ssl_config_status())



def _generated_document_name_matcher():
    template_names = {secure_filename(t.name or '') for t in list_templates()}
    template_names.update(secure_filename(row.template_name or '') for row in FormTemplateBinary.query.all())
    template_names = {x for x in template_names if x}
    notification_re = re.compile(r'^[0-9a-fA-F-]{36}_notifica-\d+\.pdf$')
    generated_re = re.compile(r'^(.+)-\d+-[0-9a-fA-F]{8}\.(?:pdf|docx)$')

    def is_generated(name, generated_template_name=None):
        safe_name = Path(name or '').name
        if not safe_name:
            return False
        if generated_template_name:
            return True
        if notification_re.match(safe_name):
            return True
        match = generated_re.match(safe_name)
        return bool(match and secure_filename(match.group(1)) in template_names)

    return is_generated


def _valid_document_storage_names():
    valid_incident_ids = {row[0] for row in db.session.query(Incident.id).all()}
    names = set()
    for doc in Document.query.all():
        if doc.incident_id in valid_incident_ids and doc.stored_name:
            names.add(Path(doc.stored_name).name)
    for att in db.session.query(ActionAttachment).join(Action, Action.id == ActionAttachment.action_id).filter(Action.incident_id.in_(valid_incident_ids)).all():
        if att.stored_name:
            names.add(Path(att.stored_name).name)
    return names


def _generated_document_orphan_candidates(upload_dir):
    """Find application-generated files in uploads that are no longer linked to incidents."""
    upload_path = Path(upload_dir or '')
    if not upload_path.exists() or not upload_path.is_dir():
        return []
    referenced = _valid_document_storage_names()
    is_generated = _generated_document_name_matcher()
    candidates = []
    for path in upload_path.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name in referenced:
            continue
        if is_generated(name):
            candidates.append(path)
    return sorted(candidates, key=lambda p: p.name)


def cleanup_orphan_generated_documents(upload_dir):
    upload_path = Path(upload_dir or '')
    valid_incident_ids = {row[0] for row in db.session.query(Incident.id).all()}
    is_generated = _generated_document_name_matcher()
    removed = []
    errors = []
    stale_documents = []

    for doc in Document.query.all():
        if doc.incident_id in valid_incident_ids:
            continue
        filename = Path(doc.stored_name or doc.filename or '').name
        if not is_generated(filename, getattr(doc, 'generated_template_name', None)):
            continue
        stale_documents.append(doc)
        path = upload_path / filename if filename else None
        if path and path.exists() and path.is_file():
            try:
                size = path.stat().st_size
                path.unlink()
                removed.append({'name': path.name, 'size': size})
            except Exception as exc:
                errors.append({'name': path.name, 'error': str(exc)})

    for path in _generated_document_orphan_candidates(upload_dir):
        try:
            size = path.stat().st_size
            path.unlink()
            removed.append({'name': path.name, 'size': size})
        except Exception as exc:
            errors.append({'name': path.name, 'error': str(exc)})

    for doc in stale_documents:
        db.session.delete(doc)
    if stale_documents:
        db.session.commit()
    return removed, errors



SETUP_WIZARD_PROGRESS_SETTING = 'setup_wizard_progress_json'
SETUP_WIZARD_COMPLETED_SETTING = 'setup_wizard_completed'

SETUP_WIZARD_AI_ENGINES = ['chatgpt', 'claude', 'gemini', 'ollama', 'perplexity']
SETUP_WIZARD_AI_LABELS = {
    'chatgpt': 'ChatGPT',
    'claude': 'Claude',
    'gemini': 'Gemini',
    'ollama': 'Ollama',
    'perplexity': 'Perplexity',
}
SETUP_WIZARD_AI_DEFAULTS = {
    'chatgpt': {'endpoint': '', 'model': 'gpt-4o-mini'},
    'claude': {'endpoint': '', 'model': 'claude-3-5-sonnet-latest'},
    'gemini': {'endpoint': '', 'model': 'gemini-1.5-flash'},
    'ollama': {'endpoint': 'http://localhost:11434/api/chat', 'model': 'llama3.1'},
    'perplexity': {'endpoint': '', 'model': 'sonar'},
}


def _setup_ai_fields():
    fields = [
        {'name': 'plugin_ai_chatbot_enabled', 'label': 'Abilita plugin Chatbot AI', 'type': 'checkbox', 'default': '0'},
        {'name': 'ai_chatbot_engine', 'label': 'Motore AI attivo', 'type': 'select', 'default': 'chatgpt', 'choices': [(name, SETUP_WIZARD_AI_LABELS.get(name, name)) for name in SETUP_WIZARD_AI_ENGINES]},
        {'name': 'ai_chatbot_include_database_context', 'label': 'Usa snapshot database anonimizzato', 'type': 'checkbox', 'default': '0'},
    ]
    for name in SETUP_WIZARD_AI_ENGINES:
        label = SETUP_WIZARD_AI_LABELS.get(name, name)
        defaults = SETUP_WIZARD_AI_DEFAULTS.get(name, {})
        fields.extend([
            {'name': f'ai_chatbot_{name}_endpoint', 'label': f'{label} endpoint', 'type': 'text', 'default': defaults.get('endpoint', '')},
            {'name': f'ai_chatbot_{name}_model', 'label': f'{label} modello', 'type': 'text', 'default': defaults.get('model', '')},
            {'name': f'ai_chatbot_{name}_api_key', 'label': f'{label} API key', 'type': 'password', 'default': '', 'placeholder': 'Lascia vuoto per mantenere la chiave salvata'},
        ])
    return fields


SETUP_WIZARD_SECTIONS = [
    {
        'code': 'admin_password',
        'title': 'Password utente admin',
        'description': 'Cambia subito la password dell’utente locale admin. È la prima operazione consigliata durante il setup iniziale.',
        'fields': [
            {'type': 'note', 'text': 'La password viene aggiornata solo se entrambi i campi sono compilati. Deve rispettare le regole di robustezza dell’applicazione.'},
            {'name': 'admin_new_password', 'label': 'Nuova password admin', 'type': 'password', 'default': '', 'placeholder': 'Inserisci la nuova password dell’utente admin'},
            {'name': 'admin_new_password2', 'label': 'Conferma nuova password admin', 'type': 'password', 'default': '', 'placeholder': 'Ripeti la nuova password'},
        ],
    },
    {
        'code': 'general',
        'title': 'Parametri generali',
        'description': 'Imposta URL esterna, fuso orario, lingua e dimensione massima degli upload.',
        'fields': [
            {'name': 'application_external_url', 'label': 'URL applicazione', 'type': 'text', 'default': 'http://localhost:8000', 'placeholder': 'https://registro.example.org'},
            {'name': 'application_timezone', 'label': 'Time zone applicazione', 'type': 'text', 'default': 'Europe/Rome', 'placeholder': 'Europe/Rome'},
            {'name': 'interface_language', 'label': 'Lingua interfaccia', 'type': 'select', 'default': 'auto', 'choices': [('auto', 'Automatica dal browser'), ('it', 'Italiano'), ('en', 'Inglese')]},
            {'name': MAX_UPLOAD_SIZE_MB_SETTING, 'label': 'Dimensione massima upload (MB)', 'type': 'number', 'default': str(DEFAULT_MAX_UPLOAD_SIZE_MB), 'min': MAX_UPLOAD_SIZE_MB_MIN, 'max': MAX_UPLOAD_SIZE_MB_MAX},
        ],
    },
    {
        'code': 'logo',
        'title': 'Logo custom',
        'description': 'Carica o rimuovi il logo custom usato dove previsto dall’applicazione. La testata del wizard usa sempre il logo applicativo di default.',
        'fields': [
            {'type': 'note', 'text': 'Il logo applicativo di default resta distinto dal logo custom. Il logo custom può essere modificato anche da Admin → Logo.'},
            {'name': 'custom_logo_file', 'label': 'Nuovo logo custom', 'type': 'file', 'accept': 'image/svg+xml,image/png,image/jpeg,image/gif,image/webp', 'help': 'Formati ammessi: SVG, PNG, JPG, GIF, WEBP. Dimensione massima 2 MB.'},
            {'name': 'custom_logo_delete', 'label': 'Rimuovi logo custom esistente', 'type': 'checkbox', 'default': '0'},
        ],
    },
    {
        'code': 'organization',
        'title': 'Struttura e riferimenti',
        'description': 'Configura i dati usati nei moduli PDF, nelle notifiche e nelle intestazioni operative.',
        'fields': [
            {'name': 'structure_name', 'label': 'Nome della struttura', 'type': 'text', 'default': '', 'placeholder': 'Dipartimento, Laboratorio, Servizio...'},
            {'name': 'security_owner_name', 'label': 'Nome del titolare', 'type': 'text', 'default': ''},
            {'name': 'security_owner_role', 'label': 'Ruolo del titolare', 'type': 'text', 'default': 'Titolare del trattamento'},
            {'name': 'security_owner_email', 'label': 'Email del titolare', 'type': 'email', 'default': ''},
            {'name': 'security_responsible_name', 'label': 'Nome responsabile', 'type': 'text', 'default': ''},
            {'name': 'security_responsible_email', 'label': 'Email responsabile', 'type': 'email', 'default': ''},
            {'name': 'security_responsible_phone', 'label': 'Telefono responsabile', 'type': 'text', 'default': '-'},
            {'name': 'security_responsible_function', 'label': 'Funzione responsabile', 'type': 'text', 'default': ''},
        ],
    },
    {
        'code': 'people',
        'title': 'Personale',
        'description': 'Aggiunge rapidamente personale al tenant attivo, senza sostituire l’elenco esistente.',
        'fields': [
            {'name': 'wizard_people_lines', 'label': 'Personale da aggiungere', 'type': 'textarea', 'rows': 6, 'default': '', 'placeholder': 'Mario Rossi <mario.rossi@example.org>\nAnna Bianchi; anna.bianchi@example.org', 'help': 'Una persona per riga. Sono accettati “Nome <email>”, “Nome; email” oppure solo il nome.'},
        ],
    },
    {
        'code': 'tenants',
        'title': 'Tenant',
        'description': 'Crea un tenant iniziale opzionale clonando la configurazione di un tenant esistente. La gestione completa resta in Admin → Tenant.',
        'fields': [
            {'name': 'wizard_tenant_name', 'label': 'Nome nuovo tenant', 'type': 'text', 'default': '', 'placeholder': 'tenant-esempio'},
            {'name': 'wizard_tenant_description', 'label': 'Descrizione nuovo tenant', 'type': 'textarea', 'rows': 3, 'default': ''},
            {'name': 'wizard_tenant_clone_from', 'label': 'Clona configurazioni da', 'type': 'select', 'default': 'default', 'dynamic_choices': 'tenants'},
        ],
    },
    {
        'code': 'ldap',
        'title': 'LDAP',
        'description': 'Configura i parametri principali per autenticazione e ricerca dati interessato tramite LDAP.',
        'fields': [
            {'name': 'ldap_uri', 'label': 'LDAP URI', 'type': 'text', 'default': '', 'placeholder': 'ldaps://ldap.example.org'},
            {'name': 'ldap_base_dn', 'label': 'Base DN', 'type': 'text', 'default': '', 'placeholder': 'dc=example,dc=org'},
            {'name': 'ldap_bind_dn', 'label': 'Bind DN', 'type': 'text', 'default': ''},
            {'name': 'ldap_bind_password', 'label': 'Bind password', 'type': 'password', 'default': '', 'placeholder': 'Lascia vuoto per mantenere la password LDAP salvata'},
            {'name': 'ldap_user_filter', 'label': 'Filtro utente login', 'type': 'text', 'default': '(uid={uid})'},
            {'name': 'ldap_incident_search_filter', 'label': 'Filtro ricerca interessato incidente', 'type': 'text', 'default': '(uid={uid})'},
            {'name': 'ldap_incident_search_attributes', 'label': 'Attributi ricerca interessato', 'type': 'text', 'default': 'uid,cn,mail,displayName,givenName,sn'},
            {'name': 'ldap_incident_reference_attribute', 'label': 'Attributo riferimento', 'type': 'text', 'default': 'cn'},
            {'name': 'ldap_incident_email_attribute', 'label': 'Attributo email', 'type': 'text', 'default': 'mail'},
        ],
    },
    {
        'code': 'sso',
        'title': 'SSO / OAuth2',
        'description': 'Configura rapidamente un profilo SSO principale. I profili multipli e i loghi provider restano gestibili da Admin → SSO.',
        'fields': [
            {'name': 'sso_profile_id', 'label': 'ID profilo SSO', 'type': 'text', 'default': 'primary'},
            {'name': 'sso_enabled', 'label': 'Abilita profilo SSO', 'type': 'checkbox', 'default': '0'},
            {'name': 'sso_provider_name', 'label': 'Nome provider', 'type': 'text', 'default': 'SSO'},
            {'name': 'sso_authorization_url', 'label': 'Authorization URL', 'type': 'text', 'default': ''},
            {'name': 'sso_token_url', 'label': 'Token URL', 'type': 'text', 'default': ''},
            {'name': 'sso_userinfo_url', 'label': 'Userinfo URL', 'type': 'text', 'default': ''},
            {'name': 'sso_client_id', 'label': 'Client ID', 'type': 'text', 'default': ''},
            {'name': 'sso_client_secret', 'label': 'Client secret', 'type': 'password', 'default': '', 'placeholder': 'Lascia vuoto per mantenere il secret salvato'},
            {'name': 'sso_scopes', 'label': 'Scopes', 'type': 'text', 'default': 'openid email profile'},
            {'name': 'sso_username_claim', 'label': 'Claim username', 'type': 'text', 'default': 'preferred_username'},
            {'name': 'sso_email_claim', 'label': 'Claim email', 'type': 'text', 'default': 'email'},
            {'name': 'sso_name_claim', 'label': 'Claim nome', 'type': 'text', 'default': 'name'},
            {'name': 'sso_subject_claim', 'label': 'Claim subject', 'type': 'text', 'default': 'sub'},
            {'name': 'sso_auto_create_users', 'label': 'Crea automaticamente utenti SSO', 'type': 'checkbox', 'default': '0'},
            {'name': 'sso_default_role', 'label': 'Ruolo iniziale utenti SSO', 'type': 'select', 'default': 'disabled', 'choices': [('disabled', 'disabilitato'), ('reader', 'reader'), ('writer', 'writer'), ('admin', 'admin')]},
        ],
    },
    {
        'code': 'ai',
        'title': 'Motori di AI',
        'description': 'Configura plugin, motore attivo, endpoint, modelli e API key dei backend AI disponibili.',
        'fields': _setup_ai_fields(),
    },
    {
        'code': 'alfresco',
        'title': 'Alfresco',
        'description': 'Configura il plugin Alfresco per invio e recupero documenti.',
        'fields': [
            {'name': 'plugin_alfresco_enabled', 'label': 'Abilita Alfresco', 'type': 'checkbox', 'default': '0'},
            {'name': 'alfresco_base_url', 'label': 'URL base Alfresco', 'type': 'text', 'default': '', 'placeholder': 'https://alfresco.example.org'},
            {'name': 'alfresco_username', 'label': 'Username API', 'type': 'text', 'default': ''},
            {'name': 'alfresco_password', 'label': 'Password/API secret', 'type': 'password', 'default': '', 'placeholder': 'Lascia vuoto per mantenere la password salvata'},
            {'name': 'alfresco_site', 'label': 'Site Alfresco opzionale', 'type': 'text', 'default': ''},
            {'name': 'alfresco_target_path', 'label': 'Cartella destinazione', 'type': 'text', 'default': 'Cybersecurity Incident Registry'},
            {'name': 'alfresco_timeout', 'label': 'Timeout API secondi', 'type': 'number', 'default': '30', 'min': 5, 'max': 300},
            {'name': 'alfresco_verify_tls', 'label': 'Verifica certificato TLS', 'type': 'checkbox', 'default': '1'},
        ],
    },
    {
        'code': 'documentation',
        'title': 'Documentazione e motivazioni predefinite',
        'description': 'Imposta testi di supporto usati nei moduli e nelle procedure.',
        'fields': [
            {'name': 'documentation_location', 'label': 'Luogo documentazione', 'type': 'textarea', 'default': ''},
            {'name': 'privacy_authority_non_notification_reason', 'label': 'Motivazione non comunicazione al Garante della Privacy', 'type': 'textarea', 'default': ''},
            {'name': 'consequence_fallback_text', 'label': 'Testo conseguenze di fallback', 'type': 'textarea', 'default': 'Conseguenze da valutare sulla base dell’analisi dell’incidente.'},
            {'name': 'recommendations_max_per_incident', 'label': 'Numero massimo raccomandazioni per incidente', 'type': 'number', 'default': '3', 'min': 1, 'max': 999},
        ],
    },
    {
        'code': 'notifications',
        'title': 'Notifiche e SMTP',
        'description': 'Configura i parametri minimi per l’invio email e per i controlli automatici.',
        'fields': [
            {'name': 'smtp_default_sender', 'label': 'Mittente SMTP predefinito', 'type': 'email', 'default': '', 'placeholder': 'registry@example.org'},
            {'name': 'smtp_host', 'label': 'SMTP host', 'type': 'text', 'default': '', 'placeholder': 'smtp.example.org'},
            {'name': 'smtp_port', 'label': 'SMTP porta', 'type': 'number', 'default': '587', 'min': 1, 'max': 65535},
            {'name': 'smtp_use_tls', 'label': 'Usa STARTTLS', 'type': 'checkbox', 'default': '1'},
            {'name': 'smtp_use_ssl', 'label': 'Usa SSL/TLS diretto', 'type': 'checkbox', 'default': '0'},
            {'name': 'smtp_auth_enabled', 'label': 'Abilita autenticazione SMTP', 'type': 'checkbox', 'default': '0'},
            {'name': 'smtp_username', 'label': 'SMTP username', 'type': 'text', 'default': ''},
            {'name': 'smtp_password', 'label': 'SMTP password', 'type': 'password', 'default': '', 'placeholder': 'Lascia vuoto per mantenere la password salvata'},
            {'name': 'notification_deadline_enabled', 'label': 'Abilita controllo automatico scadenze azioni', 'type': 'checkbox', 'default': '0'},
            {'name': 'notification_deadline_email_enabled', 'label': 'Abilita invio email per task in scadenza', 'type': 'checkbox', 'default': '1'},
        ],
    },
    {
        'code': 'security',
        'title': 'Sicurezza, TLS e audit',
        'description': 'Imposta HTTPS opzionale e retention audit iniziale.',
        'fields': [
            {'name': 'ssl_enabled', 'label': 'Abilita HTTPS/SSL integrato', 'type': 'checkbox', 'default': '0'},
            {'name': 'ssl_cert_path', 'label': 'Percorso certificato SSL', 'type': 'text', 'default': ''},
            {'name': 'ssl_key_path', 'label': 'Percorso chiave SSL', 'type': 'text', 'default': ''},
            {'name': 'audit_retention_months_part', 'label': 'Retention audit - mesi', 'type': 'number', 'default': '6', 'min': 0, 'max': 120},
            {'name': 'audit_retention_days_part', 'label': 'Retention audit - giorni', 'type': 'number', 'default': '0', 'min': 0, 'max': 3650},
            {'name': 'audit_retention_hours_part', 'label': 'Retention audit - ore', 'type': 'number', 'default': '0', 'min': 0, 'max': 23},
            {'name': 'audit_retention_minutes_part', 'label': 'Retention audit - minuti', 'type': 'number', 'default': '0', 'min': 0, 'max': 59},
        ],
    },
]

def _setup_wizard_progress():
    try:
        data = json.loads(setting_value(SETUP_WIZARD_PROGRESS_SETTING, '{}') or '{}')
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data.setdefault('completed', [])
    data.setdefault('skipped', [])
    data['completed'] = [str(x) for x in data.get('completed') or []]
    data['skipped'] = [str(x) for x in data.get('skipped') or []]
    return data


def _save_setup_wizard_progress(progress):
    progress = progress or {}
    payload = {
        'completed': [c for c in progress.get('completed', []) if c],
        'skipped': [c for c in progress.get('skipped', []) if c],
        'updated_at': utcnow().isoformat(),
    }
    set_setting_value(SETUP_WIZARD_PROGRESS_SETTING, json.dumps(payload, ensure_ascii=False))


def _setup_wizard_section_index(code=None, sections=None):
    sections = sections or SETUP_WIZARD_SECTIONS
    codes = [section['code'] for section in sections]
    if code in codes:
        return codes.index(code)
    return 0


def _setup_wizard_mark(progress, code, status):
    for key in ('completed', 'skipped'):
        progress.setdefault(key, [])
        progress[key] = [item for item in progress[key] if item != code]
    if status in ('completed', 'skipped'):
        progress[status].append(code)



def _setup_wizard_dynamic_sections():
    """Return wizard sections with runtime choices filled in."""
    sections = copy.deepcopy(SETUP_WIZARD_SECTIONS)
    tenant_choices = []
    try:
        tenant_choices = [(str(t.id), t.name) for t in Tenant.query.order_by(Tenant.name).all()]
    except Exception:
        tenant_choices = [('default', 'default')]
    if not tenant_choices:
        tenant_choices = [('default', 'default')]
    for section in sections:
        for field in section.get('fields', []):
            if field.get('dynamic_choices') == 'tenants':
                field['choices'] = tenant_choices
                field['default'] = tenant_choices[0][0]
    return sections


def _setup_wizard_sections_for_request():
    return _setup_wizard_dynamic_sections()


def _setup_wizard_sso_profile():
    try:
        profiles = sso_profiles(include_legacy=True)
    except Exception:
        profiles = []
    return profiles[0] if profiles else google_sso_example_profile()


def _parse_person_line(line):
    line = (line or '').strip()
    if not line:
        return '', ''
    email = ''
    name = line
    match = re.match(r'^(?P<name>.*?)\s*<(?P<email>[^>]+)>\s*$', line)
    if match:
        name = match.group('name').strip()
        email = match.group('email').strip()
    elif ';' in line:
        name, email = [part.strip() for part in line.split(';', 1)]
    elif ',' in line and '@' in line.split(',', 1)[1]:
        name, email = [part.strip() for part in line.split(',', 1)]
    return name[:200], email[:255]


def _save_setup_wizard_logo(files, form):
    setting = db.session.get(Setting, 'logo_path') or Setting(key='logo_path', value='')
    if form.get('custom_logo_delete') == '1':
        if setting.value and os.path.exists(setting.value):
            try:
                os.remove(setting.value)
            except OSError:
                current_app.logger.warning('Impossibile rimuovere il logo %s', setting.value)
        setting.value = ''
        db.session.merge(setting)
        return
    f = files.get('custom_logo_file') if files else None
    if not f or not f.filename:
        return
    filename = validate_upload_file(f, allowed_extensions={'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}, max_size=2 * 1024 * 1024)
    ext = os.path.splitext(filename)[1].lower() or '.img'
    os.makedirs(current_app.config['LOGO_DIR'], exist_ok=True)
    path = os.path.join(current_app.config['LOGO_DIR'], f'logo{ext}')
    f.save(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    for old in Path(current_app.config['LOGO_DIR']).glob('logo.*'):
        if str(old) != path:
            try:
                old.unlink()
            except OSError:
                current_app.logger.warning('Impossibile rimuovere il vecchio logo %s', old)
    setting.value = path
    db.session.merge(setting)


def _save_setup_wizard_people(form):
    added = 0
    for raw_line in (form.get('wizard_people_lines') or '').splitlines():
        name, email = _parse_person_line(raw_line)
        if not name:
            continue
        existing = tenant_query(Person).filter_by(name=name).first()
        if existing:
            if email:
                existing.email = email
        else:
            db.session.add(Person(tenant_id=current_tenant_id(), name=name, email=email, group='personale'))
            added += 1
    if added:
        flash(f'Personale aggiunto dal wizard: {added}.', 'success')


def _save_setup_wizard_tenants(form):
    name = (form.get('wizard_tenant_name') or '').strip()
    if not name:
        return
    if not is_superuser():
        flash('La creazione tenant dal wizard è riservata ai superuser.', 'warning')
        return
    if Tenant.query.filter(func.lower(Tenant.name) == name.lower()).first():
        flash(f'Tenant “{name}” già esistente.', 'info')
        return
    description = validate_text_field(form.get('wizard_tenant_description') or '', 'Descrizione tenant', 2000)
    clone_raw = form.get('wizard_tenant_clone_from')
    try:
        source = db.session.get(Tenant, int(clone_raw)) if clone_raw else default_tenant()
    except Exception:
        source = default_tenant()
    source = source or default_tenant()
    tenant = Tenant(name=validate_text_field(name, 'Nome tenant', 80, required=True, allow_multiline=False), description=description)
    db.session.add(tenant)
    db.session.flush()
    clone_tenant_config(source.id, tenant.id)
    audit_log('admin:tenant_create', {'tenant_id': tenant.id, 'name': tenant.name, 'cloned_from': source.id, 'source': 'setup_wizard'}, actor_type='user')
    flash(f'Tenant “{tenant.name}” creato dal wizard.', 'success')



def _save_setup_wizard_admin_password(form):
    new_password = form.get('admin_new_password') or ''
    new_password2 = form.get('admin_new_password2') or ''
    if not new_password and not new_password2:
        flash('Password admin non modificata: gruppo salvato senza nuovi valori.', 'info')
        return True
    if not is_superuser():
        flash('Il cambio password dell’utente admin dal wizard è riservato ai superuser.', 'error')
        return False
    if new_password != new_password2:
        flash('Le password admin non coincidono.', 'error')
        return False
    admin_user = User.query.filter(func.lower(User.username) == 'admin', User.auth_provider == 'local').first()
    if not admin_user:
        flash('Utente locale admin non trovato.', 'error')
        return False
    try:
        validate_password_strength(new_password, username=admin_user.username, email=admin_user.email)
    except ValueError as exc:
        flash(str(exc), 'error')
        return False
    admin_user.password_hash = hash_password(new_password)
    db.session.flush()
    audit_log('admin:setup_wizard_admin_password_change', {'user_id': admin_user.id, 'username': admin_user.username, 'by': current_user.username}, actor_type='user')
    flash('Password dell’utente admin aggiornata dal wizard.', 'success')
    return True

def _save_setup_wizard_sso(form):
    profiles = sso_profiles(include_legacy=True)
    original = _setup_wizard_sso_profile()
    profile_id = (form.get('sso_profile_id') or original.get('id') or 'primary').strip() or 'primary'
    posted = {
        'id': profile_id,
        'sso_enabled': '1' if form.get('sso_enabled') else '0',
        'sso_provider_name': form.get('sso_provider_name') or 'SSO',
        'sso_authorization_url': form.get('sso_authorization_url') or '',
        'sso_token_url': form.get('sso_token_url') or '',
        'sso_userinfo_url': form.get('sso_userinfo_url') or '',
        'sso_client_id': form.get('sso_client_id') or '',
        'sso_client_secret': (form.get('sso_client_secret') or '').strip() or original.get('sso_client_secret', ''),
        'sso_scopes': form.get('sso_scopes') or 'openid email profile',
        'sso_username_claim': form.get('sso_username_claim') or 'preferred_username',
        'sso_email_claim': form.get('sso_email_claim') or 'email',
        'sso_name_claim': form.get('sso_name_claim') or 'name',
        'sso_subject_claim': form.get('sso_subject_claim') or 'sub',
        'sso_auto_create_users': '1' if form.get('sso_auto_create_users') else '0',
        'sso_default_role': form.get('sso_default_role') or 'disabled',
        'sso_logo_path': original.get('sso_logo_path', ''),
    }
    posted = _normalize_sso_profile(posted, original.get('id') or profile_id)
    replaced = False
    new_profiles = []
    for prof in profiles:
        if prof.get('id') in {original.get('id'), profile_id} and not replaced:
            new_profiles.append(posted)
            replaced = True
        elif prof.get('id') != profile_id:
            new_profiles.append(prof)
    if not replaced:
        new_profiles.append(posted)
    save_sso_profiles(new_profiles)


def _setup_wizard_field_value(field):
    name = field.get('name')
    if not name:
        return field.get('default', '')
    if field.get('type') == 'password':
        return ''
    if name == 'audit_retention_months_part':
        return str(audit_retention_parts().get('months', field.get('default', '6')))
    if name == 'audit_retention_days_part':
        return str(audit_retention_parts().get('days', field.get('default', '0')))
    if name == 'audit_retention_hours_part':
        return str(audit_retention_parts().get('hours', field.get('default', '0')))
    if name == 'audit_retention_minutes_part':
        return str(audit_retention_parts().get('minutes', field.get('default', '0')))
    if name.startswith('sso_'):
        profile = _setup_wizard_sso_profile()
        if name == 'sso_profile_id':
            return profile.get('id', field.get('default', 'primary'))
        return profile.get(name, field.get('default', ''))
    return setting_value(name, field.get('default', ''))


def _save_setup_wizard_section(section, form, files=None):
    section_code = section.get('code')
    if section_code == 'admin_password':
        return _save_setup_wizard_admin_password(form)
    if section_code == 'logo':
        _save_setup_wizard_logo(files, form)
        return True
    if section_code == 'people':
        _save_setup_wizard_people(form)
        return True
    if section_code == 'tenants':
        _save_setup_wizard_tenants(form)
        return True
    if section_code == 'sso':
        _save_setup_wizard_sso(form)
        return True

    checkbox_names = {field['name'] for field in section.get('fields', []) if field.get('type') == 'checkbox' and field.get('name')}
    password_names = {field['name'] for field in section.get('fields', []) if field.get('type') == 'password' and field.get('name')}
    retention_values = {}
    for field in section.get('fields', []):
        name = field.get('name')
        if not name:
            continue
        if field.get('type') in {'file', 'note'}:
            continue
        if name in checkbox_names:
            value = '1' if form.get(name) else '0'
        else:
            value = form.get(name, '')
        if name in password_names and not str(value or '').strip():
            continue
        if name == MAX_UPLOAD_SIZE_MB_SETTING:
            value = str(parse_max_upload_size_mb(value, DEFAULT_MAX_UPLOAD_SIZE_MB))
            current_app.config['MAX_CONTENT_LENGTH'] = int(value) * 1024 * 1024
            current_app.config['MAX_FORM_MEMORY_SIZE'] = current_app.config['MAX_CONTENT_LENGTH']
        if name in {'ldap_user_filter', 'ldap_incident_search_filter'} and value:
            value = validate_ldap_filter_template(value)
        if name == 'ai_chatbot_engine' and value not in SETUP_WIZARD_AI_ENGINES:
            value = 'chatgpt'
        if name == 'alfresco_timeout':
            value = str(_bounded_int(value, 30, 5, 300))
        if name.startswith('audit_retention_') and name.endswith('_part'):
            retention_values[name] = value
        else:
            set_setting_value(name, value.strip() if isinstance(value, str) else value)
    if retention_values:
        month = _bounded_int(retention_values.get('audit_retention_months_part', '6'), 6, 0, 120)
        day = _bounded_int(retention_values.get('audit_retention_days_part', '0'), 0, 0, 3650)
        hour = _bounded_int(retention_values.get('audit_retention_hours_part', '0'), 0, 0, 23)
        minute = _bounded_int(retention_values.get('audit_retention_minutes_part', '0'), 0, 0, 59)
        set_setting_value('audit_retention_months_part', str(month))
        set_setting_value('audit_retention_days_part', str(day))
        set_setting_value('audit_retention_hours_part', str(hour))
        set_setting_value('audit_retention_minutes_part', str(minute))
        set_setting_value('audit_retention_months', str(month))
    return True


@bp.route('/admin/setup-wizard', methods=['GET', 'POST'])
@login_required
def admin_setup_wizard():
    if not can_admin():
        return redirect(url_for('main.index'))
    step_code = request.values.get('step')
    sections = _setup_wizard_sections_for_request()
    index = _setup_wizard_section_index(step_code, sections)
    progress = _setup_wizard_progress()
    if request.method == 'POST':
        action = request.form.get('action') or 'next'
        section = sections[index]
        if action == 'reset':
            progress = {'completed': [], 'skipped': []}
            set_setting_value(SETUP_WIZARD_COMPLETED_SETTING, '0')
            _save_setup_wizard_progress(progress)
            db.session.commit()
            flash('Wizard di setup iniziale riavviato.', 'info')
            return redirect(url_for('main.admin_setup_wizard', step=sections[0]['code']))
        if action == 'finish':
            set_setting_value(SETUP_WIZARD_COMPLETED_SETTING, '1')
            _save_setup_wizard_progress(progress)
            db.session.commit()
            flash('Wizard di setup iniziale completato.', 'success')
            return redirect(url_for('main.admin_other_configurations'))
        if action == 'skip':
            _setup_wizard_mark(progress, section['code'], 'skipped')
            flash(f'Sezione “{section["title"]}” saltata.', 'info')
        else:
            saved = _save_setup_wizard_section(section, request.form, request.files)
            if saved is False:
                db.session.rollback()
                return redirect(url_for('main.admin_setup_wizard', step=section['code']))
            _setup_wizard_mark(progress, section['code'], 'completed')
            flash(f'Sezione “{section["title"]}” salvata.', 'success')
        _save_setup_wizard_progress(progress)
        done = set(progress.get('completed', [])) | set(progress.get('skipped', []))
        if len(done) >= len(sections):
            set_setting_value(SETUP_WIZARD_COMPLETED_SETTING, '1')
            db.session.commit()
            flash('Wizard di setup iniziale completato.', 'success')
            return redirect(url_for('main.admin_other_configurations'))
        next_index = min(index + 1, len(sections) - 1)
        while next_index < len(sections) and sections[next_index]['code'] in done:
            next_index += 1
        if next_index >= len(sections):
            next_index = index
        db.session.commit()
        return redirect(url_for('main.admin_setup_wizard', step=sections[next_index]['code']))
    completed = set(progress.get('completed', []))
    skipped = set(progress.get('skipped', []))
    done_count = len(completed | skipped)
    percent = int(round((done_count / max(1, len(sections))) * 100))
    current_section = sections[index]
    field_values = {field['name']: _setup_wizard_field_value(field) for field in current_section.get('fields', []) if field.get('name')}
    return render_template(
        'admin_setup_wizard.html',
        sections=sections,
        current_section=current_section,
        current_index=index,
        field_values=field_values,
        progress=progress,
        completed=completed,
        skipped=skipped,
        progress_percent=percent,
        setup_completed=setting_value(SETUP_WIZARD_COMPLETED_SETTING, '0') == '1',
        app_name=current_app.config.get('APP_INFO', {}).get('name', 'Cybersecurity Incident Registry'),
        app_version=APP_RELEASE_VERSION,
        app_build=APP_RELEASE_BUILD,
    )

@bp.route('/admin/other-configurations', methods=['GET','POST'])
@login_required
def admin_other_configurations():
    if not can_admin():
        return redirect(url_for('main.index'))
    keys = ['privacy_authority_non_notification_reason', 'documentation_location', 'application_external_url', 'application_timezone', 'interface_language', 'consequence_fallback_text']
    retention_keys = ['audit_retention_months_part', 'audit_retention_days_part', 'audit_retention_hours_part', 'audit_retention_minutes_part']
    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        if action == 'cleanup_orphan_generated_documents':
            removed, errors = cleanup_orphan_generated_documents(current_app.config.get('UPLOAD_DIR'))
            if removed:
                flash(f'Documenti orfani generati rimossi: {len(removed)}.', 'success')
            else:
                flash('Nessun documento orfano generato da rimuovere.', 'info')
            if errors:
                flash(f'Errori durante la rimozione di {len(errors)} file: ' + '; '.join(x['name'] for x in errors[:5]), 'error')
            return redirect(url_for('main.admin_other_configurations'))
        for key in keys:
            set_setting_value(key, request.form.get(key, ''))
        max_upload_size_mb = parse_max_upload_size_mb(request.form.get(MAX_UPLOAD_SIZE_MB_SETTING), DEFAULT_MAX_UPLOAD_SIZE_MB)
        set_setting_value(MAX_UPLOAD_SIZE_MB_SETTING, str(max_upload_size_mb))
        current_app.config['MAX_CONTENT_LENGTH'] = max_upload_size_mb * 1024 * 1024
        for key in retention_keys:
            set_setting_value(key, str(_bounded_int(request.form.get(key, '0'), 0, 0, 120 if key == 'audit_retention_months_part' else 3650 if key == 'audit_retention_days_part' else 23 if key == 'audit_retention_hours_part' else 59)))
        set_setting_value('consequence_rules_json', serialize_consequence_rules_from_form(request.form))
        # Mantiene aggiornata anche la chiave storica per compatibilità con archivi precedenti.
        set_setting_value('audit_retention_months', str(_bounded_int(request.form.get('audit_retention_months_part', '6'), 6, 0, 120)))
        db.session.commit()
        flash('Altre configurazioni aggiornate', 'success')
        return redirect(url_for('main.admin_other_configurations'))
    return render_template(
        'admin_other_configurations.html',
        privacy_authority_non_notification_reason=setting_value('privacy_authority_non_notification_reason'),
        documentation_location=setting_value('documentation_location'),
        application_external_url=setting_value('application_external_url', 'http://localhost:8000'),
        application_timezone=setting_value('application_timezone', 'Europe/Rome') or 'Europe/Rome',
        interface_language=setting_value('interface_language', 'auto') or 'auto',
        max_upload_size_mb=configured_max_upload_size_mb(),
        max_upload_size_mb_min=MAX_UPLOAD_SIZE_MB_MIN,
        max_upload_size_mb_max=MAX_UPLOAD_SIZE_MB_MAX,
        audit_retention_parts=audit_retention_parts(),
        audit_retention_label=audit_retention_label(),
        consequence_rules=configured_consequence_rules(),
        consequence_fallback_text=setting_value('consequence_fallback_text', 'Conseguenze da valutare sulla base dell’analisi dell’incidente.'),
    )

def incident_consequences(inc):
    return incident_consequence_list(inc)

def incident_measures(inc):
    lines=[]
    for a in sorted([x for x in inc.actions if getattr(x, 'exportable', True)], key=lambda x: x.when_at or datetime.min):
        when=a.when_at.strftime('%Y-%m-%d %H:%M') if a.when_at else ''
        label=(a.label.description or a.label.value) if a.label else 'azione'
        desc=a.description or ''
        action_text = f'{label}: {desc}'.strip() if desc else label
        lines.append(f'{action_text} - {when}'.strip(' -'))
    return lines or ['Nessuna misura registrata.']

