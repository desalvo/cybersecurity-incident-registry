# Security Audit Round 11

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: PostgreSQL backup/restore concurrency coordination, advisory-lock isolation, connection cleanup, and regression coverage.

## Confirmed finding and remediation

### HIGH - Backup snapshots could overlap a destructive Full Import

Backup execution and Full Import previously used independent advisory locks. Backups were serialized per backup job and Full Imports were serialized against other Full Imports, but a backup could still read the database and persistent volumes while a Full Import was transactionally replacing those same resources. The resulting archive could therefore combine data from different restore states.

Round 11 introduces a common maintenance boundary. PostgreSQL backup workers acquire a **shared** advisory lock on the maintenance key, while Full Import acquires the **exclusive** form of the same lock. Multiple independent backups may still run concurrently, but no backup can overlap a destructive Full Import across workers or replicas. Non-PostgreSQL development/test execution uses the existing process-local locking model with the same mutual-exclusion intent.

### MEDIUM - Backup job advisory IDs shared the one-key integer space with the Full Import lock

The prior backup key was calculated as `47120000 + job_id`, while Full Import used `47129999`. Backup job ID 9999 therefore produced the same advisory key. Round 11 moves per-job backup locking to PostgreSQL's two-key advisory-lock form with a dedicated namespace (`namespace`, `job_id`), which is distinct from the single-key maintenance lock space.

### MEDIUM - PostgreSQL detection depended on URL string formatting

Lock selection previously tested `str(db.engine.url).startswith('postgresql')`. Round 11 checks SQLAlchemy's resolved dialect name instead, so driver-qualified PostgreSQL URLs and future URL formatting changes do not change concurrency behavior.

## Verification

- Dynamic mocked-PostgreSQL tests exercise shared backup lock acquisition/release, busy job cleanup, exclusive Full Import lock acquisition/release, and busy-lock connection cleanup.
- Static regression tests verify distinct advisory-lock namespaces and dialect-based PostgreSQL detection.
- Full application test suite remains mandatory before packaging.

## Residual priorities

1. Run the same restore/backup concurrency scenarios against a real PostgreSQL service in CI, including two independent processes/connections.
2. Exercise forced commit failure after filesystem activation and verify database + persistent-directory rollback end-to-end.
3. Verify sequence alignment with explicit high imported IDs against real PostgreSQL `setval`/`nextval` behavior.
