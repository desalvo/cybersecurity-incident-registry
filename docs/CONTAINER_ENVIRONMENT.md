# Variabili di ambiente e gestione del container

Questa guida descrive le variabili di ambiente usate dal container dell'applicazione, i volumi persistenti da mantenere e le operazioni essenziali di gestione. Prima dell'avvio in produzione copiare `.env.example` in `.env`, sostituire tutti i segreti e verificare che i percorsi sotto `/data` siano montati su storage persistente.

## Avvio rapido con Docker Compose

```bash
cp .env.example .env
# modificare POSTGRES_PASSWORD, DATABASE_URL, SECRET_KEY e ADMIN_INITIAL_PASSWORD
docker compose build --no-cache
docker compose up -d
```

Controlli utili:

```bash
docker compose ps
docker compose logs -f web
docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Per arrestare l'applicazione senza cancellare i dati:

```bash
docker compose down
```

Per rimuovere anche i volumi, operazione distruttiva da usare solo su ambienti di test:

```bash
docker compose down -v
```

## Variabili obbligatorie in produzione

| Variabile | Uso | Note operative |
|---|---|---|
| `DATABASE_URL` | Stringa SQLAlchemy per il database applicativo. | In produzione deve puntare a PostgreSQL, ad esempio `postgresql+psycopg2://utente:password@db:5432/incidents`. Con `CIR_PRODUCTION=1` SQLite viene rifiutato. |
| `SECRET_KEY` | Chiave segreta Flask per sessioni, CSRF e firme. | Deve essere casuale e lunga almeno 32 caratteri. Generare un valore, ad esempio, con `openssl rand -hex 32`. Cambiarla invalida le sessioni esistenti. |
| `ADMIN_INITIAL_PASSWORD` | Password temporanea dell'utente locale `admin` alla prima inizializzazione. | Viene usata solo se l'utente `admin` non esiste ancora. Dopo il primo accesso va cambiata dall'interfaccia. In produzione non può essere debole. |
| `CIR_PRODUCTION` | Abilita i controlli production-ready. | Impostare a `1` in produzione. Attiva il fail-fast su segreti deboli, password admin deboli e database SQLite. |

## Variabili database PostgreSQL del servizio Compose

| Variabile | Uso | Note operative |
|---|---|---|
| `POSTGRES_DB` | Nome del database creato dal container PostgreSQL. | Default `incidents`. Deve essere coerente con `DATABASE_URL`. |
| `POSTGRES_USER` | Utente PostgreSQL creato dal container. | Default `incidents`. Deve essere coerente con `DATABASE_URL`. |
| `POSTGRES_PASSWORD` | Password dell'utente PostgreSQL. | Obbligatoria nel `docker-compose.yml`. Usare una password lunga e non riutilizzata. |

Queste tre variabili sono lette dal container `db`. L'applicazione `web` usa invece `DATABASE_URL` per collegarsi al database.

## Variabili applicative e metadati

| Variabile | Default | Uso |
|---|---:|---|
| `APP_NAME` | `Cybersecurity Incident Registry` | Nome visualizzato in **Info → Applicazione**. |
| `APP_VERSION` | `0.2.1-16` | Versione applicativa visualizzata e propagata nei deploy. |
| `APP_BUILD` | `2026051901` | Numero build visualizzato. |
| `APP_AUTHOR` | `Alessandro De Salvo` | Autore visualizzato. |
| `APP_AUTHOR_EMAIL` | `Alessandro.DeSalvo@roma1.infn.it` | E-mail autore visualizzata. |
| `ADMIN_EMAIL` | `admin@example.local` | E-mail assegnata all'admin bootstrap se l'utente viene creato al primo avvio. |

## Variabili di storage persistente

| Variabile | Default container | Contenuto | Volume/PVC consigliato |
|---|---|---|---|
| `UPLOAD_DIR` | `/data/uploads` | Documenti caricati o allegati agli incidenti. | Volume/PVC persistente. |
| `LOGO_DIR` | `/data/logo` | Logo dell'applicazione configurabile. | Volume/PVC persistente. |
| `FORM_TEMPLATE_DIR` | `/data/form_templates` | Template PDF caricati per la generazione moduli. | Volume/PVC persistente. |
| `SSO_LOGO_DIR` | `/data/sso_logos` | Loghi condivisi dei profili SSO/OAuth2 caricati da interfaccia. | Volume/PVC persistente. |
| `SSL_DIR` | `/data/ssl` | Certificati HTTPS caricati o attivati dall'applicazione. | Volume/PVC persistente e protetto. |

I percorsi sotto `/data` non devono restare effimeri in produzione. Nel `docker-compose.yml` sono montati come volumi nominati; nei manifest Kubernetes sono montati tramite PVC. Backup e restore devono includere database PostgreSQL e tutti i volumi persistenti.

## Variabili di sicurezza HTTP e upload

| Variabile | Default | Uso |
|---|---:|---|
| `SESSION_COOKIE_SECURE` | `0` | Impostare a `1` quando l'applicazione è servita via HTTPS o dietro reverse proxy HTTPS. Con `CIR_PRODUCTION=1` i cookie sicuri sono forzati. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Policy SameSite del cookie di sessione. |
| `REMEMBER_COOKIE_SAMESITE` | `Lax` | Policy SameSite del cookie “remember me”. |
| `CIR_FORCE_HSTS` | `0` | Impostare a `1` per inviare HSTS anche quando Flask non vede direttamente una richiesta HTTPS, ad esempio dietro reverse proxy TLS. |
| `MAX_CONTENT_LENGTH` | `26214400` | Limite globale upload in byte, default 25 MiB. |
| `FLASK_ENV` | non impostata | Se vale `production`, viene trattata come produzione anche senza `CIR_PRODUCTION=1`. |

## Scheduler notifiche e promemoria

| Variabile | Default | Uso |
|---|---:|---|
| `CIR_ENABLE_DEADLINE_SCHEDULER` | `1` | Abilita lo scheduler interno per notifiche deadline e promemoria. Impostare a `0`, `false` o `no` per disabilitarlo. |
| `CIR_DEADLINE_SCHEDULER_POLL_SECONDS` | `60` | Intervallo di controllo dello scheduler, minimo effettivo 30 secondi. |

Con PostgreSQL lo scheduler usa advisory lock per evitare esecuzioni duplicate con più worker Gunicorn o più repliche Kubernetes.

## Variabili HTTP, HTTPS e Gunicorn

| Variabile | Default | Uso |
|---|---:|---|
| `PORT` | `8000` | Porta HTTP interna del container. |
| `WEB_CONCURRENCY` | `1` | Numero worker Gunicorn per il listener HTTP. |
| `GUNICORN_THREADS` | `4` | Thread per worker Gunicorn. |
| `GUNICORN_TIMEOUT` | `180` | Timeout richieste Gunicorn in secondi. |
| `SSL_ENABLED` | `0` | Abilita il listener HTTPS interno se vale `1`, `true`, `yes` o `on`, oppure se esiste il marker `$SSL_DIR/enabled`. |
| `SSL_PORT` | `8443` | Porta HTTPS interna del container. |
| `WEB_CONCURRENCY_SSL` | valore di `WEB_CONCURRENCY` | Numero worker per il listener HTTPS. |
| `SSL_CERT_FILE` | `$SSL_DIR/current.crt` | Certificato usato dal listener HTTPS interno. |
| `SSL_KEY_FILE` | `$SSL_DIR/current.key` | Chiave privata usata dal listener HTTPS interno. |

L'entrypoint avvia sempre il listener HTTP. Il listener HTTPS viene avviato o fermato dinamicamente quando `SSL_ENABLED` o il marker `$SSL_DIR/enabled` indicano l'abilitazione e quando certificato e chiave sono leggibili.

## Variabili runtime dell'immagine

Le seguenti variabili sono impostate dal Dockerfile per rendere il runtime prevedibile e non richiedono modifiche nella normale gestione:

| Variabile | Valore | Uso |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE` | `1` | Evita la scrittura di file `.pyc`. |
| `PYTHONUNBUFFERED` | `1` | Scrive log Python senza buffering, utile per `docker logs`. |
| `PIP_NO_CACHE_DIR` | `1` | Evita cache pip nell'immagine. |
| `PIP_DISABLE_PIP_VERSION_CHECK` | `1` | Disabilita il controllo versione pip in build. |
| `DEBIAN_FRONTEND` | `noninteractive` | Evita prompt interattivi durante il build. |

## Gestione dei volumi e backup

Elementi da salvare regolarmente:

1. dump PostgreSQL del database applicativo;
2. volume `uploads` o PVC `cir-uploads`;
3. volume `logo`;
4. volume `form_templates` o PVC `cir-form-templates`;
5. volume `sso_logos` o PVC `cir-sso-logos`;
6. volume `ssl` o PVC `cir-ssl-certs`, se il listener HTTPS interno è usato.

Esempio dump con Docker Compose:

```bash
docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-incidents.sql
```

## Aggiornamento del container

Procedura consigliata:

```bash
docker compose pull || true
docker compose build --no-cache
docker compose up -d
```

Prima dell'aggiornamento eseguire un backup del database e dei volumi. Le migrazioni leggere dell'applicazione sono idempotenti e vengono eseguite all'avvio, ma non sostituiscono una procedura di backup.

## Kubernetes

Nei manifest Kubernetes i segreti sono letti da `cir-secrets`:

- `database-url` → `DATABASE_URL`;
- `secret-key` → `SECRET_KEY`;
- `admin-initial-password` → `ADMIN_INITIAL_PASSWORD`.

Le aree persistenti sono montate tramite PVC:

- `cir-uploads` su `/data/uploads`;
- `cir-form-templates` su `/data/form_templates`;
- `cir-sso-logos` su `/data/sso_logos`;
- `cir-ssl-certs` su `/data/ssl`.

In deployment multi-replica mantenere PostgreSQL come database e lasciare attivo il lock scheduler. Se lo scheduler deve essere eseguito da un solo componente esterno, impostare `CIR_ENABLE_DEADLINE_SCHEDULER=0` sui pod web.


## Backup da container
La variabile `BACKUP_DIR`, default `/data/backups`, identifica la destinazione locale POSIX usata dalla funzione **Admin → Backup** quando la destinazione è locale. Montare questo path su volume persistente o PVC. La funzione consente backup on-demand scaricabili, backup locali, destinazioni S3/compatibili e schedulazione cron-like. I backup schedulati sono disabilitati per default e devono essere abilitati esplicitamente dall’amministratore. Per S3 è richiesta la libreria opzionale `boto3` nell’immagine o in un’immagine derivata.
