# RC80 - Tenants Default notification-type publication and retirement

## Required behavior

- Adding a notification type or one of its templates to `Tenants Default` publishes the configuration to every existing tenant within the same database transaction, through the registered `before_commit` synchronization. New tenants inherit the latest published configuration during provisioning.
- Removing a notification type from `Tenants Default` retires its shared source and its shared templates in every tenant. A pristine, unused inherited type and its pristine templates are removed, without deleting unrelated tenant-owned types.
- **A notification type changed by a tenant administrator is a tenant override and is NEVER automatically deleted when its original Tenants Default source is removed, even if no incident references it.** This includes previously existing tenant types adopted during default publication. Any still-published associated templates are also retained when their parent type has been customized, so the preserved local type remains usable.
- A tenant-customized notification template is likewise preserved independently of historical incident use; its parent type is preserved to avoid orphaning the template. A type/template referenced by incident history is preserved even if it has not been customized. Other operational dependencies are checked conservatively before a deletion.
- The shared source becomes inactive and its old per-tenant provenance records are detached. Retained local data is owned by the tenant and must never be overwritten by a later update to the former source. Existing local settings and other tenants are not changed.
- A future type published again from Tenants Default is reconciled by canonical code and template name without multiplying records or overwriting a local override.

## Transactional safety and tests

`app/tenant_defaults.py` performs synchronization in the caller's transaction. Retirement processes shared templates before shared types. It preserves the entire notification bundle for a customized type and never deletes an inherited type while a local template still references its code.

- `tests/test_rc80_notification_default_retirement.py`: isolated SQLite tests (no Flask required) exercise multi-tenant publication, pristine retirement, customized and adopted local types, customized templates, incident references, and tenant isolation.
- `tests/test_rc80_notification_default_integration.py`: full Flask/SQLAlchemy CI tests verify propagation on commit and preservation of overrides on source deletion.

The full CI PostgreSQL and HTTP regression runs remain mandatory. Do not publish source-derived documentation or Docker images before their CI checks succeed.
