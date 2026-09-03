# Security Audit Round 8

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: residual filesystem trust boundaries, public/application logo path confinement, export/backup file selection, notification attachments, and administrative exception disclosure around document-template workflows.

## Confirmed findings and remediations

### HIGH - Residual database-backed upload paths bypassed `safe_upload_path()`

Round 7 protected document and action-attachment download, deletion, and Alfresco handoff, but several secondary consumers still reconstructed paths directly with `os.path.join(UPLOAD_DIR, stored_name)`. In particular, documents selected as SMTP attachments and files collected by full/global export paths could still consume a legacy or corrupted `stored_name` without revalidating the filesystem boundary.

Round 8 routes these remaining database-backed reads through `safe_upload_path()`. Invalid, traversing, missing, or non-regular paths are rejected rather than opened or archived. Export builders skip invalid persistent metadata instead of following it outside the managed upload directory, while notification attachment failures return a controlled application error.

### HIGH - Public logo path trusted persistent database metadata as an arbitrary filesystem path

The public `/logo` route called `send_file()` on the `Setting.logo_path` value after only checking `os.path.exists()`. Administrative deletion and full/global export paths also used that setting directly. Although the normal upload flow writes generated filenames below `LOGO_DIR`, persistent settings can originate from legacy, restored, manually edited, or otherwise corrupted database state. A malicious absolute path in that setting could therefore expose or delete an unintended local file, or cause it to be included in an export.

Round 8 adds `safe_logo_path()`. The configured logo must resolve to a direct child of `LOGO_DIR`, must use one of the supported raster image extensions, and must be an existing regular file when read or deleted. Public serving, administrative deletion, and export/backup inclusion all use the same boundary. The public response also always emits `X-Content-Type-Options: nosniff`.

### MEDIUM - Document/template workflow exceptions were reflected verbatim in the UI

PDF-template analysis, PDF-template save, and generated-form preview failures could interpolate raw exception text into flash messages. Unexpected parser, filesystem, conversion, or library errors can contain local paths or implementation details.

Round 8 keeps full exception details in server logs and returns generic administrative/user-facing messages for these workflows.

## Verification

- `python -m compileall -q app tests`: PASS.
- `pytest -q tests/test_security_round5_invariants.py tests/test_security_round6_invariants.py tests/test_security_round7_invariants.py tests/test_security_round8_invariants.py`: 22 passed.
- `sh -n docker-entrypoint.sh`: PASS.
- Full `pytest -q` collection was attempted again after explicitly attempting to install Flask 3.1.3, Flask-SQLAlchemy 3.1.1 and Flask-Login 0.6.3. The sandbox cannot reach PyPI/files.pythonhosted.org, so package installation is blocked by runtime network isolation. Collection therefore still stops only on the two Flask-dependent modules (`test_markdown_rendering_and_notifications.py` and `test_outbound_security.py`) with `ModuleNotFoundError: flask`.
- Round 8 static regressions cover notification attachments, both full/global export builders, logo serving/deletion/export confinement, and generic document-template error handling.

## Residual risk / next priorities

1. Run the entire test suite in the normal project/container image with all production and test dependencies installed.
2. Exercise PostgreSQL backup/import locks and rollback behavior under real multi-worker/multi-replica concurrency.
3. Continue reviewing persistent configuration values that later become filesystem paths, URLs, or command arguments, treating restored database state as untrusted at every sink.
4. Continue removing raw exception reflection from remaining local administrative CRUD paths where diagnostics can be retained in logs instead.
5. Run complete transitive SCA/SBOM generation in network-enabled CI and gate builds on high/critical dependency findings.
