# Security Audit Round 17

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: software supply chain/SBOM, current runtime security releases, container and Kubernetes least privilege, production secret injection, and reverse-proxy trust boundaries.

## Confirmed findings and remediation

### HIGH - PostgreSQL 18.4 was superseded by the August 2026 security release

The runtime/test manifests still referenced PostgreSQL 18.4. PostgreSQL 18.6 was released on 2026-08-13 and fixes multiple security issues affecting earlier 18.x releases, including arbitrary-code-execution class defects. Runtime, integration-test, and Kubernetes manifests now use PostgreSQL 18.6.

### HIGH - Login IP rate limiting trusted X-Forwarded-For from untrusted clients

The login rate-limit identity previously preferred the first `X-Forwarded-For` value regardless of the peer that supplied it. A direct client could therefore rotate a forged header and defeat the per-IP lockout boundary. CIR now ignores forwarding headers unless `request.remote_addr` belongs to an explicitly configured `CIR_TRUSTED_PROXY_CIDRS` network. For trusted proxies the chain is evaluated from the application side toward the client and the first untrusted hop is selected.

### MEDIUM - Container permission fallback was root-by-default

The Docker entrypoint could continue as root after a persistent-volume ownership failure unless the operator disabled the fallback. The default is now fail-closed (`CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE=0`); retaining root after a volume-permission failure requires an explicit opt-in. The entrypoint also applies `umask 027`.

### MEDIUM - Production container/orchestrator manifests lacked several least-privilege controls

A production Compose override now requires an explicit production image reference, sets the web root filesystem read-only, uses a bounded `/tmp` tmpfs, enables `no-new-privileges`, drops all capabilities and adds only the startup capabilities required by the current entrypoint, forces production/CSRF/Secure-cookie/HSTS settings, and disables root fallback. Kubernetes now disables automatic service-account token mounting, uses RuntimeDefault seccomp, drops application capabilities, uses a read-only application root filesystem, provides a bounded writable `/tmp`, and adds health probes. The active application image is version-pinned rather than `latest`.

### MEDIUM - Kubernetes example embedded a deployable placeholder database Secret

The PostgreSQL manifest no longer embeds a Secret with a placeholder password. It requires an externally provisioned `cir-postgres-secret`. `k8s/secrets.example.yaml` is intentionally excluded from Kustomize and exists only as an operator template. The application deployment now also supplies the required `SETTING_ENCRYPTION_KEY` secret in production.

### MEDIUM - Core secrets were inline-environment only

`DATABASE_URL`, `SECRET_KEY`, `ADMIN_INITIAL_PASSWORD`, and `SETTING_ENCRYPTION_KEY` can now be read from `NAME_FILE` paths for Docker/Kubernetes secret-volume style injection. Supplying both the inline variable and its `_FILE` counterpart fails closed; unreadable, oversized, non-UTF-8, or NUL-containing secret files are rejected.

## Supply-chain inventory

`SBOM_ROUND17.cdx.json` is generated from the isolated offline environment and contains 47 reachable Python components. It records the direct/transitive classification, dependency graph, package URL, and SHA-256 plus wheel filename when a matching supplied wheel is available. `scripts/generate_sbom.py` performs the inventory without contacting a package index.

`scripts/run_sca.sh` is a release/CI gate for `pip-audit` and writes `SCA_PIP_AUDIT.json`. This analysis container cannot reach PyPI/OSV and does not contain the `pip-audit` tooling wheel, so a live transitive vulnerability-service query could not be executed here. The script fails clearly rather than silently treating the missing audit engine as success.

Direct dependency freshness was reviewed separately. Security-patched pins already used by CIR were retained where a newer release was not established as a necessary security update, avoiding an unnecessary compatibility change in this hardening round.

## Runtime security updates

- Python base image: `python:3.12-slim-trixie` -> `python:3.12.14-slim-trixie` to pin the August 2026 Python 3.12 security release instead of a floating patch tag.
- PostgreSQL: `18.4` -> `18.6` in Docker Compose, PostgreSQL integration tests, and Kubernetes.

## Verification

- Offline SBOM generation: PASS, 47 Python components.
- `pip check` in the isolated wheel environment: PASS.
- Round 17 targeted/container/previous-round tests: PASS.
- Full standard pytest suite: 286 passed, 7 skipped; all skips are the opt-in real-PostgreSQL tests when no test server is configured.
- `python -m compileall` / Python compilation checks: PASS.
- Shell syntax checks for entrypoint/SCA/PostgreSQL test scripts: PASS.

## Residual / release-candidate priorities

1. Run `scripts/run_sca.sh` in a network-enabled CI/release job with `pip-audit` installed and gate release on unresolved high/critical findings.
2. Build the production image, record its immutable registry digest, and use that digest in production Compose/Kubernetes promotion instead of relying only on a version tag.
3. Execute the seven opt-in PostgreSQL integration tests against PostgreSQL 18.6 through Docker/CI.
4. Run an image/container scanner (for example Trivy/Grype or an equivalent organizational scanner) against the final image, including OS packages installed by LibreOffice and PostgreSQL client dependencies.
