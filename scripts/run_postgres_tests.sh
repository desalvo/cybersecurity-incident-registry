#!/bin/sh
set -eu

COMPOSE_FILE=${CIR_POSTGRES_TEST_COMPOSE_FILE:-docker-compose.test.yml}
PORT=${CIR_POSTGRES_TEST_PORT:-55432}
DATABASE_URL=${CIR_POSTGRES_TEST_URL:-postgresql+psycopg2://cir_test:cir_test_password@127.0.0.1:${PORT}/cir_test}
TEST_TIMEOUT=${CIR_POSTGRES_TEST_TIMEOUT:-900}

if ! command -v docker >/dev/null 2>&1; then
    echo 'Docker is required for real PostgreSQL tests.' >&2
    exit 2
fi
if ! command -v timeout >/dev/null 2>&1; then
    echo 'GNU timeout is required to bound PostgreSQL tests.' >&2
    exit 2
fi

cleanup() {
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

postgres_diagnostics() {
    echo '=== PostgreSQL activity and wait diagnostics ===' >&2
    docker compose -f "$COMPOSE_FILE" exec -T postgres-test \
        psql -U cir_test -d cir_test -X -P pager=off -c \
        "SELECT pid, state, wait_event_type, wait_event, now()-query_start AS query_age, left(query, 400) AS query FROM pg_stat_activity WHERE datname = current_database() ORDER BY query_start NULLS LAST" >&2 || true
    echo '=== Blocking PostgreSQL sessions ===' >&2
    docker compose -f "$COMPOSE_FILE" exec -T postgres-test \
        psql -U cir_test -d cir_test -X -P pager=off -c \
        "SELECT a.pid, a.state, a.wait_event_type, a.wait_event, pg_blocking_pids(a.pid) AS blocked_by, left(a.query, 250) AS query FROM pg_stat_activity a WHERE a.datname=current_database() ORDER BY a.pid" >&2 || true
    echo '=== PostgreSQL container logs ===' >&2
    docker compose -f "$COMPOSE_FILE" logs --tail 120 postgres-test >&2 || true
}

docker compose -f "$COMPOSE_FILE" up -d --wait postgres-test

# Verbose reporting prints the currently executing test before fixtures start.
# PostgreSQL timeouts prevent a waiting lock/query from consuming the whole CI job.
# Pytest's faulthandler prints Python stacks if an individual test stalls.
set +e
CIR_POSTGRES_TEST_URL="$DATABASE_URL" \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
CIR_DISABLE_BACKGROUND_SCHEDULERS=1 \
PGOPTIONS='-c statement_timeout=120000 -c lock_timeout=30000 -c idle_in_transaction_session_timeout=120000' \
timeout -k 15s "${TEST_TIMEOUT}s" python -m pytest -m postgres -vv -s -o faulthandler_timeout=90 "$@"
status=$?
set -e
if [ "$status" -ne 0 ]; then
    echo "PostgreSQL test suite exited with status $status (124 means timeout)." >&2
    postgres_diagnostics
fi
exit "$status"
