"""Live setting inheritance with explicit tenant overrides."""
import json

from .models import db, Setting, Tenant, ConfigLabel, NotificationType, Recommendation
from .tenant_defaults_models import TenantDefaultReplica, TenantDefaultSource
from .route_modules.tenancy import TENANT_SHARED_CONFIGURATION_KEYS


def is_tenant_parameter(key):
    key = str(key or '')
    return bool(key and not key.startswith(('__', 'tenant:', 'scheduler_'))
                and key not in TENANT_SHARED_CONFIGURATION_KEYS
                and not key.endswith(('_last_run_at', '_last_status', '_last_error', '_last_sent_at')))


def remap_setting_references(key, value, tenant_id, defaults_id):
    """Map typed reference fields; numbers in unrelated settings stay intact."""
    if key != 'incident_button_action_labels_json':
        return value
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return value
    labels, notifications = {}, {}
    pairs = db.session.query(TenantDefaultSource, TenantDefaultReplica).join(
        TenantDefaultReplica, TenantDefaultReplica.source_id == TenantDefaultSource.id
    ).filter(TenantDefaultReplica.tenant_id == tenant_id, TenantDefaultSource.active.is_(True)).all()
    for source, replica in pairs:
        if source.source_type == 'config_label':
            labels[str(source.source_id)] = replica.local_id
        elif source.source_type == 'notification_type':
            origin = db.session.get(NotificationType, source.source_id)
            local = db.session.get(NotificationType, replica.local_id)
            if origin and local:
                notifications[origin.code] = local.code

    def transform(item):
        if isinstance(item, list):
            return [transform(x) for x in item]
        if not isinstance(item, dict):
            return item
        result = {k: transform(v) for k, v in item.items()}
        if 'label_id' in result:
            # Missing source dependencies must not bind an unrelated local ID.
            result['label_id'] = labels.get(str(result['label_id']))
        for field in ('notification_tags', 'tags'):
            if isinstance(result.get(field), list):
                result[field] = [notifications[tag] for tag in result[field]
                                 if isinstance(tag, str) and tag in notifications]
        return result
    from .routes import INCIDENT_BUTTON_ACTIONS
    allowed_buttons = {code for code, _label in INCIDENT_BUTTON_ACTIONS}
    if isinstance(payload, dict):
        # The legacy format stored a label ID directly as each button's value.
        # Limit this conversion to actual button slots, never arbitrary ints.
        payload = {code: ({'label_id': value} if code in allowed_buttons
                          and isinstance(value, (int, str)) and not isinstance(value, bool)
                          else value) for code, value in payload.items()}
    return json.dumps(transform(payload), ensure_ascii=False)


def inherited_setting(key, tenant_id):
    """Return the source value (including explicit empty strings), or None."""
    if not tenant_id or not is_tenant_parameter(key):
        return None
    source = Tenant.query.filter_by(is_system_defaults=True).first()
    if source is None or source.id == int(tenant_id):
        return None
    row = db.session.get(Setting, f'tenant:{source.id}:{key}')
    if row is None or row.value is None:
        return None
    from .routes import decrypt_setting_value
    value = decrypt_setting_value(key, row.value)
    return remap_setting_references(key, value, int(tenant_id), source.id)


def is_defaults_id(tenant_id):
    row = db.session.get(Tenant, int(tenant_id)) if tenant_id else None
    return bool(row and row.is_system_defaults)


def shared_notification_codes(codes, tenant_id):
    """Resolve published document tags through provenance, never by homonym."""
    source = Tenant.query.filter_by(is_system_defaults=True).first()
    if source is None or source.id == int(tenant_id):
        return list(codes)
    origins = {row.id: row.code for row in NotificationType.query.filter_by(tenant_id=source.id).all()}
    mapping = {}
    pairs = db.session.query(TenantDefaultSource, TenantDefaultReplica).join(
        TenantDefaultReplica, TenantDefaultReplica.source_id == TenantDefaultSource.id
    ).filter(TenantDefaultReplica.tenant_id == int(tenant_id),
             TenantDefaultSource.source_type == 'notification_type', TenantDefaultSource.active.is_(True)).all()
    for origin, replica in pairs:
        local = db.session.get(NotificationType, replica.local_id)
        if local is not None and local.tenant_id == int(tenant_id) and origin.source_id in origins:
            mapping[origins[origin.source_id]] = local.code
    return [mapping[code] for code in codes if code in mapping]
