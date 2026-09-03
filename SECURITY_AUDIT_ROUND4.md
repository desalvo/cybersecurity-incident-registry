# Security Audit Round 4

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

## Scope
Exception disclosure, SMTP/LDAP outbound connections, encryption-key lifecycle, privilege escalation, and CSRF/method safety.

## Confirmed findings and remediations

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
