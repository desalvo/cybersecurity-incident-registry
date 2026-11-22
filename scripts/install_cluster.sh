#!/usr/bin/env bash
# Render by default; --apply explicitly installs/upgrades the named Helm release.
set -euo pipefail
umask 077
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="kubernetes"
NAMESPACE="cir"
RELEASE="cir"
VALUES=""
OUTPUT=""
APPLY=0
usage() {
  cat <<'USAGE'
Usage: scripts/install_cluster.sh --values production-values.yaml [options]
  --platform kubernetes|openshift   Default: kubernetes
  --namespace NAME                 Existing namespace/project (default cir)
  --release NAME                   Helm release name (default cir)
  --output FILE                    Save rendered manifests (default stdout)
  --apply                          Validate against the server and install/upgrade

Requires Helm 3.14+ (major 3), Python3 and PyYAML. --apply additionally
requires kubectl (Kubernetes) or oc (OpenShift), an existing namespace and Secrets.
No image is built, promoted, or selected from latest. Credentials stay in Secrets.
USAGE
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform|--namespace|--release|--values|--output)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      case "$1" in
        --platform) PLATFORM="$2" ;;
        --namespace) NAMESPACE="$2" ;;
        --release) RELEASE="$2" ;;
        --values) VALUES="$2" ;;
        --output) OUTPUT="$2" ;;
      esac
      shift 2 ;;
    --apply) APPLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ "$PLATFORM" == kubernetes || "$PLATFORM" == openshift ]] || { echo 'Invalid platform' >&2; exit 2; }
[[ "$NAMESPACE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && ${#NAMESPACE} -le 63 ]] || { echo 'Invalid namespace' >&2; exit 2; }
[[ "$RELEASE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && ${#RELEASE} -le 53 ]] || { echo 'Invalid Helm release name' >&2; exit 2; }
[[ -n "$VALUES" && -f "$VALUES" ]] || { echo '--values must name your production values file' >&2; exit 2; }
command -v helm >/dev/null 2>&1 || { echo 'Install Helm 3.14+ (major 3) first.' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo 'Python3 is required.' >&2; exit 1; }
python3 "$ROOT_DIR/scripts/check_installation_package.py" --check-helm-version >&2
CHART="$ROOT_DIR/charts/cybersecurity-incident-registry"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
VALUES_ARGS=()
if [[ "$PLATFORM" == openshift ]]; then
  VALUES_ARGS+=(-f "$CHART/values-openshift.yaml")
fi
VALUES_ARGS+=(-f "$VALUES" --set-string "platform=$PLATFORM")
helm lint "$CHART" --strict "${VALUES_ARGS[@]}" >&2
helm template "$RELEASE" "$CHART" --namespace "$NAMESPACE" "${VALUES_ARGS[@]}" > "$TEMP_DIR/rendered.yaml"
python3 "$ROOT_DIR/scripts/check_installation_package.py" --rendered "$TEMP_DIR/rendered.yaml" --platform "$PLATFORM" >&2
if [[ -n "$OUTPUT" ]]; then
  cp "$TEMP_DIR/rendered.yaml" "$OUTPUT"
  echo "Rendered manifests: $OUTPUT" >&2
elif [[ "$APPLY" == 0 ]]; then
  cat "$TEMP_DIR/rendered.yaml"
fi
if [[ "$APPLY" == 0 ]]; then
  echo 'Render complete. No cluster change was made. Use --apply after reviewing the output.' >&2
  exit 0
fi
CLI=kubectl
[[ "$PLATFORM" != openshift ]] || CLI=oc
command -v "$CLI" >/dev/null 2>&1 || { echo "$CLI is required for --apply" >&2; exit 1; }
"$CLI" get namespace "$NAMESPACE" >/dev/null
python3 - "$TEMP_DIR/rendered.yaml" > "$TEMP_DIR/secret-keys.tsv" <<'PY'
import sys, yaml
keys = set()
for document in yaml.safe_load_all(open(sys.argv[1], encoding='utf-8')):
    if not document or document.get('kind') not in {'Deployment', 'StatefulSet'}:
        continue
    for container in document['spec']['template']['spec']['containers']:
        for variable in container.get('env', []):
            ref = variable.get('valueFrom', {}).get('secretKeyRef')
            if ref:
                keys.add((ref['name'], ref['key']))
for name, key in sorted(keys):
    print(name + '\t' + key)
PY
while IFS=$'\t' read -r secret_name secret_key; do
  "$CLI" --namespace "$NAMESPACE" get secret "$secret_name" \
    -o 'go-template={{range $key, $value := .data}}{{$key}}{{"\n"}}{{end}}' > "$TEMP_DIR/available-keys.txt"
  if ! grep -Fxq -- "$secret_key" "$TEMP_DIR/available-keys.txt"; then
    echo "Required key '$secret_key' missing from Secret '$secret_name' in '$NAMESPACE'." >&2
    exit 1
  fi
done < "$TEMP_DIR/secret-keys.tsv"
"$CLI" --namespace "$NAMESPACE" apply --dry-run=server -f "$TEMP_DIR/rendered.yaml" >/dev/null
echo "Installing release $RELEASE in namespace $NAMESPACE, context $("$CLI" config current-context)" >&2
helm upgrade --install "$RELEASE" "$CHART" --namespace "$NAMESPACE" \
  "${VALUES_ARGS[@]}" --atomic --wait --timeout 40m --history-max 10
