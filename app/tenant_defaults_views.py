"""Administration of shared defaults and portable workflow catalogues."""
import io
import json
from functools import wraps

from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import BadRequest

from .models import (db, Tenant, Setting, ConfigLabel, IncidentWorkflowStep, TenantDefaultAlert,
                     WorkflowCatalogEntry)
from .timeutils import utcnow


def _admin_view(fn):
    @wraps(fn)
    @login_required
    def guarded(*args, **kwargs):
        from .routes import can_admin
        if not can_admin():
            abort(403)
        return fn(*args, **kwargs)
    return guarded


def _superuser():
    from .routes import is_superuser
    if not is_superuser():
        abort(403)


def _json_upload():
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        raise ValueError('Selezionare un file JSON.')
    # Request limits also apply to multipart input. The bounded read protects
    # deployments that have configured a much larger general document limit.
    maximum = min(current_app.config.get('MAX_CONTENT_LENGTH') or 25 * 1024**2, 25 * 1024**2)
    raw = uploaded.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('File JSON troppo grande (massimo 25 MiB).')
    try:
        payload = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('File JSON non valido.') from exc
    if not isinstance(payload, dict):
        raise ValueError('Il file deve contenere un oggetto JSON.')
    return payload


def _download(payload, filename):
    # Match the validators' compact byte budget so a download near 25 MiB
    # remains reimportable through the same bounded upload endpoint.
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    response = send_file(io.BytesIO(raw), mimetype='application/json', as_attachment=True,
                         download_name=filename)
    response.headers['Cache-Control'] = 'no-store, private'
    return response


def _source_scope():
    from .routes import current_tenant_id
    tenant_id = current_tenant_id()
    # A posted source ID never grants read access to another tenant.
    raw = request.values.get('source_tenant_id')
    if raw is not None and raw != str(tenant_id):
        abort(403)
    return tenant_id


def _category_id():
    raw = request.values.get('category_id', '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise BadRequest('Categoria workflow non valida.') from exc


def register_tenant_defaults_routes(bp):
    from .tenant_defaults import export_configuration, import_configuration, sync_defaults_configuration
    from .workflow_catalog import (build_catalog_workflow_payload, save_catalog_workflow,
                                   import_catalog_workflow, export_catalog_entry)

    @bp.before_app_request
    def protect_configuration_only_tenant():
        from .routes import current_tenant, is_superuser
        if not current_user.is_authenticated:
            return None
        tenant = current_tenant()
        if tenant is None or not tenant.is_system_defaults:
            return None
        if not is_superuser():
            abort(403)
        endpoint = request.endpoint or ''
        if endpoint == 'main.index':
            return redirect(url_for('main.admin_tenant_defaults'))
        allowed = {
            'main.admin_tenants', 'main.admin_tenant_activate', 'main.admin_labels',
            'main.admin_label_update', 'main.admin_label_delete', 'main.admin_labels_restore_defaults',
            'main.admin_recommendations', 'main.admin_recommendation_delete',
            'main.notification_types', 'main.admin_incident_workflows',
            'main.admin_incident_workflow_delete', 'main.admin_incident_workflow_export_preview',
            'main.admin_incident_workflow_export_download', 'main.admin_incident_workflow_import_preview',
            'main.admin_incident_workflow_import_apply', 'main.export_full', 'main.import_full',
            'main.admin_incident_form_fields', 'main.admin_incident_custom_fields',
            'main.admin_incident_templates', 'main.admin_incident_button_actions',
            'main.admin_security_owner', 'main.admin_structure', 'main.admin_security_responsible',
            'main.admin_logo', 'main.sso_logo_asset', 'main.sso_settings_admin', 'main.ldap_settings',
            'main.admin_external_recipients', 'main.notification_settings',
            'main.notification_template_new', 'main.notification_template', 'main.modules_configuration',
            'main.admin_other_configurations', 'main.admin_backups', 'main.admin_audit',
            'alfresco.admin_plugins', 'ai_chatbot.admin_plugins',
            'main.logout', 'main.login', 'main.mfa_verify', 'main.logo_image',
            'main.help_page', 'main.admin_help_page', 'main.release_notes', 'main.app_info',
            'main.healthz', 'static',
            'ui.interface_settings',
        }
        if endpoint not in allowed and not endpoint.startswith(('main.admin_tenant_defaults', 'main.admin_workflow_catalog')):
            if request.method == 'GET':
                flash('Tenants Default contiene configurazioni e workflow. Selezionare un tenant operativo per questa funzione.', 'info')
                return redirect(url_for('main.admin_tenant_defaults'))
            abort(403, 'Tenants Default non contiene dati operativi.')
        if endpoint == 'main.admin_audit':
            # Shared audit limits are configuration. Purges, including future
            # actions added to the same legacy endpoint, require an operational
            # tenant and must never run through this configuration-only scope.
            if (request.method not in {'GET', 'POST'}
                    or request.method == 'POST' and request.form.get('action') != 'save_audit_config'):
                abort(403, 'In Tenants Default è consentita solo la configurazione dei parametri audit.')
        if request.method == 'POST':
            # A source holds definitions. Operational jobs run in destination
            # tenants, never against every tenant through the source context.
            action = request.form.get('action', '')
            if (endpoint == 'main.admin_backups' and action in {'run', 'restore'}
                    or endpoint == 'main.notification_settings' and action in {'run_deadline_check', 'run_incident_reminder_check'}
                    or endpoint == 'main.admin_incident_templates' and action == 'create_from_incident'
                    or endpoint == 'main.admin_other_configurations' and action == 'cleanup_orphan_generated_documents'):
                abort(403, 'Questa operazione richiede un tenant operativo.')

    @bp.app_context_processor
    def defaults_alert_badge():
        from .routes import can_admin, current_tenant_id
        if not current_user.is_authenticated or not can_admin():
            return {'tenant_defaults_alert_count': 0, 'workflow_notice_count': 0}
        count = TenantDefaultAlert.query.filter_by(tenant_id=current_tenant_id(), acknowledged_at=None).count()
        from .workflow_lifecycle import unread_workflow_notice_count
        return {'tenant_defaults_alert_count': count,
                'workflow_notice_count': unread_workflow_notice_count(current_user.id)}

    @bp.route('/admin/tenants-defaults')
    @_admin_view
    def admin_tenant_defaults():
        from .routes import current_tenant, is_superuser
        defaults = Tenant.query.filter_by(is_system_defaults=True).one()
        return render_template('admin_tenant_defaults.html', defaults_tenant=defaults,
                               tenant=current_tenant(), can_publish=is_superuser())

    @bp.route('/admin/tenants-defaults/configuration/export')
    @_admin_view
    def admin_tenant_defaults_export():
        tenant_id = _source_scope()
        from .tenant_defaults_bundle import export_defaults_bundle
        try:
            payload = export_defaults_bundle(source_tenant_id=tenant_id, include_secrets=False)
            # Persist the installation identity generated on the first export.
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        return _download(payload, f'cir-tenant-{tenant_id}-configuration.json')

    @bp.route('/admin/tenants-defaults/configuration/import', methods=['POST'])
    @_admin_view
    def admin_tenant_defaults_import():
        _superuser()
        defaults = Tenant.query.filter_by(is_system_defaults=True).one()
        if request.form.get('target_tenant_id', str(defaults.id)) != str(defaults.id):
            abort(400)
        try:
            if request.form.get('confirm') != '1':
                raise ValueError('Confermare la pubblicazione delle configurazioni in tutti i tenant.')
            from .tenant_defaults_bundle import BUNDLE_FORMAT, import_defaults_bundle
            payload = _json_upload()
            if payload.get('format') == BUNDLE_FORMAT:
                result = import_defaults_bundle(payload)
            else:
                result = import_configuration(payload, defaults.id)
            sync_defaults_configuration()
            from .routes import audit_log
            audit_log('admin:defaults_import', {'defaults_tenant_id': defaults.id}, actor_type='user')
            db.session.commit()
            flash('Configurazioni importate in Tenants Default e propagate ai tenant.', 'success')
            if payload.get('format') == BUNDLE_FORMAT:
                preserved = (len(result.get('preserved_settings', []))
                             + result.get('preserved_drafts', 0) + result.get('preserved_catalog', 0))
                if preserved:
                    flash('Conservate personalizzazioni locali: '
                          f"{len(result.get('preserved_settings', []))} parametri, "
                          f"{result.get('preserved_drafts', 0)} workflow in preparazione e "
                          f"{result.get('preserved_catalog', 0)} voci del catalogo.", 'info')
                if not payload.get('includes_secrets'):
                    flash('Il file non include credenziali. I segreti locali esistenti sono stati conservati; '
                          'verificare e completare le credenziali delle integrazioni importate prima di attivarle.', 'warning')
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return render_template('admin_tenant_defaults.html', defaults_tenant=defaults,
                                   tenant=defaults, can_publish=True), 400
        return redirect(url_for('main.admin_tenant_defaults'))

    @bp.route('/admin/tenants-defaults/export', methods=['POST'])
    @_admin_view
    def admin_tenant_defaults_export_all():
        _superuser()
        from .tenant_defaults_bundle import export_defaults_bundle
        try:
            payload = export_defaults_bundle(include_secrets=request.form.get('include_secrets') == '1')
            from .routes import audit_log
            audit_log('admin:defaults_export', {'secrets_included': request.form.get('include_secrets') == '1'}, actor_type='user')
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        return _download(payload, 'cir-tenants-default-complete.json')

    @bp.route('/admin/tenants-defaults/settings')
    @_admin_view
    def admin_tenant_defaults_settings():
        from .routes import current_tenant, current_tenant_id
        from .tenant_default_settings import is_tenant_parameter
        tenant = current_tenant()
        source = Tenant.query.filter_by(is_system_defaults=True).one()
        local_prefix, source_prefix = f'tenant:{current_tenant_id()}:', f'tenant:{source.id}:'
        source_keys = {r.key[len(source_prefix):] for r in Setting.query.filter(Setting.key.startswith(source_prefix)).all()
                       if tenant.is_system_defaults or r.value is not None}
        local_keys = {r.key[len(local_prefix):] for r in Setting.query.filter(Setting.key.startswith(local_prefix)).all()}
        # Only the operational default tenant retains unscoped compatibility.
        # Other tenants and the special source never inherit its private data.
        legacy_keys = set() if tenant.is_system_defaults or tenant.name != 'default' else {
            row.key for row in Setting.query.filter(~Setting.key.startswith('tenant:')).all()
            if is_tenant_parameter(row.key)
        }
        parameters = [{'key': key, 'shared': key in source_keys, 'local': key in local_keys,
                       'legacy': key in legacy_keys}
                      for key in sorted(source_keys | local_keys | legacy_keys) if is_tenant_parameter(key)]
        return render_template('admin_tenant_defaults_settings.html', tenant=tenant, parameters=parameters)

    @bp.route('/admin/tenants-defaults/settings/inherit', methods=['POST'])
    @_admin_view
    def admin_tenant_defaults_setting_inherit():
        from .routes import current_tenant_id, current_tenant, audit_log
        from .tenant_default_settings import is_tenant_parameter
        tenant_id = _source_scope()
        key = request.form.get('key', '')
        if current_tenant().is_system_defaults or not is_tenant_parameter(key):
            abort(400)
        defaults = Tenant.query.filter_by(is_system_defaults=True).one()
        if db.session.get(Setting, f'tenant:{defaults.id}:{key}') is None:
            abort(400, 'Il parametro non è pubblicato nei defaults.')
        row = db.session.get(Setting, f'tenant:{tenant_id}:{key}')
        if row is not None:
            db.session.delete(row)
        audit_log('admin:defaults_setting_inherit', {'key': key, 'tenant_id': current_tenant_id()}, actor_type='user')
        db.session.commit()
        flash('Personalizzazione locale rimossa. Il parametro segue ora Tenants Default.', 'success')
        return redirect(url_for('main.admin_tenant_defaults_settings'))

    @bp.route('/admin/tenants-defaults/alerts')
    @_admin_view
    def admin_tenant_defaults_alerts():
        from .routes import current_tenant_id, is_superuser
        query = TenantDefaultAlert.query
        if not is_superuser() or request.args.get('all') != '1':
            query = query.filter_by(tenant_id=current_tenant_id())
        notices = query.order_by(TenantDefaultAlert.id.desc()).limit(500).all()
        tenants = {t.id: t.name for t in Tenant.query.all()}
        return render_template('admin_tenant_defaults_alerts.html', notices=notices, tenant_names=tenants)

    @bp.route('/admin/tenants-defaults/alerts/<int:alert_id>/ack', methods=['POST'])
    @_admin_view
    def admin_tenant_defaults_ack(alert_id):
        from .routes import current_tenant_id, is_superuser, audit_log
        alert = db.session.get(TenantDefaultAlert, alert_id) or abort(404)
        if alert.tenant_id != current_tenant_id() and not is_superuser():
            abort(403)
        alert.acknowledged_at = utcnow()
        audit_log('admin:defaults_alert_ack', {'alert_id': alert_id, 'tenant_id': alert.tenant_id}, actor_type='user')
        db.session.commit()
        return redirect(url_for('main.admin_tenant_defaults_alerts'))

    @bp.route('/admin/workflow-catalog')
    @_admin_view
    def admin_workflow_catalog():
        from .routes import current_tenant_id, is_superuser, current_tenant
        tenant_id = current_tenant_id()
        categories = ConfigLabel.query.filter_by(tenant_id=tenant_id, kind='category').order_by(ConfigLabel.value).all()
        targets = Tenant.query.filter_by(is_system_defaults=False).order_by(Tenant.name).all() if is_superuser() else [current_tenant()]
        entries = WorkflowCatalogEntry.query.filter_by(active=True).order_by(WorkflowCatalogEntry.name).all()
        return render_template('admin_workflow_catalog.html', entries=entries, categories=categories,
                               targets=targets, source_tenant=current_tenant(), can_publish=is_superuser())

    @bp.route('/admin/workflow-catalog/export-workflow')
    @_admin_view
    def admin_workflow_catalog_export_workflow():
        try:
            payload = build_catalog_workflow_payload(_source_scope(), _category_id())
        except ValueError as exc:
            abort(400, str(exc))
        return _download(payload, 'cir-workflow-catalog.json')

    @bp.route('/admin/workflow-catalog/publish', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_publish():
        _superuser()
        try:
            payload = build_catalog_workflow_payload(_source_scope(), _category_id())
            entry = save_catalog_workflow(payload, request.form.get('name', ''), request.form.get('description', ''))
            source = db.session.get(Tenant, _source_scope())
            if source.is_system_defaults:
                from .workflow_lifecycle import ensure_workflow_state
                state = ensure_workflow_state(source.id, _category_id())
                entry.source_scope_key = state.scope_key
            from .routes import audit_log
            audit_log('admin:workflow_catalog_publish', {'entry_id': entry.id}, actor_type='user')
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        flash('Workflow aggiunto al catalogo di Tenants Default.', 'success')
        return redirect(url_for('main.admin_workflow_catalog'))

    @bp.route('/admin/workflow-catalog/import-file', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_import_file():
        _superuser()
        try:
            entry = save_catalog_workflow(_json_upload(), request.form.get('name', ''),
                                          request.form.get('description', ''),
                                          entry_id=request.form.get('entry_id', type=int))
            from .routes import audit_log
            audit_log('admin:workflow_catalog_import', {'entry_id': entry.id}, actor_type='user')
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        flash('Workflow importato nel catalogo. I workflow già installati nei tenant restano autonomi.', 'success')
        return redirect(url_for('main.admin_workflow_catalog'))

    @bp.route('/admin/workflow-catalog/<int:entry_id>/export')
    @_admin_view
    def admin_workflow_catalog_export(entry_id):
        try:
            return _download(export_catalog_entry(entry_id), f'cir-catalog-workflow-{entry_id}.json')
        except ValueError as exc:
            abort(404, str(exc))

    @bp.route('/admin/workflow-catalog/<int:entry_id>/install', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_install(entry_id):
        from .routes import current_tenant_id, is_superuser, audit_log
        target_id = request.form.get('target_tenant_id', type=int) or current_tenant_id()
        if not is_superuser() and target_id != current_tenant_id():
            abort(403)
        target = db.session.get(Tenant, target_id)
        if target is None or target.is_system_defaults:
            abort(400, 'Selezionare un tenant operativo.')
        try:
            result = import_catalog_workflow(entry_id, target_id,
                                            as_default=request.form.get('as_default') == '1',
                                            copy_name=request.form.get('copy_name') or None)
            audit_log('admin:workflow_catalog_install', {'entry_id': entry_id, 'tenant_id': target_id}, actor_type='user')
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        flash(f'Creata la copia "{result["copy_name"]}" in {target.name}. Puoi modificarla dai workflow del tenant.', 'success')
        return redirect(url_for('main.admin_workflow_catalog'))

    @bp.route('/admin/workflow-catalog/<int:entry_id>/retire', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_retire(entry_id):
        _superuser()
        entry = db.session.get(WorkflowCatalogEntry, entry_id) or abort(404)
        from .workflow_lifecycle import set_catalog_workflow_status
        set_catalog_workflow_status(entry.id, 'obsolete')
        entry.active = False
        from .routes import audit_log
        audit_log('admin:workflow_catalog_retire', {'entry_id': entry_id}, actor_type='user')
        db.session.commit()
        flash('Workflow ritirato dal catalogo. Le copie importate nei tenant sono conservate.', 'success')
        return redirect(url_for('main.admin_workflow_catalog'))

    @bp.route('/admin/workflow-catalog/<int:entry_id>/status', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_status(entry_id):
        _superuser()
        from .workflow_lifecycle import set_catalog_workflow_status
        try:
            entry = set_catalog_workflow_status(entry_id, request.form.get('status', ''))
            from .routes import audit_log
            audit_log('admin:workflow_catalog_status', {'entry_id': entry.id, 'status': entry.status}, actor_type='user')
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        flash('Stato del catalogo aggiornato. Le copie obsolete possono essere riattivate solo dai rispettivi amministratori quando la sorgente è corrente.', 'success')
        return redirect(url_for('main.admin_workflow_catalog'))

    def local_workflow_or_404(workflow_id):
        from .workflow_catalog_models import TenantWorkflow
        from .routes import current_tenant_id, is_superuser
        state = db.session.get(TenantWorkflow, workflow_id) or abort(404)
        if not is_superuser() and state.tenant_id != current_tenant_id():
            abort(403)
        return state

    @bp.route('/admin/workflow-catalog/local/<int:workflow_id>/status', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_local_status(workflow_id):
        state = local_workflow_or_404(workflow_id)
        from .workflow_lifecycle import set_workflow_status
        try:
            set_workflow_status(state.tenant_id, state.category_id, request.form.get('status', ''))
            from .routes import audit_log
            audit_log('admin:workflow_status', {'workflow_id': state.id, 'status': state.status}, actor_type='user')
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        flash('Stato del workflow aggiornato. Gli incidenti esistenti conservano il loro flusso.', 'success')
        return redirect(url_for('main.admin_incident_workflows'))

    @bp.route('/admin/workflow-catalog/local/<int:workflow_id>/personalize', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_personalize(workflow_id):
        state = local_workflow_or_404(workflow_id)
        from .workflow_lifecycle import personalize_workflow_parameters
        try:
            personalize_workflow_parameters(state.id)
            from .routes import audit_log
            audit_log('admin:workflow_personalize', {'workflow_id': state.id}, actor_type='user')
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            abort(400, str(exc))
        flash('Parametri copiati per questo workflow. Le altre copie e Tenants Default conservano le proprie configurazioni.', 'success')
        return redirect(url_for('main.admin_incident_workflows'))

    @bp.route('/admin/workflow-catalog/notices')
    @_admin_view
    def admin_workflow_catalog_notices():
        from .workflow_catalog_models import WorkflowObsolescenceNotice
        notices = WorkflowObsolescenceNotice.query.filter_by(user_id=current_user.id).order_by(
            WorkflowObsolescenceNotice.created_at.desc(), WorkflowObsolescenceNotice.id.desc()).limit(200).all()
        return render_template('admin_workflow_notices.html', notices=notices)

    @bp.route('/admin/workflow-catalog/notices/<int:notice_id>/acknowledge', methods=['POST'])
    @_admin_view
    def admin_workflow_catalog_notice_acknowledge(notice_id):
        from .workflow_catalog_models import WorkflowObsolescenceNotice
        notice = WorkflowObsolescenceNotice.query.filter_by(id=notice_id, user_id=current_user.id).first_or_404()
        notice.read_at = notice.read_at or utcnow()
        db.session.commit()
        return redirect(url_for('main.admin_workflow_catalog_notices'))
