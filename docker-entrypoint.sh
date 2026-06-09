#!/bin/sh
set -eu

APP_UID="${APP_UID:-10001}"
APP_GID="${APP_GID:-10001}"
APP_USER="${APP_USER:-appuser}"
UPLOAD_DIR="${UPLOAD_DIR:-/data/uploads}"
LOGO_DIR="${LOGO_DIR:-/data/logo}"
FORM_TEMPLATE_DIR="${FORM_TEMPLATE_DIR:-/data/form_templates}"
SSO_LOGO_DIR="${SSO_LOGO_DIR:-/data/sso_logos}"
SSL_DIR="${SSL_DIR:-/data/ssl}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
AI_CHATBOT_DOC_DIR="${AI_CHATBOT_DOC_DIR:-/data/ai_chatbot_docs}"
DATA_DIRS="$UPLOAD_DIR $LOGO_DIR $FORM_TEMPLATE_DIR $SSO_LOGO_DIR $SSL_DIR $BACKUP_DIR $AI_CHATBOT_DOC_DIR"
RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE="${CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE:-1}"

warn() {
  echo "[entrypoint] WARNING: $*" >&2
}

info() {
  echo "[entrypoint] $*" >&2
}

shell_quote() {
  printf "%s" "$1" | sed "s/'/'\\''/g; 1s/^/'/; \$s/\$/'/"
}

can_write_as_appuser() {
  dir="$1"
  if [ "$(id -u)" != "0" ]; then
    [ -w "$dir" ]
    return $?
  fi
  qdir="$(shell_quote "$dir")"
  gosu "$APP_USER" sh -c "test -d $qdir && test -w $qdir"
}

prepare_writable_dirs() {
  PERMISSION_FAILURE=0
  for dir in $DATA_DIRS; do
    [ -n "$dir" ] || continue
    mkdir -p "$dir" 2>/dev/null || {
      warn "unable to create persistent directory $dir"
      PERMISSION_FAILURE=1
      continue
    }
    if [ "$(id -u)" = "0" ]; then
      chown -R "${APP_UID}:${APP_GID}" "$dir" 2>/dev/null || true
      chmod -R u+rwX,g+rwX "$dir" 2>/dev/null || true
      if ! can_write_as_appuser "$dir"; then
        # Last-resort compatibility for pre-existing Docker bind mounts or
        # volumes created with restrictive ownership. This keeps named volumes
        # non-root writable in the normal case, while still preventing startup
        # failures on installations where chown is blocked by the host FS.
        chmod -R a+rwX "$dir" 2>/dev/null || true
      fi
    fi
    if ! can_write_as_appuser "$dir"; then
      warn "persistent directory is not writable by ${APP_USER} (${APP_UID}:${APP_GID}): $dir"
      PERMISSION_FAILURE=1
    fi
  done
}

copy_missing_files() {
  src_dir="$1"
  dst_dir="$2"
  [ -d "$src_dir" ] || return 0
  mkdir -p "$dst_dir" 2>/dev/null || return 0
  for src in "$src_dir"/*; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    dst="$dst_dir/$name"
    if [ ! -e "$dst" ]; then
      cp "$src" "$dst" 2>/dev/null || warn "unable to seed persistent asset $dst"
    fi
  done
  if [ "$(id -u)" = "0" ]; then
    chown -R "${APP_UID}:${APP_GID}" "$dst_dir" 2>/dev/null || true
    chmod -R u+rwX,g+rwX "$dst_dir" 2>/dev/null || true
  fi
}

seed_persistent_assets() {
  # Copy defaults before dropping privileges. This prevents startup crashes when
  # the app imports and tries to initialize /data/sso_logos or /data/form_templates
  # on a fresh persistent volume.
  copy_missing_files "/app/app/static/sso" "$SSO_LOGO_DIR"
  copy_missing_files "/app/app/form_templates" "$FORM_TEMPLATE_DIR"
}

if [ "${1:-}" != "--as-appuser" ]; then
  prepare_writable_dirs
  seed_persistent_assets
  if [ "$(id -u)" = "0" ]; then
    if [ "${PERMISSION_FAILURE:-0}" = "1" ] && [ "$RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE" = "1" ]; then
      warn "one or more persistent volumes are not writable by ${APP_USER}; continuing as root to avoid startup failure. Fix ownership or set APP_UID/APP_GID to the host volume owner for a non-root runtime."
    else
      if [ "${PERMISSION_FAILURE:-0}" = "1" ]; then
        echo "[entrypoint] ERROR: persistent volumes are not writable by ${APP_USER}." >&2
        echo "[entrypoint] Set APP_UID/APP_GID to match the host directory owner, fix volume ownership, or set CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE=1." >&2
        exit 1
      fi
      info "starting as ${APP_USER} (${APP_UID}:${APP_GID})"
      exec gosu "${APP_USER}" "$0" --as-appuser
    fi
  fi
fi
[ "${1:-}" = "--as-appuser" ] && shift

HTTP_PORT="${PORT:-8000}"
HTTPS_PORT="${SSL_PORT:-8443}"
DEFAULT_CERT="$SSL_DIR/current.crt"
DEFAULT_KEY="$SSL_DIR/current.key"
SSL_MARKER="$SSL_DIR/enabled"
# Prefer project-specific names for listener certificates. The generic
# SSL_CERT_FILE name is also used by many runtimes as an outbound CA bundle, so
# only treat SSL_CERT_FILE/SSL_KEY_FILE as listener paths when both are set.
if [ -n "${CIR_SSL_CERT_FILE:-}" ] || [ -n "${CIR_SSL_KEY_FILE:-}" ]; then
  CERT_FILE="${CIR_SSL_CERT_FILE:-$DEFAULT_CERT}"
  KEY_FILE="${CIR_SSL_KEY_FILE:-$DEFAULT_KEY}"
elif [ -n "${SSL_CERT_FILE:-}" ] && [ -n "${SSL_KEY_FILE:-}" ]; then
  CERT_FILE="$SSL_CERT_FILE"
  KEY_FILE="$SSL_KEY_FILE"
else
  CERT_FILE="$DEFAULT_CERT"
  KEY_FILE="$DEFAULT_KEY"
fi
export CIR_RUNTIME_SSL_CERT_FILE="$CERT_FILE"
export CIR_RUNTIME_SSL_KEY_FILE="$KEY_FILE"
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

ensure_https_certificate() {
  if python -m app.ssl_certificates >/tmp/cir_ssl_status 2>/tmp/cir_ssl_error; then
    info "HTTPS certificate ready: $(cat /tmp/cir_ssl_status 2>/dev/null || true)"
    return 0
  fi
  warn "HTTPS certificate is not ready: $(cat /tmp/cir_ssl_status 2>/dev/null || cat /tmp/cir_ssl_error 2>/dev/null || true)"
  return 1
}

certificate_state() {
  cert_state="missing"
  key_state="missing"
  marker_state="missing"
  [ -e "$CERT_FILE" ] && cert_state="$(stat -c '%Y:%s:%n' "$CERT_FILE" 2>/dev/null || echo changed)"
  [ -e "$KEY_FILE" ] && key_state="$(stat -c '%Y:%s:%n' "$KEY_FILE" 2>/dev/null || echo changed)"
  [ -e "$SSL_DIR/user_provided" ] && marker_state="$(stat -c '%Y:%s:%n' "$SSL_DIR/user_provided" 2>/dev/null || echo changed)"
  printf '%s|%s|%s' "$cert_state" "$key_state" "$marker_state"
}

start_https() {
  if ! ensure_https_certificate; then
    return 1
  fi
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
HTTPS_CERT_STATE=""

while kill -0 "$HTTP_PID" 2>/dev/null; do
  if is_enabled; then
    NEXT_CERT_STATE="$(certificate_state)"
    if [ -n "${HTTPS_PID:-}" ] && kill -0 "$HTTPS_PID" 2>/dev/null && [ "$NEXT_CERT_STATE" != "$HTTPS_CERT_STATE" ]; then
      info "HTTPS certificate files changed; restarting HTTPS listener"
      stop_https
    fi
    if [ -z "${HTTPS_PID:-}" ] || ! kill -0 "$HTTPS_PID" 2>/dev/null; then
      if start_https; then
        HTTPS_CERT_STATE="$(certificate_state)"
      fi
    fi
  else
    stop_https
    HTTPS_CERT_STATE=""
  fi
  sleep 10 &
  wait $! || true
done

stop_https
wait "$HTTP_PID" 2>/dev/null || true
