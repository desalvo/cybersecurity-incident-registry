# Security, hardening and residual-risk policy

Production security controls, temporary Debian risk acceptance, and the fail-closed Trivy policy for 0.9.0-1. The Hotfix 7 acceptance expires on 2026-10-20 and must be re-reviewed earlier if Debian publishes a fixed Trixie version.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `SECURITY_DISPOSITION_R8.md`
- `SECURITY_DISPOSITION_HOTFIX7.md`

---

## Historical source: `SECURITY_DISPOSITION_R8.md`

## Scope

This document records the production disposition of residual HIGH/CRITICAL operating-system findings after container minimization and the additional Debian Trixie review performed on **2026-09-20**. It does **not** waive Python/application vulnerabilities and is not a blanket `--ignore-unfixed` rule.

The machine-readable policy is `TRIVY_RISK_ACCEPTANCE_R8.json`.

## Release policy

Production promotion is permitted only when all of the following are true:

1. `pip-audit` reports no known application dependency vulnerabilities.
2. Real PostgreSQL tests pass.
3. The standard pytest suite passes.
4. `scripts/verify_security_gate_context.py` confirms the required container/Kubernetes hardening.
5. Both `linux/amd64` and `linux/arm64` image manifests pass `scripts/run_trivy_production_gate.sh`.
6. **No HIGH/CRITICAL Python finding is allowed.**
7. **No new/unreviewed HIGH/CRITICAL OS CVE is allowed.**
8. If an accepted CVE declares a package scope, a finding in any other package is rejected.
9. If an accepted CVE declares an installed-version scope, any version outside that scope is rejected and requires a new review.
10. If Trivy reports a `FixedVersion` for an accepted residual CVE, the gate fails and the image must be rebuilt/updated rather than continuing to accept it.
11. The temporary acceptance expires on **2026-10-20** and must then be renewed from a fresh scan and upstream review.
12. The final deployed image must be pinned by immutable registry SHA-256 digest.

## Hotfix 7 - Debian Trixie review

On 2026-09-20 Debian still reports Trixie `util-linux` `2.41.5-0+deb13u1` as vulnerable/no-DSA for:

- `CVE-2026-76642`
- `CVE-2026-78408`
- `CVE-2026-78409`
- `CVE-2026-78410`

The acceptance is limited to the exact util-linux binary package set recorded in the JSON policy and to the reviewed `2.41.5-0+deb13u1` source-version family (including binNMU suffixes). These issues concern local mount/nsenter/privilege-oriented paths that CIR does not expose in its hardened production runtime.

`CVE-2026-16742` is also accepted temporarily only for `libsystemd0` and `libudev1`. Debian reports it as a Trixie no-DSA issue in `systemd-homed`; CIR does not run systemd or systemd-homed inside the application container.

This is a temporary risk acceptance, not a statement that the vulnerabilities are absent.

## Required runtime hardening

The Hotfix 7 disposition depends on the production profile retaining:

- application process non-root (UID 10001);
- `allowPrivilegeEscalation: false`;
- all Linux capabilities dropped for the web container;
- read-only root filesystem;
- seccomp `RuntimeDefault`.

The Docker entrypoint drops bootstrap root privileges to `appuser` by default, while the Kubernetes production manifest directly runs the web container as UID/GID 10001. The optional compatibility fallback that may run as root is **not** part of the accepted Kubernetes production profile.

## Gate usage

After publishing a candidate image:

```bash
./scripts/run_trivy_production_gate.sh \
  desalvo/cybersecurity-incident-registry:0.9.0-1
```

The script first validates the security-gate context, then scans both architectures and evaluates each Trivy JSON report against the policy.

The gate fails if a Python HIGH/CRITICAL appears, a new OS HIGH/CRITICAL appears, a package/version falls outside a scoped acceptance, an accepted CVE gains a fixed version, or the time-bounded acceptance expires.

## GitHub Actions integration

`.github/workflows/ci-release.yml` runs the application, PostgreSQL, SCA and release gates. For release events it builds a multi-architecture candidate under `ci-<sha>`, scans the exact OCI digest, and only after PASS promotes that same digest to `latest` for `main` or to the Git tag for a tag push. See `docs/TESTING_AND_PRODUCTION.md`.

---

## Historical source: `SECURITY_DISPOSITION_HOTFIX7.md`

Data revisione: 2026-09-20  
Release funzionale: 0.9.0-1

## Nuovi CVE temporaneamente accettati

La policy R8 viene estesa in modo puntuale a:

- CVE-2026-76642
- CVE-2026-78408
- CVE-2026-78409
- CVE-2026-78410
- CVE-2026-16742

L'accettazione non è un `ignore-unfixed` generale. I quattro CVE util-linux sono ammessi solo per i pacchetti Debian esplicitamente elencati nella policy; CVE-2026-16742 è ammesso solo per `libsystemd0` e `libudev1`. Qualunque `FixedVersion` riportata da Trivy rende nuovamente il finding bloccante.

La revisione scade il **2026-10-20**. Restano bloccanti tutti i nuovi HIGH/CRITICAL non riesaminati e tutti i finding Python HIGH/CRITICAL.

## Condizioni di hardening

La risk acceptance dipende dal runtime CIR production:

- processo non-root UID 10001;
- `allowPrivilegeEscalation: false`;
- tutte le Linux capabilities eliminate;
- root filesystem read-only;
- seccomp `RuntimeDefault`.

`scripts/verify_security_gate_context.py` controlla queste invarianti nel Dockerfile e nel manifest Kubernetes e viene eseguito anche dal gate Trivy.

## GitHub Actions

La Hotfix 7 aggiunge `.github/workflows/ci-release.yml`. Pull request e push eseguono suite completa, PostgreSQL reale, SCA, verifica RC e packaging. Su push a `main` viene promosso `latest`; su push di un tag Git viene promosso lo stesso tag Docker. La promozione avviene solo dopo il gate Trivy amd64/arm64 sull'esatto digest candidato.

Vedere `docs/TESTING_AND_PRODUCTION.md` per configurazione di secrets/variables e flusso completo.

## Upstream references reviewed

- Debian util-linux tracker: https://security-tracker.debian.org/tracker/source-package/util-linux
- CVE-2026-76642: https://security-tracker.debian.org/tracker/CVE-2026-76642
- Debian systemd tracker: https://security-tracker.debian.org/tracker/source-package/systemd

---


## Hotfix 7 follow-up: 2026-09-20 Trivy refresh

The production gate was intentionally re-evaluated against a freshly downloaded Trivy database before image promotion. The refreshed scan surfaced two categories of findings. First, historical CycloneDX files under `sbom/` were being copied into the runtime image after the documentation/SBOM reorganization; Trivy correctly warned that third-party SBOMs can produce inaccurate package detection and reported stale Python package versions from those historical files. The runtime image now excludes the entire `sbom/` directory. Python HIGH/CRITICAL findings remain unconditionally forbidden by the gate.

Second, the refreshed Debian Trixie scan surfaced residual OS findings for Expat (`CVE-2026-76956`, `CVE-2026-76957`) and libxml2 (`CVE-2026-74860`, `CVE-2026-86138`, `CVE-2026-86139`, `CVE-2026-86140`, `CVE-2026-86142`, `CVE-2026-86143`, `CVE-2026-86144`). At review time Trixie has no fixed package for these findings. They are accepted only temporarily, only for the exact binary package and reviewed Trixie version, and only through 2026-10-20. Any Trivy `FixedVersion`, package mismatch, version mismatch, expiry, Python HIGH/CRITICAL, or new HIGH/CRITICAL remains a hard failure.

The util-linux disposition was also tightened to account for Debian epochs and the special `login` binary version (`1:4.16.0-2+really2.41.5-0+deb13u1`) using package-specific version expressions, rather than broadening the global version rule.
