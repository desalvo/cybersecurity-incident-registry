# Migration, backup, import and recovery

Current upgrade guidance for 0.9.0-1 to 0.10.0-1, with historical 0.8.0 migration notes, Full Export/Import, database/filesystem handling, Kubernetes storage migration, rollback and recovery.

<a id="aggiornamento-a-rc20-da-090-1-build-20260902"></a>

## Aggiornamento a 0.10.0-1 da 0.9.0-1

La release in sviluppo è **0.10.0-1**, con build automatica `YYYYMMDD` registrata nel file `BUILD`. Questa procedura copre la baseline **0.9.0-1 build 20260902** e i suoi cumulativi supportati. Il cambio di versione non aggiunge DDL: conserva la revisione `20261122_01_legacy_bridge` già presente nel precedente cumulativo RC20. Un database già aggiornato non la riesegue. `VERSION` e `BUILD` nell’immagine sono autorevoli; vecchi `APP_VERSION`/`APP_BUILD` nei manifest non ne alterano l’identità. Il tag storico `0.9.0-1` non viene spostato.
Per aggiornare un'istanza già operativa si cambia l'immagine applicativa, mantenendo
il database e i volumi esistenti. Il primo avvio esegue le migrazioni applicative.
**Non occorre fare Full Import o caricare un export di bootstrap:** quelle
operazioni servono a ripristinare o inizializzare dati e non sono il percorso di
aggiornamento di un'istanza che deve conservare i propri incidenti.

Versione e build restano uguali fra i cumulativi: identificare quindi il codice
installato tramite commit sorgente e **digest OCI approvato dalla CI**. Il valore
`PENDING_HOTFIX_REBUILD` indica un package sorgente ancora privo di una nuova
immagine approvata; non è utilizzabile in un Deployment. La disponibilità di un
tag su Docker Hub non sostituisce i gate di test e sicurezza. Un digest immutabile
evita che repliche diverse risolvano un tag mobile a contenuti differenti; vedere
[Kubernetes: Images](https://kubernetes.io/docs/concepts/containers/images/).

### Cosa avviene al primo avvio

L'entrypoint esegue **`python -m app.migrate` prima di avviare i listener web**.
Questa fase non usa i worker Gunicorn, disabilita i propri scheduler e deve
terminare con successo; in caso di errore il container non avvia HTTP/HTTPS.
Anche l'avvio fuori dal container, tramite `create_app()`, mantiene gli stessi
controlli. Vedere [app/migrate.py](../app/migrate.py) e
[app/__init__.py](../app/__init__.py).

Le migrazioni sono ora una sequenza ordinata registrata nella tabella locale
`cir_schema_migrations`, con identificatori indipendenti da versione e build.
La prima revisione, `20261122_01_legacy_bridge`, adotta i database precedenti al
registro: crea le tabelle mancanti, applica le migrazioni legacy e quelle del
ciclo di vita dei workflow. Il sistema verifica la presenza delle tabelle e
colonne richieste dai modelli correnti e completa il bootstrap, registrando
l'esito nella stessa transazione finale dei dati di bootstrap. I riavvii
successivi applicano soltanto le revisioni ancora mancanti.

La compatibilità della storia viene controllata **prima** del recovery di un
Full Import o di altre mutazioni di bootstrap. Una revisione sconosciuta, più
recente o fuori sequenza blocca l'avvio; non viene reinterpretata come uno schema
vecchio. Una migrazione fallita non riceve un marcatore di successo. Alcuni
passaggi DDL legacy effettuano commit intermedi: il tentativo successivo può
riprendere in modo idempotente, ma non bisogna assumere che un errore annulli
ogni modifica già effettuata. Il contratto è implementato in
[migration_manager.py](../app/migration_manager.py).

Per le prossime versioni gli sviluppatori devono aggiungere una revisione
ordinata e il relativo passaggio idempotente, con prove di upgrade dalla baseline
supportata. Aggiungere un campo al modello senza una migrazione non basta:
la verifica dello schema blocca l'avvio se il database non è stato adeguato.
Questo meccanismo copre i percorsi dichiarati e verificati; non converte
arbitrariamente schemi personalizzati né esegue downgrade automatici.
Le migrazioni obbligatorie si interrompono conservando i record se incontrano
duplicati incompatibili con i vincoli per tenant o record operativi orfani/NULL
che impediscono i vincoli di ownership. Correggere la causa e riprovare, senza
eliminare record o marcare manualmente la revisione come completata.

La produzione usa PostgreSQL. SQLite resta utile per sviluppo e prove con un
singolo processo: gli avvii di migrazione SQLite concorrenti non sono supportati.
Il percorso dalla baseline 0.9.0-1 già multitenant non deve essere confuso con
vecchi schemi SQLite pre-multitenant che conservano vincoli globali sulle label,
sui codici o sulle identità utente. La conversione di questi ultimi vincoli è
implementata per PostgreSQL; tali database SQLite richiedono una migrazione
specifica e una verifica prima di adottare il catalogo condiviso.

Il bootstrap usa un advisory lock PostgreSQL con un massimo di 60 tentativi
distanziati di un secondo. Avviare inizialmente **una replica web e un worker**
mantiene il primo passaggio semplice da osservare ed evita più pod concorrenti
durante un seed lungo. Il limite riguarda l'acquisizione del lock, non la durata
della migrazione. La fase precedente ai listener evita inoltre che il timeout
di boot di Gunicorn interrompa l'upgrade. Le probe Kubernetes devono comunque
consentire il tempo necessario a questa fase.

Il listener HTTPS interno, se attivo, usa un secondo gruppo Gunicorn e il
parametro `WEB_CONCURRENCY_SSL`: nell'entrypoint corrente entrambi i gruppi
partono dopo la migrazione iniziale. Il chart normalmente serve HTTP
all'Ingress/Route che termina TLS. Non aggirare l'entrypoint con comandi
personalizzati senza mantenere la fase di migrazione e la gestione delle probe.

L'aggiornamento conserva i dati operativi e la password dell'admin già presente.
`ADMIN_INITIAL_PASSWORD` inizializza l'account solo quando manca: modificarla nel
Secret non è un metodo per cambiare la password di un account esistente.

Se non esiste già, viene creato **Tenants Default**, distinto dal tenant operativo
`default`. L'inizializzazione copia le configurazioni riutilizzabili del tenant
`default`, documenti/template e workflow, comprese le credenziali delle
integrazioni; non copia account, incidenti o KB privata. Le impostazioni condivise
diventano sorgente di ereditarietà, con precedenza degli override locali. Prima
dell'upgrade verificare quindi quali configurazioni del tenant `default` devono
diventare condivise. Un tenant ordinario già chiamato `Tenants Default` va
rinominato prima dell'aggiornamento: non viene convertito automaticamente nel
tenant speciale. Se la sorgente speciale esiste già, anche vuota, il primo seed
non viene ripetuto. Il comportamento è implementato in
[tenant_defaults.py](../app/tenant_defaults.py) e
[tenant_defaults_seed.py](../app/tenant_defaults_seed.py).

La nuova UI non richiede una migrazione separata: usa la tabella `setting`
esistente. In assenza di `global_ui_mode` si attiva la modalità moderna. Un
superuser può scegliere **Admin → Interfaccia globale** per passare globalmente alla UI
classica o moderna; questa scelta modifica la presentazione e non ripristina il
vecchio schema dati. Le schermate reali dell'help e i PDF aggiornati vengono
installati nell'immagine dal job CI di documentazione dello stesso commit.

### Preparazione e conservazione dei dati

1. Scegliere il digest approvato del cumulativo e annotare immagine precedente,
   numero di repliche, worker e configurazione di avvio. Provare l'upgrade su una
   copia isolata del proprio backup quando il database o lo storage hanno
   personalizzazioni.
2. Pianificare una finestra di manutenzione, terminare import/esportazioni in corso
   e sospendere temporaneamente automazioni/HPA/GitOps che ricreerebbero le
   repliche durante la procedura. Fermare tutte le repliche **web** precedenti.
3. A scritture applicative ferme, acquisire un backup PostgreSQL ripristinabile e
   una copia/snapshot coerente dei volumi applicativi. Conservare separatamente
   i Secret, la configurazione e l'immagine precedente. Il database può restare
   attivo per il backup logico; una copia a caldo dei file di `PGDATA` da sola non
   costituisce questa procedura di backup.
4. Mantenere lo stesso database, gli stessi PVC/volumi e i percorsi configurati
   per upload, backup, loghi, SSO, moduli PDF, SSL e documenti AI. Conservare
   **`SECRET_KEY` e `SETTING_ENCRYPTION_KEY`**, incluse le equivalenti sorgenti
   `_FILE`: la seconda serve a leggere i Settings già cifrati. Non rigenerare i
   Secret applicativi come parte di questo upgrade.

Durante l'upgrade non avviare Full Import o restore concorrenti, e non mantenere
repliche vecchie in servizio mentre la nuova revisione migra lo schema. Il lock
di recovery/import e quello del bootstrap hanno scopi e durate differenti: la
procedura non promette una migrazione senza interruzioni con versioni miste o un
import contemporaneo. Attendere il completamento della manutenzione prima di
riaprire queste operazioni agli amministratori.

Il passaggio dai PVC separati a un PVC unico `/data` non viene effettuato dal
bootstrap. Se necessario è un intervento di storage distinto, da pianificare con
la relativa procedura in questa guida. Conservare il layout funzionante durante
l'upgrade evita di scambiare un volume nuovo e vuoto per una perdita di dati.
Per lo stesso motivo, in Compose va conservato anche il **nome del progetto**,
che partecipa al nome dei volumi gestiti.

### Kubernetes: primo avvio controllato

Usare il namespace, il Deployment, il nome del container e il selector effettivi
della propria installazione. L'esempio seguente corrisponde ai manifest `k8s/`;
con Helm o GitOps riportare le modifiche nella relativa sorgente di configurazione
per evitare che il controller le annulli. Sostituire il segnaposto con il digest
approvato prima di eseguire i comandi.

```bash
CIR_NAMESPACE=cir
CIR_DEPLOYMENT=cybersecurity-incident-registry
CIR_CONTAINER=web
CIR_POD_SELECTOR='app=cybersecurity-incident-registry'
CIR_UPGRADE_IMAGE='desalvo/cybersecurity-incident-registry@sha256:REPLACE_WITH_THE_64_HEX_APPROVED_INDEX_DIGEST'

[[ "$CIR_UPGRADE_IMAGE" =~ ^desalvo/cybersecurity-incident-registry@sha256:[a-f0-9]{64}$ ]] || exit 1
kubectl -n "$CIR_NAMESPACE" get deployment "$CIR_DEPLOYMENT"
kubectl -n "$CIR_NAMESPACE" get pods -l "$CIR_POD_SELECTOR" -o wide
kubectl -n "$CIR_NAMESPACE" get pvc

kubectl -n "$CIR_NAMESPACE" scale deployment "$CIR_DEPLOYMENT" --replicas=0
kubectl -n "$CIR_NAMESPACE" wait --for=delete pod -l "$CIR_POD_SELECTOR" --timeout=35m
```

Confermare che il selector includa tutte e soltanto le repliche web di CIR.
Se non esisteva alcun pod, il comando `wait` può segnalare assenza di risorse:
verificare che il Deployment sia effettivamente a zero. A questo punto effettuare
il backup coerente indicato sopra. **Lasciare il database e i PVC presenti.**

Prima di riportare il Deployment a una replica, controllare le probe e i timeout
nel manifest effettivamente installato. Il file legacy
[k8s/deployment.yaml](../k8s/deployment.yaml) ha liveness HTTP e non include una
`startupProbe`: il solo cambio di immagine non introduce la protezione per un
avvio lento. Il chart corrente usa `Recreate`, startup HTTP con periodo 5 secondi
e soglia iniziale 120 (circa 10 minuti), readiness HTTP e liveness TCP. Il periodo
di startup va dimensionato rispetto al proprio storage; la liveness TCP evita
di considerare morto il processo solo perché una lunga richiesta occupa i worker,
ma non è una verifica funzionale del database. Riferimenti:
[startup/readiness/liveness](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
e [strategie dei Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#strategy).

Per un manifest esistente adottare consapevolmente le probe necessarie prima
dell'avvio; non copiare l'intero manifest del package sopra una configurazione
personalizzata. Allineare anche `terminationGracePeriodSeconds` al tempo di
chiusura concesso a Gunicorn. Il chart usa 1800 secondi per `requestTimeout` e
`terminationGracePeriod`; l'entrypoint, senza override, usa invece 180 secondi
per `GUNICORN_TIMEOUT`. La migrazione preventiva è indipendente da questo
timeout, mentre richieste amministrative lunghe, come Full Import, richiedono
anche timeout adeguati di worker e proxy. Mantenere il security context di
produzione e i mount scrivibili previsti.

Con le repliche ancora a zero, aggiornare immagine e impostazioni del primo avvio:

```bash
kubectl -n "$CIR_NAMESPACE" set image deployment/"$CIR_DEPLOYMENT" \
  "$CIR_CONTAINER=$CIR_UPGRADE_IMAGE"
kubectl -n "$CIR_NAMESPACE" set env deployment/"$CIR_DEPLOYMENT" --containers="$CIR_CONTAINER" \
  WEB_CONCURRENCY=1 GUNICORN_TIMEOUT=1800 GUNICORN_GRACEFUL_TIMEOUT=1800
kubectl -n "$CIR_NAMESPACE" scale deployment "$CIR_DEPLOYMENT" --replicas=1
kubectl -n "$CIR_NAMESPACE" rollout status deployment/"$CIR_DEPLOYMENT" --timeout=20m
kubectl -n "$CIR_NAMESPACE" logs deployment/"$CIR_DEPLOYMENT" -c "$CIR_CONTAINER" --since=20m
```

Se la replica non diventa Ready, controllare log ed eventi prima di tentare altri
riavvii. `Bootstrap failed`, errori DDL, timeout del lock, storage non scrivibile o
restart ripetuti richiedono la correzione della causa; non lanciare Full Import per
compensarli e non cancellare PVC o journal di recovery. `rollout status` non
sostituisce la verifica applicativa: effettuare login, aprire incidenti e allegati
preesistenti, controllare workflow, integrazioni e il tenant speciale.

Quando il primo avvio è stabile, ripristinare il numero di repliche previsto
soltanto se database e storage condiviso lo consentono; il chart rifiuta più
repliche con un volume RWO. Riattivare le automazioni sospese e registrare digest,
commit e risultato dell'upgrade. Il runtime può mostrare il digest del manifest
della singola architettura: confrontarlo con la corrispondente voce dell'indice OCI
approvato, non con una stringa `latest`.

Per un'installazione Helm già esistente conservare release, namespace,
`existingSecret`, PVC e valori dell'ambiente. Aggiornare `image.digest` nei valori
gestiti e predisporre il primo avvio con `replicaCount: 1` e `runtime.workers: 1`.
Il chart applica `Recreate`; passare dai vecchi YAML a Helm è una migrazione della
gestione delle risorse separata e non va ottenuta creando una seconda release
contro gli stessi volumi. Su OpenShift usare la release e l'overlay già adottati,
senza cambiare SCC o privilegi per risolvere un problema di startup.

### Docker o Podman Compose

Conservare la combinazione di file Compose e il progetto già usati. Per
un'installazione che usa entrambi i file di produzione del package, dopo avere
impostato `CIR_PRODUCTION_IMAGE` al digest approvato e verificato che i valori
`DATABASE_URL`/Secret e i volumi restino quelli precedenti:

```bash
CIR_COMPOSE_PROJECT=REPLACE_WITH_THE_EXISTING_PROJECT_NAME
CIR_UPGRADE_IMAGE='desalvo/cybersecurity-incident-registry@sha256:REPLACE_WITH_THE_64_HEX_APPROVED_INDEX_DIGEST'
[[ "$CIR_UPGRADE_IMAGE" =~ ^desalvo/cybersecurity-incident-registry@sha256:[a-f0-9]{64}$ ]] || exit 1
export CIR_PRODUCTION_IMAGE="$CIR_UPGRADE_IMAGE"
export WEB_CONCURRENCY=1
export GUNICORN_TIMEOUT=1800

docker compose -p "$CIR_COMPOSE_PROJECT" -f docker-compose.yml -f docker-compose.production.yml config --quiet
docker compose -p "$CIR_COMPOSE_PROJECT" -f docker-compose.yml -f docker-compose.production.yml stop -t 1800 web
# Eseguire ora il backup coerente di database e volumi.
docker compose -p "$CIR_COMPOSE_PROJECT" -f docker-compose.yml -f docker-compose.production.yml pull web
docker compose -p "$CIR_COMPOSE_PROJECT" -f docker-compose.yml -f docker-compose.production.yml up -d --no-deps --no-build --force-recreate web
docker compose -p "$CIR_COMPOSE_PROJECT" -f docker-compose.yml -f docker-compose.production.yml logs --tail=200 web
```

Per `podman compose` usare il provider Compose già configurato e le sue opzioni
equivalenti. Ricreare soltanto `web`; mantenere il servizio database e i volumi.
Non usare `down -v`. Controllare la salute del container e gli stessi percorsi
operativi indicati per Kubernetes. Il blocco assume una configurazione di
produzione già esistente: non modifica credenziali o routing per adattarli a una
nuova installazione.

### PostgreSQL e rollback

La 0.10.0-1 non richiede un cambio di major PostgreSQL né di `PGDATA`. Conservare il
cluster e l'immagine database approvati per l'ambiente durante l'upgrade
applicativo. Un eventuale aggiornamento major PostgreSQL richiede una procedura
dedicata, per esempio dump/restore o `pg_upgrade`, con prove di compatibilità;
non basta cambiare `postgres:<major>` sul volume esistente. Vedere
[PostgreSQL: Upgrading a Cluster](https://www.postgresql.org/docs/current/upgrading.html).

Le migrazioni applicative possono avere già modificato lo schema anche se un
passaggio successivo di startup fallisce. Tornare al vecchio digest,
`kubectl rollout undo`, `helm rollback` o il rollback `--atomic` di Helm non
ripristina i dati PostgreSQL né i file. Se il vecchio codice non è compatibile con
lo schema aggiornato, fermare le repliche web e ripristinare **database, volumi e
Secret del medesimo backup**, quindi riavviare l'immagine precedente. Conservare
anche una copia dello stato fallito per analizzare eventuali operazioni avvenute
dopo il backup. Non dichiarare concluso il rollback finché login, incidenti,
allegati e configurazioni non sono stati ricontrollati.

## Tenants Default RC18

### Attivazione e contenuto

Il primo avvio della RC18, se assente, crea il tenant speciale **Tenants Default**. Il tenant
operativo `default` conserva la propria identità. Se esiste già un tenant ordinario
chiamato `Tenants Default`, l'avvio segnala il conflitto: rinominare quel tenant
prima dell'aggiornamento. La migrazione non lo converte automaticamente in sorgente
globale. La nuova sorgente viene inizializzata copiando la configurazione del tenant operativo `default`, inclusi documenti, notifiche, Settings e workflow. Account, incidenti, persone operative e KB privata sono esclusi; i riferimenti alle persone dei modelli vengono rimossi solo durante questa inizializzazione. Una sorgente già presente, anche vuota, non viene popolata di nuovo. Le bozze copiate vengono pubblicate nel catalogo.

Da **Admin → Tenants Default**, il superuser può attivare il tenant speciale e usare
le normali schermate amministrative. Sono condivisibili:

| Configurazione | Comportamento |
|---|---|
| Gravità, categorie, dati, azioni e parametri delle label | Copie locali con provenienza e ID distinti |
| Tipi e template di notifica, documenti PDF e mapping | Dipendenze validate e riferimenti rimappati |
| Raccomandazioni, modelli incidente, destinatari esterni | Copie locali indipendenti dai record già presenti |
| Definizioni backup | Copie con percorso locale del destinatario; la sorgente non esegue job |
| SSO, LDAP, SMTP, plugin, campi personalizzati, pulsanti e altri Settings di tenant | Ereditarietà live, con precedenza degli override locali |
| Workflow in preparazione e catalogo | Bozze nella sorgente; installazione selettiva di copie dal catalogo |

Gli account, gli incidenti, i relativi allegati, le persone operative, gli audit e
la KB privata non vengono trasferiti in questo export di configurazione.
Certificati TLS, URL/timezone dell'istanza, limite upload e stato del wizard sono
impostazioni globali e mantengono la loro gestione a livello di istanza.

### Collisioni, aggiornamenti e cancellazioni

Un elemento pubblicato ha una provenienza UUID distinta dalla sua chiave numerica
locale. La propagazione assegna nuovi ID; nomi o codici in conflitto ricevono un
suffisso, senza sostituire l'elemento già presente. Un indirizzo email può avere
due identità di configurazione diverse: l'indirizzo non viene alterato per evitare
una collisione. Le modifiche locali a una copia sono conservate; il sistema separa
la copia personalizzata e mantiene una copia aggiornata dai defaults.

La cancellazione dalla sorgente elimina soltanto copie inutilizzate e non
personalizzate. Gli elementi ancora referenziati da incidenti, workflow o altri
parametri restano disponibili e generano un avviso in **Admin → Avvisi Tenants
Default**. L'amministratore può confermare di avere letto l'avviso. I superuser
possono vedere gli avvisi di tutti i tenant. Se un parametro è ancora usato da una
bozza nella sorgente stessa, occorre rimuovere prima quel riferimento.

Per i singoli Settings la precedenza è valore locale, valore di Tenants Default,
valore iniziale dell'applicazione. Solo il tenant operativo `default` conserva
anche il fallback alle proprie impostazioni legacy non prefissate. Anche una
stringa locale vuota è un override intenzionale.
**Parametri ereditati e locali → Usa il valore condiviso** rimuove soltanto
l'override del tenant attivo. Durante la creazione iniziale della sorgente vengono copiate anche le credenziali di configurazione del tenant operativo. Verificare quindi le integrazioni che si desidera rendere condivise. Gli export redatti e il bootstrap hanno regole distinte di rimozione dei segreti.

### Importare più copie di un workflow

1. Aprire **Admin → Catalogo workflow** nel tenant destinatario.
2. Scegliere una voce e indicare il **nome della nuova copia**. Un superuser può
   scegliere anche il tenant destinatario; l'admin di tenant opera nel proprio.
3. Premere **Crea una nuova copia nel tenant**. Il sistema crea una categoria e
   rimappa label, condizioni, tipi di step, notifiche, PDF, font e mapping necessari. Per le dipendenze pubblicate usa la replica locale identificata dalla provenienza UUID, non un record omonimo o l’ID numerico della sorgente.
4. Aprire **Flussi operativi incidenti** per modificare la struttura della copia. Per variare anche le dipendenze senza modificare le altre copie, usare **Personalizza parametri** prima che la copia sia utilizzata da incidenti. La stessa voce e revisione possono essere importate
   nuovamente con un altro nome. Nomi ripetuti vengono disambiguati.

L'opzione flusso di default è consentita soltanto quando il destinatario non ne
possiede già uno. Le revisioni successive non sovrascrivono le strutture già installate. Il ritiro blocca nuove importazioni. L’obsolescenza è invece propagata a tutte le copie, anche personalizzate, che restano disponibili per gli incidenti già esistenti.

Per trasferire un workflow esistente, usare **Esporta un workflow dal tenant
attivo**. Il superuser carica quel JSON con **Importa un workflow nel catalogo**,
oppure pubblica direttamente il workflow del tenant attivo. I valori dei destinatari,
le regole di indirizzamento, i testi e i contenuti PDF sono conservati: il file è
una configurazione riutilizzabile e non è anonimizzato. Il precedente export di
bootstrap anonimizzato mantiene la propria funzione separata.

### Corrente, obsoleto e cancellazioni locali (RC18)

Ogni workflow nasce `current` (corrente); più workflow possono essere correnti.
La scelta del flusso di default (senza categoria) è distinta dallo stato.
L'amministratore di tenant o il superuser può impostare `obsolete`.
I nuovi incidenti, le clonazioni e i cambi di assegnazione rifiutano il workflow
obsoleto; la modifica di un incidente esistente con lo stesso flusso resta ammessa.
Gli step e le prove storiche non vengono eliminati.

Impostando obsoleto il workflow in Tenants Default, tutte le copie importate
vengono rese obsolete nella stessa transazione e vengono creati avvisi persistenti
per ogni amministratore di tenant e superuser, visibili anche cambiando tenant.
La personalizzazione conserva la provenienza necessaria per questa propagazione.
Non si può riattivare una copia finché la sorgente è obsoleta. Riattivare la
sorgente permette una scelta esplicita locale, senza riattivare tutte le copie.

Label, raccomandazioni, persone, notifiche, moduli, step e workflow usati da un
incidente del tenant non sono cancellabili. I controlli precedono qualunque
rimozione delle relazioni. Per i Settings e i modelli legacy senza una traccia
precisa d'uso il controllo è conservativo quando esistono incidenti. Le repliche
condivise sono gestite dalla sorgente; una rimozione che incontra riferimenti
mantiene il dato locale e avvisa gli amministratori.

### Bootstrap con entrambi i tenant

Il bootstrap anonimizzato RC18 include **default e Tenants Default**, i workflow,
il catalogo e i documenti necessari, conservando riferimenti e stati coerenti.
Rimuove incidenti, persone operative, account privati, audit, notifiche personali
e credenziali; l'admin viene ricreato secondo la configurazione di bootstrap
sicura dell'istanza destinataria. I PDF/template binari riusabili vanno esaminati
prima della condivisione: il contenuto interno non è automaticamente anonimizzato.
Il Full Export globale include anche stato workflow, provenienza e avvisi.

### Export e import dell'intero tenant speciale

**Admin → Tenants Default → Esporta tutto Tenants Default** scarica un solo JSON
portabile con configurazioni, Settings, documenti e mapping, loghi/immagini SSO,
bozze workflow e catalogo, comprese le voci ritirate. Per prelevare la configurazione
di un tenant esistente usare **Esporta la configurazione del tenant attivo**; il
JSON risultante può essere importato nella sorgente speciale.

L'export del tenant operativo `default` comprende anche le sue impostazioni
legacy non ancora prefissate. Negli altri tenant vengono esportati i valori
condivisi effettivi e gli override locali; i fallback legacy globali non vengono
materializzati come dati privati del tenant. Il tenant speciale esporta solo
la propria configurazione esplicita.

Le credenziali vengono omesse per impostazione iniziale, con indicazione dei
campi redatti. Solo il superuser può scegliere **Includi anche credenziali** nel
download completo: il file contiene allora valori leggibili da proteggere come
un backup di segreti. In destinazione vengono ricifrati con la chiave locale.
Importando un file redatto, i segreti già presenti vengono conservati; quelli
mancanti vanno configurati prima di attivare le integrazioni. Gli indirizzi di
notifica sono parametri di configurazione e restano nel file anche senza credenziali.

Caricare il file in **Importa configurazione in Tenants Default** e confermare
la pubblicazione ai tenant. I riferimenti vengono validati prima delle mutazioni;
ID e nomi documentali sono rimappati. Un reimport dalla stessa origine aggiorna
gli elementi corrispondenti e conserva le personalizzazioni rilevate; omissioni
dal file non significano cancellazione. I JSON sono limitati a 25 MiB complessivi,
con limiti specifici per documenti e immagini. Gli asset usano nuovi percorsi e
vengono ripuliti se la transazione viene annullata.

### Schema, Full Import e rollback

La migrazione aggiunge il flag del tenant speciale, le tabelle di provenienza,
avvisi e catalogo e la proprietà dei nuovi modelli documentali. I PDF legacy senza
proprietario mantengono la compatibilità; le nuove copie di tenant sono modificabili
soltanto nel tenant proprietario. Il Full Export globale conserva i nuovi metadati;
gli export precedenti restano importabili. Il ripristino di un export di tenant
crea copie documentali con nomi nuovi e mantiene separati i dati degli altri tenant.

Per pubblicare una notifica condivisa che usa un PDF legacy dotato di tag,
importare prima una copia del PDF nel tenant speciale. Questo rende esplicita
la provenienza dei tag e impedisce di collegarli a tipi locali omonimi. I PDF
legacy senza tag possono continuare a essere usati come documenti comuni.

L'unicità email dei destinatari viene rimossa conservando ID e contenuti. PostgreSQL
elimina soltanto i vincoli/indici sull'identità email. SQLite ricostruisce la tabella
in transazione e rifiuta schemi, trigger o riferimenti personalizzati non riconosciuti.
Prima di installare la RC effettuare un backup completo; il rollback a RC16 richiede
il ripristino del backup coerente di database e volumi, oltre al codice precedente.
La RC17 resta subordinata alle verifiche descritte in [TESTING_AND_PRODUCTION.md](TESTING_AND_PRODUCTION.md).

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

## Bootstrap anonimizzato da un'istanza configurata

La 0.9.0-1 supporta un export bootstrap del solo tenant `default`, disponibile ai superuser dal menu **Export**. L'archivio usa il formato Full Export ma include il profilo `default-tenant-anonymized-bootstrap-v1`, in modo che l'import possa applicare regole aggiuntive di sicurezza.

Il bootstrap conserva la configurazione riutilizzabile del tenant default (label, raccomandazioni, workflow, tipi/template di notifica e template PDF referenziati) e le configurazioni tecniche sanificate. Sono esclusi dati operativi o personali: incidenti, azioni, documenti/allegati operativi, persone, destinatari esterni, utenti diversi da `admin`, MFA, audit, knowledge base AI e job di backup. Secret e credenziali vengono eliminati; SSO resta configurato a livello di endpoint/claim/Client ID ma disabilitato finché non viene inserito un nuovo Client Secret.

Prima dell'import su una nuova istanza impostare almeno `SECRET_KEY`, `SETTING_ENCRYPTION_KEY`, `DATABASE_URL` e `ADMIN_INITIAL_PASSWORD` con valori propri della destinazione. La password dell'admin **non viene copiata dalla sorgente**: l'import richiede `ADMIN_INITIAL_PASSWORD` e genera un nuovo hash con quel valore. Dopo l'import riconfigurare tutti i secret SMTP/LDAP/SSO/AI/Alfresco, verificare endpoint e URL, quindi eseguire i test operativi prima del passaggio in produzione.

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
