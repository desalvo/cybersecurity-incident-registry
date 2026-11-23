# CIR 0.10.0-1 RC25 — Trivy upgrade and residual risk review

## Source evidence

- CI run `45221043225`, two uploaded diagnostic artifacts, Trivy **v0.74.0**.
- Each platform: **81 HIGH**, **1 CRITICAL**, **33 distinct CVEs**, **0 `FixedVersion` populated**.
- The package/CVE/version/severity tuples match on amd64 and arm64.
- `debian-installed.tsv`, `debian-policy.txt`, `debian-priority-packages.txt` and APT update logs were present for both platforms.
- The **scanner is now pinned to v0.76.2** in all three workflows. This change has not yet been validated by a new CI run.

## Assessment method

The attached CSV is a **review queue**, not a list of approved exceptions. Every row remains `REVIEW_REQUIRED` even if it appears in the expired historical acceptance. Scanner detection is not proof of exploitability, and absence of `FixedVersion` is not proof that no Debian fix exists. Validate Debian tracker applicability, patched source versions, package usage and reachable code paths for each CVE.

1. **Document and XML libraries** (`libxml2`, Expat, TIFF, Raptor, SQLite): treat as potentially reachable through document processing. Preserve LibreOffice DOCX/PDF conversion. Prioritize the CRITICAL `libxml2` finding for a package-specific review and safe input handling tests.
2. **TLS and networking** (OpenSSL, libcurl): distinguish Python requests usage from transitive native TLS consumers; inspect actual loaded libraries and outbound integration paths before deciding exposure.
3. **OS utilities**: review user privileges, available binaries, Linux capabilities, entrypoints, and reachable operations. Non-root execution reduces risk but does not prove non-applicability.
4. **Risk acceptance**: only an authorized reviewer can approve scoped exceptions, with owner, evidence, package/version, CVE, mitigation, expiry and reevaluation triggers. No blanket acceptance or silent extension.
5. **CI**: run `[ci-security]` to regenerate amd64/arm64 findings with Trivy v0.76.2, then compare the new results and the Debian candidate inventory. Production promotion remains blocked until approved gates pass.

The old `TRIVY_RISK_ACCEPTANCE_R8.json` remains **unchanged and expired**. This RC does not alter CIR runtime dependencies, remove LibreOffice or publish a production image.
