#!/usr/bin/env bash
set -Eeuo pipefail

# Configure a local DNS stub resolver for CI jobs before running networked
# dependency audits. This avoids pip-audit failures caused by broken default
# resolver injection in container/runner environments.
#
# Default behavior:
# - prefer systemd-resolved local stub on 127.0.0.53;
# - route the selected network interface to explicit upstream resolvers;
# - verify resolution of PyPI and OSV endpoints used by pip-audit.
#
# Environment knobs:
# - AGID_LOCAL_DNS_SERVER: local stub IP, default 127.0.0.53
# - AGID_DNS_UPSTREAMS: space-separated upstream resolvers, default "1.1.1.1 8.8.8.8"
# - AGID_DNS_TEST_HOSTS: space-separated hostnames to resolve.

LOCAL_DNS="${AGID_LOCAL_DNS_SERVER:-127.0.0.53}"
UPSTREAMS="${AGID_DNS_UPSTREAMS:-1.1.1.1 8.8.8.8}"
TEST_HOSTS="${AGID_DNS_TEST_HOSTS:-pypi.org api.osv.dev}"
BACKUP_RESOLV=""
if [[ -e /etc/resolv.conf ]]; then
  BACKUP_RESOLV="$(mktemp)"
  cp /etc/resolv.conf "$BACKUP_RESOLV" || BACKUP_RESOLV=""
fi
restore_resolv() {
  if [[ -n "$BACKUP_RESOLV" && -s "$BACKUP_RESOLV" ]]; then
    if [[ "${EUID}" -eq 0 ]]; then
      cp "$BACKUP_RESOLV" /etc/resolv.conf || true
    elif command -v sudo >/dev/null 2>&1; then
      sudo cp "$BACKUP_RESOLV" /etc/resolv.conf || true
    fi
  fi
}

log() { printf '[agid-dns] %s\n' "$*"; }

require_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    log "sudo non disponibile e utente non root: impossibile modificare DNS di sistema"
    return 1
  fi
}

verify_resolution() {
  local failed=0
  for host in $TEST_HOSTS; do
    if getent hosts "$host" >/dev/null 2>&1; then
      log "risoluzione OK: $host"
    else
      log "risoluzione KO: $host"
      failed=1
    fi
  done
  return "$failed"
}

if command -v resolvectl >/dev/null 2>&1; then
  IFACE="${AGID_DNS_INTERFACE:-$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')}"
  if [[ -n "${IFACE:-}" ]]; then
    log "configuro systemd-resolved su interfaccia $IFACE con upstream: $UPSTREAMS"
    require_sudo resolvectl dns "$IFACE" $UPSTREAMS || true
    require_sudo resolvectl domain "$IFACE" '~.' || true
    require_sudo resolvectl flush-caches || true
  else
    log "interfaccia default non rilevata; salto configurazione resolvectl per interfaccia"
  fi

  if [[ -e /run/systemd/resolve/stub-resolv.conf ]]; then
    log "uso resolver locale systemd-resolved $LOCAL_DNS"
    require_sudo ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf || true
  elif [[ -w /etc/resolv.conf || "${EUID}" -eq 0 || -n "$(command -v sudo || true)" ]]; then
    log "stub file non trovato; scrivo /etc/resolv.conf verso $LOCAL_DNS"
    printf 'nameserver %s\noptions timeout:2 attempts:2 rotate\n' "$LOCAL_DNS" | require_sudo tee /etc/resolv.conf >/dev/null || true
  fi
else
  log "resolvectl non disponibile; provo a usare direttamente il resolver locale $LOCAL_DNS"
  printf 'nameserver %s\noptions timeout:2 attempts:2 rotate\n' "$LOCAL_DNS" | require_sudo tee /etc/resolv.conf >/dev/null || true
fi

if verify_resolution; then
  exit 0
fi

log "resolver locale non funzionante; ripristino la configurazione DNS precedente"
restore_resolv
exit 1
