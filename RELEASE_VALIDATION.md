# Release validation - 0.4.0-33

Validation performed in the preparation environment on 2026-05-23.

## Completed checks

- Python dependencies installed successfully in an isolated virtual environment.
- `python -m compileall -q app tests`: PASS.
- `python -m pytest -q`: PASS, 38 passed.
- `python scripts/build_documentation_pdfs.py`: PASS; regenerated user documentation, administrator documentation and two-page portrait brochure in `docs/`.
- Static review of release metadata, Docker Compose and Kubernetes manifests: PASS after updates.

## Network-dependent check

`pip-audit` is now part of the blocking AGID compliance runner and the GitHub Actions workflow. In this preparation environment the command could not complete because DNS resolution for `pypi.org` failed. This is an environment/network limitation, not a disabled control. The release must be promoted only after the included CI workflow completes with network access and produces a passing `pip-audit.json` evidence file.

## Release packaging notes

- The release archive excludes `.venv`, Python bytecode caches and `.pytest_cache`.
- AGID evidence directories under `compliance/agid/<RUN_ID>/` are not regenerated automatically in this package; run `scripts/run_agid_compliance.sh` in CI or in a connected release environment to create the final evidence directory.
