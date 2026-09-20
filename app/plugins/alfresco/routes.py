from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from ...models import db
from ...routes import audit_log, set_setting_value, current_tenant, can_admin
from .client import config as alfresco_config, is_enabled, reset_defaults, test_destination

bp = Blueprint('alfresco', __name__, url_prefix='/alfresco', template_folder='templates')


def admin_required():
    return bool(getattr(current_user, 'is_authenticated', False) and can_admin())


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
        for key in ('base_url', 'username', 'site', 'parent_node_id', 'target_path', 'timeout'):
            set_setting_value(f'alfresco_{key}', request.form.get(f'alfresco_{key}', '').strip())
        password = (request.form.get('alfresco_password') or '').strip()
        if password:
            set_setting_value('alfresco_password', password)
        if request.form.get('clear_alfresco_password') == '1':
            set_setting_value('alfresco_password', '')
        set_setting_value('alfresco_group_by_type', '1' if request.form.get('alfresco_group_by_type') == '1' else '0')
        set_setting_value('alfresco_verify_tls', '1' if request.form.get('alfresco_verify_tls') == '1' else '0')
        audit_log('alfresco:plugin_config_update', {
            'enabled': request.form.get('plugin_alfresco_enabled') == '1',
            'base_url_set': bool(request.form.get('alfresco_base_url')),
            'site': request.form.get('alfresco_site') or '',
            'parent_node_id_set': bool(request.form.get('alfresco_parent_node_id')),
            'target_path': request.form.get('alfresco_target_path') or '',
            'group_by_type': request.form.get('alfresco_group_by_type') == '1',
        }, actor_type='user')
        db.session.commit()
        if action == 'test_alfresco_destination':
            try:
                info = test_destination()
                label = info.get('name') or info.get('node_id') or 'destinazione configurata'
                flash(f'Connessione Alfresco riuscita. Destinazione: {label}.', 'success')
            except Exception:
                current_app.logger.exception('Test destinazione Alfresco fallito')
                flash('Test Alfresco fallito. Verificare endpoint, credenziali, Site/Parent Node ID e log server.', 'danger')
            return redirect(url_for('alfresco.admin_plugins'))
        flash('Configurazione plugin Alfresco aggiornata.', 'success')
        return redirect(url_for('alfresco.admin_plugins'))
    cfg = alfresco_config()
    cfg['has_password'] = bool(cfg.get('password'))
    cfg['password'] = ''
    return render_template('alfresco_admin_plugins.html', config=cfg, tenant=current_tenant())
