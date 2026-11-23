# CIR 0.10.0-1 RC18 — evidence-based remediation decision (NOT APPROVED)

This is a **review aid**, not a risk acceptance or a production approval. The latest supplied security-only CI scans of both architectures report 79 HIGH/CRITICAL package/CVE occurrences each (78 HIGH and 1 CRITICAL), with 32 distinct CVE identifiers. The old policy expired on 2026-10-20.

## Preserve functionality

Keep LibreOffice and its DOCX-to-PDF conversion, all incident workflows, uploads, exports, authentication, and integrations. Removing a package merely to suppress Trivy is not a safe remediation. No application feature or runtime dependency has been removed in this candidate.

## Risk decision by attack surface

- **Document/data parsing:** `libxml2` (including CRITICAL CVE-2026-6653), `libexpat1`, `libraptor2-0`, `libtiff6`, `libsqlite3-0` and related X libraries. **Remediation first.** These can be reached indirectly via document conversion and other parsers. Do not accept solely because Flask does not import them.
- **Network/cryptography:** OpenSSL and libcurl packages. **Review protocol reachability and patch status** before any acceptance. Python `requests` not using libcurl does not prove LibreOffice or other native dependencies do not use it.
- **System utilities and GnuPG:** candidates for *scoped, time-limited* acceptance only after verifying that the vulnerable operation cannot be invoked by untrusted CIR inputs, container hardening is active and no vendor fix is available.
- **Other runtime libraries:** case-by-case analysis required.

## Evidence and next gate

`TRIVY_RC18_EVIDENCE_MATRIX.csv` lists every finding, exact installed version, architecture, status and proposed investigation. The generator `scripts/trivy_exposure_review.py` rejects malformed Trivy inputs and mismatched severity/fixed-version across architectures. Every row intentionally has `decision=REMEDIATE_OR_REVIEW`, `exposure=unverified` and no approval owner/date. The source report did not identify a `FixedVersion`; **check Debian security tracker and updated packages** independently before claiming unfixable status.

The CI diagnostic should rebuild the same features with a refreshed approved base image and rescan both architectures. If findings persist, assess runtime invocation with actual package dependency information (`apt-cache rdepends`, `ldd`, `dpkg -S`, process execution tracing) and test real DOCX-to-PDF conversion with representative safe fixtures. No evidence here establishes exploitability or non-exploitability.

**Do not update** `TRIVY_RISK_ACCEPTANCE_R8.json`, relax `scripts/evaluate_trivy_gate.py`, or promote a production image without authorized review. The previous acceptance remains expired. This candidate has not run Docker/Trivy anew.
