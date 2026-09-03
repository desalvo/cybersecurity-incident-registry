# Security Audit Round 14

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: crash consistency of destructive Full Import, durable filesystem recovery, database/filesystem commit disambiguation, startup recovery ordering, and multi-worker recovery serialization.

## Confirmed finding and remediation

### CRITICAL - Process/host crash could leave database and persistent volumes on different restore generations

Round 13 made ordinary Python exceptions recoverable, including failures during directory swaps and rollback. A hard termination (`SIGKILL`, container/host crash, power loss) is different: no `except`/`finally` handler runs. If the process died after persistent directories had been promoted but before the database transaction committed, PostgreSQL would roll back the database while the new filesystem snapshot remained active. Conversely, if the database commit completed and the process died before old filesystem backups were removed, startup needed a reliable way to distinguish a committed restore from an uncommitted one.

Round 14 adds a durable Full Import recovery journal under `BACKUP_DIR`. The journal is written atomically with `fsync` before destructive filesystem renames and records only a validated restore token plus managed-group state; recovery paths are always re-derived from configured managed directories rather than trusted from journal-provided arbitrary paths.

A reserved Full Import commit token is written to `Setting` inside the same database transaction as the restored data. On startup, before bootstrap writes occur:

- a matching database token proves the destructive database transaction committed, so the promoted filesystem snapshot is kept and stale backup/staging directories are finalized;
- a missing/non-matching token means the database transaction did not commit, so previous persistent directories are restored from their durable backups and newly-created volumes with no predecessor are removed;
- malformed journals fail closed without modifying live volumes;
- a stale database marker left after successful journal cleanup is harmless and is removed on the next startup.

Journal state is advanced around each destructive rename (`moving_backup`, `backup_moved`, `promoting`, `activated`, `restoring`, `removing_new`, `finalizing`) so recovery remains idempotent across another crash during recovery itself. Directory renames are followed by best-effort parent-directory `fsync`.

### HIGH - Concurrent workers could race startup recovery

PostgreSQL startup recovery now runs while holding the same exclusive maintenance advisory-lock namespace used by Full Import. This prevents another worker/replica from running backup/restore maintenance while recovery decides whether the database/filesystem restore committed. Non-PostgreSQL development environments continue to use the process-local maintenance lock.

## Verification

- `python -m compileall -q app tests`: PASS.
- Round 11 + Round 13 + Round 14 focused tests: 17 passed.
- Full suite: 263 passed, 5 skipped.
- The 5 skipped tests are the existing opt-in real PostgreSQL integration tests from Round 12 because this execution environment does not expose a PostgreSQL/Docker service.
- New Round 14 tests exercise pre-commit crash rollback, post-commit crash finalization, restoration when no prior directory existed, malformed-journal fail-closed behavior, startup ordering, commit-token ordering, and PostgreSQL advisory-lock coverage.

## Residual risk / next priorities

1. Execute the existing opt-in integration suite against the disposable PostgreSQL Docker service and add a real PostgreSQL crash/restart scenario around the Round 14 commit token.
2. Exercise actual worker termination (`SIGKILL`) from an external test harness while Full Import is paused at controlled checkpoints; unit failure injection cannot perfectly emulate kernel/container termination semantics.
3. Review durability assumptions for filesystems/storage classes used in production (local ext4/xfs, Docker volumes, NFS/network storage); rename/fsync guarantees vary by storage backend.
4. Continue final cross-cutting security audit and dependency/SBOM work before release-candidate packaging.
