"""Portable lifecycle metadata for tenant-only Full Export/Import.

Catalog database IDs and other users' notices never cross the tenant boundary.
An unavailable public origin keeps a restored workflow obsolete until reviewed.
"""
from .models import db, ConfigLabel, IncidentWorkflowStep, TenantWorkflow, WorkflowCatalogEntry
from .timeutils import utcnow


def export_scoped_workflow_states(tenant_id):
    from .routes import _row
    from .workflow_lifecycle import workflow_status
    result = []
    for state in TenantWorkflow.query.filter_by(tenant_id=int(tenant_id)).order_by(TenantWorkflow.id):
        row = _row(state)
        source = db.session.get(WorkflowCatalogEntry, state.source_entry_id) if state.source_entry_id else None
        row['source_entry_id'] = None
        row['source_entry_public_id'] = source.public_id if source else None
        row['status'] = workflow_status(tenant_id, state.category_id)
        if source is not None and not source.active:
            row['status'] = 'obsolete'
        result.append(row)
    return result


def _scope_identity(category_id):
    label = db.session.get(ConfigLabel, category_id) if category_id is not None else None
    return ('category', label.value) if label else ('default', None)


def capture_scoped_obsolete_workflows(tenant_id):
    """Remember local obsolete decisions across the authorized scope replacement."""
    from .workflow_lifecycle import workflow_status
    public_ids, scopes = set(), set()
    for state in TenantWorkflow.query.filter_by(tenant_id=int(tenant_id)):
        if workflow_status(tenant_id, state.category_id) == 'obsolete':
            public_ids.add(state.public_id)
            scopes.add(_scope_identity(state.category_id))
    return {'public_ids': public_ids, 'scopes': scopes}


def restore_scoped_workflow_states(rows, tenant_id, label_map, previous_obsolete):
    from .workflow_lifecycle import ensure_workflow_state
    for row in rows:
        source_category = row.get('category_id')
        category_id = label_map.get(source_category) if source_category is not None else None
        if source_category is not None and category_id is None:
            raise ValueError('Categoria dello stato workflow non inclusa nell archivio tenant.')
        if row.get('source_entry_id') is not None:
            raise ValueError('Un archivio tenant non può imporre ID di catalogo globali.')
        public_origin = row.get('source_entry_public_id')
        entry = WorkflowCatalogEntry.query.filter_by(public_id=public_origin).one_or_none() if public_origin else None
        state = ensure_workflow_state(tenant_id, category_id, name=row.get('name') or None,
                                      source_entry_id=entry.id if entry else None)
        status = row.get('status', 'current')
        if status not in ('current', 'obsolete'):
            raise ValueError('Stato workflow del tenant non valido.')
        if (row.get('public_id') in previous_obsolete['public_ids']
                or _scope_identity(category_id) in previous_obsolete['scopes']
                or (public_origin and (entry is None or entry.status == 'obsolete' or not entry.active))):
            status = 'obsolete'
        state.status = status
        state.obsolete_at = utcnow() if status == 'obsolete' else None
        state.personalized = bool(row.get('personalized', False))
    # Older archives have no lifecycle table. Restoring one must still respect
    # an existing tenant administrator's obsolete decision for the same scope.
    for (category_id,) in db.session.query(IncidentWorkflowStep.category_id).filter_by(tenant_id=int(tenant_id)).distinct():
        if _scope_identity(category_id) in previous_obsolete['scopes']:
            state = ensure_workflow_state(tenant_id, category_id)
            state.status, state.obsolete_at = 'obsolete', utcnow()
    db.session.flush()
