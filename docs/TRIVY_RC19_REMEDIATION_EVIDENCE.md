# RC19 — remediation evidence and decision boundary

This is a **diagnostic-only** release candidate. It preserves CIR functionality, Dockerfile, LibreOffice, and the production Trivy gate. The risk acceptance expired on 2026-10-20 and remains unchanged.

## Evidence from the uploaded security-only run 45176994864

| Architecture | HIGH occurrences | CRITICAL occurrences | Distinct CVEs | Trivy FixedVersion entries |
| --- | ---: | ---: | ---: | ---: |
| amd64 | 78 | 1 | 32 | 0 |
| arm64 | 78 | 1 | 32 | 0 |

All package/CVE/version/severity tuples match between the two scans. The one CRITICAL finding concerns `libxml2` (CVE-2026-6653). No reported FixedVersion is **not** proof of the absence of Debian updates.

## What the next [ci-security] run collects

The security-only workflow now collects, **inside the ephemeral local image** on each architecture:

- A fresh Debian `apt-get update` status and repository package candidates.
- Installed Debian package versions (`dpkg-query`).
- `apt-cache policy` and installed reverse dependencies for priority packages.
- The original Trivy JSON and a machine-readable summary.

These files are diagnostic artifacts only: they cannot modify the production candidate, do not waive the gate, and are not used to claim a CVE has been remediated. If the package repository cannot be reached, the diagnostic step reports a failure rather than claiming no fixes exist.

## Decision process

1. Compare installed and candidate package versions on both architectures; check Debian security advisories and whether a CVE is actually fixed.
2. Patch and rescan the exact rebuilt image for all fixable vulnerabilities.
3. Preserve LibreOffice conversion and run functional document tests before removing any transitive package.
4. For remaining CVEs, prepare individual scoped decisions with exposure analysis, mitigation evidence, owner, approval and expiry. Do not approve the CRITICAL XML processing issue without a concrete input-path assessment.
5. Require both Trivy gates to pass and an authorized, unexpired risk disposition before production promotion.

**No acceptance is granted by this document.**
