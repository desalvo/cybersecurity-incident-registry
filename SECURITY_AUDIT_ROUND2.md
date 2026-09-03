# Security Audit - Round 2

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
