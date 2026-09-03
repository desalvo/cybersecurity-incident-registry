# Migrating Cybersecurity Incident Registry 0.8.0 to >= 0.9.0

This guide describes deployment changes required to migrate from the **0.8.0** baseline to **0.9.0-1** or a later **>= 0.9.0** release.

Before upgrading, take a full backup of the database and persistent volumes. In production, prefer an explicit release tag (`0.9.0-1`) or, better, an immutable `@sha256:...` digest; do not use `latest` as the final production reference.

## Docker Compose

### 1. Update the CIR image

In the `web` service of your `docker-compose.yml`, replace the 0.8.0 image with >= 0.9.0. The Compose file shipped with the release uses:

```yaml
services:
  web:
    image: ${CIR_IMAGE:-desalvo/cybersecurity-incident-registry:latest}
```

For a controlled migration, set in `.env`:

```dotenv
CIR_IMAGE=desalvo/cybersecurity-incident-registry:0.9.0-1
```

or replace `image:` directly. After validation, a later >= 0.9.0 tag may be used.

### 2. Align application configuration

Ensure the `web` service includes at least the 0.9.x security configuration:

```yaml
environment:
  DATABASE_URL: ${DATABASE_URL:?Set DATABASE_URL}
  SECRET_KEY: ${SECRET_KEY:?Set SECRET_KEY}
  ADMIN_INITIAL_PASSWORD: ${ADMIN_INITIAL_PASSWORD:?Set ADMIN_INITIAL_PASSWORD}
  SETTING_ENCRYPTION_KEY: ${SETTING_ENCRYPTION_KEY:-}
  CIR_PRODUCTION: ${CIR_PRODUCTION:-0}
  SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-0}
  CIR_DISABLE_CSRF: ${CIR_DISABLE_CSRF:-0}
  CIR_TRUSTED_PROXY_CIDRS: ${CIR_TRUSTED_PROXY_CIDRS:-}
```

For production:

```dotenv
CIR_PRODUCTION=1
CIR_DISABLE_CSRF=0
SETTING_ENCRYPTION_KEY=<stable-random-secret-at-least-32-characters>
```

`SECRET_KEY`, `ADMIN_INITIAL_PASSWORD`, and `SETTING_ENCRYPTION_KEY` must be strong and distinct. Core settings also support `_FILE` variants for Docker/Kubernetes secrets. Never set both an inline value and its corresponding `_FILE` variable.

If CIR is behind a reverse proxy, set `CIR_TRUSTED_PROXY_CIDRS` **only** to genuinely trusted proxy networks. Do not use `0.0.0.0/0`.

Use `SESSION_COOKIE_SECURE=1` when CIR is exposed through HTTPS/TLS; keep it at `0` only for intentional HTTP deployments such as development/test.

### 3. Persistent volumes

0.9.x uses these persistent paths and they must survive container replacement:

- `/data/uploads`
- `/data/logo`
- `/data/form_templates`
- `/data/sso_logos`
- `/data/ssl`
- `/data/backups`
- `/data/ai_chatbot_docs`

If the 0.8.0 Compose file did not mount one or more of these paths, add the missing volumes before starting 0.9.x. Do not delete/recreate existing volumes during a simple image upgrade.

### 4. PostgreSQL

The 0.9.0-1 Compose file uses `postgres:18.6` for new installations/tests. **Do not upgrade an existing PostgreSQL installation across major versions by merely changing the image tag.** If 0.8.0 runs a different PostgreSQL major, follow the official PostgreSQL upgrade process (`pg_upgrade`, dump/restore, or the managed-service procedure) and validate backups first.

### 5. Production Compose

For production use the additional file:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
```

Set an immutable release image:

```dotenv
CIR_PRODUCTION_IMAGE=desalvo/cybersecurity-incident-registry:0.9.0-1
```

or preferably:

```dotenv
CIR_PRODUCTION_IMAGE=desalvo/cybersecurity-incident-registry@sha256:<digest>
```

The production override enables a read-only root filesystem, reduced capabilities, `no-new-privileges`, HSTS/Secure cookies, and disables root fallback for persistent-volume permission failures.

## Kubernetes / Kustomize

### 1. Update the image

In a 0.8.0 deployment replace:

```yaml
image: desalvo/cybersecurity-incident-registry:<0.8.x-tag>
```

with:

```yaml
image: desalvo/cybersecurity-incident-registry:0.9.0-1
```

The 0.9.0-1 package also ships `k8s/kustomization.yaml`:

```yaml
images:
- name: desalvo/cybersecurity-incident-registry
  newName: desalvo/cybersecurity-incident-registry
  newTag: "0.9.0-1"
```

For a private registry, change `newName`; for a later >= 0.9.0 release, change `newTag`. Production/GitOps promotion should preferably use an immutable digest.

### 2. Update Secrets

The provided 0.9.x Deployment uses these main Secret keys:

- `database-url`
- `secret-key`
- `admin-initial-password`
- `setting-encryption-key`

`k8s/secrets.example.yaml` is only a template and is **not** automatically applied by Kustomize. Create `cir-secrets` through your secret manager, External Secrets, Sealed Secrets, or another appropriate mechanism.

### 3. Update Deployment environment

Verify at least:

```yaml
- {name: APP_VERSION, value: "0.9.0-1"}
- {name: CIR_PRODUCTION, value: "1"}
- {name: SESSION_COOKIE_SECURE, value: "1"}
- {name: CIR_DISABLE_CSRF, value: "0"}
- {name: CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE, value: "0"}
```

When an ingress/reverse proxy is present, add `CIR_TRUSTED_PROXY_CIDRS` with only trusted proxy CIDRs.

### 4. Align volumes/PVCs

0.9.x mounts separate PVCs for uploads, logo, templates, SSO logos, certificates, backups, and AI knowledge-base documents. Before upgrading, reuse the 0.8.0 PVCs that contain existing data and create only missing PVCs. Do not accidentally point the new Deployment at empty PVCs when existing data must be preserved.

### 5. SecurityContext and probes

The 0.9.x manifest introduces/strengthens:

- `runAsNonRoot: true` with UID/GID 10001;
- read-only root filesystem;
- `seccompProfile: RuntimeDefault`;
- all Linux capabilities dropped for the application container;
- `automountServiceAccountToken: false`;
- readiness/liveness probes on `/healthz`;
- a size-limited `/tmp` `emptyDir`.

If you keep custom Kubernetes manifests from 0.8.0, carry these controls forward rather than changing only the image tag.

## Post-migration verification

After upgrading:

1. verify `/healthz` and startup logs;
2. verify login, CSRF, and session-cookie behavior;
3. verify tenant-isolated incident access;
4. verify upload/download, templates, logos, backups, and AI documents;
5. check for schema-hardening/orphan-row warnings;
6. take a full 0.9.x backup before declaring the migration complete.

See `RELEASE_NOTES_0.9.0-1_en.md` for the cumulative functional and security changes in the release.
