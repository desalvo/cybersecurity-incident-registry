# Security Audit - Round 5

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: database/business logic, tenant integrity, backup concurrency, restore/import boundaries, and dependency review.

## Confirmed findings and remediation

### HIGH - Backup administration was not tenant-scoped
`/admin/backups` selected the first `BackupJob` globally. A tenant administrator could therefore view or update a job belonging to another tenant (or a shared/global job). The route now selects/creates only the `BackupJob` for the active tenant. Backup notification recipients are also selected from administrators of the job tenant.

### HIGH - Tenant admins could choose an arbitrary writable local backup directory
`local_path` was accepted from the form and used as a server filesystem destination. Tenant jobs now always write below `BACKUP_DIR/tenant-<id>`. Global/local paths are constrained below `BACKUP_DIR` by `_safe_backup_local_path()`.

### HIGH - Duplicate backup execution across workers/replicas
The backup scheduler had only per-process minute state and could run the same job in multiple Gunicorn workers or Kubernetes replicas. All on-demand and scheduled executions now pass through `execute_backup_job_serialized()`. PostgreSQL deployments use a dedicated-connection advisory lock per backup job; non-PostgreSQL development uses a non-blocking process lock.

### CRITICAL - Tenant import reused global primary keys
Tenant-scoped archives contained database primary keys from the source installation. Import into another tenant could collide with IDs owned by another tenant, causing integrity failures or cross-tenant reference corruption. Tenant import now allocates fresh IDs and explicitly remaps dependent foreign keys and association-table rows.

### CRITICAL - Tenant import could overwrite another tenant's physical uploads
Document and action attachment `stored_name` values were trusted from the archive and written into the shared upload directory. A crafted tenant archive could target an existing stored filename. Imported files now receive new UUID-based physical names; database rows and archive file copies are remapped, and files are created with exclusive mode (`xb`) and mode 0600 where supported.

### MEDIUM - Derived scheduler state imported across tenants
`DeadlineNotificationState.notification_key` is globally unique and represents runtime/idempotency state. It is no longer imported in tenant-to-tenant restore. The scheduler recreates state naturally.

### HIGH - Residual tenant isolation bugs in administrative data
External recipient save/list/duplicate checks and NotificationType edit paths contained unscoped queries. These now use `tenant_query()` / `model_or_404()`. New notification types are assigned to the active tenant. The administrative status page now reports incident/reminder/backup counts only for the active tenant.

### MEDIUM - Exception disclosure in CSV import
CSV import no longer flashes raw exception text to the user. Detailed diagnostics remain in server logs.

### HIGH - Vulnerable Pillow dependency
`Pillow==12.2.0` is affected by CVE-2026-59203 (crafted EPS can cause an infinite parsing loop / denial of service). The requirement is updated to `Pillow==12.3.0`, where the issue is fixed.

## Dependency review notes

The pinned Flask 3.1.3 includes the fix for CVE-2026-27205. pypdf 6.10.2 includes the fix for CVE-2026-41313. cryptography 46.0.7 includes the fix for CVE-2026-39892. A complete transitive-dependency audit should still be run in CI with `pip-audit` or an equivalent scanner because this environment cannot resolve/install packages from PyPI.

## Verification

- `python -m compileall -q app tests`: PASS.
- `python tests/test_security_round5_invariants.py`: PASS.
- Static regression checks cover tenant-scoped backup administration, local backup path confinement, tenant import ID/file remapping, tenant-scoped administrative child queries, and the Pillow security floor.

## Residual risk / next priorities

1. Make full destructive restore filesystem operations transactional/staged so a DB rollback cannot leave partially replaced persistent files.
2. Add database-level uniqueness/ownership constraints where practical for tenant-scoped records and child entities.
3. Run the full pytest suite and a real PostgreSQL multi-worker concurrency test in CI.
4. Run complete SCA/SBOM generation for direct and transitive Python/system dependencies.
