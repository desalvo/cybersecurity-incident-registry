# Security Audit Round 6

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: database/business-logic integrity, destructive restore atomicity, multi-worker concurrency, parent/child ownership constraints, and dependency maintenance.

## Confirmed findings and remediations

### CRITICAL — Full Import was not transactional across database and persistent volumes

The previous Full Import recreated the database with `db.drop_all()` / `db.create_all()` and committed that schema change before all imported rows and persistent files had been restored. Persistent files were then written directly over the live volumes. A later exception could therefore leave either a destroyed/partially restored database or a partially replaced filesystem.

Round 6 performs PostgreSQL DDL through the active SQLAlchemy session connection, so schema replacement and row loading remain in the same transaction. Persistent data is extracted and validated into staging directories located next to each destination, then activated with reversible `os.replace()` directory swaps only after DB loading succeeds. If commit fails, the database transaction is rolled back and the prior filesystem directories are restored. Backups of replaced directories are deleted only after the DB commit succeeds.

### HIGH — Full restore could leave stale persistent files

Direct overwrite restored files present in the archive but did not guarantee that files absent from the archive disappeared. Current full exports now restore managed persistent groups as snapshots: the staged directory replaces the old directory, so stale files do not survive a successful full restore. Legacy archives that do not declare a persistent group preserve unrepresented groups rather than deleting them.

### HIGH — Concurrent import/restore across Gunicorn workers or replicas

Two workers could previously start destructive imports concurrently. Round 6 serializes all full/tenant imports with a PostgreSQL advisory lock held on a dedicated connection. Non-PostgreSQL development/test environments use a process-local non-blocking lock.

### HIGH — Tenant import could leave filesystem orphans after DB rollback

Tenant import intentionally creates new UUID-backed upload files before commit. If the database transaction failed, those new files remained orphaned. Round 6 records every newly created physical file and removes it when the tenant import transaction fails.

### HIGH — Archive relational/file integrity was trusted too late

Full-import payloads are now validated before database recreation. The validator rejects duplicate primary IDs, actions/documents/reminders referencing missing incidents, attachments referencing missing actions, unsafe `stored_name` values, and duplicate physical `stored_name` claims across documents and action attachments sharing the upload directory.

### HIGH — Parent/child ownership was primarily application-enforced

New/rebuilt schemas now declare incident ownership FKs for Action, Document and IncidentReminder, and ActionAttachment -> Action, as `NOT NULL` with `ON DELETE CASCADE`. Existing PostgreSQL schemas are hardened during startup only when no NULL/orphan rows exist. If legacy inconsistent rows are found, startup remains non-destructive and emits a warning so they can be repaired manually before the constraint is applied.

## Dependency maintenance

Round 6 updates:

- `gunicorn` 23.0.0 -> 26.2.0. The upstream security policy no longer lists 23.0.0 as a supported security branch; 26.x is supported and 26.2.0 is the current PyPI release at audit time.
- `Werkzeug` 3.1.6 -> 3.1.8. 3.1.6 already contained the February 2026 `safe_join` security fix; 3.1.7/3.1.8 add stricter Host / Transfer-Encoding parsing and subsequent compatibility correction.

No forced update was made to `ldap3`: PyPI still lists 2.9.1 as the latest stable release, with 2.10.2rc4 only a pre-release at audit time. Flask-SQLAlchemy 3.1.1 also remains the latest stable PyPI release.

`SBOM_ROUND6.cdx.json` records the directly pinned production dependencies. A complete transitive SBOM/SCA still requires dependency resolution in a network-enabled build environment; this analysis environment cannot install the project requirements from PyPI.

## Verification

- `python -m compileall app tests`: PASS
- `pytest -q tests/test_security_round6_invariants.py`: 8 passed
- `sh -n docker-entrypoint.sh`: PASS
- Full pytest collection discovers 218 tests before stopping on two import errors because Flask is not installed in the analysis environment.

## Deployment notes

Before production deployment, build the image from this source so the updated dependency pins are resolved inside the normal Docker build. For existing PostgreSQL installations, review startup logs for `Schema hardening skipped` warnings; any reported NULL/orphan child rows should be repaired before relying on DB-level ownership constraints.
