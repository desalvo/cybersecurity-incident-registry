# Development history: 0.8.0 to 0.9.0-1

Chronological engineering and hardening record for the 0.9.0-1 development line. The numbered rounds are iterations of the same functional 0.9.0-1 release, not separate functional versions.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `SECURITY_AUDIT_ROUND2.md`
- `SECURITY_AUDIT_ROUND3.md`
- `SECURITY_AUDIT_ROUND4.md`
- `SECURITY_AUDIT_ROUND5.md`
- `SECURITY_AUDIT_ROUND6.md`
- `SECURITY_AUDIT_ROUND7.md`
- `SECURITY_AUDIT_ROUND8.md`
- `SECURITY_AUDIT_ROUND9.md`
- `SECURITY_AUDIT_ROUND10.md`
- `SECURITY_AUDIT_ROUND11.md`
- `SECURITY_AUDIT_ROUND12.md`
- `SECURITY_AUDIT_ROUND13.md`
- `SECURITY_AUDIT_ROUND14.md`
- `SECURITY_AUDIT_ROUND15.md`
- `SECURITY_AUDIT_ROUND16.md`
- `SECURITY_AUDIT_ROUND17.md`
- `SECURITY_AUDIT_ROUND18.md`
- `SECURITY_UPDATE_RC_R4.md`
- `RC_R5_TEST_HARNESS_FIX.md`
- `RC_R6_CONTAINER_HARDENING.md`
- `RC_R7_FINAL_CONTAINER_MINIMIZATION.md`
- `HOTFIX6_TEST_ALIGNMENT.md`

---

## Historical source: `SECURITY_AUDIT_ROUND2.md`

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: route-level tenant isolation, generated-form temporary files, and server-side outbound HTTP integrations.

## Confirmed findings and remediations

### HIGH - Cross-tenant document deletion (IDOR)
`Document` does not carry `tenant_id` directly. The delete route loaded the document by global ID and checked write permission for the active tenant, but did not verify visibility of the parent incident. The route now resolves the parent `Incident` through the tenant-aware `visible()` query before deleting either the file or database row.

### HIGH - Generated-form preview/confirmation could address arbitrary shared upload files
Generated PDF previews live in the shared upload directory. The preview route previously accepted a basename and only checked whether the requested incident was visible. The confirmation endpoint likewise trusted hidden `pdf_stored` values. A user with access to one incident could therefore attempt to preview, rename, delete, or attach another file in the shared upload directory if its basename was known.

Temporary generated PDFs are now registered in the authenticated Flask session and bound to the incident ID. Preview and confirmation accept only session-registered basenames, reject path components, and remove consumed/rejected files from the session registry.

### HIGH - SSRF exposure through configurable outbound integrations
SSO test/callback and Alfresco use administrator-configurable URLs for server-side requests. A common outbound URL validator now blocks loopback, link-local, reserved, multicast, unspecified and private destinations by default, rejects inline URL credentials, and requires HTTPS for non-allowlisted hosts.

Legitimate intranet endpoints must be explicitly named in `CIR_OUTBOUND_PRIVATE_HOSTS`. Private allowlisted hosts may use HTTP; public HTTP additionally requires `CIR_OUTBOUND_ALLOW_HTTP=1`.

### MEDIUM - Redirect-based SSRF bypass
HTTP clients can otherwise validate an initial public URL and automatically follow a redirect to a private target. Automatic redirects are now disabled for SSO callback calls, Alfresco calls, and AI engine calls.

## Regression controls

Added tests:
- `tests/test_outbound_security.py`
- `tests/test_multitenant_route_guard_invariants.py`

The second test encodes a structural invariant: routes loading child resources without direct `tenant_id` (`IncidentReminder`, `Action`, `ActionAttachment`, `Document`) must also contain an incident visibility guard.

## Validation performed in the audit environment

- `python -m compileall -q app tests`: PASS
- standalone outbound URL policy self-check: PASS
- AST scan of child-resource route guards: PASS after remediation
- Full pytest suite: not executable in this audit environment because project dependencies cannot be installed from PyPI (outbound/DNS access is unavailable).

## Residual risk / next recommended review

The URL validator performs DNS resolution before the actual HTTP client call, so a hostile DNS service could theoretically attempt DNS rebinding between validation and connection. Automatic redirect blocking removes the easier bypass. For environments with strict SSRF threat models, the next hardening step is connection pinning to the validated address or egress filtering at container/Kubernetes/network-policy level.

The next code-review pass should prioritize XSS/HTML/Markdown rendering, CSP effectiveness, file-type validation (especially SVG), archive/import parsing and backup restore boundaries, followed by secret exposure in logs/UI/export paths.

---

## Historical source: `SECURITY_AUDIT_ROUND3.md`

## Scope

Third hardening pass focused on tenant backup boundaries, secret exposure, configurable outbound backup endpoints, XSS/Markdown edge cases, SVG uploads, CSP, and archive/import handling.

## Confirmed findings and remediation

### CRITICAL – Tenant BackupJob could archive data from all tenants

`BackupJob` is tenant-scoped, but `execute_backup_job()` previously called `build_backup_archive()` without a tenant scope. The backup builder enumerated all incidents, exported the complete database payload and, when uploads were selected, archived the whole upload directory. A tenant administrator able to configure a backup destination could therefore cause cross-tenant data to be written locally or uploaded to S3.

**Fix:** `execute_backup_job()` now propagates `job.tenant_id`. Tenant-scoped backups filter incident CSV, database tables, relations, documents and action attachments to that tenant. Shared/global templates and logos are not included in tenant backups. Only jobs with no tenant scope can produce a global full backup.

### HIGH – Tenant export disclosed authentication material that tenant import never uses

Tenant exports previously included global user rows, role rows and MFA TOTP records. This exposed password hashes and TOTP seeds even though `_import_tenant_scoped_archive()` explicitly does not restore global users or MFA material.

**Fix:** tenant-scoped exports now omit `User`, `UserTenantRole` and `MfaTotpToken` rows. Incident creator references continue to be repaired to the importing admin when the referenced global user is not available.

### HIGH – Tenant export included global/shared settings

The tenant export query for `Setting` included global/non-tenant keys. The tenant import path ignores those settings, so their inclusion provided no restore benefit and unnecessarily exposed infrastructure metadata and encrypted shared credentials.

**Fix:** tenant exports now contain only keys prefixed with the active tenant namespace.

### HIGH – Backup S3 secret stored/exported in plaintext

`BackupJob.s3_secret_key` was saved directly from the administration form and serialized by the generic export function.

**Fix:** new writes are Fernet-encrypted using the existing settings encryption root. Runtime S3 access transparently decrypts the value. Legacy plaintext database values remain usable and are automatically encrypted when serialized into an export, preventing the export itself from leaking the plaintext secret.

### HIGH – S3-compatible endpoint bypassed outbound SSRF policy

Round 2 protected SSO, Alfresco and AI HTTP endpoints, but the configurable S3-compatible endpoint used by backup jobs was passed directly to boto3.

**Fix:** custom S3 endpoint URLs now pass through `validate_outbound_http_url()` before a client is created. Private, loopback, link-local, reserved and other non-public destinations remain blocked unless explicitly allowlisted using the existing outbound-host policy.

### MEDIUM – Markdown button URL validation could rely on CSP for encoded schemes

The server-side button renderer validated the escaped representation of link targets. HTML entity encoded separators such as `javascript&#58;...` could therefore survive the syntactic check. The existing CSP blocked execution, but the renderer should not rely on CSP as its sole barrier.

**Fix:** link targets are HTML-decoded before scheme validation and escaped again when emitted into the `href` attribute. Regression coverage includes entity-encoded `javascript:` and `data:` schemes.

### MEDIUM – Same-origin administrator SVG upload surface

Administrator-configured application and SSO logos accepted SVG. SVG is an active document format and is unnecessarily risky when user-supplied files are served from the application origin.

**Fix:** new administrator logo uploads accept raster formats only (PNG/JPG/GIF/WEBP). Existing packaged or legacy SVG assets remain readable for compatibility, but SVG responses receive a restrictive sandbox CSP plus `nosniff`.

## Archive/import review

`validate_full_import_archive()` already enforces a maximum member count, maximum per-member size, maximum total uncompressed size, rejects path traversal, absolute paths, links and device entries, and requires `export.json`. Restore code uses `extractfile()` and writes to normalized destinations rather than calling `extractall()`. No exploitable archive path traversal was confirmed in this pass.

## Verification

- `python3 -m compileall -q app tests`: pass.
- Static invariants for tenant backup scope, credential exclusion, S3 SSRF validation and backup-secret encryption: pass.
- Direct standalone test of the Markdown renderer against raw and HTML-entity encoded unsafe schemes: pass.
- Full pytest execution remains environment-blocked because project dependencies cannot be installed from PyPI in the current container.

## Residual risk / next priorities

1. Run the complete pytest suite in a dependency-complete CI/container environment.
2. Add integration tests creating two tenants and asserting byte-for-byte absence of tenant B records/files from a tenant A backup archive.
3. Consider key rotation/versioning for encrypted `BackupJob` credentials independently from Flask `SECRET_KEY`.
4. Review SMTP/LDAP connection policies separately: private-network connectivity may be intentional, but should be explicitly documented and allowlisted where feasible.
5. Review application error messages that interpolate raw exception strings into administrator/user-facing flashes to minimize internal path/endpoint disclosure.

---

## Historical source: `SECURITY_AUDIT_ROUND4.md`

## Scope
Exception disclosure, SMTP/LDAP outbound connections, encryption-key lifecycle, privilege escalation, and CSRF/method safety.

### HIGH - State-changing incident clone exposed as GET
`/incident/<id>/clone` created and committed a new incident through a safe HTTP method. This bypassed the application's CSRF middleware, enabled cross-site/link-triggered cloning, and was unsafe with crawlers/prefetchers. The route is now POST-only and UI links were replaced by POST forms, which receive the normal CSRF token injection.

### HIGH - Unrestricted administrator-configured SMTP/LDAP destinations
SMTP and LDAP destinations could target loopback/private/special networks without the outbound destination policy used by HTTP integrations. A shared host validator now rejects non-public destinations unless the hostname is explicitly listed in `CIR_OUTBOUND_PRIVATE_HOSTS`. LDAP additionally requires `ldaps://` by default; legacy plaintext LDAP requires `CIR_OUTBOUND_ALLOW_PLAINTEXT_LDAP=1`.

### MEDIUM - Upstream exception disclosure
SSO, LDAP administration, SMTP test/send, Alfresco operations and backup failures could expose raw exception text in the web UI. Raw details can contain internal hostnames, paths, protocol/library diagnostics or upstream response fragments. Sensitive network/infrastructure failures now return generic UI messages while full exception details remain in server logs.

### HIGH - Encryption key coupled to Flask session secret
Encrypted settings and backup credentials could derive their key from Flask `SECRET_KEY`. Production now requires a distinct `SETTING_ENCRYPTION_KEY` of at least 32 characters and rejects equality with `SECRET_KEY`. New ciphertext uses the dedicated key. `SETTING_ENCRYPTION_PREVIOUS_KEYS` supports staged rotation; legacy values encrypted with the historical Flask secret remain decryptable during migration.

## Privilege review
No confirmed tenant-admin to global-superuser escalation was found in the user/role administration paths reviewed. Tenant admins cannot assign `superuser`, cannot select arbitrary membership tenants, and global password administration remains restricted to superusers.

## Method-safety notes
The incident clone mutation has been moved to POST. A static scan still observes commits in selected GET endpoints due to audit/default-initialization side effects (for example notification preview); these do not currently perform the same direct user-requested destructive/business mutation, but removing all persistence from safe methods remains a desirable future cleanup.

## Verification
- `python -m compileall -q app tests`: PASS
- Round 4 invariant script: PASS
- Outbound host/LDAP policy self-check with mocked DNS: PASS
- Template scan: no remaining `url_for('main.clone'...)` GET links

The full pytest suite could not be executed in the analysis environment because third-party project dependencies are unavailable and package installation is blocked by external network/DNS restrictions.

---

## Historical source: `SECURITY_AUDIT_ROUND5.md`

Scope: database/business logic, tenant integrity, backup concurrency, restore/import boundaries, and dependency review.

### HIGH - Backup administration was not tenant-scoped
`/admin/backups` selected the first `BackupJob` globally. A tenant administrator could therefore view or update a job belonging to another tenant (or a shared/global job). The route now selects/creates only the `BackupJob` for the active tenant. Backup notification recipients are also selected from administrators of the job tenant.

### HIGH - Tenant admins could choose an arbitrary writable local backup directory
`local_path` was accepted from the form and used as a server filesystem destination. Tenant jobs now always write below `BACKUP_DIR/tenant-<id>`. Global/local paths are constrained below `BACKUP_DIR` by `_safe_backup_local_path()`.

### HIGH - Duplicate backup execution across workers/replicas
The backup scheduler had only per-process minute state and could run the same job in multiple Gunicorn workers or Kubernetes replicas. All on-demand and scheduled executions now pass through `execute_backup_job_serialized()`. PostgreSQL deployments use a dedicated-connection advisory lock per backup job; non-PostgreSQL development uses a non-blocking process lock.

### CRITICAL - Tenant import reused global primary keys
Tenant-scoped archives contained database primary keys from the source installation. Import into another tenant could collide with IDs owned by another tenant, causing integrity failures or cross-tenant reference corruption. Tenant import now allocates fresh IDs and explicitly remaps dependent foreign keys and association-table rows.

### CRITICAL - Tenant import could overwrite another tenant's physical uploads
Document and action attachment `stored_name` values were trusted from the archive and written into the shared upload directory. A crafted tenant archive could target an existing stored filename. Imported files now receive new UUID-based physical names; database rows and archive file copies are remapped, and files are created with exclusive mode (`xb`) and mode 0600 where supported.

### MEDIUM - Derived scheduler state imported across tenants
`DeadlineNotificationState.notification_key` is globally unique and represents runtime/idempotency state. It is no longer imported in tenant-to-tenant restore. The scheduler recreates state naturally.

### HIGH - Residual tenant isolation bugs in administrative data
External recipient save/list/duplicate checks and NotificationType edit paths contained unscoped queries. These now use `tenant_query()` / `model_or_404()`. New notification types are assigned to the active tenant. The administrative status page now reports incident/reminder/backup counts only for the active tenant.

### MEDIUM - Exception disclosure in CSV import
CSV import no longer flashes raw exception text to the user. Detailed diagnostics remain in server logs.

### HIGH - Vulnerable Pillow dependency
`Pillow==12.2.0` is affected by CVE-2026-59203 (crafted EPS can cause an infinite parsing loop / denial of service). The requirement is updated to `Pillow==12.3.0`, where the issue is fixed.

## Dependency review notes

The pinned Flask 3.1.3 includes the fix for CVE-2026-27205. pypdf 6.10.2 includes the fix for CVE-2026-41313. cryptography 46.0.7 includes the fix for CVE-2026-39892. A complete transitive-dependency audit should still be run in CI with `pip-audit` or an equivalent scanner because this environment cannot resolve/install packages from PyPI.

- `python -m compileall -q app tests`: PASS.
- `python tests/test_security_round5_invariants.py`: PASS.
- Static regression checks cover tenant-scoped backup administration, local backup path confinement, tenant import ID/file remapping, tenant-scoped administrative child queries, and the Pillow security floor.

1. Make full destructive restore filesystem operations transactional/staged so a DB rollback cannot leave partially replaced persistent files.
2. Add database-level uniqueness/ownership constraints where practical for tenant-scoped records and child entities.
3. Run the full pytest suite and a real PostgreSQL multi-worker concurrency test in CI.
4. Run complete SCA/SBOM generation for direct and transitive Python/system dependencies.

---

## Historical source: `SECURITY_AUDIT_ROUND6.md`

Scope: database/business-logic integrity, destructive restore atomicity, multi-worker concurrency, parent/child ownership constraints, and dependency maintenance.

### CRITICAL — Full Import was not transactional across database and persistent volumes

The previous Full Import recreated the database with `db.drop_all()` / `db.create_all()` and committed that schema change before all imported rows and persistent files had been restored. Persistent files were then written directly over the live volumes. A later exception could therefore leave either a destroyed/partially restored database or a partially replaced filesystem.

Round 6 performs PostgreSQL DDL through the active SQLAlchemy session connection, so schema replacement and row loading remain in the same transaction. Persistent data is extracted and validated into staging directories located next to each destination, then activated with reversible `os.replace()` directory swaps only after DB loading succeeds. If commit fails, the database transaction is rolled back and the prior filesystem directories are restored. Backups of replaced directories are deleted only after the DB commit succeeds.

### HIGH — Full restore could leave stale persistent files

Direct overwrite restored files present in the archive but did not guarantee that files absent from the archive disappeared. Current full exports now restore managed persistent groups as snapshots: the staged directory replaces the old directory, so stale files do not survive a successful full restore. Legacy archives that do not declare a persistent group preserve unrepresented groups rather than deleting them.

### HIGH — Concurrent import/restore across Gunicorn workers or replicas

Two workers could previously start destructive imports concurrently. Round 6 serializes all full/tenant imports with a PostgreSQL advisory lock held on a dedicated connection. Non-PostgreSQL development/test environments use a process-local non-blocking lock.

### HIGH — Tenant import could leave filesystem orphans after DB rollback

Tenant import intentionally creates new UUID-backed upload files before commit. If the database transaction failed, those new files remained orphaned. Round 6 records every newly created physical file and removes it when the tenant import transaction fails.

### HIGH — Archive relational/file integrity was trusted too late

Full-import payloads are now validated before database recreation. The validator rejects duplicate primary IDs, actions/documents/reminders referencing missing incidents, attachments referencing missing actions, unsafe `stored_name` values, and duplicate physical `stored_name` claims across documents and action attachments sharing the upload directory.

### HIGH — Parent/child ownership was primarily application-enforced

New/rebuilt schemas now declare incident ownership FKs for Action, Document and IncidentReminder, and ActionAttachment -> Action, as `NOT NULL` with `ON DELETE CASCADE`. Existing PostgreSQL schemas are hardened during startup only when no NULL/orphan rows exist. If legacy inconsistent rows are found, startup remains non-destructive and emits a warning so they can be repaired manually before the constraint is applied.

## Dependency maintenance

Round 6 updates:

- `gunicorn` 23.0.0 -> 26.2.0. The upstream security policy no longer lists 23.0.0 as a supported security branch; 26.x is supported and 26.2.0 is the current PyPI release at audit time.
- `Werkzeug` 3.1.6 -> 3.1.8. 3.1.6 already contained the February 2026 `safe_join` security fix; 3.1.7/3.1.8 add stricter Host / Transfer-Encoding parsing and subsequent compatibility correction.

No forced update was made to `ldap3`: PyPI still lists 2.9.1 as the latest stable release, with 2.10.2rc4 only a pre-release at audit time. Flask-SQLAlchemy 3.1.1 also remains the latest stable PyPI release.

`sbom/SBOM_ROUND6.cdx.json` records the directly pinned production dependencies. A complete transitive SBOM/SCA still requires dependency resolution in a network-enabled build environment; this analysis environment cannot install the project requirements from PyPI.

- `python -m compileall app tests`: PASS
- `pytest -q tests/test_security_round6_invariants.py`: 8 passed
- `sh -n docker-entrypoint.sh`: PASS
- Full pytest collection discovers 218 tests before stopping on two import errors because Flask is not installed in the analysis environment.

## Deployment notes

Before production deployment, build the image from this source so the updated dependency pins are resolved inside the normal Docker build. For existing PostgreSQL installations, review startup logs for `Schema hardening skipped` warnings; any reported NULL/orphan child rows should be repaired before relying on DB-level ownership constraints.

---

## Historical source: `SECURITY_AUDIT_ROUND7.md`

Scope: filesystem trust boundaries for database-backed uploads, legacy/corrupted metadata resilience, document/attachment download and deletion, and Alfresco local-file handoff.

## Confirmed finding and remediation

### HIGH - Database-backed `stored_name` values reached filesystem operations without revalidation

Document and action-attachment paths were reconstructed with `os.path.join(UPLOAD_DIR, stored_name)` at download, delete, and Alfresco-upload boundaries. New uploads and Round 6 imports already generate/validate safe opaque names, but existing database rows are a separate trust boundary: a legacy, manually altered, or otherwise corrupted `stored_name` containing an absolute path or traversal components could make those operations address a file outside the managed upload directory.

Round 7 adds `safe_upload_path()`, which requires the stored value to be an unchanged `secure_filename()` basename, resolves the configured upload directory and candidate path, verifies the candidate remains a direct child of that directory, and (for reads/deletes) requires an existing regular file. Document downloads, action-attachment downloads, their deletion paths, and the Alfresco local-file handoff now use this helper.

This is defense in depth: archive validation from Round 6 remains in place, while the filesystem boundary no longer assumes that historical database content is trustworthy.

- `python -m compileall -q app tests`: PASS.
- `pytest -q tests/test_security_round6_invariants.py tests/test_security_round7_invariants.py`: PASS.
- Static Round 7 regression tests verify path canonicalization and coverage of document/attachment download, deletion, and Alfresco handoff.

1. Replace remaining direct `UPLOAD_DIR` path construction with centralized helpers where the filename can originate from persistent metadata.
2. Add integration tests with PostgreSQL and real multi-worker restore/backup execution.
3. Run full dependency/SCA scanning in the network-enabled CI image and generate a transitive SBOM.
4. Continue reducing raw exception text exposed by non-network administrative/UI workflows where unexpected exceptions may contain implementation details.

---

## Historical source: `SECURITY_AUDIT_ROUND8.md`

Scope: residual filesystem trust boundaries, public/application logo path confinement, export/backup file selection, notification attachments, and administrative exception disclosure around document-template workflows.

### HIGH - Residual database-backed upload paths bypassed `safe_upload_path()`

Round 7 protected document and action-attachment download, deletion, and Alfresco handoff, but several secondary consumers still reconstructed paths directly with `os.path.join(UPLOAD_DIR, stored_name)`. In particular, documents selected as SMTP attachments and files collected by full/global export paths could still consume a legacy or corrupted `stored_name` without revalidating the filesystem boundary.

Round 8 routes these remaining database-backed reads through `safe_upload_path()`. Invalid, traversing, missing, or non-regular paths are rejected rather than opened or archived. Export builders skip invalid persistent metadata instead of following it outside the managed upload directory, while notification attachment failures return a controlled application error.

### HIGH - Public logo path trusted persistent database metadata as an arbitrary filesystem path

The public `/logo` route called `send_file()` on the `Setting.logo_path` value after only checking `os.path.exists()`. Administrative deletion and full/global export paths also used that setting directly. Although the normal upload flow writes generated filenames below `LOGO_DIR`, persistent settings can originate from legacy, restored, manually edited, or otherwise corrupted database state. A malicious absolute path in that setting could therefore expose or delete an unintended local file, or cause it to be included in an export.

Round 8 adds `safe_logo_path()`. The configured logo must resolve to a direct child of `LOGO_DIR`, must use one of the supported raster image extensions, and must be an existing regular file when read or deleted. Public serving, administrative deletion, and export/backup inclusion all use the same boundary. The public response also always emits `X-Content-Type-Options: nosniff`.

### MEDIUM - Document/template workflow exceptions were reflected verbatim in the UI

PDF-template analysis, PDF-template save, and generated-form preview failures could interpolate raw exception text into flash messages. Unexpected parser, filesystem, conversion, or library errors can contain local paths or implementation details.

Round 8 keeps full exception details in server logs and returns generic administrative/user-facing messages for these workflows.

- `python -m compileall -q app tests`: PASS.
- `pytest -q tests/test_security_round5_invariants.py tests/test_security_round6_invariants.py tests/test_security_round7_invariants.py tests/test_security_round8_invariants.py`: 22 passed.
- `sh -n docker-entrypoint.sh`: PASS.
- Full `pytest -q` collection was attempted again after explicitly attempting to install Flask 3.1.3, Flask-SQLAlchemy 3.1.1 and Flask-Login 0.6.3. The sandbox cannot reach PyPI/files.pythonhosted.org, so package installation is blocked by runtime network isolation. Collection therefore still stops only on the two Flask-dependent modules (`test_markdown_rendering_and_notifications.py` and `test_outbound_security.py`) with `ModuleNotFoundError: flask`.
- Round 8 static regressions cover notification attachments, both full/global export builders, logo serving/deletion/export confinement, and generic document-template error handling.

1. Run the entire test suite in the normal project/container image with all production and test dependencies installed.
2. Exercise PostgreSQL backup/import locks and rollback behavior under real multi-worker/multi-replica concurrency.
3. Continue reviewing persistent configuration values that later become filesystem paths, URLs, or command arguments, treating restored database state as untrusted at every sink.
4. Continue removing raw exception reflection from remaining local administrative CRUD paths where diagnostics can be retained in logs instead.
5. Run complete transitive SCA/SBOM generation in network-enabled CI and gate builds on high/critical dependency findings.

---

## Historical source: `SECURITY_AUDIT_ROUND9.md`

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

- `python -m compileall -q app tests`: PASS
- `sh -n docker-entrypoint.sh`: PASS
- Full `pytest -q`: **245 passed, 8 warnings**
- The remaining warnings are SQLAlchemy `Query.get()` legacy API warnings in tests; they are non-failing technical-debt items.

## Next priorities

1. Replace remaining `Query.get()` calls with `Session.get()` and enforce warning-free tests where practical.
2. Run PostgreSQL-backed integration tests for transactional full restore, advisory locks, sequence alignment, and multi-worker behavior.
3. Generate a complete transitive SBOM/SCA report in CI using the resolved dependency set.
4. Continue auditing persistent metadata that reaches filesystem paths, URLs, command arguments, or other privileged sinks.

---

## Historical source: `SECURITY_AUDIT_ROUND10.md`

Scope: elimination of the remaining SQLAlchemy legacy warnings from Round 9, warning-regression prevention, and verification that the change does not alter application behavior.

### LOW - Test suite still used SQLAlchemy 1.x `Query.get()`

Round 9 completed with 245 passing tests and 8 `LegacyAPIWarning` messages. All eight warnings came from test assertions that still used `Setting.query.get(primary_key)`, which SQLAlchemy 2.x marks as legacy.

Round 10 replaces those test-only lookups with `db.session.get(Setting, primary_key)`. This is the SQLAlchemy 2.x primary-key lookup API and preserves the same test semantics without modifying application behavior.

### LOW - Legacy API warnings were not promoted to test failures

A future `Query.get()` regression could previously be merged while leaving the suite green and only emitting a warning.

Round 10 configures pytest to treat `sqlalchemy.exc.LegacyAPIWarning` as an error. A static regression test also scans Python sources under `app`, `tests`, and `scripts` and fails if a direct `.query.get(` call is introduced.

## Dependency-owned warnings

When Python is explicitly run with broad warning display (`-W default`), additional deprecation messages can originate inside third-party packages (notably ldap3/pyasn1 and matplotlib/pyparsing), and Python 3.13 may report SQLite resource warnings during aggressive warning diagnostics. The normal project pytest configuration already scopes known dependency deprecations, while Round 10 eliminates all project-owned SQLAlchemy legacy warnings. No dependency versions were changed in this round to avoid functional risk unrelated to the requested cleanup.

- `python -m compileall -q app tests scripts`: PASS
- `sh -n docker-entrypoint.sh`: PASS
- Full `pytest -q`: **246 passed, 0 warnings**
- `LegacyAPIWarning` is configured as a pytest error: PASS
- Static no-`Query.get()` regression invariant: PASS

1. Run PostgreSQL-backed integration tests for transactional restore, advisory locking, rollback, and sequence alignment under real concurrency.
2. Generate a complete transitive SBOM/SCA report in CI from the resolved dependency environment.
3. Review third-party dependency deprecations during the next safe dependency-maintenance cycle rather than suppressing or patching vendor code locally.
4. Continue auditing restored/persistent metadata at filesystem, URL, and command boundaries.

---

## Historical source: `SECURITY_AUDIT_ROUND11.md`

Scope: PostgreSQL backup/restore concurrency coordination, advisory-lock isolation, connection cleanup, and regression coverage.

### HIGH - Backup snapshots could overlap a destructive Full Import

Backup execution and Full Import previously used independent advisory locks. Backups were serialized per backup job and Full Imports were serialized against other Full Imports, but a backup could still read the database and persistent volumes while a Full Import was transactionally replacing those same resources. The resulting archive could therefore combine data from different restore states.

Round 11 introduces a common maintenance boundary. PostgreSQL backup workers acquire a **shared** advisory lock on the maintenance key, while Full Import acquires the **exclusive** form of the same lock. Multiple independent backups may still run concurrently, but no backup can overlap a destructive Full Import across workers or replicas. Non-PostgreSQL development/test execution uses the existing process-local locking model with the same mutual-exclusion intent.

### MEDIUM - Backup job advisory IDs shared the one-key integer space with the Full Import lock

The prior backup key was calculated as `47120000 + job_id`, while Full Import used `47129999`. Backup job ID 9999 therefore produced the same advisory key. Round 11 moves per-job backup locking to PostgreSQL's two-key advisory-lock form with a dedicated namespace (`namespace`, `job_id`), which is distinct from the single-key maintenance lock space.

### MEDIUM - PostgreSQL detection depended on URL string formatting

Lock selection previously tested `str(db.engine.url).startswith('postgresql')`. Round 11 checks SQLAlchemy's resolved dialect name instead, so driver-qualified PostgreSQL URLs and future URL formatting changes do not change concurrency behavior.

- Dynamic mocked-PostgreSQL tests exercise shared backup lock acquisition/release, busy job cleanup, exclusive Full Import lock acquisition/release, and busy-lock connection cleanup.
- Static regression tests verify distinct advisory-lock namespaces and dialect-based PostgreSQL detection.
- Full application test suite remains mandatory before packaging.

## Residual priorities

1. Run the same restore/backup concurrency scenarios against a real PostgreSQL service in CI, including two independent processes/connections.
2. Exercise forced commit failure after filesystem activation and verify database + persistent-directory rollback end-to-end.
3. Verify sequence alignment with explicit high imported IDs against real PostgreSQL `setval`/`nextval` behavior.

---

## Historical source: `SECURITY_AUDIT_ROUND12.md`

Scope: real PostgreSQL integration-test infrastructure for destructive restore, advisory locks, sequence alignment, and multi-worker coordination.

## Changes

Round 12 adds an opt-in real PostgreSQL test layer without changing production behavior:

- `docker-compose.test.yml` starts an isolated PostgreSQL 18.4 service on host port `55432` by default, backed by tmpfs.
- `scripts/run_postgres_tests.sh` starts the service with Docker Compose, waits for health, runs only `pytest -m postgres`, and always tears the test service down.
- `pytest.ini` registers the `postgres` marker.
- `tests/test_postgresql_real_integration.py` skips automatically unless `CIR_POSTGRES_TEST_URL` is configured and reachable.

## Real PostgreSQL coverage

The integration suite verifies on an actual PostgreSQL server:

1. Two different backup jobs can hold the shared maintenance boundary concurrently while Full Import is excluded.
2. An exclusive Full Import lock excludes backups.
3. The same backup job is mutually exclusive across independent worker/thread connections.
4. Explicit primary-key imports followed by `align_table_sequence()` generate the expected next ID.
5. Transactional PostgreSQL DDL rollback restores the previous table and rows after a DROP/CREATE/reload failure sequence.
6. PostgreSQL session advisory locks disappear when the owning connection closes, matching worker-crash recovery expectations.

## Execution

Normal/offline suite:

pytest

Real PostgreSQL suite with Docker:

./scripts/run_postgres_tests.sh

Or against an existing PostgreSQL server:

CIR_POSTGRES_TEST_URL='postgresql+psycopg2://user:password@host:5432/db' pytest -m postgres

The supplied test database must be disposable: integration tests create and drop uniquely named scratch tables and acquire advisory locks.

## Environment limitation during this audit

The audit runtime used to build Round 12 does not expose the Docker CLI or a PostgreSQL daemon, so the real-server tests cannot be executed here. They are deliberately skipped in the normal suite when no PostgreSQL test URL is supplied. Static validation and the complete existing regression suite remain mandatory before packaging.

---

## Historical source: `SECURITY_AUDIT_ROUND13.md`

Scope: Full Import failure injection, filesystem/database rollback boundaries, partial directory-swap recovery, and restore-state diagnostics.

### HIGH - Failure between live-directory backup and staged-directory promotion could leave a managed volume absent

The Full Import filesystem transaction used a two-step directory swap for each managed persistent volume:

1. move the current live directory to a restore backup;
2. move the staged directory into the live path.

The transaction previously recorded a volume as activated only after step 2 completed. If step 1 succeeded but step 2 failed, rollback iterated only fully activated volumes and therefore did not restore the just-created backup for that partially swapped volume. The database transaction would roll back, but the affected live filesystem path could remain absent until manual recovery.

Round 13 tracks the destructive half of each swap immediately after the live directory is moved aside. Rollback now covers every touched volume, including volumes whose staged promotion never completed, and restores them in reverse transaction order.

### HIGH - A staging exception could leave temporary restore data because the transaction object was assigned too late

The Full Import route previously constructed and staged the filesystem transaction in one expression. If `stage()` raised, assignment to `fs_txn` never completed, so the route-level exception handler could not invoke the transaction cleanup logic.

Round 13 assigns the transaction object before calling `stage()`. Any staging failure is therefore handled by the same rollback/cleanup path as later failures.

### MEDIUM - Filesystem rollback failures were logged but the UI still reported successful preservation/restoration

Rollback intentionally remains best-effort if the underlying filesystem itself refuses recovery operations. Previously the route logged those failures but still displayed the generic message saying that previous volumes were maintained or restored.

Round 13 makes rollback return the groups that could not be recovered. Their backup state is retained for a later retry/manual recovery, the server emits a critical diagnostic, and the administrative UI explicitly warns that filesystem rollback is incomplete instead of claiming success.

## Failure-injection coverage

`tests/test_security_round13_failure_injection.py` verifies:

1. failure exactly between live-directory backup and staged-directory promotion restores the old directory;
2. a failure on the second managed volume rolls back both the partially swapped volume and earlier fully activated volumes;
3. if the first rollback attempt itself fails, restore-backup metadata/directories are retained and a later rollback retry succeeds;
4. the Full Import route keeps the transaction object before staging and invokes rollback cleanup on errors.

- `python -m compileall -q app tests`: PASS.
- Full regression suite: `256 passed, 5 skipped`.
- The 5 skipped tests are the opt-in real PostgreSQL integration tests from Round 12; they require `CIR_POSTGRES_TEST_URL` or the Docker runner.
- Round 13 failure-injection suite: PASS.
- No production dependency versions changed.

1. Execute the Round 12 real PostgreSQL suite on a Docker/CI host and combine it with Full Import route-level failure injection against a disposable real database.
2. Add process-termination/crash testing around the short interval after filesystem activation and before database commit; Python exception rollback is now covered, while abrupt host/process loss requires startup recovery/journaling rather than in-process exception handling.
3. Consider a durable restore journal recording transaction token, managed paths and backup paths so startup can detect and safely reconcile an interrupted Full Import after power loss or SIGKILL.
4. Continue testing storage-specific behavior on NFS/Ceph/PVC implementations used in production, because directory rename atomicity and failure modes depend on the mounted filesystem.

---

## Historical source: `SECURITY_AUDIT_ROUND14.md`

Scope: crash consistency of destructive Full Import, durable filesystem recovery, database/filesystem commit disambiguation, startup recovery ordering, and multi-worker recovery serialization.

### CRITICAL - Process/host crash could leave database and persistent volumes on different restore generations

Round 13 made ordinary Python exceptions recoverable, including failures during directory swaps and rollback. A hard termination (`SIGKILL`, container/host crash, power loss) is different: no `except`/`finally` handler runs. If the process died after persistent directories had been promoted but before the database transaction committed, PostgreSQL would roll back the database while the new filesystem snapshot remained active. Conversely, if the database commit completed and the process died before old filesystem backups were removed, startup needed a reliable way to distinguish a committed restore from an uncommitted one.

Round 14 adds a durable Full Import recovery journal under `BACKUP_DIR`. The journal is written atomically with `fsync` before destructive filesystem renames and records only a validated restore token plus managed-group state; recovery paths are always re-derived from configured managed directories rather than trusted from journal-provided arbitrary paths.

A reserved Full Import commit token is written to `Setting` inside the same database transaction as the restored data. On startup, before bootstrap writes occur:

- a matching database token proves the destructive database transaction committed, so the promoted filesystem snapshot is kept and stale backup/staging directories are finalized;
- a missing/non-matching token means the database transaction did not commit, so previous persistent directories are restored from their durable backups and newly-created volumes with no predecessor are removed;
- malformed journals fail closed without modifying live volumes;
- a stale database marker left after successful journal cleanup is harmless and is removed on the next startup.

Journal state is advanced around each destructive rename (`moving_backup`, `backup_moved`, `promoting`, `activated`, `restoring`, `removing_new`, `finalizing`) so recovery remains idempotent across another crash during recovery itself. Directory renames are followed by best-effort parent-directory `fsync`.

### HIGH - Concurrent workers could race startup recovery

PostgreSQL startup recovery now runs while holding the same exclusive maintenance advisory-lock namespace used by Full Import. This prevents another worker/replica from running backup/restore maintenance while recovery decides whether the database/filesystem restore committed. Non-PostgreSQL development environments continue to use the process-local maintenance lock.

- `python -m compileall -q app tests`: PASS.
- Round 11 + Round 13 + Round 14 focused tests: 17 passed.
- Full suite: 263 passed, 5 skipped.
- The 5 skipped tests are the existing opt-in real PostgreSQL integration tests from Round 12 because this execution environment does not expose a PostgreSQL/Docker service.
- New Round 14 tests exercise pre-commit crash rollback, post-commit crash finalization, restoration when no prior directory existed, malformed-journal fail-closed behavior, startup ordering, commit-token ordering, and PostgreSQL advisory-lock coverage.

1. Execute the existing opt-in integration suite against the disposable PostgreSQL Docker service and add a real PostgreSQL crash/restart scenario around the Round 14 commit token.
2. Exercise actual worker termination (`SIGKILL`) from an external test harness while Full Import is paused at controlled checkpoints; unit failure injection cannot perfectly emulate kernel/container termination semantics.
3. Review durability assumptions for filesystems/storage classes used in production (local ext4/xfs, Docker volumes, NFS/network storage); rename/fsync guarantees vary by storage backend.
4. Continue final cross-cutting security audit and dependency/SBOM work before release-candidate packaging.

---

## Historical source: `SECURITY_AUDIT_ROUND15.md`

Scope: real process-termination semantics for Full Import crash recovery, PostgreSQL crash/restart coverage, and safety of the destructive integration-test harness.

### HIGH - Round 14 recovery had only exception/failure-injection coverage, not actual process death

Round 14 made Full Import crash recovery durable and unit-tested the journal/commit-token decision. Those tests could not prove that the mechanism still works when the restoring Python process disappears without executing any `except`, `finally`, SQLAlchemy session cleanup, or filesystem-transaction cleanup.

Round 15 adds an external crash worker used by integration tests. The worker activates the production `_FullImportFilesystemTransaction`, writes the real recovery journal and database commit marker, then pauses at a controlled checkpoint. The parent process terminates it with `SIGKILL` and creates a fresh Flask/SQLAlchemy context to run startup recovery. Two windows are exercised:

- pre-commit `SIGKILL`: the uncommitted database marker disappears when the process/database connection dies, so startup restores the previous filesystem snapshot;
- post-commit `SIGKILL`: the durable marker proves the database commit completed, so startup keeps the promoted filesystem and finalizes stale stage/backup artifacts.

The standard suite executes both process-death scenarios with SQLite to validate kernel/process semantics even without Docker. The opt-in real PostgreSQL suite now repeats both scenarios against the disposable PostgreSQL service, covering actual PostgreSQL transaction/session behavior.

### MEDIUM - Manually configured PostgreSQL integration URL could accidentally target a non-test database

`CIR_POSTGRES_TEST_URL` previously accepted any reachable PostgreSQL database. Round 15 crash tests intentionally use application tables such as `Setting`, so accidentally pointing the test suite at a production-like database would be unsafe.

The PostgreSQL integration fixture now refuses database names that do not contain `test` unless `CIR_POSTGRES_TEST_ALLOW_NONTEST_DATABASE=1` is explicitly set. The override is documented only for isolated disposable CI databases. The default Docker service continues to use `cir_test` and requires no override.

- External `SIGKILL` crash/restart tests on SQLite: 2 passed.
- Full suite without PostgreSQL service: 265 passed, 7 skipped.
- The 7 skips are the opt-in real PostgreSQL integration tests: the previous five Round 12 tests plus two Round 15 real-PostgreSQL `SIGKILL` scenarios.
- `python -m compileall -q app tests`: PASS.
- Shell syntax checks for project scripts: PASS.
- No application dependency changes.

1. Run `./scripts/run_postgres_tests.sh` on a Docker-capable host/CI runner and record the seven real-PostgreSQL results; this execution environment still has no Docker daemon.
2. Validate crash durability on the production storage classes actually used in deployment (Docker local volumes, ext4/xfs, and any NFS/network-backed PVC), because rename/fsync durability guarantees are filesystem-specific.
3. Perform the final cross-cutting application security audit (authentication/session boundaries, tenant isolation, filesystem/configuration trust boundaries, outbound HTTP, backup/import/export, secret handling).
4. Regenerate a transitive SBOM/SCA report in network-enabled CI before release-candidate packaging.

---

## Historical source: `SECURITY_AUDIT_ROUND16.md`

Scope: final cross-cutting review of authentication/session boundaries, tenant isolation, filesystem-backed persistent metadata, outbound integrations, backup/import/export, background schedulers, audit retention, and secret handling.

### HIGH — Notification templates/types crossed the active-tenant boundary

`NotificationTemplate` and `NotificationType` carry tenant ownership, but several administrative CRUD, default-selection, preview and workflow-import paths queried rows by global numeric ID or unscoped type/kind. A tenant administrator able to address another tenant's row ID could therefore enter edit/delete/clone/default flows or select a foreign template.

Round 16 centralizes active-tenant template/type queries and writable lookups. New defaults and imports are assigned to the active tenant; global legacy rows may remain readable where compatibility requires it, but they are never mutated as another tenant's local configuration. Workflow import/diff and notification preview/default resolution now honor the same tenant boundary.

### HIGH — AI chatbot knowledge base and database context were not tenant-isolated

The AI knowledge-document model includes `tenant_id`, but upload/list/delete and knowledge aggregation were global. In addition, a superuser using one active tenant could build an AI database context containing rows from every tenant.

Round 16 assigns uploaded AI documents to the active tenant, scopes list/delete/knowledge aggregation, and always filters tenant-aware database-context tables to the active tenant even for superusers. AI plugin administrative authorization now follows the application's active-tenant `can_admin()` boundary.

### HIGH — AI document deletion trusted persistent filenames

Deletion of an AI knowledge document used the database-backed stored filename as a filesystem path. Legacy, restored or corrupted metadata could therefore escape the managed AI document directory.

Round 16 adds a canonical path helper that requires an unchanged secure basename resolving to a direct child of `AI_CHATBOT_DOC_DIR`. Upload and deletion use the same boundary and new files receive restrictive permissions where supported.

### HIGH — Stored SMTP/LDAP/SSO secrets were reflected back into administrative HTML

SMTP passwords, LDAP bind passwords and SSO client secrets are encrypted at rest, but administrative forms decrypted them and placed the plaintext value back into password input fields. That unnecessarily exposed secrets to the browser DOM, extensions, local inspection and accidental captures.

Round 16 never renders the stored secret. Password fields are blank on GET; submitting a blank value preserves the existing credential. Tests assert that known stored secrets are absent from rendered HTML.

### HIGH — Background scheduler work defaulted to the default tenant

Background threads have no authenticated request user. Tenant-aware setting helpers therefore fell back to the default tenant while deadline/reminder/backup schedulers could process records belonging to other tenants. This could apply the wrong timezone, notification settings, SMTP configuration, scheduler status or audit context to another tenant's work.

Round 16 adds an explicit `tenant_execution_context()` for non-request jobs. Deadline and reminder scheduler passes iterate tenants independently, and scheduled backups evaluate each job inside its owning tenant. Poll intervals are derived safely across tenants while per-tenant work remains isolated.

### HIGH — Audit retention and manual purge were global while retention settings are tenant-specific

Audit rows carry `tenant_id`, but normal retention, manual keep-count/older-than purge and the admin audit query used the global table. A tenant-specific retention action could therefore delete or expose another tenant's audit records.

Round 16 scopes normal retention, manual purge and the admin audit view to the active tenant. The request-user-free restore helper remains capable of global operation only when no tenant is explicitly supplied; when a tenant ID is supplied, its deletion/count/overflow operations are strictly tenant-scoped.

- `python -m compileall -q app tests`: PASS.
- Pytest collection: 284 tests.
- Complete suite executed in isolated groups: 277 passed, 7 skipped, 0 failed.
- The 7 skipped tests are the opt-in real PostgreSQL integration tests; this runtime does not expose Docker/PostgreSQL.
- Round 16 targeted tests cover notification/template tenant isolation, AI tenant isolation and path confinement, secret non-reflection, background tenant execution, and tenant-scoped audit retention.
- No application dependency was changed in this round.

1. Execute the seven opt-in PostgreSQL tests on a Docker-capable host/CI and retain the results as release evidence.
2. Run complete transitive SCA/SBOM generation in a network-enabled CI environment and gate high/critical dependency findings.
3. Review production container/runtime settings, reverse-proxy headers, TLS termination, backup key custody, secret injection and least-privilege filesystem/database permissions.
4. Perform a final release-candidate regression using the exact production image and PostgreSQL version before tagging the hardened release.

---

## Historical source: `SECURITY_AUDIT_ROUND17.md`

Scope: software supply chain/SBOM, current runtime security releases, container and Kubernetes least privilege, production secret injection, and reverse-proxy trust boundaries.

### HIGH - PostgreSQL 18.4 was superseded by the August 2026 security release

The runtime/test manifests still referenced PostgreSQL 18.4. PostgreSQL 18.6 was released on 2026-08-13 and fixes multiple security issues affecting earlier 18.x releases, including arbitrary-code-execution class defects. Runtime, integration-test, and Kubernetes manifests now use PostgreSQL 18.6.

### HIGH - Login IP rate limiting trusted X-Forwarded-For from untrusted clients

The login rate-limit identity previously preferred the first `X-Forwarded-For` value regardless of the peer that supplied it. A direct client could therefore rotate a forged header and defeat the per-IP lockout boundary. CIR now ignores forwarding headers unless `request.remote_addr` belongs to an explicitly configured `CIR_TRUSTED_PROXY_CIDRS` network. For trusted proxies the chain is evaluated from the application side toward the client and the first untrusted hop is selected.

### MEDIUM - Container permission fallback was root-by-default

The Docker entrypoint could continue as root after a persistent-volume ownership failure unless the operator disabled the fallback. The default is now fail-closed (`CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE=0`); retaining root after a volume-permission failure requires an explicit opt-in. The entrypoint also applies `umask 027`.

### MEDIUM - Production container/orchestrator manifests lacked several least-privilege controls

A production Compose override now requires an explicit production image reference, sets the web root filesystem read-only, uses a bounded `/tmp` tmpfs, enables `no-new-privileges`, drops all capabilities and adds only the startup capabilities required by the current entrypoint, forces production/CSRF/Secure-cookie/HSTS settings, and disables root fallback. Kubernetes now disables automatic service-account token mounting, uses RuntimeDefault seccomp, drops application capabilities, uses a read-only application root filesystem, provides a bounded writable `/tmp`, and adds health probes. The active application image is version-pinned rather than `latest`.

### MEDIUM - Kubernetes example embedded a deployable placeholder database Secret

The PostgreSQL manifest no longer embeds a Secret with a placeholder password. It requires an externally provisioned `cir-postgres-secret`. `k8s/secrets.example.yaml` is intentionally excluded from Kustomize and exists only as an operator template. The application deployment now also supplies the required `SETTING_ENCRYPTION_KEY` secret in production.

### MEDIUM - Core secrets were inline-environment only

`DATABASE_URL`, `SECRET_KEY`, `ADMIN_INITIAL_PASSWORD`, and `SETTING_ENCRYPTION_KEY` can now be read from `NAME_FILE` paths for Docker/Kubernetes secret-volume style injection. Supplying both the inline variable and its `_FILE` counterpart fails closed; unreadable, oversized, non-UTF-8, or NUL-containing secret files are rejected.

## Supply-chain inventory

`sbom/SBOM_ROUND17.cdx.json` is generated from the isolated offline environment and contains 47 reachable Python components. It records the direct/transitive classification, dependency graph, package URL, and SHA-256 plus wheel filename when a matching supplied wheel is available. `scripts/generate_sbom.py` performs the inventory without contacting a package index.

`scripts/run_sca.sh` is a release/CI gate for `pip-audit` and writes `SCA_PIP_AUDIT.json`. This analysis container cannot reach PyPI/OSV and does not contain the `pip-audit` tooling wheel, so a live transitive vulnerability-service query could not be executed here. The script fails clearly rather than silently treating the missing audit engine as success.

Direct dependency freshness was reviewed separately. Security-patched pins already used by CIR were retained where a newer release was not established as a necessary security update, avoiding an unnecessary compatibility change in this hardening round.

## Runtime security updates

- Python base image: `python:3.12-slim-trixie` -> `python:3.12.14-slim-trixie` to pin the August 2026 Python 3.12 security release instead of a floating patch tag.
- PostgreSQL: `18.4` -> `18.6` in Docker Compose, PostgreSQL integration tests, and Kubernetes.

- Offline SBOM generation: PASS, 47 Python components.
- `pip check` in the isolated wheel environment: PASS.
- Round 17 targeted/container/previous-round tests: PASS.
- Full standard pytest suite: 286 passed, 7 skipped; all skips are the opt-in real-PostgreSQL tests when no test server is configured.
- `python -m compileall` / Python compilation checks: PASS.
- Shell syntax checks for entrypoint/SCA/PostgreSQL test scripts: PASS.

## Residual / release-candidate priorities

1. Run `scripts/run_sca.sh` in a network-enabled CI/release job with `pip-audit` installed and gate release on unresolved high/critical findings.
2. Build the production image, record its immutable registry digest, and use that digest in production Compose/Kubernetes promotion instead of relying only on a version tag.
3. Execute the seven opt-in PostgreSQL integration tests against PostgreSQL 18.6 through Docker/CI.
4. Run an image/container scanner (for example Trivy/Grype or an equivalent organizational scanner) against the final image, including OS packages installed by LibreOffice and PostgreSQL client dependencies.

---

## Historical source: `SECURITY_AUDIT_ROUND18.md`

Release lineage: baseline `0.8.0`; Rounds 1-18 are internal development/audit iterations of functional release `0.9.0-1`, not separate 0.8.x releases.

Scope: final release consistency, release metadata, packaging integrity, deployment policy checks, SBOM refresh, and explicit separation of offline versus infrastructure-dependent production gates.

### MEDIUM - Release build metadata no longer represented the hardened source state

The project still declared build `20260718` even though the hardened source had advanced through security rounds completed on 2026-09-02. This made runtime/UI/deployment metadata stale and weakened traceability between a deployed artifact and the reviewed source.

Round 18 finalizes release-candidate metadata at build `20260902` for functional release `0.9.0-1`, which cumulatively contains the work developed throughout Rounds 1-18 from the 0.8.0 baseline. Docker Compose, Kubernetes, README files, SBOM metadata and release tests are synchronized with the release candidate.

## Release-candidate gate

`scripts/verify_release_candidate.py` now checks source-tree invariants that must not drift between releases: VERSION/BUILD synchronization, immutable-style Kubernetes tagging (no `:latest`), production Compose and Kubernetes hardening controls, sensitive packaging exclusions, and CycloneDX SBOM consistency. It can additionally validate the syntax of a final `image@sha256:` production reference.

The release packaging script writes a SHA-256 sidecar for the generated ZIP so the artifact can be verified independently after transfer.

`sbom/SBOM_ROUND18.cdx.json` refreshes the transitive Python inventory for the RC from the supplied offline wheel environment. Dependencies are unchanged from Round 17.

## External gates intentionally not claimed as complete

The RC remains conditional until a network-enabled SCA run, the seven real-PostgreSQL integration tests, a scanner run against the exact final container image, and immutable registry digest promotion are completed. These requirements are documented in `docs/RELEASE.md` and are not represented as passing when the required infrastructure is unavailable.

- Full standard pytest suite: **292 passed, 7 skipped, 0 failed**. The seven skips are the opt-in real-PostgreSQL tests because Docker/PostgreSQL is not available in this analysis environment.
- Round 18 targeted release/packaging tests: PASS.
- `scripts/verify_release_candidate.py`: PASS.
- Offline CycloneDX SBOM refresh: PASS, 47 Python components.
- `pip check` in the isolated exact-wheel environment: PASS.
- `python -m compileall` for application/tests/scripts: PASS.
- Shell syntax checks using each script's declared interpreter: PASS.
- Docker Compose and Kubernetes YAML parsing: PASS.
- Docker daemon availability in this environment: unavailable; therefore real PostgreSQL/container-image gates remain pending by design.

---

## Historical source: `SECURITY_UPDATE_RC_R4.md`

Release: `0.9.0-1`  
Build: `20260902`

## Reason for R4

The live `pip-audit` run performed after RC R3 found known vulnerabilities in two directly pinned dependencies:

- `pypdf==6.10.2`, including denial-of-service conditions fixed across later 6.x releases;
- `cryptography==46.0.7`, including certificate-verification/resource-exhaustion issues and a PKCS#7 decryption oracle fixed in later releases.

RC R4 updates only these direct runtime pins:

- `pypdf==6.16.2`
- `cryptography==50.0.1`

No application feature or database-schema change is introduced by R4.

## Required production revalidation

Because dependency binaries changed, the production gate must be rerun in a network-enabled environment using the exact R4 requirements. Promotion requires:

1. `python -m pip check`
2. `python -m pytest -q`
3. `./scripts/run_postgres_tests.sh`
4. `python scripts/verify_release_candidate.py`
5. `./scripts/run_sca.sh` with no unresolved vulnerability in the release environment
6. multi-architecture image build and final container-image scan
7. immutable registry digest promotion

The analysis environment used to assemble R4 cannot download the new wheels, so it does not claim binary-level regression or a post-update live SCA result. Those checks must be performed on the release host before production promotion.

---

## Historical source: `RC_R5_TEST_HARNESS_FIX.md`

Version: `0.9.0-1`  
Build: `20260902`

## Context

During final validation of RC R4 with the security dependency updates (`pypdf==6.16.2`, `cryptography==50.0.1`), all external gates passed except one SQLite process-crash test:

`tests/test_security_round15_process_crash.py::test_sigkill_after_db_commit_keeps_promoted_filesystem`

The worker did not reach its checkpoint within the test harness timeout. The equivalent real-PostgreSQL pre-commit and post-commit SIGKILL tests both passed (`7 passed` for the PostgreSQL integration group), so there was no evidence of an application crash-recovery regression.

## Change

The SQLite external-process checkpoint timeout is increased from 15 seconds to 30 seconds and can be overridden with:

```bash
CIR_CRASH_TEST_CHECKPOINT_TIMEOUT=45 python -m pytest -q tests/test_security_round15_process_crash.py
```

Values below five seconds are clamped to five seconds. Invalid values fall back to 30 seconds.

The test still fails if the worker exits early or does not reach the checkpoint. The failure message now includes elapsed time and the effective timeout, in addition to worker stdout/stderr.

## Runtime impact

None. Only test-harness code changed. Application code, database schema, production configuration and dependency pins are unchanged from RC R4.

## Verification in the packaging environment

- post-commit SIGKILL test: 5 consecutive passes;
- full standard suite: `295 passed, 7 skipped` using the available offline dependency environment;
- the seven skipped tests are the opt-in real-PostgreSQL tests.

The final production promotion still requires rerunning the standard suite on the target validation host with the RC R4/R5 security dependency versions installed.

---

## Historical source: `RC_R6_CONTAINER_HARDENING.md`

Release lineage: baseline 0.8.0 -> cumulative release 0.9.0-1. RC R6 changes only the container build/runtime packaging.

## Why

Trivy reported the old `cryptography 46.0.7` and `pypdf 6.10.2` even though the R5 requirements pin 50.0.1 and 6.16.2. The image copied historical CycloneDX files (notably Round 6/17 SBOMs), and Trivy explicitly warned that third-party SBOMs were being consumed. Those historical artifacts are source/release documentation and are not runtime dependencies.

The Debian scan also showed a broad dependency surface from GUI LibreOffice packages and curl. CIR uses LibreOffice only for headless Writer conversion.

- `.dockerignore` excludes historical SBOMs, audit/release/migration markdown, pytest artifacts and tests from the runtime image. These files remain in the downloadable source ZIP.
- Docker runtime uses `libreoffice-writer-nogui` instead of `libreoffice-writer` + `libreoffice-core`.
- `curl` is removed; the Docker HEALTHCHECK uses Python `http.client`.
- `apt-get upgrade -y` is run before runtime packages are installed so available Debian security updates are incorporated.

## Required external validation

Rebuild with `--pull --no-cache` (supported by the R6 build script) and rerun Trivy. Residual Debian findings with no stable fixed version must be assessed against Debian Security Tracker and actual runtime reachability; they are not silently ignored.

---

## Historical source: `RC_R7_FINAL_CONTAINER_MINIMIZATION.md`

Release lineage: **0.8.0 baseline -> 0.9.0-1 release candidate**. R7 is a packaging/container-hardening iteration of 0.9.0-1 and does not change application functionality.

## Why R7 was required

The R6 Trivy scan no longer reported the historical pypdf/cryptography findings, but still reported two Python HIGH findings for `msgpack 1.1.2` and `setuptools 70.3.0`. Those versions originate from the CycloneDX document embedded in pip (`pip/_vendor/bom.cdx.json`), not from CIR runtime requirements. The same scan still reported Debian HIGH/CRITICAL findings in libraries pulled by the Python/Debian base and the headless LibreOffice conversion stack.

- Dockerfile converted to a two-stage build.
- Python application dependencies are installed into `/opt/cir-venv` in the `python-deps` stage.
- `pip`, `setuptools`, and `wheel` are removed from the application venv after installation.
- The runtime stage removes the packaging tooling shipped by the official Python base image as well, including pip's embedded third-party SBOM that can be interpreted by vulnerability scanners as installed packages.
- Runtime still installs only `ca-certificates`, `gosu`, `fonts-dejavu-core`, and `libreoffice-writer-nogui` with `--no-install-recommends`.
- No Debian package metadata is deleted or hidden. Full Trivy OS results remain visible and must be evaluated against Debian's security tracker/upstream patch availability.

## Production validation

Build from a clean/pulled base (the multi-arch script does this by default):

```bash
./scripts/build_multiarch_image.sh --repository desalvo/cybersecurity-incident-registry --tag 0.9.0-r7
```

Confirm application dependency versions:

```bash
docker run --rm desalvo/cybersecurity-incident-registry:0.9.0-r7 \
  python -c "import pypdf, cryptography; print(pypdf.__version__, cryptography.__version__)"
```

Confirm packaging tools are absent from runtime:

```bash
docker run --rm --entrypoint sh desalvo/cybersecurity-incident-registry:0.9.0-r7 -c \
  'command -v pip && exit 1 || true; python -c "import importlib.util; assert importlib.util.find_spec(\"setuptools\") is None"'
```

Run and retain the full scan:

```bash
trivy image --severity HIGH,CRITICAL --format json --output TRIVY_R7.json \
  desalvo/cybersecurity-incident-registry:0.9.0-r7
trivy image --severity HIGH,CRITICAL desalvo/cybersecurity-incident-registry:0.9.0-r7
```

The primary gate remains the **full** report; do not delete Debian package metadata and do not treat `--ignore-unfixed` as proof that the image is vulnerability-free.

---

## Historical source: `HOTFIX6_TEST_ALIGNMENT.md`

This maintenance update does not change application behavior.

It aligns legacy regression expectations and README wording with the Hotfix 6 Alfresco incident naming convention:

- incident folders use `incident-<id> - <incident-name>`;
- canonical reports use `incident-<id> - <incident-name> - report.pdf`;
- the README explicitly states that the Alfresco plugin is `disabilitato per default`, preserving the documented default and the legacy regression invariant.

The Alfresco parent-resolution regression now supplies an explicit incident name and verifies the Hotfix 6 path instead of the pre-Hotfix-6 `incident-<id>` path.

---

## Bootstrap export and CI stabilization (RC1-RC11) — 2026-09-20

After cumulative Hotfix 7, development remained within functional version **0.9.0-1** and added an anonymized bootstrap export for tenant `default`. The RC sequence was not a sequence of new functional versions; it was an implementation/regression-hardening cycle of the same 0.9.0-1 source line.

- RC1 introduced the default-tenant bootstrap profile, selective workflow/template retention, secret stripping and destination-side admin password regeneration.
- RC2 corrected canonical bootstrap admin identity sanitization (`admin@example.local`) without weakening generic email redaction.
- RC3 introduced automatic production-digest recording after successful promotion.
- RC4 incorporated `actions/checkout@v7` and `actions/setup-python@v7`.
- RC5 replaced the invalid assumption that a retagged OCI index must preserve the top-level digest with descriptor-level verification of approved amd64/arm64 manifests and attestations.
- RC6 adapted digest recording to protected `main` by using a dedicated metadata branch and pull request, plus metadata-only Docker-build suppression.
- RC7 added more robust Buildx manifest inspection/retry diagnostics.
- RC8 corrected workflow YAML serialization and added YAML parsing regression coverage.
- RC9 made the production-digest tests valid in both pre-promotion `PENDING_HOTFIX_REBUILD` state and post-promotion immutable-digest state.
- RC10 incorporated `actions/upload-artifact@v7`.
- RC11 incorporated the reviewed `aquasecurity/setup-trivy` v0.3.1 commit pin while keeping Trivy scanner `v0.74.0`.

The stabilized flow is: protected-branch PR -> quality/PostgreSQL/SCA gates -> multi-arch candidate -> Trivy gate -> promotion -> OCI descriptor verification -> automated production-digest PR -> metadata-only checks -> merge without Docker rebuild.

