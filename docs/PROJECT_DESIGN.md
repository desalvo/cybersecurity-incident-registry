# Cybersecurity Incident Registry — documentazione progettuale logica

## 1. Scopo del documento

Questo documento descrive la logica applicativa, il modello dati, i flussi operativi, le autorizzazioni, le integrazioni e i requisiti tecnici dell'applicazione **Cybersecurity Incident Registry** nella sua forma corrente.

La sezione finale contiene una descrizione testuale completa, pensata per poter riprodurre da capo l'applicazione con ChatGPT o con un altro sistema di generazione codice, mantenendo tutte le funzionalità implementate fino alla build corrente.

## 2. Informazioni applicative

- Nome applicazione: Cybersecurity Incident Registry
- Versione: 0.1.0
- Build: 20260516-01
- Autore: Alessandro De Salvo <Alessandro.DeSalvo@roma1.infn.it>
- Backend: Flask con server di produzione Gunicorn
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

Gli utenti possono essere locali, LDAP o SSO. Gli utenti SSO sono identificati tramite claim configurabili restituiti dal provider OAuth2/OpenID Connect.

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

Il flusso di login implementa Authorization Code: generazione dello `state`, redirect al provider, scambio del code sul token endpoint, chiamata allo UserInfo endpoint e creazione/aggiornamento dell’utente applicativo. Gli utenti SSO creati automaticamente vengono bloccati se il ruolo assegnato è `disabled`, finché un amministratore non li abilita da **Admin → Utenti**.

### 5.4 Autorizzazioni

Le route devono proteggere le funzioni lato server, non solo nascondere i pulsanti nell'interfaccia.

- Solo `admin` accede a menu Admin e Notifiche.
- Solo `admin` e utenti con ruolo `writer` vedono e usano pulsanti di creazione, modifica, cancellazione e upload.
- `reader` legge tutto senza modificare.
- `operator` legge solo gli incidenti creati da sé.
- `disabled` viene disconnesso o rediretto con messaggio di errore.

Per ogni oggetto cancellabile, la UI deve chiedere conferma prima di procedere.

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

La lista dei placeholder deve essere visibile in ogni pagina di configurazione template.

### 7.4 Invio notifiche

Nella pagina di ciascun incidente è presente una sezione Notifiche, nascosta all'utente `admin` quando richiesto. L'utente sceglie un template e procede all'anteprima. Prima dell'invio viene sempre mostrata l'anteprima.

Regole allegati:

- se il template contiene `%REPORT%`, allegare il report PDF corrente dell'incidente
- se contiene `%DOCUMENTS%`, chiedere quali documenti allegare e impedire l'invio se nessun documento è disponibile o selezionato
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

Il controllo è implementato come esecuzione opportunistica `before_app_request`: ad ogni richiesta applicativa verifica se l'intervallo configurato è trascorso e, in caso positivo, controlla gli incidenti non chiusi. Per ogni incidente aperto e non silenziato calcola le azioni attese configurate con tempo massimo numerico maggiore di zero e non ancora registrate nella timeline. Il valore 0 rappresenta l’assenza di un tempo massimo. Il riepilogo viene inviato via SMTP solo se l'invio email per task in scadenza è abilitato globalmente e solo per incidenti con almeno una unità di personale associata; i destinatari effettivi sono gli indirizzi valorizzati del personale coinvolto (`Person.email`). Il messaggio contiene azione attesa, scadenza calcolata e tempo rimanente o superato. Il flag `Incident.deadline_notifications_muted` consente di escludere singoli incidenti dai promemoria automatici senza modificare la configurazione globale. Oggetto e corpo sono costruiti con template configurabili tramite le impostazioni `notification_deadline_subject_template` e `notification_deadline_body_template`; il rendering sostituisce placeholder nella forma `%placeholder%` con valori dinamici calcolati a runtime.

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

La documentazione utente è disponibile solo dal menu Aiuto. Deve essere estesa, divisa in capitoli, ricercabile e scaricabile in PDF.

Il menu Info contiene Applicazione con nome, versione, build e autore; l'email dell'autore è cliccabile tramite link `mailto:`.

## 13. Prompt di riproduzione completa dell'applicazione

Usa il testo seguente per chiedere a ChatGPT di ricreare l'applicazione da zero nella forma corrente.

```text
Scrivi un'applicazione web completa chiamata “Cybersecurity Incident Registry”, versione 0.1.0, build 20260516-01, autore Alessandro De Salvo <Alessandro.DeSalvo@roma1.infn.it>, da usare come registro degli incidenti informatici.

L'applicazione deve essere una web app Flask servita in produzione con Gunicorn, containerizzata con Docker basato su Debian Trixie, deployabile su Kubernetes e basata su PostgreSQL 18.4 persistente. Usa SQLAlchemy/Flask-SQLAlchemy, template Jinja2, CSS/JavaScript statici, ReportLab o equivalente per PDF, smtplib/email standard per SMTP, ldap3 per LDAP. Fornisci codice completo, Dockerfile, docker-compose.yml, manifest Kubernetes, README, documentazione utente e documentazione progettuale.

Implementa autenticazione locale e LDAP. L'utente locale admin deve essere creato solo se assente, chiamarsi admin e avere password iniziale adminpass configurabile via variabile d'ambiente. Non resettare mai la password admin ai riavvii. Usa hashing password senza limite bcrypt a 72 byte, per esempio PBKDF2-SHA256, con eventuale compatibilità legacy sicura. Gli utenti LDAP appena visti al login devono essere creati con ruolo disabled. Ruoli: admin, writer, reader, operator, disabled. Admin accede a tutto, writer legge/scrive, reader legge tutto, operator legge solo i propri incidenti, disabled non accede.

Crea un modello Incident con: creatore nome/email presi dall'utente loggato e non modificabili; nome; riferimento opzionale; descrizione; gravità configurabile; tipi di dati interessati multipli configurabili; flag dati personali; data/ora inizio; data/ora fine opzionale; categorie multiple configurabili; personale coinvolto multiplo; stato aperto/in lavorazione/chiuso; documenti allegati multipli; azioni multiple. La lista incidenti deve mostrare nome, intervallo inizio/fine, compilatore, personale, stato, durata tra prima azione registrata e conclusione dell'incidente; tutte le colonne ordinabili; conteggio totale filtrato o totale visibile. Supporta ricerca per data, parola chiave e label. Supporta clonazione incidente da lista e dettaglio. Supporta cancellazione incidenti con conferma e solo per utenti con permesso di scrittura/admin.

Crea azioni con data/ora, descrizione opzionale, persona precompilata con utente corrente ma modificabile, label azione configurabile, allegati multipli. Le azioni devono essere modificabili/cancellabili con conferma e permessi. Non assegnare mai manualmente ID: lascia generare al DB e riallinea sequence PostgreSQL all'avvio e dopo import.

Crea liste configurabili per gravità, dati interessati, categorie, label azioni e personale. I valori iniziali includono gravità molto bassa, bassa, media, alta, critica; dati password e dati personali; categorie furto di credenziali, phishing, SPAM, altro; label azioni 01-informazione iniziale, 02-analisi, 03-blocco, 04-comunicazione allo CSIRT, 05-comunicazione al DPO, 06-comunicazione al Garante della Privacy, 07-notifica all'utente, 08-conclusione. Le liste configurabili sono raggruppate per categoria/tipo. Permetti aggiunta e cancellazione inserendo solo il nome della label nella sezione corretta; la cancellazione rimuove i riferimenti dagli incidenti. La gestione anagrafica personale richiede solo nome ed email, senza Categoria/Gruppo. Nei form incidente usa drag & drop per categorie, dati interessati, personale e raccomandazioni, con destinazioni adiacenti alle sorgenti e label raggruppate per tipo dove applicabile. Le checkbox devono usare uno stile compatto per non aumentare eccessivamente l’ingombro delle tabelle e dei pannelli amministrativi.

Implementa logo applicativo caricato da admin, mostrato nella barra superiore e nella login con altezza massima 2 cm. Menu accessibili con tastiera, ARIA, focus visibile, dropdown leggibili e z-index corretto. UI responsive/mobile con menu compatto, lista incidenti a schede e form touch-friendly. Login centrata e senza informazioni sull'admin di default. Redirigi alla login se non autenticato. Mostra nome utente corrente a destra nella barra.

Menu: Incidenti, Report, Export, Admin solo admin, Notifiche solo admin, Impostazioni, Info, Aiuto. La voce `Nuovo incidente` non è presente nella barra dei menu; il relativo pulsante resta nella pagina principale degli incidenti. Nel menu Admin includi gestione utenti, LDAP, SSO, liste configurabili, personale, logo. Nel menu Impostazioni includi cambio password e impostazioni SMTP/notifiche. Nel menu Info includi Applicazione con nome, versione, build e autore, con email autore cliccabile mailto. Nel menu Aiuto mostra documentazione estesa, capitoli, ricerca e download PDF.

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
- Dopo cambio password admin, il riavvio non ripristina `adminpass`.
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

La versione PDF della documentazione è generata dalla rotta `GET /aiuto/pdf`, usando lo stesso template HTML della guida online. La rotta converte il contenuto documentale in PDF ReportLab, rimuovendo gli elementi interattivi non necessari come indice di navigazione e controlli di ricerca. Il PDF resta scaricabile dal menu `Aiuto -> Scarica documentazione PDF` e dal pulsante presente nella guida.

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

Il sottosistema delle notifiche automatiche per task in scadenza usa il fuso orario applicativo configurato tramite `application_timezone` in **Admin → Altre configurazioni**. La funzione di formattazione centralizzata delle date/ore usate nei template di scadenza aggiunge il nome della timezone configurata e viene applicata a `%initial_information_at%`, `%pending_actions%` e `%generated_at%`. Anche il controllo scheduler opportunistico calcola `now` attraverso l’orario applicativo, mantenendo coerente il confronto con le date naive salvate dagli inserimenti utente.



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

English: `incident_pdf()` now produces a cover area with the application logo and the configured custom logo, a concise initial table of contents, highlighted section headings and a canvas callback for page numbers. Layout uses `CondPageBreak` and `keepWithNext` on headings so section titles are not separated from their content. Tables use alternating rows, highlighted headers and content-oriented column widths.

## Aggiornamento 0.1.0-100 - Report PDF incidenti: loghi

La funzione `incident_pdf` usa `_report_logos_table` per comporre i loghi di prima pagina. La tabella non usa più la dicitura `Logo custom`: il logo statico applicativo e l'eventuale logo caricato da GUI sono entrambi presentati come logo applicativo. Se la configurazione `logo_path` è vuota o punta a un file non esistente, il logo da GUI viene omesso senza generare celle vuote nel PDF.
