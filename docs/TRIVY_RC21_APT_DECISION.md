# CIR 0.10.0-1 RC21 — Debian security remediation decision record

**Status: technical evidence only. No risk acceptance approved; production gate remains blocking.**

Evidence: GitHub Actions security-only run `45186139811`, archived Trivy and APT inventory for linux/amd64 and linux/arm64. Each image has **78 HIGH and 1 CRITICAL package/CVE occurrences**, covering **32 distinct CVEs**; none of the Trivy findings contains a `FixedVersion` field. APT inventory is complete on both platforms.

## What the repository actually offers

For every priority package listed below, the installed version is the same as the candidate version in the configured Debian 13.8 trixie, trixie-updates and trixie-security repositories. The two architectures agree. This is evidence that an ordinary `apt-get upgrade` against *these repository snapshots* would not update those packages; it is **not** proof that the CVEs are fixed, non-exploitable, or will never receive fixes.

| Package | Installed = Candidate | Risk/usage concern |
| --- | --- | --- |
| `libxml2` | `2.12.7+dfsg+really2.9.14-2.1+deb13u3` | CRITICAL XML-processing finding; required by LibreOffice and document converters |
| `libexpat1` | `2.9.0-1~deb13u1` | XML parsing and font/document dependency chain |
| `libsqlite3-0` | `3.46.1-7+deb13u2` | Native database dependency; PostgreSQL use alone does not establish non-reachability |
| `libraptor2-0` | `2.0.16-6` | RDF parsing via LibreOffice native dependencies |
| `libtiff6` | `4.7.0-3+deb13u3` | Image/document decoding |
| `libssl3t64` | `3.5.9-1~deb13u1` | TLS/cryptographic libraries used by native components |
| `openssl` | `3.5.9-1~deb13u1` | TLS utility and certificate management |
| `libcurl4t64` | `8.14.1-2+deb13u7` | Native HTTP/TLS used by LibreOffice and other libraries |
| `util-linux` | `2.41.5-0+deb13u1` | System utilities and native libraries; assess privileged entrypoints |

## Required action before an acceptance decision

1. Preserve LibreOffice and all CIR features. Do **not** remove `libxml2`, `libraptor2-0`, `libtiff6`, or other packages just to lower Trivy counts.
2. Prioritize `CVE-2026-6653` in `libxml2`: review the actual affected function and Debian security tracker, document whether externally supplied DOCX/XML/PDF reaches the vulnerable parser, and assess containment of document conversion. An indirect dependency is **not** proof of low risk.
3. Check Debian security advisories and newly available base-image digests at the next diagnostic run. Rebuild and rescan both architectures before any decision. Candidate equality is only a snapshot.
4. For residual CVEs, create a signed-off record for each CVE/package/version scope, affected code path, reachable inputs, operational exposure, mitigations, owner, expiration, and triggers for re-review. Keep the historical acceptance unchanged.
5. Require a distinct, authorized risk owner to approve any residual acceptance. Reject newly fixable HIGH/CRITICAL findings, and retain the strict Python SCA gate. An acceptance cannot be inferred from a report or generated automatically.
6. After approved remediation/acceptance, run full CI, real PostgreSQL and document conversion tests, both Trivy architecture gates on the exact OCI candidate digest, and only then promote and record the immutable production digest.

## Decision

**Not approved for production.** No candidate package update is available in the supplied APT snapshot for the priority components. A targeted risk assessment may be justified for low-reachability system utilities; document-processing and crypto vulnerabilities need stronger evidence. Neither Trivy severity nor package presence alone determines actual exploitability. The old risk acceptance expired on 2026-10-20 and has not been renewed.
