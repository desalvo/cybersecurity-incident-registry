# RC102 — Training releases outside source Git

## Publishing contract

- The only master is Italian: `docs/presentation/visual_rc64_spec.json` and the authored Italian source JSON.
- The English PPTX/PDF are derived from the pinned Italian master, using the same browser screenshot evidence manifest. Intentional localized illustrations are hash-bound to their Italian sources.
- Same-run Playwright, document validation and SHA-256 receipts are required *before* any public release.
- GitHub Actions creates **`training-<40-character-source-sha>`** with six assets (IT/EN visual PPTX+PDF, operational PPTX, screenshot gallery PDF), three receipts and `training-release-manifest.json`.
- Release asset names remain stable, and the most recent successful release is accessible using `https://github.com/desalvo/cybersecurity-incident-registry/releases/latest/download/<asset>`.
- Existing immutable training releases can only be reused if all remote bytes match those sealed by the current run. A failed capture, validation or upload must never move the latest pointer.
- CI writes documents to temporary workspace and GitHub Releases, never back to the Git source branch and never through a documentation-only `chore` PR.
- Keep the URL to the Italian/English PDF inside the respective presentation pointed to the stable Release download path, not `blob/main`.

## Workflows, security, and resource usage

1. Ordinary PR: run quality gates, live-browser screenshots and document validations, but do not publish public assets.
2. Merge to `main`: run full quality gates, screenshot/documentation validation and, if production files change, Docker release and scanning. Publish verified training directly to GitHub Releases, without any documentation-generated PR.
3. Docker promotion may still propose a **digest-only** metadata PR. A `GITHUB_TOKEN` push does not auto-run GitHub Actions, so explicitly dispatch PR checks after opening it. On this strictly verified digest-only branch, full code quality gates still run but the browser/manual/PPTX/PDF job is skipped. On its subsequent merge, the release-scope detector again skips browser/documentation and Docker promotion; normal code gates remain enabled. Any commit containing a third changed file is **not** digest-only.
4. Immutable `training-*` tags do not trigger CIR CI; otherwise creation of the document release would recursively rebuild/re-publish itself.
5. Document assets are ignored by Git, excluded by the source and Docker packagers, and not required by source-only release smoke tests. The cumulative source archive has the canonical root `cybersecurity-incident-registry-0.10.0-1/`.

## Recovery and local commands

Use `python scripts/training_release_assets.py --help` to stage CI outputs and `bash scripts/publish_training_release.sh <commit> <staged-assets-dir>` on GitHub Actions with `GH_TOKEN` and `GITHUB_REPOSITORY`. Never publish unverified local editorial builds as authentic CI captures.

Portable source archive (no presentation binaries or `.git`):

```bash
python scripts/package_cumulative.py --source . --output /tmp/cir-sources.tar.zst --compression zstd --level 19
```

For development Flask is available via the Library's **`cir-wheels-py313.zip`** (Python 3.13); use an isolated virtual environment for offline installs.

## Notes on historical data

Removing generated documents from `main` does not erase Git history: avoid rewriting history just to reclaim old binary sizes. Existing release URLs must be available publicly before users rely on the new links; GitHub CI is the authority for final publication.
