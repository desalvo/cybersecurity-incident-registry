# Migration, backup, import and recovery

Consolidated migration guidance for 0.8.0 to 0.9.0-1, Full Export/Import, database/filesystem handling, Kubernetes storage migration, rollback and recovery.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `MIGRATION_0.8.0_TO_0.9.0.md`
- `MIGRATION_0.8.0_TO_0.9.0_en.md`
- `K8S_FULL_IMPORT_HOTFIX_0.9.0-1.md`

---

## Historical source: `MIGRATION_0.8.0_TO_0.9.0.md`

Questa guida descrive le modifiche di deployment necessarie per migrare dalla baseline **0.8.0** alla release **0.9.0-1** o a una successiva **>= 0.9.0**.

Prima dell'aggiornamento eseguire un backup completo del database e dei volumi persistenti. In produzione usare preferibilmente un tag di release esplicito (`0.9.0-1`) o, meglio, un digest immutabile `@sha256:...`; evitare `latest` come riferimento definitivo di produzione.

## Docker Compose

### 1. Aggiornare l'immagine CIR

Nel servizio `web` del proprio `docker-compose.yml`, sostituire l'immagine 0.8.0 con una >= 0.9.0. Il Compose fornito con la release usa:

```yaml
services:
  web:
    image: ${CIR_IMAGE:-desalvo/cybersecurity-incident-registry:latest}
```

Per una migrazione controllata impostare nel `.env`:

```dotenv
CIR_IMAGE=desalvo/cybersecurity-incident-registry:0.9.0-1
```

oppure sostituire direttamente `image:` con il tag desiderato. Dopo la validazione è possibile usare un tag successivo >= 0.9.0.

### 2. Allineare la configurazione applicativa

Assicurarsi che il servizio `web` includa almeno le nuove/imposte configurazioni di sicurezza della 0.9.x:

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

In produzione:

```dotenv
CIR_PRODUCTION=1
CIR_DISABLE_CSRF=0
SETTING_ENCRYPTION_KEY=<segreto-random-stabile-di-almeno-32-caratteri>
```

`SECRET_KEY`, `ADMIN_INITIAL_PASSWORD` e `SETTING_ENCRYPTION_KEY` devono essere valori robusti e distinti. Le variabili core supportano anche la variante `_FILE` per Docker/Kubernetes secrets. Non impostare contemporaneamente il valore inline e il corrispondente `_FILE`.

Se l'applicazione è dietro reverse proxy, valorizzare `CIR_TRUSTED_PROXY_CIDRS` **solo** con le reti dei proxy realmente fidati. Non usare `0.0.0.0/0`.

Impostare `SESSION_COOKIE_SECURE=1` quando CIR è esposto via HTTPS/TLS; mantenerlo a `0` solo in deployment HTTP consapevoli, tipicamente sviluppo/test.

### 3. Volumi persistenti

La 0.9.x usa i seguenti percorsi persistenti, che devono sopravvivere alla sostituzione del container:

- `/data/uploads`
- `/data/logo`
- `/data/form_templates`
- `/data/sso_logos`
- `/data/ssl`
- `/data/backups`
- `/data/ai_chatbot_docs`

Se il Compose 0.8.0 non montava uno o più di questi percorsi, aggiungere i relativi volumi prima di avviare la 0.9.x. Non cancellare o ricreare i volumi esistenti durante il semplice upgrade dell'immagine.

### 4. PostgreSQL

Il Compose della 0.9.0-1 usa `postgres:18.6` per nuove installazioni/test. **Non aggiornare automaticamente una istanza PostgreSQL esistente a una nuova major cambiando solo il tag dell'immagine.** Se la 0.8.0 usa una major PostgreSQL diversa, seguire la procedura ufficiale PostgreSQL (`pg_upgrade`, dump/restore o servizio gestito) e validare il backup prima della migrazione.

### 5. Compose production

Per production usare il file aggiuntivo:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
```

Impostare un'immagine immutabile:

```dotenv
CIR_PRODUCTION_IMAGE=desalvo/cybersecurity-incident-registry:0.9.0-1
```

oppure, preferibilmente:

```dotenv
CIR_PRODUCTION_IMAGE=desalvo/cybersecurity-incident-registry@sha256:<digest>
```

Il file production abilita root filesystem read-only, capability ridotte, `no-new-privileges`, HSTS/cookie Secure e disabilita il fallback root sui volumi.

## Kubernetes / Kustomize

### 1. Aggiornare l'immagine

Nel deployment 0.8.0 sostituire:

```yaml
image: desalvo/cybersecurity-incident-registry:<tag-0.8.x>
```

con:

```yaml
image: desalvo/cybersecurity-incident-registry:0.9.0-1
```

Il package 0.9.0-1 include anche `k8s/kustomization.yaml`:

```yaml
images:
- name: desalvo/cybersecurity-incident-registry
  newName: desalvo/cybersecurity-incident-registry
  digest: sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b
```

Il package production 0.9.0-1 e gia pinning al digest OCI validato. Se si usa un repository privato, modificare `newName` e registrare il digest della propria immagine validata; per una release successiva >= 0.9.0 aggiornare il digest dopo build e gate di sicurezza.

### 2. Aggiornare i Secret

La 0.9.x richiede/usa i seguenti secret principali nel Deployment fornito:

- `database-url`
- `secret-key`
- `admin-initial-password`
- `setting-encryption-key`

`k8s/secrets.example.yaml` è soltanto un modello e **non** viene applicato automaticamente da Kustomize. Creare `cir-secrets` con il proprio secret manager, External Secrets, Sealed Secrets o un altro meccanismo appropriato.

### 3. Aggiornare le variabili del Deployment

Verificare almeno:

```yaml
- {name: APP_VERSION, value: "0.9.0-1"}
- {name: CIR_PRODUCTION, value: "1"}
- {name: SESSION_COOKIE_SECURE, value: "1"}
- {name: CIR_DISABLE_CSRF, value: "0"}
- {name: CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE, value: "0"}
```

Se c'è un ingress/reverse proxy, aggiungere `CIR_TRUSTED_PROXY_CIDRS` con i soli CIDR dei proxy fidati.

### 4. Allineare i volumi/PVC

La hotfix Kubernetes della 0.9.0-1 usa **un unico PVC `cir-data` montato su `/data`**. Le directory `uploads`, `logo`, `form_templates`, `sso_logos`, `ssl`, `backups` e `ai_chatbot_docs` devono essere sottodirectory dello stesso filesystem. Questo requisito e necessario per il Full Import atomico: staging, backup temporaneo e directory destinazione devono supportare `os.replace()` sullo stesso filesystem.

Non montare PVC separati direttamente su `/data/uploads`, `/data/backups`, ecc. e non usare un `emptyDir` per il solo parent `/data`: entrambe le configurazioni rompono il modello di staging atomico del Full Import. Il manifest fornito richiede `ReadWriteMany` perche il Deployment prevede due repliche; se lo storage del cluster offre solo `ReadWriteOnce`, usare una replica oppure uno storage condiviso appropriato.

Se una precedente installazione 0.9.0-1 ha gia usato i sette PVC separati, scalare CIR a zero e migrare i dati nel nuovo `cir-data` prima del rollout. Il file `k8s/migrate-separated-pvcs-to-cir-data.example.yaml` fornisce un Job di esempio e non viene applicato automaticamente da Kustomize. Per una nuova installazione 0.9.0-1 che importa un Full Export 0.8.0, creare direttamente `cir-data` e poi eseguire il Full Import.

### 5. SecurityContext e probe

Il manifest 0.9.x introduce/rafforza:

- `runAsNonRoot: true` con UID/GID 10001;
- root filesystem read-only;
- `seccompProfile: RuntimeDefault`;
- drop di tutte le Linux capabilities nel container applicativo;
- `automountServiceAccountToken: false`;
- readiness/liveness probe su `/healthz`;
- volume `/tmp` `emptyDir` limitato.

Se si mantengono manifest Kubernetes personalizzati della 0.8.0, riportare questi controlli anziché aggiornare soltanto il tag immagine.

## Verifica post-migrazione

Dopo l'upgrade:

1. verificare `/healthz` e i log di startup;
2. verificare login, CSRF e session cookie;
3. verificare accesso agli incidenti del tenant corretto;
4. verificare upload/download, template, loghi, backup e documenti AI;
5. controllare che non compaiano warning di schema hardening/orphan row;
6. eseguire un backup completo 0.9.x prima di considerare conclusa la migrazione.

Le modifiche funzionali e di sicurezza cumulative della release sono descritte in `docs/RELEASE.md`.

---

## Historical source: `MIGRATION_0.8.0_TO_0.9.0_en.md`

This guide describes deployment changes required to migrate from the **0.8.0** baseline to **0.9.0-1** or a later **>= 0.9.0** release.

Before upgrading, take a full backup of the database and persistent volumes. In production, prefer an explicit release tag (`0.9.0-1`) or, better, an immutable `@sha256:...` digest; do not use `latest` as the final production reference.

### 1. Update the CIR image

In the `web` service of your `docker-compose.yml`, replace the 0.8.0 image with >= 0.9.0. The Compose file shipped with the release uses:

For a controlled migration, set in `.env`:

or replace `image:` directly. After validation, a later >= 0.9.0 tag may be used.

### 2. Align application configuration

Ensure the `web` service includes at least the 0.9.x security configuration:

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

If the 0.8.0 Compose file did not mount one or more of these paths, add the missing volumes before starting 0.9.x. Do not delete/recreate existing volumes during a simple image upgrade.

The 0.9.0-1 Compose file uses `postgres:18.6` for new installations/tests. **Do not upgrade an existing PostgreSQL installation across major versions by merely changing the image tag.** If 0.8.0 runs a different PostgreSQL major, follow the official PostgreSQL upgrade process (`pg_upgrade`, dump/restore, or the managed-service procedure) and validate backups first.

### 5. Production Compose

For production use the additional file:

Set an immutable release image:

or preferably:

The production override enables a read-only root filesystem, reduced capabilities, `no-new-privileges`, HSTS/Secure cookies, and disables root fallback for persistent-volume permission failures.

### 1. Update the image

In a 0.8.0 deployment replace:

```yaml
image: desalvo/cybersecurity-incident-registry:<0.8.x-tag>
```

with:

The 0.9.0-1 package also ships `k8s/kustomization.yaml`:

The production 0.9.0-1 package is already pinned to the validated OCI digest. For a private registry, change `newName` and record the digest of your validated image; for a later >= 0.9.0 release update the digest after build and security gates.

### 2. Update Secrets

The provided 0.9.x Deployment uses these main Secret keys:

`k8s/secrets.example.yaml` is only a template and is **not** automatically applied by Kustomize. Create `cir-secrets` through your secret manager, External Secrets, Sealed Secrets, or another appropriate mechanism.

### 3. Update Deployment environment

Verify at least:

When an ingress/reverse proxy is present, add `CIR_TRUSTED_PROXY_CIDRS` with only trusted proxy CIDRs.

### 4. Align volumes/PVCs

The 0.9.0-1 Kubernetes hotfix uses **one `cir-data` PVC mounted at `/data`**. The `uploads`, `logo`, `form_templates`, `sso_logos`, `ssl`, `backups`, and `ai_chatbot_docs` directories must be subdirectories of the same filesystem. This is required by atomic Full Import: staging, temporary rollback backup, and destination directories must support `os.replace()` on one filesystem.

Do not mount separate PVCs directly at `/data/uploads`, `/data/backups`, etc., and do not mount an `emptyDir` only at the `/data` parent: both layouts break the atomic Full Import staging model. The supplied manifest requests `ReadWriteMany` because the Deployment uses two replicas; if the cluster provides only `ReadWriteOnce`, use one CIR replica or an appropriate shared storage backend.

If an earlier 0.9.0-1 deployment already used the former seven-PVC layout, scale CIR to zero and migrate the data into the new `cir-data` claim before rollout. `k8s/migrate-separated-pvcs-to-cir-data.example.yaml` provides an example Job and is intentionally not applied by Kustomize. For a fresh 0.9.0-1 deployment receiving a Full Export from 0.8.0, create `cir-data` directly and then run Full Import.

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

See `docs/RELEASE.md` for the cumulative functional and security changes in the release.

---

## Historical source: `K8S_FULL_IMPORT_HOTFIX_0.9.0-1.md`

Date: 2026-09-03  
Scope: Kubernetes manifests only; application code and production OCI image are unchanged.

## Problem

The original 0.9.0-1 Kubernetes manifest mounted seven separate PVCs below `/data` while the application container used `readOnlyRootFilesystem: true`. Full Import deliberately creates staging and rollback directories as siblings of the managed persistent directories, for example `/data/.cir-restore-stage-<token>-uploads`, so the staging directory must be writable and must live on the same filesystem as `/data/uploads` for atomic `os.replace()` promotion.

With separate subdirectory PVCs, `/data` itself remained on the read-only image filesystem and Full Import failed during staging with `OSError: [Errno 30] Read-only file system`. Mounting an `emptyDir` only at `/data` would not be a valid fix because staging and destination would then be on different filesystems, breaking atomic rename with a possible `EXDEV`/cross-device error.

## Resolution

The shipped Kubernetes manifests now use one PVC, `cir-data`, mounted at `/data`. All managed paths (`uploads`, `logo`, `form_templates`, `sso_logos`, `ssl`, `backups`, `ai_chatbot_docs`) are subdirectories on the same persistent filesystem. `readOnlyRootFilesystem: true` remains enabled; only `/data` and `/tmp` are writable mounts.

The default PVC requests `ReadWriteMany` because the supplied Deployment has two replicas. Clusters without RWX storage should either provide equivalent shared storage or run CIR with one replica and adapt the PVC to `ReadWriteOnce`.

## Existing deployments using the former seven-PVC layout

Do not delete the old claims before copying their contents. Scale CIR to zero, create `cir-data`, copy each old claim into the corresponding `/data/...` subdirectory, verify ownership UID/GID 10001, then deploy the updated manifest. `k8s/migrate-separated-pvcs-to-cir-data.example.yaml` is provided as an example migration Job and is intentionally not included in Kustomize.

For a fresh 0.9.0-1 installation receiving a Full Import from 0.8.0, simply deploy with the new `cir-data` layout before running the import.

---
