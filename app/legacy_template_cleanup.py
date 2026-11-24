"""Conservative, transactional cleanup of unusable, unreferenced legacy form templates.

No commit, no filesystem writes. Caller owns bootstrap transaction and rollback.
Only orphan configurations with no PDF and no operational references qualify.
"""
from pathlib import Path
import json
from flask import current_app
from sqlalchemy import String, Text, JSON, cast, select
from .models import db, FormTemplateConfig, FormTemplateBinary, FormFieldMapping, AuditLog


def _pdf_exists(name):
    binary = db.session.query(FormTemplateBinary).filter_by(template_name=name).first()
    if binary and binary.pdf_data:
        return True
    base = Path(current_app.config['FORM_TEMPLATE_DIR']).resolve()
    candidate = (base / (Path(name).stem + '.pdf')).resolve()
    return candidate.parent == base and candidate.is_file() and candidate.stat().st_size > 0


def _operational_references(name):
    """Fail closed on unreadable columns; inspect all known mapped text/JSON fields.

    Own config/mappings/binary and historical audit entries are excluded. We
    intentionally scan settings and workflow JSON as well as direct FK-like text.
    """
    excluded = {'form_template_config', 'form_field_mapping', 'form_template_binary',
                'audit_log', 'cir_schema_migrations'}
    for table in db.metadata.sorted_tables:
        if table.name in excluded:
            continue
        for column in table.columns:
            if not isinstance(column.type, (String, Text, JSON)):
                continue
            # Avoid substring false positives in ordinary descriptive fields by
            # requiring a recognizable reference-bearing column or serialized config.
            key = column.name.lower()
            if not (('template' in key) or key in ('value', 'payload_json', 'settings_json', 'configuration_json')):
                continue
            # LIKE wildcard escaping ensures names containing '_' are literal.
            needle = name.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            statement = select(column).where(cast(column, String).like('%' + needle + '%', escape='\\')).limit(1)
            if db.session.execute(statement).first() is not None:
                return f'{table.name}.{column.name}'
    return None


def cleanup_unused_legacy_templates(session=None, logger=None):
    """Delete only provably unused missing-PDF configurations and their mappings.

    Runs before Tenants Default seed in the same bootstrap transaction. A failed
    bootstrap rolls back deletions and audit entries together. No silent commits.
    """
    session = session if session is not None else db.session
    result = {'deleted': [], 'preserved': []}
    for config in session.query(FormTemplateConfig).order_by(FormTemplateConfig.id).all():
        name = config.template_name
        if _pdf_exists(name):
            continue
        reference = _operational_references(name)
        if reference:
            result['preserved'].append({'template': name, 'reason': reference})
            if logger:
                logger.warning('CIR-DATA-002 missing PDF retained: template=%s reference=%s', name, reference)
            continue
        mapping_rows = session.query(FormFieldMapping).filter_by(template_name=name).all()
        count = len(mapping_rows)
        for mapping in mapping_rows:
            session.delete(mapping)
        session.delete(config)
        session.add(AuditLog(operation_type='legacy_template_cleanup', username='system',
                             actor_type='system', tenant_id=config.owner_tenant_id,
                             details=json.dumps({'template': name, 'config_id': config.id,
                                                 'mapping_count': count, 'reason': 'missing_pdf_no_operational_references'},
                                                sort_keys=True)))
        result['deleted'].append({'template': name, 'config_id': config.id, 'mappings': count})
        if logger:
            logger.warning('CIR-DATA-001 removed unused legacy template: name=%s id=%s mappings=%s', name, config.id, count)
    session.flush()
    return result
