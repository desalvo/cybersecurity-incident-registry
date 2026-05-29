"""Tenant-aware authorization helpers shared by route modules.

The effective role is read from ``UserTenantRole`` for the active/default tenant.
``User.role`` and ``User.tenant_id`` are kept only as migration/backward-
compatibility fields and must not drive normal authorization. A ``superuser``
membership makes the account superuser globally; the local ``admin`` account is
always superuser.
"""


def normalize_role(role):
    return (role or 'disabled').strip().lower() or 'disabled'


def is_builtin_admin_account(user):
    return bool(user and getattr(user, 'is_authenticated', True) and (getattr(user, 'username', '') or '').strip().lower() == 'admin' and (getattr(user, 'auth_provider', 'local') or 'local') == 'local')


def has_superuser_membership(user):
    try:
        for membership in getattr(user, 'tenant_roles', []) or []:
            if normalize_role(getattr(membership, 'role', None)) == 'superuser':
                return True
    except Exception:
        return False
    return False


def is_global_superuser(user):
    # ``User.role`` is a legacy mirror used by old backups/imports. Prefer
    # membership roles, but keep the mirror as a safe compatibility fallback.
    return bool(user and (
        is_builtin_admin_account(user)
        or has_superuser_membership(user)
        or normalize_role(getattr(user, 'role', None)) == 'superuser'
    ))


def role_for_tenant(user, tenant_id):
    if not user:
        return 'disabled'
    if is_global_superuser(user):
        return 'superuser'
    try:
        tid = int(tenant_id) if tenant_id is not None else None
    except (TypeError, ValueError):
        tid = None
    try:
        return user.role_for_tenant(tid)
    except Exception:
        pass
    # Legacy fallback only for imported databases without membership rows.
    if tid and getattr(user, 'tenant_id', None) == tid:
        return normalize_role(getattr(user, 'role', None))
    return 'disabled'


def accessible_tenant_ids(user, roles=None):
    if not user:
        return []
    if is_global_superuser(user):
        return None
    try:
        return user.managed_tenant_ids(roles=roles)
    except Exception:
        tid = getattr(user, 'tenant_id', None)
        role = normalize_role(getattr(user, 'role', None))
        allowed = {normalize_role(r) for r in roles} if roles else None
        return [tid] if tid and role != 'disabled' and (allowed is None or role in allowed) else []
