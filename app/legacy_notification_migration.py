"""Conservative, transactional migration of verified legacy notification aliases.

This migration never commits and never creates a notification type. It runs
inside the application's existing serialized bootstrap transaction. Unknown
or ambiguous aliases remain untouched and fail normal integrity validation.
"""
from sqlalchemy import select

from .models import NotificationTemplate, NotificationType

# Reviewed historical synonym only; never infer arbitrary user-defined aliases.
LEGACY_NOTIFICATION_ALIASES = {'notifica_interna': 'internal'}


def normalize_legacy_notification_kinds(session, *, logger=None):
    """Return count of normalized templates; caller owns commit or rollback."""
    changed = 0
    for old_code, canonical_code in LEGACY_NOTIFICATION_ALIASES.items():
        rows = session.scalars(select(NotificationTemplate).where(
            NotificationTemplate.kind == old_code).order_by(NotificationTemplate.id)
        ).all()
        for row in rows:
            # An explicitly defined custom type takes precedence over aliases.
            defined = session.scalars(select(NotificationType).where(
                NotificationType.tenant_id == row.tenant_id,
                NotificationType.code.in_((old_code, canonical_code))
            )).all()
            codes = {item.code for item in defined}
            if old_code in codes:
                continue
            if canonical_code not in codes:
                raise ValueError(
                    f'Legacy notification template {row.id} in tenant {row.tenant_id}: '
                    f'neither {old_code!r} nor verified target {canonical_code!r} exists; '
                    'manual review required; no changes committed')
            # Never silently collide with another template's unique key.
            duplicate = session.scalar(select(NotificationTemplate.id).where(
                NotificationTemplate.tenant_id == row.tenant_id,
                NotificationTemplate.kind == canonical_code,
                NotificationTemplate.name == row.name,
                NotificationTemplate.id != row.id
            ))
            if duplicate is not None:
                raise ValueError(
                    f'Legacy notification template {row.id} conflicts with template '
                    f'{duplicate}; manual review required; no changes committed')
            row.kind = canonical_code
            changed += 1
            if logger is not None:
                logger.info('Legacy notification kind normalized: tenant=%s template=%s %s -> %s',
                            row.tenant_id, row.id, old_code, canonical_code)
    if changed:
        session.flush()
    return changed
