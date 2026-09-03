# Security Audit Round 13

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: Full Import failure injection, filesystem/database rollback boundaries, partial directory-swap recovery, and restore-state diagnostics.

## Confirmed finding and remediation

### HIGH - Failure between live-directory backup and staged-directory promotion could leave a managed volume absent

The Full Import filesystem transaction used a two-step directory swap for each managed persistent volume:

1. move the current live directory to a restore backup;
2. move the staged directory into the live path.

The transaction previously recorded a volume as activated only after step 2 completed. If step 1 succeeded but step 2 failed, rollback iterated only fully activated volumes and therefore did not restore the just-created backup for that partially swapped volume. The database transaction would roll back, but the affected live filesystem path could remain absent until manual recovery.

Round 13 tracks the destructive half of each swap immediately after the live directory is moved aside. Rollback now covers every touched volume, including volumes whose staged promotion never completed, and restores them in reverse transaction order.

### HIGH - A staging exception could leave temporary restore data because the transaction object was assigned too late

The Full Import route previously constructed and staged the filesystem transaction in one expression. If `stage()` raised, assignment to `fs_txn` never completed, so the route-level exception handler could not invoke the transaction cleanup logic.

Round 13 assigns the transaction object before calling `stage()`. Any staging failure is therefore handled by the same rollback/cleanup path as later failures.

### MEDIUM - Filesystem rollback failures were logged but the UI still reported successful preservation/restoration

Rollback intentionally remains best-effort if the underlying filesystem itself refuses recovery operations. Previously the route logged those failures but still displayed the generic message saying that previous volumes were maintained or restored.

Round 13 makes rollback return the groups that could not be recovered. Their backup state is retained for a later retry/manual recovery, the server emits a critical diagnostic, and the administrative UI explicitly warns that filesystem rollback is incomplete instead of claiming success.

## Failure-injection coverage

`tests/test_security_round13_failure_injection.py` verifies:

1. failure exactly between live-directory backup and staged-directory promotion restores the old directory;
2. a failure on the second managed volume rolls back both the partially swapped volume and earlier fully activated volumes;
3. if the first rollback attempt itself fails, restore-backup metadata/directories are retained and a later rollback retry succeeds;
4. the Full Import route keeps the transaction object before staging and invokes rollback cleanup on errors.

## Verification

- `python -m compileall -q app tests`: PASS.
- Full regression suite: `256 passed, 5 skipped`.
- The 5 skipped tests are the opt-in real PostgreSQL integration tests from Round 12; they require `CIR_POSTGRES_TEST_URL` or the Docker runner.
- Round 13 failure-injection suite: PASS.
- No production dependency versions changed.

## Residual risk / next priorities

1. Execute the Round 12 real PostgreSQL suite on a Docker/CI host and combine it with Full Import route-level failure injection against a disposable real database.
2. Add process-termination/crash testing around the short interval after filesystem activation and before database commit; Python exception rollback is now covered, while abrupt host/process loss requires startup recovery/journaling rather than in-process exception handling.
3. Consider a durable restore journal recording transaction token, managed paths and backup paths so startup can detect and safely reconcile an interrupted Full Import after power loss or SIGKILL.
4. Continue testing storage-specific behavior on NFS/Ceph/PVC implementations used in production, because directory rename atomicity and failure modes depend on the mounted filesystem.
