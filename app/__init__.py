import os, time, shutil, secrets

from .version import APP_RELEASE_VERSION, APP_RELEASE_BUILD
from flask import Flask, session
from .text_filters import register_text_filters
from sqlalchemy import text, inspect, Table, MetaData, select, func
from sqlalchemy.exc import OperationalError
from .models import db, Tenant, User, UserTenantRole, ConfigLabel, Setting, NotificationType, NotificationTemplate, FormFieldMapping, FormTemplateConfig, FormTemplateBinary, AuditLog, IncidentReminder, ExternalRecipient, IncidentWorkflowStep, BackupJob, AIChatbotDocument, Incident, IncidentTemplate, Person, Recommendation
from .auth import login_manager, hash_password
from .env_utils import get_admin_initial_password
from .security import init_security
from .consequences import default_consequence_settings

def create_app():
    app=Flask(__name__)
    register_text_filters(app)
    app.config['SECRET_KEY']=os.getenv('SECRET_KEY') or secrets.token_urlsafe(48)
    app.config['SQLALCHEMY_DATABASE_URI']=os.getenv('DATABASE_URL','sqlite:////tmp/cir.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
    init_security(app)
    app.config['UPLOAD_DIR']=os.getenv('UPLOAD_DIR','/data/cir_uploads')
    app.config['LOGO_DIR']=os.getenv('LOGO_DIR','/data/cir_logo')
    app.config['SSO_LOGO_DIR']=os.getenv('SSO_LOGO_DIR','/data/sso_logos')
    app.config['FORM_TEMPLATE_DIR']=os.getenv('FORM_TEMPLATE_DIR','/data/form_templates')
    app.config['BACKUP_DIR']=os.getenv('BACKUP_DIR','/data/backups')
    app.config['AI_CHATBOT_DOC_DIR']=os.getenv('AI_CHATBOT_DOC_DIR','/data/ai_chatbot_docs')
    try:
        app.config['MAX_CONTENT_LENGTH']=int(os.getenv('MAX_CONTENT_LENGTH','26214400'))
    except (TypeError, ValueError):
        app.config['MAX_CONTENT_LENGTH']=26214400
    app.config['MAX_FORM_MEMORY_SIZE']=app.config['MAX_CONTENT_LENGTH']
    app.config['APP_INFO']={
        'name': os.getenv('APP_NAME','Cybersecurity Incident Registry'),
        'version': APP_RELEASE_VERSION,
        'build': APP_RELEASE_BUILD,
        'author': os.getenv('APP_AUTHOR','Alessandro De Salvo'),
        'author_email': os.getenv('APP_AUTHOR_EMAIL','Alessandro.DeSalvo@roma1.infn.it'),
    }
    for _persistent_dir in (app.config['UPLOAD_DIR'], app.config['LOGO_DIR'], app.config['SSO_LOGO_DIR'], app.config['FORM_TEMPLATE_DIR'], app.config['BACKUP_DIR'], app.config['AI_CHATBOT_DOC_DIR']):
        os.makedirs(_persistent_dir, exist_ok=True)

    def _copy_missing_packaged_assets(src_dir, dst_dir, allowed_exts):
        if not os.path.isdir(src_dir):
            return
        for name in os.listdir(src_dir):
            if os.path.splitext(name)[1].lower() not in allowed_exts:
                continue
            src = os.path.join(src_dir, name)
            dst = os.path.join(dst_dir, name)
            if os.path.exists(dst):
                continue
            try:
                shutil.copyfile(src, dst)
            except PermissionError:
                app.logger.warning('Persistent directory is not writable while seeding default asset: %s', dst)
            except OSError as exc:
                app.logger.warning('Unable to seed default asset %s: %s', dst, exc)

    # Copia i loghi SSO predefiniti nella directory persistente solo se non esistono.
    # L'entrypoint Docker li copia prima del drop dei privilegi; questo fallback
    # resta per esecuzioni locali/non-container e non deve far fallire lo startup.
    packaged_sso_logos = os.path.join(app.static_folder or os.path.join(os.path.dirname(__file__), 'static'), 'sso')
    _copy_missing_packaged_assets(packaged_sso_logos, app.config['SSO_LOGO_DIR'], {'.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp'})

    # Copia i template PDF di esempio nella directory persistente solo se non esistono.
    packaged_templates = os.path.join(os.path.dirname(__file__), 'form_templates')
    _copy_missing_packaged_assets(packaged_templates, app.config['FORM_TEMPLATE_DIR'], {'.pdf'})


    # Rimuove eventuali template di modulo predefiniti storici.
    # I template creati/caricati dall'utente non vengono toccati.
    for obsolete_name in ('comunicazione_data_breach_art34.xml', 'notifica_interna_data_breach_art33.xml'):
        obsolete_path = os.path.join(app.config['FORM_TEMPLATE_DIR'], obsolete_name)
        if os.path.exists(obsolete_path):
            try:
                os.remove(obsolete_path)
            except OSError:
                app.logger.warning('Unable to remove obsolete form template %s', obsolete_path)

    db.init_app(app); login_manager.init_app(app); login_manager.login_view='main.login'
    @app.context_processor
    def inject_app_info():
        
        from flask import g
        data = {'app_info': app.config['APP_INFO'], 'current_language': getattr(g, 'lang', 'it')}
        # Menu Notifiche dinamico: mostra tutti i tipi/template registrati,
        # inclusi quelli creati dall'utente. La query è protetta perché il
        # context processor può essere invocato anche durante login/bootstrap
        # o con schema non ancora aggiornato.
        try:
            from flask_login import current_user
            from sqlalchemy import or_
            from .routes import current_tenant_id, is_superuser, user_role_for_tenant, user_accessible_tenant_ids
            if getattr(current_user, 'is_authenticated', False) and user_role_for_tenant() in ['admin','superuser']:
                tid = current_tenant_id()
                data['notification_menu_types'] = NotificationType.query.filter(or_(NotificationType.tenant_id == tid, NotificationType.tenant_id.is_(None))).filter_by(enabled=True).order_by(NotificationType.label).all()
            else:
                data['notification_menu_types'] = []
            
            ids = user_accessible_tenant_ids()
            data['available_tenants'] = Tenant.query.order_by(Tenant.name).all() if ids is None else Tenant.query.filter(Tenant.id.in_(ids or [])).order_by(Tenant.name).all()
            data['active_tenant'] = db.session.get(Tenant, current_tenant_id()) if getattr(current_user, 'is_authenticated', False) else None
            data['current_tenant_role'] = user_role_for_tenant() if getattr(current_user, 'is_authenticated', False) else 'disabled'
            data['current_user_is_superuser'] = is_superuser()
        except Exception:
            data['notification_menu_types'] = []
            data['available_tenants'] = []
            data['active_tenant'] = None
            data['current_tenant_role'] = 'disabled'
            data['current_user_is_superuser'] = False
        try:
            from flask_login import current_user
            from .routes import user_role_for_tenant
            data['modules_menu_visible'] = bool(getattr(current_user, 'is_authenticated', False) and user_role_for_tenant() in ['admin','superuser'])
        except Exception:
            data['modules_menu_visible'] = False
        return data
    from .routes import bp, start_deadline_notification_scheduler, start_incident_reminder_scheduler, start_backup_scheduler, sso_logo_url, apply_configured_max_upload_size; app.register_blueprint(bp); app.jinja_env.globals['sso_logo_url'] = sso_logo_url
    @app.before_request
    def _refresh_configured_upload_limit():
        try:
            apply_configured_max_upload_size(app)
        except Exception:
            pass
    from .plugins.ai_chatbot import register_plugin as register_ai_chatbot_plugin; register_ai_chatbot_plugin(app)
    from .plugins.alfresco import register_plugin as register_alfresco_plugin; register_alfresco_plugin(app)
    with app.app_context():
        wait_db(db)
        bootstrap(app)
    start_deadline_notification_scheduler(app)
    start_incident_reminder_scheduler(app)
    start_backup_scheduler(app)
    return app

def wait_db(db):
    last=None
    for _ in range(30):
        try:
            db.session.execute(text('SELECT 1')); db.session.commit(); return
        except OperationalError as e:
            last=e; db.session.rollback(); time.sleep(2)
    raise last


def ensure_default_tenant():
    tenant = Tenant.query.filter_by(name='default').first()
    if tenant is None:
        tenant = Tenant(name='default', description='Tenant predefinito')
        db.session.add(tenant)
        db.session.flush()
    return tenant

def ensure_setting(key, value):
    s=db.session.get(Setting, key)
    if not s:
        db.session.add(Setting(key=key,value=value))


def _decode_legacy_refresh_token(hex_value):
    return bytes.fromhex(hex_value).decode('ascii')


def normalize_update_section_persistent_values():
    legacy_step = _decode_legacy_refresh_token('73686f775f73656374696f6e')
    legacy_scope = _decode_legacy_refresh_token('776f726b666c6f775f73656374696f6e')
    legacy_registration_step = _decode_legacy_refresh_token('636f6e6669726d')
    legacy_registration_label = _decode_legacy_refresh_token('436f6e6665726d61')
    legacy_registration_description = _decode_legacy_refresh_token('436f6e6665726d612066617365')
    IncidentWorkflowStep.query.filter_by(step_type=legacy_registration_step).update({'step_type': 'registration'}, synchronize_session=False)
    IncidentWorkflowStep.query.filter_by(step_type=legacy_step).update({'step_type': 'update_section'}, synchronize_session=False)
    workflow_types = db.session.get(Setting, 'workflow_step_types_json')
    if workflow_types and workflow_types.value:
        workflow_types.value = workflow_types.value.replace(legacy_registration_description, 'Premi per registrare').replace(legacy_registration_step, 'registration').replace(legacy_registration_label, 'Registrazione').replace(legacy_step, 'update_section')
    button_actions = db.session.get(Setting, 'incident_button_action_labels_json')
    if button_actions and button_actions.value:
        button_actions.value = button_actions.value.replace(legacy_scope, 'workflow_update_section')

DEFAULT_CONFIG_LABELS = {
    'severity': {
        'group': 'gravità',
        'values': ['molto bassa', 'bassa', 'media', 'alta', 'critica'],
    },
    'data_type': {
        'group': 'dati interessati',
        'values': ['password', 'dati personali'],
    },
    'category': {
        'group': 'categorie',
        'values': ['furto di credenziali', 'phishing', 'SPAM', 'altro'],
    },
    'action_label': {
        'group': 'azioni',
        'values': ['01-informazione iniziale', '02-analisi', '03-blocco', '04-comunicazione allo CSIRT', '05-comunicazione al DPO', '06-comunicazione al Garante della Privacy', '07-notifica all’utente', '08-conclusione', '09-aggiornamento dati incidente'],
    },
}

def default_label_metadata(kind, value):
    default_exportable = True
    automatic_operations = ''
    if kind == 'action_label':
        text_value = (value or '').lower().replace('’', "'")
        default_exportable = not any(k in text_value for k in ('notifica', 'comunicazione', 'informazione iniziale', 'analisi', 'conclusione', 'aggiornamento dati incidente'))
        if 'conclusione' in text_value:
            automatic_operations = 'close_without_warnings,end_breach'
    return default_exportable, automatic_operations

def ensure_label(kind, value, group='default'):
    label = ConfigLabel.query.filter_by(kind=kind,value=value).first()
    default_exportable, automatic_operations = default_label_metadata(kind, value)
    if not label:
        db.session.add(ConfigLabel(kind=kind,value=value,group=group,default_exportable=default_exportable,automatic_operations=automatic_operations))
        return True
    if kind == 'action_label':
        if getattr(label, 'default_exportable', None) is None:
            label.default_exportable = default_exportable
        if automatic_operations and not (getattr(label, 'automatic_operations', '') or '').strip():
            label.automatic_operations = automatic_operations
    return False

def restore_missing_default_config_labels():
    added = []
    for kind, spec in DEFAULT_CONFIG_LABELS.items():
        group = spec.get('group') or kind
        for value in spec.get('values') or []:
            if ensure_label(kind, value, group):
                added.append((kind, value))
    return added


def ensure_user_tenant_role(user, tenant_id=None, role=None):
    if not user:
        return None
    tid = tenant_id or user.tenant_id or ensure_default_tenant().id
    effective_role = (role or user.role or 'disabled').strip().lower()
    # ``superuser`` is now stored as an effective tenant membership too; the
    # account becomes global superuser if any membership has that role.
    membership = UserTenantRole.query.filter_by(user_id=user.id, tenant_id=tid).first()
    if not membership:
        membership = UserTenantRole(user_id=user.id, tenant_id=tid, role=effective_role)
        db.session.add(membership)
    else:
        membership.role = effective_role
    return membership


def sync_user_tenant_roles():
    default = ensure_default_tenant()
    for user in User.query.all():
        if not user.tenant_id:
            user.tenant_id = default.id
        if getattr(user, 'is_builtin_admin', False):
            user.role = 'superuser'
            user.default_tenant_id = None
            ensure_user_tenant_role(user, user.tenant_id, 'superuser')
        else:
            ensure_user_tenant_role(user, user.default_tenant_id or user.tenant_id, user.role)
            if not getattr(user, 'default_tenant_id', None):
                user.default_tenant_id = user.tenant_id


def assign_default_tenant_to_unscoped(default_tenant):
    scoped_models = [User, ConfigLabel, IncidentWorkflowStep, Person, Recommendation, Incident, IncidentTemplate, NotificationType, NotificationTemplate, ExternalRecipient, BackupJob, AIChatbotDocument, AuditLog]
    for model in scoped_models:
        try:
            model.query.filter(model.tenant_id.is_(None)).update({'tenant_id': default_tenant.id}, synchronize_session=False)
        except Exception:
            db.session.rollback()
            raise

def database_has_existing_operational_data():
    checks = [User, ConfigLabel, Setting]
    for model in checks:
        try:
            if db.session.query(model.id if hasattr(model, 'id') else model.key).limit(1).first():
                return True
        except Exception:
            db.session.rollback()
    return False



def run_schema_migrations(app):
    """Migrazioni leggere e idempotenti eseguite all'avvio.

    Mantengono riutilizzabile il database tra versioni successive senza
    cancellare dati. In particolare aggiungono colonne nuove quando un
    database esistente ha uno schema precedente.
    """
    try:
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())

        if 'tenant' not in tables:
            with db.engine.begin() as conn:
                conn.execute(text('CREATE TABLE tenant (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE, description TEXT, created_at TIMESTAMP)'))
            app.logger.info('Schema migration applied: tenant table created')
            inspector = inspect(db.engine); tables = set(inspector.get_table_names())
        # Ensure the default tenant exists before backfilling tenant_id columns.
        with db.engine.begin() as conn:
            if str(db.engine.url).startswith('postgresql'):
                conn.execute(text("INSERT INTO tenant (name, description, created_at) VALUES ('default', 'Tenant predefinito', CURRENT_TIMESTAMP) ON CONFLICT (name) DO NOTHING"))
            else:
                conn.execute(text("INSERT OR IGNORE INTO tenant (id, name, description, created_at) VALUES (1, 'default', 'Tenant predefinito', CURRENT_TIMESTAMP)"))
        tenant_scoped_tables = ['user','incident','config_label','incident_workflow_step','person','recommendation','incident_template','notification_type','notification_template','external_recipient','backup_job','ai_chatbot_document','audit_log']
        # Prima di popolare user_tenant_role aggiungiamo/backfilliamo tenant_id
        # sulle tabelle legacy, inclusa "user". Su PostgreSQL un SELECT non può
        # referenziare user.tenant_id se la colonna non esiste ancora: l'ordine
        # precedente causava un crash in migrazione su database pre-multitenant.
        for table_name in tenant_scoped_tables:
            if table_name in tables:
                cols_for_table = {c['name'] for c in inspector.get_columns(table_name)}
                if 'tenant_id' not in cols_for_table:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN tenant_id INTEGER'))  # nosec: B608
                        conn.execute(text(f"UPDATE \"{table_name}\" SET tenant_id = (SELECT id FROM tenant WHERE name = 'default') WHERE tenant_id IS NULL"))  # nosec: B608
                    app.logger.info('Schema migration applied: %s.tenant_id added', table_name)
                else:
                    with db.engine.begin() as conn:
                        conn.execute(text(f"UPDATE \"{table_name}\" SET tenant_id = (SELECT id FROM tenant WHERE name = 'default') WHERE tenant_id IS NULL"))  # nosec: B608
        if 'user' in tables:
            user_cols = {c['name'] for c in inspector.get_columns('user')}
            if 'default_tenant_id' not in user_cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN default_tenant_id INTEGER'))
                    conn.execute(text("UPDATE \"user\" SET default_tenant_id = tenant_id WHERE default_tenant_id IS NULL AND tenant_id IS NOT NULL AND username <> 'admin'"))
                app.logger.info('Schema migration applied: user.default_tenant_id added')
            else:
                with db.engine.begin() as conn:
                    conn.execute(text("UPDATE \"user\" SET default_tenant_id = tenant_id WHERE default_tenant_id IS NULL AND tenant_id IS NOT NULL AND username <> 'admin'"))

        inspector = inspect(db.engine); tables = set(inspector.get_table_names())

        if 'user_tenant_role' not in tables:
            with db.engine.begin() as conn:
                if str(db.engine.url).startswith('postgresql'):
                    conn.execute(text("CREATE TABLE user_tenant_role (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, tenant_id INTEGER NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'disabled', created_at TIMESTAMP, updated_at TIMESTAMP, UNIQUE(user_id, tenant_id))"))
                else:
                    conn.execute(text("CREATE TABLE user_tenant_role (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, tenant_id INTEGER NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'disabled', created_at TIMESTAMP, updated_at TIMESTAMP, UNIQUE(user_id, tenant_id))"))
            app.logger.info('Schema migration applied: user_tenant_role table created')
            inspector = inspect(db.engine); tables = set(inspector.get_table_names())
        if 'user_tenant_role' in tables and 'user' in tables:
            tenant_expr = 'u.tenant_id'  # migration invariant: kept explicit for schema-regression checks
            # The migration above guarantees user.tenant_id exists before this
            # backfill runs, so the INSERT statements can stay static and avoid
            # string-built SQL.
            with db.engine.begin() as conn:
                if str(db.engine.url).startswith('postgresql'):
                    conn.execute(text('''INSERT INTO user_tenant_role (user_id, tenant_id, role, created_at, updated_at)
                        SELECT u.id, COALESCE(u.tenant_id, (SELECT id FROM tenant WHERE name = 'default')), COALESCE(NULLIF(u.role, ''), 'disabled'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        FROM "user" AS u
                        WHERE COALESCE(u.role, '') <> 'superuser'
                        ON CONFLICT (user_id, tenant_id) DO NOTHING'''))
                    conn.execute(text('''INSERT INTO user_tenant_role (user_id, tenant_id, role, created_at, updated_at)
                        SELECT u.id, COALESCE(u.tenant_id, (SELECT id FROM tenant WHERE name = 'default')), 'superuser', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        FROM "user" AS u
                        WHERE u.role = 'superuser' AND u.username <> 'admin'
                        ON CONFLICT (user_id, tenant_id) DO NOTHING'''))
                else:
                    conn.execute(text('''INSERT OR IGNORE INTO user_tenant_role (user_id, tenant_id, role, created_at, updated_at)
                        SELECT u.id, COALESCE(u.tenant_id, (SELECT id FROM tenant WHERE name = 'default')), COALESCE(NULLIF(u.role, ''), 'disabled'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        FROM "user" AS u
                        WHERE COALESCE(u.role, '') <> 'superuser' '''))
                    conn.execute(text('''INSERT OR IGNORE INTO user_tenant_role (user_id, tenant_id, role, created_at, updated_at)
                        SELECT u.id, COALESCE(u.tenant_id, (SELECT id FROM tenant WHERE name = 'default')), 'superuser', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        FROM "user" AS u
                        WHERE u.role = 'superuser' AND u.username <> 'admin' '''))

        if 'user' in tables:
            with db.engine.begin() as conn:
                conn.execute(text("UPDATE \"user\" SET role = 'superuser', default_tenant_id = NULL WHERE username = 'admin' AND auth_provider = 'local'"))

        if str(db.engine.url).startswith('postgresql'):
            tenant_unique_specs = {
                'config_label': (['kind','value'], 'uq_label_tenant_kind_value', ['tenant_id','kind','value']),
                'notification_type': (['code'], 'uq_notification_type_tenant_code', ['tenant_id','code']),
                'notification_template': (['kind','name'], 'uq_notification_template_tenant_kind_name', ['tenant_id','kind','name']),
                'external_recipient': (['email'], 'uq_external_recipient_tenant_email', ['tenant_id','email']),
                'incident_template': (['name'], 'uq_incident_template_tenant_name', ['tenant_id','name']),
                'person': (['name'], 'uq_person_tenant_name', ['tenant_id','name']),
                'recommendation': (['text'], 'uq_recommendation_tenant_text', ['tenant_id','text']),
            }
            for table_name, (legacy_cols, new_name, new_cols) in tenant_unique_specs.items():
                if table_name not in tables:
                    continue
                try:
                    unique_constraints = inspector.get_unique_constraints(table_name)
                    indexes = inspector.get_indexes(table_name)
                    with db.engine.begin() as conn:
                        has_new = False
                        for constraint in unique_constraints:
                            cols_for_constraint = constraint.get('column_names') or []
                            name = constraint.get('name')
                            if cols_for_constraint == new_cols:
                                has_new = True
                            if name and cols_for_constraint == legacy_cols:
                                safe_name = name.replace('"', '')
                                conn.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{safe_name}"'))
                        # Alcune versioni pre-multitenant avevano indici UNIQUE
                        # generati da SQLAlchemy (es. ix_notification_type_code)
                        # invece di vincoli espliciti. Vanno rimossi, altrimenti
                        # la clonazione di un tenant fallisce quando crea nel tenant
                        # destinazione un codice gia' esistente nel tenant sorgente
                        # (ad esempio notification_type.code = 'user').
                        for index in indexes:
                            cols_for_index = index.get('column_names') or []
                            index_name = (index.get('name') or '').replace('"', '')
                            if index.get('unique') and index_name and cols_for_index == legacy_cols:
                                conn.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
                        if table_name == 'notification_type':
                            conn.execute(text('''DELETE FROM notification_type nt
                                USING notification_type keep
                                WHERE nt.tenant_id = keep.tenant_id
                                  AND nt.code = keep.code
                                  AND nt.id > keep.id'''))
                        if not has_new:
                            quoted_cols = ', '.join(f'"{col}"' for col in new_cols)
                            conn.execute(text(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{new_name}" UNIQUE ({quoted_cols})'))
                    app.logger.info('Schema migration applied: %s unique constraints tenantized', table_name)
                except Exception:
                    app.logger.exception('Unable to tenantize unique constraints for %s', table_name)
        if 'incident' in tables:
            cols = {c['name'] for c in inspector.get_columns('incident')}
            for col_name, col_type in {'data_subjects_count':'VARCHAR(255)', 'data_volume':'TEXT'}.items():
                if col_name not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE incident ADD COLUMN {col_name} {col_type}'))
                    app.logger.info('Schema migration applied: incident.%s added', col_name)
            if 'reference' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE incident ADD COLUMN reference VARCHAR(255) DEFAULT ''"))
                app.logger.info('Schema migration applied: incident.reference added')
            if 'recipient' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident ADD COLUMN recipient VARCHAR(255)'))
                app.logger.info('Schema migration applied: incident.recipient added')
            if 'recipient_email' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident ADD COLUMN recipient_email VARCHAR(255)'))
                app.logger.info('Schema migration applied: incident.recipient_email added')
            cols = {c['name'] for c in inspector.get_columns('incident')}
            if 'category_order' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE incident ADD COLUMN category_order TEXT"))
                    if 'incident_categories' in tables:
                        if str(db.engine.url).startswith('postgresql'):
                            conn.execute(text('''UPDATE incident SET category_order = ordered.ids FROM (SELECT incident_id, string_agg(label_id::text, ',' ORDER BY label_id) AS ids FROM incident_categories GROUP BY incident_id) ordered WHERE incident.id = ordered.incident_id AND (incident.category_order IS NULL OR incident.category_order = '')'''))
                        else:
                            conn.execute(text('''UPDATE incident SET category_order = (SELECT group_concat(label_id, ',') FROM incident_categories WHERE incident_categories.incident_id = incident.id) WHERE category_order IS NULL OR category_order = '' '''))
                app.logger.info('Schema migration applied: incident.category_order added')
            if 'reference' in cols or 'reference' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("UPDATE incident SET reference = 'Incidente #' || CAST(id AS VARCHAR) WHERE reference IS NULL OR TRIM(reference) = ''"))
                app.logger.info('Schema migration applied: incident.reference mandatory values normalized')
            if 'deadline_notifications_muted' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident ADD COLUMN deadline_notifications_muted BOOLEAN'))
                    conn.execute(text('UPDATE incident SET deadline_notifications_muted = FALSE WHERE deadline_notifications_muted IS NULL'))
                app.logger.info('Schema migration applied: incident.deadline_notifications_muted added')
            cols = {c['name'] for c in inspector.get_columns('incident')}
            if 'custom_fields_json' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE incident ADD COLUMN custom_fields_json TEXT"))
                    conn.execute(text("UPDATE incident SET custom_fields_json = '' WHERE custom_fields_json IS NULL"))
                app.logger.info('Schema migration applied: incident.custom_fields_json added')
            split_columns = {
                'start_date': 'DATE',
                'start_time': 'TIME',
                'end_date': 'DATE',
                'end_time': 'TIME',
            }
            added_split_columns = False
            for col_name, col_type in split_columns.items():
                if col_name not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE incident ADD COLUMN {col_name} {col_type}'))
                    added_split_columns = True
                    app.logger.info('Schema migration applied: incident.%s added', col_name)
            refreshed_cols = {c['name'] for c in inspector.get_columns('incident')}
            if {'start_date','start_time','end_date','end_time','start_at','end_at'}.issubset(refreshed_cols):
                with db.engine.begin() as conn:
                    if str(db.engine.url).startswith('postgresql'):
                        conn.execute(text('UPDATE "incident" SET start_date = COALESCE(start_date, start_at::date), start_time = COALESCE(start_time, start_at::time) WHERE start_at IS NOT NULL'))
                        conn.execute(text('UPDATE "incident" SET end_date = COALESCE(end_date, end_at::date), end_time = COALESCE(end_time, end_at::time) WHERE end_at IS NOT NULL'))
                    else:
                        conn.execute(text('UPDATE incident SET start_date = COALESCE(start_date, date(start_at)), start_time = COALESCE(start_time, time(start_at)) WHERE start_at IS NOT NULL'))
                        conn.execute(text('UPDATE incident SET end_date = COALESCE(end_date, date(end_at)), end_time = COALESCE(end_time, time(end_at)) WHERE end_at IS NOT NULL'))
                if added_split_columns:
                    app.logger.info('Schema migration applied: incident split date/time fields populated from legacy datetime columns')
        if 'action' in tables:
            cols = {c['name'] for c in inspector.get_columns('action')}
            if 'consequence_text' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE "action" ADD COLUMN consequence_text TEXT'))
                app.logger.info('Schema migration applied: action.consequence_text added')
            if 'exportable' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE "action" ADD COLUMN exportable BOOLEAN'))
                    conn.execute(text('UPDATE "action" SET exportable = TRUE WHERE exportable IS NULL'))
                app.logger.info('Schema migration applied: action.exportable added')
        if 'user' in tables:
            cols = {c['name'] for c in inspector.get_columns('user')}
            if 'default_tenant_id' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN default_tenant_id INTEGER'))
                    conn.execute(text("UPDATE \"user\" SET default_tenant_id = tenant_id WHERE default_tenant_id IS NULL AND tenant_id IS NOT NULL AND username <> 'admin'"))
                app.logger.info('Schema migration applied: user.default_tenant_id added')
                cols = {c['name'] for c in inspector.get_columns('user')}
            if 'auth_provider' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN auth_provider VARCHAR(40)"))
                    conn.execute(text("UPDATE \"user\" SET auth_provider = CASE WHEN is_ldap THEN 'ldap' ELSE 'local' END WHERE auth_provider IS NULL"))
                app.logger.info('Schema migration applied: user.auth_provider added')
            if 'external_id' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN external_id VARCHAR(255)"))
                app.logger.info('Schema migration applied: user.external_id added')
            # L'identità applicativa è la coppia username + backend di autenticazione.
            # Le versioni precedenti avevano un vincolo univoco sul solo username:
            # su PostgreSQL lo rimuoviamo e creiamo il vincolo composto. Su SQLite
            # i nuovi database usano già il modello aggiornato; gli ambienti di
            # produzione supportati usano PostgreSQL.
            with db.engine.begin() as conn:
                conn.execute(text("UPDATE \"user\" SET auth_provider = CASE WHEN is_ldap THEN 'ldap' ELSE 'local' END WHERE auth_provider IS NULL OR auth_provider = ''"))
            if str(db.engine.url).startswith('postgresql'):
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE "user" ALTER COLUMN auth_provider TYPE VARCHAR(80)'))
                except Exception:
                    app.logger.exception('Unable to widen user.auth_provider to VARCHAR(80)')
                try:
                    unique_constraints = inspector.get_unique_constraints('user')
                    with db.engine.begin() as conn:
                        has_composite = False
                        for constraint in unique_constraints:
                            cols_for_constraint = constraint.get('column_names') or []
                            name = constraint.get('name')
                            if cols_for_constraint == ['username', 'auth_provider']:
                                has_composite = True
                            if name and cols_for_constraint == ['username']:
                                safe_name = name.replace('\"', '')
                                conn.execute(text(f'ALTER TABLE "user" DROP CONSTRAINT IF EXISTS "{safe_name}"'))
                        if not has_composite:
                            conn.execute(text('ALTER TABLE "user" ADD CONSTRAINT uq_user_username_auth_provider UNIQUE (username, auth_provider)'))
                    app.logger.info('Schema migration applied: user identity changed to username + auth_provider')
                except Exception:
                    app.logger.exception('Unable to migrate user unique constraint to username + auth_provider')
        if 'config_label' in tables:
            cols = {c['name'] for c in inspector.get_columns('config_label')}
            if 'description_required' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE config_label ADD COLUMN description_required BOOLEAN DEFAULT FALSE NOT NULL'))
                app.logger.info('Schema migration applied: config_label.description_required added')
            if 'description' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE config_label ADD COLUMN description TEXT'))
                    conn.execute(text("UPDATE config_label SET description = '' WHERE description IS NULL"))
                app.logger.info('Schema migration applied: config_label.description added')
            if 'max_completion_hours' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE config_label ADD COLUMN max_completion_hours INTEGER'))
                    conn.execute(text('UPDATE config_label SET max_completion_hours = 0 WHERE max_completion_hours IS NULL'))
                app.logger.info('Schema migration applied: config_label.max_completion_hours added')
            if 'max_completion_hours' in {c['name'] for c in inspector.get_columns('config_label')}:
                with db.engine.begin() as conn:
                    conn.execute(text('UPDATE config_label SET max_completion_hours = 0 WHERE max_completion_hours IS NULL'))

            if 'default_exportable' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE config_label ADD COLUMN default_exportable BOOLEAN'))
                    conn.execute(text('UPDATE config_label SET default_exportable = TRUE WHERE default_exportable IS NULL'))
                    conn.execute(text("UPDATE config_label SET default_exportable = FALSE WHERE kind = 'action_label' AND (lower(value) LIKE '%notifica%' OR lower(value) LIKE '%comunicazione%' OR lower(value) LIKE '%informazione iniziale%' OR lower(value) LIKE '%analisi%' OR lower(value) LIKE '%conclusione%')"))
                app.logger.info('Schema migration applied: config_label.default_exportable added')
            if 'default_exportable' in {c['name'] for c in inspector.get_columns('config_label')}:
                with db.engine.begin() as conn:
                    conn.execute(text('UPDATE config_label SET default_exportable = TRUE WHERE default_exportable IS NULL'))
            refreshed_config_label_cols = {c['name'] for c in inspector.get_columns('config_label')}
            if 'automatic_operations' not in refreshed_config_label_cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE config_label ADD COLUMN automatic_operations TEXT'))
                    conn.execute(text("UPDATE config_label SET automatic_operations = '' WHERE automatic_operations IS NULL"))
                    conn.execute(text("UPDATE config_label SET automatic_operations = 'close_without_warnings,end_breach' WHERE kind = 'action_label' AND lower(value) LIKE '%conclusione%' AND (automatic_operations IS NULL OR TRIM(automatic_operations) = '')"))
                app.logger.info('Schema migration applied: config_label.automatic_operations added')
            if 'automatic_operations' in {c['name'] for c in inspector.get_columns('config_label')}:
                with db.engine.begin() as conn:
                    conn.execute(text("UPDATE config_label SET automatic_operations = '' WHERE automatic_operations IS NULL"))
                    conn.execute(text("UPDATE config_label SET automatic_operations = 'close_without_warnings,end_breach' WHERE kind = 'action_label' AND lower(value) LIKE '%conclusione%' AND (automatic_operations IS NULL OR TRIM(automatic_operations) = '')"))

        if 'audit_log' in tables:
            cols = {c['name'] for c in inspector.get_columns('audit_log')}
            if 'repeat_count' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE audit_log ADD COLUMN repeat_count INTEGER'))
                    conn.execute(text('UPDATE audit_log SET repeat_count = 1 WHERE repeat_count IS NULL'))
                app.logger.info('Schema migration applied: audit_log.repeat_count added')
            if 'repeat_count' in {c['name'] for c in inspector.get_columns('audit_log')}:
                with db.engine.begin() as conn:
                    conn.execute(text('UPDATE audit_log SET repeat_count = 1 WHERE repeat_count IS NULL OR repeat_count < 1'))

        if 'deadline_notification_state' in tables:
            cols = {c['name'] for c in inspector.get_columns('deadline_notification_state')}
            expected_cols = {
                'notification_key': 'VARCHAR(255)',
                'notification_type': 'VARCHAR(80)',
                'incident_id': 'INTEGER',
                'last_success_at': 'TIMESTAMP',
                'last_schedule_slot': 'TIMESTAMP',
                'last_recipients': 'TEXT',
                'last_details': 'TEXT',
                'send_count': 'INTEGER',
                'updated_at': 'TIMESTAMP',
            }
            for col_name, col_type in expected_cols.items():
                if col_name not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE deadline_notification_state ADD COLUMN {col_name} {col_type}'))
                    app.logger.info('Schema migration applied: deadline_notification_state.%s added', col_name)
            with db.engine.begin() as conn:
                conn.execute(text("UPDATE deadline_notification_state SET notification_type = 'deadline' WHERE notification_type IS NULL"))
                conn.execute(text('UPDATE deadline_notification_state SET send_count = 1 WHERE send_count IS NULL OR send_count < 1'))

        if 'incident_workflow_step' in tables:
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'personal_data_only' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_workflow_step ADD COLUMN personal_data_only BOOLEAN'))
                    conn.execute(text('UPDATE incident_workflow_step SET personal_data_only = FALSE WHERE personal_data_only IS NULL'))
                app.logger.info('Schema migration applied: incident_workflow_step.personal_data_only added')
            elif 'personal_data_only' in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('UPDATE incident_workflow_step SET personal_data_only = FALSE WHERE personal_data_only IS NULL'))
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'requires_notification' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_workflow_step ADD COLUMN requires_notification BOOLEAN'))
                    conn.execute(text('UPDATE incident_workflow_step SET requires_notification = FALSE WHERE requires_notification IS NULL'))
                app.logger.info('Schema migration applied: incident_workflow_step.requires_notification added')
            else:
                with db.engine.begin() as conn:
                    conn.execute(text('UPDATE incident_workflow_step SET requires_notification = FALSE WHERE requires_notification IS NULL'))
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'required_notification_type' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_workflow_step ADD COLUMN required_notification_type VARCHAR(40)'))
                app.logger.info('Schema migration applied: incident_workflow_step.required_notification_type added')
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'required' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_workflow_step ADD COLUMN required BOOLEAN'))
                    conn.execute(text('UPDATE incident_workflow_step SET required = TRUE WHERE required IS NULL'))
                app.logger.info('Schema migration applied: incident_workflow_step.required added')
            else:
                with db.engine.begin() as conn:
                    conn.execute(text('UPDATE incident_workflow_step SET required = TRUE WHERE required IS NULL'))
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'conditions' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE incident_workflow_step ADD COLUMN conditions TEXT"))
                    conn.execute(text("UPDATE incident_workflow_step SET conditions = CASE WHEN personal_data_only THEN 'personal_data' ELSE '' END WHERE conditions IS NULL"))
                app.logger.info('Schema migration applied: incident_workflow_step.conditions added')
            else:
                with db.engine.begin() as conn:
                    conn.execute(text("UPDATE incident_workflow_step SET conditions = 'personal_data' WHERE personal_data_only = TRUE AND (conditions IS NULL OR conditions = '')"))
                    conn.execute(text("UPDATE incident_workflow_step SET conditions = '' WHERE conditions IS NULL"))
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'step_type' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE incident_workflow_step ADD COLUMN step_type VARCHAR(20) DEFAULT 'registration' NOT NULL"))
                    conn.execute(text("UPDATE incident_workflow_step SET step_type = 'registration' WHERE step_type IS NULL OR step_type = ''"))
                app.logger.info('Schema migration applied: incident_workflow_step.step_type added')
            else:
                with db.engine.begin() as conn:
                    conn.execute(text("UPDATE incident_workflow_step SET step_type = 'registration' WHERE step_type IS NULL OR step_type = ''"))
            with db.engine.begin() as conn:
                conn.execute(
                    text("UPDATE incident_workflow_step SET step_type = :new_code WHERE step_type = :legacy_code"),
                    {'new_code': 'update_section', 'legacy_code': _decode_legacy_refresh_token('73686f775f73656374696f6e')},
                )
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'document_generation_enabled' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_workflow_step ADD COLUMN document_generation_enabled BOOLEAN'))
                    conn.execute(text('UPDATE incident_workflow_step SET document_generation_enabled = FALSE WHERE document_generation_enabled IS NULL'))
                app.logger.info('Schema migration applied: incident_workflow_step.document_generation_enabled added')
            else:
                with db.engine.begin() as conn:
                    conn.execute(text('UPDATE incident_workflow_step SET document_generation_enabled = FALSE WHERE document_generation_enabled IS NULL'))
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'document_template_name' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_workflow_step ADD COLUMN document_template_name VARCHAR(255)'))
                app.logger.info('Schema migration applied: incident_workflow_step.document_template_name added')
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'document_auto_tags' in cols:
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE incident_workflow_step DROP COLUMN document_auto_tags'))
                    app.logger.info('Schema migration applied: incident_workflow_step.document_auto_tags removed')
                except Exception:
                    app.logger.info('Schema migration skipped: incident_workflow_step.document_auto_tags could not be dropped by this database backend')
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'section_target' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_workflow_step ADD COLUMN section_target VARCHAR(80)'))
                app.logger.info('Schema migration applied: incident_workflow_step.section_target added')
            cols = {c['name'] for c in inspector.get_columns('incident_workflow_step')}
            if 'control_action_label_ids' in cols:
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text('ALTER TABLE incident_workflow_step DROP COLUMN control_action_label_ids'))
                    app.logger.info('Schema migration applied: incident_workflow_step.control_action_label_ids removed')
                except Exception as exc:
                    app.logger.warning('Schema migration skipped: unable to drop obsolete incident_workflow_step.control_action_label_ids: %s', exc)
            with db.engine.begin() as conn:
                conn.execute(text("UPDATE incident_workflow_step SET required = FALSE WHERE category_id IS NULL AND action_label_id IN (SELECT id FROM config_label WHERE kind = 'action_label' AND lower(value) LIKE '%conclusione%')"))

        if 'incident_template' in tables:
            cols = {c['name'] for c in inspector.get_columns('incident_template')}
            if 'recipient_email' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident_template ADD COLUMN recipient_email VARCHAR(255)'))
                app.logger.info('Schema migration applied: incident_template.recipient_email added')

        if 'form_template_config' in tables:
            cols = {c['name'] for c in inspector.get_columns('form_template_config')}
            if 'notification_tags' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE form_template_config ADD COLUMN notification_tags TEXT NOT NULL DEFAULT ''"))
                app.logger.info('Schema migration applied: form_template_config.notification_tags added')

        if 'notification_template' in tables:
            cols = {c['name'] for c in inspector.get_columns('notification_template')}
            if 'action_label_id' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE notification_template ADD COLUMN action_label_id INTEGER'))
                app.logger.info('Schema migration applied: notification_template.action_label_id added')
            if 'linked_form_template_name' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE notification_template ADD COLUMN linked_form_template_name VARCHAR(255)'))
                app.logger.info('Schema migration applied: notification_template.linked_form_template_name added')
            template_cols = {c['name'] for c in inspector.get_columns('notification_template')}
            notification_template_new_cols = {
                'recipient_source': "VARCHAR(40) DEFAULT 'type_default' NOT NULL",
                'recipient_value': "VARCHAR(255) DEFAULT ''",
                'recipient_editable': 'BOOLEAN DEFAULT TRUE NOT NULL',
                'recipient_external_allowed': 'BOOLEAN DEFAULT TRUE NOT NULL',
                'cc_source': "VARCHAR(40) DEFAULT 'type_default' NOT NULL",
                'cc_value': "VARCHAR(255) DEFAULT ''",
                'cc_editable': 'BOOLEAN DEFAULT TRUE NOT NULL',
                'cc_external_allowed': 'BOOLEAN DEFAULT TRUE NOT NULL',
            }
            for col_name, col_type in notification_template_new_cols.items():
                if col_name not in template_cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE notification_template ADD COLUMN {col_name} {col_type}'))
                    app.logger.info('Schema migration applied: notification_template.%s added', col_name)
            with db.engine.begin() as conn:
                conn.execute(text("UPDATE notification_template SET recipient_source = 'type_default' WHERE recipient_source IS NULL OR recipient_source = ''"))
                conn.execute(text("UPDATE notification_template SET cc_source = 'type_default' WHERE cc_source IS NULL OR cc_source = ''"))
            # Migrazione semantica placeholder rischio diritti/libertà nei template manuali esistenti.
            # Le UPDATE sono idempotenti e non modificano i template già aggiornati.
            with db.engine.begin() as conn:
                conn.execute(text("UPDATE notification_template SET subject = replace(subject, '%PERSONAL_DATA%', '%RISK_RIGHTS_FREEDOM%'), body = replace(body, '%PERSONAL_DATA%', '%RISK_RIGHTS_FREEDOM%') WHERE subject LIKE '%PERSONAL_DATA%' OR body LIKE '%PERSONAL_DATA%'"))
                conn.execute(text("UPDATE notification_template SET subject = replace(subject, '%RECOMMENDATION%', '%RECOMMENDATIONS%'), body = replace(body, '%RECOMMENDATION%', '%RECOMMENDATIONS%') WHERE subject LIKE '%RECOMMENDATION%' OR body LIKE '%RECOMMENDATION%'"))
                conn.execute(text("UPDATE notification_template SET subject = replace(subject, 'Dati personali:', 'Rischi per diritti e libertà:'), body = replace(body, 'Dati personali:', 'Rischi per diritti e libertà:') WHERE subject LIKE '%Dati personali:%' OR body LIKE '%Dati personali:%'"))
        if 'document' in tables:
            cols = {c['name'] for c in inspector.get_columns('document')}
            if 'generated_template_name' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE document ADD COLUMN generated_template_name VARCHAR(255)'))
                app.logger.info('Schema migration applied: document.generated_template_name added')
            if 'notification_tags' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE document ADD COLUMN notification_tags TEXT NOT NULL DEFAULT ''"))
                app.logger.info('Schema migration applied: document.notification_tags added')
            cols = {c['name'] for c in inspector.get_columns('document')}
            document_extra_columns = {
                'alfresco_node_id': 'VARCHAR(255)',
                'alfresco_path': 'TEXT',
                'alfresco_uploaded_at': 'TIMESTAMP',
            }
            for col_name, col_type in document_extra_columns.items():
                if col_name not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE document ADD COLUMN {col_name} {col_type}'))
                    app.logger.info('Schema migration applied: document.%s added', col_name)
        if 'user' in tables:
            cols = {c['name'] for c in inspector.get_columns('user')}
            if 'mfa_enabled' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN mfa_enabled BOOLEAN DEFAULT FALSE NOT NULL'))
                app.logger.info('Schema migration applied: user.mfa_enabled added')

        if 'mfa_totp_token' in tables:
            cols = {c['name'] for c in inspector.get_columns('mfa_totp_token')}
            if 'verified_at' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE mfa_totp_token ADD COLUMN verified_at TIMESTAMP'))
                    conn.execute(text('UPDATE mfa_totp_token SET verified_at = created_at WHERE verified_at IS NULL'))
                app.logger.info('Schema migration applied: mfa_totp_token.verified_at added')
        # Le nuove tabelle vengono create da create_all(); questa sezione resta
        # intenzionalmente idempotente per database creati con versioni precedenti.
        if 'action_attachment' not in tables or 'recommendation' not in tables or 'incident_recommendations' not in tables or 'mfa_totp_token' not in tables or 'form_template_binary' not in tables or 'audit_log' not in tables or 'incident_reminder' not in tables or 'deadline_notification_state' not in tables or 'external_recipient' not in tables or 'incident_workflow_step' not in tables or 'incident_template' not in tables:
            db.create_all()
            app.logger.info('Schema migration applied: auxiliary tables ensured')

        if 'notification_type' in tables:
            cols = {c['name'] for c in inspector.get_columns('notification_type')}
            if 'description' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE notification_type ADD COLUMN description TEXT'))
                app.logger.info('Schema migration applied: notification_type.description added')
        if 'backup_job' not in tables:
            BackupJob.__table__.create(db.engine, checkfirst=True)
            app.logger.info('Schema migration applied: backup_job table created')

    except Exception:
        db.session.rollback()
        app.logger.exception('Schema migration failed')
        raise


def ensure_form_mapping(template_name, template_field, db_field):
    if not FormFieldMapping.query.filter_by(template_name=template_name, template_field=template_field).first():
        db.session.add(FormFieldMapping(template_name=template_name, template_field=template_field, db_field=db_field))


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

def ensure_notification_type(code, label, description='', recipient_mode='manual', recipient_setting_key='', cc_setting_key=''):
    description = (description or '').strip() or default_notification_type_description(label, code)
    # Destinatario e CC delle notifiche manuali sono configurati nei template.
    # I tipi predefiniti sono tenant-scoped sul tenant default: crearli come
    # righe globali (tenant_id NULL) o cercarli solo per code reintroduce il
    # vecchio vincolo globale su notification_type.code e rompe la clonazione
    # tra tenant.
    default_tenant_id = ensure_default_tenant().id
    t = NotificationType.query.filter_by(tenant_id=default_tenant_id, code=code).first()
    if not t:
        legacy = NotificationType.query.filter_by(tenant_id=None, code=code).first()
        if legacy and not NotificationType.query.filter_by(tenant_id=default_tenant_id, code=code).first():
            t = legacy
            t.tenant_id = default_tenant_id
    if not t:
        db.session.add(NotificationType(tenant_id=default_tenant_id, code=code,label=label,description=description,recipient_mode='manual',recipient_setting_key='',cc_setting_key='',enabled=True))
    else:
        t.label=label or t.label; t.description=description or t.description; t.recipient_mode='manual'; t.recipient_setting_key=''; t.cc_setting_key=''



def ensure_default_incident_workflow():
    """Create the editable default incident workflow on fresh installations.

    The function is tenant-aware: it only inspects and creates baseline steps
    for the default tenant, so cloning or creating another tenant never causes
    hidden/global workflow rows to appear in multiple tenants.
    """
    default_tenant = ensure_default_tenant()
    default_tenant_id = default_tenant.id
    if IncidentWorkflowStep.query.filter_by(tenant_id=default_tenant_id, category_id=None).first():
        return
    desired = [
        ('Informazione iniziale', 'informazione iniziale', False),
        ('Analisi', 'analisi', False),
        ('Notifica allo CSIRT', 'csirt', False),
        ('Notifica al DPO', 'dpo', False),
        ('Comunicazione al Garante', 'garante', True),
        ('Comunicazione all’utente', 'utente', False),
        ('Conclusione', 'conclusione', False),
    ]
    for idx, (caption, needle, personal_data_only) in enumerate(desired, start=1):
        label = ConfigLabel.query.filter(
            ConfigLabel.tenant_id == default_tenant_id,
            ConfigLabel.kind == 'action_label',
            ConfigLabel.value.ilike(f'%{needle}%')
        ).order_by(ConfigLabel.value).first()
        if not label:
            label = ConfigLabel(tenant_id=default_tenant_id, kind='action_label', value=caption, group='azioni', description=caption, default_exportable=False)
            db.session.add(label)
            db.session.flush()
        db.session.add(IncidentWorkflowStep(
            tenant_id=default_tenant_id,
            category_id=None,
            action_label_id=label.id,
            position=idx * 10,
            description='',
            personal_data_only=personal_data_only,
            required=('conclusione' not in (label.value or '').lower())
        ))

def ensure_default_workflow_required_steps():
    """Keep the editable default workflow aligned with mandatory baseline steps.

    Existing administrator customisations are preserved and the check is scoped
    to the default tenant only.
    """
    default_tenant_id = ensure_default_tenant().id
    default_steps = IncidentWorkflowStep.query.filter_by(tenant_id=default_tenant_id, category_id=None).all()
    if not default_steps:
        return
    existing_values = {((step.action_label.value or '').lower()) for step in default_steps if step.action_label}
    additions = [
        ('Comunicazione al Garante', 'garante', True),
        ('Comunicazione all’utente', 'utente', False),
    ]
    for step in default_steps:
        if step.action_label and 'garante' in (step.action_label.value or '').lower():
            step.personal_data_only = True
    conclusion = next((s for s in default_steps if s.action_label and 'conclusione' in s.action_label.value.lower()), None)
    if conclusion:
        conclusion.required = False
    base_pos = (conclusion.position if conclusion else max((s.position for s in default_steps), default=40) + 30)
    inserted = 0
    for caption, needle, personal_data_only in additions:
        if any(needle in value for value in existing_values):
            continue
        label = ConfigLabel.query.filter(
            ConfigLabel.tenant_id == default_tenant_id,
            ConfigLabel.kind == 'action_label',
            ConfigLabel.value.ilike(f'%{needle}%')
        ).order_by(ConfigLabel.value).first()
        if not label:
            label = ConfigLabel(tenant_id=default_tenant_id, kind='action_label', value=caption, group='azioni', description=caption, default_exportable=False)
            db.session.add(label)
            db.session.flush()
        db.session.add(IncidentWorkflowStep(
            tenant_id=default_tenant_id,
            category_id=None,
            action_label_id=label.id,
            position=base_pos - 20 + inserted * 10,
            description='',
            personal_data_only=personal_data_only
        ))
        inserted += 1
    if inserted and conclusion:
        conclusion.position = max(conclusion.position, base_pos + 10)

def repair_postgres_sequences(app):
    """Riallinea le sequenze PostgreSQL dopo import o migrazioni.

    Se dati con ID espliciti sono stati importati, le sequenze SERIAL possono
    restare indietro e il successivo INSERT automatico può generare:
    duplicate key value violates unique constraint.
    La funzione è idempotente e viene ignorata su database non PostgreSQL.
    """
    if not str(db.engine.url).startswith('postgresql'):
        return
    sequence_map = [
        # Ogni tabella applicativa con PK intera autoincrementale deve essere
        # riallineata.  Dopo un Full import i record vengono reinseriti con ID
        # espliciti: se una sola sequence resta indietro, il successivo INSERT
        # può fallire con "duplicate key value violates unique constraint".
        ('user', 'id'),
        ('audit_log', 'id'),
        ('mfa_totp_token', 'id'),
        ('config_label', 'id'),
        ('incident_workflow_step', 'id'),
        ('person', 'id'),
        ('recommendation', 'id'),
        ('incident', 'id'),
        ('incident_template', 'id'),
        ('incident_reminder', 'id'),
        ('action', 'id'),
        ('action_attachment', 'id'),
        ('document', 'id'),
        ('backup_job', 'id'),
        ('deadline_notification_state', 'id'),
        ('notification_type', 'id'),
        ('notification_template', 'id'),
        ('external_recipient', 'id'),
        ('form_template_config', 'id'),
        ('form_template_binary', 'id'),
        ('form_field_mapping', 'id'),
        ('ai_chatbot_document', 'id'),
    ]
    try:
        with db.engine.begin() as conn:
            metadata = MetaData()
            for table, column in sequence_map:
                reflected = Table(table, metadata, autoload_with=conn)
                max_value = conn.execute(select(func.max(reflected.c[column]))).scalar() or 0
                seq_name = conn.execute(
                    text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                    {"table_name": table, "column_name": column},
                ).scalar()
                if seq_name:
                    conn.execute(
                        text("SELECT setval(:seq_name, :next_value, false)"),
                        {"seq_name": seq_name, "next_value": max(int(max_value) + 1, 1)},
                    )
        app.logger.info('PostgreSQL sequences aligned successfully')

    except Exception:
        db.session.rollback()
        app.logger.exception('Unable to align PostgreSQL sequences')
        raise

def bootstrap(app):
    # Bootstrap protetto da advisory lock PostgreSQL non bloccante.
    # Con più worker Gunicorn, un pg_advisory_lock bloccante può lasciare il
    # container apparentemente avviato ma senza risposte HTTP. Qui proviamo il
    # lock per un tempo limitato e logghiamo chiaramente l'errore.
    lock_ok = False
    is_postgres = str(db.engine.url).startswith('postgresql')
    if is_postgres:
        for _ in range(60):
            try:
                lock_ok = bool(db.session.execute(text('SELECT pg_try_advisory_lock(7420171)')).scalar())
                db.session.commit()
                if lock_ok:
                    break
            except Exception:
                db.session.rollback()
                app.logger.exception('Unable to acquire PostgreSQL bootstrap advisory lock')
                break
            time.sleep(1)
        if not lock_ok:
            raise RuntimeError('Timeout waiting for PostgreSQL bootstrap advisory lock')
    try:
        db.create_all()
        run_schema_migrations(app)
        repair_postgres_sequences(app)
        default_tenant = ensure_default_tenant()
        database_already_populated = database_has_existing_operational_data()
        try:
            from .form_generation import restore_missing_template_files_from_db
            restore_missing_template_files_from_db()
        except Exception:
            app.logger.exception('Unable to restore PDF form templates from database')
        admin=User.query.filter_by(username='admin', auth_provider='local').first()
        if not admin:
            repair_postgres_sequences(app)
            initial_password = get_admin_initial_password() or secrets.token_urlsafe(18)
            if not get_admin_initial_password():
                app.logger.warning('ADMIN_INITIAL_PASSWORD non impostata: generata password iniziale temporanea per admin; impostarla esplicitamente prima del deploy.')
            admin=User(username='admin', name='Administrator', email=os.getenv('ADMIN_EMAIL','admin@example.local'), role='superuser', tenant_id=default_tenant.id, is_ldap=False, auth_provider='local', password_hash=hash_password(initial_password))
            db.session.add(admin)
        else:
            admin.role='superuser'; admin.tenant_id=admin.tenant_id or default_tenant.id; admin.is_ldap=False; admin.auth_provider='local'  # never reset password on restart
        db.session.flush()
        sync_user_tenant_roles()
        for k,v in {'security_owner_name':'','security_owner_role':'','security_owner_email':'','structure_name':'','security_responsible_name':'','security_responsible_email':'','security_responsible_phone':'-','security_responsible_function':'','ldap_uri':'','ldap_base_dn':'','ldap_bind_dn':'','ldap_bind_password':'','ldap_user_filter':'(uid={uid})','sso_profiles_json':'','sso_enabled':'0','sso_provider_name':'SSO','sso_authorization_url':'','sso_token_url':'','sso_userinfo_url':'','sso_client_id':'','sso_client_secret':'','sso_scopes':'openid email profile','sso_username_claim':'preferred_username','sso_email_claim':'email','sso_name_claim':'name','sso_subject_claim':'sub','sso_auto_create_users':'1','sso_default_role':'disabled','logo_path':'','smtp_host':'','smtp_port':'587','smtp_use_tls':'1','smtp_use_ssl':'0','smtp_auth_enabled':'0','smtp_username':'','smtp_password':'','smtp_default_sender':'','notification_deadline_enabled':'0','notification_deadline_email_enabled':'1','notification_deadline_schedule_mode':'interval','notification_deadline_cron_times':'','notification_deadline_interval_hours':'24','notification_deadline_interval_minutes':'0','notification_deadline_poll_seconds':'60','notification_incident_reminder_poll_seconds':'60','privacy_authority_non_notification_reason':'','documentation_location':'','application_external_url':'http://localhost:8000','application_timezone':'Europe/Rome','interface_language':'auto','audit_retention_months':'6','audit_retention_months_part':'6','audit_retention_days_part':'0','audit_retention_hours_part':'0','audit_retention_minutes_part':'0','audit_records_per_page':'20','audit_max_records':'10000','plugin_ai_chatbot_enabled':'0','ai_chatbot_engine':'chatgpt','ai_chatbot_include_database_context':'0','ai_chatbot_chatgpt_api_key':'','ai_chatbot_chatgpt_endpoint':'','ai_chatbot_chatgpt_model':'gpt-4o-mini','ai_chatbot_claude_api_key':'','ai_chatbot_claude_endpoint':'','ai_chatbot_claude_model':'claude-3-5-sonnet-latest','ai_chatbot_gemini_api_key':'','ai_chatbot_gemini_endpoint':'','ai_chatbot_gemini_model':'gemini-1.5-flash','ai_chatbot_ollama_api_key':'','ai_chatbot_ollama_endpoint':'http://localhost:11434/api/chat','ai_chatbot_ollama_model':'llama3.1','ai_chatbot_perplexity_api_key':'','ai_chatbot_perplexity_endpoint':'','ai_chatbot_perplexity_model':'sonar','recommendations_max_per_incident':'3','ssl_enabled':'0','notification_csirt_subject':'Notifica CSIRT - Incidente: {name}','notification_dpo_subject':'Notifica DPO - Incidente: {name}','notification_csirt_body':'Buongiorno,\nsi invia notifica relativa al seguente incidente informatico.\n\nDati interessati: %DATI%\nCategorie: %CATEGORIE%\nData di inizio: %DATA%\nRischio per diritti e libertà: %DATI_PERSONALI%\n\nReport aggiornato: %REPORT%\n\nCordiali saluti','notification_dpo_body':'Buongiorno,\nsi invia notifica al DPO relativa al seguente incidente informatico.\n\nDati interessati: %DATI%\nCategorie: %CATEGORIE%\nData di inizio: %DATA%\nRischio per diritti e libertà: %DATI_PERSONALI%\n\nReport aggiornato: %REPORT%\n\nCordiali saluti','workflow_step_type_registration_description':'Premi per registrare','workflow_step_type_execution_description':'Premi per eseguire','workflow_step_type_update_section_description':'Aggiorna dati','workflow_step_type_operation_description':'Effettua operazione','workflow_step_types_json':''}.items(): ensure_setting(k,v)
        normalize_update_section_persistent_values()
        for k,v in default_consequence_settings().items(): ensure_setting(k,v)
        if not database_already_populated:
            restore_missing_default_config_labels()
        else:
            app.logger.info('Database già popolato: bootstrap label configurabili predefinite saltato. Usare il pulsante Admin per reinserire solo i default mancanti.')
        ensure_default_incident_workflow()
        ensure_default_workflow_required_steps()
        ensure_notification_type('user','Notifica utente','Notifiche formali ad utenti a seguito di gravi violazioni su diritti e libertà','manual','','')
        ensure_notification_type('csirt','Notifica CSIRT','Notifiche destinate allo CSIRT.','manual','','')
        ensure_notification_type('dpo','Notifica DPO','Notifiche destinate al DPO.','manual','','')
        for _nt in NotificationType.query.all():
            if not (_nt.description or '').strip():
                _nt.description = default_notification_type_description(_nt.label, _nt.code)

        # Mapping iniziale solo per il template di esempio.
        # I vecchi template predefiniti art. 33/art. 34 sono stati rimossi; i template
        # operativi devono essere caricati o creati dall'utente dal menu Moduli.
        FormFieldMapping.query.filter(FormFieldMapping.template_name.in_(['comunicazione_data_breach_art34', 'notifica_interna_data_breach_art33'])).delete(synchronize_session=False)
        default_form_mappings = {
            'esempio-notifica': {
                'input_data_name': 'name',
                'input_data_reference': 'reference',
                'input_data_recipient': 'recipient',
                'input_data_status': 'status',
                'input_data_start': 'start_at',
                'input_data_categories': 'categories',
                'input_data_data_types': 'data_types',
                'input_data_description': 'description',
                'input_data_actions': 'actions',
            },
        }
        for template_name, mapping in default_form_mappings.items():
            for template_field, db_field in mapping.items():
                ensure_form_mapping(template_name, template_field, db_field)
        if BackupJob.query.count() == 0:
            db.session.add(BackupJob(tenant_id=default_tenant.id, name='Backup schedulato principale', enabled=False, cron_expression='0 2 * * *', categories='incidents,database,templates,logos,uploads', destination='local', local_path=os.getenv('BACKUP_DIR','/data/backups')))
        db.session.flush()
        assign_default_tenant_to_unscoped(default_tenant)
        db.session.commit()

    except Exception:
        db.session.rollback(); app.logger.exception('Bootstrap failed'); raise
    finally:
        if lock_ok:
            try: db.session.execute(text('SELECT pg_advisory_unlock(7420171)')); db.session.commit()
            except Exception: db.session.rollback()
