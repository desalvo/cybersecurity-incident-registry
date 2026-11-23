# CIR 0.10.0-1 — RC32 production risk decision

**Status: DRAFT — NOT APPROVED. Production promotion remains blocked.**

## Evidence

- GitHub `[ci-security]` run `45227508842`, 2026-11-23: both `linux/amd64` and `linux/arm64` show **81 HIGH + 1 CRITICAL** occurrences, **33 distinct CVEs**. Both architectures have the same 82 package/CVE findings.
- No `FixedVersion` was populated in the provided Trivy reports. This is not proof of absence of an upstream or Debian fix.
- The old policy expired on 2026-10-20 and applies to a different reviewed baseline. It has **not** been renewed.
- The full CI after RC31 built a multiarch candidate but did not promote it because the production gate rejected the old policy.

## Proposed time-bounded decision

A **14-day**, exact-package-and-version-scoped exception may be considered by the authorized risk owner only after reviewing the accompanying CSV matrix. The proposal lists 33 CVEs with exact package scopes and anchored installed versions, but deliberately has no approval date, signature or operational effect. In particular, the CRITICAL `libxml2` finding is **not** considered non-exploitable; document processing can expose native parsers to untrusted input.

Before approval, verify the Debian Security Tracker status for each CVE and record mitigations for document/XML processing, TLS integrations, and OS utility exposure. Keep non-root, read-only root filesystem, no-new-privileges, dropped capabilities, least-privilege access, document validation and size limits where supported. These are required conditions to verify, **not claims that every condition has been verified**.

## Mandatory approval and production sequence

1. Complete the CSV review, including exposure and mitigations for every finding, especially `libxml2` and network/crypto libraries.
2. Obtain explicit approval from the authorized risk owner with date and signature/record ID; set a 14-day expiry from that approval.
3. Only then update `TRIVY_RISK_ACCEPTANCE_R8.json` with approved CVEs, exact package/version scope and per-CVE expiry. Preserve all blocking rules for new, fixable or Python vulnerabilities.
4. Run full CI and Trivy against **both architectures of the exact production candidate digest**, with current advisory data; do not use the prior diagnostic image as production evidence.
5. If all gates pass, promote the scanned immutable OCI index, verify the published digest and merge the production-digest metadata PR.
6. Reassess weekly and immediately on a newly available fix, new CVE, change in package versions, or expiry. The approval is not renewable by automation.

**No Debian package, application functionality, security gate or active risk policy is changed by RC32.**
