# CIR 0.10.0-1 RC13 — production security remediation checkpoint

This is **not** a new risk acceptance and **not** a production approval.

## Evidence

The attached historical Trivy artifact `trivy-b16b9dc9011cb5c7294b6e608151d27aec5b82f8.zip` contains only the amd64 scan of OCI index `sha256:6a8607f840fa47fd79f848cf55290906455d6aa61feeec52259fdb20aa2513a0`. Its normalized findings are in `rc13-previous-amd64-findings.json`. The evidence reports 79 HIGH/CRITICAL package occurrences, including one CRITICAL, with no FixedVersion populated. This does not establish that current Debian repositories lack fixes.

## Runtime decision

Do not remove `libreoffice-writer-nogui` without replacing and testing the DOCX-to-PDF path in `app/form_generation.py`. It is required by the current release verifier. Keep `gosu`, `tzdata`, and the existing runtime hardening until their runtime usages have been assessed. No unverified package removals are made in RC13.

## Required promotion gates

1. Rebuild from updated base image with the existing pull/no-cache CI configuration.
2. Produce Trivy reports for **both** linux/amd64 and linux/arm64 even if one fails; fail closed if either rejects.
3. Compare installed versions and FixedVersion fields against the previous evidence; patch any fixable vulnerabilities.
4. Review residual OS findings with an accountable approver, package/version scopes, mitigations and new expiry; do not copy forward expired approvals.
5. Re-run full CI and scan the exact immutable candidate OCI digest. Promote only after every gate passes.

`TRIVY_RISK_ACCEPTANCE_R8.json` is deliberately unchanged: it expired 2026-10-20. `PRODUCTION_IMAGE_DIGEST` remains pending.
