# Production security evidence — 0.10.0-1 RC14

The November 23, 2026 CI produced both architecture scans. **Production promotion was blocked** by the Trivy gate. The risk acceptance expired October 20, 2026 and has not been renewed.

| Architecture | HIGH package/CVE occurrences | CRITICAL occurrences | Distinct CVEs | FixedVersion populated |
| --- | ---: | ---: | ---: | ---: |
| linux/amd64 | 78 | 1 | 32 | 0 |
| linux/arm64 | 78 | 1 | 32 | 0 |

These counts describe package/CVE occurrences, not independent vulnerabilities. A missing Trivy FixedVersion does **not** prove that Debian has no available security update. The CRITICAL `libxml2` finding (CVE-2026-6653) and new HIGH findings require investigation.

## Required actions

1. Rebuild the candidate with current approved base-image and Debian security packages; scan the exact immutable candidate digest for amd64 and arm64.
2. Review installed packages and runtime necessity, including LibreOffice document conversion. Do not remove libraries without functional regression tests.
3. Remediate available fixes, rerun SCA, application tests, document conversion tests and both Trivy gates.
4. Document each remaining risk with affected package/version, exposure, mitigation, owner, review date and expiry; obtain explicit approval before changing the acceptance file.
5. Promote only after both gates pass and the digest is verified and recorded through the metadata PR.

No production promotion or risk approval is implied by this report.
