# Environment variables and container operations

This guide describes the environment variables used by the application container, the persistent volumes to preserve and the essential management operations. Before production startup, copy `.env.example` to `.env`, replace every secret and make sure every path under `/data` is backed by persistent storage.

## Quick start with Docker Compose

```bash
cp .env.example .env
# edit POSTGRES_PASSWORD, DATABASE_URL, SECRET_KEY and ADMIN_INITIAL_PASSWORD
# default: use the published desalvo/cybersecurity-incident-registry:latest image
docker compose pull
docker compose up -d

# alternative: build the image locally from the source tree
docker compose -f docker-compose.yml -f docker-compose.build.yml build --no-cache web
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d
```

Useful checks:

```bash
docker compose ps
docker compose logs -f web
docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Stop the application without deleting data:

```bash
docker compose down
```

Remove containers and volumes, destructive and intended only for test environments:

```bash
docker compose down -v
```

## Required production variables

| Variable | Purpose | Operational notes |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string for the application database. | In production it must point to PostgreSQL, for example `postgresql+psycopg2://user:password@db:5432/incidents`. SQLite is rejected when `CIR_PRODUCTION=1`. |
| `SECRET_KEY` | Flask secret key for sessions, CSRF and signatures. | Must be random and at least 32 characters long. Generate it, for example, with `openssl rand -hex 32`. Changing it invalidates existing sessions. |
| `ADMIN_INITIAL_PASSWORD` | Temporary password for the local `admin` user at first initialization. | Used only when the `admin` user does not exist yet. Change it from the UI after first login. Weak values are rejected in production. Bootstrap accepts values copied with surrounding quotes or CRLF and removes only those artefacts. |
| `CIR_PRODUCTION` | Enables production-ready checks. | Set to `1` in production. It enables fail-fast validation for weak secrets, weak admin bootstrap passwords, SQLite databases and refuses CSRF disabling. |


## Local/test security switches

| Variable | Default | Purpose |
|---|---:|---|
| `CIR_DISABLE_CSRF` | `0` | Disables CSRF validation only for local development or automated tests. With `CIR_PRODUCTION=1`, the application refuses to start when this variable is set to a truthy value. Never use it in production. |


## Docker image, local build and runtime user

Compose defaults to `CIR_IMAGE=desalvo/cybersecurity-incident-registry:latest`. Use the `docker-compose.build.yml` override to build locally. `APP_UID` and `APP_GID`, default `10001`, define the owner used by the entrypoint when preparing writable volumes. Change them only when the target infrastructure requires specific UID/GID values. `CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE`, default `1`, avoids startup crashes on host bind mounts that cannot be fixed by the container; hardened installations can set it to `0` to require correct host-side permissions.

## PostgreSQL Compose service variables

| Variable | Purpose | Operational notes |
|---|---|---|
| `POSTGRES_DB` | Database name created by the PostgreSQL container. | Default `incidents`. Must match `DATABASE_URL`. |
| `POSTGRES_USER` | PostgreSQL user created by the container. | Default `incidents`. Must match `DATABASE_URL`. |
| `POSTGRES_PASSWORD` | Password for the PostgreSQL user. | Required by `docker-compose.yml`. Use a long, unique password. |

These three variables are consumed by the `db` container. The `web` application uses `DATABASE_URL` to connect to the database.

## Application metadata variables

| Variable | Default | Purpose |
|---|---:|---|
| `APP_NAME` | `Cybersecurity Incident Registry` | Name shown in **Info → Application**. |
| `APP_VERSION` | `0.7.0-7` | Application version shown by the UI and deployment manifests. |
| `APP_BUILD` | `20260608` | Build number shown by the UI. |
| `APP_AUTHOR` | `Alessandro De Salvo` | Displayed author. |
| `APP_AUTHOR_EMAIL` | `Alessandro.DeSalvo@roma1.infn.it` | Displayed author e-mail. |
| `ADMIN_EMAIL` | `admin@example.local` | E-mail assigned to the bootstrap admin when the user is created on first startup. |

## Persistent storage variables

| Variable | Container default | Content | Recommended volume/PVC |
|---|---|---|---|
| `UPLOAD_DIR` | `/data/uploads` | Uploaded documents and incident attachments. | Persistent volume/PVC. |
| `LOGO_DIR` | `/data/logo` | Configurable application logo. | Persistent volume/PVC. |
| `FORM_TEMPLATE_DIR` | `/data/form_templates` | PDF templates uploaded for form generation. | Persistent volume/PVC. |
| `SSO_LOGO_DIR` | `/data/sso_logos` | Shared SSO/OAuth2 provider logos uploaded from the UI. | Persistent volume/PVC. |
| `SSL_DIR` | `/data/ssl` | HTTPS certificates uploaded or activated by the application. | Protected persistent volume/PVC. |
| `BACKUP_DIR` | `/data/backups` | Local backups generated by the application. | Persistent volume/PVC. |

Paths under `/data` must not be ephemeral in production. `docker-compose.yml` mounts them as named volumes; Kubernetes manifests mount them through PVCs. At Docker startup the entrypoint fixes ownership and permissions for UID/GID `10001`; in Kubernetes an initContainer named `prepare-persistent-volumes` and `fsGroup: 10001` prepare the PVCs, including SSO logos and AI documents, before the non-root application container starts. Backup and restore procedures must include both PostgreSQL and all persistent volumes.

## HTTP security and upload variables

| Variable | Default | Purpose |
|---|---:|---|
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` when the app is served through HTTPS or behind an HTTPS reverse proxy. With `SESSION_COOKIE_SECURE=0`, cookies remain usable on `http://localhost:8000` and CSRF-protected login works even with `CIR_PRODUCTION=1`. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | SameSite policy for the session cookie. |
| `REMEMBER_COOKIE_SAMESITE` | `Lax` | SameSite policy for the remember-me cookie. |
| `CIR_FORCE_HSTS` | `0` | Set to `1` to send HSTS even when Flask does not directly see HTTPS, for example behind a TLS reverse proxy. |
| `MAX_CONTENT_LENGTH` | `26214400` | Global upload limit in bytes, default 25 MiB. The initial value comes from `MAX_CONTENT_LENGTH`, but it can be changed from Admin → Other configurations → Maximum upload size (MB). The app also aligns `MAX_FORM_MEMORY_SIZE` to the same value to avoid 413 errors on multipart forms with large fields; workflow imports also use a temporary server-side token after the preview. Align reverse proxy and Kubernetes ingress limits to the same or a higher value. |
| `LOGIN_LOCKOUT_THRESHOLD` | `5` | Failed attempts, per IP/username pair, after which server-side lockout starts. |
| `LOGIN_LOCKOUT_WINDOW_SECONDS` | `900` | Time window in seconds used to count failed attempts. |
| `LOGIN_LOCKOUT_STEP_SECONDS` | `60` | Progressive temporary-lockout increment after the threshold is exceeded. |
| `LOGIN_LOCKOUT_MAX_SECONDS` | `900` | Maximum temporary-lockout duration. |
| `FLASK_ENV` | unset | If set to `production`, the app is treated as production even without `CIR_PRODUCTION=1`. |

## Notification and reminder scheduler

| Variable | Default | Purpose |
|---|---:|---|
| `CIR_ENABLE_DEADLINE_SCHEDULER` | `1` | Enables the internal scheduler for deadline notifications and reminders. Set to `0`, `false` or `no` to disable it. |
| `CIR_DEADLINE_SCHEDULER_POLL_SECONDS` | `60` | Scheduler polling interval, with an effective minimum of 30 seconds. |

With PostgreSQL the scheduler uses advisory locks to avoid duplicate executions with multiple Gunicorn workers or multiple Kubernetes replicas.

## HTTP, HTTPS and Gunicorn variables

| Variable | Default | Purpose |
|---|---:|---|
| `PORT` | `8000` | Internal HTTP port. |
| `WEB_CONCURRENCY` | `1` | Number of Gunicorn workers for the HTTP listener. |
| `GUNICORN_THREADS` | `4` | Threads per Gunicorn worker. |
| `GUNICORN_TIMEOUT` | `180` | Gunicorn request timeout in seconds. |
| `SSL_ENABLED` | `0` | Enables the internal HTTPS listener when set to `1`, `true`, `yes` or `on`, or when the `$SSL_DIR/enabled` marker exists. |
| `SSL_PORT` | `8443` | Internal HTTPS port. |
| `WEB_CONCURRENCY_SSL` | value of `WEB_CONCURRENCY` | Number of workers for the HTTPS listener. |
| `CIR_SSL_CERT_FILE` | empty | Explicit user-managed certificate path for the internal HTTPS listener. |
| `CIR_SSL_KEY_FILE` | empty | Explicit user-managed private-key path for the internal HTTPS listener. |
| `SSL_CERT_FILE` | `$SSL_DIR/current.crt` | Compatibility: used as the listener certificate only when `SSL_KEY_FILE` is also set, avoiding collisions with system CA bundles. |
| `SSL_KEY_FILE` | `$SSL_DIR/current.key` | Compatibility: used as the listener key only when `SSL_CERT_FILE` is also set. |

The entrypoint always starts the HTTP listener. The HTTPS listener is started or stopped dynamically when `SSL_ENABLED` or the `$SSL_DIR/enabled` marker enable it. If `CIR_SSL_CERT_FILE`/`CIR_SSL_KEY_FILE` or the compatible `SSL_CERT_FILE`/`SSL_KEY_FILE` pair are not set and no certificate has been uploaded from the web UI, the entrypoint generates a self-signed host certificate in `$SSL_DIR/current.crt` and `$SSL_DIR/current.key`, regenerating it when it is missing or invalid. Certificates uploaded from the UI or explicitly configured through environment variables always take precedence and are never overwritten automatically.

## Image runtime variables

The following variables are set by the Dockerfile to make the runtime predictable and normally do not need to be changed:

| Variable | Value | Purpose |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE` | `1` | Avoids writing `.pyc` files. |
| `PYTHONUNBUFFERED` | `1` | Writes Python logs without buffering, useful for `docker logs`. |
| `PIP_NO_CACHE_DIR` | `1` | Avoids pip cache in the image. |
| `PIP_DISABLE_PIP_VERSION_CHECK` | `1` | Disables pip version checks during build. |
| `DEBIAN_FRONTEND` | `noninteractive` | Avoids interactive prompts during build. |

## Volume management and backup

Back up regularly:

1. PostgreSQL dump of the application database;
2. `uploads` volume or `cir-uploads` PVC;
3. `logo` volume;
4. `form_templates` volume or `cir-form-templates` PVC;
5. `sso_logos` volume or `cir-sso-logos` PVC;
6. `ssl` volume or `cir-ssl-certs` PVC, when the internal HTTPS listener is used.

Example dump with Docker Compose:

```bash
docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-incidents.sql
```

## Container upgrade

Recommended procedure with the published image:

```bash
docker compose pull
docker compose up -d
```

Recommended procedure with a local build:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml build --no-cache web
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d
```

Before upgrading, back up the database and volumes. The application's lightweight migrations are idempotent and run at startup, but they are not a replacement for backups.

## Kubernetes

The Kubernetes manifests read secrets from `cir-secrets`:

- `database-url` → `DATABASE_URL`;
- `secret-key` → `SECRET_KEY`;
- `admin-initial-password` → `ADMIN_INITIAL_PASSWORD`.

Persistent areas are mounted through PVCs:

- `cir-uploads` on `/data/uploads`;
- `cir-logo` on `/data/logo`;
- `cir-form-templates` on `/data/form_templates`;
- `cir-sso-logos` on `/data/sso_logos`;
- `cir-ssl-certs` on `/data/ssl`;
- `cir-backups` on `/data/backups`.

The deployment uses `desalvo/cybersecurity-incident-registry:latest` with `imagePullPolicy: IfNotPresent`. To use a local build in a test cluster, build/tag the same image and load it into the cluster, or change the tag with Kustomize (`k8s/kustomization.yaml`). `CIR_DISABLE_CSRF` is included in the manifests and must remain `0` in production.

In multi-replica deployments keep PostgreSQL as the database and leave the scheduler lock enabled. If the scheduler must be run by a single external component, set `CIR_ENABLE_DEADLINE_SCHEDULER=0` on the web pods.


## Container backups
The `BACKUP_DIR` variable, default `/data/backups`, identifies the local POSIX destination used by **Admin → Backup** when the local destination is selected. Mount this path on a persistent volume or PVC. The feature supports downloadable on-demand backups, local backups, S3/compatible destinations and cron-like scheduling. Scheduled backups are disabled by default and must be explicitly enabled by an administrator. S3 requires the optional `boto3` library in the image or in a derived image.

## Docker entrypoint permissions

The container uses `/app/docker-entrypoint.sh` as its startup command. The Dockerfile always runs `chmod 0755 /app/docker-entrypoint.sh` during the build. The entrypoint starts as root only to create and fix ownership/permissions of persistent volumes mounted under `/data`, seeds freshly-created volumes with default assets such as SSO logos and sample templates, then re-executes as the unprivileged `appuser` through `gosu`. This avoids startup failures on freshly-created Docker named volumes, which are normally mounted as root-owned directories. If a host bind mount blocks `chown`/`chmod`, `CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE=1` lets the container continue as root with a warning; set it to `0` to fail explicitly and fix host permissions.

When editing the script manually, check before release:

```bash
ls -l docker-entrypoint.sh
test -x docker-entrypoint.sh
pytest tests/test_container_packaging.py
```
