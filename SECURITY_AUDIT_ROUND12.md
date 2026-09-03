# Security Audit Round 12

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: real PostgreSQL integration-test infrastructure for destructive restore, advisory locks, sequence alignment, and multi-worker coordination.

## Changes

Round 12 adds an opt-in real PostgreSQL test layer without changing production behavior:

- `docker-compose.test.yml` starts an isolated PostgreSQL 18.4 service on host port `55432` by default, backed by tmpfs.
- `scripts/run_postgres_tests.sh` starts the service with Docker Compose, waits for health, runs only `pytest -m postgres`, and always tears the test service down.
- `pytest.ini` registers the `postgres` marker.
- `tests/test_postgresql_real_integration.py` skips automatically unless `CIR_POSTGRES_TEST_URL` is configured and reachable.

## Real PostgreSQL coverage

The integration suite verifies on an actual PostgreSQL server:

1. Two different backup jobs can hold the shared maintenance boundary concurrently while Full Import is excluded.
2. An exclusive Full Import lock excludes backups.
3. The same backup job is mutually exclusive across independent worker/thread connections.
4. Explicit primary-key imports followed by `align_table_sequence()` generate the expected next ID.
5. Transactional PostgreSQL DDL rollback restores the previous table and rows after a DROP/CREATE/reload failure sequence.
6. PostgreSQL session advisory locks disappear when the owning connection closes, matching worker-crash recovery expectations.

## Execution

Normal/offline suite:

    pytest

Real PostgreSQL suite with Docker:

    ./scripts/run_postgres_tests.sh

Or against an existing PostgreSQL server:

    CIR_POSTGRES_TEST_URL='postgresql+psycopg2://user:password@host:5432/db' pytest -m postgres

The supplied test database must be disposable: integration tests create and drop uniquely named scratch tables and acquire advisory locks.

## Environment limitation during this audit

The audit runtime used to build Round 12 does not expose the Docker CLI or a PostgreSQL daemon, so the real-server tests cannot be executed here. They are deliberately skipped in the normal suite when no PostgreSQL test URL is supplied. Static validation and the complete existing regression suite remain mandatory before packaging.
