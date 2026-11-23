# CIR 0.10.0-1 RC33 — 14-day conditional Debian 13 residual-risk decision

**Effective:** 2026-11-23 · **Expiry:** 2026-12-07 (14 days) · **Status:** conditionally approved for gate evaluation; production promotion remains subject to complete CI and immutable-digest verification.

## Authorization and evidence

The project owner instructed proceeding after the RC32 14-day approval proposal. The PR approval/merge record must remain the auditable authorization record. The technical scope comes from the two CI diagnostic scans `45227508842`, not from historical accepted CVEs.

The allowlist covers **33 distinct CVEs**, each constrained to exactly the affected Debian binary packages and installed versions observed on both `linux/amd64` and `linux/arm64`. No new packages, versions, CVEs, Python HIGH/CRITICAL findings or findings with a `FixedVersion` are allowed.

## Conditions

- Preserve LibreOffice and all application functions, including document conversion and XML-related integrations.
- Maintain non-root runtime, no-new-privileges, dropped capabilities, read-only root filesystem, PostgreSQL and normal authorization and input-validation controls.
- Run complete CI, real PostgreSQL tests, documentation tests and multiarch Trivy scans on the **actual candidate digest** before promotion.
- Review residual risk weekly, on each new CVE or fixed version, and at expiry. A failed or expired policy blocks promotion; never extend automatically.
- The CRITICAL `CVE-2026-6653` in `libxml2` is included as a *time-limited conditional residual risk*, **not** declared unexploitable; its document/XML input exposure must be monitored and mitigations retained.
- Do not promote a different OCI digest or deploy from mutable tags.

## Security gate outcome

The policy has been tested against the supplied historical Trivy JSON reports on both architectures. This does not prove a new CI run or production approval; GitHub Actions must re-evaluate the candidate.
