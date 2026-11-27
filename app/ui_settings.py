"""Persistent, installation-wide selection of the approved application UI.

The setting is intentionally read by physical key. Tenant overrides, browser
preferences and the current tenant must never change an installation-wide mode.
An absent setting selects the modern interface on both fresh and upgraded DBs.
"""
import json
import hashlib

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from .models import AuditLog, Setting, db


GLOBAL_UI_MODE_KEY = 'global_ui_mode'
DEFAULT_UI_MODE = 'modern'
GLOBAL_GRAVATAR_KEY = 'global_gravatar_enabled'
DEFAULT_GRAVATAR_ENABLED = True
UI_MODES = frozenset({'modern', 'classic'})
bp = Blueprint('ui', __name__)


def global_ui_mode():
    """Read through the shared database, with no process or browser cache."""
    value = db.session.execute(
        select(Setting.value).where(Setting.key == GLOBAL_UI_MODE_KEY)
    ).scalar_one_or_none()
    return value if value in UI_MODES else DEFAULT_UI_MODE


def global_gravatar_enabled():
    """Installation-wide avatar option; absent row defaults to enabled.

    A tenant-local setting must never override this physical global key.
    """
    value = db.session.execute(
        select(Setting.value).where(Setting.key == GLOBAL_GRAVATAR_KEY)
    ).scalar_one_or_none()
    return value not in ('0', 'false', 'off', 'no')


def gravatar_url_for_user(user):
    """Return only an HTTPS avatar URL, never the raw user email.

    The browser shows initials if the address has no Gravatar (`d=404`) or
    its request is blocked; no request is made when the option is disabled.
    """
    if not global_gravatar_enabled() or not getattr(user, 'is_authenticated', False):
        return None
    email = (getattr(user, 'email', None) or '').strip().lower()
    if not email or '@' not in email or len(email) > 254:
        return None
    # Gravatar's documented email normalization uses lowercase/trim + MD5.
    digest = hashlib.md5(email.encode('utf-8')).hexdigest()  # noqa: S324 - Gravatar address lookup, not password hashing
    return f'https://secure.gravatar.com/avatar/{digest}?s=80&d=404&r=g'


@bp.before_request
def enforce_existing_session_policy():
    # This separate blueprint retains the same inactivity, MFA and disabled-user
    # checks that already protect the core application routes.
    from .routes import block_disabled
    return block_disabled()


@bp.app_context_processor
def ui_context():
    from .ui_documentation import documentation_screenshot
    mode = global_ui_mode()
    database_context = False
    if current_user.is_authenticated:
        from .plugins.ai_chatbot.database_context import database_context_enabled
        database_context = database_context_enabled()
    return {
        'cir_ui_mode': mode,
        'cir_gravatar_enabled': global_gravatar_enabled(),
        'cir_gravatar_url': gravatar_url_for_user(current_user),
        'cir_new_ui_enabled': mode == 'modern',
        'cir_ai_database_context_enabled': database_context,
        'cir_documentation_screenshot': documentation_screenshot,
    }


@bp.route('/admin/interface', methods=['GET', 'POST'])
@login_required
def interface_settings():
    from .routes import current_tenant_id, is_superuser
    if not is_superuser():
        abort(403)
    if request.method == 'POST':
        # CSRF is enforced by the application-wide security hook. Reject unknown
        # and repeated values instead of silently selecting a different mode.
        values = request.form.getlist('mode')
        if len(values) != 1 or values[0] not in UI_MODES:
            abort(400, 'Interfaccia non valida / Invalid interface mode.')
        desired = values[0]
        # Older clients may submit only `mode`. Preserve the existing avatar
        # preference in that case; the page always submits both fields.
        gravatar_values = request.form.getlist('gravatar_enabled')
        if len(gravatar_values) > 1 or (gravatar_values and gravatar_values[0] not in ('0', '1')):
            abort(400, 'Invalid Gravatar preference.')
        desired_gravatar = (gravatar_values[0] == '1') if gravatar_values else global_gravatar_enabled()
        previous_gravatar = global_gravatar_enabled()
        previous = global_ui_mode()
        row = db.session.get(Setting, GLOBAL_UI_MODE_KEY)
        if row is None:
            db.session.add(Setting(key=GLOBAL_UI_MODE_KEY, value=desired))
        else:
            row.value = desired
        if previous_gravatar != desired_gravatar:
            avatar_setting = db.session.get(Setting, GLOBAL_GRAVATAR_KEY)
            if avatar_setting is None:
                db.session.add(Setting(key=GLOBAL_GRAVATAR_KEY, value='1' if desired_gravatar else '0'))
            else:
                avatar_setting.value = '1' if desired_gravatar else '0'
            db.session.add(AuditLog(
                tenant_id=current_tenant_id(), user_id=current_user.id,
                username=current_user.username, actor_type='user',
                operation_type='admin:global_gravatar_update',
                details=json.dumps({'scope': 'all-tenants-and-users',
                                    'previous': previous_gravatar, 'enabled': desired_gravatar}, sort_keys=True),
            ))
        if previous != desired:
            db.session.add(AuditLog(
                tenant_id=current_tenant_id(), user_id=current_user.id,
                username=current_user.username, actor_type='user',
                operation_type='admin:global_ui_mode_update',
                details=json.dumps({'scope': 'all-tenants-and-users',
                                    'previous': previous, 'mode': desired}, sort_keys=True),
            ))
        # Choice and audit event are committed together. A restart never resets
        # an explicit choice, including a later upgrade with a new default.
        db.session.commit()
        message = ('Global interface updated for all tenants and users.'
                   if getattr(g, 'lang', 'it') == 'en'
                   else 'Interfaccia globale aggiornata per tutti i tenant e gli utenti.')
        flash(message, 'success')
        return redirect(url_for('ui.interface_settings'), code=303)
    return render_template('ui/interface_settings.html', selected_ui_mode=global_ui_mode(),
                           selected_gravatar_enabled=global_gravatar_enabled())
