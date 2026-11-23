# CIR 0.10.0-1 RC28 — 14-day residual-risk decision package

**Status: PROPOSAL ONLY — NOT AN APPROVAL.** The user authorized preparation of a 14-day review, not automatic production promotion or blanket acceptance of 33 CVEs.

## Evidence and limits

The supplied CI evidence for run `45227508842` reports 82 HIGH/CRITICAL package/CVE occurrences per architecture (81 HIGH, 1 CRITICAL), covering 33 distinct CVEs, with matching findings on amd64 and arm64. APT candidates for the prioritized packages matched installed versions in that run. Trivy did not report `FixedVersion`; this is not proof that Debian has no available fix. The current `TRIVY_RISK_ACCEPTANCE_R8.json` expired 2026-10-20 and remains unchanged.

## Proposed review decision

Retain Debian 13, LibreOffice and all CIR functionality. Request a maximum **14-day acceptance from the actual signed decision date** for *only* specifically reviewed OS CVE/package/version tuples. Review weekly and immediately when vendor fixes, new CVEs or changed packages appear. Any new finding, newly patchable CVE, unexpected version or Python HIGH/CRITICAL continues to block the gate. This proposal is not a substitute for testing the runtime controls.

### Prioritized conditions before sign-off

1. Verify the exact candidate OCI digest and both architecture reports from the same build. Recheck Debian Security Tracker for all 33 CVEs on the decision date, recording the actual vendor status and any backports.
2. Prioritize `libxml2` CRITICAL, document/XML/TIFF parsers and TLS libraries. Confirm document input controls and isolation; do not claim these paths are unreachable without evidence.
3. Confirm non-root execution, no-new-privileges, dropped capabilities, read-only root filesystem, writable temporary storage constraints and access restrictions in the actual production deployment.
4. Confirm PostgreSQL-backed production operation and document-conversion regression tests, and maintain backup/rollback readiness.
5. Record an accountable risk owner, explicit per-CVE decision, rationale, signed approval time and exact expiry. Do not extend old acceptance dates automatically.
6. After approval, update the production gate's exact CVE/package/version scopes only for approved items; rerun SCA and Trivy on both platforms; promote the scanned digest only after all required gates PASS.

## Deliverables

- `TRIVY_RC28_14_DAY_RISK_PROPOSAL.json`: 33 CVE-level pending decisions, including package/version scopes.
- `TRIVY_RC28_APPROVAL_REGISTER.csv`: review worksheet for the authorized risk owner.
- This document: approval checklist and non-negotiable gates.

No runtime, Dockerfile, Trivy gate or risk-acceptance policy change is made in RC28. The application must remain available through a separately authorized operational decision; an unapproved image must not be represented as production-approved.
