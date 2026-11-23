# CIR 0.10.0-1 — RC27 security decision gate

## Evidence and scope

Diagnostic run **45227508842** produced **81 HIGH and 1 CRITICAL** OS package findings per architecture, **33 distinct CVEs**, and identical package/CVE/version/severity tuples on amd64 and arm64. Debian APT inventory was complete. The gate failed because the previous acceptance expired **2026-10-20** and because of new/unreviewed findings. **No risk is approved by this document.**

Historical acceptance coverage: 23 CVE identifiers present in the old record; 10 identifiers not found there. A historical entry is not valid approval for the new image.

## Decisions required before production

1. For each CVE in `TRIVY_RC27_REVIEW_REGISTER.csv`, consult the current Debian Security Tracker for the exact Trixie package/version, and record the evidence date and vendor disposition. Do not equate absence of `FixedVersion` with absence of a patch.
2. Inspect reachable code paths. Prioritize `libxml2` CRITICAL, document parsers, LibreOffice conversion, XML import, attachments, TLS and authentication integrations. Treat untrusted document processing as potentially exposed unless tested or mitigated.
3. Verify runtime controls (non-root, read-only rootfs, no-new-privileges, dropped capabilities, network restrictions, input size limits, document conversion isolation). These are conditions to test, not assumed controls.
4. Remediate any available fixes first. For residual findings, document risk owner, rationale, affected package and exact version, CVE, mitigating controls, evidence, decision date and finite expiry.
5. Obtain explicit authorized sign-off. Only then update `TRIVY_RISK_ACCEPTANCE_R8.json` and rerun both architecture gates on the exact OCI digest. Do not suppress unknown/new findings or auto-renew the old policy.

## Current release decision

**HOLD**: no verified reachability verdict for all CVEs, no current sign-off, and risk acceptance expired. The application and LibreOffice document-conversion functionality remain unchanged.

## Next technical work

Capture vendor-level applicability evidence and test the document-processing threat boundary; only then propose narrow, time-limited risk acceptance for items that cannot be remediated. This RC27 adds an auditable review register but does not claim to solve Trivy findings.
