# Cybersecurity Incident Registry 0.9.0-1 — Production Release

Release: `0.9.0-1`  
Build: `20260902`  
Baseline: `0.8.0` (build `20260718`)  
Promotion date: `2026-09-03`

## Production image

- Tag: `desalvo/cybersecurity-incident-registry:0.9.0-1`
- OCI index digest: `sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`
- Immutable reference: `desalvo/cybersecurity-incident-registry@sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`
- Platforms validated: `linux/amd64`, `linux/arm64`

The additional `unknown/unknown` manifests shown by Docker Buildx are attestation manifests associated with the two platform images; they are not extra runnable application platforms.

## Final validation gates

All release gates required by the Release Candidate process have been completed:

- Standard pytest suite: **295 passed, 7 skipped, 0 failed**.
- Real PostgreSQL suite: **7 passed, 295 deselected**.
- `python -m pip check`: **PASS — No broken requirements found**.
- Release consistency gate: **PASS**, version `0.9.0-1`, build `20260902`.
- Live SCA / `pip-audit`: **PASS — No known vulnerabilities found**.
- Trivy production gate on `linux/amd64`: **PASS**.
- Trivy production gate on `linux/arm64`: **PASS**.
- Residual OS risk acceptance: **30 reviewed CVEs**, governed by `TRIVY_RISK_ACCEPTANCE_R8.json`, valid until **2026-10-03**.
- Immutable registry digest recorded: **PASS**.

## Deployment requirement

Production deployments should use the immutable image reference:

```text
desalvo/cybersecurity-incident-registry@sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b
```

`k8s/kustomization.yaml` is pinned to this digest. Docker Compose production should set `CIR_PRODUCTION_IMAGE` to the same immutable reference.

## Residual-risk follow-up

The R8 acceptance is time-bounded. Before or on **2026-10-03**, rerun the production Trivy gate. The gate is designed to fail if an accepted CVE becomes patchable, a new HIGH/CRITICAL finding appears, a Python HIGH/CRITICAL appears, or the acceptance expires.

## Release lineage

Version `0.8.0` is the functional baseline. All changes introduced in development/audit Rounds 1–18 and RC hardening R4–R8 belong to the single functional release `0.9.0-1`; those round/RC labels are internal development milestones, not intermediate functional releases.
