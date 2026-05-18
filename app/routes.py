import os, csv, io, json, tarfile, uuid, shutil, tempfile, smtplib, base64, secrets, re
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app, Response, abort, session, g
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_, and_, text
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError
from ldap3 import Server, Connection, ALL
from urllib.parse import urlencode
import requests
import threading, time
import pyotp
import qrcode
from .models import *
from .auth import verify_password, hash_password
from .reports import incident_pdf, statistics_pdf
from .form_generation import list_templates, available_incident_fields, FormFieldMapping, generate_pdf_from_template, analyze_pdf_template, save_template_pdf, get_template_config, save_template_config, missing_required_incident_fields_for_templates, format_missing_required_incident_fields
bp=Blueprint('main',__name__)


SUPPORTED_LANGUAGES = {'it', 'en'}

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
    return datetime.utcnow() - audit_retention_delta()

def purge_audit_logs(commit=False):
    """Elimina i record di audit più vecchi della retention configurata.

    La funzione è richiamata in modo opportunistico dopo le operazioni
    utente e dopo i task schedulati/automatici, così la tabella resta
    coerente con il periodo configurato in Admin -> Altre configurazioni.
    """
    deleted = AuditLog.query.filter(AuditLog.occurred_at < audit_cutoff_datetime()).delete(synchronize_session=False)
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
        if op == 'scheduler:incident_reminder_check':
            return f"Scheduler: controllo promemoria specifici, scaduti {data.get('due',0)}, inviati {data.get('sent',0)}, saltati {data.get('skipped',0)}, errori {len(data.get('errors') or [])}"
        if op == 'scheduler:deadline_notification_check':
            sent = data.get('sent') or data.get('sent_count') or 0
            due = data.get('due') or data.get('due_count') or 0
            return f"Scheduler: controllo notifiche task in scadenza, elementi in scadenza {due}, notifiche inviate {sent}, sorgente {short(data.get('source')) or '-'}"
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
    user_id, username, resolved_actor_type = audit_actor(actor_type)
    db.session.add(AuditLog(
        occurred_at=datetime.utcnow(),
        operation_type=(operation_type or 'operazione')[:120],
        username=username,
        user_id=user_id,
        actor_type=resolved_actor_type,
        details=audit_detail_summary(operation_type, details)[:1000],
    ))
    if commit:
        db.session.commit()

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


def align_table_sequence(table_name):
    """Riallinea una sequenza PostgreSQL prima di un INSERT critico.

    Protegge il flusso di notifica quando il DB contiene dati importati con ID
    espliciti e la sequenza è rimasta indietro. Su SQLite o altri DB non fa nulla.
    """
    if not str(db.engine.url).startswith('postgresql'):
        return
    db.session.execute(text(
        f"SELECT setval(pg_get_serial_sequence('\"{table_name}\"','id'), COALESCE((SELECT MAX(id) FROM \"{table_name}\"), 0) + 1, false)"
    ))






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


def is_conclusion_action(label=None, description=None):
    """Individua le azioni di conclusione dalla label, descrizione label o testo libero."""
    text = ' '.join([
        getattr(label, 'value', '') or '',
        getattr(label, 'description', '') or '',
        description or '',
    ]).lower().replace('’', "'")
    return 'conclusione' in text


def close_incident_from_conclusion_action(incident_id, action):
    """Chiude l'incidente quando viene registrata un'azione di conclusione.

    La chiusura automatica deve mantenere coerenti sia lo stato sia i campi
    separati di fine incidente usati da form, export, report e template PDF:
    ``end_date`` ed ``end_time`` vengono sempre derivati dalla data/ora
    dell'azione di conclusione. L'assegnazione esplicita evita regressioni su
    database già migrati o su codice che legge direttamente i campi separati
    senza passare dalla property ``end_at``.
    """
    label = getattr(action, 'label', None) or (ConfigLabel.query.get(action.label_id) if action.label_id else None)
    if not is_conclusion_action(label, action.description):
        return False
    inc = Incident.query.get(incident_id)
    if not inc:
        return False
    if incident_procedural_status(inc)['has_warnings']:
        setattr(inc, '_closure_blocked_by_procedural_warnings', True)
        return False
    inc.status = 'chiuso'
    if action.when_at:
        action_end = action.when_at.replace(second=0, microsecond=0)
        inc.end_at = action_end
        inc.end_date = action_end.date()
        inc.end_time = action_end.time()
    return True


def incident_procedural_status(inc):
    """Calcola in modo centralizzato gli avvisi procedurali di un incidente.

    La notifica all'utente è richiesta: se non è presente un'azione
    riconducibile a tale notifica, l'incidente deve esporre un avviso sia nel
    dettaglio sia nella lista principale.
    """
    def _action_text(action):
        parts = []
        if action.label and action.label.value:
            parts.append(action.label.value)
        if action.description:
            parts.append(action.description)
        return ' '.join(parts).strip().lower().replace('’', "'")

    action_texts = [_action_text(a) for a in (inc.actions or [])]
    status = {
        'has_csirt_notification': any('comunicazione allo csirt' in value for value in action_texts),
        'has_dpo_notification': any('comunicazione al dpo' in value for value in action_texts),
        'has_privacy_authority_notification': any('comunicazione al garante della privacy' in value for value in action_texts),
        'has_user_notification': any('notifica' in value and 'utente' in value for value in action_texts),
    }
    warnings = []
    if not status['has_csirt_notification']:
        warnings.append('Notifica CSIRT richiesta')
    if not status['has_dpo_notification']:
        warnings.append('Notifica DPO richiesta')
    if inc.personal_data and not status['has_privacy_authority_notification']:
        warnings.append('Notifica al Garante Privacy da valutare')
    if not status['has_user_notification']:
        warnings.append("Notifica all'utente richiesta")
    status['warnings'] = warnings
    status['has_warnings'] = bool(warnings)
    return status

def annotate_procedural_status(incidents):
    """Aggiunge attributi transienti usati dalla lista principale."""
    for inc in incidents:
        status = incident_procedural_status(inc)
        inc.procedural_warnings = status['warnings']
        inc.has_procedural_warnings = status['has_warnings']
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
    rows = ConfigLabel.query.filter(ConfigLabel.kind == kind, ConfigLabel.id.in_(ids)).all()
    order = {value: idx for idx, value in enumerate(ids)}
    return sorted(rows, key=lambda item: order.get(item.id, 10**9))


def people_from_form(field_name='people'):
    ids = unique_int_list(field_name)
    if not ids:
        return []
    rows = Person.query.filter(Person.id.in_(ids)).all()
    order = {value: idx for idx, value in enumerate(ids)}
    return sorted(rows, key=lambda item: order.get(item.id, 10**9))


def commit_with_sequence_retry(sequence_tables=None):
    """Commit robusto contro sequence PostgreSQL disallineate.

    Non assegna mai ID applicativi; in caso di duplicate key su INSERT riallinea
    le sequence indicate e ritenta una sola volta.
    """
    sequence_tables = sequence_tables or []
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if 'duplicate key value violates unique constraint' not in str(exc):
            raise
        for table in sequence_tables:
            align_table_sequence(table)
        flash('Sequenze del database riallineate: ripetere il salvataggio se necessario.', 'warning')
        raise

def add_notification_action_safely(inc, label, description):
    """Crea l'azione automatica senza assegnare manualmente la PK.

    In caso di sequenza PostgreSQL disallineata, riallinea e ritenta una sola
    volta per evitare duplicate key durante l'invio notifiche.
    """
    align_table_sequence('action')
    action = Action(
        incident_id=inc.id,
        when_at=datetime.utcnow(),
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
            when_at=datetime.utcnow(),
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
    name = secure_filename(file_storage.filename)
    stored = str(uuid.uuid4()) + '_' + name
    file_storage.save(os.path.join(current_app.config['UPLOAD_DIR'], stored))
    att = ActionAttachment(action_id=action.id, filename=name, stored_name=stored)
    db.session.add(att)
    return att

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
        ['Data generazione', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')],
    ]
    table = RLTable([[Paragraph(escape(str(a)), small), Paragraph(escape(str(b)), small)] for a,b in meta], colWidths=[4*cm, 12*cm])
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey),('BACKGROUND',(0,0),(0,-1),colors.whitesmoke),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]))
    story += [table, Spacer(1, 0.4*cm), Paragraph('Corpo della mail', styles['Heading2'])]
    for line in (body or '').splitlines() or ['']:
        story.append(Paragraph(escape(line) if line else '&nbsp;', normal))
    doc.build(story)
    return path, stored, f'testo-mail-notifica-{inc.id}-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.pdf'


def labels(kind): return ConfigLabel.query.filter_by(kind=kind).order_by(ConfigLabel.group,ConfigLabel.value).all()
def can_write(): return current_user.role in ['admin','writer']
def can_admin(): return current_user.role=='admin'

def mfa_required_for(user):
    return bool(user and getattr(user, 'mfa_enabled', False) and getattr(user, 'auth_provider', 'local') in ['local','ldap'] and MfaTotpToken.query.filter_by(user_id=user.id).filter(MfaTotpToken.verified_at.isnot(None)).first())

def complete_login_or_mfa(user):
    if mfa_required_for(user):
        session['mfa_user_id'] = user.id
        session['mfa_next'] = request.args.get('next') or url_for('main.index')
        return redirect(url_for('main.mfa_verify'))
    login_user(user)
    return redirect(request.args.get('next') or url_for('main.index'))

def visible(q):
    if current_user.role=='admin' or current_user.role in ['reader','writer']: return q
    if current_user.role=='operator': return q.filter(Incident.creator_id==current_user.id)
    return q.filter(False)
@bp.before_request
def block_disabled():
    g.lang = detect_interface_language()
    if session.get('mfa_user_id') and request.endpoint not in ['main.mfa_verify','main.login','main.logout','static']:
        return redirect(url_for('main.mfa_verify'))
    if current_user.is_authenticated and current_user.role=='disabled' and request.endpoint not in ['main.logout','main.login','main.sso_login','main.sso_callback']:
        logout_user(); flash('Utente disabilitato. Contattare un amministratore.','error'); return redirect(url_for('main.login'))


def setting_map():
    return {row.key: row.value for row in Setting.query.all()}

def bool_setting(cfg, key, default=False):
    value = str(cfg.get(key, '1' if default else '') or '').strip().lower()
    return value in {'1', 'true', 'yes', 'on', 'si', 'sì'}

def sso_settings():
    cfg = setting_map()
    return {
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

def sso_is_enabled(cfg=None):
    cfg = cfg or sso_settings()
    return bool_setting(cfg, 'sso_enabled') and bool(cfg.get('sso_authorization_url')) and bool(cfg.get('sso_token_url')) and bool(cfg.get('sso_client_id'))

def sso_callback_url():
    return url_for('main.sso_callback', _external=True)


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
                    # Molti provider non implementano OPTIONS: proviamo una POST minima, che deve rispondere con errore OAuth2 e non con errore di rete.
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
    user = None
    if subject:
        user = User.query.filter_by(auth_provider='sso', external_id=subject).first()
    if not user:
        user = User.query.filter_by(username=username).first()
    if not user:
        if not bool_setting(cfg, 'sso_auto_create_users', True):
            raise ValueError('Utente SSO non registrato e creazione automatica disabilitata')
        user = User(username=username, name=name, email=email, role=cfg.get('sso_default_role') or 'disabled', is_ldap=False, auth_provider='sso', external_id=subject or None, password_hash=None)
        db.session.add(user)
    else:
        user.name = name or user.name
        user.email = email or user.email
        user.auth_provider = 'sso'
        if subject:
            user.external_id = subject
        user.is_ldap = False
    db.session.commit()
    return user

def ldap_auth(username,password):
    cfg={s.key:s.value for s in Setting.query.all()}
    uri=cfg.get('ldap_uri'); base=cfg.get('ldap_base_dn'); filt=cfg.get('ldap_user_filter') or '(uid={uid})'
    if not uri or not base: return None
    search_filter=filt.replace('{uid}',username)
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
        u=request.form['username']; p=request.form['password']; user=User.query.filter_by(username=u).first()
        if user and not user.is_ldap and verify_password(user.password_hash,p): return complete_login_or_mfa(user)
        info=ldap_auth(u,p)
        if info:
            if not user:
                user=User(username=u,is_ldap=True,auth_provider='ldap',name=info['name'],email=info['email'],role='disabled'); db.session.add(user); db.session.commit()
            else:
                user.name=info['name']; user.email=info['email']; user.is_ldap=True; user.auth_provider='ldap'; db.session.commit()
            if user.role=='disabled': flash('Utente LDAP registrato ma disabilitato.','error'); return render_template('login.html', sso=sso_settings(), sso_enabled=sso_is_enabled())
            return complete_login_or_mfa(user)
        current_app.logger.warning('Errore password/login per utente %s',u); flash('Credenziali non valide.','error')
    return render_template('login.html', sso=sso_settings(), sso_enabled=sso_is_enabled())

@bp.route('/sso/login')
def sso_login():
    cfg = sso_settings()
    if not sso_is_enabled(cfg):
        flash('Login SSO non configurato o non abilitato.', 'error')
        return redirect(url_for('main.login'))
    state = secrets.token_urlsafe(32)
    session['sso_state'] = state
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
    cfg = sso_settings()
    if not sso_is_enabled(cfg):
        flash('Login SSO non configurato o non abilitato.', 'error')
        return redirect(url_for('main.login'))
    if request.args.get('error'):
        flash('Login SSO annullato o rifiutato: ' + request.args.get('error_description', request.args.get('error')), 'error')
        return redirect(url_for('main.login'))
    if not request.args.get('state') or request.args.get('state') != session.pop('sso_state', None):
        flash('Stato SSO non valido. Riprovare il login.', 'error')
        return redirect(url_for('main.login'))
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
        if user.role == 'disabled':
            flash('Utente SSO registrato ma disabilitato. Contattare un amministratore.', 'error')
            return redirect(url_for('main.login'))
        login_user(user)
        return redirect(url_for('main.index'))
    except Exception as exc:
        current_app.logger.exception('SSO login failed')
        flash(f'Login SSO fallito: {exc}', 'error')
        return redirect(url_for('main.login'))

@bp.route('/logout')
def logout(): logout_user(); return redirect(url_for('main.login'))

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

    if kw:
        q = q.filter(or_(
            Incident.name.ilike(f'%{kw}%'),
            Incident.description.ilike(f'%{kw}%'),
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

    # Ordinamento su tutte le colonne mostrate nella home.
    # Le colonne semplici vengono ordinate in SQL; quelle calcolate o multi-valore
    # vengono ordinate in Python dopo il recupero della lista filtrata.
    sql_sort_map = {
        'name': Incident.name,
        'creator_name': Incident.creator_name,
        'status': Incident.status,
    }
    if sort in sql_sort_map:
        col = sql_sort_map[sort]
        incidents = q.order_by(col.asc() if direction == 'asc' else col.desc()).all()
    else:
        incidents = q.all()
        def duration_seconds(inc):
            return inc.effective_duration_seconds or 0
        def people_names(inc):
            return ', '.join(sorted([p.name or '' for p in inc.people]))
        sort_key_map = {
            'people': people_names,
            'duration': duration_seconds,
        }
        incidents = sorted(incidents, key=sort_key_map.get(sort, lambda inc: inc.start_at or datetime.min), reverse=reverse)

    annotate_procedural_status(incidents)

    return render_template(
        'index.html',
        incidents=incidents,
        total=total,
        labels=labels('action_label'),
        sort=sort,
        direction=direction,
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
    return f'{base}{url_for("main.incident_detail", iid=incident_id)}'

@bp.route('/incident/new',methods=['GET','POST'])
@login_required
def incident_new():
    if not can_write(): flash('Permessi insufficienti','error'); return redirect(url_for('main.index'))
    if request.method=='POST':
        start_at = combine_incident_date_time('start', 'start_at', default_now=True)
        end_at = combine_incident_date_time('end', 'end_at')
        inc=Incident(creator_id=current_user.id,creator_name=current_user.name,creator_email=current_user.email,name=request.form['name'],reference=request.form.get('reference') or None,recipient=request.form.get('recipient') or None,description=request.form.get('description'),severity_id=request.form.get('severity_id') or None,personal_data=bool(request.form.get('personal_data')),data_subjects_count=request.form.get('data_subjects_count') or None,data_volume=request.form.get('data_volume') or None,start_at=start_at,end_at=end_at,status=request.form.get('status','aperto'))
        sync_incident_split_datetime(inc)
        inc.categories = labels_from_form('category', 'categories')
        inc.data_types = labels_from_form('data_type', 'data_types')
        inc.people = people_from_form('people')
        inc.recommendations = recommendations_from_form('recommendations')
        align_table_sequence('incident')
        db.session.add(inc)
        try:
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
    return render_template('incident_form.html',inc=None,severities=labels('severity'),categories=labels('category'),data_types=labels('data_type'),people=Person.query.order_by(Person.name).all(), recommendations=Recommendation.query.order_by(Recommendation.text).all())
@bp.route('/incident/<int:iid>',methods=['GET','POST'])
@login_required
def incident_detail(iid):
    inc=visible(Incident.query).get_or_404(iid)
    if request.method=='POST':
        if not can_write(): flash('Permessi insufficienti','error'); return redirect(url_for('main.incident_detail',iid=iid))
        requested_status = request.form.get('status')
        inc.name=request.form['name']; inc.reference=request.form.get('reference') or None; inc.recipient=request.form.get('recipient') or None; inc.description=request.form.get('description'); inc.severity_id=request.form.get('severity_id') or None; inc.personal_data=bool(request.form.get('personal_data')); inc.data_subjects_count=request.form.get('data_subjects_count') or None; inc.data_volume=request.form.get('data_volume') or None; inc.deadline_notifications_muted=bool(request.form.get('deadline_notifications_muted')); inc.start_at=combine_incident_date_time('start', 'start_at', default_now=True); inc.end_at=combine_incident_date_time('end', 'end_at'); sync_incident_split_datetime(inc)
        if requested_status == 'chiuso' and incident_procedural_status(inc)['has_warnings']:
            section_flash('Impossibile chiudere l’incidente: sono ancora presenti avvisi procedurali attivi.', 'incident-main', 'danger')
        else:
            inc.status=requested_status
        inc.categories = labels_from_form('category', 'categories')
        inc.data_types = labels_from_form('data_type', 'data_types')
        inc.people = people_from_form('people')
        inc.recommendations = recommendations_from_form('recommendations')
        try:
            db.session.commit()
            section_flash('Incidente aggiornato', 'incident-main', 'success')
        except IntegrityError as exc:
            db.session.rollback()
            current_app.logger.exception('Errore durante l\'aggiornamento dell\'incidente')
            flash(f'Errore durante l\'aggiornamento dell\'incidente: {exc}', 'error')
        return incident_detail_redirect(iid, 'incident-main')
    procedural_status = incident_procedural_status(inc)
    return render_template(
        'incident_detail.html',
        inc=inc,
        severities=labels('severity'),
        categories=labels('category'),
        data_types=labels('data_type'),
        people=Person.query.order_by(Person.name).all(),
        action_labels=labels('action_label'),
        has_csirt_notification=procedural_status['has_csirt_notification'],
        has_dpo_notification=procedural_status['has_dpo_notification'],
        has_privacy_authority_notification=procedural_status['has_privacy_authority_notification'],
        has_user_notification=procedural_status['has_user_notification'],
        notification_types=notification_type_records(),
        form_templates=list_templates(),
        recommendations=Recommendation.query.order_by(Recommendation.text).all(),
        owner_name=setting_value('security_owner_name'),
        owner_role=setting_value('security_owner_role'),
        structure_name=setting_value('structure_name'),
        responsible_name=setting_value('security_responsible_name'),
        responsible_email=setting_value('security_responsible_email'),
        responsible_phone=setting_value('security_responsible_phone','-'),
        responsible_function=setting_value('security_responsible_function'),
        consequences=incident_consequences(inc),
        measures=incident_measures(inc),
        default_action_when=datetime_local_value(),
        application_timezone=application_timezone_name(),
        section_messages=section_messages,
        global_messages=global_messages,
        split_email_list=_split_email_list,
    )

@bp.route('/incident/<int:iid>/reminder/add',methods=['POST'])
@login_required
def add_incident_reminder(iid):
    inc=visible(Incident.query).get_or_404(iid)
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
    db.session.commit()
    section_flash('Promemoria aggiunto','incident-reminders','success')
    return incident_detail_redirect(iid, 'incident-reminders')

@bp.route('/incident/reminder/<int:rid>/update',methods=['POST'])
@login_required
def update_incident_reminder(rid):
    rem=IncidentReminder.query.get_or_404(rid)
    inc=visible(Incident.query).get_or_404(rem.incident_id)
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
    rem.scheduled_at=scheduled_at; rem.message=message; rem.cc_emails=request.form.get('cc_emails') or ''; rem.updated_at=datetime.utcnow()
    if request.form.get('reset_sent'):
        rem.sent_at=None; rem.last_error=''
    audit_log('incident_reminder:update', json.dumps({'reminder_id': rem.id, 'incident_id': inc.id, 'scheduled_at': scheduled_at.isoformat(timespec='seconds'), 'reset_sent': bool(request.form.get('reset_sent'))}, ensure_ascii=False))
    db.session.commit()
    section_flash('Promemoria aggiornato','incident-reminders','success')
    return incident_detail_redirect(inc.id, 'incident-reminders')

@bp.route('/incident/reminder/<int:rid>/delete',methods=['POST'])
@login_required
def delete_incident_reminder(rid):
    rem=IncidentReminder.query.get_or_404(rid)
    iid=rem.incident_id
    visible(Incident.query).get_or_404(iid)
    if not can_write():
        section_flash('Permessi insufficienti','incident-reminders','error')
        return incident_detail_redirect(iid, 'incident-reminders')
    audit_log('incident_reminder:delete', json.dumps({'reminder_id': rem.id, 'incident_id': iid, 'scheduled_at': rem.scheduled_at.isoformat(timespec='seconds') if rem.scheduled_at else None}, ensure_ascii=False))
    db.session.delete(rem)
    db.session.commit()
    section_flash('Promemoria cancellato','incident-reminders','success')
    return incident_detail_redirect(iid, 'incident-reminders')

@bp.route('/incident/<int:iid>/delete',methods=['POST'])
@login_required
def incident_delete(iid):
    if can_write(): db.session.delete(Incident.query.get_or_404(iid)); db.session.commit()
    return redirect(url_for('main.index'))
@bp.route('/incident/<int:iid>/clone')
@login_required
def clone(iid):
    if not can_write(): return redirect(url_for('main.index'))
    src=Incident.query.get_or_404(iid); inc=Incident(creator_id=current_user.id,creator_name=current_user.name,creator_email=current_user.email,name='Copia di '+src.name,reference=src.reference,recipient=src.recipient,description=src.description,severity_id=src.severity_id,personal_data=src.personal_data,data_subjects_count=src.data_subjects_count,data_volume=src.data_volume,start_at=datetime.utcnow(),status='aperto')
    sync_incident_split_datetime(inc); inc.categories=list(src.categories); inc.data_types=list(src.data_types); inc.people=list(src.people); inc.recommendations=list(src.recommendations); db.session.add(inc); db.session.commit(); return redirect(url_for('main.incident_detail',iid=inc.id))
def create_manual_action_safely(iid):
    """Crea una nuova azione manuale senza assegnare ID espliciti.

    Alcuni database aggiornati/importati possono avere la sequence PostgreSQL
    della tabella action rimasta indietro rispetto al valore massimo già
    presente. In quel caso l'INSERT fallisce con duplicate key. Qui
    riallineiamo prima dell'INSERT e ritentiamo una volta se necessario.
    """
    align_table_sequence('action')
    label_id = request.form.get('label_id') or None
    label = ConfigLabel.query.get(label_id) if label_id else None
    description = request.form.get('description') or None
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
            if getattr(Incident.query.get(iid), '_closure_blocked_by_procedural_warnings', False):
                section_flash('Incidente non chiuso: sono ancora presenti avvisi procedurali attivi.', 'incident-actions', 'warning')
            for f in request.files.getlist('action_files'):
                save_action_attachment_file(f, action)
            db.session.commit()
            section_flash('Azione aggiunta correttamente', 'incident-actions', 'success')
        except IntegrityError:
            db.session.rollback()
            current_app.logger.exception('Errore duplicate key durante inserimento azione manuale')
            section_flash('Errore durante l’inserimento dell’azione: chiave duplicata. Le sequenze del database sono state riallineate, riprovare.', 'incident-actions', 'danger')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Errore durante inserimento azione manuale')
            section_flash('Errore durante l’inserimento dell’azione.', 'incident-actions', 'danger')
    return incident_detail_redirect(iid, 'incident-actions')
@bp.route('/action/<int:aid>/update',methods=['POST'])
@login_required
def update_action(aid):
    a=Action.query.get_or_404(aid); iid=a.incident_id
    if can_write():
        a.person_name=request.form.get('person_name') or a.person_name
        a.description=request.form.get('description') or None
        a.consequence_text=request.form.get('consequence_text') or None
        label_id=request.form.get('label_id') or None
        a.label_id=label_id
        a.exportable=bool(request.form.get('exportable'))
        close_incident_from_conclusion_action(iid, a)
        if getattr(Incident.query.get(iid), '_closure_blocked_by_procedural_warnings', False):
            section_flash('Incidente non chiuso: sono ancora presenti avvisi procedurali attivi.', 'incident-actions', 'warning')
        try:
            db.session.commit(); section_flash('Azione aggiornata', 'incident-actions', 'success')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore aggiornamento azione'); section_flash(f'Errore aggiornamento azione: {exc}', 'incident-actions', 'error')
    return incident_detail_redirect(iid, 'incident-actions')

@bp.route('/action/<int:aid>/delete',methods=['POST'])
@login_required
def del_action(aid):
    a=Action.query.get_or_404(aid); iid=a.incident_id
    if can_write(): db.session.delete(a); db.session.commit()
    return incident_detail_redirect(iid, 'incident-actions')
@bp.route('/action/<int:aid>/exportable',methods=['POST'])
@login_required
def update_action_exportable(aid):
    a=Action.query.get_or_404(aid); iid=a.incident_id
    visible(Incident.query).get_or_404(iid)
    if can_write():
        a.exportable = bool(request.form.get('exportable'))
        db.session.commit()
        section_flash('Flag exportable aggiornato', 'incident-actions', 'success')
    return incident_detail_redirect(iid, 'incident-actions')

@bp.route('/action-attachment/<int:att_id>/download')
@login_required
def download_action_attachment(att_id):
    att=ActionAttachment.query.get_or_404(att_id)
    action=Action.query.get_or_404(att.action_id)
    visible(Incident.query).get_or_404(action.incident_id)
    return send_file(os.path.join(current_app.config['UPLOAD_DIR'],att.stored_name),download_name=att.filename,as_attachment=True)

@bp.route('/action-attachment/<int:att_id>/delete',methods=['POST'])
@login_required
def del_action_attachment(att_id):
    att=ActionAttachment.query.get_or_404(att_id)
    action=Action.query.get_or_404(att.action_id)
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
            for f in request.files.getlist('files'):
                if f.filename:
                    name=secure_filename(f.filename); stored=str(uuid.uuid4())+'_'+name; f.save(os.path.join(current_app.config['UPLOAD_DIR'],stored)); db.session.add(Document(incident_id=iid,filename=name,stored_name=stored)); saved += 1
            db.session.commit()
            section_flash(f'Documenti caricati: {saved}', 'incident-documents', 'success')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore upload documenti'); section_flash(f'Errore upload documenti: {exc}', 'incident-documents', 'error')
    return incident_detail_redirect(iid, 'incident-documents')
@bp.route('/document/<int:did>/download')
@login_required
def download_doc(did):
    d=Document.query.get_or_404(did); visible(Incident.query).get_or_404(d.incident_id); return send_file(os.path.join(current_app.config['UPLOAD_DIR'],d.stored_name),download_name=d.filename,as_attachment=True)
@bp.route('/document/<int:did>/delete',methods=['POST'])
@login_required
def del_doc(did):
    d=Document.query.get_or_404(did); iid=d.incident_id
    if can_write():
        try:
            try: os.remove(os.path.join(current_app.config['UPLOAD_DIR'],d.stored_name))
            except OSError: pass
            db.session.delete(d); db.session.commit(); section_flash('Documento eliminato', 'incident-documents', 'info')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore cancellazione documento'); section_flash(f'Errore cancellazione documento: {exc}', 'incident-documents', 'error')
    return incident_detail_redirect(iid, 'incident-documents')
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
            existing=ConfigLabel.query.filter_by(kind=kind,value=value).first()
            max_hours=request.form.get('max_completion_hours', type=int)
            default_exportable = bool(request.form.get('default_exportable')) if kind == 'action_label' else True
            if existing:
                existing.group=group; existing.description=description
                if kind == 'action_label':
                    existing.max_completion_hours = max_hours if max_hours is not None and max_hours >= 0 else 0
                    existing.default_exportable = default_exportable
                flash('Label già presente: gruppo e descrizione aggiornati','info')
            else:
                db.session.add(ConfigLabel(kind=kind,group=group,value=value,description=description,max_completion_hours=(max_hours if kind=='action_label' and max_hours is not None and max_hours >= 0 else 0),default_exportable=default_exportable))
            try:
                db.session.commit()
            except Exception as exc:
                current_app.logger.exception('Errore durante il salvataggio della label')
                db.session.rollback(); flash(f'Errore salvataggio label: {exc}','error')
    return render_template('admin_labels.html',items=ConfigLabel.query.order_by(ConfigLabel.kind,ConfigLabel.group,ConfigLabel.value).all())
@bp.route('/admin/labels/<int:lid>/update',methods=['POST'])
@login_required
def admin_label_update(lid):
    if not can_admin():
        return redirect(url_for('main.index'))
    lab=ConfigLabel.query.get_or_404(lid)
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
        try:
            db.session.commit(); flash('Label aggiornata','success')
        except Exception as exc:
            db.session.rollback(); current_app.logger.exception('Errore aggiornamento label'); flash(f'Errore aggiornamento label: {exc}','error')
    return redirect(url_for('main.admin_labels'))

@bp.route('/admin/labels/<int:lid>/delete',methods=['POST'])
@login_required
def admin_label_delete(lid):
    if can_admin():
        lab=ConfigLabel.query.get_or_404(lid)
        # Rimuove la label da tutti gli incidenti e dalle azioni prima della cancellazione,
        # così non restano foreign key pendenti e la cancellazione è coerente con la UI.
        for inc in Incident.query.all():
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
            existing=Person.query.filter_by(name=name).first()
            if existing:
                existing.email=email
                flash('Persona già presente: email aggiornata','info')
            else:
                # Il personale non usa più Categoria/Gruppo: l'unico input richiesto è nome + email.
                db.session.add(Person(name=name,email=email,group='personale'))
            try:
                db.session.commit()
            except Exception as exc:
                current_app.logger.exception('Errore durante il salvataggio del personale')
                db.session.rollback(); flash(f'Errore salvataggio personale: {exc}','error')
    return render_template('admin_people.html',people=Person.query.order_by(Person.name).all())

@bp.route('/admin/people/<int:pid>/delete',methods=['POST'])
@login_required
def admin_people_delete(pid):
    if not can_admin(): return redirect(url_for('main.index'))
    person=Person.query.get_or_404(pid)
    for inc in Incident.query.all():
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
        db.session.commit(); flash('Dati titolare salvati','success')
        return redirect(url_for('main.admin_security_owner'))
    return render_template('admin_security_owner.html', owner_name=setting_value('security_owner_name'), owner_role=setting_value('security_owner_role'))

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
        text=(request.form.get('text') or '').strip()
        rid=request.form.get('id')
        if not text:
            flash('Indicare il testo della raccomandazione','error')
        elif rid:
            rec=Recommendation.query.get_or_404(int(rid)); rec.text=text
            try: db.session.commit(); flash('Raccomandazione aggiornata','success')
            except Exception as exc: db.session.rollback(); flash(f'Errore: {exc}','error')
        elif Recommendation.query.filter_by(text=text).first():
            flash('Raccomandazione già presente','info')
        else:
            db.session.add(Recommendation(text=text))
            try: db.session.commit(); flash('Raccomandazione aggiunta','success')
            except Exception as exc: db.session.rollback(); flash(f'Errore: {exc}','error')
    return render_template('admin_recommendations.html', recommendations=Recommendation.query.order_by(Recommendation.text).all())

@bp.route('/admin/recommendations/<int:rid>/delete',methods=['POST'])
@login_required
def admin_recommendation_delete(rid):
    if not can_admin(): return redirect(url_for('main.index'))
    rec=Recommendation.query.get_or_404(rid)
    for inc in Incident.query.all():
        if rec in inc.recommendations:
            inc.recommendations.remove(rec)
    db.session.delete(rec)
    db.session.commit(); flash('Raccomandazione cancellata e rimossa dagli incidenti','info')
    return redirect(url_for('main.admin_recommendations'))

@bp.route('/logo')
def logo_image():
    setting=Setting.query.get('logo_path')
    path=setting.value if setting and setting.value else ''
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path)

@bp.route('/admin/logo',methods=['GET','POST'])
@login_required
def admin_logo():
    if not can_admin(): return redirect(url_for('main.index'))
    setting=Setting.query.get('logo_path') or Setting(key='logo_path',value='')
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
            ext=os.path.splitext(secure_filename(f.filename))[1].lower() or '.img'
            if ext not in ['.png','.jpg','.jpeg','.gif','.webp','.svg']:
                flash('Formato logo non supportato','error')
            else:
                os.makedirs(current_app.config['LOGO_DIR'],exist_ok=True)
                path=os.path.join(current_app.config['LOGO_DIR'],f'logo{ext}')
                f.save(path)
                # rimuove eventuali vecchi logo con estensione diversa
                for old in Path(current_app.config['LOGO_DIR']).glob('logo.*'):
                    if str(old)!=path:
                        try: old.unlink()
                        except OSError: pass
                setting.value=path
                db.session.merge(setting); db.session.commit(); flash('Logo aggiornato','info')
                return redirect(url_for('main.admin_logo'))
    return render_template('admin_logo.html')


@bp.route('/mfa/verify', methods=['GET','POST'])
def mfa_verify():
    uid = session.get('mfa_user_id')
    if not uid:
        return redirect(url_for('main.login'))
    user = User.query.get(uid)
    if not user or user.role == 'disabled':
        session.pop('mfa_user_id', None); session.pop('mfa_next', None)
        flash('Sessione MFA non valida.', 'error')
        return redirect(url_for('main.login'))
    if request.method == 'POST':
        code = (request.form.get('code') or '').replace(' ', '').strip()
        for token in MfaTotpToken.query.filter_by(user_id=user.id).all():
            if pyotp.TOTP(token.secret).verify(code, valid_window=1):
                token.last_used_at = datetime.utcnow(); db.session.commit()
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
            session['pending_mfa_token'] = {'name': request.form.get('name') or 'Token TOTP', 'secret': secret, 'created_at': datetime.utcnow().isoformat()}
            flash('Token generato. Scansiona il QR Code o copia la stringa, poi inserisci il codice TOTP per verificarlo e salvarlo.')
        elif action == 'verify_new':
            pending_token = session.get('pending_mfa_token')
            code = (request.form.get('code') or '').replace(' ', '').strip()
            if not pending_token:
                flash('Nessun token in verifica. Crea un nuovo token TOTP.', 'error')
            elif pyotp.TOTP(pending_token['secret']).verify(code, valid_window=1):
                token = MfaTotpToken(user_id=current_user.id, name=pending_token.get('name') or 'Token TOTP', secret=pending_token['secret'], verified_at=datetime.utcnow())
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
    user = User.query.get_or_404(uid)
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

@bp.route('/admin/users',methods=['GET','POST'])
@login_required
def admin_users():
    if not can_admin(): return redirect(url_for('main.index'))
    if request.method=='POST':
        is_ldap=bool(request.form.get('is_ldap')); u=User(username=request.form['username'],name=request.form.get('name'),email=request.form.get('email'),role=request.form.get('role'),is_ldap=is_ldap,auth_provider='ldap' if is_ldap else 'local',password_hash=hash_password(request.form.get('password','changeme')) if not is_ldap else None); db.session.add(u); db.session.commit()
    return render_template('admin_users.html',users=User.query.order_by(User.username).all())
@bp.route('/admin/user/<int:uid>/role',methods=['POST'])
@login_required
def user_role(uid):
    if can_admin(): u=User.query.get_or_404(uid); u.role=request.form['role']; u.email=request.form.get('email',u.email); db.session.commit()
    return redirect(url_for('main.admin_users'))
@bp.route('/settings/password',methods=['GET','POST'])
@login_required
def change_password():
    if current_user.is_ldap or getattr(current_user, 'auth_provider', 'local') == 'sso': flash('Cambio password non disponibile per utenti LDAP/SSO','error'); return redirect(url_for('main.index'))
    if request.method=='POST':
        if request.form['new_password']!=request.form['new_password2']: flash('Le password non coincidono','error')
        elif not verify_password(current_user.password_hash,request.form['old_password']): flash('Password attuale errata','error')
        else: current_user.password_hash=hash_password(request.form['new_password']); db.session.commit(); flash('Password aggiornata')
    return render_template('change_password.html')

@bp.route('/admin/sso',methods=['GET','POST'])
@login_required
def sso_settings_admin():
    if not can_admin(): return redirect(url_for('main.index'))
    keys = ['sso_enabled','sso_provider_name','sso_authorization_url','sso_token_url','sso_userinfo_url','sso_client_id','sso_client_secret','sso_scopes','sso_username_claim','sso_email_claim','sso_name_claim','sso_subject_claim','sso_auto_create_users','sso_default_role']
    settings = sso_settings()
    test_result = None
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        for k in keys:
            value = request.form.get(k, '')
            if k in ['sso_enabled','sso_auto_create_users']:
                value = '1' if request.form.get(k) else '0'
            settings[k] = value
        if action == 'test_connection':
            test_result = sso_test_configuration(settings)
            if test_result['success']:
                flash('Test configurazione SSO completato senza errori bloccanti')
            else:
                flash('Test configurazione SSO completato con criticità: verificare i dettagli', 'warning')
        else:
            for k in keys:
                s = Setting.query.get(k) or Setting(key=k)
                s.value = settings.get(k, '')
                db.session.merge(s)
            db.session.commit()
            flash('Parametri SSO salvati')
            return redirect(url_for('main.sso_settings_admin'))
    return render_template('sso.html', settings=settings, callback_url=sso_callback_url(), test_result=test_result)

@bp.route('/admin/ldap',methods=['GET','POST'])
@login_required
def ldap_settings():
    if not can_admin(): return redirect(url_for('main.index'))
    settings={s.key:s.value for s in Setting.query.all()}
    result=None
    def form_cfg():
        cfg=dict(settings)
        for k in ['ldap_uri','ldap_base_dn','ldap_bind_dn','ldap_bind_password','ldap_user_filter']:
            cfg[k]=request.form.get(k,cfg.get(k,''))
        return cfg
    if request.method=='POST':
        action=request.form.get('action','save')
        cfg=form_cfg()
        if action=='save':
            for k in ['ldap_uri','ldap_base_dn','ldap_bind_dn','ldap_bind_password','ldap_user_filter']:
                s=Setting.query.get(k) or Setting(key=k); s.value=cfg.get(k,''); db.session.merge(s)
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
                    filt=(cfg.get('ldap_user_filter') or '(uid={uid})').replace('{uid}',uid)
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
    ('%PERSONAL_DATA%', 'Frase esplicativa sul coinvolgimento di dati personali'),
    ('%REPORT%', 'Allega il report PDF aggiornato e inserisce un riferimento nel testo'),
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
    ('%INCIDENT_URL%', 'Link diretto alla pagina dell’incidente'),
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
Dati personali: %PERSONAL_DATA%

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
Dati personali: %PERSONAL_DATA%

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
Dati personali: %PERSONAL_DATA%

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

def notification_type_records(enabled_only=True):
    q = NotificationType.query
    if enabled_only:
        q = q.filter_by(enabled=True)
    return q.order_by(NotificationType.label).all()

def notification_type_map(enabled_only=True):
    rows = notification_type_records(enabled_only=enabled_only)
    if not rows:
        return {'user':'Notifica utente','csirt':'Notifica CSIRT','dpo':'Notifica DPO'}
    return {t.code: t.label for t in rows}

def get_notification_type(kind):
    t = NotificationType.query.filter_by(code=kind).first()
    if t:
        return t
    # fallback compatibile con database precedenti
    fallback = {
        'user': ('Notifica utente','manual','',''),
        'csirt': ('Notifica CSIRT','settings','csirt_email','csirt_cc'),
        'dpo': ('Notifica DPO','settings','dpo_email','dpo_cc'),
    }
    label, mode, recip_key, cc_key = fallback.get(kind, (kind, 'manual', '', ''))
    t = NotificationType(code=kind, label=label, recipient_mode=mode, recipient_setting_key=recip_key, cc_setting_key=cc_key, enabled=True)
    db.session.add(t); db.session.commit()
    return t

def setting_value(key, default=''):
    s = Setting.query.get(key)
    return s.value if s and s.value is not None else default

def set_setting_value(key, value):
    s = Setting.query.get(key) or Setting(key=key)
    s.value = value or ''
    db.session.merge(s)

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
        t = NotificationTemplate(kind=kind, name=DEFAULT_TEMPLATE_NAMES.get(kind, 'Template '+kind), subject=DEFAULT_NOTIFICATION_SUBJECTS.get(kind, 'Notifica incidente %NAME%'), body=DEFAULT_NOTIFICATION_BODIES.get(kind, DEFAULT_NOTIFICATION_BODIES['user']), action_label_id=action_label.id if action_label else None, is_default=True)
        db.session.add(t); db.session.commit()
    return t

def render_notification_text(template, inc, selected_documents=None):
    data_types = ', '.join([x.value for x in inc.data_types]) or 'nessun tipo di dato indicato'
    categories = ', '.join([x.value for x in inc.categories]) or 'nessuna categoria indicata'
    start = inc.start_at.strftime('%d/%m/%Y %H:%M') if inc.start_at else ''
    end = inc.end_at.strftime('%d/%m/%Y %H:%M') if inc.end_at else 'non disponibile'
    personal = 'Sono presenti dati personali coinvolti.' if inc.personal_data else 'Non risultano dati personali coinvolti.'
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
        '%PERSONAL_DATA%': personal,
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
        '%EXTERNAL_URL%': setting_value('application_external_url', 'http://localhost:8000') or 'http://localhost:8000',
        '%INCIDENT_URL%': incident_absolute_url(inc),
    }
    text = template or ''
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

def notification_subject(kind, inc, template_id=None):
    tmpl = get_notification_template(kind, template_id)
    return render_notification_text(tmpl.subject, inc)

def notification_body_template(kind, template_id=None):
    return get_notification_template(kind, template_id).body

def notification_body(kind, inc, selected_documents=None, template_id=None):
    body = render_notification_text(notification_body_template(kind, template_id), inc, selected_documents=selected_documents)
    link = incident_absolute_url(inc)
    if link not in (body or ''):
        body = (body or '').rstrip() + f'\n\nLink diretto incidente: {link}'
    return body

def notification_needs_report(kind, template_id=None):
    return '%REPORT%' in (notification_body_template(kind, template_id) or '')

def notification_needs_documents(kind, template_id=None):
    return '%DOCUMENTS%' in (notification_body_template(kind, template_id) or '')

def split_addresses(value):
    if not value:
        return []
    return [x.strip() for x in value.replace(';', ',').split(',') if x.strip()]

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

def send_notification_email(kind, inc, recipient, cc, subject, body, attach_report, selected_documents=None):
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
    link = incident_absolute_url(inc)
    if link not in (body or ''):
        body = (body or '').rstrip() + f'\n\nLink diretto incidente: {link}'
    msg.set_content(body)
    if attach_report:
        pdf_file = incident_pdf(inc)
        try:
            if isinstance(pdf_file, (str, os.PathLike)):
                with open(pdf_file, 'rb') as fh:
                    pdf_bytes = fh.read()
            else:
                pdf_bytes = pdf_file.getvalue() if hasattr(pdf_file, 'getvalue') else pdf_file.read()
            msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=f'incident-{inc.id}-report.pdf')
        finally:
            if isinstance(pdf_file, (str, os.PathLike)) and os.path.exists(pdf_file):
                try: os.remove(pdf_file)
                except OSError: pass
    for doc in selected_documents or []:
        path = os.path.join(current_app.config['UPLOAD_DIR'], doc.stored_name or '')
        if not os.path.isfile(path):
            raise RuntimeError(f'Documento non trovato sul filesystem: {doc.filename}')
        with open(path, 'rb') as fh:
            data = fh.read()
        msg.add_attachment(data, maintype='application', subtype='octet-stream', filename=doc.filename)
    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    current_app.logger.info('Invio notifica %s incidente %s via SMTP host=%s port=%s ssl=%s starttls=%s auth=%s from=%s to=%s cc=%s attach_report=%s documents=%s', kind, inc.id, host, port, use_ssl, use_tls and not use_ssl, auth_enabled, sender, recipient, cc or '', attach_report, len(selected_documents or []))
    with smtp_cls(host, port, timeout=20) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if auth_enabled:
            if not username:
                raise RuntimeError('Autenticazione SMTP abilitata ma username non configurato')
            smtp.login(username, password or '')
        smtp.send_message(msg)
    return {'sender': sender, 'recipient': recipient, 'cc': cc or '', 'attach_report': attach_report, 'documents': [d.filename for d in (selected_documents or [])]}


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


def _deadline_slot_label(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec='minutes')
    return str(value or '')


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
    # Le notifiche di scadenza sono inviate solo se esiste personale
    # esplicitamente associato all'incidente. L'assenza di unità di
    # personale significa che non deve partire alcuna mail, anche se
    # esistono azioni mancanti con Tempo massimo configurato.
    if not list(inc.people or []):
        return []
    if not start:
        return []
    done_label_ids = {a.label_id for a in (inc.actions or []) if a.label_id}
    labels_q = ConfigLabel.query.filter(
        ConfigLabel.kind == 'action_label',
        ConfigLabel.max_completion_hours.isnot(None),
        ConfigLabel.max_completion_hours > 0,
    ).order_by(ConfigLabel.value).all()
    rows = []
    for lab in labels_q:
        if lab.id in done_label_ids:
            continue
        due_at = start + timedelta(hours=int(lab.max_completion_hours or 0))
        remaining = due_at - now
        total_seconds = int(remaining.total_seconds())
        sign = '' if total_seconds >= 0 else '-'
        total_seconds = abs(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        rows.append({
            'label': lab,
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
    ('%pending_actions%', 'Elenco puntato delle azioni mancanti con scadenza e tempo rimanente'),
    ('%pending_actions_count%', 'Numero di azioni mancanti soggette a tempo massimo'),
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
        label_text = lab.description or lab.value
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
    subject = render_deadline_template(subject_template, inc, pending_rows, recipients, now=now).strip() or default_deadline_subject_template().replace('%incident_name%', inc.name or '')
    body = render_deadline_template(body_template, inc, pending_rows, recipients, now=now)
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

def send_deadline_summary_email(inc, pending_rows):
    recipients = sorted({(p.email or '').strip() for p in (inc.people or []) if (p.email or '').strip()})
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
        f'Messaggio:\n{reminder.message or ""}\n\n'
        f'Link diretto incidente: {incident_absolute_url(inc) if inc else "-"}\n\n'
        f'Questa mail è stata generata automaticamente da Cybersecurity Incident Registry il {generated_at}.\n'
        f'Accesso applicazione: {setting_value("application_external_url", "http://localhost:8000") or "http://localhost:8000"}'
    )

def send_incident_reminder_email(reminder):
    inc = reminder.incident
    recipients = sorted({(p.email or '').strip() for p in (inc.people or []) if (p.email or '').strip()}) if inc else []
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

def _audit_has_reminder_sent(reminder_id):
    pattern = f'"reminder_id": {int(reminder_id)}'
    return AuditLog.query.filter(AuditLog.operation_type=='scheduler:incident_reminder_sent', AuditLog.details.contains(pattern)).first() is not None

def process_due_incident_reminders(source='background_scheduler'):
    now = application_now()
    due = IncidentReminder.query.filter(IncidentReminder.sent_at.is_(None), IncidentReminder.scheduled_at <= now).order_by(IncidentReminder.scheduled_at.asc(), IncidentReminder.id.asc()).all()
    sent = skipped = 0
    errors = []
    for reminder in due:
        if _audit_has_reminder_sent(reminder.id):
            reminder.sent_at = now
            reminder.last_error = ''
            skipped += 1
            continue
        ok, info = send_incident_reminder_email(reminder)
        if ok:
            reminder.sent_at = now
            reminder.last_error = ''
            sent += 1
            audit_log('scheduler:incident_reminder_sent', json.dumps({'reminder_id': reminder.id, 'incident_id': reminder.incident_id, 'scheduled_at': reminder.scheduled_at.isoformat(timespec='seconds'), 'recipients': info, 'source': source}, ensure_ascii=False), actor_type='scheduler')
        else:
            reminder.last_error = info
            skipped += 1
            errors.append(f'Promemoria {reminder.id}: {info}')
    if due:
        audit_log('scheduler:incident_reminder_check', json.dumps({'source': source, 'due': len(due), 'sent': sent, 'skipped': skipped, 'errors': errors[:10]}, ensure_ascii=False), actor_type='scheduler')
        purge_audit_logs()
        db.session.commit()
    return {'due': len(due), 'sent': sent, 'skipped': skipped, 'errors': errors}

def run_deadline_notification_check(force=False, source='request'):
    """Controlla e invia le notifiche periodiche dei task in scadenza.

    La funzione è usata sia dal pulsante manuale sia dallo scheduler automatico.
    Lo scheduler automatico non dipende più dal traffico web: un thread interno
    richiama questa funzione a intervalli brevi e la funzione decide se
    l'intervallo configurato è realmente trascorso. Ogni esecuzione effettiva
    registra un record di audit con attore scheduler/automatic_task.
    """
    if setting_value('notification_deadline_enabled', '0') != '1' and not force:
        return {'sent': 0, 'skipped': 0, 'errors': [], 'executed': False, 'reason': 'disabled'}
    if setting_value('notification_deadline_email_enabled', '1') != '1':
        result = {'sent': 0, 'skipped': 0, 'errors': ['Invio email per task in scadenza disabilitato nelle impostazioni notifiche'], 'executed': True}
        audit_log('scheduler:deadline_notification_check', json.dumps({**result, 'source': source}, ensure_ascii=False), actor_type='scheduler')
        purge_audit_logs()
        db.session.commit()
        return result
    now = application_now()
    schedule_slot = current_deadline_schedule_slot(now)
    last_raw = setting_value('notification_deadline_last_run_at', '')
    if not last_raw:
        last_audit = AuditLog.query.filter_by(operation_type='scheduler:deadline_notification_check').order_by(AuditLog.occurred_at.desc()).first()
        if last_audit:
            try:
                last_details = json.loads(last_audit.details or '{}')
                last_raw = last_details.get('schedule_slot') or ''
            except Exception:
                last_raw = ''
    if not force:
        try:
            last = datetime.fromisoformat(last_raw) if last_raw else None
        except ValueError:
            last = None
        if last and last >= schedule_slot:
            return {
                'sent': 0, 'skipped': 0, 'errors': [], 'executed': False,
                'reason': 'schedule_slot_already_executed',
                'next_run_at': next_deadline_notification_at(now).isoformat(timespec='minutes'),
            }
    sent = skipped = 0
    errors = []
    incidents_checked = 0
    incidents_with_pending = 0
    incidents = Incident.query.filter(Incident.status != 'chiuso', Incident.deadline_notifications_muted.is_(False)).all()
    for inc in incidents:
        incidents_checked += 1
        rows = pending_deadline_actions_for_incident(inc, now=now)
        if not rows:
            continue
        incidents_with_pending += 1
        try:
            ok, info = send_deadline_summary_email(inc, rows)
            if ok:
                sent += 1
            else:
                skipped += 1
                errors.append(f'Incidente {inc.id}: {info}')
        except Exception as exc:
            current_app.logger.exception('Errore notifica scadenze incidente %s', inc.id)
            errors.append(f'Incidente {inc.id}: {exc}')
    if not force:
        # Memorizza lo slot pianificato, non l'ora di avvio/esecuzione: in questo modo
        # gli intervalli restano ancorati alla mezzanotte del giorno corrente.
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
        'next_run_at': next_deadline_notification_at(now).isoformat(timespec='minutes'),
        'incidents_checked': incidents_checked,
        'incidents_with_pending': incidents_with_pending,
    }
    audit_log('scheduler:deadline_notification_check', json.dumps({**result, 'errors': errors[:10]}, ensure_ascii=False), actor_type='scheduler')
    purge_audit_logs()
    db.session.commit()
    return result


@bp.before_app_request
def maybe_run_deadline_notification_check():
    # Esecuzione leggera opportunistica: il controllo reale parte solo se è
    # abilitato e se l'intervallo configurato è trascorso.
    try:
        if request.endpoint and request.endpoint.startswith('static'):
            return
        run_deadline_notification_check(force=False, source='request_hook')
        process_due_incident_reminders(source='request_hook')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Controllo automatico scadenze azioni non completato')



_deadline_scheduler_started = False
_deadline_scheduler_lock = threading.Lock()

def start_deadline_notification_scheduler(app):
    """Avvia il controllo periodico automatico delle notifiche in scadenza.

    Il controllo precedente era solo opportunistico e partiva durante le
    richieste web: se l'applicazione restava inattiva, nessuna notifica veniva
    inviata allo scadere dell'intervallo. Questo thread interno esegue il poll
    indipendentemente dal traffico web. La funzione resta idempotente per
    evitare avvii duplicati nello stesso processo.
    """
    global _deadline_scheduler_started
    if _deadline_scheduler_started:
        return
    if os.getenv('CIR_ENABLE_DEADLINE_SCHEDULER', '1').lower() in {'0', 'false', 'no'}:
        app.logger.info('Scheduler notifiche task in scadenza disabilitato da CIR_ENABLE_DEADLINE_SCHEDULER')
        return
    # Evita il doppio thread quando si usa il reloader di Flask in sviluppo.
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return
    _deadline_scheduler_started = True

    def loop():
        poll_seconds = max(30, int(os.getenv('CIR_DEADLINE_SCHEDULER_POLL_SECONDS', '60') or '60'))
        app.logger.info('Scheduler notifiche task in scadenza avviato con poll=%ss', poll_seconds)
        while True:
            if not _deadline_scheduler_lock.acquire(blocking=False):
                time.sleep(poll_seconds)
                continue
            try:
                with app.app_context():
                    run_deadline_notification_check(force=False, source='background_scheduler')
                    process_due_incident_reminders(source='background_scheduler')
            except Exception:
                try:
                    with app.app_context():
                        db.session.rollback()
                        app.logger.exception('Scheduler notifiche task in scadenza non completato')
                except Exception:
                    app.logger.exception('Scheduler notifiche task in scadenza non completato')
            finally:
                _deadline_scheduler_lock.release()
            time.sleep(poll_seconds)

    t = threading.Thread(target=loop, name='cir-deadline-notification-scheduler', daemon=True)
    t.start()


@bp.before_app_request
def mark_auditable_request():
    g.audit_started_at = datetime.utcnow()

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
            t = NotificationType.query.get_or_404(type_id)
            if NotificationTemplate.query.filter_by(kind=t.code).first():
                flash('Impossibile cancellare il tipo: esistono template associati. Cancellare o spostare prima i template.', 'error')
            elif t.code in ['user','csirt','dpo']:
                flash('I tipi predefiniti non possono essere cancellati.', 'error')
            else:
                db.session.delete(t); db.session.commit(); flash('Tipo di notifica cancellato')
            return redirect(url_for('main.notification_types'))
        code = (request.form.get('code') or '').strip().lower().replace(' ','_')
        label = (request.form.get('label') or '').strip()
        description = request.form.get('description') or ''
        mode = request.form.get('recipient_mode') or 'manual'
        recipient_key = request.form.get('recipient_setting_key') or ''
        cc_key = request.form.get('cc_setting_key') or ''
        enabled = bool(request.form.get('enabled'))
        if not code or not label:
            flash('Codice e nome del tipo sono obbligatori.', 'error')
        else:
            t = NotificationType.query.get(type_id) if type_id else NotificationType()
            if t.id and t.code in ['user','csirt','dpo'] and code != t.code:
                flash('Il codice dei tipi predefiniti non può essere modificato.', 'error')
            else:
                t.code=code; t.label=label; t.description=description; t.recipient_mode=mode; t.recipient_setting_key=recipient_key; t.cc_setting_key=cc_key; t.enabled=enabled
                db.session.add(t)
                try:
                    db.session.commit(); flash('Tipo di notifica salvato')
                except IntegrityError:
                    db.session.rollback(); flash('Esiste già un tipo di notifica con lo stesso codice.', 'error')
        return redirect(url_for('main.notification_types'))
    edit_id=request.args.get('edit', type=int)
    editing=NotificationType.query.get(edit_id) if edit_id else None
    return render_template('notification_types.html', types=NotificationType.query.order_by(NotificationType.label).all(), editing=editing)

@bp.route('/notifiche/impostazioni', methods=['GET','POST'])
@login_required
def notification_settings():
    if not can_admin(): return redirect(url_for('main.index'))
    keys = ['csirt_email','dpo_email','csirt_cc','dpo_cc','smtp_host','smtp_port','smtp_use_tls','smtp_use_ssl','smtp_auth_enabled','smtp_username','smtp_password','smtp_default_sender','notification_deadline_enabled','notification_deadline_email_enabled','notification_deadline_schedule_mode','notification_deadline_cron_times','notification_deadline_interval_hours','notification_deadline_interval_minutes','notification_deadline_subject_template','notification_deadline_body_template']
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
        'notification_deadline_schedule_mode':'interval','notification_deadline_cron_times':'','notification_deadline_interval_hours':'24','notification_deadline_interval_minutes':'0',
        'notification_deadline_subject_template': default_deadline_subject_template(),
        'notification_deadline_body_template': default_deadline_body_template(),
    }
    settings = {k: setting_value(k, defaults.get(k,'')) for k in keys}
    preview_subject, preview_body = sample_deadline_preview()
    schedule_info = format_deadline_schedule_info()
    return render_template('notification_settings.html', settings=settings, deadline_placeholders=DEADLINE_NOTIFICATION_PLACEHOLDERS, preview_subject=preview_subject, preview_body=preview_body, schedule_info=schedule_info)

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
        action_label_id = request.form.get('action_label_id', type=int)
        tmpl.action_label_id = action_label_id or None
        if request.form.get('is_default'):
            NotificationTemplate.query.filter_by(kind=kind).update({'is_default': False})
            tmpl.is_default = True
        db.session.add(tmpl); db.session.commit(); flash('Template di notifica aggiunto')
        return redirect(url_for('main.notification_template', kind=kind))
    return render_template('notification_template.html', kind=kind, title='Nuovo template', fields=NOTIFICATION_FIELDS, templates=[], editing=None, adding=True, kinds=kinds, action_labels=labels('action_label'))

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
                action_label_id=source.action_label_id,
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
        action_label_id = request.form.get('action_label_id', type=int)
        tmpl.action_label_id = action_label_id or None
        if request.form.get('is_default'):
            NotificationTemplate.query.filter_by(kind=kind).update({'is_default': False})
            tmpl.is_default = True
        db.session.add(tmpl); db.session.commit(); flash(f'Template {title} salvato')
        return redirect(url_for('main.notification_template', kind=kind))
    templates = NotificationTemplate.query.filter_by(kind=kind).order_by(NotificationTemplate.is_default.desc(), NotificationTemplate.name).all()
    return render_template('notification_template.html', kind=kind, title=title, fields=NOTIFICATION_FIELDS, templates=templates, editing=editing, adding=False, action_labels=labels('action_label'))

@bp.route('/incident/<int:iid>/notify/<kind>/preview')
@login_required
def notify_preview(iid, kind):
    if kind not in notification_type_map(): abort(404)
    ntype = get_notification_type(kind)
    inc = visible(Incident.query).get_or_404(iid)
    if not can_write():
        flash('Permessi insufficienti per inviare notifiche','error')
        return redirect(url_for('main.incident_detail', iid=iid))
    ensure_default_notification_templates(); db.session.commit()
    if ntype.recipient_mode == 'settings':
        recipient = setting_value(ntype.recipient_setting_key)
        cc = setting_value(ntype.cc_setting_key)
        recipient_locked = True
    else:
        recipient = request.args.get('recipient') or inc.creator_email or ''
        cc = request.args.get('cc') or ''
        recipient_locked = False
    template_id = request.args.get('template_id', type=int)
    tmpl = get_notification_template(kind, template_id)
    subject = notification_subject(kind, inc, tmpl.id)
    needs_documents = notification_needs_documents(kind, tmpl.id)
    attach_report = notification_needs_report(kind, tmpl.id)
    body = notification_body(kind, inc, template_id=tmpl.id)
    title = ntype.label
    templates = NotificationTemplate.query.filter_by(kind=kind).order_by(NotificationTemplate.is_default.desc(), NotificationTemplate.name).all()
    if needs_documents and not inc.documents:
        flash('Il template contiene %DOCUMENTS%, ma non sono presenti documenti allegati all’incidente. Invio bloccato.', 'error')
    return render_template('notification_preview.html', inc=inc, kind=kind, title=title, sender=current_user.email or '', recipient=recipient, cc=cc, subject=subject, body=body, attach_report=attach_report, needs_documents=needs_documents, template=tmpl, templates=templates, recipient_locked=recipient_locked)

@bp.route('/incident/<int:iid>/notify/<kind>/send', methods=['POST'])
@login_required
def notify_send(iid, kind):
    if kind not in notification_type_map(): abort(404)
    ntype = get_notification_type(kind)
    inc = visible(Incident.query).get_or_404(iid)
    if not can_write():
        flash('Permessi insufficienti per inviare notifiche','error')
        return redirect(url_for('main.incident_detail', iid=iid))
    template_id = request.form.get('template_id', type=int)
    tmpl = get_notification_template(kind, template_id)
    if ntype.recipient_mode == 'settings':
        recipient = setting_value(ntype.recipient_setting_key)
        cc = setting_value(ntype.cc_setting_key)
        if not recipient:
            flash('Destinatario non configurato nelle impostazioni.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id))
    else:
        # Il destinatario manuale viene inserito nella pagina di anteprima e
        # reinviato come campo hidden nella conferma. Manteniamo anche alcuni
        # alias per compatibilità con versioni precedenti dei template.
        recipient = (
            request.form.get('recipient')
            or request.form.get('manual_recipient')
            or request.form.get('to')
            or ''
        ).strip()
        cc = (request.form.get('cc') or request.form.get('manual_cc') or '').strip()
        if not recipient:
            flash('Specificare un destinatario per questa notifica.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id, recipient=recipient, cc=cc))
    subject = notification_subject(kind, inc, tmpl.id)
    title = ntype.label
    attach_report = notification_needs_report(kind, tmpl.id)
    needs_documents = notification_needs_documents(kind, tmpl.id)
    selected_documents = []
    if needs_documents:
        selected_ids = [int(x) for x in request.form.getlist('document_ids') if x.isdigit()]
        if not inc.documents:
            flash('Invio bloccato: il template contiene %DOCUMENTS%, ma l’incidente non ha documenti allegati.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id))
        if not selected_ids:
            flash('Invio bloccato: selezionare almeno un documento da allegare perché il template contiene %DOCUMENTS%.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id))
        selected_documents = Document.query.filter(Document.incident_id == inc.id, Document.id.in_(selected_ids)).all()
        if len(selected_documents) != len(set(selected_ids)):
            flash('Invio bloccato: uno o più documenti selezionati non appartengono a questo incidente.', 'error')
            return redirect(url_for('main.notify_preview', iid=iid, kind=kind, template_id=tmpl.id))
    body = notification_body(kind, inc, selected_documents=selected_documents if needs_documents else None, template_id=tmpl.id)
    try:
        send_info = send_notification_email(kind, inc, recipient, cc, subject, body, attach_report, selected_documents=selected_documents)
        label = tmpl.action_label or ConfigLabel.query.filter_by(kind='action_label', value=notification_label_value(kind)).first()
        if not label:
            label = ConfigLabel(kind='action_label', group='azioni', value=notification_label_value(kind))
            db.session.add(label); db.session.flush()
        docs_text = ', '.join(send_info.get('documents') or []) or 'nessuno'
        desc = f'Invio {title.lower()} con template "{tmpl.name}". Mittente: {send_info["sender"]}; Destinatario: {send_info["recipient"]}; CC: {send_info["cc"] or "nessuno"}; Report PDF allegato: {"sì" if send_info["attach_report"] else "no"}; Documenti allegati: {docs_text}.'
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
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib import colors
    from xml.sax.saxutils import escape

    static_dir = Path(current_app.static_folder)
    logo_path = static_dir / 'help' / 'app-logo.png'
    visual_paths = [
        ('Figura 1 - Flusso amministrativo consigliato', static_dir / 'help' / 'admin-flow.png'),
        ('Figura 2 - Configurazione SSO e controllo connessione', static_dir / 'help' / 'admin-screenshot-sso.png'),
        ('Figura 3 - Configurazione template PDF e mapping', static_dir / 'help' / 'admin-screenshot-modules.png'),
        ('Figura 4 - Mappa delle aree di governance amministrativa', static_dir / 'help' / 'admin-chart-governance.png'),
    ]

    html = render_template('admin_help_en.html' if getattr(g, 'lang', 'it') == 'en' else 'admin_help.html')
    html = re.sub(r'<(script|style|figure)[\s\S]*?</\1>', ' ', html, flags=re.I)
    html = re.sub(r'<nav[\s\S]*?</nav>', ' ', html, flags=re.I)
    html = re.sub(r'<li[^>]*>', '\n• ', html, flags=re.I)
    html = re.sub(r'</(p|h1|h2|h3|tr|section|div)>', '\n', html, flags=re.I)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    text = unescape(re.sub(r'<[^>]+>', ' ', html))
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    skip = {'Scarica PDF amministrativo', 'Vai all’indice', 'Digita una parola per filtrare i capitoli.'}
    lines = [line for line in lines if line and line not in skip and not line.startswith('Cerca nella documentazione')]

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
    story.append(Paragraph('Questa guida descrive l’amministrazione completa dell’applicazione: ruoli, utenti, LDAP, OAuth2/SSO, liste, categorie, notifiche, moduli PDF, documentazione, export, import, backup e controlli periodici. Il logo presente è il logo applicativo e non include il logo custom configurabile.', callout))
    story.append(PageBreak())

    chapters = [line for line in lines if re.match(r'^\d+\.\s+', line)]
    if chapters:
        story.append(Paragraph('Indice', h2))
        tbl = [[Paragraph(escape(c), normal)] for c in chapters]
        t = Table(tbl, colWidths=[17.0*cm])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f8fafc')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e2e8f0')),('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor('#e2e8f0')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(t); story.append(PageBreak())

    visual_inserted = False
    for line in lines:
        if line.startswith('Documentazione amministrativa') or line.startswith('Cybersecurity Incident Registry'):
            continue
        if re.match(r'^\d+\.\s+', line):
            story.append(Paragraph(escape(line), h2))
            if not visual_inserted:
                for label, path in visual_paths:
                    if path.exists():
                        img = Image(str(path), width=16.3*cm, height=16.3*cm * 0.46)
                        img.hAlign = 'CENTER'
                        story.append(KeepTogether([img, Paragraph(escape(label), caption), Spacer(1, .2*cm)]))
                visual_inserted = True
            continue
        if line.startswith('• '):
            story.append(Paragraph(escape(line), bullet)); continue
        if len(line) < 90 and (line.startswith('Esempio') or line.startswith('Configurazione') or line.startswith('Procedura') or line in {'Buone pratiche','Campi database incidenti','Misure adottate','Sostituzione template','Backup consigliato','Checklist mensile','SSO non funziona','Modulo PDF incompleto','Export o import non coerente'}):
            story.append(Paragraph(escape(line), h3)); continue
        story.append(Paragraph(escape(line), normal))

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
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib import colors
    from xml.sax.saxutils import escape

    static_dir = Path(current_app.static_folder)
    logo_path = static_dir / 'help' / 'app-logo.png'
    visual_paths = [
        ('Figura 1 - Flusso consigliato di gestione incidente', static_dir / 'help' / 'flow-incident-lifecycle.png'),
        ('Figura 2 - Pagina principale con avvisi procedurali', static_dir / 'help' / 'screenshot-dashboard.png'),
        ('Figura 3 - Dettaglio incidente e timeline azioni', static_dir / 'help' / 'screenshot-incident-detail.png'),
        ('Figura 4 - Configurazione moduli PDF e mapping', static_dir / 'help' / 'screenshot-modules.png'),
        ('Figura 5 - Esempi di grafici di reportistica', static_dir / 'help' / 'charts-reporting.png'),
    ]

    html = render_template('help_en.html' if getattr(g, 'lang', 'it') == 'en' else 'help.html')
    html = re.sub(r'<(script|style|figure)[\s\S]*?</\1>', ' ', html, flags=re.I)
    html = re.sub(r'<nav[\s\S]*?</nav>', ' ', html, flags=re.I)
    html = re.sub(r'<li[^>]*>', '\n• ', html, flags=re.I)
    html = re.sub(r'</(p|h1|h2|h3|tr|section|div)>', '\n', html, flags=re.I)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    text = unescape(re.sub(r'<[^>]+>', ' ', html))
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    skip = {'Scarica PDF', 'Vai all’indice', 'Digita una parola per filtrare i capitoli.'}
    lines = [line for line in lines if line and line not in skip and not line.startswith('Cerca nella documentazione')]

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

    story = []
    if logo_path.exists():
        story.append(Image(str(logo_path), width=3.0*cm, height=3.0*cm))
        story[-1].hAlign = 'CENTER'
    story.append(Paragraph('Cybersecurity Incident Registry', h1))
    story.append(Paragraph('Documentazione utente completa', ParagraphStyle('subtitle', parent=normal, alignment=TA_CENTER, fontSize=12, leading=15, textColor=colors.HexColor('#475569'))))
    story.append(Spacer(1, .35*cm))
    story.append(Paragraph('La documentazione descrive funzionalità, flussi operativi, ruoli, incidenti, azioni, notifiche, moduli PDF, report, export/import e configurazioni amministrative. Il logo presente in questa guida è il logo applicativo e non include il logo custom configurabile.', callout))
    story.append(PageBreak())

    # Indice sintetico professionale
    chapters = [line for line in lines if re.match(r'^\d+\.\s+', line)]
    if chapters:
        story.append(Paragraph('Indice', h2))
        tbl = [[Paragraph(escape(c), normal)] for c in chapters]
        t = Table(tbl, colWidths=[17.0*cm])
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f8fafc')),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#e2e8f0')),('INNERGRID',(0,0),(-1,-1),0.25,colors.HexColor('#e2e8f0')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(t); story.append(PageBreak())

    visual_inserted = False
    for line in lines:
        if line.startswith('Documentazione utente') or line.startswith('Cybersecurity Incident Registry'):
            continue
        if re.match(r'^\d+\.\s+', line):
            story.append(Paragraph(escape(line), h2))
            if not visual_inserted:
                for label, path in visual_paths:
                    if path.exists():
                        img = Image(str(path), width=16.3*cm, height=16.3*cm * 0.46)
                        img.hAlign = 'CENTER'
                        story.append(KeepTogether([img, Paragraph(escape(label), caption), Spacer(1, .2*cm)]))
                visual_inserted = True
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
    inc=visible(Incident.query).get_or_404(iid); return send_file(incident_pdf(inc),download_name=f'incident-{iid}.pdf',as_attachment=True)


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
    Setting, User, MfaTotpToken, ConfigLabel, Person, Recommendation,
    NotificationType, NotificationTemplate, FormTemplateConfig,
    FormTemplateBinary, FormFieldMapping, Incident, Action, Document,
    ActionAttachment, IncidentReminder, AuditLog,
]

FULL_EXPORT_TABLES = {
    'settings': Setting,
    'users': User,
    'mfa_totp_tokens': MfaTotpToken,
    'config_labels': ConfigLabel,
    'people': Person,
    'recommendations': Recommendation,
    'notification_types': NotificationType,
    'notification_templates': NotificationTemplate,
    'form_template_configs': FormTemplateConfig,
    'form_template_binaries': FormTemplateBinary,
    'form_field_mappings': FormFieldMapping,
    'incidents': Incident,
    'actions': Action,
    'documents': Document,
    'action_attachments': ActionAttachment,
    'incident_reminders': IncidentReminder,
    'audit_logs': AuditLog,
}

FULL_EXPORT_RELATION_TABLES = {
    'incident_people': incident_people,
    'incident_categories': incident_categories,
    'incident_data_types': incident_data_types,
    'incident_recommendations': incident_recommendations,
}

def _export_tables_payload():
    return {
        name: [_row(x) for x in model.query.order_by(*model.__table__.primary_key.columns).all()]
        for name, model in FULL_EXPORT_TABLES.items()
    }

def _export_relations_payload():
    return {name: _table_rows(table) for name, table in FULL_EXPORT_RELATION_TABLES.items()}

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
        'file_groups': ['documents', 'action_attachments', 'form_templates', 'custom_logo', 'application_logos'],
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
        flash('Permessi insufficienti per esportare tutti i dati applicativi','error')
        return redirect(url_for('main.index'))

    fd, path = tempfile.mkstemp(prefix='cir-full-export-', suffix='.tar.gz')
    os.close(fd)
    now = datetime.utcnow().isoformat()

    payload = {
        'format': 'cybersecurity-incident-registry-full-export',
        'version': 4,
        'created_at': now,
        'schema': _export_schema_payload(),
        'tables': _export_tables_payload(),
        'relations': _export_relations_payload(),
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
        },
    }

    logo_setting = Setting.query.get('logo_path')
    if logo_setting and logo_setting.value and os.path.exists(logo_setting.value):
        payload['files']['logo'] = {
            'path': logo_setting.value,
            'archive_path': f'files/logo/{os.path.basename(logo_setting.value)}'
        }

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

    return send_file(path, download_name=f'export-completo-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}.tar.gz', as_attachment=True)

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
                start_at = datetime.utcnow()
                end_at = None
                if ' - ' in periodo:
                    a,b = periodo.split(' - ',1)
                    try: start_at = datetime.fromisoformat(a.strip())
                    except Exception: pass
                    try: end_at = datetime.fromisoformat(b.strip()) if b.strip() else None
                    except Exception: pass
                inc = Incident(
                    creator_id=current_user.id,
                    creator_name=current_user.name or current_user.username,
                    creator_email=current_user.email,
                    name=name,
                    reference=row.get('riferimento') or row.get('reference') or None,
                    recipient=row.get('destinatario') or row.get('recipient') or None,
                    description=row.get('descrizione') or row.get('description') or '',
                    start_at=start_at,
                    end_at=end_at,
                    status=(row.get('stato') or 'aperto').strip() or 'aperto'
                )
                people_text = row.get('personale') or ''
                for pname in [p.strip() for p in people_text.split(',') if p.strip()]:
                    person = Person.query.filter_by(name=pname).first()
                    if not person:
                        person = Person(name=pname, group='import')
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

        tmp = f'/tmp/{uuid.uuid4()}-import.tar.gz'
        f.save(tmp)
        try:
            with tarfile.open(tmp, 'r:gz') as archive:
                member = archive.getmember('export.json')
                data = json.load(archive.extractfile(member))
                if data.get('format') != 'cybersecurity-incident-registry-full-export':
                    raise ValueError('Formato export completo non riconosciuto')
                tables = data.get('tables', {})
                relations = data.get('relations', {})

                # Pulizia in ordine di dipendenza. L'import completo ripristina lo stato
                # dell'archivio e sostituisce quello corrente.
                db.session.execute(incident_people.delete())
                db.session.execute(incident_categories.delete())
                db.session.execute(incident_data_types.delete())
                db.session.execute(incident_recommendations.delete())
                for model in [ActionAttachment, Document, IncidentReminder, Action, Incident, FormFieldMapping, FormTemplateBinary, FormTemplateConfig, NotificationTemplate, NotificationType, Recommendation, Person, ConfigLabel, MfaTotpToken, AuditLog, User, Setting]:
                    db.session.query(model).delete()
                db.session.flush()

                for row in tables.get('settings', []):
                    db.session.add(Setting(**_coerce_row_for_model(Setting, row)))
                for row in tables.get('users', []):
                    db.session.add(User(**_coerce_row_for_model(User, row)))
                db.session.flush()

                for row in tables.get('mfa_totp_tokens', []):
                    db.session.add(MfaTotpToken(**_coerce_row_for_model(MfaTotpToken, row)))
                for row in tables.get('audit_logs', []):
                    db.session.add(AuditLog(**_coerce_row_for_model(AuditLog, row)))
                db.session.flush()

                for row in tables.get('config_labels', []):
                    db.session.add(ConfigLabel(**_coerce_row_for_model(ConfigLabel, row)))
                for row in tables.get('people', []):
                    db.session.add(Person(**_coerce_row_for_model(Person, row)))
                for row in tables.get('recommendations', []):
                    db.session.add(Recommendation(**_coerce_row_for_model(Recommendation, row)))

                for row in tables.get('notification_types', []):
                    db.session.add(NotificationType(**_coerce_row_for_model(NotificationType, row)))
                db.session.flush()

                for row in tables.get('notification_templates', []):
                    db.session.add(NotificationTemplate(**_coerce_row_for_model(NotificationTemplate, row)))
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
                    db.session.add(Incident(**_coerce_row_for_model(Incident, row)))
                db.session.flush()

                for row in tables.get('actions', []):
                    db.session.add(Action(**_coerce_row_for_model(Action, row)))
                for row in tables.get('documents', []):
                    db.session.add(Document(**_coerce_row_for_model(Document, row)))
                for row in tables.get('action_attachments', []):
                    db.session.add(ActionAttachment(**_coerce_row_for_model(ActionAttachment, row)))
                for row in tables.get('incident_reminders', []):
                    db.session.add(IncidentReminder(**_coerce_row_for_model(IncidentReminder, row)))
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
                        setting = Setting.query.get('logo_path') or Setting(key='logo_path')
                        setting.value = dst
                        db.session.merge(setting)
                    except KeyError:
                        current_app.logger.warning('Logo indicato nel manifest ma non presente nell archivio')

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

            purge_audit_logs()
            db.session.commit()
            flash('Import completo completato: database, configurazioni, audit log, utenti, MFA, notifiche, logo, documenti, allegati e template moduli PDF ripristinati. I record audit oltre retention sono stati eliminati.','info')
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
    now = datetime.utcnow()
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
                return render_template('modules_configuration.html', templates=templates, selected=selected, db_fields=available_incident_fields(), mappings=current_mappings, template_configs={t.name:get_template_config(t.name) for t in templates}, preview=preview)
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
    return render_template('modules_configuration.html', templates=templates, selected=selected, db_fields=available_incident_fields(), mappings=current_mappings, template_configs={t.name:get_template_config(t.name) for t in templates}, preview=preview)

@bp.route('/incident/<int:iid>/forms/generate', methods=['POST'])
@login_required
def generate_incident_forms(iid):
    inc = visible(Incident.query).get_or_404(iid)
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
    visible(Incident.query).get_or_404(iid)
    safe = Path(stored_name).name
    path = Path(current_app.config['UPLOAD_DIR']) / safe
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=False)

@bp.route('/incident/<int:iid>/forms/confirm', methods=['POST'])
@login_required
def confirm_generated_forms(iid):
    inc = visible(Incident.query).get_or_404(iid)
    if not can_write():
        section_flash('Permessi insufficienti', 'incident-forms', 'error')
        return incident_detail_redirect(iid, 'incident-forms')
    upload_dir = Path(current_app.config['UPLOAD_DIR'])
    action = request.form.get('decision','reject')
    pdf_files = request.form.getlist('pdf_stored')
    names = request.form.getlist('document_name')
    if action != 'accept':
        for stored in pdf_files:
            try:
                (upload_dir / Path(stored).name).unlink(missing_ok=True)
            except Exception:
                pass
        section_flash('Generazione rifiutata: i file temporanei sono stati eliminati.', 'incident-forms', 'info')
        return incident_detail_redirect(iid, 'incident-forms')
    saved = 0
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
        db.session.add(Document(incident_id=inc.id, filename=final_path.name, stored_name=final_path.name))
        saved += 1
    try:
        db.session.commit()
        section_flash(f'Documenti generati e allegati: {saved}', 'incident-forms', 'success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Errore salvataggio documenti generati dopo anteprima')
        section_flash(f'Errore salvataggio documenti generati: {exc}', 'incident-forms', 'error')
    return incident_detail_redirect(iid, 'incident-forms')

def recommendations_from_form(field='recommendations'):
    ids=unique_int_list(field)
    if not ids:
        return []
    return Recommendation.query.filter(Recommendation.id.in_(ids)).order_by(Recommendation.text).all()

def setting_value(key, default=''):
    s=Setting.query.get(key)
    return s.value if s and s.value is not None else default

def set_setting_value(key, value):
    s=Setting.query.get(key)
    if not s:
        s=Setting(key=key,value=value or '')
        db.session.add(s)
    else:
        s.value=value or ''
    return s


@bp.route('/admin/audit')
@login_required
def admin_audit():
    if not can_admin():
        return redirect(url_for('main.index'))
    purge_audit_logs()
    db.session.commit()
    q = AuditLog.query
    total_records = AuditLog.query.count()
    search = (request.args.get('q') or '').strip()
    operation_type = (request.args.get('operation_type') or '').strip()
    username = (request.args.get('username') or '').strip()
    actor_type = (request.args.get('actor_type') or '').strip()
    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()
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
    if start:
        try:
            q = q.filter(AuditLog.occurred_at >= datetime.fromisoformat(start))
        except ValueError:
            flash('Data inizio ricerca audit non valida', 'error')
    if end:
        try:
            q = q.filter(AuditLog.occurred_at <= datetime.fromisoformat(end))
        except ValueError:
            flash('Data fine ricerca audit non valida', 'error')
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
    selected_from = offset + 1 if filtered_count else 0
    selected_to = min(offset + page_size, filtered_count)
    return render_template(
        'admin_audit.html',
        logs=logs,
        search=search,
        operation_type=operation_type,
        username=username,
        actor_type=actor_type,
        start=start,
        end=end,
        retention_label=audit_retention_label(),
        retention_parts=audit_retention_parts(),
        cutoff=audit_cutoff_datetime(),
        total_records=total_records,
        filtered_count=filtered_count,
        page=page,
        page_size=page_size,
        max_page=max_page,
        selected_from=selected_from,
        selected_to=selected_to,
    )

@bp.route('/admin/other-configurations', methods=['GET','POST'])
@login_required
def admin_other_configurations():
    if not can_admin():
        return redirect(url_for('main.index'))
    keys = ['privacy_authority_non_notification_reason', 'documentation_location', 'application_external_url', 'application_timezone', 'interface_language']
    retention_keys = ['audit_retention_months_part', 'audit_retention_days_part', 'audit_retention_hours_part', 'audit_retention_minutes_part']
    if request.method == 'POST':
        for key in keys:
            set_setting_value(key, request.form.get(key, ''))
        for key in retention_keys:
            set_setting_value(key, str(_bounded_int(request.form.get(key, '0'), 0, 0, 120 if key == 'audit_retention_months_part' else 3650 if key == 'audit_retention_days_part' else 23 if key == 'audit_retention_hours_part' else 59)))
        # Mantiene aggiornata anche la chiave storica per compatibilità con archivi precedenti.
        set_setting_value('audit_retention_months', str(_bounded_int(request.form.get('audit_retention_months_part', '6'), 6, 0, 120)))
        set_setting_value('audit_records_per_page', str(_bounded_int(request.form.get('audit_records_per_page', '20'), 20, 1, 100)))
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
        audit_retention_parts=audit_retention_parts(),
        audit_retention_label=audit_retention_label(),
        audit_records_per_page=_bounded_int(setting_value('audit_records_per_page', '20') or '20', 20, 1, 100),
    )

def incident_consequences(inc):
    explicit=[a.consequence_text.strip() for a in sorted(inc.actions, key=lambda x: x.when_at or datetime.min) if getattr(a, 'consequence_text', None) and a.consequence_text.strip()]
    if explicit:
        return explicit
    cats=[(c.value or '').lower() for c in inc.categories]
    data=[(d.value or '').lower() for d in inc.data_types]
    out=[]
    if any('credential' in c or 'credenzial' in c for c in cats) or any('password' in d for d in data):
        out.append('Possibile compromissione di credenziali, accessi non autorizzati e necessità di rotazione password.')
    if any('phishing' in c for c in cats):
        out.append('Possibile esposizione a messaggi fraudolenti, furto di informazioni o propagazione dell’attacco.')
    if any('spam' in c for c in cats):
        out.append('Possibile ricezione o invio di comunicazioni indesiderate e impatto sulla reputazione dei servizi.')
    if inc.personal_data or any('dati personali' in d for d in data):
        out.append('Possibile coinvolgimento di dati personali con impatti sui diritti e le libertà degli interessati.')
    return out or ['Conseguenze da valutare sulla base dell’analisi dell’incidente.']

def incident_measures(inc):
    lines=[]
    for a in sorted([x for x in inc.actions if getattr(x, 'exportable', True)], key=lambda x: x.when_at or datetime.min):
        when=a.when_at.strftime('%Y-%m-%d %H:%M') if a.when_at else ''
        label=(a.label.description or a.label.value) if a.label else 'azione'
        desc=a.description or ''
        action_text = f'{label}: {desc}'.strip() if desc else label
        lines.append(f'{action_text} - {when}'.strip(' -'))
    return lines or ['Nessuna misura registrata.']

