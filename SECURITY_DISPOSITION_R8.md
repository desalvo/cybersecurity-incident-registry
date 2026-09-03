# RC R8 — Final Security Disposition

## Scope

This document records the production disposition of the residual HIGH/CRITICAL operating-system findings observed after RC R7 container minimization. It does **not** waive Python/application vulnerabilities and it is not a blanket `--ignore-unfixed` rule.

The reviewed R7 image scan reported 43 Debian findings (38 HIGH, 5 CRITICAL) and no remaining Python vulnerability table. The apparent count is larger than the number of unique CVEs because the same vulnerability can be reported against multiple binary packages.

## Release policy

Production promotion is permitted only when all of the following are true:

1. `pip-audit` reports no known application dependency vulnerabilities.
2. Real PostgreSQL tests pass.
3. The standard pytest suite passes.
4. Both `linux/amd64` and `linux/arm64` image manifests pass `scripts/run_trivy_production_gate.sh`.
5. **No HIGH/CRITICAL Python finding is allowed.**
6. **No new/unreviewed HIGH/CRITICAL OS CVE is allowed.**
7. If Trivy starts reporting a `FixedVersion` for an accepted residual CVE, the gate fails and the image must be rebuilt/updated rather than continuing to accept it.
8. The temporary acceptance expires on **2026-10-03** and must then be renewed from a fresh scan and upstream review.
9. The final deployed image must be pinned by immutable registry SHA-256 digest.

The machine-readable policy is `TRIVY_RISK_ACCEPTANCE_R8.json`.

## Rationale categories

The allowlist contains only CVEs present in the reviewed R7 scan. Each has an explicit rationale. The residuals fall into these categories:

- Debian/Python base-runtime components for which the reviewed image had no fixed package version available.
- Headless LibreOffice transitive libraries (GLib, libxml2, libtiff and related libraries) retained because document conversion is a CIR feature.
- CLI/library paths CIR does not invoke directly, such as libcurl SFTP/SCP, `tiffcrop`, Perl Archive::Tar and Perl IO::Compress.
- SQLite findings accepted **only under the documented production condition that PostgreSQL is used**.

This is defense-in-depth risk acceptance, not a claim that the CVEs do not exist. Existing mitigations include non-root runtime, `no-new-privileges`, dropped Linux capabilities, read-only root filesystem, upload/path validation, bounded uploads, PostgreSQL production deployment and immutable-image pinning.

## Gate usage

After publishing the final candidate image:

```bash
./scripts/run_trivy_production_gate.sh \
  desalvo/cybersecurity-incident-registry:0.9.0-1
```

By default the script scans both `linux/amd64` and `linux/arm64`, writes raw Trivy JSON under `generated/trivy-r8/`, and evaluates each report against the policy.

The gate fails if:

- a Python HIGH/CRITICAL appears;
- a new HIGH/CRITICAL OS CVE appears;
- an accepted CVE gains a fixed version;
- the risk acceptance has expired.

## Release decision

RC R8 is eligible for production promotion only after the R8 gate has been executed against the exact multi-architecture image intended for release and the resulting manifest has been pinned by digest. The policy does not convert an unscanned image into a production-approved image.
