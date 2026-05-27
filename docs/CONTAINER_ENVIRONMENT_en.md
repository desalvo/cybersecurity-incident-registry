# Environment variables and container operations

This guide describes the environment variables used by the application container, the persistent volumes to preserve and the essential management operations. Before production startup, copy `.env.example` to `.env`, replace every secret and make sure every path under `/data` is backed by persistent storage.

## Quick start with Docker Compose

```bash
cp .env.example .env
# edit POSTGRES_PASSWORD, DATABASE_URL, SECRET_KEY and ADMIN_INITIAL_PASSWORD
docker compose build --no-cache
docker compose up -d
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
| `ADMIN_INITIAL_PASSWORD` | Temporary password for the local `admin` user at first initialization. | Used only when the `admin` user does not exist yet. Change it from the UI after first login. Weak values are rejected in production. |
| `CIR_PRODUCTION` | Enables production-ready checks. | Set to `1` in production. It enables fail-fast validation for weak secrets, weak admin bootstrap passwords and SQLite databases. |

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
| `APP_VERSION` | `0.5.0-1` | Application version shown by the UI and deployment manifests. |
| `APP_BUILD` | `20260522` | Build number shown by the UI. |
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

Paths under `/data` must not be ephemeral in production. `docker-compose.yml` mounts them as named volumes; Kubernetes manifests mount them through PVCs. Backup and restore procedures must include both PostgreSQL and all persistent volumes.

## HTTP security and upload variables

| Variable | Default | Purpose |
|---|---:|---|
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` when the app is served through HTTPS or behind an HTTPS reverse proxy. Secure cookies are forced when `CIR_PRODUCTION=1`. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | SameSite policy for the session cookie. |
| `REMEMBER_COOKIE_SAMESITE` | `Lax` | SameSite policy for the remember-me cookie. |
| `CIR_FORCE_HSTS` | `0` | Set to `1` to send HSTS even when Flask does not directly see HTTPS, for example behind a TLS reverse proxy. |
| `MAX_CONTENT_LENGTH` | `26214400` | Global upload limit in bytes, default 25 MiB. |
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
| `SSL_CERT_FILE` | `$SSL_DIR/current.crt` | Certificate used by the internal HTTPS listener. |
| `SSL_KEY_FILE` | `$SSL_DIR/current.key` | Private key used by the internal HTTPS listener. |

The entrypoint always starts the HTTP listener. The HTTPS listener is started or stopped dynamically when `SSL_ENABLED` or the `$SSL_DIR/enabled` marker enable it and when the certificate and key are readable.

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

Recommended procedure:

```bash
docker compose pull || true
docker compose build --no-cache
docker compose up -d
```

Before upgrading, back up the database and volumes. The application's lightweight migrations are idempotent and run at startup, but they are not a replacement for backups.

## Kubernetes

The Kubernetes manifests read secrets from `cir-secrets`:

- `database-url` → `DATABASE_URL`;
- `secret-key` → `SECRET_KEY`;
- `admin-initial-password` → `ADMIN_INITIAL_PASSWORD`.

Persistent areas are mounted through PVCs:

- `cir-uploads` on `/data/uploads`;
- `cir-form-templates` on `/data/form_templates`;
- `cir-sso-logos` on `/data/sso_logos`;
- `cir-ssl-certs` on `/data/ssl`.

In multi-replica deployments keep PostgreSQL as the database and leave the scheduler lock enabled. If the scheduler must be run by a single external component, set `CIR_ENABLE_DEADLINE_SCHEDULER=0` on the web pods.


## Container backups
The `BACKUP_DIR` variable, default `/data/backups`, identifies the local POSIX destination used by **Admin → Backup** when the local destination is selected. Mount this path on a persistent volume or PVC. The feature supports downloadable on-demand backups, local backups, S3/compatible destinations and cron-like scheduling. Scheduled backups are disabled by default and must be explicitly enabled by an administrator. S3 requires the optional `boto3` library in the image or in a derived image.

## Docker entrypoint permissions

The container uses `/app/docker-entrypoint.sh` as its startup command. The Dockerfile always runs `chmod 0755 /app/docker-entrypoint.sh` during the build, before switching to `USER appuser`, so the image remains startable even when the source ZIP package or extraction filesystem does not preserve Unix executable bits.

When editing the script manually, check before release:

```bash
ls -l docker-entrypoint.sh
test -x docker-entrypoint.sh
pytest tests/test_container_packaging.py
```
