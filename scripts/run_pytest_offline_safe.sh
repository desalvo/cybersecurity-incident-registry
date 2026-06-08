#!/usr/bin/env bash
# Run pytest in isolated module-level processes for Docker/offline compliance.
# A shell parent is used intentionally: some Python parent runners can inherit
# file descriptors/resources from pytest subprocesses and wait indefinitely even
# after pytest has printed a successful result.
set -u
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 2
export PYTEST_VERSION="${PYTEST_VERSION:-agid}"
export CIR_TEST_PASSWORD_HASH_METHOD="${CIR_TEST_PASSWORD_HASH_METHOD:-pbkdf2:sha256:1}"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-1}"
export CIR_FORCE_PYTEST_PROCESS_EXIT="${CIR_FORCE_PYTEST_PROCESS_EXIT:-1}"
export CIR_DISABLE_BACKGROUND_SCHEDULERS="${CIR_DISABLE_BACKGROUND_SCHEDULERS:-1}"
TMP_ROOT_BASE="${PYTEST_DEBUG_TEMPROOT:-$ROOT_DIR/.pytest_tmp}"
rm -rf "$TMP_ROOT_BASE"
mkdir -p "$TMP_ROOT_BASE"
FILE_TIMEOUT="${AGID_PYTEST_FILE_TIMEOUT:-180}"
ITEM_TIMEOUT="${AGID_PYTEST_ITEM_TIMEOUT:-90}"
if [ "$#" -gt 0 ]; then
  TEST_FILES=("$@")
else
  mapfile -t TEST_FILES < <(find tests -maxdepth 1 -type f -name 'test_*.py' | sort)
fi
TOTAL="${#TEST_FILES[@]}"
FAILED=()
run_target() {
  local target="$1"
  local timeout_seconds="$2"
  local tmp_root="$3"
  rm -rf "$tmp_root"
  mkdir -p "$tmp_root"
  PYTEST_DEBUG_TEMPROOT="$tmp_root" CIR_PYTEST_ISOLATED_CHILD=1 timeout --kill-after=5 "$timeout_seconds" python -m pytest -q "$target"
}
collect_nodeids() {
  local test_file="$1"
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 CIR_FORCE_PYTEST_PROCESS_EXIT=0 CIR_PYTEST_ISOLATED_CHILD=1 \
    timeout --kill-after=5 60 python -m pytest --collect-only -q "$test_file" | awk '/::/ {print $0}'
}
for idx in "${!TEST_FILES[@]}"; do
  test_file="${TEST_FILES[$idx]}"
  echo "==> pytest module $((idx + 1))/$TOTAL: $test_file"
  module_tmp="$TMP_ROOT_BASE/module_$((idx + 1))"
  if run_target "$test_file" "$FILE_TIMEOUT" "$module_tmp"; then
    echo "PASS $test_file"
    continue
  fi
  rc=$?
  echo "Retrying $test_file with per-test isolation after exit $rc."
  mapfile -t NODEIDS < <(collect_nodeids "$test_file")
  if [ "${#NODEIDS[@]}" -eq 0 ]; then
    FAILED+=("$test_file:$rc")
    continue
  fi
  item_failed=0
  for nodeid in "${NODEIDS[@]}"; do
    item_tmp="$module_tmp/item_${#FAILED[@]}_${RANDOM}"
    if ! run_target "$nodeid" "$ITEM_TIMEOUT" "$item_tmp"; then
      item_rc=$?
      echo "FAIL $nodeid exit=$item_rc"
      item_failed=1
    fi
  done
  if [ "$item_failed" -eq 0 ]; then
    echo "PASS $test_file via per-test isolation"
  else
    FAILED+=("$test_file:1")
  fi
done
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo
  echo "FAILED pytest modules:"
  printf -- '- %s\n' "${FAILED[@]}"
  exit 1
fi
echo
echo "All $TOTAL pytest modules passed in isolated offline-safe mode."
