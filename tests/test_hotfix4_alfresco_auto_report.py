from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app/routes.py').read_text(encoding='utf-8')
MODELS = (ROOT / 'app/models.py').read_text(encoding='utf-8')
APP_INIT = (ROOT / 'app/__init__.py').read_text(encoding='utf-8')
CLIENT = (ROOT / 'app/plugins/alfresco/client.py').read_text(encoding='utf-8')
DETAIL = (ROOT / 'app/templates/incident_detail.html').read_text(encoding='utf-8')
TENANTS = (ROOT / 'app/templates/admin_tenants.html').read_text(encoding='utf-8')
PLUGIN_INIT = (ROOT / 'app/plugins/alfresco/__init__.py').read_text(encoding='utf-8')


def test_incident_model_and_schema_persist_auto_report_state():
    names = (
        'alfresco_auto_report_enabled',
        'alfresco_report_node_id',
        'alfresco_report_path',
        'alfresco_report_updated_at',
        'alfresco_report_fingerprint',
    )
    for name in names:
        assert name in MODELS
        assert name in APP_INIT


def test_incident_option_requires_plugin_and_tenant_visibility_policy():
    assert "alfresco_plugin_enabled() and alfresco_auto_report_option_visible()" in DETAIL
    assert 'Genera e aggiorna automaticamente report su Alfresco' in DETAIL
    assert 'inc.alfresco_auto_report_enabled' in DETAIL
    assert "app.jinja_env.globals['alfresco_auto_report_option_visible']" in PLUGIN_INIT


def test_tenant_controls_visibility_and_default_on_off():
    assert 'alfresco_auto_report_option_visible' in TENANTS
    assert 'alfresco_auto_report_default_enabled' in TENANTS
    assert "ALFRESCO_AUTO_REPORT_VISIBLE_DEFAULT = '1'" in ROUTES
    assert "ALFRESCO_AUTO_REPORT_ENABLED_DEFAULT = '0'" in ROUTES
    assert 'set_tenant_setting_value_for_id(ALFRESCO_AUTO_REPORT_VISIBLE_SETTING' in ROUTES
    assert 'set_tenant_setting_value_for_id(ALFRESCO_AUTO_REPORT_DEFAULT_SETTING' in ROUTES


def test_new_and_cloned_incidents_use_tenant_default_only_if_plugin_enabled():
    marker = 'alfresco_auto_report_enabled=bool(alfresco_is_enabled_safe() and alfresco_auto_report_default_enabled())'
    assert ROUTES.count(marker) >= 2


def test_report_refresh_is_content_fingerprinted_and_best_effort():
    block = ROUTES[ROUTES.index('def _incident_alfresco_report_fingerprint'):ROUTES.index('def make_notification_mail_pdf')]
    assert 'hashlib.sha256' in block
    assert 'incident_pdf(inc)' in block
    assert 'upload_or_update_incident_report' in block
    assert 'incident_report_filename(inc.id, inc.name)' in block
    assert 'alfresco_report_fingerprint = fingerprint' in block
    assert 'if not force and fingerprint ==' in block
    assert "current_app.logger.exception('Aggiornamento automatico report Alfresco fallito" in block


def test_report_is_created_and_refreshed_after_report_relevant_mutations():
    for reason in (
        'incident-create', 'incident-update', 'incident-clone',
        'action-add', 'action-update', 'action-delete',
        'document-upload', 'document-delete', 'generated-forms',
        'reminder-add', 'reminder-update', 'document-download-action',
        'document-tags-action',
    ):
        assert f"reason='{reason}'" in ROUTES


def test_get_incident_detail_does_not_mutate_alfresco_or_database():
    start = ROUTES.index("@bp.route('/incident/<int:iid>',methods=['GET','POST'])")
    end = ROUTES.index("@bp.route('/incident/<int:iid>/delete'", start)
    block = ROUTES[start:end]
    assert "reason='incident-detail'" not in block


def test_client_updates_existing_report_node_with_put_and_recreates_missing_node():
    block = CLIENT[CLIENT.index('def upload_or_update_incident_report'):CLIENT.index('def download_file', CLIENT.index('def upload_or_update_incident_report'))]
    assert 'requests.put(' in block
    assert "f'nodes/{quote(node_id, safe=\"\")}/content'" in block
    assert 'response.status_code not in {404, 410}' in block
    assert "group_by_type=False" in block


def test_canonical_report_lives_directly_under_incident_directory():
    block = CLIENT[CLIENT.index('def upload_or_update_incident_report'):CLIENT.index('def download_file', CLIENT.index('def upload_or_update_incident_report'))]
    assert 'incident_folder_name(incident_id, incident_name)' in block
    assert "group_by_type=False" in block
    assert "mimetype='application/pdf'" in block
