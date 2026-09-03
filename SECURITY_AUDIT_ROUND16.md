# Security Audit Round 16

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: final cross-cutting review of authentication/session boundaries, tenant isolation, filesystem-backed persistent metadata, outbound integrations, backup/import/export, background schedulers, audit retention, and secret handling.

## Confirmed findings and remediation

### HIGH — Notification templates/types crossed the active-tenant boundary

`NotificationTemplate` and `NotificationType` carry tenant ownership, but several administrative CRUD, default-selection, preview and workflow-import paths queried rows by global numeric ID or unscoped type/kind. A tenant administrator able to address another tenant's row ID could therefore enter edit/delete/clone/default flows or select a foreign template.

Round 16 centralizes active-tenant template/type queries and writable lookups. New defaults and imports are assigned to the active tenant; global legacy rows may remain readable where compatibility requires it, but they are never mutated as another tenant's local configuration. Workflow import/diff and notification preview/default resolution now honor the same tenant boundary.

### HIGH — AI chatbot knowledge base and database context were not tenant-isolated

The AI knowledge-document model includes `tenant_id`, but upload/list/delete and knowledge aggregation were global. In addition, a superuser using one active tenant could build an AI database context containing rows from every tenant.

Round 16 assigns uploaded AI documents to the active tenant, scopes list/delete/knowledge aggregation, and always filters tenant-aware database-context tables to the active tenant even for superusers. AI plugin administrative authorization now follows the application's active-tenant `can_admin()` boundary.

### HIGH — AI document deletion trusted persistent filenames

Deletion of an AI knowledge document used the database-backed stored filename as a filesystem path. Legacy, restored or corrupted metadata could therefore escape the managed AI document directory.

Round 16 adds a canonical path helper that requires an unchanged secure basename resolving to a direct child of `AI_CHATBOT_DOC_DIR`. Upload and deletion use the same boundary and new files receive restrictive permissions where supported.

### HIGH — Stored SMTP/LDAP/SSO secrets were reflected back into administrative HTML

SMTP passwords, LDAP bind passwords and SSO client secrets are encrypted at rest, but administrative forms decrypted them and placed the plaintext value back into password input fields. That unnecessarily exposed secrets to the browser DOM, extensions, local inspection and accidental captures.

Round 16 never renders the stored secret. Password fields are blank on GET; submitting a blank value preserves the existing credential. Tests assert that known stored secrets are absent from rendered HTML.

### HIGH — Background scheduler work defaulted to the default tenant

Background threads have no authenticated request user. Tenant-aware setting helpers therefore fell back to the default tenant while deadline/reminder/backup schedulers could process records belonging to other tenants. This could apply the wrong timezone, notification settings, SMTP configuration, scheduler status or audit context to another tenant's work.

Round 16 adds an explicit `tenant_execution_context()` for non-request jobs. Deadline and reminder scheduler passes iterate tenants independently, and scheduled backups evaluate each job inside its owning tenant. Poll intervals are derived safely across tenants while per-tenant work remains isolated.

### HIGH — Audit retention and manual purge were global while retention settings are tenant-specific

Audit rows carry `tenant_id`, but normal retention, manual keep-count/older-than purge and the admin audit query used the global table. A tenant-specific retention action could therefore delete or expose another tenant's audit records.

Round 16 scopes normal retention, manual purge and the admin audit view to the active tenant. The request-user-free restore helper remains capable of global operation only when no tenant is explicitly supplied; when a tenant ID is supplied, its deletion/count/overflow operations are strictly tenant-scoped.

## Verification

- `python -m compileall -q app tests`: PASS.
- Pytest collection: 284 tests.
- Complete suite executed in isolated groups: 277 passed, 7 skipped, 0 failed.
- The 7 skipped tests are the opt-in real PostgreSQL integration tests; this runtime does not expose Docker/PostgreSQL.
- Round 16 targeted tests cover notification/template tenant isolation, AI tenant isolation and path confinement, secret non-reflection, background tenant execution, and tenant-scoped audit retention.
- No application dependency was changed in this round.

## Residual risk / next priorities

1. Execute the seven opt-in PostgreSQL tests on a Docker-capable host/CI and retain the results as release evidence.
2. Run complete transitive SCA/SBOM generation in a network-enabled CI environment and gate high/critical dependency findings.
3. Review production container/runtime settings, reverse-proxy headers, TLS termination, backup key custody, secret injection and least-privilege filesystem/database permissions.
4. Perform a final release-candidate regression using the exact production image and PostgreSQL version before tagging the hardened release.
