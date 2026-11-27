#!/usr/bin/env bash
# Publish immutable, fully verified training assets. Never overwrite an existing release.
set -euo pipefail
SOURCE_SHA="${1:?Full Git source SHA required}"
ASSETS_DIR="${2:?Verified training asset directory required}"
REPOSITORY="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY required}"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid source SHA' >&2; exit 1; }
python scripts/training_release_assets.py --verify-only --output-dir "$ASSETS_DIR" --source-commit "$SOURCE_SHA"
TAG="training-${SOURCE_SHA}"
readarray -t FILES < <(python - "$ASSETS_DIR" <<'PY'
import sys
from pathlib import Path
from scripts.training_release_assets import ASSETS, RECEIPTS, MANIFEST
p = Path(sys.argv[1])
for name in [*ASSETS, *RECEIPTS.values(), MANIFEST]:
    print(p / name)
PY
)
if gh release view "$TAG" --repo "$REPOSITORY" >/dev/null 2>&1; then
  # A rerun must never silently overwrite an immutable release. Compare the
  # actual remote bytes against the locally sealed manifest before reusing it.
  TEMP="$(mktemp -d)"
  trap 'rm -rf "$TEMP"' EXIT
  gh release download "$TAG" --repo "$REPOSITORY" --dir "$TEMP"
  python scripts/training_release_assets.py --verify-only --output-dir "$TEMP" --source-commit "$SOURCE_SHA"
  python - "$ASSETS_DIR" "$TEMP" <<'PY'
from pathlib import Path
from scripts.training_release_assets import MANIFEST, sha
import sys
local, remote = map(Path, sys.argv[1:])
for name in (p.name for p in local.iterdir() if p.is_file()):
    if sha(local/name) != sha(remote/name):
        raise SystemExit('Existing immutable GitHub Release differs from locally verified artifact: ' + name)
PY
  gh release edit "$TAG" --repo "$REPOSITORY" --latest
else
  # gh release create stages the uploads in a draft and publishes only after
  # all uploads succeed. The tag is unique to this source commit.
  gh release create "$TAG" "${FILES[@]}" \
    --repo "$REPOSITORY" --target "$SOURCE_SHA" --latest \
    --title "CIR verified training (${SOURCE_SHA:0:12})" \
    --notes "CI-verified Italian master and derived English training. Source commit: $SOURCE_SHA. Every file has a SHA-256 digest in training-release-manifest.json."
fi
printf 'Published training release: https://github.com/%s/releases/tag/%s\n' "$REPOSITORY" "$TAG"
