# Documentazione progettuale

## Baseline progettuale 0.2.1 - build 2026051901

La documentazione progettuale descrive lo stato corrente dell’applicazione. I metadati tecnici della release sono mantenuti nella pagina Info, nelle Note di rilascio e nel CHANGELOG, mentre le guide operative restano prive di banner di versione.

## Aggiornamento 0.2.1 - Pulsanti data/ora locale e azioni notifica

La pagina di creazione incidente e la pagina di dettaglio incidente espongono pulsanti rapidi accanto ai campi separati `start_date`, `start_time`, `end_date` ed `end_time`. Il JavaScript dei template calcola il momento corrente usando la timezone applicativa configurata (`application_timezone`) tramite `Intl.DateTimeFormat`, con fallback alla timezone del browser. La route `incident_new` passa ora il nome del fuso al template come avviene già per `incident_detail`.

Le azioni automatiche generate dall'invio di notifiche manuali sono create tramite `add_notification_action_safely()` con `application_now()` invece di `datetime.utcnow()`. In questo modo gli eventi registrati nella timeline dell'incidente sono espressi nella timezone locale applicativa, coerentemente con gli input HTML e con la documentazione utente.

## Aggiornamento 0.2.1 - Workflow con dipendenze da notifiche e percorso guidato

`IncidentWorkflowStep` supporta i campi `requires_notification` e `required_notification_type`. Quando uno step è configurato come dipendente da una notifica, `incident_workflow_status()` calcola se una azione di notifica compatibile è già presente nell’incidente, usando le label azione associate ai template di notifica del tipo richiesto e la label fallback del tipo notifica.

Nel dettaglio incidente gli step mancanti con dipendenza da notifica espongono al frontend l’URL della notifica, lo stato dei documenti richiesti e la sezione di destinazione. Il click sullo step non preseleziona più direttamente l’azione se la notifica manca: apre la preview della notifica specifica solo quando i documenti attesi sono disponibili; in caso contrario mostra un avviso e scorre alla generazione moduli o al tagging documenti. L’inserimento manuale dell’azione corrispondente resta bloccato lato server finché la notifica richiesta non risulta presente tra le azioni.

# Cybersecurity Incident Registry — documentazione progettuale logica

## 1. Scopo del documento

Questo documento descrive la logica applicativa, il modello dati, i flussi operativi, le autorizzazioni, le integrazioni e i requisiti tecnici dell'applicazione **Cybersecurity Incident Registry** nella sua forma corrente.

La sezione finale contiene una descrizione testuale completa, pensata per poter riprodurre da capo l'applicazione con ChatGPT o con un altro sistema di generazione codice, mantenendo tutte le funzionalità implementate fino alla build corrente.

## 2. Informazioni applicative

- Nome applicazione: Cybersecurity Incident Registry
- Versione: 0.2.1
- Build: 2026051901
- Autore: Alessandro De Salvo <Alessandro.DeSalvo@roma1.infn.it>
- Backend: Flask con server di produzione Gunicorn
## Baseline progettuale 0.2.1 - build 2026051901

La baseline 0.2.1 stabilizza l'applicazione come registro operativo bilingue per incidenti informatici. Include:

- interfaccia e documentazione in italiano e inglese con selezione automatica da locale browser e override amministrativo;
- menu Aiuto riorganizzato in Documentazione utente, Documentazione amministrativa e Note di rilascio, con PDF scaricabili dalle pagine relative;
- gestione completa dell'audit con dettagli sintetici, anti-flooding, conteggio occorrenze, retention temporale, limite massimo record, purge manuale/automatico ed export CSV;
- scheduler notifiche deadline con pianificazione cron o a intervalli, slot ancorati alla mezzanotte nel fuso applicativo, deduplica per finestra di schedule, audit degli slot utili e lock distribuito PostgreSQL per deployment multi-replica;
- promemoria puntuali per incidente indirizzati al personale associato con CC opzionali e recupero post-riavvio;
- report PDF incidenti con layout professionale, indice, numerazione pagine, loghi, orari con secondi interi e durata incidente quando disponibile;
- profili SSO/OAuth2 multipli, callback HTTPS, pulsanti di login grigio chiaro, repository condiviso loghi SSO persistente e configurabile via `SSO_LOGO_DIR`, con Google/Facebook/Apple predefiniti, upload, selezione, rimozione ed export/import;
- HTTPS/SSL opzionale su porta 8443, non bloccante per l'accesso HTTP su porta 8000, configurabile da ambiente e da interfaccia Admin; baseline sicurezza produzione con CSRF, header HTTP, cookie sicuri e controllo fail-fast dei segreti;
- miglioramenti mobile per i promemoria schedulati e impaginazione più robusta della documentazione online/PDF.

- Database: PostgreSQL 18.4
- ORM: SQLAlchemy / Flask-SQLAlchemy
- Autenticazione: account locali, LDAP configurabile e SSO/OAuth2/OpenID Connect configurabile
- Container: Docker basato su Debian Trixie
- Orchestrazione: manifest Kubernetes inclusi

## 3. Architettura logica

L'applicazione è una web application server-side basata su Flask. Le pagine sono renderizzate tramite template Jinja2, con CSS e JavaScript statici per menu accessibili, interfaccia mobile e drag & drop.

Componenti principali:

1. **Modulo autenticazione**: login locale, LDAP e SSO/OAuth2/OpenID Connect, gestione password locali, ruoli e sessioni.
2. **Modulo incidenti**: creazione, visualizzazione, modifica, ricerca, clonazione, cancellazione e report degli incidenti.
3. **Modulo configurazioni**: liste configurabili, logo, LDAP, SSO, SMTP, utenti locali, utenti LDAP e utenti SSO importati.
4. **Modulo notifiche**: tipi di notifica, template CRUD, anteprima, invio mail, allegati condizionali e registrazione automatica delle azioni.
5. **Modulo reportistica**: PDF per incidente, PDF statistiche, CSV, export/import completo.
6. **Modulo documentazione**: guida estesa ricercabile e download PDF della documentazione.

## 4. Modello dati principale

### 4.1 Utenti

Gli utenti possono essere locali, LDAP o SSO. L’identità applicativa non è il solo `username`, ma la coppia `username + auth_provider`. Questo consente di avere account distinti con lo stesso username su backend diversi, ad esempio `local`, `ldap`, `sso:google` o `sso:ente`. Gli utenti SSO sono identificati tramite claim configurabili restituiti dal provider OAuth2/OpenID Connect e associati al backend tecnico del profilo SSO.

Campi logici:

- username
- password_hash, solo per utenti locali
- nome, corrispondente al `cn` LDAP oppure al nome locale
- email
- ruolo
- flag `is_ldap`

Ruoli previsti:

- `admin`: accesso completo, incluse funzioni amministrative
- `writer`: lettura e scrittura sugli incidenti
- `reader`: sola lettura su tutti gli incidenti
- `operator`: sola lettura sugli incidenti creati dall'utente stesso
- `disabled`: nessun accesso operativo

L'utente locale `admin` viene creato automaticamente solo se assente. La password iniziale è configurabile con variabile d'ambiente; dopo il primo avvio non deve essere reimpostata automaticamente ai riavvii.

### 4.2 Incidenti

### Help contestuale nella scheda incidente

La pagina di modifica/visualizzazione del singolo incidente mostra icone informative accanto ai campi principali della scheda. I tooltip sono disponibili anche da tastiera tramite focus e chiariscono il significato operativo di nome, riferimento, destinatario, descrizione, gravità, stato, data/ora inizio, data/ora fine, dati personali, silenziamento notifiche deadline, numero interessati e volume dati.

Questi testi sono parte della documentazione procedurale perché distinguono esplicitamente il periodo della violazione dalla data/ora di venuta a conoscenza, gestita tramite l’azione di informazione iniziale, e dalla conclusione amministrativa dell’incidente.

Ogni incidente registra:

- creatore: nome ed email presi automaticamente dall'utente loggato e non modificabili
- nome incidente
- riferimento opzionale
- descrizione
- gravità
- tipi di dati interessati, multipli
- flag dati personali sì/no
- data e ora di inizio
- data e ora di fine opzionale
- categorie multiple
- personale coinvolto opzionale, multiplo
- stato: aperto, in lavorazione, chiuso
- documenti allegati
- azioni intraprese

La pagina principale mostra, in ordine:

1. nome incidente
2. intervallo data/ora di inizio e fine
3. nome compilatore senza email
4. personale coinvolto
5. stato
6. durata, calcolata come tempo tra la prima azione registrata e la conclusione dell'incidente

Tutte le colonne sono ordinabili. In cima alla lista viene mostrato il numero totale degli incidenti filtrati o, in assenza di ricerca, il totale complessivo visibile all'utente.

### 4.3 Azioni

Ogni azione appartiene a un incidente e contiene:

- data e ora
- descrizione opzionale
- nome della persona che ha effettuato l'azione
- label azione
- allegati multipli opzionali

Il campo persona è precompilato con il nome dell'utente loggato ma può essere modificato. È possibile modificare o cancellare le azioni, se l'utente ha permessi di scrittura. Le azioni sono ordinate cronologicamente.

Le notifiche generano automaticamente un'azione associata alla label configurata nel template usato. L'azione automatica include nella descrizione mittente, destinatari e CC. Inoltre viene generato e allegato all'azione un PDF con il testo della mail inviata.

### 4.4 Documenti

Gli incidenti supportano allegati multipli. Ogni documento conserva:

- nome file originale
- nome file salvato internamente
- data di caricamento, visualizzata nella sezione Documenti della pagina incidente
- riferimento all'incidente

I documenti possono essere scaricati o cancellati. Se il placeholder `%DOCUMENTS%` è usato in un template di notifica, in fase di invio l'utente deve selezionare quali documenti allegare. L'invio viene impedito se non esistono documenti o non ne viene selezionato alcuno.

### 4.5 Liste configurabili

Le liste configurabili sono gestite da label tipizzate. Tipi principali:

- gravità
- categorie
- dati interessati
- label azioni
- personale

Le label sono raggruppate per categoria/tipo nelle pagine di amministrazione e nel drag & drop. Nella pagina `Admin -> Liste configurabili` le sezioni sono rese in sequenza verticale, una sotto l'altra, invece che in colonne affiancate, per massimizzare la larghezza disponibile ai campi modificabili come nome, descrizione e tempo massimo. L'aggiunta avviene inserendo il nome della label nella sezione della categoria corretta. La cancellazione rimuove anche i riferimenti esistenti negli incidenti quando previsto. Per le label azioni, oltre al tempo massimo, è disponibile il campo `default_exportable`, gestito in UI come “Esportabile per default”, che determina il valore iniziale del flag `Action.exportable` quando viene inserita una nuova azione con quella label.

La gestione del personale è analoga alle altre label per il drag & drop negli incidenti, ma l'anagrafica del personale richiede solo nome ed email e non mostra campi Categoria/Gruppo. Anche le raccomandazioni configurate da Admin -> Raccomandazioni sono selezionate nelle pagine incidente con il medesimo meccanismo drag & drop: sorgente “Raccomandazioni disponibili”, destinazione “Raccomandazioni selezionate” e rimozione tramite clic sulla chip già selezionata.

### 4.6 Impostazioni

La tabella impostazioni è a chiave primaria testuale. Tutte le operazioni di seed devono essere idempotenti, tramite get-or-create/upsert, per evitare errori `duplicate key value violates unique constraint`.

Impostazioni principali:

- LDAP
- SMTP/notifiche
- indirizzi CSIRT e DPO
- logo applicativo
- dati informativi applicazione

## 5. Autenticazione e sicurezza applicativa

### 5.1 Login locale

Gli utenti locali accedono tramite username/password. Le password devono essere hashate con un algoritmo che non soffra del limite bcrypt a 72 byte, ad esempio PBKDF2-SHA256. Hash bcrypt legacy possono essere gestiti solo in compatibilità, senza generare crash.

Il cambio password è disponibile nel menu Impostazioni solo per utenti locali, quindi non per utenti LDAP o SSO. La form richiede due volte la nuova password.

### 5.2 Login LDAP

L'LDAP è configurabile da interfaccia amministrativa. Parametri previsti:

- server URI
- base DN
- bind DN e password opzionali
- filtro utenti
- attributi uid, cn, email

La configurazione LDAP include:

- test comunicazione verso il server
- ricerca utente tramite uid
- visualizzazione degli attributi ottenuti

Gli utenti LDAP che effettuano login per la prima volta e non sono già presenti nel database vengono creati con ruolo `disabled`.


### 5.3 Login SSO / OAuth2 / OpenID Connect

Il login SSO è configurabile dal menu **Admin → SSO**, accessibile solo all’utente `admin` e agli utenti con ruolo `admin`. Il login locale e LDAP restano disponibili anche quando SSO è abilitato.

Parametri configurabili:

- abilitazione del login SSO;
- nome provider mostrato nella pagina di login;
- authorization endpoint;
- token endpoint;
- userinfo endpoint;
- client ID;
- client secret;
- scope OAuth2/OIDC, con valore suggerito `openid email profile`;
- claim username, email, nome e soggetto univoco;
- creazione automatica degli utenti SSO;
- ruolo predefinito dei nuovi utenti, con default `disabled`.

La pagina mostra il redirect URI assoluto da registrare sul provider. Include inoltre un meccanismo di controllo configurazione accessibile con il pulsante `Controlla configurazione`. Il controllo usa i valori correnti della form, anche non ancora salvati, e richiama la funzione server-side `sso_test_configuration`: verifica parametri obbligatori, presenza di scope e claim principali, raggiungibilità dell'authorization endpoint, del token endpoint e dello UserInfo endpoint. Il controllo è non distruttivo, non crea utenti, non salva implicitamente i parametri e non richiede credenziali dell'utente finale. Per lo UserInfo endpoint considera accettabili anche risposte HTTP 401/403 perché, durante il test tecnico, non viene inviato un access token reale. La pagina mostra inoltre l'URL di autorizzazione generata e, quando la configurazione minima è abilitata, il link `Avvia test login interattivo`, che esegue il normale redirect OAuth2 verso il provider.

Il flusso di login implementa Authorization Code: generazione dello `state`, redirect al provider, scambio del code sul token endpoint, chiamata allo UserInfo endpoint e creazione/aggiornamento dell’utente applicativo. Ogni profilo SSO usa un backend tecnico distinto nel formato `sso:<id profilo>`, quindi due provider diversi che restituiscono lo stesso username creano due utenti applicativi separati. Gli utenti SSO creati automaticamente vengono bloccati se il ruolo assegnato è `disabled`, finché un amministratore non li abilita da **Admin → Utenti**.

### 5.4 Autorizzazioni

Le route devono proteggere le funzioni lato server, non solo nascondere i pulsanti nell'interfaccia.

- Solo `admin` accede a menu Admin e Notifiche.
- Solo `admin` e utenti con ruolo `writer` vedono e usano pulsanti di creazione, modifica, cancellazione e upload.
- `reader` legge tutto senza modificare.
- `operator` legge solo gli incidenti creati da sé.
- `disabled` viene disconnesso o rediretto con messaggio di errore.

Per ogni oggetto cancellabile, la UI deve chiedere conferma prima di procedere.

### 5.5 Baseline di sicurezza produzione

La build 2026051901 aggiunge il modulo `app/security.py`, inizializzato da `create_app()` prima della registrazione delle blueprint. Il modulo applica una baseline production-ready senza introdurre dipendenze esterne obbligatorie:

- validazione CSRF per tutti i metodi mutativi (`POST`, `PUT`, `PATCH`, `DELETE`), con token per sessione e confronto costante tramite `secrets.compare_digest`;
- inserimento automatico server-side del campo nascosto `_csrf_token` in tutte le form HTML con `method=post`, così i template esistenti restano protetti senza affidarsi a JavaScript;
- supporto del token anche via header `X-CSRFToken`/`X-CSRF-Token` per eventuali chiamate AJAX future;
- header di sicurezza `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` e HSTS quando la richiesta è HTTPS o `CIR_FORCE_HSTS=1`;
- cookie di sessione e remember-cookie `HttpOnly`, `SameSite=Lax` e `Secure` quando `CIR_PRODUCTION=1` o `SESSION_COOKIE_SECURE=1`;
- limite upload globale tramite `MAX_CONTENT_LENGTH`, default 25 MiB;
- controllo fail-fast in produzione: con `CIR_PRODUCTION=1` vengono rifiutati `SECRET_KEY` deboli o troppo corti, `ADMIN_INITIAL_PASSWORD` deboli e database SQLite.

Il `docker-compose.yml` non contiene più segreti hardcoded. L'operatore deve copiare `.env.example` in `.env` e valorizzare password database, `DATABASE_URL`, `SECRET_KEY` e `ADMIN_INITIAL_PASSWORD`. I manifest Kubernetes continuano a leggere i segreti da `cir-secrets` e impostano `CIR_PRODUCTION=1` e `SESSION_COOKIE_SECURE=1`.

### 5.6 Scheduler in deployment multi-replica

Lo scheduler interno resta disabilitabile con `CIR_ENABLE_DEADLINE_SCHEDULER=0`, ma ora ogni ciclo automatico usa due livelli di lock:

1. lock di processo Python, per evitare sovrapposizioni nello stesso worker;
2. advisory lock PostgreSQL (`pg_try_advisory_lock`) con chiave applicativa costante, per evitare che più worker Gunicorn o più pod Kubernetes eseguano contemporaneamente notifiche deadline e promemoria specifici.

In ambienti non PostgreSQL resta attivo solo il lock di processo. La deduplica funzionale per incidente/slot e i record `deadline_notification_state` continuano a proteggere dagli invii ripetuti; il lock distribuito riduce il rischio operativo e il rumore audit in produzione scalata.


### 5.7 Storage persistente loghi SSO

I loghi condivisi dei profili SSO/OAuth2 non vengono più salvati in `app/static/sso`, perché tale directory appartiene all’immagine applicativa e può essere effimera nei container. La funzione `sso_logo_storage_dir()` usa ora `current_app.config['SSO_LOGO_DIR']`, valorizzata dalla variabile d’ambiente `SSO_LOGO_DIR`, con default `/data/sso_logos`.

La rotta `GET /sso-logos/<filename>` serve i loghi dallo storage persistente dopo validazione del nome file e dell’estensione. I profili continuano a memorizzare riferimenti logici nel formato `sso/<filename>` per mantenere compatibilità con configurazioni ed export esistenti; la UI converte tali riferimenti nell’URL servito dalla nuova rotta.

All’avvio i loghi predefiniti presenti nel pacchetto in `app/static/sso` vengono copiati nella directory persistente solo se mancanti. Il full export legge i loghi da `SSO_LOGO_DIR`; il full import ripristina i file nella stessa directory, accettando solo path sicuri nel formato `sso/<filename>`.

### Anteprima dei loghi caricati

Tutte le anteprime dei loghi SSO visualizzate in `Admin → SSO/OAuth2` devono usare la funzione `sso_logo_url(relative_path)`. Questa funzione genera URL sulla rotta `/sso-logos/<filename>`, servita da `sso_logo_asset()`, e non su `url_for('static', filename=...)`. La regola è necessaria perché i loghi caricati dagli amministratori sono salvati nello storage persistente `SSO_LOGO_DIR`, non nell’area statica dell’immagine applicativa. Le gallerie dello storage, la selezione del logo di profilo, la tabella dei profili e la pagina di login usano quindi lo stesso meccanismo di rendering per loghi predefiniti e loghi caricati da interfaccia.


Configurazione produzione:

- Docker Compose: volume nominato `sso_logos` montato su `/data/sso_logos` e variabile `SSO_LOGO_DIR`;
- Kubernetes: PVC `cir-sso-logos` montata su `/data/sso_logos`;
- `.env.example`: variabile `SSO_LOGO_DIR=/data/sso_logos`.


### 5.8 Variabili di ambiente e gestione container

La documentazione del pacchetto include ora una guida dedicata alla gestione runtime del container:

- `docs/CONTAINER_ENVIRONMENT.md` per l'italiano;
- `docs/CONTAINER_ENVIRONMENT_en.md` per l'inglese.

La guida cataloga tutte le variabili di ambiente effettivamente usate dall'applicazione, dal Dockerfile, dal `docker-compose.yml`, dall'entrypoint e dai manifest Kubernetes. Le variabili sono organizzate per area funzionale:

- database e segreti: `DATABASE_URL`, `SECRET_KEY`, `ADMIN_INITIAL_PASSWORD`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
- produzione e sicurezza HTTP: `CIR_PRODUCTION`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, `REMEMBER_COOKIE_SAMESITE`, `CIR_FORCE_HSTS`, `MAX_CONTENT_LENGTH`, `FLASK_ENV`;
- storage persistente: `UPLOAD_DIR`, `LOGO_DIR`, `FORM_TEMPLATE_DIR`, `SSO_LOGO_DIR`, `SSL_DIR`;
- listener HTTP/HTTPS e tuning Gunicorn: `PORT`, `WEB_CONCURRENCY`, `WEB_CONCURRENCY_SSL`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `SSL_ENABLED`, `SSL_PORT`, `SSL_CERT_FILE`, `SSL_KEY_FILE`;
- scheduler notifiche e promemoria: `CIR_ENABLE_DEADLINE_SCHEDULER`, `CIR_DEADLINE_SCHEDULER_POLL_SECONDS`;
- metadati applicativi: `APP_NAME`, `APP_VERSION`, `APP_BUILD`, `APP_AUTHOR`, `APP_AUTHOR_EMAIL`, `ADMIN_EMAIL`;
- variabili runtime dell'immagine: `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`, `PIP_NO_CACHE_DIR`, `PIP_DISABLE_PIP_VERSION_CHECK`, `DEBIAN_FRONTEND`.

La stessa descrizione è stata integrata nella documentazione amministrativa online come sezione autonoma, in modo che l'amministratore possa consultare direttamente dall'applicazione quali parametri usare per avvio, hardening, backup, HTTPS, scheduler e deploy Kubernetes.

Il file `.env.example` è stato ampliato per includere anche le variabili operative non segrete e i riferimenti alla guida. Il `docker-compose.yml` espone in modo esplicito i percorsi configurabili `UPLOAD_DIR`, `LOGO_DIR`, `FORM_TEMPLATE_DIR`, `SSO_LOGO_DIR` e `SSL_DIR`, montandoli sui volumi nominati corrispondenti. Questo consente di cambiare i mount point in fase di avvio del container senza modificare l'immagine.

Regola di produzione: un backup completo deve includere il dump PostgreSQL e tutti i volumi collegati alle directory persistenti. La rimozione dei volumi con `docker compose down -v` è esplicitamente documentata come operazione distruttiva e non ammessa per ambienti reali.

## 6. Interfaccia utente

### 6.1 Layout generale

La barra superiore contiene:

- logo, massimo 2 cm di altezza
- menu principali, senza voce dedicata a `Nuovo incidente`: la creazione resta disponibile tramite pulsante nella pagina principale
- nome dell'utente corrente all'estrema destra

Menu principali:

- Incidenti
- Report
- Export
- Admin, solo admin
- Notifiche, solo admin
- Impostazioni
- Info
- Aiuto

I menu devono essere accessibili:

- supporto tastiera
- focus visibile
- attributi ARIA
- contrasto adeguato
- dropdown leggibili anche in hover/focus
- z-index adeguato per evitare sovrapposizioni

### 6.2 Login

La pagina di login ha layout centrato, eventuale logo e non deve mostrare informazioni sul nome o password dell'amministratore di default.

Gli utenti non autenticati che accedono a pagine protette vengono rediretti alla login.

### 6.3 Mobile UI

L'interfaccia deve essere responsive:

- menu compatto su schermi piccoli
- lista incidenti trasformabile in schede
- form touch-friendly
- tabelle scrollabili o adattate

### 6.4 Drag & drop

Nei form degli incidenti, le label disponibili devono essere raggruppate per tipo/categoria e i campi destinazione devono essere adiacenti alle liste da cui si trascinano gli elementi.

Drag & drop richiesto per:

- categorie
- dati interessati
- label azioni ove applicabile
- personale coinvolto

## 7. Notifiche

### 7.1 Tipi di notifica

Il menu Notifiche, visibile solo agli admin, contiene la gestione dei tipi di notifica. Ogni tipo definisce:

- codice
- etichetta
- descrizione
- modalità destinatario: da impostazioni o manuale
- eventuale chiave impostazione destinatario
- eventuale chiave impostazione CC
- stato abilitato/disabilitato

Per CSIRT e DPO i destinatari sono presi dalle impostazioni. Per altri tipi di notifica il destinatario viene richiesto all'invio, salvo sia già presente nel campo della form.

### 7.2 Template di notifica

I template sono gestiti con CRUD completo:

- aggiunta da voce separata del menu Notifiche
- modifica
- cancellazione
- clonazione
- associazione a un tipo di notifica
- associazione a una label azione

I template aggiunti dall'utente non devono essere cancellati ai riavvii. Il bootstrap deve creare solo i template predefiniti mancanti.

Esempi di template devono essere forniti per:

- notifica all'utente
- notifica allo CSIRT
- notifica al DPO

### 7.3 Placeholder disponibili

Nel testo delle mail di notifica sono disponibili:

- `%DATA%`: tipo di dati interessati nell'incidente
- `%CATEGORIES%`: categorie dell'incidente
- `%PERSONAL_DATA%`: frase esplicativa sulla presenza di dati personali
- `%REPORT%`: report PDF automatico dell'incidente; se presente, il PDF viene allegato
- `%NAME%`: nome dell'incidente
- `%OPERATOR%`: nome dell'utente che invia la mail
- `%START%`: data e ora di inizio
- `%END%`: data e ora di fine, se disponibile
- `%DESCRIPTION%`: descrizione
- `%REFERENCE%`: riferimento
- `%CREATOR%`: creatore dell'incidente
- `%CREATOR_EMAIL%`: email del creatore
- `%DOCUMENTS%`: documenti allegati all'incidente; se presente, richiede selezione documenti
- `%STATUS%`: stato incidente
- `%ACTIONS%`: lista cronologica delle azioni con data e ora
- `%MEASURES_ADOPTED%`: lista delle contromisure adottate finora nell'incidente, calcolata dalla stessa origine dati del campo `measures_adopted` usato per la compilazione dei moduli
- `%INCIDENT_URL%`: link diretto all'incidente; nelle notifiche manuali/non schedulate il link viene inserito solo se questo placeholder è presente nel template
- `%SITE%`: nome della struttura dove si è verificato l'incidente, letto dalla configurazione **Admin → Struttura**
- `%STATISTICS%`: richiede l'allegato del report statistiche in PDF

La lista dei placeholder deve essere visibile in ogni pagina di configurazione template. I valori dei placeholder vengono normalizzati a testo prima della sostituzione: valori mancanti diventano stringa vuota, liste/tuple/set diventano righe separate da ritorno a capo e gli altri tipi vengono convertiti in stringa. Questa regola evita errori di rendering quando valori condivisi con i moduli, come `%MEASURES_ADOPTED%`, sono calcolati internamente come liste di righe.

### 7.4 Invio notifiche

Nella pagina di ciascun incidente è presente una sezione Notifiche, nascosta all'utente `admin` quando richiesto. L'utente sceglie un template e procede all'anteprima. Prima dell'invio viene sempre mostrata l'anteprima.

Regole allegati:

- se il template contiene `%REPORT%`, allegare il report PDF corrente dell'incidente
- se contiene `%DOCUMENTS%`, chiedere quali documenti allegare e impedire l'invio se nessun documento è disponibile o selezionato
- se contiene `%STATISTICS%`, allegare il report statistiche in PDF
- per ogni notifica inviata, creare automaticamente un'azione con la label associata al template
- allegare all'azione un PDF contenente il testo della mail inviata

### 7.5 SMTP

Le impostazioni SMTP sono nel menu Impostazioni, sezione Notifiche/SMTP, non nel menu Notifiche.

Parametri:

- host
- porta
- TLS/SSL
- autenticazione abilitata sì/no
- username SMTP opzionale, obbligatorio se auth abilitata quando richiesto dalla configurazione
- password SMTP opzionale
- mittente SMTP predefinito, obbligatorio se autenticazione SMTP è abilitata
- destinatario CSIRT
- destinatario DPO
- CC eventuali

È disponibile una funzione di test invio mail verso un indirizzo specificato. Anche l'utente admin deve poter inviare la mail di test. Quando autenticazione SMTP è abilitata e un utente/mittente SMTP predefinito è presente, tutte le mail di notifica e di test usano tale identità SMTP, non l'email personale dell'utente.

### 7.6 Promemoria automatici di scadenza azioni

Ogni `ConfigLabel` di tipo `action_label` include il campo numerico `max_completion_hours` visualizzato come Tempo massimo (ore), con default 0. Il campo rappresenta il tempo massimo, espresso in ore, entro il quale l'azione corrispondente deve essere completata a partire dalla prima azione dell'incidente riconducibile a `informazione iniziale`. Il valore 0 rappresenta esplicitamente l'assenza di un tempo massimo e quindi esclude la label dal controllo.

Le impostazioni notifiche includono:

- `notification_deadline_enabled`: abilita/disabilita i promemoria automatici;
- `notification_deadline_interval_hours`: componente ore dell'intervallo di controllo;
- `notification_deadline_interval_minutes`: componente minuti dell'intervallo di controllo;
- `notification_deadline_email_enabled`: abilita/disabilita totalmente l'invio email per task in scadenza;
- `notification_deadline_last_run_at`: timestamp tecnico dell'ultima esecuzione completata.

Il controllo è implementato dal thread scheduler dedicato: ad ogni ciclo verifica se lo slot configurato è dovuto e, in caso positivo, controlla gli incidenti non chiusi. Per ogni incidente aperto e non silenziato calcola le azioni attese configurate con tempo massimo numerico maggiore di zero e non ancora registrate nella timeline. Il valore 0 rappresenta l’assenza di un tempo massimo. Il riepilogo viene inviato via SMTP solo se l'invio email per task in scadenza è abilitato globalmente e solo per incidenti con almeno una unità di personale associata; i destinatari effettivi sono gli indirizzi valorizzati del personale coinvolto (`Person.email`). Il messaggio contiene azione attesa, scadenza calcolata e tempo rimanente o superato. Il flag `Incident.deadline_notifications_muted` consente di escludere singoli incidenti dai promemoria automatici senza modificare la configurazione globale. Oggetto e corpo sono costruiti con template configurabili tramite le impostazioni `notification_deadline_subject_template` e `notification_deadline_body_template`; il rendering sostituisce placeholder nella forma `%placeholder%` con valori dinamici calcolati a runtime.

La pagina impostazioni notifiche espone anche un'azione manuale `Esegui controllo ora`, utile per test operativi e troubleshooting. L'invio non avviene se l'invio email per scadenze è disabilitato, se SMTP non è configurato, se l'incidente non ha alcuna unità di personale associata o se nessuna persona associata ha un indirizzo e-mail valorizzato.

#### Template configurabile per email task in scadenza

La sezione `Template mail task in scadenza` in `app/templates/notification_settings.html` espone i campi di oggetto e corpo del messaggio. I placeholder supportati sono definiti in `DEADLINE_NOTIFICATION_PLACEHOLDERS` e sono sostituiti dalla funzione `render_deadline_template()`. La funzione `build_deadline_email_content()` applica il template salvato alle righe di azioni mancanti calcolate da `pending_deadline_actions_for_incident()`. I placeholder sconosciuti non vengono rimossi: restano nel testo e sono segnalati come warning durante l'anteprima. La preview è gestita dall'azione POST `preview_deadline_template`, usa dati dimostrativi prodotti da `sample_deadline_preview()` e non invia email.

## 8. Avvisi procedurali nel dettaglio incidente

Nel dettaglio di ogni incidente devono comparire avvisi evidenti:

- se manca l'azione `04-comunicazione allo CSIRT`, indicare che la procedura prevede la notifica allo CSIRT
- se manca l'azione `05-comunicazione al DPO`, indicare che la procedura prevede la notifica al DPO
- se dati personali è sì e manca `06-comunicazione al Garante della Privacy`, indicare che la procedura prevede la notifica al Garante
- se manca `07-notifica all’utente`, indicare che la notifica all’utente è richiesta e deve essere registrata nella lista delle azioni effettuate; il controllo è sempre attivo, indipendentemente dal flag dati personali

La stessa logica è centralizzata e riutilizzata nella pagina principale: ogni incidente con almeno un avviso procedurale pendente viene marcato nella lista con un simbolo di pericolo accanto al nome e un tooltip riepilogativo. Nel template `incident_detail.html` la sezione degli avvisi procedurali è posizionata immediatamente dopo la scheda principale dell’incidente, prima delle sezioni informative e operative, così che gli operatori vedano subito le attività procedurali da completare.

## 9. Reportistica ed export


### 9.0 Campi data/ora incidente

La UI degli incidenti separa data e ora di inizio/fine in quattro campi: `start_date`, `start_time`, `end_date`, `end_time`. Le colonne storiche `start_at` ed `end_at` sono rimosse dal database dopo la migrazione dei dati; nel modello restano solo proprietà calcolate compatibili, da usare per visualizzazione, report ed export. Le query SQL, gli ordinamenti e i filtri temporali devono usare le colonne reali `start_date`/`start_time` e `end_date`/`end_time`, perché le proprietà Python non supportano `.asc()`/`.desc()` in SQLAlchemy.

### Calcolo della durata operativa

La durata dell'incidente è una metrica operativa e non coincide necessariamente con il periodo dichiarato tramite data/ora inizio e data/ora fine. Il modello `Incident` espone `first_action_at`, `effective_duration` ed `effective_duration_seconds`. La durata viene calcolata solo se sono disponibili almeno una azione con `when_at` e una conclusione (`end_at` derivata da `end_date`/`end_time`); il valore è `end_at - first_action_at`. Se manca uno dei due estremi o la conclusione precede la prima azione, la durata è non disponibile.

Questo criterio è usato in modo coerente in lista principale, ordinamento per durata, export CSV, statistiche online e PDF statistiche. I campi `start_date`/`start_time` restano disponibili per rappresentare il periodo noto o dichiarato dell'evento, per filtri temporali e per compatibilità nei report/moduli, ma non entrano nel calcolo della durata.

### 9.1 Report PDF incidente

Il report PDF deve essere professionale e articolato, con:

- copertina o intestazione
- sezioni descrittive
- tabelle con font ridotto e testo wrappato per non uscire dalle celle
- personale coinvolto ordinato per nome
- azioni ordinate cronologicamente
- grafico delle azioni nel tempo con etichetta completa della label

### 9.2 Statistiche

Nel menu Report è presente la voce Statistiche. La pagina mostra statistiche separate per:

- finestra ricercata dall'utente
- ultima settimana
- ultimo mese
- ultimi 3 mesi
- ultimi 6 mesi
- ultimo anno

Statistiche richieste:

- numero incidenti per categoria
- numero incidenti per tipo di dati interessati
- durata media, calcolata sul tempo tra prima azione e conclusione
- aggregazioni disponibili su gravità, stato, dati personali, personale, compilatore, azioni e label ove possibile

È disponibile download PDF delle statistiche con grafici a barre e a torta.

### 9.3 Export e import

Menu Export:

- Export incidenti in CSV
- CSV import
- Export completo
- Full import

L'export completo deve contenere:

- tutti i dati del database, esportando tutte le colonne reali delle tabelle applicative
- incidenti completi
- configurazioni applicative
- logo eventuale
- utenti
- documenti caricati negli incidenti
- allegati delle azioni
- tipi di notifica
- template di notifica, inclusi quelli aggiunti dall'utente
- template dei moduli PDF originari caricati dagli amministratori
- mappature campo PDF/campo database e metadati dei campi PDF rilevati
- sezione `schema` del manifest con l’elenco dei campi esportati per ogni tabella

L'export completo non usa liste parziali di attributi: le righe sono generate dai metadati SQLAlchemy delle tabelle, così ogni nuova colonna del database viene inclusa automaticamente. Per la tabella incidenti, i quattro campi temporali granulari `start_date`, `start_time`, `end_date`, `end_time` sono forzati nel payload con formato ISO stabile e fallback dagli alias applicativi `start_at`/`end_at`; gli alias sono esportati anche nel manifest come campi di compatibilità, pur non essendo più colonne fisiche del modello corrente. L'import completo filtra i campi in base al modello corrente e converte date, ore e datetime prima del ripristino.

L'import completo deve ripristinare coerentemente il contenuto dell'archivio.

## 10. Bootstrap, migrazioni e robustezza DB

All'avvio l'applicazione deve:

1. attendere PostgreSQL con retry
2. creare tabelle mancanti
3. applicare migrazioni leggere per schema obsoleto, ad esempio aggiunta della colonna `reference`
4. riallineare le sequence PostgreSQL dopo import o dati con ID espliciti
5. eseguire seed idempotente senza duplicati
6. creare admin solo se manca
7. non resettare password admin ai riavvii

Tutte le operazioni di seed devono gestire correttamente i vincoli univoci, evitando errori `duplicate key value violates unique constraint`.

La creazione di azioni manuali e automatiche deve lasciare generare l'ID al database. In caso di sequence disallineata, riallineare e ritentare in sicurezza.

## 11. Deployment

### 11.1 Docker

Il container usa Debian Trixie e Gunicorn. Il Dockerfile deve installare le dipendenze native necessarie a PostgreSQL, LDAP, ReportLab e librerie Python.

Avvio consigliato:

```bash
gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 wsgi:app
```

### 11.2 Docker Compose

Il compose include:

- servizio app
- PostgreSQL 18.4 con volume persistente
- volume upload persistente
- variabili d'ambiente per DB, secret key, admin initial password

### 11.3 Kubernetes

Manifest inclusi:

- Deployment
- Service
- PVC per upload
- configurazione env per database e admin initial password

Il database deve essere persistente e riutilizzabile tra riavvii e versioni successive.

## 12. Documentazione utente

La documentazione utente è disponibile dal menu Aiuto come voce `Documentazione utente`. Deve essere estesa, divisa in capitoli, ricercabile e scaricabile in PDF dall’interno della pagina.

Il menu Info contiene Applicazione con nome, versione, build e autore; l'email dell'autore è cliccabile tramite link `mailto:`.

## 13. Prompt di riproduzione completa dell'applicazione

Usa il testo seguente per chiedere a ChatGPT di ricreare l'applicazione da zero nella forma corrente.

```text
Scrivi un'applicazione web completa chiamata “Cybersecurity Incident Registry”, versione 0.2.1, build 2026051901, autore Alessandro De Salvo <Alessandro.DeSalvo@roma1.infn.it>, da usare come registro degli incidenti informatici.

L'applicazione deve essere una web app Flask servita in produzione con Gunicorn, containerizzata con Docker basato su Debian Trixie, deployabile su Kubernetes e basata su PostgreSQL 18.4 persistente. Usa SQLAlchemy/Flask-SQLAlchemy, template Jinja2, CSS/JavaScript statici, ReportLab o equivalente per PDF, smtplib/email standard per SMTP, ldap3 per LDAP. Fornisci codice completo, Dockerfile, docker-compose.yml, manifest Kubernetes, README, documentazione utente e documentazione progettuale.

Implementa autenticazione locale e LDAP. L'utente locale admin deve essere creato solo se assente, chiamarsi admin e avere password iniziale configurabile via variabile d'ambiente `ADMIN_INITIAL_PASSWORD`; in produzione non deve essere un valore debole o predefinito. Non resettare mai la password admin ai riavvii. Usa hashing password senza limite bcrypt a 72 byte, per esempio PBKDF2-SHA256, con eventuale compatibilità legacy sicura. Gli utenti LDAP appena visti al login devono essere creati con ruolo disabled. Ruoli: admin, writer, reader, operator, disabled. Admin accede a tutto, writer legge/scrive, reader legge tutto, operator legge solo i propri incidenti, disabled non accede.

Crea un modello Incident con: creatore nome/email presi dall'utente loggato e non modificabili; nome; riferimento opzionale; descrizione; gravità configurabile; tipi di dati interessati multipli configurabili; flag dati personali; data/ora inizio; data/ora fine opzionale; categorie multiple configurabili; personale coinvolto multiplo; stato aperto/in lavorazione/chiuso; documenti allegati multipli; azioni multiple. La lista incidenti deve mostrare nome, intervallo inizio/fine, compilatore, personale, stato, durata tra prima azione registrata e conclusione dell'incidente; tutte le colonne ordinabili; conteggio totale filtrato o totale visibile. Supporta ricerca per data, parola chiave e label. Supporta clonazione incidente da lista e dettaglio. Supporta cancellazione incidenti con conferma e solo per utenti con permesso di scrittura/admin.

Crea azioni con data/ora, descrizione opzionale, persona precompilata con utente corrente ma modificabile, label azione configurabile, allegati multipli. Le azioni devono essere modificabili/cancellabili con conferma e permessi. Non assegnare mai manualmente ID: lascia generare al DB e riallinea sequence PostgreSQL all'avvio e dopo import.

Crea liste configurabili per gravità, dati interessati, categorie, label azioni e personale. I valori iniziali includono gravità molto bassa, bassa, media, alta, critica; dati password e dati personali; categorie furto di credenziali, phishing, SPAM, altro; label azioni 01-informazione iniziale, 02-analisi, 03-blocco, 04-comunicazione allo CSIRT, 05-comunicazione al DPO, 06-comunicazione al Garante della Privacy, 07-notifica all'utente, 08-conclusione. Le liste configurabili sono raggruppate per categoria/tipo. Permetti aggiunta e cancellazione inserendo solo il nome della label nella sezione corretta; la cancellazione rimuove i riferimenti dagli incidenti. La gestione anagrafica personale richiede solo nome ed email, senza Categoria/Gruppo. Nei form incidente usa drag & drop per categorie, dati interessati, personale e raccomandazioni, con destinazioni adiacenti alle sorgenti e label raggruppate per tipo dove applicabile. Le checkbox devono usare uno stile compatto per non aumentare eccessivamente l’ingombro delle tabelle e dei pannelli amministrativi.

Implementa logo applicativo caricato da admin, mostrato nella barra superiore e nella login con altezza massima 2 cm. Menu accessibili con tastiera, ARIA, focus visibile, dropdown leggibili e z-index corretto. UI responsive/mobile con menu compatto, lista incidenti a schede e form touch-friendly. Login centrata e senza informazioni sull'admin di default. Redirigi alla login se non autenticato. Mostra nome utente corrente a destra nella barra.

Menu: Incidenti, Report, Export, Admin solo admin, Notifiche solo admin, Impostazioni, Info, Aiuto. La voce `Nuovo incidente` non è presente nella barra dei menu; il relativo pulsante resta nella pagina principale degli incidenti. Nel menu Admin includi gestione utenti, LDAP, SSO, liste configurabili, personale, logo. Nel menu Impostazioni includi cambio password e impostazioni SMTP/notifiche. Nel menu Info includi Applicazione con nome, versione, build e autore, con email autore cliccabile mailto. Nel menu Aiuto mostra `Documentazione utente`, `Documentazione amministrativa` e `Note di rilascio`; non mostrare voci dirette di download PDF, perché i PDF devono essere scaricabili dai pulsanti interni alle rispettive pagine.

Implementa LDAP configurabile con server URI, base DN, bind DN/password opzionali, filtro utenti, attributi uid/cn/email. Implementa inoltre SSO/OAuth2/OpenID Connect configurabile da Admin → SSO con endpoint authorization/token/userinfo, client ID/secret, scope, mapping claim, ruolo predefinito, controllo non distruttivo della configurazione e avvio del test login interattivo. Permetti test comunicazione e ricerca utente tramite uid mostrando attributi ottenuti. Permetti da admin inserire utenti LDAP nell'app e assegnare ruoli. Permetti account locali aggiunta/rimozione, ma admin non eliminabile e email admin modificabile. Cambio password per utenti locali con doppia verifica nuova password.

Implementa notifiche. Menu Notifiche visibile solo admin e protetto lato backend. Gestisci tipi di notifica CRUD con codice, label, descrizione, modalità destinatario settings/manual, chiavi destinatario/cc e abilitazione. Gestisci template di notifica CRUD, aggiunta da voce separata, modifica, cancellazione, clonazione; associa ogni template a tipo notifica e a label azione. I template utente non devono essere cancellati al riavvio. Mostra elenco placeholder disponibili. Fornisci esempi per notifica utente, CSIRT e DPO.

Placeholder template: %DATA%, %CATEGORIES%, %PERSONAL_DATA%, %REPORT%, %NAME%, %OPERATOR%, %START%, %END%, %DESCRIPTION%, %REFERENCE%, %CREATOR%, %CREATOR_EMAIL%, %DOCUMENTS%, %STATUS%, %ACTIONS%. %REPORT% allega automaticamente il PDF report incidente. %DOCUMENTS% richiede scelta dei documenti e blocca invio se nessun documento è selezionato o presente. %ACTIONS% diventa lista cronologica azioni con data/ora. Prima di inviare mostra sempre anteprima. Per CSIRT e DPO non chiedere destinatario ma usa impostazioni; per altre notifiche chiedi destinatario manuale e conserva correttamente il campo tra anteprima e conferma. Se un template ha label azione associata, dopo invio crea automaticamente azione con quella label, descrizione con mittente/destinatari/cc e allega un PDF con testo esatto della mail inviata. Nascondi controlli invio notifiche nel dettaglio incidente se utente corrente è admin.

SMTP: impostazioni nel menu Impostazioni, non nel menu Notifiche. Campi host, porta, TLS/SSL, autenticazione opzionale, username, password, mittente SMTP predefinito obbligatorio se autenticazione abilitata, destinatari CSIRT/DPO e cc. Test invio mail verso indirizzo specificato, disponibile anche ad admin. Se auth SMTP è abilitata e mittente/utente default è configurato, tutte le mail usano l'identità SMTP default.

Nel dettaglio incidente mostra avvisi evidenti se manca azione 04 CSIRT, se manca 05 DPO e, se dati personali è sì, se manca 06 Garante Privacy.

Report: PDF incidente professionale con sezioni, titoli, tabelle wrappate/font piccolo, personale ordinato per nome, grafico azioni nel tempo con label completa. Report menu Statistiche con statistiche per finestra ricercata, ultima settimana, ultimo mese, ultimi 3 mesi, ultimi 6 mesi, ultimo anno: incidenti per categoria, dati interessati, durata media e aggregazioni da tutte le informazioni disponibili. Visualizza grafici a barre e torta e permetti download PDF statistiche dettagliato.

Export menu: Export incidenti in CSV, CSV import, Export completo, Full import. Export completo deve includere tutti i dati DB, incidenti, configurazioni, logo, utenti, documenti, allegati azioni, tipi notifica e template utente. Import completo deve ripristinare coerentemente tutto.

Bootstrap: attesa DB con retry, create_all per tabelle mancanti, migrazioni leggere per schemi obsoleti come aggiunta colonna reference, seed idempotente con upsert/get-or-create, advisory lock o meccanismo equivalente per evitare concorrenza, riallineamento sequence PostgreSQL, nessun duplicate key, nessun WORKER_BOOT_ERROR. Proteggi tutte le route lato backend e non solo tramite UI. Chiedi conferma prima di ogni cancellazione.
```

## 14. Checklist funzionale di verifica

- Login admin funziona con password iniziale al primo avvio.
- Dopo cambio password admin, il riavvio non ripristina la password iniziale configurata.
- Avvio Gunicorn non produce WORKER_BOOT_ERROR.
- Riavvii ripetuti non generano duplicate key.
- Creazione azione manuale non genera duplicate key.
- Creazione azione automatica da notifica non genera duplicate key.
- Template utente restano presenti dopo riavvio.
- Template utente sono visibili dal menu Notifiche.
- Export completo include tipi e template notifica.
- `%REPORT%` allega il PDF solo se presente nel template.
- `%DOCUMENTS%` richiede selezione documenti e blocca invio senza allegati selezionati.
- `%ACTIONS%` mostra azioni cronologiche.
- Menu Notifiche visibile solo admin.
- Pulsanti di eliminazione visibili solo a admin/writer e protetti lato route.
- Documentazione accessibile solo da Aiuto e scaricabile in PDF.


## Aggiornamento PostgreSQL 18.4 e robustezza sugli inserimenti

La distribuzione container usa PostgreSQL 18.4. Nel deployment locale il servizio `db` di `docker-compose.yml` usa l'immagine `postgres:18.4`; in Kubernetes è disponibile il manifest `k8s/postgresql.yaml` con PVC persistente e servizio interno.

Per evitare errori `duplicate key value violates unique constraint` durante la creazione di nuovi incidenti, l'applicazione deve rispettare queste regole progettuali:

1. non valorizzare mai manualmente `Incident.id`;
2. riallineare le sequence PostgreSQL all'avvio, dopo import completi e prima degli inserimenti critici;
3. deduplicare tutti gli ID provenienti dai controlli drag & drop prima di assegnarli alle relazioni many-to-many;
4. filtrare le label per `kind` quando si popolano categorie e dati interessati;
5. filtrare il personale sulla tabella `person`;
6. preservare l'ordine logico inviato dalla form senza inserire record duplicati nelle tabelle associative.

Queste regole sono applicate dagli helper `unique_int_list`, `labels_from_form`, `people_from_form` e dal riallineamento sequence PostgreSQL.


## Modulo `form_generation` per moduli PDF AcroForm

Il modulo `app/form_generation.py` gestisce template basati sul PDF originario caricato dall’amministratore. Il sistema non genera più file XML per i moduli: la directory `FORM_TEMPLATE_DIR` contiene i PDF compilabili, mentre la tabella `form_field_mapping` conserva l’associazione fra nome campo PDF e campo database dell’incidente.

### Configurazione

In **Moduli → Configurazione** l’amministratore carica un PDF con campi AcroForm. L’applicazione legge i nomi dei campi direttamente dal PDF, mostra una preview tabellare dei campi rilevati e salva il PDF originario come template. I nomi dei campi non vengono rinominati: coincidono con quelli definiti nel modulo PDF.

Nella mappatura, la sezione **Campi database incidenti** è scorrevole verticalmente per rendere più agevole il drag & drop quando i campi disponibili sono numerosi.

### Generazione

Quando un utente genera un modulo da un incidente, l’applicazione apre il PDF sorgente, legge posizione e dimensione dei campi AcroForm mappati, disegna i valori direttamente sulle pagine e scrive un nuovo PDF finale statico. Il PDF originale resta invariato. Ogni template ha una configurazione di compilazione persistente nella tabella `form_template_config`: font ammessi `Helvetica` e `Times-Roman`, dimensione ammessa da 8 a 16 pt. Durante la generazione il modulo applica il font e la dimensione configurati, wrappa i testi lunghi sulla larghezza del campo e rimuove dal PDF prodotto le annotazioni widget e il dizionario AcroForm, lasciando solo i valori compilati come contenuto pagina non modificabile. Per garantire la visualizzazione corretta dei campi, la compilazione risolve il nome completo dei campi anche quando il widget eredita il nome da uno o più parent AcroForm, supporta campi con più widget, usa le coordinate del CropBox e non disegna annotazioni nascoste o non visibili. La raccolta dei widget avviene sia dagli array `/Annots` delle pagine sia dall’albero `/AcroForm /Fields`, così i campi vengono disegnati anche quando un editor PDF li memorizza solo nella gerarchia AcroForm o non mantiene coerenti le due strutture. Il lookup del valore privilegia il nome completo, ma accetta come fallback il nome terminale del campo; inoltre la resa statica adatta il font nei riquadri molto piccoli e centra verticalmente i valori monoriga, evitando omissioni di campi compatti come date e orari.

### Campi dati aggiuntivi

I campi database disponibili per la mappatura includono ora anche:

- `security_owner_role`, ruolo del titolare della sicurezza configurato in **Admin → Dati titolare**;
- `structure`, nome della struttura configurato in **Admin → Struttura**.

Questi si aggiungono ai dati già disponibili per titolare, responsabile, conseguenze, misure adottate e raccomandazioni.

### Export/import

L’export completo include i template PDF originari presenti in `FORM_TEMPLATE_DIR` o, se il file operativo manca, la copia binaria persistente salvata nel database. I metadati dei campi AcroForm rilevati, le relative mappature salvate in `form_field_mapping` e la configurazione di font/dimensione salvata in `form_template_config` restano esportati insieme ai file. L’import completo ripristina i PDF nella stessa directory e ricrea le impostazioni dei template, rendendoli subito disponibili nella configurazione e nella generazione moduli; non sono richiesti file XML intermedi. La pagina di configurazione consente anche la sostituzione del PDF sorgente di un template esistente. Prima di sovrascrivere il file, il nuovo PDF viene analizzato e confrontato con il modello corrente: l’operazione è permessa solo se l’insieme dei campi AcroForm compilabili è identico. In questo modo le righe di `form_field_mapping` e la configurazione `form_template_config` rimangono valide e non vengono cancellate.

## PostgreSQL 18.4 volume

Per PostgreSQL 18.4 il volume persistente deve essere montato su `/var/lib/postgresql` sia in `docker-compose.yml` sia nei manifest Kubernetes. L'applicazione continua a usare `DATABASE_URL` per la connessione; la persistenza è garantita dal volume nominato/PVC montato su tale path.


## Dati amministrativi e campi derivati degli incidenti

L’applicazione mantiene in tabella `setting` le informazioni globali relative a titolare e responsabile della sicurezza. Le chiavi utilizzate sono:

- `security_owner_name`
- `security_owner_role`
- `structure_name`
- `security_responsible_name`
- `security_responsible_email`
- `security_responsible_phone`
- `security_responsible_function`

Le raccomandazioni sono gestite dalla tabella `recommendation` e associate agli incidenti tramite tabella many-to-many `incident_recommendations`. La configurazione avviene nel menu Admin. Le raccomandazioni sono esportate e importate dal full backup insieme alla relazione con gli incidenti.

I campi derivati `consequences` e `measures_adopted` non sono duplicati nel database: sono calcolati al momento a partire da categorie, dati interessati e azioni dell’incidente. Il modulo `form_generation` espone questi campi nella lista dei dati mappabili sui template PDF.

### 11.10 Campi dinamici e filtro azioni esportabili

Il modulo `form_generation` espone nella lista dei campi database incidenti due campi calcolati non persistenti:

- `awareness_date`, visualizzato come **Data venuta a conoscenza**;
- `awareness_time`, visualizzato come **Ora venuta a conoscenza**.

Entrambi sono calcolati cercando la prima azione dell’incidente, ordinata per `when_at`, la cui label contiene il testo “informazione iniziale”. Da tale azione vengono estratte rispettivamente data e ora. Se non esiste un’azione corrispondente, i campi vengono valorizzati con stringa vuota.

La tabella `action` contiene il flag booleano `exportable`, usato per determinare se un’azione debba essere inclusa nel campo derivato `measures_adopted`. Per le nuove azioni manuali o generate automaticamente, il valore iniziale deriva dal campo `ConfigLabel.default_exportable` della label azione selezionata. In assenza di una label configurata resta il fallback storico basato su parole chiave come “notifica”, “comunicazione”, “informazione iniziale”, “analisi” o “conclusione”. Il dettaglio incidente consente agli utenti con permessi di scrittura di modificare il flag per ogni azione. `measures_adopted` considera esclusivamente le azioni con `exportable=True`, mentre la lista completa delle azioni resta disponibile nel campo `actions` e nella vista dell’incidente. La rappresentazione testuale di ogni misura esportata segue l’ordine richiesto per i moduli: prima il testo dell’azione, composto da label ed eventuale descrizione, quindi la data e ora nel formato `YYYY-MM-DD HH:MM`.

## Documentazione utente ricercabile e logo applicativo

La documentazione utente è disponibile dal menu `Aiuto -> Documentazione` ed è implementata nel template `app/templates/help.html`. La guida è stata riscritta come manuale operativo completo, organizzato in capitoli separati e dedicati a:

1. scopo dell’applicazione e concetti base del registro incidenti;
2. accesso, ruoli e navigazione;
3. pagina principale, ricerca e avvisi procedurali;
4. creazione di un nuovo incidente passo-passo;
5. modifica, clonazione, chiusura e cancellazione;
6. gestione delle azioni e flag `exportable`;
7. notifiche e-mail e notifica all’utente richiesta;
8. documenti e allegati;
9. configurazione e generazione moduli PDF;
10. report, statistiche, export e import;
11. amministrazione e configurazioni;
12. esempi completi passo-passo;
13. uso mobile, accessibilità e buone pratiche.

La documentazione online è ricercabile lato client tramite `makeDocumentationSearch()` in `app/static/app.js`. Il campo di ricerca filtra i blocchi `.doc-chapter` usando il testo del capitolo e l’attributo `data-doc-title`; il conteggio dei risultati viene aggiornato in tempo reale e viene mostrato un messaggio dedicato quando non esistono capitoli corrispondenti. La ricerca non richiede chiamate server e resta disponibile anche per utenti con permessi di sola lettura, purché autenticati.

La versione PDF della documentazione è generata dalla rotta `GET /aiuto/pdf`, usando lo stesso template HTML della guida online. La rotta converte il contenuto documentale in PDF ReportLab, rimuovendo gli elementi interattivi non necessari come indice di navigazione e controlli di ricerca. Il PDF resta scaricabile dal pulsante presente nella guida; il menu Aiuto non contiene voci dirette di download PDF.

È stato aggiunto un logo pittorico applicativo statico in `app/static/cir-application-logo.svg`. Il logo rappresenta graficamente il concetto di registro incidenti cybersecurity tramite scudo, registro, lucchetto, tracciati digitali e simbolo di pericolo. Questo logo è separato dal logo custom configurabile dall’amministratore:

- il logo custom resta gestito dalla rotta `/logo`, dalle impostazioni `logo_path`, dal menu `Admin -> Logo` e dal full export/import;
- il logo pittorico applicativo non sostituisce, non modifica e non cancella il logo custom;
- nella pagina di login il logo pittorico applicativo è sempre mostrato tramite `app/templates/login.html`, indipendentemente dalla presenza del logo custom;
- nelle pagine interne desktop/non mobile il logo pittorico applicativo è mostrato nella barra del menu principale tramite la classe `.menu-app-logo`;
- nelle pagine interne desktop resta inoltre disponibile la variante decorativa fissa in basso a destra tramite la classe `.app-corner-logo`;
- nelle viste mobile il logo pittorico della barra menu e quello decorativo sono nascosti con media query per non ridurre lo spazio operativo.

Le regole CSS sono in `app/static/style.css`. Per le viste desktop/non mobile la barra superiore `.topbar` usa background blu `#1d4ed8`; gli stati hover/attivo del menu usano una tonalità blu più scura per mantenere contrasto e leggibilità. La presenza del logo nel menu e del logo decorativo in basso a destra è definita in `app/templates/base.html`, mentre la visualizzazione nella pagina di login è definita in `app/templates/login.html`. Nel menu desktop/non mobile il nome applicativo `Cybersecurity Incident Registry` è reso tramite `.brand-title` come titolo verticale a tre righe, una parola per riga, per risparmiare spazio orizzontale. La voce `Nuovo incidente` è stata rimossa dal menu principale: il flusso di creazione resta accessibile dal pulsante `Nuovo incidente` nella pagina principale, coerentemente con il template `app/templates/index.html`.


### 11.15 Estensioni dati incidente, label descrittive e campi moduli

Il modello `Incident` include i campi `data_subjects_count`, `data_volume` e `deadline_notifications_muted`, gestiti nelle form di creazione/modifica incidente e serializzati dal full export tramite il meccanismo introspectivo sulle colonne SQLAlchemy. Il modello `Action` include `consequence_text`, modificabile dalla tabella azioni del dettaglio incidente. I report e la generazione moduli usano le conseguenze esplicite delle azioni quando presenti; il calcolo euristico resta come fallback.

Il modello `ConfigLabel` include il campo `description`, gestito da `Admin -> Liste configurabili`. La descrizione è utilizzata per due funzioni: descrivere le categorie incidente nel campo dinamico `category_descriptions` (“Descrizione e causa”) e rappresentare le label azione nel campo `measures_adopted`. Se la descrizione è vuota viene usato il valore della label per compatibilità con configurazioni esistenti.

La lista `available_incident_fields()` espone i nuovi campi mappabili: `category_descriptions`, `data_subjects_count`, `data_volume`, `privacy_authority_non_notification_reason` e `documentation_location`. Gli ultimi due sono letti dalla tabella `setting` tramite le chiavi `privacy_authority_non_notification_reason` e `documentation_location`, configurabili dalla nuova rotta amministrativa `Admin -> Altre configurazioni`.

La configurazione moduli supporta la rinomina del template PDF tramite azione `rename_template`: il file in `FORM_TEMPLATE_DIR`, le righe di `form_field_mapping` e la riga `form_template_config` vengono aggiornati allo stesso nuovo nome, senza alterare il contenuto del PDF né i mapping esistenti.

## Documentazione utente visuale e PDF professionale

La documentazione utente accessibile dal menu **Aiuto** è mantenuta come pagina HTML ricercabile lato client. La ricerca filtra i capitoli tramite gli attributi `data-doc-title` e il testo dei contenuti, preservando l'indice navigabile e la consultazione online.

La pagina include esclusivamente il logo pittorico dell'applicazione `cir-application-logo.svg` convertito anche in `app/static/help/app-logo.png` per l'uso nella documentazione e nella generazione PDF. Il logo custom configurabile dall'amministratore resta separato e non viene incluso nella documentazione utente, per evitare confusione fra identità applicativa e identità dell'ente utilizzatore.

Gli asset visuali della guida sono conservati in `app/static/help/`:

- `app-logo.png`: logo applicativo usato nella documentazione;
- `flow-incident-lifecycle.png`: diagramma di flusso del ciclo di vita dell'incidente;
- `screenshot-dashboard.png`: schermata illustrativa della pagina principale;
- `screenshot-incident-detail.png`: schermata illustrativa del dettaglio incidente e della timeline azioni;
- `screenshot-modules.png`: schermata illustrativa della configurazione moduli PDF;
- `charts-reporting.png`: esempi di grafici per statistiche e reportistica.

Le schermate sono illustrative e non contengono dati reali. Servono a rendere la guida più chiara senza introdurre dipendenze da uno specifico ambiente di esercizio o da dati di produzione.

La rotta `GET /aiuto/pdf` genera una versione PDF professionale della guida con ReportLab. La generazione include copertina, logo applicativo, indice sintetico, intestazione blu, piè di pagina con numerazione pagine, stili tipografici coerenti, callout introduttivo e inserimento degli asset visuali. Il PDF viene prodotto dinamicamente e scaricato come `cybersecurity-incident-registry-documentazione.pdf`.

## Implicazioni manutentive

Quando si aggiungono nuove funzionalità applicative, aggiornare sia la pagina `app/templates/help.html` sia la documentazione progettuale. Se la funzionalità ha impatto operativo rilevante, aggiungere o aggiornare anche un asset visuale in `app/static/help/` e verificare che la versione PDF resti leggibile. Il logo custom dell'ente non deve essere usato negli asset della guida utente.

## Documentazione amministrativa online e PDF professionale

È stata aggiunta una documentazione amministrativa distinta dalla documentazione utente. La pagina online è implementata nel template `app/templates/admin_help.html` ed è raggiungibile da `GET /aiuto/amministrazione`, esposta nel menu `Aiuto` con la voce **Documentazione amministrativa**. La pagina è autenticata come la documentazione utente e usa lo stesso motore di ricerca client-side `makeDocumentationSearch()` in `app/static/app.js`: i capitoli sono elementi `.doc-chapter`, il testo ricercabile comprende contenuto e attributo `data-doc-title`, il conteggio risultati è aggiornato in tempo reale e un messaggio dedicato viene mostrato in assenza di risultati.

La guida amministrativa è organizzata in capitoli separati dedicati a:

1. scopo, prerequisiti e responsabilità amministrative;
2. accesso amministrativo, ruoli e sicurezza account;
3. gestione utenti locali e autorizzazioni;
4. LDAP, OAuth2 e SSO;
5. liste configurabili, label e categorie;
6. dati organizzativi, titolare, struttura, responsabile e altre configurazioni;
7. SMTP, template e notifiche;
8. template PDF, mapping e generazione moduli;
9. logo, documentazione e menu Aiuto;
10. export, import, backup e ripristino;
11. controlli periodici, audit e qualità dati;
12. troubleshooting e checklist operative.

Il menu `Aiuto` include ora quattro voci: documentazione utente, download PDF utente, documentazione amministrativa e download PDF amministrativo. Le nuove route sono:

- `GET /aiuto/amministrazione` -> pagina HTML amministrativa ricercabile;
- `GET /aiuto/amministrazione/pdf` -> generazione dinamica del PDF amministrativo.

La rotta `admin_help_pdf()` genera il PDF amministrativo con ReportLab, mantenendo la stessa impostazione professionale della guida utente ma con titolo, metadati e contenuti specifici per l'amministrazione. Il PDF include copertina con logo applicativo, informazioni applicative lette da `current_app.config['APP_INFO']`, indice sintetico, header blu, footer con numerazione pagine, stili tipografici dedicati, callout introduttivo, diagrammi e schermate illustrative. Il file viene scaricato come `cybersecurity-incident-registry-documentazione-amministrativa.pdf`.

Gli asset visuali amministrativi sono salvati in `app/static/help/` e non contengono dati reali:

- `admin-flow.png`: diagramma del flusso amministrativo consigliato;
- `admin-screenshot-sso.png`: schermata illustrativa della configurazione SSO e del controllo connessione;
- `admin-screenshot-modules.png`: schermata illustrativa della configurazione moduli PDF e mapping;
- `admin-chart-governance.png`: mappa delle aree di governance amministrativa.

Come per la documentazione utente, viene usato esclusivamente il logo pittorico applicativo (`app/static/help/app-logo.png`), senza includere il logo custom configurabile dall'amministratore. Questo mantiene separata l'identità applicativa dalla personalizzazione dell'ente utilizzatore.

### Implicazioni manutentive della documentazione amministrativa

Ogni nuova funzionalità con impatto su configurazione, sicurezza, ruoli, integrazioni, export/import, template PDF, notifiche o governance deve aggiornare anche `app/templates/admin_help.html` e, quando utile, gli asset visuali amministrativi in `app/static/help/`. La documentazione progettuale deve rimanere allineata alle route e ai template disponibili nel menu Aiuto. Le modifiche al PDF amministrativo devono essere verificate generando il documento e controllando che logo, indice, immagini, capitoli e numerazione risultino leggibili.

## Multi-factor authentication TOTP

La versione 0.110-72 consolida il sottosistema MFA basato su TOTP per utenti locali e LDAP introducendo la verifica obbligatoria prima del salvataggio dei token.

### Modello dati

- `User.mfa_enabled`: flag booleano, disattivato per default, che abilita la richiesta di secondo fattore per l'utenza.
- `MfaTotpToken`: tabella dei token TOTP associati agli utenti, con nome descrittivo, secret, data di creazione, data di verifica (`verified_at`) e data ultimo utilizzo.

La migrazione idempotente aggiunge `user.mfa_enabled` ai database esistenti, crea la tabella `mfa_totp_token` tramite `db.create_all()` e aggiunge `verified_at` valorizzandolo con `created_at` per i token preesistenti, così da preservare la compatibilità degli upgrade.

### Flusso di autenticazione

1. L'utente locale inserisce username e password, oppure l'utente LDAP completa il bind LDAP.
2. Se `mfa_enabled` è attivo e l'utente ha almeno un token TOTP verificato (`verified_at` valorizzato), il login non viene ancora completato.
3. L'identificativo utente viene salvato temporaneamente in sessione come `mfa_user_id`.
4. La pagina `/mfa/verify` richiede il codice TOTP.
5. Il codice viene verificato con finestra temporale tollerante `valid_window=1`.
6. Al successo viene aggiornata `last_used_at`, viene rimossa la sessione MFA temporanea e viene completato `login_user()`.

La MFA non viene applicata al login SSO, perché il secondo fattore può essere già demandato all'Identity Provider esterno.

### Gestione utente

La pagina **Impostazioni → Multi-factor authentication** consente all'utente autenticato di:

- attivare o disattivare il flag MFA personale, solo se esiste almeno un token verificato;
- generare un token TOTP temporaneo con nome descrittivo;
- visualizzare stringa segreta, URI provisioning e QR Code prima del salvataggio;
- inserire il codice generato dall'app TOTP per verificare il token;
- salvare il token solo dopo verifica positiva;
- annullare la creazione del token non ancora verificato;
- rimuovere i token personali.

I dettagli del token vengono mostrati durante la fase di verifica iniziale. Se la verifica fallisce il token non viene salvato. La rimozione dell'ultimo token verificato disattiva automaticamente `mfa_enabled`.

### Gestione amministrativa

La pagina **Admin → Utenti → gestisci MFA** consente agli amministratori di:

- attivare o disattivare MFA per qualsiasi utente locale o LDAP, solo se l'utenza dispone di almeno un token verificato;
- rimuovere singoli token;
- rimuovere tutti i token di un utente, con disattivazione automatica della MFA.

Gli amministratori non vedono i segreti TOTP degli altri utenti. L'unica eccezione è l'accesso ai propri token, che resta equivalente alla pagina personale.

### Dipendenze

- `pyotp`: generazione e verifica dei codici TOTP.
- `qrcode[pil]`: generazione del QR Code mostrato alla creazione del token.

### Licenza

Il pacchetto include un file `LICENSE` con indicazione EUPL-1.2.

### Aggiornamento 0.110-72 - verifica preventiva token TOTP

Il flusso di provisioning MFA è stato reso atomico rispetto alla verifica: il secret generato resta temporaneamente in sessione e non viene persistito finché il codice TOTP non viene validato con `pyotp.TOTP(secret).verify(..., valid_window=1)`. Questo evita token inutilizzabili o configurati in modo incompleto nel database. Le viste utente e amministratore disabilitano il toggle MFA quando non esistono token verificati e il backend applica lo stesso vincolo anche sulle richieste POST, così da non dipendere solo dall'interfaccia.

### Aggiornamento 0.110-73 - raccomandazioni drag & drop e checkbox compatte

Le pagine di creazione e dettaglio/modifica incidente includono le raccomandazioni nel componente `dnd_fields.html`, estendendo il pattern drag & drop già usato per categorie, dati interessati e personale. Il target `recommendations` genera campi hidden omonimi, consumati dalla funzione `recommendations_from_form`, mantenendo invariata la relazione many-to-many `incident_recommendations` e la deduplicazione server-side degli identificativi. Le raccomandazioni già associate sono renderizzate come chip removibili tramite clic, così il comportamento è uniforme per tutte le selezioni collegate all’incidente.

Il CSS globale applica dimensioni più piccole agli input checkbox e riduce padding/gap nelle liste con checkbox, migliorando la leggibilità delle tabelle operative senza modificare la semantica dei form.


## Selezione template PDF nel dettaglio incidente

La sezione di generazione moduli nelle pagine incidente utilizza una UI a schede cliccabili invece di checkbox visibili. Ogni scheda rappresenta un template PDF e contiene nome template e numero di campi rilevati. La selezione è multipla, viene evidenziata con stato visuale blu e mantiene il contratto applicativo preesistente inviando al backend il parametro `templates` con i nomi selezionati. Per compatibilità e accessibilità, le checkbox restano nel DOM come input nascosti, mentre la selezione può essere modificata tramite click o tastiera.


## Persistenza robusta dei template PDF

Per evitare la perdita dei modelli dopo un riavvio, i PDF dei template moduli sono persistiti su due livelli:

1. file system operativo configurato da `FORM_TEMPLATE_DIR`, usato direttamente da analisi AcroForm, anteprima, sostituzione e generazione dei PDF compilati;
2. tabella `form_template_binary`, che conserva `template_name`, `filename`, contenuto binario del PDF e timestamp di creazione/aggiornamento.

Il bootstrap applicativo invoca il ripristino dei template mancanti subito dopo le migrazioni dello schema. Anche `list_templates()` e `get_template()` richiamano il ripristino on-demand, così la pagina di configurazione moduli e la generazione documenti sono protette anche se la directory viene svuotata mentre l’applicazione è in esecuzione.

Le operazioni amministrative mantengono allineati i due livelli:

- creazione e sostituzione template scrivono il file PDF e aggiornano/upsertano `form_template_binary`;
- rinomina template aggiorna il file, `form_field_mapping`, `form_template_config` e `form_template_binary`;
- cancellazione template rimuove file, mapping, configurazione e copia binaria;
- export completo legge il file da `FORM_TEMPLATE_DIR` e, se non disponibile, usa la copia binaria del database.

La directory `FORM_TEMPLATE_DIR` rimane comunque da montare come volume persistente in produzione per ridurre I/O sul database e mantenere compatibilità con strumenti esterni, ma la copia DB rende il sistema resiliente ai riavvii con volume vuoto o non montato correttamente.


## Full export: copertura completa dei dati applicativi

Il full export è progettato come backup applicativo autosufficiente e ripristinabile. La funzione di export serializza le tabelle elencate in `FULL_EXPORT_TABLES` usando direttamente le colonne SQLAlchemy effettive, evitando sottoinsiemi manuali di campi. Il manifest include inoltre `schema._coverage`, che dichiara tabelle database, tabelle di relazione e gruppi di file esportati.

La copertura comprende:

- `settings`, incluse configurazioni generali, LDAP, SSO, notifiche, template email, logo custom e opzioni operative;
- utenti locali, LDAP e SSO, ruoli e stato MFA;
- token MFA TOTP, inclusi metadati e segreti cifrati/serializzati secondo il modello applicativo;
- label configurabili, categorie, descrizioni, tempi massimi task e tassonomie;
- personale, raccomandazioni, incidenti, azioni, documenti, allegati azione;
- template moduli, mapping campi, configurazioni font e copie binarie persistenti dei PDF;
- tabelle di relazione many-to-many tra incidenti, personale, categorie, tipologie dati e raccomandazioni;
- documenti fisici associati agli incidenti, allegati azione, template PDF, logo custom e loghi applicativi statici.

I campi binari nel database, come i PDF salvati in `FormTemplateBinary`, sono codificati in Base64 nel JSON e decodificati in fase di import. L'import completo elimina lo stato applicativo corrente e ricrea dati, relazioni e file nello stesso ordine logico delle dipendenze.

Per verificare la completezza di un export, aprire `export.json` nell'archivio e controllare le sezioni `schema`, `tables`, `relations` e `files`. La presenza dei gruppi `documents`, `action_attachments`, `form_templates`, `logo` e `application_logos` conferma la copertura dei file associati.


Aggiornamento 0.110-82: configurazione URL applicazione e placeholder notifiche. Nel menu Admin → Altre configurazioni è disponibile il campo “URL applicazione”, con default http://localhost:8000, usato per generare link esterni nelle email. Nei template delle email dei task in scadenza sono disponibili %external_url%, %report% e %statistics%: il primo inserisce la URL esterna configurata, mentre %report% e %statistics% richiedono rispettivamente l'allegato PDF del report incidente e il PDF delle statistiche, generati al momento dell'invio. Nei template generali del menu Notifiche è disponibile anche %EXTERNAL_URL%. L’anteprima dei task in scadenza segnala gli allegati previsti senza inviare email.

## Aggiornamento 0.110-84 - mantenimento della posizione nella pagina incidente

Nelle pagine di dettaglio incidente, dopo le operazioni eseguite dai pulsanti di salvataggio, aggiunta azione, upload documenti e generazione moduli PDF, l’applicazione torna automaticamente alla stessa sezione operativa da cui è partita l’azione. Le sezioni interessate sono identificate con ancore stabili: dati principali dell’incidente, azioni, documenti e generazione moduli. Il comportamento riduce la perdita di contesto nelle pagine lunghe e semplifica l’inserimento progressivo di azioni, allegati e moduli generati.


## Aggiornamento 0.110-85 - fuso orario applicativo e conclusione automatica

È stata aggiunta la configurazione `application_timezone` nella tabella `setting`, gestibile da **Admin → Altre configurazioni**. Il valore di default è `Europe/Rome` ed è interpretato come identificativo IANA tramite `zoneinfo`. Se il valore non è valido, la logica applicativa usa `Europe/Rome` come fallback sicuro.

La rotta di dettaglio incidente passa al template `incident_detail.html` i valori `default_action_when` e `application_timezone`. `default_action_when` è formattato come `YYYY-MM-DDTHH:MM` per l'input HTML `datetime-local` ed è calcolato al caricamento della pagina nel fuso orario configurato. In questo modo ogni nuova azione parte dal momento effettivo di caricamento della form, pur restando modificabile dall'utente prima del salvataggio.

È stata introdotta la funzione di dominio `is_conclusion_action()`, che riconosce le azioni di conclusione leggendo label, descrizione della label e descrizione libera. Quando una nuova azione manuale, oppure una modifica a un'azione esistente, viene riconosciuta come conclusione, `close_incident_from_conclusion_action()` aggiorna l'incidente a `status='chiuso'` e imposta `end_at` alla data/ora dell'azione. La scelta mantiene coerente il calcolo della durata operativa, basato sull'intervallo tra prima azione registrata e conclusione.


## Aggiornamento 0.110-86 - Chiusura automatica e data/ora fine

La chiusura automatica tramite azione di conclusione aggiorna esplicitamente `status`, `end_date` ed `end_time` dell’incidente a partire dal timestamp dell’azione di conclusione. La logica non si limita alla property compatibile `end_at`, così i valori risultano immediatamente disponibili per form, full export, CSV, statistiche, report PDF e compilazione dei moduli.


## Aggiornamento 0.110-87 - Validazione preventiva dei campi usati dai template

La generazione dei moduli PDF passa ora da una validazione preventiva dei mapping selezionati. La funzione `missing_required_incident_fields_for_templates()` legge i mapping `FormFieldMapping` dei template selezionati, calcola i valori tramite `incident_value()` e considera mancanti i campi il cui valore normalizzato è vuoto.

La rotta `generate_incident_forms()` blocca la generazione prima di invocare `generate_pdf_from_template()` se la validazione trova campi mancanti. Il messaggio utente è prodotto da `format_missing_required_incident_fields()` e raggruppa in un'unica segnalazione template, campo database e campo PDF interessato. Il redirect torna alla sezione `incident-forms`, coerentemente con il meccanismo di mantenimento posizione introdotto in precedenza.

La scelta evita la creazione di PDF incompleti, centralizza la logica sui mapping esistenti e non modifica lo schema dati. Il controllo si applica a tutti i campi disponibili nella lista dei campi database incidente, inclusi campi calcolati e derivati, perché il valore effettivo viene risolto dalla stessa funzione usata dalla compilazione PDF.

## Aggiornamento 0.110-88 - audit log, messaggi contestuali e menu Moduli

### Messaggi contestuali nel dettaglio incidente

Il dettaglio incidente usa flash message categorizzati con prefisso `section:<anchor>:<category>`. Il template consuma i messaggi una sola volta e li redistribuisce nelle aree operative corrispondenti: `incident-main`, `incident-actions`, `incident-documents` e `incident-forms`. I messaggi non sezionali continuano a essere mostrati come notifiche globali. Questa scelta mantiene il redirect con ancora già presente e rende l’errore visibile nel punto in cui l’utente ha richiesto l’operazione.

### Audit log applicativo

È stato aggiunto il modello `AuditLog`, corrispondente alla tabella `audit_log`, con i campi principali `occurred_at`, `operation_type`, `username`, `user_id`, `actor_type` e `details`. Un hook `after_app_request` registra automaticamente le richieste mutative completate con successo (`POST`, `PUT`, `PATCH`, `DELETE`) includendo endpoint, metodo, path, status code e ancora di provenienza. Il controllo automatico delle scadenze notifiche registra una voce dedicata `scheduler:deadline_notification_check` con attore `scheduler`.

La ritenzione è configurata con la chiave `audit_retention_months_part / audit_retention_days_part / audit_retention_hours_part / audit_retention_minutes_part` nella tabella `setting`, default 6 mesi. Il valore è modificabile in **Admin -> Altre configurazioni** da utenti con ruolo admin. La cancellazione dei record più vecchi della retention avviene in modo opportunistico durante la registrazione delle operazioni, evitando la necessità di un job separato obbligatorio.

### Menu Moduli dinamico

Il context processor calcola `modules_menu_visible` e il template base mostra il dropdown **Moduli** solo se l’utente ha almeno una voce accessibile. Nella configurazione corrente la voce **Configurazione** resta riservata agli amministratori; di conseguenza il menu non compare per utenti che non avrebbero elementi visualizzabili.



## Aggiornamento 0.110-90 - Retention audit espressa in mesi, giorni, ore e minuti

La retention della tabella `audit_log` è stata resa granulare tramite quattro chiavi di configurazione: `audit_retention_months_part`, `audit_retention_days_part`, `audit_retention_hours_part` e `audit_retention_minutes_part`. La funzione `audit_retention_parts()` legge tali valori, mantiene compatibilità con la precedente chiave `audit_retention_months` e applica il default di 6 mesi quando la configurazione risulta vuota o nulla. `audit_retention_delta()` traduce la configurazione in un `timedelta`, usando il criterio applicativo già adottato di 30 giorni per mese, e `audit_cutoff_datetime()` continua a fornire il cutoff usato da `purge_audit_logs()`.

La pagina **Admin -> Altre configurazioni** espone i quattro campi numerici e aggiorna anche la chiave storica dei mesi per compatibilità con export/import precedenti. Il pulsante di salvataggio è stato vincolato tramite CSS a un'altezza massima di 1 cm con la classe `admin-config-save-button`.

## Aggiornamento 0.110-89 - Consultazione audit, export/import e retention

Il full export include esplicitamente la tabella `audit_log` attraverso `FULL_EXPORT_TABLES['audit_logs']` e include tutte le configurazioni applicative attraverso `FULL_EXPORT_TABLES['settings']`. La funzione `_export_schema_payload()` espone tali tabelle anche nella sezione `schema` del manifest, consentendo di verificare la copertura dell’archivio. Il full import importa prima impostazioni e utenti, poi token MFA e audit log, preservando i riferimenti utente quando presenti.

La retention audit è applicata dalla funzione `purge_audit_logs()`, che usa `audit_cutoff_datetime()` e quindi il valore configurato in `setting.audit_retention_months_part / audit_retention_days_part / audit_retention_hours_part / audit_retention_minutes_part`, con default 6 mesi e valori espressi in mesi, giorni, ore e minuti. La funzione viene invocata dall’hook `after_app_request` dopo le richieste mutative concluse con successo, dal task scheduler delle notifiche in scadenza e al termine del full import. In questo modo anche i record audit importati vengono immediatamente riallineati alla policy di conservazione configurata.

La nuova rotta `GET /admin/audit`, riservata agli amministratori, espone una pagina di consultazione della tabella audit. La pagina supporta ricerca libera su operazione, utente, origine e dettagli, filtri specifici per tipo operazione, username, actor type e intervallo data/ora. Il menu Admin contiene la voce **Audit** solo per utenti con ruolo admin. Il template `admin_audit.html` mostra il cutoff corrente, la retention configurata e gli ultimi 500 risultati ordinati per data decrescente.


## Aggiornamento 0.110-91 - Avvisi procedurali nella parte alta del dettaglio incidente

La sezione `procedural-alerts` del template `app/templates/incident_detail.html` è stata spostata nella parte alta della pagina di dettaglio incidente, subito dopo la scheda principale con i dati editabili dell’incidente. Restano invariati i controlli centralizzati sugli avvisi e la visualizzazione nella pagina principale; cambia solo l’ordine di presentazione per dare priorità operativa alle notifiche e verifiche procedurali pendenti.


## Aggiornamento 0.110-92 - Default exportable configurabile sulle label azioni

Il modello `ConfigLabel` include la colonna booleana `default_exportable`, valorizzata a `True` per default e migrata automaticamente sui database esistenti. La pagina `Admin -> Liste configurabili`, sezione `Label azioni`, consente di impostare il campo “Esportabile per default”. La funzione di creazione delle azioni usa questo valore per inizializzare `Action.exportable` quando l’utente inserisce una nuova azione in un incidente o quando un flusso automatico crea un’azione con una label configurata. Il flag della singola azione resta modificabile dal dettaglio incidente.

## Aggiornamento 0.110-93 - Tempo massimo in ore e fuso orario notifiche scadenza

La gestione delle liste configurabili espone nella sezione **Label azioni** la colonna **Tempo massimo (ore)**, rendendo esplicita l’unità di misura del campo `ConfigLabel.max_completion_hours`.

Il sottosistema delle notifiche automatiche per task in scadenza usa il fuso orario applicativo configurato tramite `application_timezone` in **Admin → Altre configurazioni**. La funzione di formattazione centralizzata delle date/ore usate nei template di scadenza aggiunge il nome della timezone configurata e viene applicata a `%initial_information_at%`, `%pending_actions%` e `%generated_at%`. Anche il thread scheduler calcola `now` attraverso l’orario applicativo, mantenendo coerente il confronto con le date naive salvate dagli inserimenti utente.



## Aggiornamento 0.110-94 - Internazionalizzazione IT/EN

L'applicazione mantiene l'interfaccia web e le documentazioni utente/amministratore in italiano e inglese. La lingua effettiva viene determinata dal nuovo setting `interface_language`:

- `auto`: usa il locale del browser, italiano per locale italiano e inglese per tutto il resto;
- `it`: forza l'interfaccia e le documentazioni in italiano;
- `en`: forza l'interfaccia e le documentazioni in inglese.

Il setting è gestito da Admin → Altre configurazioni ed è incluso nel full export/import come tutte le altre configurazioni applicative. Le pagine di aiuto online e i PDF amministrativi/utente selezionano il template documentale coerente con la lingua risolta. Le traduzioni dell'interfaccia sono applicate anche ai principali testi statici di menu, form, pulsanti e messaggi di navigazione.

Policy di manutenzione: le richieste operative possono continuare a essere raccolte in italiano; ogni modifica successiva deve aggiornare anche la resa inglese dell'interfaccia e della documentazione.

## Aggiornamento 0.110-95 - README bilingue del pacchetto

Il pacchetto distribuisce ora due README di primo livello: `README.md` in italiano e `README_en.md` in inglese. `README_en.md` è la controparte inglese del README italiano e deve essere aggiornato insieme a `README.md` ogni volta che cambiano funzionalità, configurazioni, istruzioni di deploy, export/import, audit, notifiche o criteri di internazionalizzazione.

La policy di manutenzione bilingue è quindi estesa da interfaccia web e documentazioni utente/amministratore ai README del pacchetto. Le istruzioni operative possono continuare a essere espresse in italiano; la traduzione inglese dei testi documentali interessati deve essere prodotta contestualmente all'aggiornamento.


## Aggiornamento 0.110-96 - Dicitura avviso notifica utente

Nel template `app/templates/incident_detail.html` la label visualizzata negli avvisi procedurali per la notifica all'utente è stata uniformata alla logica applicativa già presente in `procedural_warnings()`: **Notifica all'utente richiesta**. La modifica evita ambiguità tra un controllo ancora da valutare e un adempimento procedurale richiesto che scompare quando viene registrata l'azione corrispondente.

### Report PDF incidenti: layout documenti e timestamp

La funzione `incident_pdf()` in `app/reports.py` costruisce la sezione **Documenti** con larghezze esplicite di colonna: il nome del documento usa la parte più ampia della tabella, mentre la data/ora di caricamento usa una colonna compatta. Il timestamp di caricamento viene normalizzato tramite `_format_upload_datetime()`, che rimuove eventuali microsecondi e produce il formato `YYYY-MM-DD HH:MM:SS`, garantendo secondi sempre interi.

### Incident PDF reports: document layout and timestamps

The `incident_pdf()` function in `app/reports.py` builds the **Documents** section with explicit column widths: the document name receives most of the table width, while the upload date/time uses a compact column. The upload timestamp is normalised through `_format_upload_datetime()`, which removes any microseconds and outputs `YYYY-MM-DD HH:MM:SS`, ensuring seconds are always integer values.
### Aggiornamento 0.1.0-98 - Report PDF incidenti: orari e durata

La funzione `incident_pdf()` in `app/reports.py` usa il formatter comune `_format_pdf_datetime()` per tutti i valori data/ora testuali del report incidente. Il formatter rimuove i microsecondi e produce sempre una rappresentazione con secondi interi nel formato `YYYY-MM-DD HH:MM:SS`. La tabella di sintesi include inoltre il campo **Durata**, valorizzato tramite `Incident.effective_duration`, quindi con lo stesso criterio della lista principale: differenza tra prima azione registrata e conclusione dell’incidente, solo quando entrambi gli estremi sono disponibili e coerenti.

### Update 0.1.0-98 - Incident PDF reports: times and duration

The `incident_pdf()` function in `app/reports.py` uses the shared `_format_pdf_datetime()` formatter for every textual date/time value in the incident report. The formatter strips microseconds and always outputs integer seconds in the `YYYY-MM-DD HH:MM:SS` format. The summary table also includes the **Duration** field, populated from `Incident.effective_duration`, therefore using the same rule as the main list: the difference between the first recorded action and the incident closing time, only when both endpoints are available and consistent.
### Aggiornamento 0.1.0-99 - Report PDF incidenti: impaginazione professionale

La funzione `incident_pdf()` in `app/reports.py` genera ora una copertina con logo applicativo e logo custom configurato, un indice sintetico iniziale, intestazioni di sezione evidenziate e un callback canvas per la numerazione delle pagine. L'impaginazione usa `CondPageBreak` e `keepWithNext` sugli heading per evitare che il titolo di una sezione venga separato dal contenuto della sezione stessa. Le tabelle mantengono righe alternate, intestazioni evidenziate e larghezze ottimizzate per i contenuti.

English: `incident_pdf()` now produces a cover area with the application logo and the configured GUI-uploaded logo, a concise initial table of contents, highlighted section headings and a canvas callback for page numbers. Layout uses `CondPageBreak` and `keepWithNext` on headings so section titles are not separated from their content. Tables use alternating rows, highlighted headers and content-oriented column widths.

## Aggiornamento 0.1.0-100 - Report PDF incidenti: loghi

La funzione `incident_pdf` usa `_report_logos_table` per comporre i loghi di prima pagina. La tabella non usa più la dicitura `Logo custom`: il logo statico applicativo e l'eventuale logo caricato da GUI sono entrambi presentati come logo applicativo. Se la configurazione `logo_path` è vuota o punta a un file non esistente, il logo da GUI viene omesso senza generare celle vuote nel PDF.


## Aggiornamento 0.1.0-101 - Rendering immagini logo nei report PDF

La funzione `_pdf_logo_flowable()` in `app/reports.py` rasterizza i file SVG tramite `svglib.svg2rlg()` e `reportlab.graphics.renderPM.drawToFile()` in un PNG temporaneo, poi inserisce il PNG come `Image` ReportLab scalata. Questo rende affidabile la visualizzazione del logo applicativo statico `cir-application-logo.svg` nei report PDF incidenti ed evita che titolo, descrizione o testo alternativo dello SVG vengano mostrati al posto dell'immagine. `_report_logos_table()` genera solo la riga delle immagini e non aggiunge più etichette testuali sotto i loghi. Il logo caricato da GUI continua a essere inserito solo se `logo_path` è valorizzato e punta a un file esistente.

### Update 0.1.0-101 - Logo image rendering in PDF reports

The `_pdf_logo_flowable()` function in `app/reports.py` rasterises SVG files through `svglib.svg2rlg()` and `reportlab.graphics.renderPM.drawToFile()` into a temporary PNG, then inserts that PNG as a scaled ReportLab `Image`. This reliably displays the static `cir-application-logo.svg` application logo in incident PDF reports and prevents SVG title, description or fallback text from being rendered instead of the image. `_report_logos_table()` now generates only the image row and no textual labels below the logos. The GUI-uploaded logo is still included only when `logo_path` is set and points to an existing file.

## Aggiornamento 0.1.0-102 - Logo applicativo e logo caricato nei report PDF

La funzione `_report_logos_table()` in `app/reports.py` usa ora come sorgente primaria del logo applicativo `app/static/help/app-logo.png`, già rasterizzato e quindi gestito in modo affidabile da ReportLab. Lo SVG `cir-application-logo.svg` resta disponibile solo come fallback. La funzione `_resolve_logo_path()` normalizza sia percorsi assoluti sia percorsi relativi del logo caricato da GUI. Nei report PDF degli incidenti il logo applicativo viene sempre mostrato come immagine reale quando l’asset statico è presente; il logo caricato da GUI viene mostrato accanto al logo applicativo solo se configurato e realmente esistente.

### Update 0.1.0-102 - Application and uploaded logos in PDF reports

The `_report_logos_table()` function in `app/reports.py` now uses `app/static/help/app-logo.png` as the primary source for the application logo, because it is already rasterised and reliably handled by ReportLab. The `cir-application-logo.svg` asset remains available only as a fallback. The `_resolve_logo_path()` function normalises both absolute and relative paths for the GUI-uploaded logo. Incident PDF reports always show the application logo as a real image when the static asset is present; the GUI-uploaded logo is shown next to it only when configured and actually present.

## Aggiornamento 0.1.0-103 - Scheduler notifiche indipendente dal traffico e menu Admin collassabile

La funzione `run_deadline_notification_check(force=False, source='request')` è richiamata dal pulsante manuale e dallo scheduler automatico in background; non viene più eseguita dalle richieste web per evitare sovrapposizioni di invio. Il nuovo `start_deadline_notification_scheduler(app)` avvia all'avvio dell'applicazione un thread daemon denominato `cir-deadline-notification-scheduler`; il thread esegue un poll breve, configurabile tramite `CIR_DEADLINE_SCHEDULER_POLL_SECONDS` con minimo 30 secondi, e richiama il controllo solo quando l'intervallo funzionale configurato in tabella `setting` è trascorso. In questo modo un intervallo di 4 ore genera il controllo anche se non arrivano richieste HTTP all'applicazione.

Lo scheduler può essere disabilitato impostando `CIR_ENABLE_DEADLINE_SCHEDULER=0`, per ambienti che vogliono delegare l'esecuzione a un job esterno. Non esiste più fallback opportunistico da `before_app_request`: l'esecuzione periodica è del thread interno dedicato. Una lock di processo impedisce sovrapposizioni nello stesso worker e il lock advisory PostgreSQL serializza i cicli fra worker o repliche.

Ogni esecuzione effettiva delle notifiche in scadenza registra una riga in `audit_log` con `operation_type='scheduler:deadline_notification_check'` e `actor_type='scheduler'`. I dettagli JSON includono `source`, `interval_minutes`, `incidents_checked`, `incidents_with_pending`, `sent`, `skipped` ed eventuali errori limitati. Le chiamate che non eseguono il controllo perché la funzionalità è disabilitata o l'intervallo non è ancora trascorso non generano righe di audit operative.

Il template `base.html` riorganizza il menu Admin in gruppi `<details>` collassabili dentro il dropdown principale. I gruppi sono: **Configurazione generale**, **Anagrafiche e workflow**, **Utenti e accesso**, **Controllo e audit**. Le regole CSS `.admin-menu` e `.admin-menu-group` limitano l'altezza del menu e ne permettono lo scroll verticale, riducendo l'ingombro quando le voci amministrative aumentano.

## Aggiornamento 0.1.0-104 - Slot schedulati da mezzanotte per notifiche task

Il sottosistema delle notifiche automatiche dei task in scadenza introduce le funzioni `deadline_schedule_reference_midnight()`, `current_deadline_schedule_slot()`, `next_deadline_notification_at()` e `format_deadline_schedule_info()`. Queste funzioni calcolano gli slot funzionali partendo dalla mezzanotte del giorno corrente nel fuso orario applicativo, evitando che l'orario di avvio del processo determini la cadenza delle notifiche. La funzione `run_deadline_notification_check()` confronta l'ultimo slot eseguito con lo slot corrente e memorizza in `notification_deadline_last_run_at` lo slot pianificato, non l'orario effettivo di invocazione.

Il template `app/templates/notification_settings.html` visualizza una sezione informativa con il prossimo invio stimato, l'intervallo effettivo, la mezzanotte di riferimento, lo slot corrente e l'ultima esecuzione automatica. Il pulsante manuale continua a usare `force=True` e non sposta la pianificazione automatica basata sugli slot.

## Promemoria specifici e scheduler

È stata aggiunta la tabella `incident_reminder`, collegata a `incident`, per gestire promemoria non periodici con `scheduled_at`, `message`, `cc_emails`, `sent_at`, autore e ultimo errore di invio. La pagina dettaglio incidente espone una sezione dedicata per creare, modificare, cancellare e, se necessario, sbloccare il reinvio di un promemoria già marcato come inviato.

Il thread scheduler esegue sia il controllo periodico dei task in scadenza sia il recupero dei promemoria specifici. Per i task periodici la pianificazione resta ancorata agli slot calcolati dalla mezzanotte nella timezone applicativa. Per i promemoria specifici non periodici vengono inviati esclusivamente i record scaduti con `sent_at` nullo. A differenza dei riepiloghi periodici dei task in scadenza, non viene applicato alcun blocco per tipologia o finestra di schedule: ogni promemoria puntuale è autonomo e può essere recuperato anche se cade nello stesso periodo di altri promemoria. Prima dell'invio viene comunque registrato un claim tecnico temporaneo in `deadline_notification_state`, usato solo per impedire invii contemporanei dello stesso record mentre l'SMTP è in corso; l'esito funzionale resta il campo `incident_reminder.sent_at`.

Il full export/import include `incident_reminders`; le migrazioni leggere creano automaticamente la nuova tabella sui database esistenti e riallineano la sequenza PostgreSQL.


## Aggiornamento 0.1.0-106 - Chiusura incidenti, audit paginato e link diretti nelle notifiche

La chiusura manuale o automatica di un incidente viene impedita quando sono ancora presenti avvisi procedurali attivi. Il messaggio di blocco viene mostrato nella sezione dell'operazione richiesta: dati principali dell'incidente per la chiusura manuale, sezione Azioni per la chiusura automatica tramite azione di conclusione.

La pagina **Admin → Audit** ora usa paginazione. Il numero predefinito di record per pagina è configurabile in **Admin → Altre configurazioni** tramite il campo **Record audit per pagina**, con default 20 e massimo 100. In cima alla pagina Audit sono visualizzati il numero totale corrente dei record della tabella, il numero di record filtrati e l'intervallo attualmente selezionato.

Nelle notifiche manuali/non schedulate relative a incidenti il link diretto alla pagina dello specifico incidente viene inserito nel testo solo se il template contiene il placeholder `%INCIDENT_URL%`. Nei template dei task in scadenza resta disponibile `%incident_url%` e il comportamento dello scheduler è separato. Nei template generali sono inoltre disponibili `%MEASURES_ADOPTED%` (lista delle contromisure adottate finora nell’incidente), `%SITE%` (nome della struttura configurata in Admin → Struttura) e `%STATISTICS%`, che richiede l’allegato PDF del report statistiche generato al momento dell’invio.

## Aggiornamento 0.1.0-107 / Update 0.1.0-107

- IT: la UI dei promemoria specifici incidente è stata convertita in un layout responsive a schede, con griglia desktop e disposizione verticale mobile per impedire overflow laterali.
- EN: the incident-specific reminder UI has been converted to a responsive card layout, using a desktop grid and a vertical mobile layout to prevent horizontal overflow.
- IT: la funzione centrale di audit normalizza ora i dettagli tramite una sintesi applicativa, conservando soltanto campi identificativi, contatori, esiti e descrizioni brevi.
- EN: the central audit function now normalizes details through an application-level summary, retaining only identifiers, counters, outcomes and short descriptions.


### 7.8 Pianificazione cron delle notifiche task

Dalla versione 0.1.0-108 le notifiche dei task con scadenza usano una pianificazione unificata gestita dalle impostazioni `notification_deadline_schedule_mode`, `notification_deadline_cron_times`, `notification_deadline_interval_hours` e `notification_deadline_interval_minutes`. La modalità `interval` produce slot regolari calcolati dalla mezzanotte applicativa; la modalità `cron` aggiunge orari giornalieri espliciti nel formato `HH:MM` agli slot di intervallo. La funzione `current_deadline_schedule_slot()` determina l’ultimo slot dovuto rispetto alla mezzanotte nel fuso configurato, mentre `next_deadline_notification_at()` calcola il prossimo slot. Il timestamp tecnico `notification_deadline_last_run_at` memorizza lo slot eseguito, non l’ora di avvio del processo.

La funzione `run_deadline_notification_check()` è condivisa da pulsante manuale e scheduler di background. In esecuzione automatica esegue solo l’ultimo slot periodico dovuto, così un riavvio dopo più slot saltati non genera invii duplicati. Il record audit `scheduler:deadline_notification_check` contiene modalità, orari cron, slot, prossimo invio, incidenti controllati, incidenti con task pendenti, invii, salti ed errori SMTP sintetizzati.

### Admin menu 0.1.0-109
Il menu Admin usa gruppi HTML `<details>` senza attributo `open`, così ogni caricamento pagina presenta i sottogruppi chiusi per default. Questo evita stato iniziale espanso e mantiene il menu compatto.


## Scheduler notifiche task 0.1.0-110

La logica di `run_deadline_notification_check()` è stata corretta per evitare falsi negativi nei controlli automatici. In precedenza lo slot corrente poteva essere marcato come eseguito anche quando il primo poll dello scheduler non trovava task pendenti; eventuali task presenti o diventati rilevabili subito dopo nello stesso slot non venivano più notificati fino allo slot successivo.

La deduplica è ora per incidente e slot, tramite record audit `scheduler:deadline_notification_sent` con marker leggibile `Incidente <id>; slot <timestamp>`. Il record globale `scheduler:deadline_notification_check` resta diagnostico e contiene incidenti controllati, incidenti con task pendenti, invii, salti, incidenti già notificati nello slot e incidenti senza destinatari. La funzione `pending_deadline_actions_for_incident()` rileva le azioni mancanti indipendentemente dalla presenza di destinatari; l'assenza di personale o indirizzi email viene gestita in fase di invio come condizione di skip, rendendo audit e diagnostica coerenti con i task effettivamente presenti.

## Aggiornamento 0.1.0-111 - Audit degli slot notifiche task

La funzione `run_deadline_notification_check()` mantiene il poll tecnico frequente dello scheduler, ma separa il poll dall'evento funzionale di audit. Il record `scheduler:deadline_notification_check` viene scritto solo se `sent > 0`, se il controllo è manuale oppure se lo slot pianificato corrente non ha ancora un audit diagnostico. La nuova funzione `_deadline_notification_check_already_audited_for_slot()` verifica la presenza di un record globale per lo stesso `schedule_slot`, evitando che i poll ripetuti dello stesso slot producano molte righe senza valore operativo.

In assenza di task da notificare viene quindi mantenuta una sola evidenza per lo slot cron/intervallo in cui l'invio sarebbe dovuto avvenire. Gli invii reali restano tracciati sia nel record globale del controllo sia nei record puntuali `scheduler:deadline_notification_sent`, usati anche per la deduplica per incidente e slot.

## Aggiornamento 0.1.0-112 - Qualità grafica della documentazione
La documentazione online e la documentazione PDF bilingue usano immagini illustrative rigenerate e regole CSS più robuste per evitare overflow di titoli, testi e pulsanti nei riquadri. I generatori PDF della documentazione mantengono il rapporto originale delle immagini e le ridimensionano entro l'area utile della pagina, riducendo il rischio di tagli o deformazioni. Le risorse in `app/static/help/` devono essere mantenute con testi già leggibili alla risoluzione originale e con spazi interni sufficienti per la versione PDF.

### Audit anti-flooding and release notes

The audit subsystem stores concise details and collapses consecutive equal events by updating `audit_log.repeat_count`. A new row is forced every 100 equal consecutive occurrences to preserve periodic evidence without flooding the table. Release notes are exposed through a dedicated Help menu entry and PDF endpoint; the PDF is downloaded from inside the release-notes page, keeping operational user/admin documentation focused on procedures.


## Audit retention, maximum size and export

The audit subsystem applies two independent controls: time-based retention and maximum table size. `audit_max_records` defaults to 10000 and is configured from Admin → Audit. Automatic purge first removes records older than the configured retention window, then removes the oldest remaining records if the physical row count exceeds the configured maximum. Manual purge actions can keep only the latest N records or delete rows older than a selected cutoff date. The Audit page also exposes filtered CSV export.


## Aggiornamento 0.1.0-117 - Stato persistente ultimo invio notifiche deadline

È stata introdotta la tabella `deadline_notification_state`, indicizzata tramite `notification_key`, per tracciare l’ultimo invio riuscito delle notifiche automatiche dei task in scadenza. Per le notifiche riepilogative l’identificatore è nella forma `deadline_summary:incident:<id>`, con `last_success_at`, `last_schedule_slot`, destinatari e contatore invii.

La funzione `deadline_schedule_window()` calcola la finestra funzionale `[slot_corrente, slot_successivo)` a partire dalla pianificazione cron/intervalli. Prima dell’invio, `_deadline_notification_sent_in_current_window()` verifica la tabella di stato e usa l’audit `scheduler:deadline_notification_sent` come fallback per dati storici. Se lo stesso riepilogo di incidente è già stato inviato con successo nella finestra corrente, lo scheduler non invia una seconda email e incrementa i contatori di skip del controllo.

Gli invii riusciti chiamano `_record_deadline_notification_success()`, che aggiorna o crea il record persistente. La tabella è inclusa in full export/import, così la deduplica sopravvive a backup, restore e riavvii.


## Aggiornamento 0.1.0-118 - Profili multipli SSO/OAuth2

L'accesso federato SSO/OAuth2/OpenID Connect supporta ora più profili configurabili e attivabili contemporaneamente da **Admin → SSO**. Ogni profilo ha un ID tecnico, nome provider, stato attivo/disattivo, endpoint authorization/token/userinfo, client ID, client secret, scope e mapping dei claim.

Nella pagina di login, quando sono presenti profili SSO attivi e completi, viene mostrato un pulsante per ciascun provider, così l'utente può scegliere quale SSO utilizzare. Il redirect URI resta comune e viene mostrato nella pagina Admin → SSO. Gli utenti creati automaticamente da SSO mantengono il ruolo predefinito del profilo; il valore consigliato resta `disabled` per consentire la successiva abilitazione amministrativa.

È disponibile il pulsante **Aggiungi esempio Google**, che precompila un profilo Google OpenID Connect con:

- Authorization endpoint: `https://accounts.google.com/o/oauth2/v2/auth`;
- Token endpoint: `https://oauth2.googleapis.com/token`;
- UserInfo endpoint: `https://openidconnect.googleapis.com/v1/userinfo`;
- scope: `openid email profile`;
- claim: `email`, `email`, `name`, `sub`.

Compilare poi Client ID e Client secret ottenuti dalla console Google e registrare il redirect URI mostrato dall'applicazione. I profili SSO sono salvati nelle configurazioni applicative e inclusi nel full export/import.

## Aggiornamento 0.1.0-119 - Profili SSO/OAuth2: callback HTTPS e profilo generico

La configurazione dei profili SSO/OAuth2 genera e usa sempre un redirect/callback URI con schema `https://`, anche quando l'applicazione riceve traffico interno HTTP dietro reverse proxy o container. I pulsanti **Salva profilo SSO** e **Controlla configurazione** non richiedono più conferme di cancellazione; la conferma resta limitata alla sola eliminazione del profilo.

In **Admin → SSO** è disponibile anche il pulsante **Aggiungi profilo generico**, oltre all'esempio Google, per creare un profilo OAuth2/OpenID Connect vuoto da completare con gli endpoint del proprio Identity Provider.


## Aggiornamento 0.1.0-120 - Accesso HTTPS/SSL opzionale

Il container espone ora anche la porta 8443 per l'accesso HTTPS/SSL opzionale. La porta HTTP 8000 resta sempre disponibile e la mancata configurazione SSL o l'assenza dei certificati non blocca l'avvio dell'applicazione.

La configurazione può essere eseguita tramite variabili di ambiente in Docker Compose o Kubernetes: `SSL_ENABLED`, `SSL_PORT`, `SSL_DIR`, `SSL_CERT_FILE` e `SSL_KEY_FILE`. In alternativa, un amministratore può usare la nuova voce **Admin → HTTPS/SSL** per abilitare o disabilitare l'accesso HTTPS e caricare certificato host e chiave privata in formato PEM. Se HTTPS viene abilitato ma certificato o chiave privata non sono presenti, il listener HTTPS resta spento e l'accesso HTTP continua a funzionare.

Il full export/import include anche i certificati SSL caricati dall'interfaccia, così da mantenere ripristinabile la configurazione applicativa completa.


## Documentation structure - 0.1.0-121

User and administrator documentation is maintained in Italian and English. The online templates are the source for PDF generation and are structured into searchable chapters, operational procedures, checklists and troubleshooting sections.


### 0.1.0-122 - Documentazione e timezone audit

La documentazione utente espone le informazioni applicative essenziali lette da `APP_INFO` e chiarisce che la generazione dei documenti considera solo le azioni contrassegnate come esportabili. La schermata illustrativa del dettaglio incidente è stata rigenerata con il riquadro “Scheda principale” più alto per evitare overflow del testo nella guida online e PDF.

La vista `Admin -> Audit` converte i timestamp audit, registrati internamente come UTC naive, nel fuso configurato in `application_timezone`; anche filtri temporali, purge per data ed export CSV interpretano/esportano i valori nel fuso applicativo.

### Aggiornamento 0.1.0-124

I profili SSO/OAuth2 supportano un logo opzionale per provider. Il profilo Google di esempio usa il logo Google incluso nel pacchetto e copiato nello storage persistente al primo avvio. I loghi caricati sono salvati nella directory configurata da `SSO_LOGO_DIR` (default `/data/sso_logos`), referenziati nel JSON dei profili nel formato logico `sso/<filename>` e inclusi nel full export/import.


### Rimozione utenti amministrata

La gestione utenti consente agli amministratori di creare e rimuovere account locali, LDAP o SSO non più necessari. Lo stesso username può essere presente più volte se cambia il backend di autenticazione; la tabella utenti espone un tipo di login leggibile e il valore `auth_provider` tecnico per distinguere le identità. Per gli utenti SSO il tipo di login include anche nome provider e id profilo, in modo che due provider SSO diversi che restituiscono lo stesso username restino riconoscibili anche dall'interfaccia amministrativa. La cancellazione è progettata per essere sicura in produzione: non è consentito eliminare l’account amministratore della sessione corrente e non è consentito eliminare l’ultimo account con ruolo `admin`. Prima della cancellazione vengono svincolati i riferimenti tecnici da incidenti, promemoria e audit (`creator_id`, `created_by_id`, `user_id`), preservando i record storici e le informazioni testuali già salvate, come nome compilatore, e-mail e dettagli audit. I token MFA dell’utente vengono eliminati tramite la relazione cascade del modello `User`.

From the administrator perspective, user deletion is an access-control operation, not a data-retention purge. Removing a user blocks future access and removes MFA tokens, but does not remove incidents, reminders or audit history. This keeps operational traceability intact while allowing administrators to keep the active user list clean.


## Aggiornamento 0.2.1-125 - Identità utente composta

Il modello `User` usa ora il vincolo composto `username + auth_provider` (`uq_user_username_auth_provider`) invece dell’unicità sul solo `username`. I login locali cercano esclusivamente utenti con `auth_provider='local'`; il login LDAP cerca o crea utenti con `auth_provider='ldap'`; i profili SSO/OAuth2 cercano o creano utenti con `auth_provider='sso:<id profilo>'`. In questo modo lo stesso identificativo restituito dai diversi backend non causa fusioni accidentali di account, ruoli o token MFA.

La migrazione idempotente all’avvio aggiorna gli utenti storici con backend mancante e, su PostgreSQL, rimuove il vincolo univoco precedente sul solo username prima di creare il vincolo composto. I nuovi database SQLite di sviluppo usano direttamente il modello aggiornato; per produzione il database supportato resta PostgreSQL.


### Aggiornamento 0.2.1-126 - Visualizzazione provider nel tipo login SSO

La vista `Admin → Utenti` costruisce una mappa dei backend disponibili a partire dai profili SSO configurati. I backend `local` e `ldap` sono mostrati come login locali o LDAP, mentre ogni backend nel formato `sso:<id profilo>` viene presentato come `SSO/OAuth2 · <nome provider> (<id profilo>)`, mantenendo visibile anche il codice tecnico. Se un utente fa riferimento a un profilo SSO eliminato o non più configurato, l'interfaccia lo segnala come profilo non configurato invece di nascondere l'account.


## Aggiornamento 0.2.1-10 - Placeholder notifiche manuali e link incidente esplicito

Le notifiche manuali/non schedulate non aggiungono più automaticamente il link diretto all’incidente: il link compare solo se il template contiene `%INCIDENT_URL%`. Sono stati aggiunti i placeholder `%MEASURES_ADOPTED%`, `%SITE%` e `%STATISTICS%`; quest’ultimo allega il PDF delle statistiche. La documentazione utente chiarisce che l’utente locale `admin` non può inviare notifiche dalla pagina degli incidenti: per inviare tali notifiche è necessario accedere con un altro utente autorizzato.

## Template notifiche, moduli associati e rubrica destinatari esterni

`NotificationTemplate.linked_form_template_name` collega opzionalmente un template di notifica manuale a un template modulo PDF. I documenti generati tramite il flusso moduli salvano `Document.generated_template_name`; in anteprima notifica i documenti dello stesso incidente con quel valore vengono preselezionati. La preselezione non è vincolante: l’utente può modificare gli allegati e, se nessun documento corrisponde, viene mostrato un warning non bloccante.

La tabella `ExternalRecipient` contiene nome, email e note della rubrica condivisa. I campi destinatario/CC delle notifiche manuali usano questa rubrica come suggerimento; durante l’invio, nuove email vengono aggiunte dopo acquisizione del nome. La rubrica è amministrabile da menu Admin e inclusa nel full export/import.


### Tag multipli dei documenti per preselezione allegati notifiche

Il modello `Document` contiene il campo `notification_tags`, una lista compatta di codici di tipo notifica associati al documento. Nel dettaglio incidente la sezione Documenti espone una palette dei tipi notifica e una drop-zone per ogni documento: l’utente con permesso di scrittura trascina il tipo sulla drop-zone, può rimuovere il tag e salva la configurazione. La route `update_document_notification_tags` valida i codici rispetto a `NotificationType` e aggiorna solo documenti appartenenti a incidenti visibili all’utente.

In anteprima invio notifica, `auto_selected_notification_documents()` combina due criteri di preselezione: documenti taggati con il tipo notifica corrente e documenti generati dal template modulo eventualmente collegato al template di notifica. I duplicati vengono rimossi. La lista rimane modificabile dall’utente prima dell’invio, quindi il tagging è un suggerimento operativo e non un vincolo di allegazione. Il full export/import include il campo perché deriva dallo schema SQLAlchemy.


## Aggiornamento 0.2.1 - Picker rubrica destinatari esterni

La pagina di anteprima delle notifiche manuali con destinatario libero riceve la lista `ExternalRecipient` solo quando il tipo di notifica non usa destinatari bloccati da configurazione. Il template `notification_preview.html` espone un selettore con nome ed e-mail dei destinatari esterni e pulsanti client-side per valorizzare il campo destinatario principale o aggiungere l’indirizzo al campo CC, mantenendo invariata la validazione server-side e l’acquisizione dei nuovi indirizzi tramite `ensure_external_recipients_from_addresses()`.

## Aggiornamento 0.2.1 - Tag automatici dei documenti generati

La conferma dei moduli PDF generati dall'incidente ora determina i tag di notifica da applicare al documento partendo dai template di notifica manuali che hanno `linked_form_template_name` uguale al template modulo usato per la generazione. La funzione `notification_tags_for_generated_form_template()` restituisce i codici dei tipi di notifica abilitati, rimuove i duplicati e viene invocata durante `confirm_generated_forms()` prima del salvataggio del nuovo record `Document`.

Il campo `Document.notification_tags`, già introdotto per il tagging multiplo degli allegati, viene quindi valorizzato automaticamente anche per i documenti generati. La preselezione in invio notifica continua a usare `auto_selected_notification_documents()`, che combina tag del documento e template modulo collegato, lasciando invariata la possibilità per l'utente di modificare manualmente gli allegati.

Metadati runtime aggiornati: versione `0.2.1`, build `2026051901`.

## Aggiornamento 0.2.1 - Gestione rubrica destinatari esterni per utenti writer

La rubrica `ExternalRecipient` resta una risorsa applicativa condivisa. La rotta amministrativa `admin_external_recipients()` continua a essere disponibile solo agli utenti con ruolo `admin`, mentre la nuova rotta `settings_external_recipients()` espone la stessa gestione CRUD dal menu **Impostazioni** agli utenti non amministratori con ruolo `writer`. La funzione di autorizzazione dedicata `can_manage_external_recipients_from_settings()` evita di aprire il menu amministrativo e limita l’accesso agli utenti con privilegi di scrittura/modifica sugli incidenti. Le due route condividono la funzione interna `_external_recipients_page()`, così validazione, controllo duplicati, audit, template HTML e comportamento operativo rimangono coerenti.

Il template `base.html` mostra **Impostazioni → Destinatari esterni** solo agli utenti `writer`; gli amministratori mantengono la voce **Admin → Destinatari esterni**. La funzione comune `_external_recipients_page()` accetta il parametro `q` e filtra `ExternalRecipient` per nome, email o note mantenendo il filtro durante modifica, salvataggio e cancellazione. Il template `admin_external_recipients.html` è stato parametrizzato con `endpoint_name` e `settings_mode`, in modo che annullamento, modifica e salvataggio ritornino alla route corretta in base al punto di accesso. Gli audit generati dalla pagina Impostazioni usano il prefisso `settings:external_recipient_*`, mentre quelli amministrativi mantengono il prefisso `admin:external_recipient_*`.

## Flussi operativi incidenti

Il modello dati include `IncidentWorkflowStep`, che rappresenta un passo operativo atteso. Ogni passo contiene un riferimento opzionale a una categoria di incidente (`category_id` nullo per il flusso di default), un riferimento obbligatorio a una label azione (`action_label_id`), una posizione ordinabile e una descrizione operativa. Le label azione continuano a essere gestite nella tabella `ConfigLabel` con `kind='action_label'`, quindi il catalogo delle azioni resta estendibile.

Nel dettaglio incidente il servizio calcola il flusso applicabile partendo dalle categorie associate. Se esistono passi per almeno una categoria dell’incidente, i passi vengono uniti e i duplicati identici, definiti da stessa azione e stessa descrizione normalizzata, vengono rimossi. Se non esiste alcun passo per le categorie selezionate, viene caricato il flusso di default. Il completamento è calcolato confrontando i passi con le azioni registrate sull’incidente; in caso di più passi con la stessa azione, il conteggio delle azioni disponibili viene consumato progressivamente in ordine di flusso.

L’interfaccia amministrativa `Admin → Flussi operativi incidenti` permette di creare, ordinare, modificare e cancellare passi. L’interfaccia utente del dettaglio incidente mostra una scheda riepilogativa con stato completato/mancante usando colori distinti; la scheda è informativa e non sostituisce gli avvisi procedurali né impedisce l’inserimento di azioni aggiuntive.

## Incident operational workflows

The data model includes `IncidentWorkflowStep`, representing an expected operational step. Each step contains an optional incident category reference (`category_id` null for the default workflow), a required action-label reference (`action_label_id`), an order position and an operational description. Action labels are still managed in `ConfigLabel` with `kind='action_label'`, keeping the action catalogue extensible.

On the incident detail page, the service computes the applicable workflow from the incident categories. If at least one selected category has configured steps, those steps are merged and identical duplicates, defined as same action and same normalised description, are removed. If no selected category has configured steps, the default workflow is loaded. Completion is calculated by comparing workflow steps with actions recorded on the incident; when several steps use the same action, available action occurrences are consumed progressively in workflow order.

The `Admin → Incident operational workflows` interface lets administrators create, order, edit and delete steps. The incident detail UI shows a summary card with completed/missing states using distinct colours; the card is informational and does not replace procedural warnings or prevent additional actions.

### Workflow captions, editable default flow and deadline display

Workflow-step captions are resolved from `ConfigLabel.description` first and from `ConfigLabel.value` only when no task description is configured. The `IncidentWorkflowStep.description` field is kept as an additional per-flow operational note, allowing administrators to reuse the same action label multiple times with different context.

On fresh installations the bootstrap creates an editable default workflow with five steps: initial information, analysis, CSIRT notification, DPO notification and closure. The default workflow is stored in the same `incident_workflow_step` table with `category_id = NULL`; it is not hard-coded in the UI and can be changed, extended or reduced from the administration page.

For each workflow step whose action label has `max_completion_hours > 0`, `incident_workflow_status()` computes the due timestamp and remaining time from the incident initial-information timestamp, using the same reference logic as deadline notifications. The incident page displays these values only while the workflow step is still missing. Completed steps do not show deadline/remaining-time details anymore. A missing step is marked as critical when the remaining time is less than or equal to zero; the status remains informational and does not block manual completion or attachment/notification choices.

### Aggiornamento 0.2.1 - Workflow interattivo nella pagina incidente

La sezione degli avvisi procedurali è stata ricollocata subito sotto la sezione delle operazioni previste, in modo da mostrare all’operatore lo stato del workflow e i vincoli procedurali prima della scheda principale. Gli elementi del workflow esposti nella pagina incidente includono l'identificativo della label azione associata e sono resi attivabili da mouse e tastiera. L'attivazione scorre alla sezione Azioni e preseleziona la label dell'azione corrispondente, senza salvare automaticamente alcun dato: l'utente conserva il controllo su data, persona, descrizione, conseguenze e allegati.


## Backup applicativi
La versione corrente introduce un sottosistema di backup configurabile da **Admin → Backup**. Il modello `BackupJob` contiene abilitazione, espressione cron-like, categorie incluse, destinazione, parametri POSIX/S3, preferenza di notifica e ultimo esito. La generazione produce archivi `tar.gz` con manifest `backup.json`; le categorie sono `incidents`, `database`, `templates`, `logos` e `uploads`. Se tutte sono selezionate l’archivio è trattato come full backup applicativo. Lo scheduler interno verifica i job abilitati a granularità di minuto; in deployment multi-replica è raccomandato eseguire lo scheduler in una sola replica o introdurre locking distribuito dedicato.

## Application backups
The current version adds a configurable backup subsystem under **Admin → Backup**. The `BackupJob` model stores enablement, cron-like expression, included categories, destination, POSIX/S3 parameters, notification preference and last status. Backup generation creates `tar.gz` archives with a `backup.json` manifest; categories are `incidents`, `database`, `templates`, `logos` and `uploads`. When all categories are selected the archive is treated as an application full backup. The internal scheduler checks enabled jobs with minute granularity; in multi-replica deployments run the scheduler on a single replica or add dedicated distributed locking.

## Aggiornamento 0.2.1 - Ricerca nella rubrica destinatari esterni

La gestione della rubrica `ExternalRecipient`, sia dal menu Admin sia dal menu Impostazioni per utenti `writer`, espone un filtro testuale `q`. Il filtro viene applicato ai campi `name`, `email` e `notes` con matching case-insensitive e il template `admin_external_recipients.html` mantiene il parametro nelle azioni di modifica, salvataggio e cancellazione. La modifica non introduce nuove tabelle né migrazioni: utilizza il modello esistente e mantiene invariati audit, export/import e controlli di unicità sull'e-mail.

## Aggiornamento 0.2.1 - Modelli incidente e gestione utenti

La release introduce la tabella `incident_template`, usata per memorizzare profili di bootstrap degli incidenti. I modelli contengono solo dati iniziali e associazioni anagrafiche, non azioni né documenti. La pagina `Admin → Modelli incidente` permette CRUD completo e creazione da incidente esistente. La form di nuovo incidente può caricare un modello e imposta comunque `start_date` e `start_time` al momento corrente.

La cancellazione utenti è stata resa più robusta riallineando la sequence PostgreSQL della tabella `audit_log` prima dell’inserimento dell’evento di audit. La pagina `Admin → Utenti` supporta ora filtro testuale su username, nome, email, backend e ruolo.

## Aggiornamento 0.2.1 - Correzione sequence audit nelle operazioni utenti

Le operazioni di aggiunta, modifica e cancellazione utenti registrano eventi nella tabella `audit_log`. In installazioni PostgreSQL ripristinate da full import, restore o migrazioni con ID espliciti, la sequence della tabella `audit_log` poteva restare disallineata e provocare l'errore `duplicate key value violates unique constraint "audit_log_pkey"` durante le operazioni sugli utenti. La gestione audit ora riallinea la sequence con una connessione separata e persistente prima degli inserimenti critici e riprova l'inserimento audit se viene rilevata una collisione sulla chiave primaria. La correzione si applica anche alle altre funzioni che usano il registro audit.

## Aggiornamento 0.2.1 - Full import con ricostruzione dello schema database

La funzione `import_full()` valida prima l'archivio di export completo e poi richiama `rebuild_database_for_full_import()`, che esegue rollback della sessione corrente, rimozione della sessione scoped, `db.drop_all()`, `db.create_all()` e commit dello schema vuoto. Solo dopo questa ricostruzione vengono importate le righe con ID espliciti e le relazioni molti-a-molti. La scelta rende il Full import coerente con una semantica di ripristino totale: non rimangono dati applicativi precedenti, vincoli o sequence PostgreSQL disallineate. I file contenuti nell'export continuano a essere ripristinati nelle directory persistenti configurate; la manutenzione di file orfani non referenziati resta responsabilità delle procedure operative di storage.
### Correzione sequence utenti 0.2.1

Gli inserimenti nella tabella utenti eseguono un riallineamento preventivo della sequence PostgreSQL `user.id` prima delle creazioni critiche. La creazione manuale da `Admin → Utenti` gestisce inoltre una collisione `user_pkey` con rollback, riallineamento persistente e reinserimento del record. Questo rende sicuri gli inserimenti dopo full import distruttivi, restore o import con chiavi primarie esplicite.

## Aggiornamento 0.2.1 - Riallineamento sequence PostgreSQL generalizzato

La protezione contro collisioni di chiave primaria PostgreSQL non è più limitata a singole tabelle. Il progetto introduce una funzione di introspezione dei metadati SQLAlchemy che individua tutte le tabelle applicative con colonna `id` intera e riallinea la sequence associata tramite `pg_get_serial_sequence` e `setval`. La procedura viene usata dopo Full import/restore e come recupero generalizzato in caso di `duplicate key value violates unique constraint`.

Questa scelta riduce il rischio di regressioni quando vengono aggiunte nuove entità applicative: se la tabella è dichiarata nei modelli SQLAlchemy con chiave primaria intera standard, viene inclusa automaticamente nel riallineamento globale. Le tabelle associative con chiave composta, prive di sequence, restano escluse.



## Aggiornamento 0.2.1 - Riferimento incidente obbligatorio

Il modello applicativo considera il campo `Incident.reference` obbligatorio. La validazione viene eseguita nella creazione e nella modifica degli incidenti, con attributo HTML `required` e controllo server-side. Le migrazioni leggere e il Full import normalizzano eventuali record storici con riferimento nullo o vuoto usando un valore tecnico `Incidente #<id>`, evitando dati incompleti dopo import di archivi precedenti.


## Versione 0.2.1 - Workflow condizionali e provisioning utenti

La tabella `incident_workflow_step` include il flag booleano `personal_data_only`. Quando il flag è attivo, `workflow_steps_for_incident()` mantiene lo step nel flusso amministrativo ma lo esclude dalle operazioni previste se `Incident.personal_data` è falso. La chiave di deduplica include anche questo flag per evitare collisioni tra step ordinari e step condizionali.

Il provisioning automatico LDAP/SSO crea gli utenti con ruolo predefinito `disabled` quando previsto dalla configurazione. Dopo il commit del nuovo utente, `notify_admin_disabled_user_created()` tenta un invio SMTP best-effort all’indirizzo dell’utente locale `admin` o, in fallback, al primo utente con ruolo admin. La mail contiene dati identificativi dell’utente creato e il link diretto `/admin/users`, costruito a partire da `application_external_url`. Errori SMTP vengono loggati ma non interrompono il flusso di login/provisioning.

## Versione 0.2.1 - Hardening sequence step workflow

L’inserimento degli step nei flussi operativi usa un riallineamento preventivo della sequence PostgreSQL `incident_workflow_step.id`. Il percorso di salvataggio intercetta inoltre eventuali collisioni duplicate-key residue, ricostruisce l’oggetto dopo rollback e ritenta l’inserimento con sequence riallineata. Questo completa la protezione post Full import/restore per la gestione dei workflow.

## Versione 0.2.1 - Estensione workflow di default

Il bootstrap del workflow di default usa ora la sequenza: Informazione iniziale, Analisi, Notifica allo CSIRT, Notifica al DPO, Comunicazione al Garante, Comunicazione all’utente, Conclusione. Lo step Comunicazione al Garante viene creato con `personal_data_only=True`, quindi resta configurabile nel workflow ma viene considerato tra le operazioni previste solo per incidenti in cui è indicato il coinvolgimento di dati personali.

Per installazioni già esistenti, `ensure_default_workflow_required_steps()` aggiunge in modo conservativo i due step mancanti al flusso di default senza cancellare o riscrivere personalizzazioni amministrative; se uno step verso il Garante è già presente, il flag `personal_data_only` viene riallineato a vero.

## Aggiornamento 0.2.1 - Frecce negli step workflow e versione applicativa

La pagina del singolo incidente visualizza gli step delle operazioni previste con una freccia di sequenza quando il workflow è ordinato tramite il campo `position`. Il template `incident_detail.html` aggiunge l'indicatore tra due step consecutivi e `style.css` ne definisce il layout responsive. I metadati runtime dell'applicazione usano la versione normalizzata `0.2.1` e il build `2026051901`, visibili in Info → Applicazione e configurabili tramite `APP_VERSION` e `APP_BUILD`.

## Aggiornamento 0.2.1 - Cancellazione incidenti con stati deadline collegati

La funzione `incident_delete()` non elimina più direttamente solo il record `Incident`: usa `delete_incident_with_related_state()`, che rimuove prima i record `DeadlineNotificationState` collegati tramite `incident_id` e poi elimina l'incidente. Il modello dichiara inoltre la relazione `Incident.deadline_notification_states` con cascade applicativa e il vincolo `ForeignKey('incident.id', ondelete='CASCADE')` per i nuovi schemi. La cancellazione esplicita resta necessaria per database esistenti nei quali il vincolo PostgreSQL è stato creato da versioni precedenti senza `ON DELETE CASCADE`.

### Conferma destinatario per notifiche manuali
Le notifiche non schedulate con destinatario libero richiedono una conferma esplicita prima dell’invio. Il template di anteprima valorizza un campo `recipient_confirmed` solo dopo conferma dell’operatore; la route di invio verifica lato server tale valore e, in assenza di conferma, reindirizza alla preview senza inviare. Le notifiche con destinatario automatico da configurazione applicativa non sono soggette a questa conferma aggiuntiva.

Manual/non-scheduled notifications with a free recipient require explicit confirmation before sending. The preview template sets `recipient_confirmed` only after operator confirmation; the send route checks this value server-side and redirects to preview without delivery if it is missing. Notifications with automatically configured recipients are not subject to this additional confirmation.


## Riepilogo notifiche schedulate e protezione anti-flooding

La vista `notification_settings.html` riceve da `upcoming_scheduled_notifications()` un riepilogo delle notifiche previste nelle successive 24 ore, ordinato per ora. La funzione combina promemoria puntuali (`IncidentReminder`) non ancora inviati e slot futuri del riepilogo task in scadenza, mostrando destinatari, tipo notifica e incidente.

Il controllo opportunistico `maybe_run_deadline_notification_check()` non invia più notifiche dalle richieste web. La chiamata automatica a `run_deadline_notification_check()` e `process_due_incident_reminders()` avviene solo nel thread scheduler dedicato, protetto da lock in-process e advisory lock PostgreSQL. In questo modo deployment con più worker o repliche evitano mail duplicate nello stesso intervallo, mentre la tabella `DeadlineNotificationState` registra claim ed esiti per incidente, slot e promemoria.


### 0.2.1-27 - Blocco invio admin e autosalvataggio destinatari

Le notifiche manuali/non schedulate dalla pagina incidente ora verificano esplicitamente l'utente locale `admin`: la pagina di anteprima mostra un errore e il pulsante di invio è disabilitato; il controllo è replicato lato server nella route di invio. Per i destinatari liberi non presenti nella rubrica esterna, l'inserimento non richiede più il nome: il contatto viene creato automaticamente usando il campo `Incident.reference` come nome associato, con fallback tecnico solo se il riferimento fosse assente.


## Versione 0.2.1-28 - Avvisi procedurali basati sul workflow richiesto

La funzione `incident_procedural_status()` calcola ora gli avvisi procedurali a partire da `incident_workflow_status()`: vengono considerati solo gli step applicabili all'incidente marcati con `IncidentWorkflowStep.required=True` e non ancora completati. Ogni avviso usa `step.description` se disponibile, altrimenti la descrizione o il nome della label azione. La pagina principale continua a mostrare l'icona di pericolo per gli incidenti con `has_procedural_warnings=True`. La chiusura automatica tramite azione di conclusione continua a chiamare `incident_procedural_status()` e viene eseguita solo quando la lista degli avvisi è vuota.

## Version 0.2.1-28 - Procedural warnings based on required workflow steps

`incident_procedural_status()` now derives procedural warnings from `incident_workflow_status()`: only workflow steps applicable to the incident, marked with `IncidentWorkflowStep.required=True` and still missing, are considered. Each warning uses `step.description` when available, otherwise the action-label description or name. The dashboard still displays the warning icon for incidents with `has_procedural_warnings=True`. Automatic closure through a closure action still calls `incident_procedural_status()` and runs only when the warning list is empty.


## Versione 0.2.1-29 - Operazioni automatiche sulle label azione
Il modello `ConfigLabel` include il campo `automatic_operations`, usato per le label di tipo `action_label`. L'amministratore configura i tag tramite drag & drop in `admin_labels.html`; le operazioni supportate sono `close_without_warnings`, `end_breach` e `global_check`. La funzione `apply_action_automatic_operations()` applica gli effetti al momento dell'inserimento dell'azione, usando la timezone applicativa e bloccando la chiusura se restano avvisi procedurali attivi.

## Version 0.2.1-29 - Automatic operations on action labels
The `ConfigLabel` model includes the `automatic_operations` field for `action_label` rows. Administrators configure tags by drag and drop in `admin_labels.html`; supported operations are `close_without_warnings`, `end_breach` and `global_check`. `apply_action_automatic_operations()` applies the effects when an action is added, using the application timezone and blocking closure while procedural warnings remain active.


## Versione 0.2.1-30 - Leggibilità label azioni
La sezione delle label azioni in Admin → Liste configurabili è stata trasformata da tabella larga a vista a schede. Ogni label azione espone in modo separato nome, descrizione, tempo massimo, flag di esportazione e operazioni automatiche configurabili con drag & drop. La modifica è puramente di interfaccia e non altera il modello dati né la semantica delle operazioni automatiche.

## Version 0.2.1-30 - Action-label readability
The action-label section in Admin → Configurable lists has been changed from a wide table to a card layout. Each action label exposes name, description, maximum time, export flag and drag-and-drop automatic operations separately. The change is UI-only and does not alter the data model or automatic-operation semantics.


## Versione 0.2.1-31 - Controllo globale sui task
Le label azione supportano l'operazione automatica `global_check`, configurabile tramite drag & drop da Admin → Liste configurabili → Label azioni. Quando l'utente tenta di inserire un'azione con una label che contiene questo tag, `create_manual_action_safely()` invoca `workflow_global_check_blocking_message()`: il sistema individua lo step workflow applicabile associato alla label e impedisce l'inserimento se uno degli step precedenti non è ancora completato. Il controllo è lato server e quindi resta valido anche in caso di richieste manuali o interfacce personalizzate.

## Version 0.2.1-31 - Global task check
Action labels support the `global_check` automatic operation, configured by drag and drop under Admin → Configurable lists → Action labels. When a user tries to add an action whose label includes this tag, `create_manual_action_safely()` calls `workflow_global_check_blocking_message()`: the system finds the applicable workflow step associated with that label and blocks insertion if any previous step is still incomplete. The check is enforced server-side, so it also applies to manual requests or customized interfaces.



## Versione 0.2.1-32 - Condizioni workflow estese
Gli step dei flussi operativi supportano ora condizioni multiple memorizzate nel campo `IncidentWorkflowStep.conditions`. Le condizioni disponibili sono `personal_data`, `severity:<id>` e `data_type:<id>`. La valutazione è con logica AND: lo step è incluso nelle operazioni previste solo se non ha condizioni oppure tutte le condizioni sono soddisfatte dall’incidente. La UI amministrativa usa un selettore drag & drop compatto per ridurre lo spazio occupato.

## Version 0.2.1-32 - Extended workflow conditions
Operational workflow steps now support multiple conditions stored in `IncidentWorkflowStep.conditions`. Available conditions are `personal_data`, `severity:<id>` and `data_type:<id>`. Evaluation uses AND logic: a step is included in expected operations only when it has no conditions or all conditions are satisfied by the incident. The administrative UI uses a compact drag-and-drop selector to reduce page space.


## Versione 0.2.1-33 - Pulizia versione e documentazione

La versione applicativa esposta da `APP_VERSION` e dalla pagina Info è normalizzata a `0.2.1`, con build `2026051901`. Le guide utente e amministrativa sono mantenute come documentazione operativa dello stato corrente: non devono contenere banner di versione né blocchi di changelog. Le variazioni cronologiche sono centralizzate in `CHANGELOG.txt` e nelle pagine `release_notes.html` / `release_notes_en.html`.

## Version 0.2.1-33 - Version and documentation cleanup

The application version exposed by `APP_VERSION`, the Info page and the guides is normalized to `0.2.1`, with build `2026051901`. User and administrator guides are maintained as operational documentation of the current state and must not contain changelog blocks. Chronological changes are centralized in `CHANGELOG.txt` and in `release_notes.html` / `release_notes_en.html`.

## Versione 0.2.1-34 - Riallineamento guide operative

Le guide utente e amministrativa sono state ricontrollate per eliminare i banner espliciti di versione dal corpo operativo, lasciando la versione alla pagina Info, alle Note di rilascio e al CHANGELOG. Le sezioni che erano fuori dal contenitore principale della documentazione online sono state integrate come capitoli regolari.

## Version 0.2.1-34 - Operational guide alignment

The user and administrator guides were reviewed to remove explicit version banners from the operational body, leaving release identifiers to the Info page, Release notes and CHANGELOG. Sections that were outside the main online-documentation container were integrated as regular chapters.


### Scheduler notifiche deadline: deduplica persistente e timezone

Le notifiche schedulate per task con tempo massimo usano `DeadlineNotificationState` come stato persistente per incidente e slot. Prima dell'invio viene scritto un claim dello slot corrente; la chiave unica della notifica e il controllo su `last_schedule_slot` impediscono invii multipli nello stesso intervallo anche in presenza di più worker o repliche. Ogni ciclo dello scheduler rimuove gli stati orfani collegati a incidenti cancellati.

La pianificazione cron/intervallo è calcolata con `application_now()` e quindi nel fuso orario applicativo. Gli intervalli regolari sono ancorati alla mezzanotte locale del giorno corrente; gli orari cron sono interpretati come HH:MM della stessa timezone.

### Workflow step text rendering

Workflow step descriptions are stored as text, capped at 500 characters at the application boundary, and rendered with a safe linkification filter. The filter escapes all text first and only converts detected `http://` or `https://` URLs to links with `target="_blank"` and `rel="noopener noreferrer"`. Click handling on workflow cards ignores clicks originating from links, preserving both link navigation and the existing guided workflow card behaviour.

## Aggiornamento 0.2.1-36a - Bonifica criticità progettuali

Sono state chiuse le criticità emerse dall’analisi del pacchetto allegato:

- le guide operative `README.md` e `README_en.md` non espongono più il banner iniziale di versione, evitando la duplicazione con Info, Note di rilascio e CHANGELOG;
- la documentazione progettuale chiarisce che le versioni sono metadati tecnici/release e non contenuto operativo delle guide utente/amministrative;
- il filtro Jinja `linkify_text`, usato per rendere cliccabili gli URL nelle descrizioni degli step procedurali, è stato estratto da `app/__init__.py` nel modulo dedicato `app/text_filters.py` e registrato tramite `register_text_filters(app)`, riducendo l’accoppiamento dell’app factory;
- è stato aggiunto `.gitignore` per impedire il reinserimento di cache Python, ambienti virtuali, artefatti di build e dati locali;
- le directory `__pycache__` presenti nel pacchetto sono state rimosse;
- i test automatici Pytest risultano eseguiti con esito positivo nell’ambiente di verifica dopo l’installazione delle dipendenze applicative.

Questa bonifica non modifica il modello dati né le route pubbliche. La modularizzazione avviata sui filtri testuali è compatibile con ulteriori estrazioni future da `app/routes.py` verso moduli dedicati per scheduler, notifiche, workflow e amministrazione.



## Aggiornamento 0.2.1-37 - Scheduler notifiche seriale e anti-duplicazione mail

Il meccanismo di invio delle notifiche schedulate è stato rivisto per eliminare le sovrapposizioni fra più sorgenti di esecuzione. L'hook `before_app_request` non esegue più controlli automatici né invii SMTP: le notifiche schedulate vengono gestite esclusivamente dal thread daemon `cir-deadline-notification-scheduler`, avviato da `start_deadline_notification_scheduler(app)`. Il pulsante manuale in **Admin → Notifiche** resta separato e continua a richiamare il controllo esplicito richiesto dall'amministratore.

Il thread esegue in sequenza il controllo delle notifiche periodiche dei task in scadenza e il recupero dei promemoria specifici. Ogni ciclo usa il lock locale `_deadline_scheduler_lock`; nei deployment PostgreSQL viene inoltre usato il lock advisory `_CIR_SCHEDULER_LOCK_ID`, che serializza i cicli fra worker Gunicorn e repliche Kubernetes che condividono lo stesso database. L'invio SMTP delle mail schedulate passa anche dal lock `_scheduler_mail_send_lock`, così nel processo applicativo una sola mail schedulata alla volta può aprire la connessione SMTP ed essere inviata.

La deduplica persistente è stata estesa ai promemoria specifici incidente. Prima dell'invio viene scritto un claim nella tabella `deadline_notification_state` con `notification_type='incident_reminder'` e `notification_key='incident_reminder:<id>'`. Se un secondo ciclo trova già quel claim, salta l'invio. Le notifiche periodiche dei task in scadenza continuano invece a usare `notification_type='deadline_summary'`, chiave per incidente e slot pianificato calcolato nella timezone applicativa. In questo modo non vengono inviate più copie della stessa mail né più mail dello stesso tipo nello stesso periodo funzionale.

La tabella `deadline_notification_state` assume quindi il ruolo di registro anti-flooding generale dello scheduler: contiene claim preventivi, ultimo esito, slot/finestra di riferimento, destinatari e dettagli sintetici. La funzione di cleanup degli stati orfani continua a essere eseguita ad ogni ciclo per eliminare record collegati a incidenti cancellati.

## Aggiornamento 0.2.1-38 - Stato notifiche schedulate e cambio password solo locale

Lo scheduler aggiorna lo stato persistente delle mail schedulate immediatamente dopo ogni tentativo di invio, non solo al termine dell'intero ciclo. Per i promemoria specifici incidente `process_due_incident_reminders()` imposta `IncidentReminder.sent_at` o `last_error`, aggiorna il corrispondente record `DeadlineNotificationState` e committa subito l'esito del singolo messaggio. Per le notifiche periodiche dei task in scadenza `run_deadline_notification_check()` committa subito il risultato per incidente dopo `_record_deadline_notification_success()` o `_record_deadline_notification_failure()`. Questo evita che una mail già consegnata resti temporaneamente nello stato programmato e riduce il rischio di reinvio in caso di errore successivo nello stesso ciclo.

La funzione `upcoming_scheduled_notifications()` mostra ora nella pagina **Impostazioni → Notifiche** sia le notifiche previste nelle prossime 24 ore sia gli esiti recenti delle 24 ore precedenti, con colonna `Stato`. I promemoria passano a `inviata` quando `sent_at` è valorizzato oppure mostrano l'errore registrato; le notifiche deadline leggono lo stato da `deadline_notification_state`, visualizzando destinatari, slot e data di aggiornamento dell'ultimo invio. In questo modo il riepilogo amministrativo si aggiorna automaticamente dopo il passaggio dello scheduler senza richiedere reset manuali.

La voce di menu **Impostazioni → Cambio password** è visibile solo per utenti autenticati con backend `auth_provider='local'` e non LDAP. La route `/settings/password` replica il controllo lato server e rifiuta qualsiasi backend esterno, inclusi LDAP e profili SSO nel formato `sso:<profilo>`, perché tali password sono gestite dal provider di identità esterno.

## Aggiornamento 0.2.1-40 - Audit degli incidenti saltati dallo scheduler notifiche

Lo scheduler registra ora un record audit specifico ogni volta che un incidente viene conteggiato come saltato durante l'elaborazione delle notifiche. Per i riepiloghi periodici dei task in scadenza viene usato il tipo operazione `scheduler:deadline_notification_skipped`; per i promemoria specifici viene usato `scheduler:incident_reminder_skipped`.

Ogni record include l'identificativo dell'incidente, nome e riferimento quando disponibili, sorgente del ciclo scheduler, codice motivo e descrizione leggibile. Per le notifiche deadline vengono registrati anche slot e fine finestra; per i promemoria specifici vengono registrati identificativo del promemoria e data programmata. I motivi coperti includono notifica già inviata o già presa in carico nello slot corrente, claim concorrente non acquisito, errore SMTP/destinatari assenti ed eccezioni applicative. Il record globale `scheduler:deadline_notification_check` resta un riepilogo aggregato, mentre i nuovi record permettono di capire quale incidente è stato saltato e perché.

## Aggiornamento 0.2.1-41 - Audit robusto nel controllo manuale e promemoria senza slot

Il pulsante manuale **Esegui controllo ora** della sezione **Controllo scadenze azioni** richiama `run_deadline_notification_check(force=True, source='manual_button')`. Prima del calcolo dello slot vengono ora riallineate tutte le sequence applicative PostgreSQL tramite `align_all_table_sequences()`, così eventuali database ripristinati o importati non mantengono sequence arretrate.

La funzione centrale `audit_log()` è stata rafforzata: usa `db.session.no_autoflush` durante la ricerca dell'ultimo record collassabile, riallinea `audit_log` prima dell'inserimento e forza `db.session.flush([log])` subito dopo l'add. Se PostgreSQL segnala ancora `audit_log_pkey`, la sessione viene riportata a uno stato valido, la sequence viene riallineata e il record audit viene ricostruito e reinserito. La collisione viene quindi gestita nel punto di inserimento dell'audit e non viene più rinviata al commit finale del controllo manuale.

Per i promemoria specifici incidente la funzione `_claim_incident_reminder()` non usa più lo slot programmato come blocco. Il blocco funzionale rimane soltanto `IncidentReminder.sent_at`: un promemoria con `sent_at` valorizzato è considerato inviato, un promemoria con `sent_at` nullo resta eleggibile anche se esistono record tecnici storici in `deadline_notification_state`. Il record tecnico con `notification_type='incident_reminder'` conserva solo lo stato temporaneo "promemoria in invio" e scade dopo il timeout anti-concorrenza; `last_schedule_slot` viene lasciato nullo anche dopo successo o errore, per evitare qualsiasi interpretazione a finestra/periodo.
