"""Safely synchronize the operational default workflow from Tenants Default.

Specialized/category workflows remain tenant-owned. The default source is
inherited at tenant creation and refreshed when its shared definition changes.
Historical incidents prevent destructive in-place changes; they never silently
receive a different workflow than the one they were opened with.
"""
from __future__ import annotations

from flask import current_app

from .models import db, ConfigLabel, IncidentWorkflowStep, Tenant
from .workflow_catalog_models import TenantWorkflow


def _default_steps(tenant_id):
    return IncidentWorkflowStep.query.filter_by(tenant_id=int(tenant_id), category_id=None).order_by(
        IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()


def _mapped_label(source_label_id, tenant_id):
    """Resolve shared UUID provenance before considering matching local labels."""
    if source_label_id is None:
        return None
    source = db.session.get(ConfigLabel, int(source_label_id))
    if source is None:
        raise ValueError('Il default di Tenants Default ha una label non valida.')
    from .workflow_catalog import resolve_shared_copy_dependency
    shared = resolve_shared_copy_dependency(source, 'config_label', tenant_id)
    if shared is not None:
        return shared.id
    local = ConfigLabel.query.filter_by(tenant_id=tenant_id, kind=source.kind, value=source.value).first()
    if local is None:
        local = ConfigLabel(
            tenant_id=tenant_id, kind=source.kind, value=source.value,
            description=source.description, group=source.group,
            default_exportable=source.default_exportable,
            max_completion_hours=source.max_completion_hours,
            description_required=source.description_required,
            automatic_operations=source.automatic_operations,
        )
        db.session.add(local)
        db.session.flush()
    return local.id


def _step_fields(source_step, target_id, label_map):
    def mapped(label_id):
        if label_id not in label_map:
            label_map[label_id] = _mapped_label(label_id, target_id)
        return label_map[label_id]

    conditions = []
    for token in source_step.condition_tokens():
        negated = token.startswith('!')
        base = token[1:] if negated else token
        if ':' in base:
            kind, raw_id = base.split(':', 1)
            if kind in ('severity', 'data_type', 'step_completed'):
                base = f'{kind}:{mapped(int(raw_id))}'
        conditions.append(('!' if negated else '') + base)
    return dict(
        tenant_id=target_id, category_id=None,
        action_label_id=mapped(source_step.action_label_id),
        position=source_step.position,
        description=source_step.description or '',
        personal_data_only=source_step.personal_data_only,
        required=source_step.required,
        step_type=source_step.step_type,
        conditions=','.join(conditions),
        requires_notification=source_step.requires_notification,
        required_notification_type=source_step.required_notification_type,
        document_generation_enabled=source_step.document_generation_enabled,
        document_template_name=source_step.document_template_name,
        section_target=source_step.section_target,
    )


def _fields_match(step, intended):
    return all(getattr(step, field) == value for field, value in intended.items())


def sync_tenant_default_workflow(tenant_id):
    """Copy only when safe, preserving existing incident history and custom scopes."""
    from .workflow_lifecycle import ensure_workflow_state, lock_workflow_configuration
    lock_workflow_configuration()
    tenant = db.session.get(Tenant, int(tenant_id))
    if tenant is None or tenant.is_system_defaults:
        raise ValueError('La destinazione deve essere un tenant operativo.')
    source = Tenant.query.filter_by(is_system_defaults=True).first()
    if source is None:
        return {'status': 'defaults_absent'}
    source_steps = _default_steps(source.id)
    if not source_steps:
        return {'status': 'source_default_absent'}
    existing = _default_steps(tenant.id)
    map_ids = {}
    intended = [_step_fields(step, tenant.id, map_ids) for step in source_steps]
    from .workflow_lifecycle import get_workflow_state
    source_state = get_workflow_state(source.id)
    if len(existing) == len(intended) and all(_fields_match(row, value) for row, value in zip(existing, intended)):
        ensure_workflow_state(tenant.id, name=source_state.name if source_state else 'Flusso di default')
        return {'status': 'unchanged', 'steps': len(existing)}
    if existing:
        # A tenant-specific default in use must not be rewritten retroactively.
        from .configuration_usage import workflow_incident_usage
        reason = workflow_incident_usage(tenant.id, None)
        if reason:
            return {'status': 'blocked_by_incident', 'reason': reason, 'steps': len(existing)}
    for step in existing:
        db.session.delete(step)
    db.session.flush()
    for fields in intended:
        db.session.add(IncidentWorkflowStep(**fields))
    ensure_workflow_state(tenant.id, name=source_state.name if source_state else 'Flusso di default')
    db.session.flush()
    return {'status': 'synchronized', 'steps': len(intended)}


def sync_all_tenant_default_workflows():
    """Called after inherited parameters are synchronized and source edits."""
    source = Tenant.query.filter_by(is_system_defaults=True).first()
    if source is None or not _default_steps(source.id):
        return {}
    results = {}
    for tenant in Tenant.query.filter_by(is_system_defaults=False).all():
        result = sync_tenant_default_workflow(tenant.id)
        results[tenant.id] = result
        if result['status'] == 'blocked_by_incident':
            current_app.logger.warning(
                'Default workflow synchronization deferred for tenant %s: %s',
                tenant.id, result['reason'])
    return results
