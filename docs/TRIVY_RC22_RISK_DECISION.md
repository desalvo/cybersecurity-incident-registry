# CIR 0.10.0-1 — RC22 security decision dossier

Source: CI `[ci-security]` run **45200319586**, both amd64 and arm64 artifacts. This is a **review proposal**, not an approved risk acceptance.

## Verified observations

| Platform | HIGH occurrences | CRITICAL occurrences | Unique CVEs | FixedVersion populated | APT evidence |
|---|---:|---:|---:|---:|---|
| amd64 | 81 | 1 | 33 | 0 | Complete |
| arm64 | 81 | 1 | 33 | 0 | Complete |

The previous run recorded 78 HIGH and 1 CRITICAL, 32 distinct CVEs per architecture. The current run therefore has **three additional HIGH occurrences and one additional distinct CVE**. Refer to `TRIVY_RC22_EVIDENCE.csv` for package-level details.

## Recommendation without functional regression

- **Preserve LibreOffice document conversion and all existing CIR functions.** Native XML/document libraries are in its dependency chain. Removing packages to reduce scanner counts is not a safe remediation without a demonstrated functional equivalent.
- **CRITICAL CVE-2026-6653 in libxml2:** hold production approval pending input-path assessment and mitigation evidence for user-supplied XML and office documents. The scanner describes a crafted-XML use-after-free denial of service. Consider isolation, file-size/complexity bounds, conversion resource limits, and sandbox controls, but do not assert these controls exist without testing.
- **Document parsing HIGH:** assess reachable ingestion/conversion paths and whether malicious documents can reach vulnerable libraries. Require functional regression tests before package substitutions.
- **TLS/crypto HIGH:** assess actual runtime network use, library linkage, affected protocol paths and upstream advisories. No blanket acceptance.
- **System utility HIGH:** potential time-limited acceptance only with proof of non-root runtime, no privileged operations, restricted capabilities, no-new-privileges, read-only filesystem and lack of reachable attack paths. These controls must be validated on the deployed configuration.
- **Debian repository availability:** for the priority packages, installed and candidate versions match in the captured APT output. No `FixedVersion` is reported by Trivy. Neither fact proves the absence of upstream fixes or mitigations.

## Required approval before production

For each proposed residual exception record CVE, affected package/version, amd64/arm64, affected functionality, attack preconditions, validated controls, residual impact, accountable owner, review date and short expiry. An authorized reviewer must explicitly approve. Do not renew the old acceptance dated 2026-10-20 by changing dates or weakening Trivy gates. Continue to scan both architectures and the exact OCI candidate digest. Any new CVE or fixed version requires renewed review.

## Decision

**NO-GO for production at this stage.** This source-only change improves evidence; it does not repair packages or grant risk acceptance. Full CI and image security gates are still required.
