# Release Notes - Cybersecurity Incident Registry 0.9.0-1

**Release:** 0.9.0-1  
**Build:** 20260902  
**Starting baseline:** 0.8.0 (build 20260718)

## Release lineage

Version 0.9.0-1 is the functional release following baseline 0.8.0. Every change introduced throughout Rounds 1-18 belongs cumulatively to 0.9.0-1. The rounds are internal development, audit, hardening and verification milestones and **are not** intermediate 0.8.x functional releases.

Historical working-artifact names containing strings such as `0.8.0-1`, `0.8.0-2-hardened-roundX` or similar identify intermediate audit packages only and do not define the official release lineage.

## Main changes from 0.8.0

### Application security and authentication

- Strengthened CSRF, cookies, HTTP security headers, session lifecycle and production policy.
- Hardened login rate limiting and prevented `X-Forwarded-For` spoofing unless the connection comes through explicitly trusted proxies.
- Strengthened local-password, bootstrap-credential and secret configuration handling.
- Stored SMTP, LDAP and SSO credentials are no longer reflected in administrative HTML.

### Multi-tenant isolation

- Corrected administrative queries and operations that were not sufficiently tenant-scoped.
- Notification templates/types, AI knowledge/database context, schedulers, backups, audit logs, recipients and several CRUD paths now consistently honor the active/owning tenant.
- Hardened tenant import and identifier remapping to prevent collisions and cross-tenant contamination.

### Filesystem, uploads and documents

- Centralized validation of filesystem paths derived from persistent metadata.
- Documents, attachments, logos and AI files are confined to managed directories and reject traversal, absolute paths and non-canonical stored names.
- Strengthened upload validation, file permissions, archive handling and cleanup.

### Outbound HTTP and plugins

- Strengthened SSRF protection and HTTP/HTTPS destination validation for AI engines and Alfresco.
- Disabled implicit redirects where they could weaken destination validation.
- Reduced raw exception disclosure in administrative workflows.

### Backup, import and crash recovery

- Full Import coordinates database transactions with staged filesystem activation.
- Backup/import maintenance is serialized with appropriate PostgreSQL advisory locks.
- Restore can atomically recover managed volumes and realign sequences/relations.
- Added a durable restore journal and DB commit token to distinguish committed from uncommitted restores after crashes.
- End-to-end tests actually terminate a worker with `SIGKILL` before and after commit and verify restart recovery.

### PostgreSQL and concurrency

- Added opt-in real PostgreSQL tests through Docker Compose for advisory locks, rollback, sequences and crash recovery.
- Separated maintenance lock namespaces and shared/exclusive modes to avoid collisions and prevent backups from overlapping destructive restores.

### Supply chain and production deployment

- Reference PostgreSQL updated to 18.6 and reference Python runtime to 3.12.14.
- Added `docker-compose.production.yml` with read-only root filesystem, `no-new-privileges`, reduced capabilities and fail-closed production policy.
- Kubernetes uses `RuntimeDefault` seccomp, dropped capabilities, read-only application root filesystem, disabled automatic service-account tokens and external Secrets.
- Added a transitive CycloneDX 1.6 SBOM with SHA-256 hashes of supplied wheels.
- Added SCA gates, Release Candidate verification and SHA-256 release-package checksums.

## Production validation

Release Candidate R8 was promoted to production on 3 September 2026 after all mandatory gates completed successfully:

- standard suite: **295 passed, 7 skipped, 0 failed**;
- real PostgreSQL suite: **7 passed, 295 deselected**;
- `pip check`: **PASS**;
- live SCA / `pip-audit`: **No known vulnerabilities found**;
- R8 Trivy production gate: **PASS on linux/amd64 and linux/arm64**;
- immutable OCI digest recorded: `sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`.

The production image tag is `desalvo/cybersecurity-incident-registry:0.9.0-1`. Production deployments should prefer `desalvo/cybersecurity-incident-registry@sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`. The 30 residual OS CVEs are governed by the time-bounded R8 risk policy through **3 October 2026** and must be re-reviewed by that date.

## Technical round documentation

`SECURITY_AUDIT_ROUND2.md` ... `SECURITY_AUDIT_ROUND18.md` retain the technical history of each audit phase. They must be read as the internal history of building **0.9.0-1 from the 0.8.0 baseline**, not as a list of separate releases.

### Multi-architecture Docker image

The release includes `scripts/build_multiarch_image.sh`, which builds and publishes `desalvo/cybersecurity-incident-registry:latest` by default as a Docker Buildx multi-architecture manifest for `linux/amd64` and `linux/arm64`. Repository and tag can be configured independently through `--repository`/`--tag` or `CIR_DOCKER_REPOSITORY`/`CIR_DOCKER_TAG`; `--image`/`CIR_DOCKER_IMAGE` remains available for a complete image reference. Authenticate to the registry with `docker login` before running it.

Operational migration from the 0.8.0 baseline is documented in `MIGRATION_0.8.0_TO_0.9.0_en.md`, including required changes to Docker Compose, production Compose, Kubernetes/Kustomize, Secrets, PVCs, and security variables.
## RC R4 security update

The live SCA gate executed against RC R3 found known vulnerabilities in the pinned `pypdf==6.10.2` and `cryptography==46.0.7`. RC R4 changes only these dependencies to `pypdf==6.16.2` and `cryptography==50.0.1`. No functional or database-schema change is introduced. Because dependency binaries change, all production gates must be rerun against R4 before promotion.

## RC R5 test stabilization

Final validation stabilized the external post-commit SIGKILL test: the SQLite worker checkpoint timeout is increased from 15 to 30 seconds and can be configured with `CIR_CRASH_TEST_CHECKPOINT_TIMEOUT`. This change affects only the test harness and does not change CIR runtime behavior.


### RC R6 - container image hardening

RC R6 does not change application behaviour. The runtime image excludes historical SBOM/audit artifacts (which caused false positives in container scanners), uses `libreoffice-writer-nogui` instead of GUI LibreOffice packages, removes `curl` from the healthcheck by using Python's standard library, and applies available Debian updates during the build. Trivy must be rerun against the published image after rebuilding.

### RC R7 - final container minimization

- Dockerfile converted to a multi-stage build with an isolated application virtualenv.
- `pip`, `setuptools`, and `wheel` are removed from runtime after dependency installation.
- The pip-embedded SBOM that Trivy could interpret as installed Python packages (`msgpack`/`setuptools`) is no longer present at runtime.
- No Debian finding is hidden: the complete OS scan remains an explicit production gate.

### RC R8 - final container finding disposition

RC R8 adds a machine-readable residual-risk policy and a fail-closed Trivy gate for the Debian findings remaining after R7. It does not generically ignore `unfixed` vulnerabilities: only specifically reviewed CVEs with no `FixedVersion` are temporarily accepted, through 3 October 2026. Any new HIGH/CRITICAL, any Python HIGH/CRITICAL, or any accepted CVE that becomes patchable blocks release. The gate scans `linux/amd64` and `linux/arm64` separately.
