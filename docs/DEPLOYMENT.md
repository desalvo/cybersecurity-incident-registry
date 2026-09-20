# Deployment

This document is the consolidated deployment reference for Cybersecurity Incident Registry 0.9.0-1.

## Production invariants

- Production database: PostgreSQL.
- Run the application container as non-root.
- `allowPrivilegeEscalation: false`.
- Drop all Linux capabilities.
- Use a read-only root filesystem.
- Use seccomp `RuntimeDefault`.
- Keep mutable CIR data under the dedicated persistent `/data` layout.
- Configure trusted proxies explicitly; do not trust forwarded headers from arbitrary clients.
- Inject secrets through the supported secret/file mechanisms rather than baking them into images or manifests.

## Docker and Docker Compose

Use `Dockerfile` for the runtime image, `docker-compose.yml` for the development/reference topology and `docker-compose.production.yml` for the hardened production topology. Production Compose requires an explicitly supplied `CIR_PRODUCTION_IMAGE`; do not silently fall back to `latest`.

The release build script is `scripts/build_multiarch_image.sh`. Production publication is handled by `.github/workflows/ci-release.yml`, which first publishes a temporary `ci-<sha>` candidate, scans the exact digest for both `linux/amd64` and `linux/arm64`, then promotes that approved digest to the final tag.

## Kubernetes

The `k8s/` directory contains the deployment, PostgreSQL example, shared PVC, Kustomize configuration, secret example and the storage-layout migration example. The application deployment must preserve the hardened security context verified by `scripts/verify_security_gate_context.py`.

The 0.9.0-1 reference layout uses the shared `cir-data` PVC mounted at `/data`; the old split uploads/backups PVC layout is obsolete. `k8s/migrate-separated-pvcs-to-cir-data.example.yaml` documents the migration pattern.

## Upgrade from 0.8.0

Follow [MIGRATION.md](MIGRATION.md) before changing the running deployment. Back up database and filesystem data, validate configuration/secret changes, migrate persistent storage deliberately, and retain a rollback path. PostgreSQL major-version upgrades require a database migration procedure; do not treat a major image-tag change as an in-place data-format upgrade.

## Secrets and trusted proxies

Core settings support the documented `_FILE` form for container secrets. Never set both a direct value and its `_FILE` counterpart. Configure `CIR_TRUSTED_PROXY_CIDRS` only with actual reverse-proxy networks so client IP handling and login rate limiting cannot be bypassed by spoofed forwarded headers.

## Production image digest

Hotfix 7 passed the production gates and the promoted multi-architecture OCI index is pinned in `PRODUCTION_IMAGE_DIGEST` as:

```text
desalvo/cybersecurity-incident-registry@sha256:6f4f48c64cc62c64ab6663166fb80e14caaeb88b5652ea0d030e9684e67e5e87
```

Kustomize pins the same OCI index digest. Production rollout should use this immutable reference rather than `:latest`; the promoted digest must not be rebuilt under the final tag.

## Related documents

- [SECURITY.md](SECURITY.md)
- [MIGRATION.md](MIGRATION.md)
- [TESTING_AND_PRODUCTION.md](TESTING_AND_PRODUCTION.md)
- [RELEASE.md](RELEASE.md)
