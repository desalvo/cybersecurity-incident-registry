# Security audit – Round 3

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

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
