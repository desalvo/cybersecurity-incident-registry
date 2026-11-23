# CIR 0.10.0-1 RC17 — Security disposition proposal (NOT APPROVED)

**Decision:** preserve all CIR functionality; do not remove LibreOffice, alter runtime features, renew acceptance, or bypass Trivy. The production gate must remain FAIL until an authorized, current review and both architecture gates pass.

## Evidence and limitations

- Evidence: supplied CI Trivy JSON for `linux/amd64` and `linux/arm64`, generated 2026-11-23; same 79 HIGH/CRITICAL package occurrences on each architecture (78 HIGH, 1 CRITICAL).
- 32 distinct vulnerability IDs and 79 package/CVE/version entries. `FixedVersion` is empty in this snapshot; that is **not** proof that no patched Debian package exists now.
- Prior policy `TRIVY_RISK_ACCEPTANCE_R8.json` expired 2026-10-20. No dates, rules, allowlists or approval were modified.
- This is a triage hypothesis, **not** an exploitability assessment or acceptance decision. A package not called directly by Flask may be called by LibreOffice or another runtime component.

## Risk-oriented classification

### GnuPG transitive utilities — 7 package/CVE entries

LOWER if not invoked by application; package may still be used by supporting tools

Verify runtime invocation, package dependency and threat model before scoped acceptance

### OS administration utilities/libraries — 36 package/CVE entries

LOWER for privileged local operations in non-root container, but runtime library paths remain relevant

Verify non-root isolation, privileges and reachable utilities before scoped acceptance

### cryptography/network libraries — 7 package/CVE entries

MEDIUM/HIGH: TLS and outbound integrations may depend on these libraries indirectly

Review reachable protocols and library call paths; no automatic acceptance

### document/data parsing — 18 package/CVE entries

HIGH: potential untrusted document or metadata input; review parser entrypoints and file provenance

Remediate if fix available; consider acceptance only after input-path and isolation review

### other runtime dependency — 11 package/CVE entries

UNKNOWN: requires explicit exposure analysis

Verify necessity, input reachability and fixed-version availability

## Decision rules for authorized reviewers

1. **Patch first:** rebuild using a reviewed, current base digest and current Debian security repositories; scan the immutable candidate for both architectures. Check vendor security advisories, not just `FixedVersion`.
2. **Preserve behavior:** keep DOCX→PDF conversion and all integrations; changes to native packages require end-to-end document conversion, import/export, authentication and functional tests.
3. **Prioritize document parsers:** `libxml2` CRITICAL CVE-2026-6653 and Expat/Raptor/SQLite/TIFF findings should not be called low risk merely because they are transitive. Validate untrusted inputs and execution paths.
4. **Potentially acceptable residuals:** privileged OS utilities and GnuPG tools may be candidates for narrowly scoped temporary acceptance if proven unreachable from CIR inputs, without available fixes, with container hardening verified.
5. **Formal acceptance:** record each CVE and exact package/version, architecture, affected entrypoints, compensating controls, reviewer/owner, approval date and expiry. No blanket approval or automatic expiry extension.
6. **Production remains blocked** until all remaining findings are either remediated or approved under a current, explicitly reviewed policy and Trivy passes on both platforms.

## Evidence matrix

Full machine-readable matrix: [`TRIVY_RC17_REVIEW_MATRIX.csv`](TRIVY_RC17_REVIEW_MATRIX.csv).

| CVE | Severity | Packages in report | Prior policy entry |
|---|---|---|---|
| CVE-2025-69720 | HIGH | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | yes |
| CVE-2025-71436 | HIGH | libraptor2-0 | no |
| CVE-2026-113351 | HIGH | libexpat1 | no |
| CVE-2026-115506 | HIGH | libexpat1 | no |
| CVE-2026-117610 | HIGH | libexpat1 | no |
| CVE-2026-118370 | HIGH | libexpat1 | no |
| CVE-2026-119373 | HIGH | libsqlite3-0 | no |
| CVE-2026-119374 | HIGH | libsqlite3-0 | no |
| CVE-2026-119379 | HIGH | libsqlite3-0 | no |
| CVE-2026-12064 | HIGH | libcurl3t64-gnutls, libcurl4t64 | yes |
| CVE-2026-124709 | HIGH | libssl3t64, openssl, openssl-provider-legacy | no |
| CVE-2026-16742 | HIGH | libsystemd0, libudev1 | yes |
| CVE-2026-24882 | HIGH | dirmngr, gnupg, gnupg-l10n, gpg, gpg-agent, gpgconf, gpgsm | yes |
| CVE-2026-36849 | HIGH | libtiff6 | yes |
| CVE-2026-52490 | HIGH | libtiff6 | yes |
| CVE-2026-54369 | HIGH | libacl1 | yes |
| CVE-2026-6653 | CRITICAL | libxml2 | yes |
| CVE-2026-74860 | HIGH | libxml2 | yes |
| CVE-2026-76642 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | yes |
| CVE-2026-78408 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | yes |
| CVE-2026-78409 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | yes |
| CVE-2026-78410 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | yes |
| CVE-2026-8458 | HIGH | libcurl3t64-gnutls, libcurl4t64 | yes |
| CVE-2026-86138 | HIGH | libxml2 | yes |
| CVE-2026-86139 | HIGH | libxml2 | yes |
| CVE-2026-86140 | HIGH | libxml2 | yes |
| CVE-2026-86142 | HIGH | libxml2 | yes |
| CVE-2026-86143 | HIGH | libxml2 | yes |
| CVE-2026-86144 | HIGH | libxml2 | yes |
| CVE-2026-88806 | HIGH | libx11-6, libx11-data | yes |
| CVE-2026-88807 | HIGH | libxrender1 | yes |
| CVE-2026-9538 | HIGH | perl-base | yes |
