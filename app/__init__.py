import os, time, shutil
from flask import Flask
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError
from .models import db, User, ConfigLabel, Setting, NotificationType, FormFieldMapping, FormTemplateConfig, FormTemplateBinary, AuditLog, IncidentReminder
from .auth import login_manager, hash_password

def create_app():
    app=Flask(__name__)
    app.config['SECRET_KEY']=os.getenv('SECRET_KEY','dev-change-me')
    app.config['SQLALCHEMY_DATABASE_URI']=os.getenv('DATABASE_URL','sqlite:////tmp/cir.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
    app.config['UPLOAD_DIR']=os.getenv('UPLOAD_DIR','/tmp/cir_uploads')
    app.config['LOGO_DIR']=os.getenv('LOGO_DIR','/tmp/cir_logo')
    app.config['FORM_TEMPLATE_DIR']=os.getenv('FORM_TEMPLATE_DIR','/data/form_templates')
    app.config['APP_INFO']={
        'name': os.getenv('APP_NAME','Cybersecurity Incident Registry'),
        'version': os.getenv('APP_VERSION','0.2.0'),
        'build': os.getenv('APP_BUILD','2026051801'),
        'author': os.getenv('APP_AUTHOR','Alessandro De Salvo'),
        'author_email': os.getenv('APP_AUTHOR_EMAIL','Alessandro.DeSalvo@roma1.infn.it'),
    }
    os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True); os.makedirs(app.config['LOGO_DIR'], exist_ok=True); os.makedirs(app.config['FORM_TEMPLATE_DIR'], exist_ok=True)

    # Copia i template PDF di esempio nella directory persistente solo se non esistono.
    packaged_templates = os.path.join(os.path.dirname(__file__), 'form_templates')
    if os.path.isdir(packaged_templates):
        for name in os.listdir(packaged_templates):
            if name.endswith('.pdf'):
                src = os.path.join(packaged_templates, name)
                dst = os.path.join(app.config['FORM_TEMPLATE_DIR'], name)
                if not os.path.exists(dst):
                    shutil.copyfile(src, dst)


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
            if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'role', None) == 'admin':
                data['notification_menu_types'] = NotificationType.query.filter_by(enabled=True).order_by(NotificationType.label).all()
            else:
                data['notification_menu_types'] = []
        except Exception:
            data['notification_menu_types'] = []
        try:
            from flask_login import current_user
            data['modules_menu_visible'] = bool(getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'role', None) == 'admin')
        except Exception:
            data['modules_menu_visible'] = False
        return data
    from .routes import bp, start_deadline_notification_scheduler; app.register_blueprint(bp)
    with app.app_context():
        wait_db(db)
        bootstrap(app)
    start_deadline_notification_scheduler(app)
    return app

def wait_db(db):
    last=None
    for _ in range(30):
        try:
            db.session.execute(text('SELECT 1')); db.session.commit(); return
        except OperationalError as e:
            last=e; db.session.rollback(); time.sleep(2)
    raise last

def ensure_setting(key, value):
    s=Setting.query.get(key)
    if not s:
        db.session.add(Setting(key=key,value=value))

def ensure_label(kind, value, group='default'):
    label = ConfigLabel.query.filter_by(kind=kind,value=value).first()
    default_exportable = True
    if kind == 'action_label':
        text = (value or '').lower().replace('’', "'")
        default_exportable = not any(k in text for k in ('notifica','comunicazione','informazione iniziale','analisi','conclusione'))
    if not label:
        db.session.add(ConfigLabel(kind=kind,value=value,group=group,default_exportable=default_exportable))
    elif kind == 'action_label' and getattr(label, 'default_exportable', None) is None:
        label.default_exportable = default_exportable



def run_schema_migrations(app):
    """Migrazioni leggere e idempotenti eseguite all'avvio.

    Mantengono riutilizzabile il database tra versioni successive senza
    cancellare dati. In particolare aggiungono colonne nuove quando un
    database esistente ha uno schema precedente.
    """
    try:
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        if 'incident' in tables:
            cols = {c['name'] for c in inspector.get_columns('incident')}
            for col_name, col_type in {'data_subjects_count':'VARCHAR(255)', 'data_volume':'TEXT'}.items():
                if col_name not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE incident ADD COLUMN {col_name} {col_type}'))
                    app.logger.info('Schema migration applied: incident.%s added', col_name)
            if 'reference' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident ADD COLUMN reference VARCHAR(255)'))
                app.logger.info('Schema migration applied: incident.reference added')
            if 'recipient' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident ADD COLUMN recipient VARCHAR(255)'))
                app.logger.info('Schema migration applied: incident.recipient added')
            if 'deadline_notifications_muted' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE incident ADD COLUMN deadline_notifications_muted BOOLEAN'))
                    conn.execute(text('UPDATE incident SET deadline_notifications_muted = FALSE WHERE deadline_notifications_muted IS NULL'))
                app.logger.info('Schema migration applied: incident.deadline_notifications_muted added')
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
            if 'auth_provider' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN auth_provider VARCHAR(40)"))
                    conn.execute(text("UPDATE \"user\" SET auth_provider = CASE WHEN is_ldap THEN 'ldap' ELSE 'local' END WHERE auth_provider IS NULL"))
                app.logger.info('Schema migration applied: user.auth_provider added')
            if 'external_id' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN external_id VARCHAR(255)"))
                app.logger.info('Schema migration applied: user.external_id added')
        if 'config_label' in tables:
            cols = {c['name'] for c in inspector.get_columns('config_label')}
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
        if 'notification_template' in tables:
            cols = {c['name'] for c in inspector.get_columns('notification_template')}
            if 'action_label_id' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE notification_template ADD COLUMN action_label_id INTEGER'))
                app.logger.info('Schema migration applied: notification_template.action_label_id added')
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
        if 'action_attachment' not in tables or 'recommendation' not in tables or 'incident_recommendations' not in tables or 'mfa_totp_token' not in tables or 'form_template_binary' not in tables or 'audit_log' not in tables or 'incident_reminder' not in tables or 'deadline_notification_state' not in tables:
            db.create_all()
            app.logger.info('Schema migration applied: auxiliary tables ensured')
    except Exception:
        db.session.rollback()
        app.logger.exception('Schema migration failed')
        raise


def ensure_form_mapping(template_name, template_field, db_field):
    if not FormFieldMapping.query.filter_by(template_name=template_name, template_field=template_field).first():
        db.session.add(FormFieldMapping(template_name=template_name, template_field=template_field, db_field=db_field))

def ensure_notification_type(code, label, description='', recipient_mode='manual', recipient_setting_key='', cc_setting_key=''):
    t=NotificationType.query.filter_by(code=code).first()
    if not t:
        db.session.add(NotificationType(code=code,label=label,description=description,recipient_mode=recipient_mode,recipient_setting_key=recipient_setting_key,cc_setting_key=cc_setting_key,enabled=True))
    else:
        t.label=label or t.label; t.description=description or t.description; t.recipient_mode=recipient_mode; t.recipient_setting_key=recipient_setting_key; t.cc_setting_key=cc_setting_key


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
        ('user', 'id'),
        ('config_label', 'id'),
        ('person', 'id'),
        ('incident', 'id'),
        ('action', 'id'),
        ('action_attachment', 'id'),
        ('document', 'id'),
        ('notification_type', 'id'),
        ('notification_template', 'id'),
        ('form_field_mapping', 'id'),
        ('form_template_config', 'id'),
        ('recommendation', 'id'),
        ('mfa_totp_token', 'id'),
        ('audit_log', 'id'),
        ('incident_reminder', 'id'),
    ]
    try:
        with db.engine.begin() as conn:
            for table, column in sequence_map:
                quoted_table = f'"{table}"'
                seq_table_arg = quoted_table
                conn.execute(text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{seq_table_arg}', '{column}'),
                        COALESCE((SELECT MAX({column}) FROM {quoted_table}), 0) + 1,
                        false
                    )
                    """
                ))
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
        try:
            from .form_generation import restore_missing_template_files_from_db
            restore_missing_template_files_from_db()
        except Exception:
            app.logger.exception('Unable to restore PDF form templates from database')
        admin=User.query.filter_by(username='admin').first()
        if not admin:
            admin=User(username='admin', name='Administrator', email=os.getenv('ADMIN_EMAIL','admin@example.local'), role='admin', is_ldap=False, password_hash=hash_password(os.getenv('ADMIN_INITIAL_PASSWORD','adminpass')))
            db.session.add(admin)
        else:
            admin.role='admin'; admin.is_ldap=False; admin.auth_provider='local'  # never reset password on restart
        for k,v in {'security_owner_name':'','security_owner_role':'','structure_name':'','security_responsible_name':'','security_responsible_email':'','security_responsible_phone':'-','security_responsible_function':'','ldap_uri':'','ldap_base_dn':'','ldap_bind_dn':'','ldap_bind_password':'','ldap_user_filter':'(uid={uid})','sso_profiles_json':'','sso_enabled':'0','sso_provider_name':'SSO','sso_authorization_url':'','sso_token_url':'','sso_userinfo_url':'','sso_client_id':'','sso_client_secret':'','sso_scopes':'openid email profile','sso_username_claim':'preferred_username','sso_email_claim':'email','sso_name_claim':'name','sso_subject_claim':'sub','sso_auto_create_users':'1','sso_default_role':'disabled','logo_path':'','csirt_email':'','dpo_email':'','csirt_cc':'','dpo_cc':'','smtp_host':'','smtp_port':'587','smtp_use_tls':'1','smtp_use_ssl':'0','smtp_auth_enabled':'0','smtp_username':'','smtp_password':'','smtp_default_sender':'','notification_deadline_enabled':'0','notification_deadline_email_enabled':'1','notification_deadline_schedule_mode':'interval','notification_deadline_cron_times':'','notification_deadline_interval_hours':'24','notification_deadline_interval_minutes':'0','privacy_authority_non_notification_reason':'','documentation_location':'','application_external_url':'http://localhost:8000','application_timezone':'Europe/Rome','interface_language':'auto','audit_retention_months':'6','audit_retention_months_part':'6','audit_retention_days_part':'0','audit_retention_hours_part':'0','audit_retention_minutes_part':'0','audit_records_per_page':'20','audit_max_records':'10000','recommendations_max_per_incident':'3','ssl_enabled':'0','notification_csirt_subject':'Notifica CSIRT - Incidente: {name}','notification_dpo_subject':'Notifica DPO - Incidente: {name}','notification_csirt_body':'Buongiorno,\nsi invia notifica relativa al seguente incidente informatico.\n\nDati interessati: %DATI%\nCategorie: %CATEGORIE%\nData di inizio: %DATA%\nDati personali: %DATI_PERSONALI%\n\nReport aggiornato: %REPORT%\n\nCordiali saluti','notification_dpo_body':'Buongiorno,\nsi invia notifica al DPO relativa al seguente incidente informatico.\n\nDati interessati: %DATI%\nCategorie: %CATEGORIE%\nData di inizio: %DATA%\nDati personali: %DATI_PERSONALI%\n\nReport aggiornato: %REPORT%\n\nCordiali saluti'}.items(): ensure_setting(k,v)
        for v in ['molto bassa','bassa','media','alta','critica']: ensure_label('severity',v,'gravità')
        for v in ['password','dati personali']: ensure_label('data_type',v,'dati interessati')
        for v in ['furto di credenziali','phishing','SPAM','altro']: ensure_label('category',v,'categorie')
        for v in ['01-informazione iniziale','02-analisi','03-blocco','04-comunicazione allo CSIRT','05-comunicazione al DPO','06-comunicazione al Garante della Privacy','07-notifica all’utente','08-conclusione']: ensure_label('action_label',v,'azioni')
        ensure_notification_type('user','Notifica utente','Notifica generica a un destinatario specificato in fase di invio','manual','','')
        ensure_notification_type('csirt','Notifica CSIRT','Notifica allo CSIRT usando il destinatario configurato nelle impostazioni','settings','csirt_email','csirt_cc')
        ensure_notification_type('dpo','Notifica DPO','Notifica al DPO usando il destinatario configurato nelle impostazioni','settings','dpo_email','dpo_cc')

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
        db.session.commit()
    except Exception:
        db.session.rollback(); app.logger.exception('Bootstrap failed'); raise
    finally:
        if lock_ok:
            try: db.session.execute(text('SELECT pg_advisory_unlock(7420171)')); db.session.commit()
            except Exception: db.session.rollback()
