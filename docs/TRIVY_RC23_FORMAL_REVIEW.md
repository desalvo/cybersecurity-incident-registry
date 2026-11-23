# CIR 0.10.0-1 — Trivy applicability and residual-risk decision dossier (RC23)

**Status: review proposal only — no production approval, no automatic exception.**

## Evidence and limits

- Exact inputs: CI run `45200319586`, Trivy JSON for amd64 and arm64, and the repository's expired `TRIVY_RISK_ACCEPTANCE_R8.json`.
- The attached CSV enumerates every reported HIGH/CRITICAL package/CVE/version tuple and records both architectures, historical review coverage, Trivy status, and a proposed investigation class.
- Package detection **does not prove reachability or exploitability**. Conversely, a Debian `no-dsa` designation, a missing Trivy `FixedVersion`, or absence of direct Python imports **does not prove non-applicability**.
- Debian tracker links are provided as verification entry points, **not as evidence that each tracker entry was inspected in this iteration**. The status of Debian source-package backports and vulnerable code paths remains to be checked with authoritative tracker/changelog evidence.

## Current quantitative evidence

- amd64: **81 HIGH, 1 CRITICAL**; arm64: **81 HIGH, 1 CRITICAL**.
- **33 distinct CVEs**; **23** have a historical entry in the old acceptance; **10** are not covered by it.
- Historical risk acceptance expired **2026-10-20** and is not renewed here.

## Prioritization

1. **CRITICAL `libxml2` (CVE-2026-6653):** inspect Debian security tracker, package changelog and actual parser paths in LibreOffice/document conversion. Validate document import, upload controls, process sandboxing and malicious-document handling. No automatic acceptance.
2. **Document/data parsers** (libxml2, Expat, Raptor, TIFF, SQLite, GLib): verify vulnerable API reachability through uploaded or generated documents and external integrations. PostgreSQL production does not by itself establish SQLite non-reachability.
3. **Cryptography and networking** (OpenSSL, libcurl): check native call paths, protocol exposure and TLS usage; do not infer safety from Python `requests` alone.
4. **System/privilege and GnuPG utilities:** consider short-lived acceptance only after confirming no exposed invocation path, non-root/no-new-privileges, read-only rootfs, dropped capabilities, restricted filesystem and network access, and matching package/version scope.

## Decision and approval workflow

For **each CVE and affected Debian binary package/version**, the reviewer must record: official Debian applicability and fixed-version evidence, actual vulnerable function/path, CIR entry points, threat model, compensating controls verified in the deployed image, residual severity, accountable owner, review date, expiration, and explicit approval or rejection. Avoid blanket acceptance by group. For CRITICAL document parsers, require additional review and targeted tests.

Any approved acceptance must be a **new, explicitly reviewed, time-bounded** policy update. Never extend the old date or silently insert exceptions. Gate must still reject unexpected packages, newly available fixes, Python HIGH/CRITICAL and expired entries. Rebuild and scan both architectures on the exact immutable OCI candidate digest; preserve conversion functionality and run document regression tests.

## Next CI evidence required

- Debian Security Tracker and package changelog references, per CVE; no network retrieval is asserted here.
- Build identity, SBOM, package inventory, and full Trivy JSON for both architectures.
- Container hardening verification and end-to-end DOCX/PDF conversion tests using representative untrusted inputs.
- A signed/recorded decision from the authorized risk owner before any production gate exception is activated.

The previous README restructuring and permanent `[ci-security]` workflows are preserved unchanged.
