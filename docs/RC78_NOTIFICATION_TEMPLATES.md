# RC78 - Notification-template inheritance and bulk deletion

## Functional behavior

- **Identity:** notification template equivalence is tenant-scoped by notification kind and normalized name. A template already present locally must not be duplicated with a `[Tenants Default]` suffix when the shared template is published, when a tenant is created, or when tenant settings are cloned.
- **Local overrides:** the tenant's template ID, text, recipients/CC, and default flag are preserved when the shared source is updated. Local administrators can still edit the template normally.
- **Revert on removal:** deleting a local override (or an inherited replica) in an operational tenant makes the published Tenants Default definition available again in the same commit, provided the shared source still exists. This is not a permanent exclusion of the inherited template.
- **Shared deletion:** removal from the Tenants Default tenant is administrative publication and may affect all tenants. Independently owned local customizations remain intact.
- **One-time built-in bootstrap:** first-use built-in examples are seeded only when the tenant has no templates and has not been initialized previously. The tenant-scoped `notification_templates_bootstrapped_v2` flag stops administrative deletions from being undone by the next page load. Legacy tenants with existing templates are treated as already initialized. The notification-send fallback can still initialize a usable template if the tenant has none at all and an operator starts a notification; that is separate from administration page loads.

## UI

The new *Notifications -> Manage / delete templates* page is available to tenant admins and super admins, including users of the classic interface. It lists notification templates from **the active tenant only** (with type, name, subject, origin and default marker), allows selecting some or all templates, and provides a confirmation prompt. The POST handler only accepts bounded, positive integer IDs; resolves **every** row in the active tenant before deleting; protects referenced templates; and executes deletion in a single commit with an audit entry. A failed authorization/validation leaves all selected templates in place. A super admin must activate a different tenant before managing its templates.

Existing per-type **Delete** actions remain available. The Tenants Default configuration-only access allowlist also includes the new administrative page.

## Testing and limitations

Dependency-free route tests exercise bulk deletion, no selection, malformed input, cross-tenant IDs, role denial, blocked rows, and shared override reappearance. Isolated SQLAlchemy tests verify that initial bootstrap is idempotent, deleted built-in examples do not reappear, a legacy tenant with existing templates is not reseeded, and bootstrap is tenant-scoped. SQLAlchemy-isolated tests exercise the actual inheritance and deduplication algorithms. The full Flask/PostgreSQL test suite and live browser interface must be verified in GitHub Actions; no CI-green claim is made for this local release.
