# Variabili di ambiente e gestione del container

Questa guida descrive le variabili di ambiente usate dal container dell'applicazione, i volumi persistenti da mantenere e le operazioni essenziali di gestione. Prima dell'avvio in produzione copiare `.env.example` in `.env`, sostituire tutti i segreti e verificare che i percorsi sotto `/data` siano montati su storage persistente.

## Avvio rapido con Docker Compose

```bash
cp .env.example .env
# modificare POSTGRES_PASSWORD, DATABASE_URL, SECRET_KEY e ADMIN_INITIAL_PASSWORD
# default: usa l'immagine pubblicata desalvo/cybersecurity-incident-registry:latest
docker compose pull
docker compose up -d

# alternativa: build locale dell'immagine dal sorgente
docker compose -f docker-compose.yml -f docker-compose.build.yml build --no-cache web
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d
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


## Permessi dell'entrypoint Docker

Il container usa `/app/docker-entrypoint.sh` come comando di avvio. Il Dockerfile esegue sempre `chmod 0755 /app/docker-entrypoint.sh` durante la build. L'entrypoint parte come root solo per creare e correggere proprietà/permessi dei volumi persistenti montati sotto `/data`, copia nei volumi appena creati gli asset predefiniti come i loghi SSO e i template di esempio, quindi rientra come utente non privilegiato `appuser` tramite `gosu`. Questo evita errori di startup su volumi Docker appena creati, che normalmente arrivano montati con proprietario root. Se un bind mount host non consente `chown`/`chmod`, `CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE=1` permette l'avvio come root con warning; impostarlo a `0` per fallire esplicitamente e correggere i permessi host.

Se si modifica manualmente lo script, verificare prima del rilascio:

```bash
ls -l docker-entrypoint.sh
test -x docker-entrypoint.sh
pytest tests/test_container_packaging.py
```

## Variabili obbligatorie in produzione

| Variabile | Uso | Note operative |
|---|---|---|
| `DATABASE_URL` | Stringa SQLAlchemy per il database applicativo. | In produzione deve puntare a PostgreSQL, ad esempio `postgresql+psycopg2://utente:password@db:5432/incidents`. Con `CIR_PRODUCTION=1` SQLite viene rifiutato. |
| `SECRET_KEY` | Chiave segreta Flask per sessioni, CSRF e firme. | Deve essere casuale e lunga almeno 32 caratteri. Generare un valore, ad esempio, con `openssl rand -hex 32`. Cambiarla invalida le sessioni esistenti. |
| `ADMIN_INITIAL_PASSWORD` | Password temporanea dell'utente locale `admin` alla prima inizializzazione. | Viene usata solo se l'utente `admin` non esiste ancora. Dopo il primo accesso va cambiata dall'interfaccia. In produzione non può essere debole. Il bootstrap accetta valori copiati con virgolette esterne o CRLF e rimuove solo questi artefatti. |
| `CIR_PRODUCTION` | Abilita i controlli production-ready. | Impostare a `1` in produzione. Attiva il fail-fast su segreti deboli, password admin deboli, database SQLite e impedisce la disabilitazione del CSRF. |


## Opzioni di sicurezza locali/test

| Variabile | Default | Uso |
|---|---:|---|
| `CIR_DISABLE_CSRF` | `0` | Disabilita la validazione CSRF solo per sviluppo locale o test automatizzati. Con `CIR_PRODUCTION=1` l'applicazione rifiuta l'avvio se questa variabile è impostata a un valore vero. Non usare mai in produzione. |


## Immagine Docker, build locale e utente runtime

Compose usa di default `CIR_IMAGE=desalvo/cybersecurity-incident-registry:latest`. Per costruire localmente usare l'override `docker-compose.build.yml`. Le variabili `APP_UID` e `APP_GID`, default `10001`, definiscono l'utente proprietario dei volumi preparati dall'entrypoint. Cambiarle solo se l'infrastruttura richiede UID/GID specifici. `CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE`, default `1`, evita crash di startup su bind mount host non correggibili; in installazioni hardened può essere impostato a `0` per richiedere permessi corretti prima dell'avvio.

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
| `APP_VERSION` | `0.7.0-7` | Versione applicativa visualizzata e propagata nei deploy. |
| `APP_BUILD` | `20260608` | Numero build visualizzato. |
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
| `BACKUP_DIR` | `/data/backups` | Backup locali generati dall'applicazione. | Volume/PVC persistente. |

I percorsi sotto `/data` non devono restare effimeri in produzione. Nel `docker-compose.yml` sono montati come volumi nominati; nei manifest Kubernetes sono montati tramite PVC. All'avvio Docker l'entrypoint corregge i permessi dei volumi per UID/GID `10001`; in Kubernetes un initContainer `prepare-persistent-volumes` e `fsGroup: 10001` preparano i PVC, inclusi loghi SSO e documenti AI, prima dell'avvio del container applicativo non-root. Backup e restore devono includere database PostgreSQL e tutti i volumi persistenti.

## Variabili di sicurezza HTTP e upload

| Variabile | Default | Uso |
|---|---:|---|
| `SESSION_COOKIE_SECURE` | `0` | Impostare a `1` quando l'applicazione è servita via HTTPS o dietro reverse proxy HTTPS. Con `SESSION_COOKIE_SECURE=0` i cookie restano utilizzabili su `http://localhost:8000` e la login protetta da CSRF funziona anche con `CIR_PRODUCTION=1`. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Policy SameSite del cookie di sessione. |
| `REMEMBER_COOKIE_SAMESITE` | `Lax` | Policy SameSite del cookie “remember me”. |
| `CIR_FORCE_HSTS` | `0` | Impostare a `1` per inviare HSTS anche quando Flask non vede direttamente una richiesta HTTPS, ad esempio dietro reverse proxy TLS. |
| `MAX_CONTENT_LENGTH` | `26214400` | Limite globale upload in byte, default 25 MiB. Il valore iniziale deriva da `MAX_CONTENT_LENGTH`, ma può essere modificato da Admin → Altre configurazioni → Dimensione massima upload (MB). L'app allinea anche `MAX_FORM_MEMORY_SIZE` allo stesso valore per evitare 413 su form multipart con campi grandi; gli import workflow usano inoltre un token temporaneo lato server dopo la preview. Allineare reverse proxy e ingress Kubernetes allo stesso valore o a un valore superiore. |
| `LOGIN_LOCKOUT_THRESHOLD` | `5` | Numero di tentativi falliti, per coppia IP/username, dopo il quale scatta il blocco server-side. |
| `LOGIN_LOCKOUT_WINDOW_SECONDS` | `900` | Finestra temporale in secondi entro cui contare i tentativi falliti. |
| `LOGIN_LOCKOUT_STEP_SECONDS` | `60` | Incremento progressivo del blocco temporaneo dopo il superamento della soglia. |
| `LOGIN_LOCKOUT_MAX_SECONDS` | `900` | Durata massima del blocco temporaneo. |
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
| `CIR_SSL_CERT_FILE` | vuoto | Percorso esplicito del certificato gestito dall'utente per il listener HTTPS interno. |
| `CIR_SSL_KEY_FILE` | vuoto | Percorso esplicito della chiave privata gestita dall'utente per il listener HTTPS interno. |
| `SSL_CERT_FILE` | `$SSL_DIR/current.crt` | Compatibilità: usato come certificato del listener solo se anche `SSL_KEY_FILE` è impostato, per evitare conflitti con CA bundle di sistema. |
| `SSL_KEY_FILE` | `$SSL_DIR/current.key` | Compatibilità: usato come chiave del listener solo se anche `SSL_CERT_FILE` è impostato. |

L'entrypoint avvia sempre il listener HTTP. Il listener HTTPS viene avviato o fermato dinamicamente quando `SSL_ENABLED` o il marker `$SSL_DIR/enabled` indicano l'abilitazione. Se i percorsi `CIR_SSL_CERT_FILE`/`CIR_SSL_KEY_FILE` oppure la coppia compatibile `SSL_CERT_FILE`/`SSL_KEY_FILE` non sono impostati e non è stato caricato un certificato da interfaccia, l'entrypoint genera in `$SSL_DIR/current.crt` e `$SSL_DIR/current.key` un certificato host self-signed e lo rigenera quando manca o non è valido. I certificati caricati da interfaccia o definiti esplicitamente via ambiente hanno sempre precedenza e non vengono sovrascritti automaticamente.

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

Procedura consigliata con immagine pubblicata:

```bash
docker compose pull
docker compose up -d
```

Procedura consigliata con build locale:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml build --no-cache web
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d
```

Prima dell'aggiornamento eseguire un backup del database e dei volumi. Le migrazioni leggere dell'applicazione sono idempotenti e vengono eseguite all'avvio, ma non sostituiscono una procedura di backup.

## Kubernetes

Nei manifest Kubernetes i segreti sono letti da `cir-secrets`:

- `database-url` → `DATABASE_URL`;
- `secret-key` → `SECRET_KEY`;
- `admin-initial-password` → `ADMIN_INITIAL_PASSWORD`.

Le aree persistenti sono montate tramite PVC:

- `cir-uploads` su `/data/uploads`;
- `cir-logo` su `/data/logo`;
- `cir-form-templates` su `/data/form_templates`;
- `cir-sso-logos` su `/data/sso_logos`;
- `cir-ssl-certs` su `/data/ssl`;
- `cir-backups` su `/data/backups`.

Il deployment usa `desalvo/cybersecurity-incident-registry:latest` con `imagePullPolicy: IfNotPresent`. Per usare una build locale in cluster di test, costruire/taggare la stessa immagine e caricarla nel cluster, oppure modificare il tag con Kustomize (`k8s/kustomization.yaml`). La variabile `CIR_DISABLE_CSRF` è presente nei manifest e deve restare `0` in produzione.

In deployment multi-replica mantenere PostgreSQL come database e lasciare attivo il lock scheduler. Se lo scheduler deve essere eseguito da un solo componente esterno, impostare `CIR_ENABLE_DEADLINE_SCHEDULER=0` sui pod web.


## Backup da container
La variabile `BACKUP_DIR`, default `/data/backups`, identifica la destinazione locale POSIX usata dalla funzione **Admin → Backup** quando la destinazione è locale. Montare questo path su volume persistente o PVC. La funzione consente backup on-demand scaricabili, backup locali, destinazioni S3/compatibili e schedulazione cron-like. I backup schedulati sono disabilitati per default e devono essere abilitati esplicitamente dall’amministratore. Per S3 è richiesta la libreria opzionale `boto3` nell’immagine o in un’immagine derivata.
