from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...models import db
from ...routes import audit_log, setting_value, set_setting_value
from .client import config as alfresco_config, is_enabled, reset_defaults

bp = Blueprint('alfresco', __name__, url_prefix='/alfresco', template_folder='templates')


def admin_required():
    return getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'role', None) == 'admin'


@bp.route('/admin/plugins', methods=['GET', 'POST'])
@login_required
def admin_plugins():
    if not admin_required():
        flash('Accesso riservato agli amministratori.', 'danger')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        if action == 'reset_alfresco_defaults':
            reset_defaults(set_setting_value)
            audit_log('alfresco:plugin_config_reset', {'enabled': False}, actor_type='user')
            db.session.commit()
            flash('Configurazione Alfresco ripristinata ai valori di default.', 'success')
            return redirect(url_for('alfresco.admin_plugins'))
        set_setting_value('plugin_alfresco_enabled', '1' if request.form.get('plugin_alfresco_enabled') == '1' else '0')
        for key in ('base_url', 'username', 'site', 'target_path', 'timeout'):
            set_setting_value(f'alfresco_{key}', request.form.get(f'alfresco_{key}', '').strip())
        password = (request.form.get('alfresco_password') or '').strip()
        if password:
            set_setting_value('alfresco_password', password)
        if request.form.get('clear_alfresco_password') == '1':
            set_setting_value('alfresco_password', '')
        set_setting_value('alfresco_verify_tls', '1' if request.form.get('alfresco_verify_tls') == '1' else '0')
        audit_log('alfresco:plugin_config_update', {
            'enabled': request.form.get('plugin_alfresco_enabled') == '1',
            'base_url_set': bool(request.form.get('alfresco_base_url')),
            'site': request.form.get('alfresco_site') or '',
            'target_path': request.form.get('alfresco_target_path') or '',
        }, actor_type='user')
        db.session.commit()
        flash('Configurazione plugin Alfresco aggiornata.', 'success')
        return redirect(url_for('alfresco.admin_plugins'))
    cfg = alfresco_config()
    cfg['has_password'] = bool(setting_value('alfresco_password', ''))
    return render_template('alfresco_admin_plugins.html', config=cfg)
