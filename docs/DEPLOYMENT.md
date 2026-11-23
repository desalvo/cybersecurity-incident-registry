# Deployment

This document is the consolidated deployment reference for Cybersecurity Incident Registry 0.10.0-1.

## Upgrade an existing 0.9.0-1 installation to 0.10.0-1

Use the [0.10.0-1 upgrade procedure](MIGRATION.md#aggiornamento-a-0100-1-da-090-1)
when replacing an existing application image. The functional version is
`0.10.0-1`; CI generates the `YYYYMMDD` build once and shares it across all jobs.
The distributed `VERSION`/`BUILD`, source commit and immutable image digest
identify the release. The version bump adds no DDL revision; the existing
`20261122_01_legacy_bridge` remains unchanged. Keep the existing PostgreSQL database, storage
layout and encryption/session secrets. Start one application replica with one
worker after a coordinated database/filesystem backup, allow startup migrations
to finish, then verify the application before restoring the intended scale.
Routine upgrade does not require Full Import or an anonymized bootstrap export.
The container runs `python -m app.migrate` before starting HTTP/HTTPS workers.
An ordered, destination-local schema ledger applies missing revisions and rejects
unknown or newer history. Failed upgrades do not start the web listeners; the
same compatibility validation also applies to non-container application starts.
Stop the old web replicas and finish any Full Import/restore before upgrading;
concurrent imports and mixed-version rolling upgrades are outside this procedure.
PostgreSQL is the production backend; concurrent SQLite migration starts are not
supported.

Review the manifest actually installed: the legacy `k8s/deployment.yaml` has no
startup probe and uses HTTP liveness; the Helm chart provides `Recreate`, a startup
probe, TCP liveness and longer request/termination timeouts. Updating only the
image does not transfer these chart settings to an existing Deployment. The
migration guide includes the maintenance sequence, slow-start checks, Compose
procedure and rollback limitations. A change of PostgreSQL major version or
migration from separate PVCs to `/data` remains a separate operation.

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

Direct Docker builds generate the build date automatically. If the source package
already contains validated UI screenshots and manuals, preserve the build to which
that evidence belongs by supplying `--build-arg CIR_RELEASE_BUILD="$(cat BUILD)"`.
The build rejects evidence stamped for another version or build. For a new build,
CI captures the running application and regenerates the manuals using the same
shared build value before assembling the image. Source packaging stamps its
staging directory and leaves the working checkout unchanged.

## Kubernetes

The `k8s/` directory contains the deployment, PostgreSQL example, shared PVC, Kustomize configuration, secret example and the storage-layout migration example. The application deployment must preserve the hardened security context verified by `scripts/verify_security_gate_context.py`.

The current reference layout uses the shared `cir-data` PVC mounted at `/data`; the old split uploads/backups PVC layout is obsolete. `k8s/migrate-separated-pvcs-to-cir-data.example.yaml` documents the migration pattern.

## Upgrade from 0.8.0

Follow [MIGRATION.md](MIGRATION.md) before changing the running deployment. Back up database and filesystem data, validate configuration/secret changes, migrate persistent storage deliberately, and retain a rollback path. PostgreSQL major-version upgrades require a database migration procedure; do not treat a major image-tag change as an in-place data-format upgrade.

## Secrets and trusted proxies

Core settings support the documented `_FILE` form for container secrets. Never set both a direct value and its `_FILE` counterpart. Configure `CIR_TRUSTED_PROXY_CIDRS` only with actual reverse-proxy networks so client IP handling and login rate limiting cannot be bypassed by spoofed forwarded headers.

## Production image digest

The 0.10.0-1 RC1 source package keeps `PRODUCTION_IMAGE_DIGEST` at
`PENDING_HOTFIX_REBUILD`. It is not an image reference and cannot be deployed.
Supply the immutable OCI **index** digest only after the new source image passes
the CI gates separately for `linux/amd64` and `linux/arm64`. A manifest inspection
alone is not vulnerability-gate evidence. The installation tools never build,
promote, or record a production image.

Historical record: Hotfix 7 previously recorded the OCI index
`sha256:37ad92c7437abce6f5a7b8504b8c440cab6f1ac5e38ecdaf287128bffbb9702a`.
That historical image does not contain the current cumulative changes. The digest-recording commit
remains metadata-only and must not trigger another image build.

## Related documents

- [SECURITY.md](SECURITY.md)
- [MIGRATION.md](MIGRATION.md)
- [TESTING_AND_PRODUCTION.md](TESTING_AND_PRODUCTION.md)
- [RELEASE.md](RELEASE.md)


## Helm installation on Kubernetes and OpenShift

The chart is in `charts/cybersecurity-incident-registry`. Its `appVersion` is
`0.10.0-1`; `version: 0.2.0-rc1` identifies the installation package separately
from the functional application version. One chart supports both platforms. The
`values-openshift.yaml` overlay selects OpenShift and its HTTPS Route. There are
no chart dependencies to download during installation.

The defaults intentionally cannot be installed without configuration:
`image.digest` and `existingSecret` are empty. The JSON schema and template guards
reject a missing or mutable image digest, a missing Secret, unsupported parameters,
a non-TLS Ingress, and multiple application replicas with RWO storage. Credentials
are never stored in Helm values, generated manifests or Helm release history.
Helm applies `values.schema.json` to the merged values during lint, template,
install and upgrade; see the [official chart format](https://helm.sh/docs/topics/charts/).

### Prerequisites and secrets

Use Helm 3.14 or newer within major version 3, plus `kubectl` for Kubernetes
or `oc` for OpenShift. The installer checks rendered YAML using Python 3 and
PyYAML, already used by the CIR development checks. The namespace/project and its
Secrets must exist before installation. Check the current client context before
running a deployment command.

Create a Secret, for example `cir-secrets`, using your secret manager or the console
Secret form. The default keys are:

| Key | Required value |
| --- | --- |
| `database-url` | `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE`, with credentials URL-encoded; use your PostgreSQL TLS parameters when required |
| `secret-key` | At least 32 random characters |
| `setting-encryption-key` | A different random value of at least 32 characters; retain it when restoring encrypted application settings |
| `admin-initial-password` | A unique initial administrator password of at least 12 characters |

The application still validates production secrets at startup. Only the two
PostgreSQL URL schemes supported by the installation wrapper are accepted:
`postgresql://` and `postgresql+psycopg2://`. SQLite is not an installation option.
Keep credentials out of shell command arguments, source control and value files.
Secret key names can be changed through `secretKeys` when adapting an existing
secret manager integration. Private registries can use `image.pullSecrets`.

### Values and a reviewed installation

Create a local `production-values.yaml` outside the release source tree. Replace
the digest placeholder with the approved index digest; the example is deliberately
not executable unchanged.

```yaml
image:
  digest: "sha256:REPLACE_WITH_THE_64_HEX_APPROVED_OCI_INDEX_DIGEST"
existingSecret: cir-secrets
persistence:
  size: 20Gi
  storageClass: YOUR_STORAGE_CLASS
trustedProxyCidrs:
  - YOUR_ACTUAL_ROUTER_CIDR
```

The default database is **external PostgreSQL**, and the default application has
one replica with a `ReadWriteOnce` PVC. Existing storage can be selected through
`persistence.existingClaim`; otherwise a PVC is created. To use multiple replicas,
set `persistence.accessMode: ReadWriteMany` and provide a compatible shared storage
class. The chart uses `Recreate` during a revision change, so plan the brief
maintenance window; it does not run overlapping old and new revisions against a
restore volume. Full Import remains a coordinated administrative operation.

For Kubernetes, either configure a TLS Ingress with `ingress.enabled`,
`ingress.host`, `ingress.className` and `ingress.tlsSecret`, or put the internal
ClusterIP Service behind your existing HTTPS proxy. Secure cookies remain enabled
when Ingress is disabled, so a plain HTTP public endpoint is insufficient.

Render and review first:

```bash
./scripts/install_cluster.sh --values production-values.yaml \
  --platform kubernetes --namespace cir --release cir \
  --output cir-rendered.yaml
```

For OpenShift, change `--platform kubernetes` to `--platform openshift`; the
installer loads the OpenShift overlay before your own values file. Rendering is
the default and does not access or change a cluster. To install after review:

```bash
./scripts/install_cluster.sh --values production-values.yaml \
  --platform openshift --namespace cir --release cir --apply
```

`--apply` checks required Secret **key names** without printing their values,
performs server-side dry-run admission, then runs Helm with `--atomic --wait` and
a 40-minute timeout. A failed admission, schema, rendering or security check stops
before installation. The command uses the current authenticated client context;
it does not create RBAC grants or grant privileged SCCs.

The immutable-image check verifies syntax. Approval of that digest still comes
from the CI scan evidence and is not inferred from the existence of the image.

### Non-root volumes and OpenShift restricted SCCs

Both chart modes enforce `runAsNonRoot`, `allowPrivilegeEscalation: false`,
`readOnlyRootFilesystem: true`, capabilities `drop: [ALL]`, `RuntimeDefault`
seccomp and disabled service-account token mounting. No privileged or root
permission-fixing init container is used. The application writes only to the
persistent `/data` tree and the `/tmp` volume. Its temporary home is
`/tmp/cir-home`.

Kubernetes defaults to UID/GID/fsGroup 10001 for CIR. OpenShift omits fixed UID,
GID and fsGroup so a compatible restricted SCC can allocate them for the project.
Use storage whose CSI driver honors the assigned fsGroup; for pre-existing
volumes, have the storage administrator arrange appropriate ownership before
installation. Do not solve a permission error by granting `anyuid`, enabling
root fallback or disabling the read-only root filesystem.

The design follows Red Hat's [arbitrary UID image guidance](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/images/creating-images)
and [restricted SCC requirements](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html-single/authentication_and_authorization/index).
Kubernetes describes volume-group ownership and CSI delegation in its
[security-context documentation](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/).
The shipped source has not been runtime-certified for a particular OpenShift or
storage-driver combination; perform admission and writable-volume checks in your
target environment before a production rollout.

### Optional internal PostgreSQL 18

Set `database.mode: internal` only when you want this chart to manage a single
PostgreSQL instance. This is not an HA database service. Supply both
`database.internal.image.digest` for a verified **PostgreSQL 18 Debian-based**
image and `database.internal.existingSecret`. The latter defaults to keys
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. The CIR `database-url` Secret
must reference the corresponding service:
`<release>-<chart-name>-postgres` (the generated prefix is truncated to 52
characters). With release `cir` and no name override it is
`cir-cybersecurity-incident-registry-postgres`.

The internal database mounts its PVC at `/var/lib/postgresql` and sets
`PGDATA=/var/lib/postgresql/18/docker`. Separate writable volumes provide
`/var/run/postgresql`, `/tmp` and `/dev/shm`, allowing a read-only root filesystem.
Kubernetes defaults to UID/GID/fsGroup 999; OpenShift again uses the SCC-assigned
UID and fsGroup. The official Debian image's entrypoint includes support for an
arbitrary UID through `nss_wrapper` when no passwd entry is available. Verify that
behavior for the exact pinned image when selecting another image distribution.

All PostgreSQL probes use `pg_isready -h 127.0.0.1`, so they wait for the final TCP
listener. The temporary initialization server is socket-only in the
[official entrypoint](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh).
The startup probe allows 360 attempts at five-second intervals (30 minutes),
preventing liveness/readiness checks from prematurely terminating `initdb`.
`PGCTLTIMEOUT=1800` also permits a slow initialization shutdown checkpoint; its
meaning is documented by [PostgreSQL pg_ctl](https://www.postgresql.org/docs/18/app-pg-ctl.html).
These budgets are configurable, but do not repair a blocked storage device. If
`initdb` is stuck in uninterruptible I/O, investigate the PVC/CSI/node rather than
disabling durable writes or deleting a volume containing data.

CIR startup has a ten-minute budget by default. Web liveness checks the TCP
listener, while readiness checks `/healthz`, so busy HTTP workers during a Full
Import do not alone cause a liveness restart. The chart sets request and graceful
shutdown timeouts to 1800 seconds; the entrypoint now validates and uses
`GUNICORN_GRACEFUL_TIMEOUT` for both listeners. These checks follow the Kubernetes
[startup-probe lifecycle](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

### Graphical installation from the OpenShift console

Two paths are supplied. Both require an already-approved image digest and a
pre-existing Secret in the chosen project.

**Console Template, without publishing a chart repository:**

1. Select the target project. Create the `cir-secrets` Secret in the console with
   the keys above, pointing at external PostgreSQL.
2. Use **+Add → Import YAML** (or the console's resource import) and load
   `openshift/cir-template.yaml`. It is JSON, which is also valid YAML. This creates
   a `Template` resource in the project; it does not yet instantiate the application.
3. Open **Developer Catalog / All services**, filter for Templates and select
   **Cybersecurity Incident Registry 0.10.0-1**. Instantiate it with `NAME`,
   `EXISTING_SECRET`, `IMAGE_REPOSITORY`, the 64 hexadecimal characters of the
   approved index in `IMAGE_SHA256`, storage size and optional hostname/proxy CIDRs.
4. Review the generated Deployment, Service, PVC and HTTPS Route, then create
   them. Follow the pod events and open the Route after the readiness probe passes.

This Template intentionally offers the simple one-replica, external-PostgreSQL
installation. Use the Helm form for custom existing PVCs, internal PostgreSQL or
other chart options. If your administrator has disabled the Template catalog,
use the generated resource List with Import YAML instead:

```bash
python3 scripts/render_openshift_template.py \
  -p IMAGE_SHA256=REPLACE_WITH_64_APPROVED_HEX_CHARACTERS \
  -p EXISTING_SECRET=cir-secrets --output cir-openshift.json
```

The offline renderer validates parameters and writes a resource List; it does not
deploy it. The console's native Template processing checks required parameters,
while the Kubernetes image pull also rejects an invalid `@sha256` reference.
The application wrapper enforces PostgreSQL and production secret validation at
startup. Template uploads and instantiation follow the Red Hat
[template workflow](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/observability/building_applications/index).

**Helm catalog and form:**

Create the local packages first, with a real Helm client available:

```bash
python3 scripts/check_installation_package.py --require-helm
python3 scripts/package_installers.py --output ../cir-installers \
  --repository-url https://YOUR_CONTROLLED_HOST/cir --require-helm
```

The output contains a chart `.tgz`, `index.yaml`, an installation ZIP, SHA-256 files
and a verification-status JSON. Package creation is local only. Publish the
`.tgz` and `index.yaml` at the controlled HTTPS endpoint using your normal release
process, after verifying the package. Update `openshift/helm-repository.example.yaml`
with that real URL and import it into the target project. Its
`ProjectHelmChartRepository` is namespaced; it does not require a cluster-wide
repository when the project's RBAC permits it. The example `.invalid` URL is
intentionally unusable.

In **+Add → Helm / Developer Catalog**, select the CIR repository and chart, then
configure the form generated from `values.schema.json`. Select `platform:
openshift`, enable `route.enabled`, provide the approved image digest and existing
Secret, and review the YAML before installing. The chart is a prerelease version;
if your console filters prereleases, use the Template path or the supplied local
Helm command until a verified chart version is published for that catalog.
The repository layout follows [Helm's repository guide](https://helm.sh/docs/topics/chart_repository/)
and the console registration follows [Red Hat's Helm catalog guide](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/building_applications/working-with-helm-charts).

### Verification, upgrades and retained data

`python3 scripts/check_installation_package.py` validates source structure and the
processed standalone Template. It explicitly reports that Helm and cluster checks
were not run. `--require-helm` additionally performs real `helm lint --strict` and
`helm template` for Kubernetes/OpenShift with external/internal PostgreSQL, checks
rendered hardening and confirms missing credentials metadata/digests are rejected.
The rendering fixtures contain synthetic digests only for tests; they are never
stored in `PRODUCTION_IMAGE_DIGEST` or deployed.

The installer packager is deterministic and does not require Helm for source
packaging. Without `--require-helm`, its evidence records `helm_render: NOT_RUN`;
that source package must still pass the render gate before release/deployment.
For RC18 prepared in this workspace, 24 installer unittest cases passed and the
real Helm case was skipped because Helm was unavailable and its official binary
download was blocked. Cluster admission, image startup, CSI permissions and real
PostgreSQL initialization remain environment checks, not claimed results.

The chart sets `helm.sh/resource-policy: keep` on its PVCs. Uninstall therefore
retains data; an explicit later reuse should select `existingClaim`. Keep matching
PostgreSQL and `/data` backups before upgrade. Helm rollback changes Kubernetes
objects but is not a database schema or data rollback. PostgreSQL major-version
changes require a separate migration. The console Template also leaves ownership
of backup and PVC lifecycle with the administrator; never delete a claim merely
to resolve a failed first-start diagnosis.


The GitHub `quality-gates` job now runs `helm version --short` and
`check_installation_package.py --require-helm` before pytest. The official
[Ubuntu 24.04 runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)
lists Helm; its actual version is recorded in the run log. The verifier requires
a stable Helm 3 release at least 3.14; a major-version migration must be reviewed
before changing the supported range. A missing or unsupported Helm client
is a hard failure, including when adopting a self-hosted runner. After the other
quality gates, CI packages the chart/Template with `--require-helm` and uploads
`installation-<commit>` artifacts. No source-only fallback can authorize promotion.
