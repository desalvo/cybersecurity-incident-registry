#!/bin/sh
set -eu

COMPOSE_FILE=${CIR_POSTGRES_TEST_COMPOSE_FILE:-docker-compose.test.yml}
PORT=${CIR_POSTGRES_TEST_PORT:-55432}
DATABASE_URL=${CIR_POSTGRES_TEST_URL:-postgresql+psycopg2://cir_test:cir_test_password@127.0.0.1:${PORT}/cir_test}

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker non disponibile: impossibile avviare PostgreSQL reale." >&2
    exit 2
fi

cleanup() {
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker compose -f "$COMPOSE_FILE" up -d --wait postgres-test
CIR_POSTGRES_TEST_URL="$DATABASE_URL" \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
CIR_DISABLE_BACKGROUND_SCHEDULERS=1 \
python -m pytest -m postgres "$@"
