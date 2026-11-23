"""Provision a newly created shared source from the operational default.

This operation is called only while creating an absent special tenant. It must
never infer that an existing empty source was accidental or overwrite it.
"""
from flask import current_app

from .models import db, Tenant, IncidentTemplate, Setting


def seed_new_defaults_tenant(defaults, *, session=None):
    """Copy configuration and dependencies atomically; caller owns the commit."""
    session = session if session is not None else db.session()
    if session is not db.session():
        raise ValueError('La prima configurazione dei defaults richiede la sessione applicativa corrente.')
    if not defaults.is_system_defaults:
        raise ValueError('Il destinatario deve essere Tenants Default.')
    source = session.query(Tenant).filter_by(name='default', is_system_defaults=False).first()
    if source is None:
        return {'created': False, 'reason': 'operational-default-absent'}
    # This marker belongs to the same transaction as the source, configuration,
    # documents and provenance, so a failed startup cannot leave a partial seed.
    marker_key = '__cir_defaults_initial_seed'
    if session.get(Setting, marker_key) is not None:
        raise ValueError('La provenienza del seed esiste già: non ricreare automaticamente una sorgente rimossa.')
    stripped = sum(bool((row.people_ids or '').strip()) for row in session.query(IncidentTemplate).filter_by(tenant_id=source.id))
    from .tenant_defaults_bundle import export_defaults_bundle, import_defaults_bundle
    payload = export_defaults_bundle(source_tenant_id=source.id, include_secrets=True, _for_initial_seed=True)
    result = import_defaults_bundle(payload)
    from .workflow_catalog import publish_defaults_workflows
    published = publish_defaults_workflows(defaults.id)
    import json
    summary = {
        'source_tenant_id': source.id,
        'defaults_tenant_id': defaults.id,
        'configuration': result['configuration'],
        'documents': result['documents'],
        'settings': result['settings'],
        'draft_workflows': result['draft_workflows'],
        'catalog_workflows': len(published),
        'templates_with_personnel_links_removed': stripped,
        'operational_records_copied': False,
    }
    session.add(Setting(key=marker_key, value=json.dumps(summary, sort_keys=True)))
    session.flush()
    current_app.logger.info(
        'Tenants Default inizializzato dal tenant default: configurazioni=%s, documenti=%s, '
        'workflow=%s, modelli con riferimenti a personale rimossi=%s; nessun account o incidente copiato.',
        result['configuration'].get('created', 0), result['documents'], len(published), stripped,
    )
    return summary
