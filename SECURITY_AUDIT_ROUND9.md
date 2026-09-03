# Security / Regression Round 9

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: offline dependency enablement with the supplied Python wheels, full test-suite execution, regression repair, and test-invariant alignment after Rounds 6-8.

## Environment

- Python: 3.13.5
- Application dependencies installed offline from `cir-python-wheels.zip` into a dedicated virtual environment.
- Verified imports include Flask, Flask-SQLAlchemy, Flask-Login, psycopg2, Gunicorn, ldap3, ReportLab, matplotlib, Pillow, python-dotenv, python-docx, pypdf, requests, pyotp, qrcode, boto3, cryptography, and defusedxml.

## Findings and remediation

### HIGH - Incident templates contained invalid escaped Jinja expressions

`index.html` and `incident_detail.html` contained literal backslashes in `url_for(\'main.clone\', ...)`. Jinja rejects that syntax, causing incident-list/detail rendering to fail and cascading into multiple functional tests.

Round 9 removes the accidental escaping and restores valid `url_for('main.clone', ...)` expressions.

### MEDIUM - Version/build regression tests were pinned to obsolete release metadata

Several tests still expected `0.7.0-7` / build `20260608`, while the application now centralizes packaged release metadata in `VERSION` and `BUILD` through `app/version.py`.

Round 9 updates the tests to verify the centralized metadata contract rather than stale literal values.

### MEDIUM - Full-import static tests no longer matched the transactional restore design

Older invariants expected a bootstrap-row clear call and sequence alignment after a restore commit. Since Round 6, full restore rebuilds metadata on the active SQLAlchemy transaction and aligns sequences before the final commit so database and filesystem activation remain atomic.

Round 9 updates the tests to verify the current transactional guarantees: `db.metadata.drop_all/create_all` on `db.session.connection()`, rebuild before tenant restoration, and sequence alignment before the final commit.

### MEDIUM - Production cookie smoke tests did not satisfy the new encryption-key requirement

Security hardening now requires a distinct strong `SETTING_ENCRYPTION_KEY` in production mode. Two tests intended to exercise secure-cookie behavior failed earlier during production configuration validation.

Round 9 supplies a distinct test-only encryption key in those cases so each test reaches the behavior it is intended to verify.

## Verification

- `python -m compileall -q app tests`: PASS
- `sh -n docker-entrypoint.sh`: PASS
- Full `pytest -q`: **245 passed, 8 warnings**
- The remaining warnings are SQLAlchemy `Query.get()` legacy API warnings in tests; they are non-failing technical-debt items.

## Next priorities

1. Replace remaining `Query.get()` calls with `Session.get()` and enforce warning-free tests where practical.
2. Run PostgreSQL-backed integration tests for transactional full restore, advisory locks, sequence alignment, and multi-worker behavior.
3. Generate a complete transitive SBOM/SCA report in CI using the resolved dependency set.
4. Continue auditing persistent metadata that reaches filesystem paths, URLs, command arguments, or other privileged sinks.
