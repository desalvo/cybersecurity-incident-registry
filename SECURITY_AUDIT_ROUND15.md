# Security Audit Round 15

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: real process-termination semantics for Full Import crash recovery, PostgreSQL crash/restart coverage, and safety of the destructive integration-test harness.

## Confirmed findings and remediation

### HIGH - Round 14 recovery had only exception/failure-injection coverage, not actual process death

Round 14 made Full Import crash recovery durable and unit-tested the journal/commit-token decision. Those tests could not prove that the mechanism still works when the restoring Python process disappears without executing any `except`, `finally`, SQLAlchemy session cleanup, or filesystem-transaction cleanup.

Round 15 adds an external crash worker used by integration tests. The worker activates the production `_FullImportFilesystemTransaction`, writes the real recovery journal and database commit marker, then pauses at a controlled checkpoint. The parent process terminates it with `SIGKILL` and creates a fresh Flask/SQLAlchemy context to run startup recovery. Two windows are exercised:

- pre-commit `SIGKILL`: the uncommitted database marker disappears when the process/database connection dies, so startup restores the previous filesystem snapshot;
- post-commit `SIGKILL`: the durable marker proves the database commit completed, so startup keeps the promoted filesystem and finalizes stale stage/backup artifacts.

The standard suite executes both process-death scenarios with SQLite to validate kernel/process semantics even without Docker. The opt-in real PostgreSQL suite now repeats both scenarios against the disposable PostgreSQL service, covering actual PostgreSQL transaction/session behavior.

### MEDIUM - Manually configured PostgreSQL integration URL could accidentally target a non-test database

`CIR_POSTGRES_TEST_URL` previously accepted any reachable PostgreSQL database. Round 15 crash tests intentionally use application tables such as `Setting`, so accidentally pointing the test suite at a production-like database would be unsafe.

The PostgreSQL integration fixture now refuses database names that do not contain `test` unless `CIR_POSTGRES_TEST_ALLOW_NONTEST_DATABASE=1` is explicitly set. The override is documented only for isolated disposable CI databases. The default Docker service continues to use `cir_test` and requires no override.

## Verification

- External `SIGKILL` crash/restart tests on SQLite: 2 passed.
- Full suite without PostgreSQL service: 265 passed, 7 skipped.
- The 7 skips are the opt-in real PostgreSQL integration tests: the previous five Round 12 tests plus two Round 15 real-PostgreSQL `SIGKILL` scenarios.
- `python -m compileall -q app tests`: PASS.
- Shell syntax checks for project scripts: PASS.
- No application dependency changes.

## Residual risk / next priorities

1. Run `./scripts/run_postgres_tests.sh` on a Docker-capable host/CI runner and record the seven real-PostgreSQL results; this execution environment still has no Docker daemon.
2. Validate crash durability on the production storage classes actually used in deployment (Docker local volumes, ext4/xfs, and any NFS/network-backed PVC), because rename/fsync durability guarantees are filesystem-specific.
3. Perform the final cross-cutting application security audit (authentication/session boundaries, tenant isolation, filesystem/configuration trust boundaries, outbound HTTP, backup/import/export, secret handling).
4. Regenerate a transitive SBOM/SCA report in network-enabled CI before release-candidate packaging.
