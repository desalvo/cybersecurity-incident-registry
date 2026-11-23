"""Ownership of new tenant documents; existing unowned templates stay shared."""
import hashlib
from pathlib import Path
from .models import db, Tenant, Setting, FormTemplateConfig, FormTemplateBinary, FormFieldMapping, NotificationTemplate, IncidentWorkflowStep, Document


def _retired_key(name):
    return '__cir_retired_document:' + hashlib.sha256(name.encode('utf-8')).hexdigest()


def _canonical_name(name):
    from .form_generation import _sanitize_field_name
    return _sanitize_field_name(Path(str(name or '')).stem, 'template')


def _template_names(name):
    """Check the stored identity as well as the runtime PDF filename identity."""
    raw = str(name or '')
    canonical = _canonical_name(raw)
    return tuple(dict.fromkeys((raw, canonical, canonical + '.pdf')))


def _matching_configs(name):
    # Older global archives may store e.g. "form.v1" while materializing
    # "form.pdf". Match the actual runtime identity in both directions, so
    # such aliases cannot turn an owned document into an unowned file.
    canonical = _canonical_name(name)
    return [config for config in FormTemplateConfig.query.all()
            if _canonical_name(config.template_name) == canonical]


def retire_tenant_documents(tenant_id):
    """Persist tombstones before removing owners; orphan disk files stay private.

    No physical file is deleted before the caller's database commit. The
    tombstone also prevents stale files on a mounted volume from becoming
    apparently global templates after their tenant has been removed.
    """
    for config in FormTemplateConfig.query.filter_by(owner_tenant_id=int(tenant_id)).all():
        for name in _template_names(config.template_name):
            db.session.merge(Setting(key=_retired_key(name), value=name))
        FormTemplateBinary.query.filter_by(template_name=config.template_name).delete(synchronize_session=False)
        FormFieldMapping.query.filter_by(template_name=config.template_name).delete(synchronize_session=False)
        db.session.delete(config)


def _tenant_id(tenant_id):
    if tenant_id is None:
        from .routes import current_tenant_id
        tenant_id = current_tenant_id()
    return int(tenant_id) if tenant_id else None


def can_read_template(template_name, tenant_id=None):
    names = _template_names(template_name)
    if any(db.session.get(Setting, _retired_key(name)) is not None for name in names):
        return False
    tenant_id = _tenant_id(tenant_id)
    for config in _matching_configs(template_name):
        if config.owner_tenant_id is None or config.owner_tenant_id == tenant_id:
            continue
        owner = db.session.get(Tenant, config.owner_tenant_id)
        if not owner or not owner.is_system_defaults:
            return False
    return True


def can_edit_template(template_name, tenant_id=None):
    names = _template_names(template_name)
    if any(db.session.get(Setting, _retired_key(name)) is not None for name in names):
        return False
    tenant_id = _tenant_id(tenant_id)
    configs = _matching_configs(template_name)
    if any(config.owner_tenant_id not in (None, tenant_id) for config in configs):
        return False
    if configs and all(config.owner_tenant_id == tenant_id for config in configs):
        return True
    tenant = db.session.get(Tenant, tenant_id) if tenant_id else None
    # Publishing defaults must not alter pre-existing unowned documents.
    return not (tenant and tenant.is_system_defaults)


def require_readable_template(template_name, tenant_id=None):
    if not can_read_template(template_name, tenant_id):
        raise ValueError('Il documento appartiene a un altro tenant.')


def template_in_use(template_name):
    names = _template_names(template_name)
    template_name = _canonical_name(template_name)
    if NotificationTemplate.query.filter(NotificationTemplate.linked_form_template_name.in_(names)).first():
        return True
    if IncidentWorkflowStep.query.filter(IncidentWorkflowStep.document_template_name.in_(names)).first():
        return True
    if Document.query.filter(Document.generated_template_name.in_(names)).first():
        return True
    # Button mappings are JSON and may refer to a document without a workflow.
    import json
    from .models import Setting
    for row in Setting.query.filter(Setting.key.endswith('incident_button_action_labels_json')).all():
        try:
            from .routes import decrypt_setting_value
            value = json.loads(decrypt_setting_value('incident_button_action_labels_json', row.value))
        except (TypeError, ValueError):
            continue
        def contains(item):
            if isinstance(item, list):
                return any(contains(x) for x in item)
            if isinstance(item, dict):
                return any((key in {'template_name', 'document_template_name', 'linked_form_template_name', 'generated_template_name'}
                            and isinstance(value, str) and value and _canonical_name(value) == template_name)
                           or contains(value) for key, value in item.items())
            return False
        if contains(value):
            return True
    return False
