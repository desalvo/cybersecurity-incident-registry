from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db=SQLAlchemy()
incident_people=db.Table('incident_people', db.Column('incident_id',db.Integer,db.ForeignKey('incident.id'),primary_key=True), db.Column('person_id',db.Integer,db.ForeignKey('person.id'),primary_key=True))
incident_categories=db.Table('incident_categories', db.Column('incident_id',db.Integer,db.ForeignKey('incident.id'),primary_key=True), db.Column('label_id',db.Integer,db.ForeignKey('config_label.id'),primary_key=True))
incident_data_types=db.Table('incident_data_types', db.Column('incident_id',db.Integer,db.ForeignKey('incident.id'),primary_key=True), db.Column('label_id',db.Integer,db.ForeignKey('config_label.id'),primary_key=True))
incident_recommendations=db.Table('incident_recommendations', db.Column('incident_id',db.Integer,db.ForeignKey('incident.id'),primary_key=True), db.Column('recommendation_id',db.Integer,db.ForeignKey('recommendation.id'),primary_key=True))
class Setting(db.Model): key=db.Column(db.String(100),primary_key=True); value=db.Column(db.Text,default='')


class AuditLog(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    occurred_at=db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    operation_type=db.Column(db.String(120), nullable=False, index=True)
    username=db.Column(db.String(160), nullable=False, default='system', index=True)
    user_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    actor_type=db.Column(db.String(40), nullable=False, default='user')
    details=db.Column(db.Text, default='')
    repeat_count=db.Column(db.Integer, nullable=False, default=1)
    user=db.relationship('User', foreign_keys=[user_id])

class User(UserMixin,db.Model):
    id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),nullable=False,index=True); password_hash=db.Column(db.String(255)); name=db.Column(db.String(160)); email=db.Column(db.String(255)); role=db.Column(db.String(20),default='disabled'); is_ldap=db.Column(db.Boolean,default=False); auth_provider=db.Column(db.String(80),default='local',nullable=False,index=True); external_id=db.Column(db.String(255),nullable=True,index=True); mfa_enabled=db.Column(db.Boolean,default=False,nullable=False)
    __table_args__=(db.UniqueConstraint('username','auth_provider',name='uq_user_username_auth_provider'),)
    mfa_tokens=db.relationship('MfaTotpToken',back_populates='user',cascade='all,delete-orphan')

    @property
    def backend_label(self):
        provider = self.auth_provider or ('ldap' if self.is_ldap else 'local')
        return provider

class MfaTotpToken(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False,index=True)
    name=db.Column(db.String(160),nullable=False,default='Token TOTP')
    secret=db.Column(db.String(64),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    last_used_at=db.Column(db.DateTime,nullable=True)
    verified_at=db.Column(db.DateTime,nullable=True)
    user=db.relationship('User',back_populates='mfa_tokens')

class ConfigLabel(db.Model):
    id=db.Column(db.Integer,primary_key=True); kind=db.Column(db.String(40),nullable=False,index=True); group=db.Column(db.String(80),default='default'); value=db.Column(db.String(255),nullable=False); description=db.Column(db.Text,default=''); max_completion_hours=db.Column(db.Integer,nullable=False,default=0); default_exportable=db.Column(db.Boolean,default=True,nullable=False); automatic_operations=db.Column(db.Text,default=''); __table_args__=(db.UniqueConstraint('kind','value',name='uq_label_kind_value'),)

    def automatic_operation_list(self):
        values=[]
        for item in (self.automatic_operations or '').split(','):
            item=(item or '').strip()
            if item and item not in values:
                values.append(item)
        return values

    def has_automatic_operation(self, code):
        return (code or '').strip() in self.automatic_operation_list()

class IncidentWorkflowStep(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    category_id=db.Column(db.Integer,db.ForeignKey('config_label.id'),nullable=True,index=True)
    action_label_id=db.Column(db.Integer,db.ForeignKey('config_label.id'),nullable=False,index=True)
    position=db.Column(db.Integer,nullable=False,default=0,index=True)
    description=db.Column(db.Text,default='')
    personal_data_only=db.Column(db.Boolean,default=False,nullable=False)
    required=db.Column(db.Boolean,default=True,nullable=False)
    requires_notification=db.Column(db.Boolean,default=False,nullable=False)
    required_notification_type=db.Column(db.String(40),nullable=True,index=True)
    conditions=db.Column(db.Text,default='')
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    category=db.relationship('ConfigLabel',foreign_keys=[category_id])
    action_label=db.relationship('ConfigLabel',foreign_keys=[action_label_id])

    def condition_tokens(self):
        values=[]
        for item in (self.conditions or '').split(','):
            item=(item or '').strip()
            if item and item not in values:
                values.append(item)
        # Compatibilita' con il vecchio flag: gli step gia' marcati
        # "solo rischio per diritti e libertà" continuano a comportarsi come prima.
        if getattr(self, 'personal_data_only', False) and 'personal_data' not in values:
            values.insert(0, 'personal_data')
        return values

    def set_condition_tokens(self, tokens):
        cleaned=[]
        for item in tokens or []:
            item=(item or '').strip()
            if item and item not in cleaned:
                cleaned.append(item)
        self.conditions=','.join(cleaned)
        self.personal_data_only=('personal_data' in cleaned)


class Person(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(160),unique=True,nullable=False); email=db.Column(db.String(255)); group=db.Column(db.String(80),default='personale')
class Recommendation(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    text=db.Column(db.Text,unique=True,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)

class Incident(db.Model):
    id=db.Column(db.Integer,primary_key=True); creator_id=db.Column(db.Integer,db.ForeignKey('user.id')); creator_name=db.Column(db.String(160)); creator_email=db.Column(db.String(255)); name=db.Column(db.String(255),nullable=False); reference=db.Column(db.String(255),nullable=False,default=''); recipient=db.Column(db.String(255),nullable=True); recipient_email=db.Column(db.String(255),nullable=True); description=db.Column(db.Text); severity_id=db.Column(db.Integer,db.ForeignKey('config_label.id')); personal_data=db.Column(db.Boolean,default=False); data_subjects_count=db.Column(db.String(255)); data_volume=db.Column(db.Text); start_date=db.Column(db.Date); start_time=db.Column(db.Time); end_date=db.Column(db.Date); end_time=db.Column(db.Time); status=db.Column(db.String(40),default='aperto'); deadline_notifications_muted=db.Column(db.Boolean,default=False,nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow)

    @property
    def start_at(self):
        if self.start_date:
            from datetime import datetime, time
            return datetime.combine(self.start_date, self.start_time or time())
        return None

    @start_at.setter
    def start_at(self, value):
        if value is None:
            self.start_date = None; self.start_time = None
        else:
            self.start_date = value.date(); self.start_time = value.time().replace(second=0, microsecond=0)

    @property
    def end_at(self):
        if self.end_date:
            from datetime import datetime, time
            return datetime.combine(self.end_date, self.end_time or time())
        return None

    @end_at.setter
    def end_at(self, value):
        if value is None:
            self.end_date = None; self.end_time = None
        else:
            self.end_date = value.date(); self.end_time = value.time().replace(second=0, microsecond=0)

    @property
    def first_action_at(self):
        values = [a.when_at for a in (self.actions or []) if getattr(a, 'when_at', None)]
        return min(values) if values else None

    @property
    def effective_duration(self):
        """Durata operativa dell'incidente.

        La durata è calcolata solo sul tempo intercorso tra la prima azione
        registrata e la conclusione dell'incidente (`end_at`). I campi di
        inizio incidente non entrano più nel computo. Se manca la prima azione
        o la conclusione, la durata non è disponibile.
        """
        first = self.first_action_at
        end = self.end_at
        if not first or not end:
            return None
        if end < first:
            return None
        return end - first

    @property
    def effective_duration_seconds(self):
        value = self.effective_duration
        return value.total_seconds() if value is not None else None

    creator=db.relationship(User); severity=db.relationship(ConfigLabel,foreign_keys=[severity_id]); categories=db.relationship(ConfigLabel,secondary=incident_categories); data_types=db.relationship(ConfigLabel,secondary=incident_data_types); people=db.relationship(Person,secondary=incident_people); recommendations=db.relationship(Recommendation,secondary=incident_recommendations); actions=db.relationship('Action',cascade='all,delete-orphan',order_by='Action.when_at'); documents=db.relationship('Document',cascade='all,delete-orphan'); reminders=db.relationship('IncidentReminder',cascade='all,delete-orphan',order_by='IncidentReminder.scheduled_at',back_populates='incident'); deadline_notification_states=db.relationship('DeadlineNotificationState',cascade='all,delete-orphan',back_populates='incident')



class IncidentTemplate(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(160),nullable=False,unique=True,index=True)
    description=db.Column(db.Text,default='')
    incident_name=db.Column(db.String(255),default='')
    reference=db.Column(db.String(255),nullable=True)
    recipient=db.Column(db.String(255),nullable=True)
    recipient_email=db.Column(db.String(255),nullable=True)
    incident_description=db.Column(db.Text,default='')
    severity_id=db.Column(db.Integer,db.ForeignKey('config_label.id'),nullable=True)
    personal_data=db.Column(db.Boolean,default=False,nullable=False)
    data_subjects_count=db.Column(db.String(255),nullable=True)
    data_volume=db.Column(db.Text,nullable=True)
    status=db.Column(db.String(40),default='aperto')
    category_ids=db.Column(db.Text,default='')
    data_type_ids=db.Column(db.Text,default='')
    people_ids=db.Column(db.Text,default='')
    recommendation_ids=db.Column(db.Text,default='')
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    updated_at=db.Column(db.DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    severity=db.relationship('ConfigLabel',foreign_keys=[severity_id])

    def _ids(self, field):
        values=[]
        for item in (getattr(self, field) or '').split(','):
            try:
                values.append(int(item.strip()))
            except (TypeError, ValueError):
                pass
        return values
    def category_id_list(self): return self._ids('category_ids')
    def data_type_id_list(self): return self._ids('data_type_ids')
    def people_id_list(self): return self._ids('people_ids')
    def recommendation_id_list(self): return self._ids('recommendation_ids')

class IncidentReminder(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    incident_id=db.Column(db.Integer,db.ForeignKey('incident.id'),nullable=False,index=True)
    scheduled_at=db.Column(db.DateTime,nullable=False,index=True)
    message=db.Column(db.Text,nullable=False,default='')
    cc_emails=db.Column(db.Text,default='')
    sent_at=db.Column(db.DateTime,nullable=True,index=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow,nullable=False)
    updated_at=db.Column(db.DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,nullable=False)
    created_by_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=True)
    created_by_name=db.Column(db.String(160),default='')
    last_error=db.Column(db.Text,default='')
    incident=db.relationship('Incident',back_populates='reminders')
    created_by=db.relationship('User',foreign_keys=[created_by_id])

class Action(db.Model):
    id=db.Column(db.Integer,primary_key=True); incident_id=db.Column(db.Integer,db.ForeignKey('incident.id')); when_at=db.Column(db.DateTime,nullable=False); person_name=db.Column(db.String(160)); description=db.Column(db.Text,nullable=True); consequence_text=db.Column(db.Text,nullable=True); label_id=db.Column(db.Integer,db.ForeignKey('config_label.id')); exportable=db.Column(db.Boolean,default=True,nullable=False); label=db.relationship(ConfigLabel); attachments=db.relationship('ActionAttachment',cascade='all,delete-orphan')

    @property
    def action_at(self):
        """Alias compatibile con versioni precedenti del codice/template.

        Il modello usa il campo persistente ``when_at``; alcune parti del
        modulo notifiche introdotte in versioni intermedie facevano riferimento
        a ``action_at`` causando AttributeError. Manteniamo l'alias per
        compatibilità senza aggiungere una seconda colonna.
        """
        return self.when_at

    @action_at.setter
    def action_at(self, value):
        self.when_at = value
class ActionAttachment(db.Model):
    id=db.Column(db.Integer,primary_key=True); action_id=db.Column(db.Integer,db.ForeignKey('action.id'),nullable=False,index=True); filename=db.Column(db.String(255),nullable=False); stored_name=db.Column(db.String(255),nullable=False); uploaded_at=db.Column(db.DateTime,default=datetime.utcnow)
class Document(db.Model):
    id=db.Column(db.Integer,primary_key=True); incident_id=db.Column(db.Integer,db.ForeignKey('incident.id')); filename=db.Column(db.String(255)); stored_name=db.Column(db.String(255)); uploaded_at=db.Column(db.DateTime,default=datetime.utcnow); generated_template_name=db.Column(db.String(255),nullable=True,index=True); notification_tags=db.Column(db.Text,default='',nullable=False)

    @property
    def notification_tag_list(self):
        raw = self.notification_tags or ''
        return [x.strip() for x in raw.split(',') if x.strip()]

    def set_notification_tags(self, values):
        seen = []
        for value in values or []:
            code = str(value or '').strip()
            if code and code not in seen:
                seen.append(code)
        self.notification_tags = ','.join(seen)




class BackupJob(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(160),nullable=False,default='Backup schedulato')
    enabled=db.Column(db.Boolean,default=False,nullable=False)
    cron_expression=db.Column(db.String(120),default='0 2 * * *')
    categories=db.Column(db.Text,default='incidents,database,templates,logos,uploads')
    destination=db.Column(db.String(40),default='local')
    local_path=db.Column(db.String(500),default='/data/backups')
    s3_endpoint_url=db.Column(db.String(500),default='')
    s3_bucket=db.Column(db.String(255),default='')
    s3_prefix=db.Column(db.String(255),default='cybersecurity-incident-registry')
    s3_access_key=db.Column(db.String(255),default='')
    s3_secret_key=db.Column(db.String(255),default='')
    notify_admin=db.Column(db.Boolean,default=False,nullable=False)
    last_run_at=db.Column(db.DateTime,nullable=True)
    last_status=db.Column(db.String(40),default='never')
    last_message=db.Column(db.Text,default='')
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    updated_at=db.Column(db.DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)

    def category_list(self):
        return [x.strip() for x in (self.categories or '').split(',') if x.strip()]

class DeadlineNotificationState(db.Model):
    """Stato dell'ultimo invio riuscito delle notifiche task in scadenza.

    Evita reinvii multipli della stessa tipologia di notifica all'interno
    dell'intervallo tra due slot pianificati, anche se lo scheduler effettua
    poll ripetuti o l'applicazione viene riavviata.
    """
    id=db.Column(db.Integer,primary_key=True)
    notification_key=db.Column(db.String(255),unique=True,nullable=False,index=True)
    notification_type=db.Column(db.String(80),nullable=False,default='deadline')
    incident_id=db.Column(db.Integer,db.ForeignKey('incident.id', ondelete='CASCADE'),nullable=True,index=True)
    last_success_at=db.Column(db.DateTime,nullable=False,index=True)
    last_schedule_slot=db.Column(db.DateTime,nullable=True,index=True)
    last_recipients=db.Column(db.Text,default='')
    last_details=db.Column(db.Text,default='')
    send_count=db.Column(db.Integer,nullable=False,default=1)
    updated_at=db.Column(db.DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,nullable=False)
    incident=db.relationship('Incident',foreign_keys=[incident_id],back_populates='deadline_notification_states')


class NotificationType(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    code=db.Column(db.String(40),unique=True,nullable=False,index=True)
    label=db.Column(db.String(160),nullable=False)
    description=db.Column(db.Text,default='')
    # Campi mantenuti solo per compatibilità schema: la configurazione destinatario/CC
    # delle notifiche manuali è nei singoli template.
    recipient_mode=db.Column(db.String(20),default='manual')
    recipient_setting_key=db.Column(db.String(100),default='')
    cc_setting_key=db.Column(db.String(100),default='')
    enabled=db.Column(db.Boolean,default=True)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)

class NotificationTemplate(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    kind=db.Column(db.String(40),nullable=False,index=True)  # user, csirt, dpo
    name=db.Column(db.String(160),nullable=False)
    subject=db.Column(db.String(255),nullable=False,default='')
    body=db.Column(db.Text,nullable=False,default='')
    linked_form_template_name=db.Column(db.String(255),nullable=True,index=True)
    action_label_id=db.Column(db.Integer,db.ForeignKey('config_label.id'),nullable=True)
    action_label=db.relationship('ConfigLabel',foreign_keys=[action_label_id])
    recipient_source=db.Column(db.String(40),default='type_default',nullable=False)
    recipient_value=db.Column(db.String(255),default='')
    recipient_editable=db.Column(db.Boolean,default=True,nullable=False)
    recipient_external_allowed=db.Column(db.Boolean,default=True,nullable=False)
    cc_source=db.Column(db.String(40),default='type_default',nullable=False)
    cc_value=db.Column(db.String(255),default='')
    cc_editable=db.Column(db.Boolean,default=True,nullable=False)
    cc_external_allowed=db.Column(db.Boolean,default=True,nullable=False)

    is_default=db.Column(db.Boolean,default=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    __table_args__=(db.UniqueConstraint('kind','name',name='uq_notification_template_kind_name'),)




class ExternalRecipient(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(160),nullable=False,default='')
    email=db.Column(db.String(255),nullable=False,unique=True,index=True)
    notes=db.Column(db.Text,default='')
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    updated_at=db.Column(db.DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)


class FormTemplateConfig(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    template_name=db.Column(db.String(255), nullable=False, unique=True, index=True)
    font_family=db.Column(db.String(40), nullable=False, default='Helvetica')
    font_size=db.Column(db.Integer, nullable=False, default=10)
    notification_tags=db.Column(db.Text, default='', nullable=False)
    created_at=db.Column(db.DateTime, default=datetime.utcnow)
    updated_at=db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def notification_tag_list(self):
        raw = self.notification_tags or ''
        return [x.strip() for x in raw.split(',') if x.strip()]

    def set_notification_tags(self, values):
        seen = []
        for value in values or []:
            code = str(value or '').strip()
            if code and code not in seen:
                seen.append(code)
        self.notification_tags = ','.join(seen)

    @staticmethod
    def normalize_font_family(value):
        value = (value or 'Helvetica').strip()
        return 'Times-Roman' if value in {'Times-Roman', 'Times Roman'} else 'Helvetica'

    @staticmethod
    def normalize_font_size(value):
        try:
            size = int(value)
        except (TypeError, ValueError):
            size = 10
        return max(8, min(16, size))



class FormTemplateBinary(db.Model):
    """Copia persistente DB dei PDF template dei moduli.

    Il file system resta la sorgente operativa per generazione e anteprima,
    ma questa tabella permette di ripristinare automaticamente i PDF quando
    il volume/file system non e` disponibile dopo un riavvio.
    """
    id=db.Column(db.Integer, primary_key=True)
    template_name=db.Column(db.String(255), nullable=False, unique=True, index=True)
    filename=db.Column(db.String(255), nullable=False)
    pdf_data=db.Column(db.LargeBinary, nullable=False)
    created_at=db.Column(db.DateTime, default=datetime.utcnow)
    updated_at=db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FormFieldMapping(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    template_name=db.Column(db.String(255), nullable=False, index=True)
    template_field=db.Column(db.String(255), nullable=False)
    db_field=db.Column(db.String(255), nullable=False)
    created_at=db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__=(db.UniqueConstraint('template_name','template_field',name='uq_form_template_field'),)
