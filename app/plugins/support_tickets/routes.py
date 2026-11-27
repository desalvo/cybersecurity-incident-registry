"""Support Tickets: tenant-aware collaborative helpdesk, disabled by default.

All access checks use the ticket's target tenant, never a user-controlled query
parameter.  Server-side actions are required even if a button is hidden by the UI.
"""
import hashlib
import html
import mimetypes
import os
import re
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

from flask import (Blueprint, abort, current_app, flash, redirect, g,
                   render_template, request, send_from_directory, url_for)
from flask_login import current_user, login_required
from sqlalchemy import and_, or_
from werkzeug.utils import secure_filename
from markupsafe import Markup, escape

from ...models import db, Setting, Tenant, User, UserTenantRole, AuditLog
from ...routes import (audit_log, current_tenant_id, is_superuser,
                       user_accessible_tenant_ids, user_role_for_tenant,
                       tenant_setting_value_for_id)
from ...outbound_security import validate_outbound_host
from ...text_filters import workflow_markdown
from ...timeutils import utcnow
from .models import (SupportTicket, SupportTicketCategory,
                     SupportTicketMessage, SupportTicketAttachment)

bp = Blueprint('support_tickets', __name__, url_prefix='/support', template_folder='templates')

PRIORITIES = {'urgent': 'Urgente', 'high': 'Alta', 'medium': 'Media', 'low': 'Bassa'}
STATUSES = {
    'submitted': 'Sottomesso', 'open': 'Aperto', 'assigned': 'Assegnato',
    'in_progress': 'In lavorazione', 'completed': 'Completato',
    'rejected': 'Rifiutato', 'closed': 'Chiuso',
}
LEVELS = {'tenant_admin': 'Admin del tenant', 'super_admin': 'Super admin'}
SUPPORT_EN = {'Richieste, risposte e collaborazione tra utenti, amministratori di tenant e super admin.': 'Requests, answers and collaboration between users, tenant admins and super admins.', 'Nuovo ticket': 'New ticket', 'Totale visibili': 'Visible tickets', 'Da prendere in carico': 'Awaiting assignment', 'In lavorazione': 'In progress', 'Completati e chiusi': 'Completed and closed', 'Ticket': 'Tickets', 'Filtra per uno o più parametri per restringere i risultati.': 'Combine one or more filters to narrow the results.', 'Ricerca libera / codice': 'Search / reference', 'Stato': 'Status', 'Priorità': 'Priority', 'Categoria': 'Category', 'Tenant': 'Tenant', 'Assegnatario': 'Assigned team', 'Richiedente': 'Requester', 'Aggiornato': 'Updated', 'Ricerca': 'Search', 'Tutti': 'All', 'Tutte': 'All', 'ID richiedente': 'Requester ID', 'Creazione dal': 'Created from', 'Creazione al': 'Created to', 'Cerca': 'Search', 'Reimposta': 'Reset', 'Oggetto': 'Subject', 'Nessun ticket corrisponde ai filtri.': 'No tickets match your filters.', 'Crea una richiesta': 'Create a request', 'Precedente': 'Previous', 'Successiva': 'Next', 'Pagina': 'Page', 'messaggi': 'messages', '← Supporto / Tutti i ticket': '← Support / All tickets', 'Come possiamo aiutarti?': 'How can we help?', 'Descrivi la tua domanda e scegli il team di supporto. Il ticket sarà inizialmente': 'Describe your question and choose a support team. Your ticket starts as', 'Sottomesso': 'Submitted', 'Tenant destinatario': 'Target tenant', 'Chi contattare': 'Contact', 'Amministratori del tenant': 'Tenant administrators', 'Super admin · supporto di livello superiore': 'Super admins · second-level support', 'Descrizione della richiesta': 'Request description', 'Markdown': 'Markdown', 'Supportati titoli, liste, checklist, link, tabelle, codice e formattazione Markdown sicura.': 'Supports headings, lists, checklists, links, tables, code and safe Markdown formatting.', 'Allegati': 'Attachments', 'facoltativi': 'optional', 'Annulla': 'Cancel', 'Sottometti ticket': 'Submit ticket', '← Tutti i ticket': '← All tickets', 'Conversazione': 'Conversation', 'Scrivi una risposta': 'Write a reply', 'Messaggio · Markdown esteso': 'Message · extended Markdown', 'Invia risposta': 'Send reply', 'Ticket chiuso. È possibile riaprirlo tramite il pannello di gestione.': 'Ticket closed. Reopen it from the management panel to reply.', 'Dettagli richiesta': 'Request details', 'Destinatario': 'Recipient', 'Creato': 'Created', 'Ultima attività': 'Last activity', 'Motivo dello stato': 'Status reason', 'Gestione ticket': 'Ticket management', 'Nuovo stato': 'New status', 'Motivo (facoltativo)': 'Reason (optional)', 'Aggiorna stato': 'Update status', 'Coinvolgi i super admin': 'Involve super admins', 'Eliminazione definitiva': 'Permanent deletion', 'Solo i super admin possono eliminare integralmente il ticket e gli allegati.': 'Only super admins can permanently delete tickets and attachments.', 'Elimina definitivamente': 'Permanently delete', 'Disponibilità del servizio': 'Service availability', 'Attiva Support Tickets per gli utenti autenticati': 'Enable Support Tickets for signed-in users', 'Salva configurazione': 'Save settings', 'Quando il plugin è disattivato, nessuna dashboard, conversazione o allegato è accessibile. I dati già conservati non vengono cancellati.': 'When disabled, dashboards, conversations and attachments are unavailable; existing data is preserved.', 'Categorie del service desk': 'Service desk categories', 'Disattiva': 'Disable', 'Riattiva': 'Enable', 'Aggiungi una categoria': 'Add a category', 'Codice (slug)': 'Identifier (slug)', 'Nome italiano': 'Italian label', 'Nome inglese': 'English label', 'Crea categoria': 'Create category', 'Aperto': 'Open', 'Assegnato': 'Assigned', 'Completato': 'Completed', 'Rifiutato': 'Rejected', 'Chiuso': 'Closed', 'Urgente': 'Urgent', 'Alta': 'High', 'Media': 'Medium', 'Bassa': 'Low', 'Admin del tenant': 'Tenant admin'}

def support_t(text):
    return SUPPORT_EN.get(str(text), str(text)) if getattr(g, 'lang', 'it') == 'en' else str(text)

INITIAL_CATEGORIES = (
    ('autorizzazione', 'Autorizzazione', 'Authorization'),
    ('incidenti', 'Incidenti', 'Incidents'),
    ('workflow', 'Workflow', 'Workflow'),
    ('documentazione', 'Documentazione', 'Documentation'),
    ('altro', 'Altro', 'Other'),
)
# No executable files, active HTML/SVG, archives or macro-enabled documents.
ALLOWED_EXTENSIONS = {'.txt', '.log', '.csv', '.pdf', '.png', '.jpg', '.jpeg',
                      '.webp', '.docx', '.xlsx', '.pptx', '.json'}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 5


def is_enabled():
    try:
        row = db.session.get(Setting, 'plugin_support_tickets_enabled')
        return bool(row and row.value == '1')
    except Exception:
        return False


def seed_default_categories():
    """Idempotent bootstrap; never override super-admin changes."""
    changed = False
    for slug, it, en in INITIAL_CATEGORIES:
        if SupportTicketCategory.query.filter_by(slug=slug).first() is None:
            db.session.add(SupportTicketCategory(slug=slug, label_it=it, label_en=en))
            changed = True
    if changed:
        db.session.commit()


@bp.before_request
def check_plugin_and_session():
    if not current_user.is_authenticated:
        return redirect(url_for('main.login', next=request.path))
    if request.endpoint == 'support_tickets.admin_config':
        if not is_superuser():
            abort(403)
        return None
    if not is_enabled():
        abort(404)
    if not (is_superuser() or user_accessible_tenant_ids()):
        abort(403)
    return None


def _super(user=None):
    return bool(is_superuser(user or current_user))


def _role(user, tenant_id):
    return user_role_for_tenant(user, tenant_id)


def _manage(ticket, user=None):
    user = user or current_user
    return _super(user) or (
        _role(user, ticket.tenant_id) == 'admin' and
        (ticket.assignee_level == 'tenant_admin' or ticket.escalated)
    )


def _view(ticket, user=None):
    user = user or current_user
    if _super(user):
        return True
    if user.id == ticket.created_by_id and _role(user, ticket.tenant_id) != 'disabled':
        return True
    return _manage(ticket, user)


def _must_view(ticket):
    if not _view(ticket):
        abort(404)  # Don't disclose cross-tenant ticket existence.


def _available_tenants():
    ids = user_accessible_tenant_ids()
    query = Tenant.query.filter_by(is_system_defaults=False)
    if ids is not None:
        query = query.filter(Tenant.id.in_(ids or [-1]))
    return query.order_by(Tenant.name).all()


def _visible_query():
    q = SupportTicket.query
    if _super():
        return q
    ids = user_accessible_tenant_ids() or []
    managed = [tid for tid in ids if _role(current_user, tid) == 'admin']
    criteria = [and_(SupportTicket.created_by_id == current_user.id,
                     SupportTicket.tenant_id.in_(ids or [-1]))]
    if managed:
        criteria.append(and_(SupportTicket.tenant_id.in_(managed),
                             or_(SupportTicket.assignee_level == 'tenant_admin',
                                 SupportTicket.escalated.is_(True))))
    return q.filter(or_(*criteria))


def _ticket(ticket_id):
    return db.session.get(SupportTicket, ticket_id) or abort(404)


def _valid_target(raw):
    try:
        target = db.session.get(Tenant, int(raw))
    except (ValueError, TypeError):
        target = None
    if not target or target.is_system_defaults:
        abort(400, description='Tenant destinatario non valido.')
    if not _super() and _role(current_user, target.id) == 'disabled':
        abort(403)
    return target


def _author_label():
    return (current_user.name or current_user.username or str(current_user.id))[:160]


def _upload_dir():
    directory = Path(current_app.config['SUPPORT_TICKETS_DIR'])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        current_app.logger.warning('Support tickets: cannot restrict storage directory permissions')
    return directory


def _save_attachments(msg, files):
    """Stream bounded private files; caller cleans up paths if commit fails."""
    attached = [item for item in files if item and item.filename]
    if len(attached) > MAX_FILES:
        raise ValueError(f'Massimo {MAX_FILES} allegati per messaggio.')
    saved = []
    for upload in attached:
        original = secure_filename(upload.filename or '')[:255]
        extension = Path(original).suffix.lower()
        if not original or extension not in ALLOWED_EXTENSIONS:
            raise ValueError('Formato allegato non permesso: usare PDF, immagini o documenti non eseguibili.')
        stored = f'{uuid.uuid4().hex}{extension}'
        target = _upload_dir() / stored
        digest = hashlib.sha256()
        count = 0
        # Open with exclusive creation; never trust browser-supplied paths.
        try:
            with open(target, 'xb') as output:
                os.chmod(target, 0o600)
                saved.append(target)
                while True:
                    data = upload.stream.read(1024 * 1024)
                    if not data:
                        break
                    count += len(data)
                    if count > MAX_FILE_BYTES:
                        raise ValueError('Allegato superiore al limite di 10 MB.')
                    output.write(data)
                    digest.update(data)
            if not count:
                raise ValueError('Gli allegati vuoti non sono ammessi.')
            mimetype = mimetypes.guess_type(original)[0] or 'application/octet-stream'
            db.session.add(SupportTicketAttachment(message=msg,
                uploaded_by_id=current_user.id, original_filename=original,
                stored_filename=stored, content_type=mimetype,
                byte_count=count, sha256=digest.hexdigest()))
        except Exception:
            for filename in saved:
                filename.unlink(missing_ok=True)
            raise
    return saved


def _record(action, ticket, extra=None):
    audit_log('support:' + action, {'ticket_id': ticket.id,
        'target_tenant_id': ticket.tenant_id, 'level': ticket.assignee_level,
        **(extra or {})}, actor_type='user')
    # An explicit tenant-scoped audit record keeps the target visible even when
    # the requester is operating in another accessible tenant.
    db.session.add(AuditLog(tenant_id=ticket.tenant_id,
        operation_type=('support:target:' + action)[:120],
        username=current_user.username or '', user_id=current_user.id,
        actor_type='user', details=f'ticket_id={ticket.id}'))


def _possible_recipients(ticket):
    users = User.query.all()
    if ticket.assignee_level == 'super_admin':
        return [u for u in users if _super(u)]
    return [u for u in users if _role(u, ticket.tenant_id) == 'admin' and not _super(u)]


def _notify(ticket, event):
    """Best-effort HTML email. No ticket body or attachment is emailed."""
    try:
        recipients = list(_possible_recipients(ticket))
        if event != 'created':
            owner = db.session.get(User, ticket.created_by_id) if ticket.created_by_id else None
            if owner and owner not in recipients:
                recipients.append(owner)
        if ticket.escalated:
            for u in User.query.all():
                if _super(u) and u not in recipients:
                    recipients.append(u)
        addresses = set()
        for user in recipients:
            email_addr = (user.email or '').strip()
            if (event == 'created' or user.id != current_user.id) and email_addr and '\n' not in email_addr and '\r' not in email_addr:
                addresses.add(email_addr)
        if not addresses:
            return
        tid = ticket.tenant_id
        def setting(key, default=''):
            return tenant_setting_value_for_id(key, tid, default)
        host = setting('smtp_host', '').strip()
        if not host:
            current_app.logger.warning('Support ticket %s: SMTP not configured for tenant %s', ticket.id, tid)
            return
        host = validate_outbound_host(host, purpose='SMTP')
        port = int(setting('smtp_port', '587') or '587')
        ssl = setting('smtp_use_ssl', '0') == '1'
        tls = setting('smtp_use_tls', '1') == '1' and not ssl
        auth = setting('smtp_auth_enabled', '0') == '1'
        username = setting('smtp_username', '')
        sender = setting('smtp_default_sender', '') or username or 'admin@localhost.localdomain'
        if auth and (not username or not setting('smtp_default_sender', '')):
            current_app.logger.warning('Support tickets: incomplete authenticated SMTP sender')
            return
        base = setting('application_external_url', 'http://localhost:8000').rstrip('/')
        parsed = urlsplit(base)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
            current_app.logger.warning('Support tickets: invalid configured external URL')
            return
        link = base + url_for('support_tickets.view_ticket', ticket_id=ticket.id)
        subject = f'[{ticket.reference}] {ticket.subject}'
        if event == 'created':
            subtitle = 'Nuova richiesta di supporto'
        elif event == 'escalated':
            subtitle = 'Escalation al supporto di livello superiore'
        elif event == 'status':
            subtitle = 'Stato del ticket aggiornato'
        else:
            subtitle = 'Nuova risposta sul ticket'
        from .mail import ticket_email_html
        body = ticket_email_html(ticket, subtitle, link, STATUSES[ticket.status], PRIORITIES[ticket.priority])
        smtp_cls = smtplib.SMTP_SSL if ssl else smtplib.SMTP
        with smtp_cls(host, port, timeout=20) as smtp:
            if tls:
                smtp.starttls()
            if auth:
                smtp.login(username, setting('smtp_password', ''))
            for address in sorted(addresses):
                msg = EmailMessage()
                msg['From'] = sender
                msg['To'] = address
                msg['Subject'] = subject
                msg.set_content(f'{subtitle}\n{ticket.reference}: {ticket.subject}\n{link}')
                msg.add_alternative(body, subtype='html')
                smtp.send_message(msg)
    except Exception:
        current_app.logger.exception('Support Tickets: notification delivery failed for ticket %s', ticket.id)


def _render_markdown(value):
    """Extended safe Markdown: CIR inline formatting plus fenced code/tables."""
    lines = (value or '').splitlines()
    pieces = []
    normal = []
    def flush():
        if normal:
            pieces.append(str(workflow_markdown('\n'.join(normal))))
            normal.clear()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith('```'):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].lstrip().startswith('```'):
                code.append(lines[i]); i += 1
            pieces.append('<pre><code>' + str(escape('\n'.join(code))) + '</code></pre>')
        elif (i+1 < len(lines) and '|' in line and
              re.fullmatch(r'\s*\|?[\s:\-|]+\|?\s*', lines[i+1]) and '-' in lines[i+1]):
            flush()
            header = [c.strip() for c in line.strip('|').split('|')]
            i += 2
            rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip('|').split('|')]); i += 1
            def cells(values, tag):
                return '<tr>' + ''.join(f'<{tag}>' + str(workflow_markdown(v)) + f'</{tag}>' for v in values) + '</tr>'
            pieces.append('<table><thead>' + cells(header, 'th') + '</thead><tbody>' +
                          ''.join(cells(row, 'td') for row in rows) + '</tbody></table>')
            continue
        else:
            if re.match(r'^\s*[-*]\s+\[[xX ]\]\s+', line):
                line = re.sub(r'\[([xX ])\]', lambda m: '☑' if m.group(1).lower() == 'x' else '☐', line, count=1)
            normal.append(line)
        i += 1
    flush()
    return Markup('\n'.join(pieces))


@bp.app_context_processor
def inject_helpers():
    if getattr(g, 'lang', 'it') == 'en':
        priority = {key: support_t(value) for key, value in PRIORITIES.items()}
        statuses = {key: support_t(value) for key, value in STATUSES.items()}
        levels = {key: support_t(value) for key, value in LEVELS.items()}
    else:
        priority, statuses, levels = PRIORITIES, STATUSES, LEVELS
    return dict(support_priorities=priority, support_statuses=statuses,
                support_levels=levels, support_markdown=_render_markdown, support_t=support_t)


@bp.route('/')
@login_required
def dashboard():
    q = _visible_query()
    terms = (request.args.get('q') or '').strip()[:120]
    if terms:
        like = f'%{terms}%'
        conditions = [SupportTicket.subject.ilike(like), SupportTicket.creator_label.ilike(like),
                      SupportTicket.status_reason.ilike(like)]
        if terms.upper().startswith('SUP-') and terms[4:].isdigit():
            conditions.append(SupportTicket.id == int(terms[4:]))
        q = q.filter(or_(*conditions))
    for key, column, valid in (
        ('priority', SupportTicket.priority, set(PRIORITIES)),
        ('status', SupportTicket.status, set(STATUSES)),
        ('assignee', SupportTicket.assignee_level, set(LEVELS)),
    ):
        value = request.args.get(key, '')
        if value in valid:
            q = q.filter(column == value)
    for key, column in (('category_id', SupportTicket.category_id),
                        ('tenant_id', SupportTicket.tenant_id),
                        ('created_by_id', SupportTicket.created_by_id)):
        value = request.args.get(key, '')
        if value.isdecimal():
            q = q.filter(column == int(value))
    for key, column, is_upper in (
        ('created_from', SupportTicket.created_at, False),
        ('created_to', SupportTicket.created_at, True),
    ):
        value = request.args.get(key, '')
        if value:
            try:
                day = datetime.fromisoformat(value).date()
            except (ValueError, TypeError):
                abort(400, description='Filtro data non valido.')
            from datetime import time
            dt = datetime.combine(day, time.max if is_upper else time.min)
            q = q.filter(column <= dt if is_upper else column >= dt)
    try:
        page = min(max(int(request.args.get('page', '1')), 1), 100000)
    except ValueError:
        page = 1
    page_obj = q.order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc()).paginate(
        page=page, per_page=40, error_out=False)
    visible = _visible_query()
    counts = {status: visible.filter(SupportTicket.status == status).count() for status in STATUSES}
    categories = SupportTicketCategory.query.order_by(SupportTicketCategory.label_it).all()
    return render_template('support_dashboard.html', tickets=page_obj.items,
        pagination=page_obj, counts=counts, categories=categories,
        tenants=_available_tenants(), filter_values=request.args,
        total=visible.count(), is_manager=_super() or bool(user_accessible_tenant_ids(roles=['admin'])))


@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_ticket():
    tenants = _available_tenants()
    categories = SupportTicketCategory.query.filter_by(active=True).order_by(SupportTicketCategory.label_it).all()
    if request.method == 'POST':
        target = _valid_target(request.form.get('tenant_id', ''))
        category = db.session.get(SupportTicketCategory, request.form.get('category_id', type=int))
        level = request.form.get('assignee_level', 'tenant_admin')
        priority = request.form.get('priority', 'medium')
        subject = re.sub(r'[\r\n\t]+', ' ', request.form.get('subject') or '').strip()
        body = (request.form.get('body') or '').strip()
        if not category or not category.active or level not in LEVELS or priority not in PRIORITIES:
            abort(400)
        if not (3 <= len(subject) <= 255 and 4 <= len(body) <= 20000):
            flash('Inserire un oggetto (3-255 caratteri) e una richiesta (4-20000 caratteri).', 'danger')
            return redirect(url_for('support_tickets.new_ticket'))
        ticket = SupportTicket(tenant_id=target.id, category_id=category.id,
            created_by_id=current_user.id, creator_label=_author_label(),
            subject=subject, priority=priority, assignee_level=level,
            status='submitted', status_reason='')
        message = SupportTicketMessage(ticket=ticket, author_id=current_user.id,
            author_label=_author_label(), body=body)
        saved = []
        try:
            db.session.add(ticket)
            db.session.add(message)
            db.session.flush()
            saved = _save_attachments(message, request.files.getlist('attachments'))
            _record('created', ticket)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
            return redirect(url_for('support_tickets.new_ticket'))
        except Exception:
            db.session.rollback()
            for path in saved:
                path.unlink(missing_ok=True)
            raise
        _notify(ticket, 'created')
        flash(f'Ticket {ticket.reference} sottomesso.', 'success')
        return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket.id))
    return render_template('support_new.html', tenants=tenants,
        categories=categories, current_tid=current_tenant_id(), max_files=MAX_FILES)


@bp.route('/tickets/<int:ticket_id>')
@login_required
def view_ticket(ticket_id):
    ticket = _ticket(ticket_id)
    _must_view(ticket)
    is_owner = ticket.created_by_id == current_user.id
    return render_template('support_detail.html', ticket=ticket,
        can_manage=_manage(ticket), is_owner=is_owner,
        can_edit_fields=(_manage(ticket) or (is_owner and ticket.status == 'submitted')),
        categories=SupportTicketCategory.query.filter_by(active=True).order_by(SupportTicketCategory.label_it).all(),
        max_files=MAX_FILES)


@bp.route('/tickets/<int:ticket_id>/reply', methods=['POST'])
@login_required
def reply(ticket_id):
    ticket = _ticket(ticket_id)
    _must_view(ticket)
    if ticket.status == 'closed':
        abort(409, description='Il ticket è chiuso; riaprirlo prima di rispondere.')
    body = (request.form.get('body') or '').strip()
    if not 1 <= len(body) <= 20000:
        abort(400, description='La risposta deve contenere da 1 a 20000 caratteri.')
    message = SupportTicketMessage(ticket_id=ticket.id, author_id=current_user.id,
        author_label=_author_label(), body=body)
    saved = []
    try:
        db.session.add(message)
        db.session.flush()
        saved = _save_attachments(message, request.files.getlist('attachments'))
        ticket.updated_at = utcnow()
        _record('replied', ticket)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket.id))
    except Exception:
        db.session.rollback()
        for path in saved:
            path.unlink(missing_ok=True)
        raise
    _notify(ticket, 'reply')
    return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket.id))


@bp.route('/tickets/<int:ticket_id>/details', methods=['POST'])
@login_required
def update_details(ticket_id):
    ticket = _ticket(ticket_id)
    _must_view(ticket)
    manager = _manage(ticket)
    if not manager and not (ticket.created_by_id == current_user.id and ticket.status == 'submitted'):
        abort(403)
    if ticket.status == 'closed':
        abort(409)
    priority = request.form.get('priority', '')
    category = db.session.get(SupportTicketCategory, request.form.get('category_id', type=int))
    if priority not in PRIORITIES or not category or not category.active:
        abort(400)
    old = {'priority': ticket.priority, 'category_id': ticket.category_id}
    ticket.priority = priority
    ticket.category_id = category.id
    if _super() and request.form.get('assignee_level') in LEVELS:
        old['assignee_level'] = ticket.assignee_level
        ticket.assignee_level = request.form['assignee_level']
        ticket.escalated = (ticket.assignee_level == 'super_admin' and ticket.escalated)
    ticket.updated_at = utcnow()
    _record('details_updated', ticket, {'previous': old})
    db.session.commit()
    _notify(ticket, 'status')
    return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket.id))


@bp.route('/tickets/<int:ticket_id>/status', methods=['POST'])
@login_required
def set_status(ticket_id):
    ticket = _ticket(ticket_id)
    _must_view(ticket)
    desired = request.form.get('status', '')
    if desired not in STATUSES:
        abort(400)
    if not _manage(ticket):
        # Requesters may close or re-open *their own* tickets only.
        if ticket.created_by_id != current_user.id or desired not in {'closed', 'submitted'}:
            abort(403)
        if desired == 'submitted' and ticket.status not in {'closed', 'completed', 'rejected'}:
            abort(409)
    reason = (request.form.get('reason') or '').strip()
    if len(reason) > 1000:
        abort(400)
    if desired in {'closed', 'rejected'} and ticket.status != desired:
        # Require a deliberate choice; a reason is optional by specification.
        pass
    old_status = ticket.status
    ticket.status = desired
    ticket.status_reason = reason
    ticket.closed_at = utcnow() if desired == 'closed' else None
    ticket.updated_at = utcnow()
    _record('status_changed', ticket, {'from': old_status, 'to': desired})
    db.session.commit()
    _notify(ticket, 'status')
    return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket.id))


@bp.route('/tickets/<int:ticket_id>/escalate', methods=['POST'])
@login_required
def escalate(ticket_id):
    ticket = _ticket(ticket_id)
    if not _manage(ticket):
        abort(403)
    if ticket.status == 'closed':
        abort(409)
    ticket.escalated = True
    ticket.assignee_level = 'super_admin'
    ticket.updated_at = utcnow()
    _record('escalated', ticket)
    db.session.commit()
    _notify(ticket, 'escalated')
    return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket.id))


@bp.route('/attachments/<int:attachment_id>')
@login_required
def download_attachment(attachment_id):
    attachment = db.session.get(SupportTicketAttachment, attachment_id) or abort(404)
    _must_view(attachment.message.ticket)
    if not re.fullmatch(r'[0-9a-f]{32}\.[a-z0-9]+', attachment.stored_filename):
        abort(404)
    # Detect unexpected modification of an attachment before delivery.
    location = _upload_dir() / attachment.stored_filename
    try:
        with open(location, 'rb') as stream:
            digest = hashlib.sha256()
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        if digest.hexdigest() != attachment.sha256:
            current_app.logger.error('Support ticket attachment SHA-256 mismatch: %s', attachment.id)
            abort(409, description='Verifica di integrità allegato non superata.')
    except FileNotFoundError:
        abort(404)
    response = send_from_directory(_upload_dir(), attachment.stored_filename,
        as_attachment=True, download_name=attachment.original_filename,
        mimetype=attachment.content_type)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return response


@bp.route('/tickets/<int:ticket_id>/delete', methods=['POST'])
@login_required
def delete_ticket(ticket_id):
    if not _super():
        abort(403)
    ticket = _ticket(ticket_id)
    if request.form.get('confirm_reference', '').strip().upper() != ticket.reference:
        abort(400, description='Inserire il codice del ticket per confermare la cancellazione definitiva.')
    filenames = [att.stored_filename for msg in ticket.messages for att in msg.attachments]
    _record('deleted', ticket)
    db.session.delete(ticket)
    db.session.commit()
    for name in filenames:
        if re.fullmatch(r'[0-9a-f]{32}\.[a-z0-9]+', name):
            try:
                (_upload_dir() / name).unlink(missing_ok=True)
            except OSError:
                current_app.logger.exception('Support tickets: unable to clean attachment')
    flash('Ticket eliminato definitivamente.', 'success')
    return redirect(url_for('support_tickets.dashboard'))


@bp.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_config():
    if not _super():
        abort(403)
    if request.method == 'POST':
        action = request.form.get('action', 'toggle')
        if action == 'toggle':
            enabled = request.form.get('enabled') == '1'
            setting = db.session.get(Setting, 'plugin_support_tickets_enabled')
            if not setting:
                setting = Setting(key='plugin_support_tickets_enabled', value='0')
                db.session.add(setting)
            setting.value = '1' if enabled else '0'
            audit_log('support:plugin_config', {'enabled': enabled}, actor_type='user')
        elif action == 'add_category':
            label_it = (request.form.get('label_it') or '').strip()[:120]
            label_en = (request.form.get('label_en') or '').strip()[:120] or label_it
            slug = (request.form.get('slug') or '').strip().lower()
            if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,79}', slug) or not label_it:
                abort(400)
            if SupportTicketCategory.query.filter_by(slug=slug).first():
                abort(409, description='Categoria già presente.')
            db.session.add(SupportTicketCategory(slug=slug, label_it=label_it, label_en=label_en))
            audit_log('support:category_created', {'slug': slug}, actor_type='user')
        elif action == 'category_state':
            category = db.session.get(SupportTicketCategory, request.form.get('category_id', type=int)) or abort(404)
            category.active = request.form.get('active') == '1'
            audit_log('support:category_state', {'category': category.slug, 'active': category.active}, actor_type='user')
        else:
            abort(400)
        db.session.commit()
        flash('Configurazione Support Tickets salvata.', 'success')
        return redirect(url_for('support_tickets.admin_config'))
    return render_template('support_admin.html', enabled=is_enabled(),
        categories=SupportTicketCategory.query.order_by(SupportTicketCategory.label_it).all())
