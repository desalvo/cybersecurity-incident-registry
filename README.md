# cybersecurity-incident-registry

Applicazione Flask/Gunicorn per registro incidenti informatici con PostgreSQL.

## Avvio locale

```bash
docker compose up --build
```

Aprire `http://localhost:8000`. L'utente locale iniziale è `admin`; la password iniziale deriva da `ADMIN_INITIAL_PASSWORD` solo alla prima creazione dell'utente. Ai riavvii non viene resettata.

## Caratteristiche principali

- PostgreSQL persistente.
- Login locale, LDAP configurabile con filtro utenti e login SSO/OAuth2/OpenID Connect configurabile da interfaccia Admin.
- Ruoli: admin, operator, reader, writer, disabled.
- Drag & drop per categorie, dati interessati, personale e raccomandazioni, con destinazioni adiacenti alle palette.
- Upload/download documenti.
- Export CSV, export completo compresso con tutti i campi reali del database, report PDF professionale con tabelle wrappate e grafico azioni nel tempo.
- Seed idempotente con lock PostgreSQL per evitare duplicate key e WORKER_BOOT_ERROR.
- Hash password PBKDF2-SHA256 con pre-hash SHA256 per evitare il limite bcrypt di 72 byte.


## Login SSO / OAuth2

Gli amministratori possono configurare l’accesso federato da **Admin → SSO**. La configurazione include:

- abilitazione/disabilitazione del login SSO;
- nome del provider visualizzato nella pagina di login;
- authorization endpoint, token endpoint e userinfo endpoint;
- client ID e client secret;
- scope OAuth2/OpenID Connect, di default `openid email profile`;
- nomi dei claim da usare per username, email, nome e identificativo univoco;
- creazione automatica degli utenti SSO e ruolo predefinito, di default `disabled`.

Il redirect URI da registrare sul provider viene mostrato nella pagina Admin → SSO. La stessa pagina include il pulsante **Controlla configurazione**, che usa i valori presenti nella form anche prima del salvataggio e verifica parametri obbligatori, endpoint di autorizzazione, token endpoint, UserInfo endpoint, scope e claim principali. Il controllo è non distruttivo: non crea utenti e non completa un login reale. Per la prova completa è disponibile anche **Avvia test login interattivo**, che usa il normale flusso OAuth2 con redirect verso il provider. Il login locale e LDAP restano disponibili. Gli utenti SSO creati automaticamente possono essere abilitati o promossi da **Admin → Utenti**.

## Kubernetes

Applicare i manifest in `k8s/` dopo aver pubblicato l'immagine container.

## Build container

```bash
docker build --no-cache -t cybersecurity-incident-registry:latest .
docker compose up --build
```

Questa versione usa `python:3.11-slim-bookworm`, installa le librerie native richieste da `psycopg2`, `reportlab` e `matplotlib`, usa Gunicorn come server Flask di produzione e include `.dockerignore` per evitare di copiare file locali nel build context.

## Aggiornamento container Debian Trixie

Il Dockerfile usa ora `python:3.12-slim-trixie`, basato su Debian 13 Trixie. Le dipendenze native necessarie per PostgreSQL, ReportLab, Matplotlib e healthcheck vengono installate con `apt` e le dipendenze di build vengono rimosse dopo `pip install`.

Build:

```bash
docker compose build --no-cache
```

Avvio:

```bash
docker compose up -d
```

## Fix Docker build Debian Trixie

Il Dockerfile usa `python:3.12-slim-trixie` e installa solo dipendenze runtime disponibili in Debian Trixie. Le dipendenze Python vengono installate solo da wheel binarie (`--only-binary=:all:`), evitando compilazioni native e pacchetti come `build-essential`/`libpq-dev`, che erano la causa più probabile del fallimento allo step 4.

Build:

```bash
docker build --no-cache -t cybersecurity-incident-registry:trixie .
```


## Aggiornamento incluso
- Cancellazione incidenti da lista e dettaglio per ruoli admin/writer.
- Gestione personale semplificata: aggiunta solo con nome ed email; rimosso il campo Categoria/Gruppo.
- Cancellazione del personale con rimozione automatica dai riferimenti negli incidenti.

## Aggiornamento schema

All'avvio l'applicazione esegue migrazioni leggere e idempotenti. Se un database esistente non contiene la colonna `incident.reference`, questa viene aggiunta automaticamente senza cancellare dati.


## Informazioni applicazione
- Nome: Cybersecurity Incident Registry
- Versione: 0.1.0
- Build: 20260516-01
- Autore: Alessandro De Salvo <Alessandro.DeSalvo@roma1.infn.it>

Le informazioni sono visibili da **Info → Applicazione** e configurabili via variabili d’ambiente `APP_NAME`, `APP_VERSION`, `APP_BUILD`, `APP_AUTHOR`, `APP_AUTHOR_EMAIL`.

## Notifiche CSIRT/DPO

Dal dettaglio di ogni incidente è disponibile la sezione **Notifiche** con i pulsanti **Notifica CSIRT** e **Notifica DPO**.
Prima dell'invio viene mostrata un'anteprima del messaggio. L'invio usa il mittente dell'utente loggato, allega il report PDF aggiornato e aggiunge automaticamente un'azione all'incidente con label:

- `04-comunicazione allo CSIRT` per CSIRT
- `05-comunicazione al DPO` per DPO

Dal menu **Notifiche** un amministratore può configurare:

- email CSIRT e DPO;
- parametri SMTP;
- template separati per CSIRT e DPO;
- promemoria automatici di scadenza delle azioni.

Nei template sono disponibili i segnaposto `%DATI%`, `%CATEGORIE%`, `%DATA%`, `%DATI_PERSONALI%`, `%REPORT%`.

### Promemoria automatici scadenze azioni

Nelle label azioni, amministrate da **Admin → Liste configurabili**, sono disponibili il campo numerico **Tempo massimo (ore)**, espresso in ore e con default 0, e il campo **Esportabile per default**. Il valore 0 significa che per quella label non esiste alcun tempo massimo e la label non viene considerata nei promemoria. Se il valore è maggiore di zero, il sistema considera l’azione come attività da completare entro quel numero di ore a partire dalla prima azione di tipo **informazione iniziale** dell’incidente.

Nelle impostazioni notifiche sono configurabili:

- abilitazione/disabilitazione dei promemoria automatici;
- intervallo di controllo in ore e minuti;
- esecuzione manuale immediata del controllo.

A ogni controllo, per ogni incidente aperto e non silenziato, l’applicazione cerca le label azione con tempo massimo configurato che non sono ancora presenti nella timeline dell’incidente. L’invio delle email può essere disabilitato totalmente da **Admin → Notifiche** con l’opzione dedicata **Abilita invio email per task in scadenza**. Se l’invio è abilitato ed esistono azioni mancanti, la mail viene inviata solo quando nell’incidente è selezionata almeno una unità di personale associata; i destinatari effettivi sono le persone coinvolte con indirizzo e-mail valorizzato. In assenza di personale selezionato l’incidente viene saltato e non viene inviata alcuna mail. Dalla pagina di dettaglio di ogni incidente è possibile selezionare **Silenzia notifiche email per task in scadenza** per escludere solo quello specifico incidente dai promemoria automatici. Il testo delle email di scadenza task è configurabile nella stessa pagina tramite template di oggetto e corpo con placeholder nella forma `%nome_placeholder%`; la pagina mostra l’elenco dei placeholder disponibili e una preview con dati dimostrativi prima dell’invio reale.

## Aiuto

Il menu **Aiuto** mostra una documentazione sintetica d'uso dell'applicazione.

### Template email task in scadenza

In **Admin → Notifiche** sono disponibili i campi **Oggetto** e **Corpo del messaggio** per personalizzare le email dei task in scadenza. I placeholder supportati sono mostrati nella pagina e includono, tra gli altri, `%incident_name%`, `%incident_reference%`, `%incident_status%`, `%initial_information_at%`, `%pending_actions%`, `%pending_actions_count%`, `%recipients%`, `%generated_at%` e `%application_name%`. Il pulsante **Anteprima template task** genera una preview usando dati dimostrativi e non invia alcuna email.

## Documentazione progettuale

Il pacchetto include `docs/PROJECT_DESIGN.md`, che descrive l'architettura logica, il modello dati, i flussi applicativi, le regole di autorizzazione, il sistema notifiche, export/reportistica e una sezione testuale completa per riprodurre l'applicazione da capo mantenendo le funzionalità della build corrente.


## Aggiornamento PostgreSQL 18.4 e fix creazione incidenti

Questa build usa PostgreSQL `18.4` nel `docker-compose.yml` e include anche un manifest Kubernetes dedicato in `k8s/postgresql.yaml` con immagine `postgres:18.4`.

La creazione di nuovi incidenti è stata resa più robusta:

- gli ID non vengono mai assegnati dall'applicazione;
- la sequence PostgreSQL della tabella `incident` viene riallineata prima dell'inserimento;
- i valori provenienti dai campi drag & drop vengono deduplicati prima di popolare le tabelle associative `incident_categories`, `incident_data_types`, `incident_people` e `incident_recommendations`;
- questo evita errori `duplicate key value violates unique constraint` sia sulla tabella degli incidenti sia sulle relazioni many-to-many quando la UI invia accidentalmente lo stesso valore più volte.

Per ricostruire il container:

```bash
docker compose down
docker compose build --no-cache
docker compose up
```



## Date e ore degli incidenti

Nella form degli incidenti la data e l’ora di inizio sono campi separati (**Data inizio** e **Ora inizio**). Anche la fine dell’incidente usa campi separati (**Data fine** e **Ora fine**). All’avvio l’applicazione migra automaticamente i database esistenti popolando i nuovi campi separati a partire dalle colonne storiche `start_at` ed `end_at`; dopo la migrazione le colonne legacy non più usate vengono rimosse dal database. Il codice espone proprietà compatibili per report e filtri, calcolate dai nuovi campi granulari. La pagina principale e le statistiche ordinano e filtrano usando le colonne reali `start_date` e `start_time`, evitando query SQL sulle proprietà calcolate `start_at`/`end_at`.

Nei mapping dei moduli PDF sono disponibili i campi granulari `start_date`, `start_time`, `end_date`, `end_time`; le etichette compatibili `start_at`/`end_at` restano disponibili come valori calcolati combinati, senza colonne legacy nel database.


## Durata degli incidenti

La durata operativa degli incidenti è calcolata esclusivamente dal momento della prima azione registrata fino alla conclusione dell’incidente, rappresentata da `end_date` e `end_time` / proprietà compatibile `end_at`. I campi `start_date` e `start_time` descrivono l’inizio dichiarato o noto dell’evento e restano usati per filtri, ordinamenti temporali e periodo visualizzato, ma non partecipano al computo della durata. Se un incidente non ha azioni o non ha data/ora fine, la durata è considerata non disponibile. Lo stesso criterio è usato nella lista principale, nell’ordinamento per durata, nel CSV e nelle statistiche/PDF statistiche.

## Generazione moduli PDF compilabili

L’applicazione genera moduli partendo direttamente dal PDF originario caricato in **Moduli → Configurazione**. Il PDF deve contenere campi AcroForm compilabili: i nomi dei campi da mappare coincidono con i nomi presenti nel modulo PDF. Non viene più creato né usato un template XML intermedio.

Il flusso amministrativo è:

1. caricare un PDF compilabile da **Moduli → Configurazione**;
2. verificare l’elenco dei campi AcroForm rilevati;
3. salvare il PDF originario come template;
4. associare i campi database dell’incidente ai campi PDF tramite drag & drop. Le sezioni **Campi database incidenti** e **Campi del template** hanno barre di scorrimento verticali per gestire liste lunghe senza perdere il contesto della pagina.

Dalla pagina di dettaglio dell’incidente, gli utenti abilitati selezionano uno o più template PDF facendo click sulle schede dei template, evidenziate con colore diverso quando selezionate, e generano un’anteprima. Alla conferma, il PDF compilato viene registrato come documento allegato all’incidente. Nella configurazione di ciascun template l’amministratore può scegliere il font di compilazione, tra Helvetica e Times Roman, e la dimensione da usare, tra 8 e 16 pt. Durante la compilazione l’applicazione usa tutta la larghezza disponibile, applica il font e la dimensione configurati e genera un **nuovo PDF finale statico**: i valori compilati sono disegnati nel contenuto delle pagine e i campi AcroForm vengono rimossi. La resa dei campi risolve anche widget annidati o privi di nome diretto usando il nome completo del campo AcroForm, tiene conto del CropBox della pagina, ignora i widget nascosti e raccoglie i widget sia dalle annotazioni di pagina sia dall’albero AcroForm. In questo modo vengono gestiti anche PDF prodotti da editor che non sincronizzano completamente `/Annots` e `/Fields`. Per evitare campi mancanti, la generazione accetta anche la corrispondenza tra nome gerarchico completo e nome terminale del campo e centra verticalmente i valori nei campi piccoli. Il file prodotto non contiene più campi modificabili e può essere visualizzato correttamente anche da viewer PDF che non rigenerano le apparenze dei moduli.

I template PDF sono conservati nella directory persistente `FORM_TEMPLATE_DIR` e, da questa versione, anche in una copia binaria nel database nella tabella `form_template_binary`. All’avvio l’applicazione verifica la directory dei template e ripristina automaticamente dal database eventuali PDF mancanti: in questo modo un riavvio del container o una configurazione incompleta del volume non fa più sparire i modelli dalla configurazione moduli. I template sono inclusi nell’export/import completo insieme alle mappature e ai metadati dei campi PDF rilevati, così l’archivio è autosufficiente per rigenerare i moduli dopo un ripristino. Dalla configurazione moduli è possibile sostituire il PDF originario di un template esistente: la sostituzione viene accettata solo se il nuovo PDF contiene esattamente gli stessi campi AcroForm compilabili del modello precedente. In questo caso vengono mantenuti nome template, mapping dei campi, font e dimensione configurati.

## Campi amministrativi disponibili nei moduli

Oltre ai dati dell’incidente, nei mapping dei moduli sono disponibili anche:

- `security_owner`: nome del titolare della sicurezza, configurato in **Admin → Dati titolare**;
- `security_owner_role`: ruolo del titolare della sicurezza, configurato in **Admin → Dati titolare**;
- `structure`: nome della struttura, configurato in **Admin → Struttura**;
- i dati del responsabile della sicurezza configurati in **Admin → Dati responsabile**.

## Nota PostgreSQL 18.4

Nei manifest Docker Compose e Kubernetes il volume persistente PostgreSQL è montato su `/var/lib/postgresql`, come richiesto per l'immagine `postgres:18.4`. La directory dati effettiva viene gestita dall'immagine ufficiale all'interno del volume, evitando problemi di permessi o inizializzazione quando si monta direttamente `/var/lib/postgresql/data`.


## Aggiornamento dati titolare, responsabile e raccomandazioni

Questa versione aggiunge ai dati disponibili per ciascun incidente anche le informazioni amministrative centralizzate relative al titolare e al responsabile della sicurezza:

- **Titolare**: configurabile da `Admin -> Dati titolare`.
- **Responsabile**: configurabile da `Admin -> Dati responsabile`.
- **Email responsabile**: configurabile da `Admin -> Dati responsabile`.
- **Telefono responsabile**: configurabile da `Admin -> Dati responsabile`; il valore predefinito è `-`.
- **Funzione responsabile**: configurabile da `Admin -> Dati responsabile`.

Nella pagina dell’incidente vengono inoltre mostrati:

- **Conseguenze**, derivate automaticamente dalle categorie dell’incidente e dai tipi di dati interessati.
- **Misure adottate**, derivate automaticamente dalla lista cronologica delle azioni intraprese.
- **Raccomandazioni**, selezionabili tra le voci configurate da `Admin -> Raccomandazioni` mediante lo stesso meccanismo drag & drop usato per categorie, dati interessati e personale. Le raccomandazioni disponibili sono trascinate nella sezione “Raccomandazioni selezionate”; un clic sulla chip selezionata la rimuove dalla scheda.

I campi sono disponibili anche per la generazione dei moduli PDF tramite il modulo `form_generation` e sono inclusi nell’export completo. Il full export serializza tutte le colonne effettive delle tabelle applicative e delle tabelle di relazione, includendo nel manifest anche lo schema dei campi esportati.


## Aggiornamento campo Destinatario
Ogni incidente include il campo opzionale **Destinatario**, usato per indicare l'utente destinatario delle comunicazioni di data breach. Se il campo non viene compilato, l'applicazione usa automaticamente il valore di **Riferimento**. Il campo è disponibile nelle form, nei mapping dei moduli PDF e nei template tramite il campo database `recipient`.

## Export completo

L’export completo produce un archivio `tar.gz` autosufficiente. Il file `export.json` contiene tutte le colonne reali delle tabelle applicative SQLAlchemy, le tabelle di relazione molti-a-molti e una sezione `schema` con l’elenco dei campi esportati per ogni tabella. Per gli incidenti, i campi temporali granulari `start_date`, `start_time`, `end_date` ed `end_time` sono sempre serializzati esplicitamente, con fallback dai valori compatibili `start_at`/`end_at` quando necessario; nel manifest sono presenti anche gli alias `start_at` ed `end_at` per compatibilità con script o import di versioni precedenti. L’archivio include inoltre i file fisici collegati: documenti degli incidenti, allegati delle azioni, logo e template PDF dei moduli. L’import completo filtra e converte i campi in base al modello corrente, così gli export restano compatibili anche in presenza di campi aggiunti da versioni successive.

## Template moduli
I template moduli predefiniti basati su XML/DOCX sono stati rimossi. Dal menu **Moduli → Configurazione** è possibile caricare PDF AcroForm compilabili, salvarli come template originari e cancellare template esistenti con conferma.

## Aggiornamento documenti allegati

Nella sezione Documenti della pagina di dettaglio incidente viene mostrata, per ogni documento allegato, anche la data e ora di upload.




- Rimossi i campi legacy database start_at/end_at: il sistema utilizza ora esclusivamente start_date/start_time/end_date/end_time con proprietà compatibili applicative.

### Campi dinamici e azioni esportabili nei moduli PDF

Nella configurazione dei moduli PDF, tra i **Campi database incidenti**, sono disponibili anche i campi calcolati dinamicamente `awareness_date` (**Data venuta a conoscenza**) e `awareness_time` (**Ora venuta a conoscenza**). I due valori sono ricavati dalla prima azione cronologica dell’incidente la cui label contiene “informazione iniziale”. Se l’azione non è presente, il campo compilato resta vuoto.

Il campo derivato `measures_adopted` include solo le azioni marcate come **exportable**. Per ogni azione esportabile la stringa compilata mostra prima il testo dell’azione, composto da label ed eventuale descrizione, e poi la data e ora dell’azione nel formato `YYYY-MM-DD HH:MM`. Il valore iniziale del flag sulle nuove azioni deriva dal campo **Esportabile per default** configurato sulla label azione in **Admin → Liste configurabili**; in assenza di label configurata resta il fallback sulle parole chiave storiche “notifica”, “comunicazione”, “informazione iniziale”, “analisi” o “conclusione”. Il flag può essere modificato dalla tabella Azioni nel dettaglio dell’incidente.

## Avvisi procedurali

Nel dettaglio incidente il sistema mostra avvisi procedurali quando non risultano registrate le azioni previste. In particolare, la notifica all’utente è richiesta: l’avviso viene visualizzato se nella lista delle azioni effettuate non è presente una label o descrizione riconducibile a una notifica all’utente. Gli avvisi CSIRT e DPO restano sempre verificati, mentre l’avviso per il Garante Privacy è subordinato al coinvolgimento di dati personali. Nella lista della pagina principale gli incidenti con almeno un avviso procedurale pendente sono evidenziati con un simbolo di pericolo accanto al nome, con tooltip riepilogativo degli avvisi presenti. La sezione "Avvisi procedurali" è collocata nella parte alta del dettaglio incidente, subito dopo il riepilogo principale, in modo che le verifiche operative pendenti siano visibili prima delle sezioni dati titolare, conseguenze, azioni, documenti e moduli.


## Documentazione utente e logo applicativo

La guida utente è disponibile dal menu **Aiuto -> Documentazione**. È stata riscritta come manuale operativo completo, con capitoli separati, esempi dettagliati passo-passo, checklist e descrizione delle principali funzioni di gestione incidenti. La pagina è ricercabile: il campo di ricerca filtra in tempo reale i capitoli della documentazione online.

Dal menu **Aiuto -> Scarica documentazione PDF** è possibile scaricare la stessa documentazione in formato PDF.

L’applicazione include inoltre un logo pittorico statico che rappresenta un cybersecurity incident registry. Il logo è mostrato sempre nella pagina di login e, nelle viste desktop/non mobile, anche nella barra del menu principale; resta disponibile anche la variante decorativa in basso a destra nelle pagine interne. Non sostituisce e non modifica il logo custom configurabile da **Admin -> Logo**, che continua a funzionare come nelle versioni precedenti. Nella versione mobile il logo pittorico della barra e quello decorativo sono nascosti per preservare lo spazio dello schermo. La barra menu desktop/non mobile usa background blu e mostra il nome **Cybersecurity Incident Registry** in verticale, con una parola per riga. La voce **Nuovo incidente** è rimossa dalla barra dei menu: la creazione avviene dal pulsante omonimo nella pagina principale degli incidenti.


## Aggiornamenti funzionali su azioni, label, categorie, moduli e dati incidente

Le azioni dell’incidente includono ora anche il campo **Conseguenze associate all’azione**, modificabile dal dettaglio incidente insieme a persona, label, descrizione e flag `exportable`. Le conseguenze esplicite inserite sulle azioni sono usate nei report e nei moduli quando viene richiesto il campo derivato delle conseguenze; in assenza di testi specifici resta disponibile la derivazione automatica basata su categorie, dati interessati e dati personali.

In **Admin → Liste configurabili** le sezioni sono visualizzate in verticale, una sotto l’altra, per migliorare la leggibilità dei campi modificabili e delle descrizioni estese.

Le label configurabili hanno un campo **Descrizione** amministrabile da **Admin → Liste configurabili**. La descrizione è disponibile per le label delle azioni e per le categorie incidente. Nel campo modulo `measures_adopted` le azioni esportabili sono riportate usando la descrizione della label, se presente, al posto del nome tecnico della label; seguono l’eventuale descrizione dell’azione e la data/ora. Per le categorie incidente, il nuovo campo modulo `category_descriptions` / “Descrizione e causa” restituisce l’elenco delle descrizioni delle categorie associate, usando il nome categoria come fallback.

Gli incidenti includono i nuovi campi **Numero di interessati** e **Volume dati**, modificabili nella scheda incidente ed esportati/importati nel full export come tutte le colonne reali del database. In **Moduli → Configurazione** sono disponibili anche i nuovi campi database: `data_subjects_count`, `data_volume`, `privacy_authority_non_notification_reason` e `documentation_location`. Questi ultimi due leggono i valori configurati in **Admin → Altre configurazioni**: “Motivazione non comunicazione al Garante della Privacy” e “Luogo documentazione”.

Nella configurazione moduli è ora possibile rinominare un template PDF esistente mantenendo il PDF, i mapping campo PDF/campo database e la configurazione di font. La sostituzione del PDF continua a richiedere gli stessi campi AcroForm per preservare i mapping.

## Documentazione utente

La documentazione utente è disponibile dal menu **Aiuto → Documentazione** come guida online ricercabile e da **Aiuto → Scarica documentazione PDF** come PDF formattato professionalmente. La guida include il logo applicativo, diagrammi di flusso, grafici e schermate illustrative. Il logo custom configurato dall'amministratore non viene incluso nella documentazione utente.

## Documentazione amministrativa

Dal menu **Aiuto → Documentazione amministrativa** è disponibile una guida dedicata agli amministratori. La guida è ricercabile online con lo stesso meccanismo della documentazione utente e descrive in modo esteso:

- responsabilità amministrative, prerequisiti e sicurezza degli account;
- gestione utenti, ruoli e autorizzazioni;
- configurazione LDAP, OAuth2/SSO e controllo della connessione SSO;
- tassonomie, label, categorie, descrizioni e dati organizzativi;
- SMTP, template e notifiche;
- template PDF, mapping, sostituzione e rinomina dei moduli;
- logo applicativo, logo custom e menu Aiuto;
- full export, import, backup, ripristino e continuità operativa;
- controlli periodici, audit, qualità dati e troubleshooting.

Dal menu **Aiuto → Scarica documentazione amministrativa PDF** è possibile scaricare la versione PDF professionale della guida amministrativa. Il PDF include copertina, logo applicativo, informazioni di versione lette da `APP_INFO`, indice, header/footer, numerazione pagine, diagrammi di flusso, grafici e schermate illustrative. Anche in questo caso viene usato esclusivamente il logo applicativo, senza includere il logo custom configurabile dall'amministratore.

## Multi-factor authentication TOTP

L'applicazione supporta la multi-factor authentication basata su TOTP per utenti locali e LDAP. La MFA è disattivata per default per ogni utente. La creazione di un token avviene in due fasi: generazione temporanea di stringa segreta/QR Code e verifica obbligatoria del codice TOTP. Il token viene salvato nel database solo se la verifica ha esito positivo.

Ogni utente può gestire i propri token dal menu **Impostazioni → Multi-factor authentication**. La MFA può essere attivata solo quando nell'utenza esiste almeno un token verificato; se viene rimosso l'ultimo token verificato la MFA viene disattivata automaticamente per evitare blocchi di accesso.

Gli amministratori possono gestire la MFA di tutti gli utenti da **Admin → Utenti → gestisci MFA**: possono attivare o disattivare la richiesta MFA solo in presenza di token verificati, revocare singoli token o rimuovere tutti i token di un utente. I dettagli segreti dei token altrui non sono visibili agli amministratori; restano visibili solo per i propri token nella pagina di gestione personale. Le cancellazioni usano un solo passaggio di conferma operativa, evitando doppie richieste di conferma.

Per l'utilizzo sono richieste le dipendenze `pyotp` e `qrcode[pil]`, incluse nel file `requirements.txt`.

## Licenza

Il pacchetto include il file `LICENSE` con indicazione di licenza europea EUPL-1.2.

0.110-72
- I token TOTP vengono salvati solo dopo verifica positiva del codice generato dall'app.
- La MFA può essere attivata solo se l'utente possiede almeno un token verificato.
- La rimozione dell'ultimo token verificato disattiva automaticamente la MFA dell'utente.
- Semplificate le cancellazioni dei token evitando conferme duplicate.
- Aggiornate documentazioni utente, amministrativa e progettuale.

## Aggiornamento interfaccia selezioni incidente

Nelle pagine di creazione e modifica incidente la selezione delle raccomandazioni usa ora il medesimo schema drag & drop già adottato per categorie, dati interessati e personale. Le voci disponibili sono presentate nella colonna sorgente e vanno trascinate nell’area di destinazione; le selezioni sono salvate come campi nascosti e vengono deduplicate lato server prima dell’associazione all’incidente. Le checkbox dell’interfaccia sono state rese più compatte per ridurre l’ingombro visivo nelle tabelle, nei pannelli di configurazione e nelle anteprime.


## Aggiornamento selezione template nei moduli incidente

Nella sezione **Generazione moduli** del dettaglio incidente la scelta dei template PDF non usa più checkbox visibili. Ogni template è presentato come una scheda cliccabile con nome e numero di campi PDF; un click seleziona o deseleziona la scheda, che viene evidenziata in blu quando attiva. La selezione multipla resta supportata e il backend riceve gli stessi valori del campo `templates`, mantenendo compatibilità con la generazione esistente.


### Persistenza dei template PDF

I PDF caricati nella configurazione moduli vengono salvati sia nel file system operativo (`FORM_TEMPLATE_DIR`) sia nel database applicativo. Il file system resta usato per analisi, anteprima, sostituzione e generazione dei PDF finali; la copia nel database è una copia di sicurezza applicativa che permette il ripristino automatico dei file mancanti dopo un riavvio. Se la directory montata è vuota o viene ricreata, i template registrati vengono riscritti automaticamente prima della visualizzazione della configurazione moduli e prima della generazione dei documenti. La rinomina, sostituzione e cancellazione di un template aggiorna coerentemente file, mapping, configurazione e copia binaria persistente.


### Full export completo

Il full export produce un archivio `tar.gz` autosufficiente. L'archivio contiene:

- tutte le tabelle applicative configurate nel modello dati corrente;
- tutte le colonne reali di ogni tabella, incluse configurazioni, utenti, ruoli, LDAP/SSO, MFA TOTP, notifiche, label, categorie, incidenti, azioni, raccomandazioni e template;
- tutte le tabelle di relazione many-to-many;
- documenti associati agli incidenti e allegati delle azioni;
- template PDF dei moduli sia come file fisico sia come copia binaria persistente nel database;
- logo custom configurato e loghi applicativi statici;
- manifest `schema` con elenco colonne e sezione `_coverage` per verificare cosa viene esportato.

I dati binari presenti nel database sono serializzati in Base64 all'interno del manifest JSON. L'import completo ricostruisce database, configurazioni, file, template e loghi.


Aggiornamento 0.110-82: configurazione URL applicazione e placeholder notifiche. Nel menu Admin → Altre configurazioni è disponibile il campo “URL applicazione”, con default http://localhost:8000, usato per generare link esterni nelle email. Nei template delle email dei task in scadenza sono disponibili %external_url%, %report% e %statistics%: il primo inserisce la URL esterna configurata, mentre %report% e %statistics% richiedono rispettivamente l'allegato PDF del report incidente e il PDF delle statistiche, generati al momento dell'invio. Nei template generali del menu Notifiche è disponibile anche %EXTERNAL_URL%. L’anteprima dei task in scadenza segnala gli allegati previsti senza inviare email.

## Aggiornamento 0.110-84 - mantenimento della posizione nella pagina incidente

Nelle pagine di dettaglio incidente, dopo le operazioni eseguite dai pulsanti di salvataggio, aggiunta azione, upload documenti e generazione moduli PDF, l’applicazione torna automaticamente alla stessa sezione operativa da cui è partita l’azione. Le sezioni interessate sono identificate con ancore stabili: dati principali dell’incidente, azioni, documenti e generazione moduli. Il comportamento riduce la perdita di contesto nelle pagine lunghe e semplifica l’inserimento progressivo di azioni, allegati e moduli generati.


## Aggiornamento 0.110-85 - data/ora azioni e chiusura automatica

Nella scheda di modifica incidente, il campo **Data e ora** della sezione **Azioni** viene precompilato quando la pagina viene caricata. Il valore corrisponde al momento corrente calcolato nel fuso orario applicativo configurato in **Admin → Altre configurazioni → Time zone applicazione**. Il valore predefinito è `Europe/Rome`; è possibile usare qualunque identificativo IANA valido, ad esempio `UTC` o `Europe/Rome`.

Quando viene aggiunta, o aggiornata, un’azione la cui label, descrizione della label o descrizione libera contiene il testo “conclusione”, l’incidente viene automaticamente portato nello stato **chiuso**. La data/ora fine dell’incidente viene allineata alla data/ora dell’azione di conclusione, così il computo della durata operativa continua a usare l’intervallo tra prima azione e conclusione.


### 0.110-86

- Chiusura automatica: quando viene aggiunta un’azione di conclusione, lo stato passa a `chiuso` e i campi `Data fine` e `Ora fine` vengono copiati dalla data/ora dell’azione.


### 0.110-87

- Prima della generazione dei moduli PDF, l’applicazione verifica i campi dell’incidente utilizzati dai mapping dei template selezionati.
- Se uno o più valori sono mancanti, la generazione viene bloccata e l’utente riceve un messaggio cumulativo con i campi da completare, raggruppati per template e campo PDF.
- La validazione evita la produzione di documenti compilati parzialmente e mantiene la posizione nella sezione di generazione moduli.

## Aggiornamento 0.110-88 - errori contestuali, audit log e menu Moduli dinamico

Nella scheda di modifica incidente gli esiti e gli errori delle operazioni richieste dall’utente vengono mostrati nella sezione operativa da cui sono stati generati: dati principali dell’incidente, azioni, documenti o generazione moduli. In questo modo, ad esempio, un errore di generazione PDF o di validazione dei campi necessari al template resta visibile direttamente nella sezione **Generazione moduli**, mentre gli errori di inserimento o aggiornamento azione restano nella sezione **Azioni**.

È stata introdotta la tabella `audit_log`, usata per registrare le operazioni applicative con data/ora, tipo di operazione, utente, tipo attore e dettagli tecnici essenziali. Le operazioni effettuate dagli utenti tramite richieste di modifica vengono registrate automaticamente; il controllo automatico delle scadenze notifiche registra una voce con attore scheduler. La ritenzione predefinita dell’audit è di 6 mesi ed è configurabile in **Admin → Altre configurazioni → Ritenzione audit log**. La pulizia dei record più vecchi avviene in modo opportunistico durante le operazioni applicative.

Il menu **Moduli** è ora visualizzato solo quando l’utente dispone di almeno una voce accessibile. Per gli utenti senza privilegi di configurazione dei moduli il menu non viene mostrato, evitando dropdown vuoti.



## Aggiornamento 0.110-90 - Retention audit granulare e layout configurazioni

La configurazione della ritenzione del registro audit in **Admin → Altre configurazioni** è ora espressa in quattro campi separati: mesi, giorni, ore e minuti. Il valore predefinito resta 6 mesi; se tutti i campi vengono impostati a zero, l’applicazione ripristina automaticamente il default a 6 mesi per evitare una retention nulla. La pulizia della tabella `audit_log` usa il valore complessivo configurato e continua a essere applicata dopo operazioni utente, scheduler notifiche e full import.

Il pulsante di salvataggio della pagina **Altre configurazioni** usa la classe `admin-config-save-button` e ha altezza massima pari a 1 cm, così il layout resta compatto anche con il nuovo gruppo di campi.

## Aggiornamento 0.110-89 - Audit consultabile, full export/import e retention

La tabella `audit_log` e tutte le configurazioni salvate nella tabella `setting` sono incluse nel full export e nel full import. Il manifest `export.json` riporta `audit_logs` e `settings` tra le tabelle esportate, così il ripristino conserva sia i parametri applicativi sia il registro audit entro i limiti di retention.

La pulizia della tabella audit è centralizzata nella funzione `purge_audit_logs()`, che elimina i record con `occurred_at` più vecchio del cutoff calcolato da `audit_retention_months_part / audit_retention_days_part / audit_retention_hours_part / audit_retention_minutes_part`. La funzione viene richiamata dopo le operazioni utente, dopo il controllo scheduler delle notifiche e al termine del full import; dopo un import completo, eventuali record audit più vecchi della retention configurata nell’archivio ripristinato vengono rimossi automaticamente.

Nel menu **Admin** è disponibile la nuova voce **Audit**, visibile solo agli utenti con ruolo admin. La pagina permette di visualizzare gli ultimi record audit e di cercare per testo libero, tipo operazione, utente, origine (`user`, `scheduler`, `system`) e intervallo temporale. I risultati sono ordinati dal più recente e limitati a 500 righe per mantenere la pagina reattiva.


## Aggiornamento 0.110-91 - Avvisi procedurali in cima al dettaglio incidente

La pagina di dettaglio di uno specifico incidente mostra ora la sezione **Avvisi procedurali** nella parte alta, subito dopo la scheda principale dell’incidente. La documentazione utente e progettuale è stata aggiornata per chiarire la nuova posizione della sezione e la finalità di evidenziare subito eventuali notifiche o verifiche mancanti.


## Aggiornamento 0.110-92 - Exportable default configurabile sulle label azioni

In **Admin → Liste configurabili → Label azioni** è stato aggiunto il campo **Esportabile per default**. Durante l’inserimento di una nuova azione in un incidente, il sistema inizializza il flag `exportable` dell’azione usando il valore configurato sulla label selezionata. Il modello dati `ConfigLabel` include la nuova colonna `default_exportable`, migrata automaticamente sui database esistenti e inclusa nel full export/import insieme alle altre configurazioni delle label.

## Aggiornamento 0.110-93 - Tempo massimo in ore e timezone nelle notifiche di scadenza

La colonna della sezione **Label azioni** in **Admin → Liste configurabili** è ora denominata **Tempo massimo (ore)**, così l’unità di misura è esplicita anche nella tabella di modifica. Le notifiche automatiche dei task in scadenza formattano tutte le date e ore, incluse scadenza, prima informazione iniziale e data di generazione, nel fuso orario applicativo configurato in **Admin → Altre configurazioni**. Il nome della timezone configurata viene riportato nel testo della notifica per evitare ambiguità operative.



### Lingua interfaccia

L'interfaccia e le documentazioni sono disponibili in italiano e inglese. Per default la lingua segue il locale del browser: italiano per locale italiano, inglese per tutti gli altri locale. Un amministratore può forzare `auto`, `it` o `en` da Admin → Altre configurazioni.

## Aggiornamento 0.110-95 - README inglese del pacchetto

Il pacchetto include ora anche `README_en.md`, traduzione inglese del file `README.md`. Da questa versione il README italiano e il README inglese devono essere mantenuti allineati insieme alla documentazione utente, amministrativa e progettuale. Le richieste operative possono continuare a essere fornite in italiano; gli aggiornamenti funzionali devono riportare automaticamente anche la corrispondente documentazione inglese.


## Aggiornamento 0.110-96 - Dicitura avviso notifica utente

Negli **Avvisi procedurali** del dettaglio incidente la voce relativa alla notifica all'utente è ora espressa come **Notifica all'utente richiesta**. La nuova dicitura chiarisce che l'adempimento è richiesto dalla procedura e non semplicemente da valutare.

### Report PDF incidenti: sezione Documenti

Nei report PDF degli incidenti, la tabella della sezione **Documenti** assegna più spazio alla colonna del nome del documento e riduce lo spazio riservato alla data e ora di caricamento. La data e ora di caricamento è formattata come `YYYY-MM-DD HH:MM:SS`; i secondi sono sempre espressi come valori interi e non vengono riportate frazioni di secondo o microsecondi.

## Aggiornamento 0.110-97 - Report PDF documenti

La sezione Documenti dei report PDF degli incidenti usa ora una colonna data/ora di caricamento più compatta e assegna più spazio al nome del documento. I timestamp di caricamento sono normalizzati nel formato `YYYY-MM-DD HH:MM:SS`, senza microsecondi e con secondi sempre interi.
## Aggiornamento 0.1.0-98 - Report PDF incidenti: orari e durata

Nei report PDF degli incidenti tutti i valori data/ora testuali sono normalizzati nel formato `YYYY-MM-DD HH:MM:SS`: i secondi sono sempre interi e non vengono mai visualizzate frazioni di secondo o microsecondi. La sezione di sintesi del report include ora anche la **Durata**, quando disponibile, calcolata con lo stesso criterio della pagina principale dell’applicazione: intervallo tra la prima azione registrata e la data/ora di conclusione dell’incidente.
## Aggiornamento 0.1.0-99 - Report PDF incidenti: impaginazione professionale

I report PDF degli incidenti sono stati riformattati con una presentazione più professionale: all'inizio del documento viene mostrato il logo applicativo; se è stato caricato un logo da GUI viene mostrato anch'esso senza etichette testuali. Se nessun logo è caricato da GUI, il relativo spazio viene omesso. Subito dopo viene inserito un indice sintetico delle sezioni. I titoli delle sezioni usano uno stile evidenziato e vengono mantenuti sulla stessa pagina del contenuto relativo, evitando titoli isolati a fine pagina. Il piè di pagina include la numerazione delle pagine.

## Aggiornamento 0.1.0-100 - Report PDF incidenti: loghi

Nei report PDF degli incidenti la prima pagina non mostra più la dicitura **logo custom**. Il logo applicativo statico resta presente; il logo caricato da GUI viene mostrato, quando disponibile, come logo applicativo aggiuntivo. Se nessun logo è stato caricato da GUI, il relativo spazio viene omesso dal PDF.


## Aggiornamento 0.1.0-101 - Report PDF incidenti: rendering immagini logo

Nei report PDF degli incidenti i loghi della prima pagina vengono renderizzati come immagini effettive. In particolare il logo applicativo SVG viene convertito internamente in PNG temporaneo prima dell'inserimento nel PDF, evitando che metadata o testo alternativo dello SVG vengano visualizzati al posto dell'immagine. La tabella iniziale dei loghi non mostra etichette testuali sotto le immagini; il logo caricato da GUI continua a essere omesso quando non configurato o non disponibile.

## Aggiornamento 0.1.0-102 - Report PDF incidenti: logo applicativo e logo caricato

Nei report PDF degli incidenti il logo applicativo viene ora inserito usando come sorgente primaria l’immagine PNG applicativa già usata dalla documentazione, con fallback allo SVG solo se necessario. Questo evita che nel PDF compaia testo o che il logo applicativo venga omesso. Il logo caricato da GUI continua ad apparire accanto al logo applicativo quando configurato e presente su filesystem; se non è stato caricato alcun logo da GUI, viene mostrato solo il logo applicativo.

## Aggiornamento 0.1.0-103 - Scheduler notifiche e menu Admin raggruppato

Le notifiche periodiche dei task in scadenza non dipendono più dal passaggio di richieste web sull'applicazione. All'avvio viene avviato uno scheduler interno leggero che controlla periodicamente se l'intervallo configurato in **Admin → Notifiche** è trascorso e, in caso positivo, esegue lo stesso controllo usato dal pulsante manuale. Il poll tecnico dello scheduler è configurabile con la variabile d'ambiente `CIR_DEADLINE_SCHEDULER_POLL_SECONDS` e può essere disabilitato con `CIR_ENABLE_DEADLINE_SCHEDULER=0` per installazioni che preferiscono un job esterno. Ogni esecuzione effettiva registra un record nella tabella `audit_log` con tipo operazione `scheduler:deadline_notification_check`, attore `scheduler`, sorgente dell'esecuzione e riepilogo di incidenti controllati, invii, salti ed errori.

Il menu **Admin** è stato riorganizzato in sottogruppi collassabili: configurazione generale, anagrafiche e workflow, utenti e accesso, controllo e audit. La riorganizzazione riduce l'altezza del menu e consente di visualizzare meglio tutte le voci amministrative anche su schermi più piccoli.

## Aggiornamento 0.1.0-104 - Prossimo invio notifiche task e schedulazione da mezzanotte

La pagina **Impostazioni → Notifiche** mostra ora una sezione **Prossimo invio stimato** per i promemoria automatici dei task in scadenza. La sezione indica lo stato del controllo automatico, lo stato dell'invio email, l'intervallo effettivo in minuti, la mezzanotte di riferimento nel fuso applicativo, lo slot corrente, l'ultima esecuzione automatica registrata e la data/ora stimata del prossimo invio.

Lo scheduler non calcola più gli intervalli a partire dall'avvio dell'applicazione. Gli slot di esecuzione sono sempre multipli dell'intervallo configurato a partire dalla mezzanotte del giorno corrente nel fuso orario impostato in **Admin → Altre configurazioni**. Per esempio, con intervallo di 4 ore, gli slot sono 00:00, 04:00, 08:00, 12:00, 16:00 e 20:00. Il pulsante manuale continua a eseguire subito il controllo senza modificare la pianificazione automatica.

## Promemoria specifici per incidente

Ogni incidente dispone ora della sezione **Promemoria specifici**, dalla quale gli utenti con permessi di scrittura possono programmare, modificare e cancellare promemoria non periodici con data e ora puntuali. Il messaggio è definito dall’utente, i destinatari principali sono automaticamente le persone associate all’incidente con indirizzo e-mail valorizzato ed è possibile indicare ulteriori indirizzi in CC.

Lo scheduler invia tutti i promemoria specifici scaduti e non ancora inviati. Dopo un riavvio dell’applicazione, i promemoria non periodici saltati vengono recuperati tutti, confrontando lo stato del promemoria con i record di audit di invio. Le notifiche periodiche dei task in scadenza restano invece deduplicate per tipologia/intervallo: se l’applicazione salta più slot, viene eseguita solo l’ultima notifica dovuta per quella tipologia.

Il full export/import include anche la tabella dei promemoria specifici e mantiene la cronologia audit degli invii automatici.


## Aggiornamento 0.1.0-106 - Chiusura incidenti, audit paginato e link diretti nelle notifiche

La chiusura manuale o automatica di un incidente viene impedita quando sono ancora presenti avvisi procedurali attivi. Il messaggio di blocco viene mostrato nella sezione dell'operazione richiesta: dati principali dell'incidente per la chiusura manuale, sezione Azioni per la chiusura automatica tramite azione di conclusione.

La pagina **Admin → Audit** ora usa paginazione. Il numero predefinito di record per pagina è configurabile in **Admin → Altre configurazioni** tramite il campo **Record audit per pagina**, con default 20 e massimo 100. In cima alla pagina Audit sono visualizzati il numero totale corrente dei record della tabella, il numero di record filtrati e l'intervallo attualmente selezionato.

Tutte le notifiche relative a incidenti includono sempre un link diretto alla pagina dello specifico incidente. Nei template di notifica generale è disponibile il placeholder `%INCIDENT_URL%`; nei template dei task in scadenza è disponibile `%incident_url%`. Anche con template personalizzati che non includono il placeholder, il link diretto viene aggiunto automaticamente al messaggio inviato.

### Aggiornamento 0.1.0-107

- La sezione **Promemoria specifici** nella pagina del singolo incidente usa un layout responsive a schede: su smartphone data/ora, messaggio, CC, stato e azioni restano visibili e modificabili senza scorrimento orizzontale.
- I record di **Audit** registrano e mostrano dettagli sintetici, leggibili e limitati alle informazioni essenziali dell’operazione, evitando di salvare payload lunghi o poco comprensibili.

### Aggiornamento 0.1.0-108 - Pianificazione cron notifiche task

Le notifiche automatiche dei task con scadenza passano da una sola pianificazione a intervallo regolare a una pianificazione in stile cron configurabile da **Admin → Notifiche**. È possibile scegliere tra modalità **Intervallo regolare** e **Cron / orari specifici**. In modalità cron si possono indicare orari giornalieri nel formato `HH:MM`, separati da virgole, spazi o righe; gli eventuali intervalli restano disponibili e sono sempre calcolati dalla mezzanotte del fuso applicativo. Lo scheduler non usa l’orario di avvio dell’applicazione come riferimento: se l’applicazione riparte dopo uno o più slot saltati, esegue solo l’ultimo slot periodico dovuto e registra l’esito nella tabella audit. La pagina mostra anche gli slot configurati, lo slot corrente, il prossimo invio stimato e l’ultima esecuzione automatica.

La logica di invio è stata ricontrollata: lo scheduler interno continua a funzionare indipendentemente dal traffico web, usa la stessa funzione del pulsante manuale, registra errori SMTP e riepilogo invii in audit, e mantiene il link diretto all’incidente nel corpo della notifica anche quando il template personalizzato non contiene il placeholder `%incident_url%`.
