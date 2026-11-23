"""Persistent, installation-wide selection of the approved application UI.

The setting is intentionally read by physical key. Tenant overrides, browser
preferences and the current tenant must never change an installation-wide mode.
An absent setting selects the modern interface on both fresh and upgraded DBs.
"""
import json

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from .models import AuditLog, Setting, db


GLOBAL_UI_MODE_KEY = 'global_ui_mode'
DEFAULT_UI_MODE = 'modern'
UI_MODES = frozenset({'modern', 'classic'})
bp = Blueprint('ui', __name__)


def global_ui_mode():
    """Read through the shared database, with no process or browser cache."""
    value = db.session.execute(
        select(Setting.value).where(Setting.key == GLOBAL_UI_MODE_KEY)
    ).scalar_one_or_none()
    return value if value in UI_MODES else DEFAULT_UI_MODE


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
        previous = global_ui_mode()
        row = db.session.get(Setting, GLOBAL_UI_MODE_KEY)
        if row is None:
            db.session.add(Setting(key=GLOBAL_UI_MODE_KEY, value=desired))
        else:
            row.value = desired
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
    return render_template('ui/interface_settings.html', selected_ui_mode=global_ui_mode())
