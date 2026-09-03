# Migrazione da Cybersecurity Incident Registry 0.8.0 a >= 0.9.0

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
  newTag: "0.9.0-1"
```

Se si usa un repository privato, modificare `newName`; se si usa una release successiva >= 0.9.0, modificare `newTag`. In produzione è preferibile promuovere un digest immutabile nel sistema di deployment/GitOps.

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

La 0.9.x monta PVC separati per upload, logo, template, loghi SSO, certificati, backup e knowledge base AI. Prima dell'upgrade verificare che i PVC esistenti della 0.8.0 siano riutilizzati per i dati già presenti e creare soltanto quelli mancanti. Non puntare accidentalmente i nuovi Deployment a PVC vuoti se si devono preservare i dati esistenti.

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

Le modifiche funzionali e di sicurezza cumulative della release sono descritte in `RELEASE_NOTES_0.9.0-1.md`.
