# Release Candidate Round 18

Release: `0.9.0-1`  
Build: `20260902`
Baseline: `0.8.0` (build `20260718`)

## Release lineage

This Release Candidate is the cumulative result of Rounds 1-18 applied to the 0.8.0 baseline. All round changes belong to functional release `0.9.0-1`; round numbers identify internal audit/development milestones and are not intermediate application releases. See `RELEASE_NOTES_0.9.0-1.md` / `RELEASE_NOTES_0.9.0-1_en.md`.

## RC status — promoted

This document preserves the Release Candidate criteria and audit trail. The candidate was formally promoted to **production release 0.9.0-1 on 2026-09-03** after completion of the external gates. The authoritative production record is `PRODUCTION_RELEASE_0.9.0-1.md`.

## Offline release gates

- Full standard pytest regression must pass; only the explicitly opt-in real-PostgreSQL tests may be skipped when no PostgreSQL test URL is configured.
- `python -m compileall` must pass.
- `pip check` must pass in the isolated wheel environment.
- Shell scripts must parse with their declared interpreter.
- Docker/Kubernetes release metadata must match `VERSION` and `BUILD`.
- Active production/Kubernetes manifests must not use `:latest` for the CIR application release.
- Production Compose must retain read-only root filesystem, no-new-privileges, CSRF enabled, Secure cookies/HSTS, and fail-closed root fallback.
- Kubernetes must retain non-root execution, RuntimeDefault seccomp, read-only root filesystem, dropped capabilities and disabled automatic service-account tokens.
- `k8s/secrets.example.yaml` must remain an example only and must not be included in active Kustomize resources.
- Release packaging must exclude `.env`, private keys/certificates, runtime databases/uploads/backups and Python caches.
- `SBOM_ROUND18.cdx.json` must be valid CycloneDX 1.6 and match the application release version.
- `scripts/verify_release_candidate.py` must pass.
- The final release ZIP must have a SHA-256 sidecar checksum.

## External gates required before production (completed on 2026-09-03)

1. **Live SCA:** run `scripts/run_sca.sh` in a network-enabled release job with `pip-audit` installed. Resolve or formally accept any relevant high/critical vulnerability before promotion.
2. **Real PostgreSQL:** run all seven `pytest -m postgres` integration tests against the supported PostgreSQL 18.6 test container/database (`scripts/run_postgres_tests.sh`).
3. **Final image scan:** scan the exact production container image, including OS/LibreOffice/PostgreSQL-client packages, with the organization-approved scanner (for example Trivy or Grype).
4. **Immutable image promotion:** record the registry digest and deploy with `image@sha256:<digest>`. For Compose, set `CIR_PRODUCTION_IMAGE` to that digest. For Kubernetes, promote an environment overlay that resolves to the same digest.

All four gates above were subsequently completed for the final `0.9.0-1` image. The immutable OCI index digest is `sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`; see `PRODUCTION_RELEASE_0.9.0-1.md` for the final evidence summary.

## Round 18 verification result

Offline RC verification completed on 2026-09-02: **292 passed, 7 skipped, 0 failed**. SBOM generation, `pip check`, compilation, shell syntax and YAML parsing all passed. The seven skipped tests are exactly the opt-in real-PostgreSQL tests; Docker is unavailable in the analysis environment, so the external gates above remain pending rather than being reported as successful.

## RC R8 — final container security disposition

After R7, application/Python vulnerability findings are required to be zero. Residual Debian HIGH/CRITICAL findings are governed by `TRIVY_RISK_ACCEPTANCE_R8.json` and `SECURITY_DISPOSITION_R8.md`; this is a time-bounded exact allowlist, not a generic `--ignore-unfixed` policy.

Before production promotion, run the final multi-architecture image through:

```bash
./scripts/run_trivy_production_gate.sh IMAGE
```

The gate scans both amd64 and arm64 and fails on any Python HIGH/CRITICAL, new/unreviewed OS HIGH/CRITICAL, newly patchable accepted CVE, or expired acceptance. The exact image that passes must then be pinned by registry SHA-256 digest.
