"""Workflow lifecycle independent of step rows and catalogue revisions.

Current is the initial state, not a singleton default. Obsolescence prevents a
new assignment; it never removes the workflow used by an existing incident.
All writes belong to the caller's transaction, including recipient notices.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import inspect, or_, select, text

from .models import db, ConfigLabel, IncidentWorkflowStep, Tenant, User
from .timeutils import utcnow
from .workflow_catalog_models import (
    TenantWorkflow, WorkflowCatalogEntry, WorkflowCatalogInstallation,
    WorkflowObsolescenceNotice,
)

WORKFLOW_STATUSES = {'current', 'obsolete'}
_NEW_ASSIGNMENT = object()


def lock_workflow_configuration():
    """Use the publisher's lock order: shared source, then local/catalog rows."""
    from .tenant_defaults import _lock_defaults
    session = db.session()
    with session.no_autoflush:
        return _lock_defaults(session)


def workflow_scope_key(category_id=None):
    if category_id is None:
        return 'default'
    if type(category_id) is not int or category_id <= 0:
        raise ValueError('Categoria workflow non valida.')
    return f'category:{category_id}'


def _steps_query(tenant_id, category_id=None):
    tenant = db.session.get(Tenant, int(tenant_id))
    if tenant is None:
        raise ValueError('Tenant workflow inesistente.')
    q = IncidentWorkflowStep.query
    if tenant.name == 'default' and not tenant.is_system_defaults:
        q = q.filter(or_(IncidentWorkflowStep.tenant_id == tenant.id,
                         IncidentWorkflowStep.tenant_id.is_(None)))
    else:
        q = q.filter_by(tenant_id=tenant.id)
    return q.filter(IncidentWorkflowStep.category_id == category_id)


def _category_query(tenant, category_id):
    query = ConfigLabel.query.filter_by(id=category_id, kind='category')
    if tenant.name == 'default' and not tenant.is_system_defaults:
        return query.filter(or_(ConfigLabel.tenant_id == tenant.id, ConfigLabel.tenant_id.is_(None)))
    return query.filter_by(tenant_id=tenant.id)


def workflow_scope_for_categories(tenant_id, category_ids):
    """Return the runtime scope: first category if populated, else default."""
    ids = list(category_ids or [])
    tenant = db.session.get(Tenant, int(tenant_id))
    if tenant is None:
        raise ValueError('Tenant workflow inesistente.')
    for category_id in ids:
        if type(category_id) is not int or category_id <= 0:
            raise ValueError('Categoria incidente non valida.')
        if _category_query(tenant, category_id).first() is None:
            raise ValueError('Categoria incidente non appartenente al tenant.')
    if ids and _steps_query(tenant_id, ids[0]).first() is not None:
        return ids[0]
    return None


def get_workflow_state(tenant_id, category_id=None):
    return TenantWorkflow.query.filter_by(tenant_id=int(tenant_id),
                                         scope_key=workflow_scope_key(category_id)).first()


def ensure_workflow_state(tenant_id, category_id=None, *, name=None, source_entry_id=None):
    lock_workflow_configuration()
    tenant = Tenant.query.filter_by(id=int(tenant_id)).with_for_update().first()
    if tenant is None:
        raise ValueError('Tenant workflow inesistente.')
    category = None
    if category_id is not None:
        category = _category_query(tenant, category_id).first()
        if category is None:
            raise ValueError('Categoria workflow non appartenente al tenant.')
    state = get_workflow_state(tenant.id, category_id)
    if state is None:
        state = TenantWorkflow(tenant_id=tenant.id, category_id=category_id,
                               scope_key=workflow_scope_key(category_id), status='current',
                               personalized=False,
                               name=(name or (category.value if category else 'Flusso di default'))[:160])
        db.session.add(state)
    if name is not None:
        if not isinstance(name, str) or not name.strip() or len(name) > 160:
            raise ValueError('Nome workflow non valido.')
        state.name = name.strip()
    if source_entry_id is not None:
        entry = db.session.get(WorkflowCatalogEntry, int(source_entry_id))
        if entry is None:
            raise ValueError('Origine del workflow inesistente.')
        if state.source_entry_id not in (None, entry.id):
            raise ValueError('La copia appartiene già a un altro workflow di catalogo.')
        state.source_entry_id = entry.id
        if entry.status == 'obsolete':
            state.status, state.obsolete_at = 'obsolete', state.obsolete_at or utcnow()
    db.session.flush()
    return state


def workflow_status(tenant_id, category_id=None):
    state = get_workflow_state(tenant_id, category_id)
    if state is None:
        return 'current'
    if state.source_entry_id:
        entry = db.session.get(WorkflowCatalogEntry, state.source_entry_id)
        if entry is None or entry.status == 'obsolete':
            # Missing origin is a corrupt lifecycle, never a reactivation path.
            return 'obsolete'
    return state.status


def assert_workflow_assignable(tenant_id, category_ids, *, previous_category_ids=_NEW_ASSIGNMENT):
    scope = workflow_scope_for_categories(tenant_id, category_ids)
    if previous_category_ids is not _NEW_ASSIGNMENT:
        previous_scope = workflow_scope_for_categories(tenant_id, previous_category_ids)
        if previous_scope == scope:
            return scope
    if workflow_status(tenant_id, scope) != 'current':
        raise ValueError('Il workflow selezionato è obsoleto: scegliere un workflow corrente per un nuovo incidente o una nuova assegnazione.')
    return scope


def workflow_states_for_tenant(tenant_id):
    """Return UI states keyed exactly like legacy grouped workflow steps."""
    return {(row.category_id or 0): row for row in TenantWorkflow.query.filter_by(tenant_id=int(tenant_id)).all()}


def backfill_workflow_states(tenant_id=None):
    """Attach old RC17 receipts without relying on unchanged step IDs."""
    lock_workflow_configuration()
    query = db.session.query(IncidentWorkflowStep.tenant_id, IncidentWorkflowStep.category_id).distinct()
    if tenant_id is not None:
        query = query.filter(IncidentWorkflowStep.tenant_id == int(tenant_id))
    for tid, category_id in query.all():
        if tid is not None:
            ensure_workflow_state(tid, category_id)
    receipts = WorkflowCatalogInstallation.query.order_by(WorkflowCatalogInstallation.id)
    if tenant_id is not None:
        receipts = receipts.filter_by(tenant_id=int(tenant_id))
    for receipt in receipts.all():
        if receipt.workflow_id is not None:
            continue
        state = get_workflow_state(receipt.tenant_id, receipt.category_id)
        if state is None or state.source_entry_id not in (None, receipt.entry_id):
            continue
        try:
            step_ids = json.loads(receipt.step_ids_json)
        except (ValueError, TypeError):
            continue
        if (not isinstance(step_ids, list) or not step_ids
                or any(type(value) is not int or value <= 0 for value in step_ids)):
            continue
        surviving = IncidentWorkflowStep.query.filter(IncidentWorkflowStep.id.in_(step_ids)).all()
        if not surviving or any(row.tenant_id != receipt.tenant_id or row.category_id != receipt.category_id
                                or row.created_at is None or receipt.created_at is None
                                or row.created_at > receipt.created_at for row in surviving):
            continue
        # A receipt whose scope has been removed stays historical; a new
        # incarnation must never silently obtain an unrelated origin. At
        # least one original step must survive; creation dates also detect
        # SQLite's possible reuse of a deleted integer primary key.
        state.source_entry_id = receipt.entry_id
        entry = db.session.get(WorkflowCatalogEntry, receipt.entry_id)
        if entry is not None and entry.status == 'obsolete':
            state.status, state.obsolete_at = 'obsolete', state.obsolete_at or utcnow()
        receipt.workflow_id = state.id
    db.session.flush()


def _notify_obsolescence(entry):
    event_id = str(uuid.uuid4())
    tenant_ids = [tid for (tid,) in db.session.query(Tenant.id).filter_by(is_system_defaults=False).all()]
    message = (f'Il workflow "{entry.name}" di Tenants Default è stato dichiarato obsoleto. '
               'Non è più importabile. Tutte le copie già importate, comprese quelle personalizzate, '
               'sono obsolete per i nuovi incidenti; gli incidenti esistenti conservano il loro workflow.')
    for user in User.query.all():
        if user.is_global_superuser or any(user.role_for_tenant(tid) == 'admin' for tid in tenant_ids):
            db.session.add(WorkflowObsolescenceNotice(event_id=event_id, user_id=user.id,
                                                      entry_id=entry.id, message=message))


def set_catalog_workflow_status(entry_id, status):
    if not isinstance(status, str) or status not in WORKFLOW_STATUSES:
        raise ValueError('Stato workflow non valido.')
    lock_workflow_configuration()
    entry = WorkflowCatalogEntry.query.filter_by(id=int(entry_id)).populate_existing().with_for_update().first()
    if entry is None:
        raise ValueError('Workflow di catalogo inesistente.')
    upstream_id = json.loads(entry.payload_json).get('workflow', {}).get('catalog_source_public_id')
    upstream = WorkflowCatalogEntry.query.filter_by(public_id=upstream_id).first() if upstream_id else None
    if status == 'current' and upstream is not None and upstream.id != entry.id and upstream.status != 'current':
        raise ValueError('La sorgente originaria del catalogo è obsoleta: questa voce non può essere riattivata.')
    previous = entry.status
    entry.status = status
    entry.obsolete_at = (entry.obsolete_at or utcnow()) if status == 'obsolete' else None
    if status == 'obsolete':
        backfill_workflow_states()
        # Exporting a copy and reimporting it as a catalogue entry preserves its
        # public origin. Include such derivatives without assuming step rows or
        # snapshot hashes are unchanged, and tolerate cyclic historical links.
        affected_ids, public_ids = {entry.id}, {entry.public_id}
        candidates = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=entry.defaults_tenant_id).all()
        changed = True
        while changed:
            changed = False
            for candidate in candidates:
                parent = json.loads(candidate.payload_json).get('workflow', {}).get('catalog_source_public_id')
                same_source_scope = entry.source_scope_key and candidate.source_scope_key == entry.source_scope_key
                if candidate.id not in affected_ids and (parent in public_ids or same_source_scope):
                    affected_ids.add(candidate.id)
                    public_ids.add(candidate.public_id)
                    candidate.status, candidate.obsolete_at = 'obsolete', candidate.obsolete_at or entry.obsolete_at
                    changed = True
        for state in TenantWorkflow.query.filter(TenantWorkflow.source_entry_id.in_(affected_ids)).all():
            state.status, state.obsolete_at = 'obsolete', state.obsolete_at or entry.obsolete_at
        for candidate in candidates:
            if candidate.id in affected_ids and candidate.source_scope_key:
                draft = TenantWorkflow.query.filter_by(tenant_id=candidate.defaults_tenant_id,
                                                       scope_key=candidate.source_scope_key).first()
                if draft:
                    draft.status, draft.obsolete_at = 'obsolete', draft.obsolete_at or entry.obsolete_at
        if previous != 'obsolete':
            _notify_obsolescence(entry)
    elif entry.source_scope_key:
        # Multiple published revisions/names of one source draft share that
        # draft's lifecycle; installed copies still require local reactivation.
        for sibling in WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=entry.defaults_tenant_id,
                                                           source_scope_key=entry.source_scope_key).all():
            sibling.status, sibling.obsolete_at = 'current', None
    # Reactivating a source permits explicit local reactivation; it does not
    # reverse a tenant administrator's obsolete decision automatically.
    if entry.source_scope_key:
        state = TenantWorkflow.query.filter_by(tenant_id=entry.defaults_tenant_id,
                                               scope_key=entry.source_scope_key).first()
        if state:
            state.status, state.obsolete_at = status, entry.obsolete_at
    db.session.flush()
    return entry


def set_workflow_status(tenant_id, category_id, status):
    if not isinstance(status, str) or status not in WORKFLOW_STATUSES:
        raise ValueError('Stato workflow non valido.')
    state = ensure_workflow_state(tenant_id, category_id)
    tenant = db.session.get(Tenant, state.tenant_id)
    if status == 'current' and state.source_entry_id:
        source = db.session.get(WorkflowCatalogEntry, state.source_entry_id)
        if source is None or source.status == 'obsolete':
            raise ValueError('La sorgente nel catalogo è obsoleta: questa copia non può essere riattivata.')
    state.status, state.obsolete_at = status, utcnow() if status == 'obsolete' else None
    if tenant.is_system_defaults:
        for entry in WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=tenant.id,
                                                         source_scope_key=state.scope_key).all():
            set_catalog_workflow_status(entry.id, status)
    db.session.flush()
    return state


def copy_workflow_origin(source_tenant_id, source_category_id, target_tenant_id, target_category_id):
    lock_workflow_configuration()
    if workflow_status(source_tenant_id, source_category_id) != 'current':
        raise ValueError('Un workflow obsoleto non può essere copiato per nuovi incidenti.')
    source = get_workflow_state(source_tenant_id, source_category_id)
    entry_id = source.source_entry_id if source else None
    source_tenant = db.session.get(Tenant, int(source_tenant_id))
    target_tenant = db.session.get(Tenant, int(target_tenant_id))
    if (entry_id is None and source_tenant is not None and source_tenant.is_system_defaults
            and target_tenant is not None and not target_tenant.is_system_defaults):
        entry = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=source_tenant.id,
            source_scope_key=workflow_scope_key(source_category_id)).order_by(WorkflowCatalogEntry.id).first()
        if entry is None:
            from .workflow_catalog import build_catalog_workflow_payload, save_catalog_workflow
            source = source or ensure_workflow_state(source_tenant.id, source_category_id)
            entry = save_catalog_workflow(build_catalog_workflow_payload(source_tenant.id, source_category_id), source.name)
            entry.source_scope_key = source.scope_key
        entry_id = entry.id
    if target_tenant is not None and target_tenant.is_system_defaults:
        # A new configuration draft is not an installed operational copy.
        entry_id = None
    return ensure_workflow_state(target_tenant_id, target_category_id,
                                 source_entry_id=entry_id)


def portable_workflow_lifecycle(tenant_id, category_id=None):
    state = get_workflow_state(tenant_id, category_id)
    result = {'status': workflow_status(tenant_id, category_id)}
    entry = db.session.get(WorkflowCatalogEntry, state.source_entry_id) if state and state.source_entry_id else None
    if entry is None:
        tenant = db.session.get(Tenant, int(tenant_id))
        if tenant and tenant.is_system_defaults:
            entry = WorkflowCatalogEntry.query.filter_by(defaults_tenant_id=tenant.id,
                source_scope_key=workflow_scope_key(category_id)).order_by(WorkflowCatalogEntry.id).first()
    if entry is not None:
        result['catalog_source_public_id'] = entry.public_id
    return result


def validate_portable_workflow_lifecycle(workflow):
    status = workflow.get('status', 'current')
    if not isinstance(status, str) or status not in WORKFLOW_STATUSES:
        raise ValueError('Stato del workflow esportato non valido.')
    if status != 'current':
        raise ValueError('Un workflow obsoleto non può essere importato o assegnato a nuovi incidenti.')
    source_id = workflow.get('catalog_source_public_id')
    if source_id is None:
        return None
    try:
        if not isinstance(source_id, str) or str(uuid.UUID(source_id)) != source_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Origine pubblica del workflow non valida.') from exc
    entry = WorkflowCatalogEntry.query.filter_by(public_id=source_id).first()
    if entry is not None and (entry.status != 'current' or not entry.active):
        raise ValueError('La sorgente del workflow nel catalogo non è più disponibile per nuove importazioni.')
    return entry


def apply_portable_workflow_origin(workflow, tenant_id, category_id=None):
    entry = validate_portable_workflow_lifecycle(workflow)
    return ensure_workflow_state(tenant_id, category_id,
                                 source_entry_id=entry.id if entry is not None else None)


def remove_workflow_state(tenant_id, category_id=None):
    """Called after the central incident-usage guard permits deliberate deletion."""
    lock_workflow_configuration()
    state = get_workflow_state(tenant_id, category_id)
    if state is None:
        # Legacy imports can have step rows and an imported category but no
        # lifecycle state. Deleting their final step must release the name too.
        _prune_catalog_category(tenant_id, category_id)
        return
    # Leave receipts as historical pointers, never reconnect them to a newly
    # created scope during a later backfill.
    db.session.delete(state)
    db.session.flush()
    _prune_catalog_category(tenant_id, category_id, workflow_id=state.id)


def rename_workflow(tenant_id, category_id, new_name):
    """Rename the workflow and its first-category label as one tenant-scoped edit.

    Never apply an automatic ``v2`` suffix here: an explicit rename must either
    use exactly the requested name or fail, including case-insensitive clashes.
    """
    if category_id is None:
        raise ValueError('Il workflow di default ha nome riservato e non può essere rinominato.')
    if not isinstance(new_name, str) or not new_name.strip() or len(new_name.strip()) > 160:
        raise ValueError('Inserire un nome workflow valido (massimo 160 caratteri).')
    name = new_name.strip()
    lock_workflow_configuration()
    tenant = Tenant.query.filter_by(id=int(tenant_id)).with_for_update().first()
    if tenant is None:
        raise ValueError('Tenant inesistente.')
    label = _category_query(tenant, int(category_id)).first()
    if label is None or not _steps_query(tenant.id, label.id).first():
        raise ValueError('Workflow inesistente o vuoto.')
    from .tenant_defaults_models import TenantDefaultReplica
    if TenantDefaultReplica.query.filter_by(tenant_id=tenant.id, local_type='config_label', local_id=label.id).first():
        raise ValueError('Categoria ereditata da Tenants Default: creare prima una copia locale indipendente.')
    wanted = name.casefold()
    for category in ConfigLabel.query.filter_by(tenant_id=tenant.id, kind='category').all():
        if category.id != label.id and category.value.strip().casefold() == wanted:
            raise ValueError('Il nome scelto è già presente nel tenant.')
    for other in TenantWorkflow.query.filter_by(tenant_id=tenant.id).all():
        if other.category_id != label.id and other.name.strip().casefold() == wanted:
            raise ValueError('Il nome scelto è già presente nel tenant.')
    label.value = name
    state = get_workflow_state(tenant.id, label.id)
    if state is None:
        state = ensure_workflow_state(tenant.id, label.id, name=name)
    else:
        state.name = name
    # Installation receipts intentionally retain the historical import name.
    # The stable category/workflow IDs preserve incident associations.
    db.session.flush()
    return state


def _prune_catalog_category(tenant_id, category_id, *, workflow_id=None):
    """Release an imported workflow name only when its category is unused.

    Categories may also classify incidents or templates. Never discard those
    records, or a live replica of the shared defaults configuration.
    """
    if category_id is None:
        return False
    category = ConfigLabel.query.filter_by(id=int(category_id), tenant_id=int(tenant_id), kind='category').first()
    if category is None:
        return False
    receipt_query = WorkflowCatalogInstallation.query.filter_by(tenant_id=int(tenant_id), category_id=category.id)
    receipts = receipt_query.all()
    owned = category.group == 'catalogo workflow' or any(
        row.workflow_id == workflow_id for row in receipts if workflow_id is not None
    )
    if not owned:
        return False
    if _steps_query(tenant_id, category.id).first() or get_workflow_state(tenant_id, category.id):
        return False
    from .models import IncidentTemplate, incident_categories
    from .tenant_defaults_models import TenantDefaultReplica, TenantDefaultSource
    if db.session.execute(select(incident_categories.c.incident_id).where(
            incident_categories.c.label_id == category.id).limit(1)).first():
        return False
    if any(str(category.id) in str(row.category_ids or '').split(',') for row in
           IncidentTemplate.query.filter_by(tenant_id=int(tenant_id)).all()):
        return False
    if TenantDefaultReplica.query.filter_by(tenant_id=int(tenant_id), local_type='config_label', local_id=category.id).first():
        return False
    if TenantDefaultSource.query.filter_by(source_type='config_label', source_id=category.id).first():
        return False
    db.session.delete(category)
    db.session.flush()
    return True


def prune_empty_workflows(tenant_id=None):
    """Remove empty lifecycle records and safe orphaned catalogue categories.

    Called during explicit workflow maintenance/import, not on every request.
    Receipts remain immutable historical records; they cannot reserve names.
    """
    lock_workflow_configuration()
    rows = TenantWorkflow.query
    if tenant_id is not None:
        rows = rows.filter_by(tenant_id=int(tenant_id))
    states = rows.all()
    removed_states = 0
    for state in states:
        if _steps_query(state.tenant_id, state.category_id).first():
            continue
        tid, cid, wid = state.tenant_id, state.category_id, state.id
        # Delete empty scopes, including legacy empty default states; the
        # bootstrap/sync routine recreates the required default steps.
        db.session.delete(state)
        db.session.flush()
        removed_states += 1
        _prune_catalog_category(tid, cid, workflow_id=wid)
    receipts = WorkflowCatalogInstallation.query
    if tenant_id is not None:
        receipts = receipts.filter_by(tenant_id=int(tenant_id))
    removed_categories = 0
    for receipt in receipts.all():
        if receipt.category_id is None:
            continue
        if _prune_catalog_category(receipt.tenant_id, receipt.category_id,
                                   workflow_id=receipt.workflow_id):
            removed_categories += 1
    return {'empty_states_removed': removed_states, 'orphan_categories_removed': removed_categories}

def unread_workflow_notice_count(user_id):
    return WorkflowObsolescenceNotice.query.filter_by(user_id=int(user_id), read_at=None).count()


def personalize_workflow_parameters(workflow_id):
    from .workflow_catalog import personalize_workflow_parameters as personalize
    return personalize(workflow_id)


def migrate_workflow_lifecycle_schema(engine):
    """Idempotent RC17 upgrade; new lifecycle tables come from create_all()."""
    migrations = {
        'workflow_catalog_entry': {
            'status': "VARCHAR(20) NOT NULL DEFAULT 'current'",
            'obsolete_at': 'TIMESTAMP', 'source_scope_key': 'VARCHAR(80)',
        },
        'workflow_catalog_installation': {'workflow_id': 'INTEGER'},
    }
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        for table, additions in migrations.items():
            if table not in tables:
                continue
            columns = {column['name'] for column in inspector.get_columns(table)}
            for column, definition in additions.items():
                if column not in columns:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {definition}'))
