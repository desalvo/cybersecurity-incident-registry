# CIR 0.10.0-1 RC26 — security review decision package

Evidence: GitHub Actions run `45224547175`, amd64 and arm64 JSON reports. This is a **review draft, not an authorization to suppress CVEs**.

## Findings

Both architectures: **81 HIGH, 1 CRITICAL, 33 distinct CVEs**; 82 package/CVE occurrences. No `FixedVersion` is supplied in the scanner data. Both Debian inventories were successfully collected. The Trivy production gate rejected both scans because the previous acceptance expired and findings remain unreviewed.

## Review method (mandatory for every future scan)

1. Check the exact Debian release, package version, source package, security tracker entry, DSA and backported patches for **each CVE**. Record evidence URL, review date and vendor status; do not equate NVD severity with Debian risk.
2. Check runtime call paths, especially untrusted document conversion via LibreOffice, XML parsers, network and cryptographic libraries. A package's presence or reverse dependency is not proof of exploitation, but neither is non-direct usage proof of safety.
3. Prefer available supported fixes without removing functionality. Validate DOCX/PDF conversion, import/export, TLS, authentication and tenant isolation after changes.
4. For residual CVEs, record exact package/version, compensating controls, risk owner, scope, expiry and explicit approval. Do not automatically renew the acceptance that expired on 2026-10-20.
5. Scan both architectures of the **exact immutable OCI digest** before promotion. Any new HIGH/CRITICAL, available fix, changed package scope or expired acceptance must fail closed.

## Priority and decisions

- `CVE-2026-6653` in `libxml2` is reported CRITICAL: document-processing reachability and vendor status require independent verification before acceptance.
- XML/Expat/Raptor/TIFF/SQLite: possible untrusted data processing; retain conversion functionality and review individually.
- OpenSSL/libcurl: review TLS paths and legacy provider loading; do not assume legacy provider is enabled.
- GnuPG/util-linux and other OS utilities: evaluate permissions, container hardening and reachability; a temporary scoped acceptance may be proposed, but is not granted.

## Decision

**NO GO for production** until formal review and gate PASS. This document does not modify Trivy policy, application runtime or risk acceptance.

See `TRIVY_RC26_REVIEW_REGISTER.csv` for all 82 package/CVE occurrences and evidence status.
