#!/bin/sh
set -eu

HTTP_PORT="${PORT:-8000}"
HTTPS_PORT="${SSL_PORT:-8443}"
SSL_DIR="${SSL_DIR:-/data/ssl}"
DEFAULT_CERT="$SSL_DIR/current.crt"
DEFAULT_KEY="$SSL_DIR/current.key"
SSL_MARKER="$SSL_DIR/enabled"
CERT_FILE="${SSL_CERT_FILE:-$DEFAULT_CERT}"
KEY_FILE="${SSL_KEY_FILE:-$DEFAULT_KEY}"
mkdir -p "$SSL_DIR"

is_enabled() {
  case "${SSL_ENABLED:-0}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
  esac
  [ -f "$SSL_MARKER" ]
}

start_http() {
  gunicorn --bind "0.0.0.0:${HTTP_PORT}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-180}" \
    --access-logfile - --error-logfile - wsgi:app &
  HTTP_PID=$!
}

start_https() {
  gunicorn --bind "0.0.0.0:${HTTPS_PORT}" \
    --certfile "$CERT_FILE" --keyfile "$KEY_FILE" \
    --workers "${WEB_CONCURRENCY_SSL:-${WEB_CONCURRENCY:-1}}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-180}" \
    --access-logfile - --error-logfile - wsgi:app &
  HTTPS_PID=$!
  echo "HTTPS listener started on port ${HTTPS_PORT} with certificate ${CERT_FILE}"
}

stop_https() {
  if [ -n "${HTTPS_PID:-}" ] && kill -0 "$HTTPS_PID" 2>/dev/null; then
    kill "$HTTPS_PID" 2>/dev/null || true
    wait "$HTTPS_PID" 2>/dev/null || true
  fi
  HTTPS_PID=""
}

shutdown() {
  stop_https
  if [ -n "${HTTP_PID:-}" ] && kill -0 "$HTTP_PID" 2>/dev/null; then
    kill "$HTTP_PID" 2>/dev/null || true
    wait "$HTTP_PID" 2>/dev/null || true
  fi
  exit 0
}
trap shutdown INT TERM

start_http
HTTPS_PID=""

while kill -0 "$HTTP_PID" 2>/dev/null; do
  if is_enabled && [ -r "$CERT_FILE" ] && [ -r "$KEY_FILE" ]; then
    if [ -z "${HTTPS_PID:-}" ] || ! kill -0 "$HTTPS_PID" 2>/dev/null; then
      start_https
    fi
  else
    stop_https
  fi
  sleep 10 &
  wait $! || true
done

stop_https
wait "$HTTP_PID" 2>/dev/null || true
