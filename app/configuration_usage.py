"""Read-only guards for configuration used by existing tenant incidents.

Call these before removing associations or deleting a row. Database failures
propagate to the caller: an unavailable reference check never grants deletion.
Legacy data without a recorded template identity is treated conservatively.
"""
from sqlalchemy import select, or_
from email.utils import getaddresses
from pathlib import Path

from .models import (
    db, Tenant, Incident, Action, Document, ConfigLabel, IncidentWorkflowStep,
    IncidentTemplate, NotificationTemplate, DeadlineNotificationState, IncidentReminder,
    incident_categories, incident_data_types, incident_people, incident_recommendations,
)


def _session(session=None):
    return session if session is not None else db.session()


def _legacy_default_id(session):
    return session.scalar(select(Tenant.id).where(Tenant.name == 'default', Tenant.is_system_defaults.is_(False)))


def _tenant_scope(column, tenant_id, session):
    if tenant_id is None:
        return column.is_not(None) | column.is_(None)
    tid = int(tenant_id)
    if tid == _legacy_default_id(session):
        return or_(column == tid, column.is_(None))
    return column == tid


def _incident_query(tenant_id, session=None):
    session = _session(session)
    query = select(Incident)
    if tenant_id is not None:
        query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
    return query


def _has_incident(session, tenant_id, *conditions):
    query = select(Incident.id)
    if tenant_id is not None:
        query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
    return session.scalar(query.where(*conditions).limit(1)) is not None


def workflow_incident_usage(tenant_id, category_id=None, steps=None, session=None):
    """Return a reason when the current workflow applies to any old incident."""
    session = _session(session)
    from .workflow_lifecycle import workflow_scope_for_categories
    from .routes import incident_ordered_categories
    if tenant_id is None:
        tenant_id = _legacy_default_id(session)
    for incident in session.scalars(_incident_query(tenant_id, session)):
        owner = incident.tenant_id or _legacy_default_id(session)
        if owner is None:
            raise ValueError('Impossibile determinare il tenant degli incidenti legacy.')
        resolved = workflow_scope_for_categories(owner, [label.id for label in incident_ordered_categories(incident)])
        if resolved == category_id:
            return f'workflow utilizzato dall’incidente #{incident.id}'
    return ''


def _workflow_reference_usage(session, tenant_id, predicate):
    query = select(IncidentWorkflowStep)
    if tenant_id is not None:
        query = query.where(_tenant_scope(IncidentWorkflowStep.tenant_id, tenant_id, session))
    scopes = {(step.tenant_id, step.category_id) for step in session.scalars(query) if predicate(step)}
    for owner, category in scopes:
        reason = workflow_incident_usage(owner, category, session=session)
        if reason:
            return reason
    return ''


def form_template_incident_usage(template_name, tenant_id=None, session=None):
    session = _session(session)
    if not template_name:
        return ''
    names = {template_name, Path(template_name).stem, Path(template_name).stem + '.pdf'}
    query = select(Document.id).join(Incident, Document.incident_id == Incident.id).where(
        Document.generated_template_name.in_(names))
    if tenant_id is not None:
        query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
    if session.scalar(query.limit(1)) is not None:
        return 'modulo utilizzato da documenti già generati per un incidente'
    reason = _workflow_reference_usage(session, tenant_id, lambda step: step.document_template_name in names)
    if reason:
        return reason
    query = select(NotificationTemplate).where(NotificationTemplate.linked_form_template_name.in_(names))
    if tenant_id is not None:
        query = query.where(_tenant_scope(NotificationTemplate.tenant_id, tenant_id, session))
    for template in session.scalars(query):
        reason = configuration_incident_usage('notification_template', template, session)
        if reason:
            return reason
    return ''


def setting_incident_usage(tenant_id, key, session=None):
    """A legacy setting has no usage ledger, so preserve it once incidents exist."""
    session = _session(session)
    if _has_incident(session, tenant_id):
        return 'parametro di un tenant con incidenti esistenti; l’utilizzo storico non è separatamente registrato'
    return ''


def custom_field_incident_usage(tenant_id, field_key, session=None):
    """Preserve a custom-field definition whenever an incident stores its key."""
    import json
    session = _session(session)
    for incident in session.scalars(_incident_query(tenant_id, session)):
        try:
            values = json.loads(incident.custom_fields_json or '{}')
        except (ValueError, TypeError) as exc:
            raise ValueError('Impossibile verificare il campo: dati personalizzati di un incidente non validi.') from exc
        if not isinstance(values, dict):
            raise ValueError('Impossibile verificare il campo: struttura dei dati personalizzati non valida.')
        if field_key in values:
            return f'campo personalizzato presente nell’incidente #{incident.id}'
    return ''


def configuration_incident_usage(kind, row, session=None):
    """Return an incident-use reason, or an empty string when none is found."""
    session = _session(session)
    if kind == 'form_template':
        return form_template_incident_usage(row.template_name, session=session)
    tenant_id = getattr(row, 'tenant_id', None)
    if tenant_id is None:
        tenant_id = _legacy_default_id(session)
    record_id = getattr(row, 'id', None)
    if record_id is None:
        return ''
    if kind == 'config_label':
        if _has_incident(session, tenant_id, Incident.severity_id == record_id):
            return 'gravità utilizzata da un incidente'
        query = select(Action.id).join(Incident, Action.incident_id == Incident.id).where(Action.label_id == record_id)
        if tenant_id is not None:
            query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
        if session.scalar(query.limit(1)) is not None:
            return 'label utilizzata nello storico delle azioni di un incidente'
        for table in (incident_categories, incident_data_types):
            query = select(table.c.incident_id).join(Incident, table.c.incident_id == Incident.id).where(table.c.label_id == record_id)
            if tenant_id is not None:
                query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
            if session.scalar(query.limit(1)) is not None:
                return 'label utilizzata da categorie o dati di un incidente'
        from .tenant_defaults import _json_contains_reference
        return _workflow_reference_usage(session, tenant_id, lambda step:
            step.category_id == record_id or step.action_label_id == record_id
            or _json_contains_reference(step.conditions or '', record_id))
    if kind in {'recommendation', 'person'}:
        table, column = ((incident_recommendations, incident_recommendations.c.recommendation_id)
                         if kind == 'recommendation' else (incident_people, incident_people.c.person_id))
        query = select(table.c.incident_id).join(Incident, table.c.incident_id == Incident.id).where(column == record_id)
        if tenant_id is not None:
            query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
        if session.scalar(query.limit(1)) is not None:
            return 'elemento associato a un incidente'
    elif kind == 'external_recipient':
        email = (row.email or '').strip().casefold()

        def contains_address(raw):
            return email in {address.strip().casefold() for _name, address in
                             getaddresses([(raw or '').replace(';', ',')])}

        for incident in session.scalars(_incident_query(tenant_id, session)):
            if email and contains_address(incident.recipient_email):
                return 'destinatario utilizzato in un incidente'
        for model, field in ((DeadlineNotificationState, DeadlineNotificationState.last_recipients),
                             (IncidentReminder, IncidentReminder.cc_emails)):
            query = select(field).join(Incident, model.incident_id == Incident.id)
            if tenant_id is not None:
                query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
            if email and any(contains_address(value) for value in session.scalars(query)):
                return 'destinatario utilizzato nelle notifiche o nei promemoria di un incidente'
    elif kind in {'notification_type', 'notification_template'}:
        code = row.code if kind == 'notification_type' else row.kind
        query = select(Document).join(Incident, Document.incident_id == Incident.id)
        if tenant_id is not None:
            query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
        for document in session.scalars(query):
            if code in document.notification_tag_list:
                return 'notifica utilizzata da un documento di incidente'
            if kind == 'notification_template' and row.linked_form_template_name and document.generated_template_name == row.linked_form_template_name:
                return 'template utilizzato da un documento di incidente'
        query = select(DeadlineNotificationState.id).join(Incident, DeadlineNotificationState.incident_id == Incident.id).where(
            DeadlineNotificationState.notification_type == code)
        if tenant_id is not None:
            query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
        if session.scalar(query.limit(1)) is not None:
            return 'notifica presente nello storico di un incidente'
        if kind == 'notification_template' and row.action_label_id:
            query = select(Action.id).join(Incident, Action.incident_id == Incident.id).where(Action.label_id == row.action_label_id)
            if tenant_id is not None:
                query = query.where(_tenant_scope(Incident.tenant_id, tenant_id, session))
            if session.scalar(query.limit(1)) is not None:
                return 'template associato a un’azione già registrata in un incidente'
        return _workflow_reference_usage(session, tenant_id, lambda step: step.required_notification_type == code)
    elif kind == 'incident_template':
        if _has_incident(session, tenant_id):
            return 'modello potenzialmente utilizzato da incidenti esistenti; gli archivi legacy non registrano il modello di origine'
    return ''


def require_configuration_unused(kind, row, session=None):
    reason = configuration_incident_usage(kind, row, session)
    if reason:
        raise ValueError('Cancellazione non consentita: ' + reason + '.')
