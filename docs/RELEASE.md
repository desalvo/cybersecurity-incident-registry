# Release and Hotfix lifecycle

## 0.10.0-1 / RC105: visual-training and hermetic screenshot capture

The PR regression run attached in `logs_124226114072.zip` reported seven
pytest failures from a stale slide-title contract and a separate browser
capture failure for a non-existent Gravatar of a synthetic fixture user.
RC105 restores the historical **AlBot: AI assistiva con RAG sanitizzato**
training slide as slide 74, retaining its knowledge-base and tenant-privacy
explanation. The **AlBot: crea e aggiorna workflow con conferma** slide follows
immediately as slide 75, with an editable native PowerPoint decision diagram.
Both localized decks therefore contain **117 slides**, and the matching
PDFs contain 117 pages. The slide masters, translations, screenshots,
appendix indices and integrity tests are updated together; strict CI
checks for authentic browser captures and media provenance remain mandatory.

The isolated documentation fixture disables remote Gravatar loading for its
synthetic users, without changing the application-wide Gravatar default.
RC105 needs a new green remote PR CI run before merge; the independently
validated bilingual editorial decks are not replacements for same-run CI
screenshot evidence.

## 0.10.0-1 / RC104: PR CI recovery after RC103

GitHub Actions run `45914128899` reported **32 failed, 1,215 passed, 59 skipped**
tests and a separate real-UI screenshot failure. The first runtime cause was a
Jinja `%>` typo in the AlBot widget, blocking rendering of the main application.
Other failures revealed inline styles forbidden by the production CSP, a missing
Tenants Default AlBot allowlist/navigation path, leftover Markdown links to
PPTX moved outside the repository, and Node dependencies absent from the
quality-gates job where the PowerPoint regression tests execute.

RC104 restores strict Jinja/CSP conformance; permits AlBot draft and preview
configuration operations in Tenants Default **only for super admins**; preserves
the explicit import confirmation, tenant isolation, and session-bound drafts; and
installs pinned PptxGenJS/image-size tooling before pytest, as the UI capture job
already does. Contract tests are updated to the RC102 immutable training release
pipeline without bypassing documentation, digest or integrity gates. The earlier
slide text that validates AlBot's workflow-authoring role remains unchanged.

A Python 3.13 isolated virtualenv was provisioned from the project's offline
wheel archive. Focused local integration and regression checks were run after
the fixes; details are in the RC104 verification report. A new remote CI run
on the corrected PR head is required before merging or production promotion.

## 0.10.0-1 / RC103: AlBot workflow authoring

AlBot now prepares new tenant workflows and safe updates to existing workflows from
step-by-step natural-language specifications, including required steps, completion
prerequisites, severity/data/risk conditions and linked configured documents and
notifications. Tenant admins may create a workflow in their active tenant; super admins
can also manage **Tenants Default**. The interface offers a portable JSON download
or an editable preview that requires explicit confirmation before a transactional
write. Existing-incident workflows cannot be destructively changed.

Updated both source-driven 116-slide PowerPoint decks and exported the matching
116-page PDF training documents, which remain **outside** the main Git source
history, consistent with the RC102 GitHub Releases publication design. See
`docs/RC103_ALBOT_WORKFLOW_AUTHORING.md` for operations and security policy.

**Validation:** Python compile checks and bilingual slide/PDF generation pass
locally. Full Flask/PostgreSQL integration tests and remote GitHub CI require the
project runtime and have not yet been executed for RC103.


<a id="0100-1--rc1-linea-di-sviluppo-corrente"></a>

## 0.10.0-1 / RC1: linea di sviluppo corrente

La release in sviluppo passa a **0.10.0-1** su richiesta dell'utente. È un nuovo
identificatore funzionale: Hotfix 1–7 e RC precedenti restano nella cronologia
della **0.9.0-1**, il cui tag esistente non viene alterato. Baseline del cumulativo:
`cybersecurity-incident-registry-0.9.0-1-ui-rc20.zip`, SHA-256
`163e7f80e68b01c775c3e0188d292f025f1850d75d2ce70f481d09807996b760`.

### Identità coerente di sorgenti, documenti e immagine

`VERSION` contiene `0.10.0-1`. `BUILD` è generato in formato `YYYYMMDD`, nel fuso
`Europe/Rome`, da `scripts/prepare_release_metadata.py`. La CI calcola un solo
valore per esecuzione, lo passa ai job e lo scrive prima di verifiche, screenshot,
manuali e build Docker. Le etichette OCI e i metadati runtime/documentali usano
lo stesso valore. I file distribuiti prevalgono sugli override d'ambiente legacy,
così un Deployment aggiornato non continua a mostrare 0.9.0-1/20260902.

La nuova versione è allineata in applicazione, help, README, Helm/OpenShift,
validatori, documenti PDF, brochure, presentazione e metadati SBOM applicativi.
Le attestazioni, i test di compatibilità con vecchi export, le note storiche e
i mock approvati mantengono i dati originali dove descrivono il passato.

### Aggiornamento da 0.9.0-1

Non è necessario reimportare il database. Usare il percorso automatico già
presente: backup coerente di database/storage, arresto delle vecchie repliche,
aggiornamento a un'immagine verificata e avvio iniziale di una sola replica.
L'entrypoint completa le migrazioni prima di aprire i worker HTTP/HTTPS.
Il ledger `cir_schema_migrations` e la revisione `20261122_01_legacy_bridge`
restano invariati; questo cambio di versione non introduce DDL aggiuntivo.
Un database già migrato viene riconosciuto senza ripetere inizializzazioni o
sovrascrivere Tenants Default e preferenze UI. Gli schemi sconosciuti/più recenti
continuano a bloccare l'avvio. [Procedura, verifiche e rollback](MIGRATION.md#aggiornamento-a-0100-1-da-090-1).


### Copertine approvate, formazione e revisione periodica

Dal 23 novembre 2026 la copertina approvata è applicata ai manuali PDF e online,
alle brochure e alle guide PDF scaricate dall'applicazione. Dati About, URL del
progetto e sei piattaforme sono condivisi con il runtime. Le guide mantengono
contenuti, ricerca e navigazione; il nuovo indice laterale documentale conserva
anche il menu operativo dell'applicazione.

Il PowerPoint didattico ha 34 slide modificabili con note, esercizi step-by-step,
prime pagine dei manuali e riferimenti di compliance/sviluppo sicuro. Il job CI
produce 17 screenshot reali con dati fittizi isolati, 8 PDF e PPTX completo; verifica
hash e commit/versione/build dell'intero batch prima di includerlo nel candidato.
L'edizione sorgente contiene segnaposti dichiarati per le acquisizioni non ancora
eseguite. Il nuovo workflow di revisione settimanale SCA/Trivy non pubblica immagini
né rinnova eccezioni. Non sono necessarie ulteriori migrazioni DB per queste
modifiche; resta la procedura di upgrade descritta sopra.

### Limiti e promozione

RC1 è un candidato sorgente. Non trasferisce alla 0.10.0-1 una certificazione
production della 0.9.0-1. `PRODUCTION_IMAGE_DIGEST` resta `PENDING_HOTFIX_REBUILD`.
Prima del rilascio sono necessari i gate CI, PostgreSQL reale, SCA, screenshot
reali e scan Trivy amd64/arm64 dell'esatto digest da promuovere. La risk acceptance
Debian è scaduta il 2026-10-20 e non è estesa da questo cambio di versione.
Il report di verifica e [HANDOFF.md](HANDOFF.md) distinguono i controlli realmente
eseguiti dai gate ancora richiesti. Non è stata costruita o promossa un'immagine.

## Cronologia della linea 0.9.0-1

Le sezioni seguenti sono evidenza storica. Versioni, build, hash e risultati qui
registrati appartengono ai rispettivi candidati e non identificano la 0.10.0-1.

## RC20: interfaccia approvata e migrazione — 2026-11-22

Versione funzionale **0.9.0-1**, build **20260902**, senza cambio di versione funzionale.
Baseline esatta: `cybersecurity-incident-registry-0.9.0-1-design-review-rc19.zip`,
SHA-256 `10badfb6b5f70b17a45b8c40f9c6020a16727bb4b1f3ea0a1609793ac45a3331`.
La consegna RC20 comprende il cumulativo, il checksum e la patch binaria rispetto a tale RC19.

### Interfaccia e funzioni

Implementati i quattro riferimenti approvati: login v2, pagina principale home v1,
dettaglio incidente v1 e assistente v1. Le fotografie originali di apparati,
sicurezza e data breach, senza persone, vengono copiate negli asset runtime senza
modificarne i byte. I sorgenti approvati in `design/` rimangono invariati.

Il registro conserva lista, filtri, ordinamenti, paginazione e operazioni multiple.
Gli incidenti mantengono descrizione e task in due riquadri, comandi reali e frecce;
i vincoli dipendono dal workflow configurato, senza imporre una sequenza ulteriore.
Menu desktop e mobile mantengono destinazioni e permessi. La modalità classica
rimane disponibile. Gli handler inline bloccati dalla CSP sono sostituiti da
listener esterni, incluse conferme, invio dei filtri e indicatori dinamici.

**Admin → Interfaccia globale** è riservato ai superuser. La scelta unica nel
Setting fisico `global_ui_mode` ammette `modern` e `classic`; l'assenza di valore
seleziona `modern`, anche aggiornando un database preesistente. Le preferenze di
tenant o browser non possono sovrascriverla. La scelta esplicita sopravvive ai
riavvii, è registrata nell'audit e si applica alla pagina successivamente caricata.
Il vecchio default OFF dei mock è superato dalla successiva istruzione dell'utente.

AlBot è chiuso all'apertura e richiamabile dalla testata. Usa l'endpoint reale,
CSRF, ruolo e tenant attivo. Il controllo di sessione copre inattività e MFA;
un pannello riferito a un tenant precedente viene bloccato prima del provider.
Ogni richiesta contiene la domanda: la pagina incidente e la cronologia visibile
non vengono aggiunte automaticamente. Documentazione, KB e snapshot database
opzionale seguono la configurazione del plugin. L'icona è neutra e senza persone.

### Screenshot e manuali tramite CI

Il job **Real UI screenshots and documentation** avvia l'app Flask reale su
loopback con database/storage isolati, CSRF attivo e credenziali temporanee.
Esegue login, menu mobile, workflow, permessi, cambio tenant, switch globale e
chat tramite un provider HTTP locale dimostrativo. Produce 13 screenshot,
quattro manuali e `CIR_UI_Screenshots.pdf`. Il manifest lega ciascun file al
commit, viewport, modalità e checksum. Il validatore rifiuta prove mancanti,
errate o di un altro commit, e percorsi fuori dall'artefatto.

Le immagini e i PDF validati vengono installati nella build candidate prima del
build multiarch e di Trivy. La pipeline non modifica direttamente main per
aggiornare le figure; l'artefatto GitHub contiene anche il sorgente cumulativo
con documentazione aggiornata. Le PR dei soli metadati digest restano verificate
e non innescano un nuovo build Docker. Aggiungere il nuovo job ai controlli
obbligatori delle regole di protezione di main.

### Aggiornamento da 0.9.0-1 build 20260902

**Sì: aggiornare l'immagine e ricreare il pod è il meccanismo ordinario.** Si
mantengono PostgreSQL, PVC e mount, variabili operative e Secret esistenti, in
particolare `DATABASE_URL`, `SECRET_KEY` e `SETTING_ENCRYPTION_KEY`. Non servono
Full Export/Import, import del bootstrap, reset dell'admin o un comando Alembic.
VERSION/BUILD non distinguono le correzioni cumulative: registrare anche il
vecchio e il nuovo digest OCI.

1. Prima dell'intervento, provare il candidato su una copia dei dati, preparare
   un backup coerente di database e file persistenti e prevedere manutenzione.
2. Fermare le vecchie repliche web; aggiornare al **digest approvato dalla CI**,
   quindi avviare una sola replica con un worker applicativo per il primo avvio.
   Il database rimane attivo. Verificare startup probe e timeout: manifest vecchi
   senza startup probe possono riavviare il pod durante una migrazione lenta.
3. L'entrypoint esegue `python -m app.migrate` con l'utente runtime prima di
   avviare i worker HTTP/HTTPS. Le revisioni mancanti e il riallineamento
   PostgreSQL sono serializzati dal lock applicativo. Se manca, crea **Tenants Default**
   dalla configurazione di `default`; una sorgente esistente non viene ricreata.
   Un tenant ordinario già chiamato `Tenants Default` va rinominato prima.
   Rivedere le credenziali di integrazione copiate nella nuova sorgente condivisa.
4. Controllare avvio, readiness, accesso, tenant, incidenti, workflow, documenti,
   integrazioni e scelta dell'interfaccia. Ripristinare quindi repliche e worker
   necessari, compatibilmente con lo storage usato.

La sola nuova UI usa la tabella `setting` esistente; l'aggiornamento cumulativo da
una build precedente a Tenants Default include invece le migrazioni già descritte.
Non cambiare contestualmente major PostgreSQL, `PGDATA`, Secret o layout PVC solo
per aggiornare CIR. I vecchi volumi separati supportati dall'app non richiedono
una conversione al PVC unico. Il chart Helm non adotta automaticamente un'installazione
preesistente e non deve essere applicato indiscriminatamente sopra i vecchi mount.
Dopo modifiche di schema, un rollback può richiedere il ripristino del backup
coerente e della vecchia immagine; il solo `rollout undo` non ripristina il database.
La UI classica, invece, si riattiva dallo switch senza rollback del database.
Procedura e comandi: [MIGRATION.md](MIGRATION.md#aggiornamento-a-rc20-da-090-1-build-20260902).

### Migrazioni automatiche versionate

RC20 introduce il registro tecnico `cir_schema_migrations`, separato da VERSION
e BUILD. La prima revisione, `20261122_01_legacy_bridge`, adotta le installazioni
precedenti senza registro usando le migrazioni cumulative idempotenti. Gli avvii
successivi eseguono solo le revisioni mancanti; il normale bootstrap dei dati
resta attivo, anche dopo Full Import. Il registro tecnico non viene esportato
come configurazione del tenant né sostituito da un restore applicativo.

Lo schema viene confrontato con tabelle e colonne richieste dai modelli. Una
revisione sconosciuta/più recente, una cronologia incoerente o una migrazione
fallita impediscono l'avvio. I marker vengono scritti nella stessa transazione
finale dei dati di bootstrap: nessuna migrazione viene marcata completata prima
del successo. Alcune DDL storiche hanno commit separati; in caso di arresto
possono restare modifiche parziali, riprese al riavvio dalle operazioni
idempotenti. Il meccanismo non sostituisce un backup e non esegue downgrade.

Corretti l'ordine di creazione di `auth_provider`, l'ispezione delle colonne
dopo DDL e il primo backfill delle date. Flag workflow, operazioni automatiche
volutamente vuote e testi di notifica personalizzati non vengono riportati ai
default a ogni avvio. I vincoli PostgreSQL obbligatori falliscono esplicitamente
se non applicabili; duplicati e relazioni orfane richiedono una correzione dei
dati, senza cancellazioni automatiche. Le sequenze vengono riallineate anche
prima che il bridge inserisca un tenant `default` mancante.

Per le prossime versioni, ogni modifica dello schema deve aggiungere una
revisione ordinata e un test di upgrade dal precedente schema supportato; una
revisione già pubblicata non va riscritta. Sono supportate le transizioni
implementate e verificate, non modifiche arbitrarie del database o versioni
future sconosciute. L'upgrade avviene in manutenzione, senza vecchie repliche o
Full Import concorrenti. La serializzazione production richiede PostgreSQL;
non è dichiarato supporto a migrazioni SQLite concorrenti.

### Stato del candidato

I controlli locali realmente eseguiti sono elencati nell'[Handoff](HANDOFF.md) e
nel report RC20. Un ambiente di compatibilità Python 3.13 con wheel disponibili
ha eseguito vere prove SQLite/SQLAlchemy/HTTP, incluse migrazione dallo schema
RC16 e import completo. Le versioni delle dipendenze differiscono dai pin CI:
non vengono dichiarati PASS di pytest completo con Python 3.12, PostgreSQL,
browser, SCA o Trivy. I PDF nel sorgente locale aggiornano il testo; gli screenshot reali
saranno aggiunti dal job CI, senza usare mock al loro posto.

`PRODUCTION_IMAGE_DIGEST=PENDING_HOTFIX_REBUILD`. Nessuna immagine costruita o
promossa in questa consegna. La disposition Debian è ancora scaduta al
**2026-10-20** e blocca il gate reale: occorre una revisione separata con evidenze
aggiornate. Non sono state ampliate eccezioni, disabilitati gate o alterata la
politica HIGH/CRITICAL Python.

Le sezioni che seguono sono cronologia: i riferimenti a UI non implementata,
assistente da approvare e switch OFF descrivono lo stato RC19, superato da RC20.

## Candidato RC19 - revisione grafica da approvare - 2026-11-22

Login `design/login-v2/`, pagina principale `design/home-v1/` con hero
cybersecurity e dettaglio `design/incident-v1/` sono approvati integralmente.
Sorgenti, renderer e fotografie restano identici alla precedente consegna RC19.
Il passo corrente propone lo **spazio per l'assistente AI** nelle pagine
autenticate, in `design/assistant-v1/`, ancora da approvare.

AlBot è richiamabile dalla testata, con pannello destro da 360 px affiancato
su viewport da 1800 px; al di sotto usa una vista dedicata richiudibile, a
schermo intero su mobile. Le tre tavole `CIR_Assistant_v1` mostrano dettaglio,
registro e richiamo/conversazione mobile; accompagnate da PDF e HTML autonomo.
Liste, blocchi procedurali e comandi restano accessibili nella pagina di lavoro.
Il pannello rappresenta guida applicativa basata sulle capacità esistenti:
nessuna lettura automatica dell'incidente aperto, cronologia backend o esecuzione
di operazioni. La demo usa risposte fittizie e non chiama servizi AI.
L'icona di conversazione sostituisce il volto soltanto nel mock; l'asset runtime
resta invariato. Contratto e inventario dei sorgenti documentano il confine.

Il dettaglio conserva il layout operativo del sorgente: blocchi procedurali
numerati, riquadro descrittivo sopra e task con comando sotto, frecce orizzontali
su desktop e verticali su mobile. Evidenzia fase corrente, completamento e
scadenze senza imporre un nuovo vincolo sequenziale alle fasi successive.
Restano accessibili dati generali, responsabili, conseguenze/misure,
azioni, promemoria, documenti e Alfresco, moduli e notifiche. L'inventario del
sorgente distingue permessi, vincoli configurati e percorsi applicativi reali.

La consegna `CIR_Incident_v1` contiene tre tavole native (desktop, mobile,
sezioni operative), un PDF e un HTML autonomo con dati fittizi. I comandi nel
prototipo non eseguono operazioni su CIR, Alfresco o servizi esterni. Le tavole
non sono screenshot browser. La precedente timeline e le fotografie
amministrative rimangono proposte superate. Applicazione e documenti adottati
non vengono modificati; il report registra solo le verifiche effettive.

La login mantiene il testo «Gestione degli incidenti di sicurezza e tracciabilità
delle attività.» e su mobile logo/nome completo sopra l'immagine senza slogan.
La home conserva lista, geometria, menu e hero approvati; la scala della foto è
132% dell'altezza del banner desktop e 100% mobile, allineata a destra.

Versione funzionale **0.9.0-1**, build **20260902**. Baseline esatta: cumulativo
RC18 aggiornato con conservazione di 20 package,
SHA-256 `fc4ad0dad5ea918dfb7a6961d6b4288d90234ae6600f2e48e0dd64a7dfc199bc`.

La prima consegna RC19 preparava tre proposte: interfaccia desktop/mobile, prima pagina
dei manuali e brochure. Le immagini originali generate non contengono persone
e rappresentano fascicoli d'incidente, workflow, documenti e notifiche.
Include sorgenti e prototipi riproducibili sotto `docs/design/`, con provenienza
in `docs/visual-assets/PROVENANCE.json`. **Quelle prime proposte non costituiscono approvazione delle
schermate successive; copertine e brochure restano da valutare.** La prima revisione
procedeva per step sul solo web: login, home e incidente desktop/mobile, menu
mobile aperto e interruttore globale. Il primo PDF web conteneva otto tavole. I PDF adottati e i
generatori documentali ordinari restano quelli della baseline.

Il mock web usa dati dimostrativi senza connessioni al backend. Lo switch globale
è dimostrativo, inizialmente disattivato e riservato ai super admin; il contratto
per l'implementazione prevede un'impostazione unica per tutti i tenant e utenti,
con ritorno alla UI attuale. La persistenza server è ancora da implementare.

I file applicativi `app/` restano quelli della baseline RC18. Il PowerPoint
esistente resta disponibile; la sua anteprima PDF riproduce le 21 slide e non
include le note relatore, che si trovano nel PPTX. Il report di questa consegna
registra i controlli sui mock e il packaging, senza estendere gli
esiti offline RC18 a test applicativi o gate production non eseguiti.

`PRODUCTION_IMAGE_DIGEST` resta `PENDING_HOTFIX_REBUILD`; la disposition scaduta
il 2026-10-20 non viene prorogata. Guida alla ripresa in [HANDOFF.md](HANDOFF.md).

## Candidato RC18 - 2026-11-22

Versione funzionale **0.9.0-1**, build **20260902**. Baseline: RC17 verificata, SHA-256 `6ef38bd0c8bf93c4404000300e8ff21049ceb90c1d0b532e7b3ef08b4d477c37`.

RC18 completa inizializzazione di Tenants Default dal default operativo, portabilità del tenant speciale, inclusione nel bootstrap, ciclo di vita e notifiche di obsolescenza, mapping degli ID delle dipendenze e protezioni dalle cancellazioni in uso. Introduce installatori Helm/OpenShift e materiale didattico aggiornato. Le revisioni precedenti restano documentate sotto.

`PRODUCTION_IMAGE_DIGEST` resta `PENDING_HOTFIX_REBUILD`. Nessuna immagine production è stata costruita o promossa durante la preparazione. La risk acceptance Debian con scadenza 2026-10-20 è scaduta: deve essere riesaminata sulla base di evidenze attuali, senza bypass. Risultati effettivi e limiti in [TESTING_AND_PRODUCTION.md](TESTING_AND_PRODUCTION.md) e [HANDOFF.md](HANDOFF.md).


Release-candidate, production-release and cumulative Hotfix documentation for 0.9.0-1. Hotfixes correct the same functional version and do not create new functional releases.

## Evidenze storiche RC17 Tenants Default

Stato della RC17 al **2026-11-22**: candidato cumulativo basato sulla RC16; versione
funzionale **0.9.0-1**, build **20260902**. Il dettaglio operativo è in
[MIGRATION.md](MIGRATION.md#tenants-default-rc18); lo stato riprendibile è in
[HANDOFF.md](HANDOFF.md). Le sezioni successive conservano le evidenze storiche
delle precedenti release.

La RC introduce il tenant speciale, propagazione con provenienza e gestione delle
collisioni, impostazioni condivise con override locali, avvisi di cancellazione,
catalogo workflow con installazioni ripetute indipendenti ed export/import completo
del tenant di defaults con documenti, asset e credenziali opzionali. Comprende
isolamento dei nuovi documenti, lettori di configurazione tenant-aware anche nei
report e migrazione delle identità dei destinatari. Le correzioni cumulative
Alfresco, bootstrap, recupero import e pipeline della RC16 restano nella baseline.

La compilazione Python e i verificatori offline della release e del contesto di
sicurezza sono stati eseguiti. Sono inoltre presenti prove SQLite reali della
migrazione e controlli puri dei formati portabili; i risultati conclusivi sono
registrati nel Handoff. **La suite pytest completa, PostgreSQL reale, SCA e Trivy
non sono certificati da questo ambiente**, che non dispone delle dipendenze web,
di pytest o di un runtime container e non riesce a scaricarli.

I test unitari della disposition storica usano una data di riferimento solo nel
test. Il gate production mantiene l'orologio reale e la policy invariata, scaduta
il **2026-10-20**. È aggiunto un test che invoca il valutatore reale per verificare
il rifiuto della policy scaduta. Nessuna immagine è stata costruita o promossa;
`PRODUCTION_IMAGE_DIGEST` rimane `PENDING_HOTFIX_REBUILD`.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `RELEASE_CANDIDATE_ROUND18.md`
- `PRODUCTION_RELEASE_0.9.0-1.md`
- `RELEASE_NOTES_0.9.0-1.md`
- `RELEASE_NOTES_0.9.0-1_en.md`
- `APPLICATION_HOTFIX_0.9.0-1.md`

---

## Historical source: `RELEASE_CANDIDATE_ROUND18.md`

Release: `0.9.0-1`  
Build: `20260902`
Baseline: `0.8.0` (build `20260718`)

## Release lineage

This Release Candidate is the cumulative result of Rounds 1-18 applied to the 0.8.0 baseline. All round changes belong to functional release `0.9.0-1`; round numbers identify internal audit/development milestones and are not intermediate application releases. See `docs/RELEASE.md` / `docs/RELEASE.md`.

## RC status — promoted

This document preserves the Release Candidate criteria and audit trail. The candidate was formally promoted to **production release 0.9.0-1 on 2026-09-03** after completion of the external gates. The authoritative production record is `docs/RELEASE.md`.

## Offline release gates

- Full standard pytest regression must pass; only the explicitly opt-in real-PostgreSQL tests may be skipped when no PostgreSQL test URL is configured.
- `python -m compileall` must pass.
- `pip check` must pass in the isolated wheel environment.
- Shell scripts must parse with their declared interpreter.
- Docker/Kubernetes release metadata must match `VERSION` and `BUILD`.
- Active production/Kubernetes manifests must not use `:latest` for the CIR application release.
- Production Compose must retain read-only root filesystem, no-new-privileges, CSRF enabled, Secure cookies/HSTS, and fail-closed root fallback.
- Kubernetes must retain non-root execution, RuntimeDefault seccomp, read-only root filesystem, dropped capabilities and disabled automatic service-account tokens.
- `k8s/secrets.example.yaml` must remain an example only and must not be included in active Kustomize resources.
- Release packaging must exclude `.env`, private keys/certificates, runtime databases/uploads/backups and Python caches.
- `sbom/SBOM_ROUND18.cdx.json` must be valid CycloneDX 1.6 and match the application release version.
- `scripts/verify_release_candidate.py` must pass.
- The final release ZIP must have a SHA-256 sidecar checksum.

## External gates required before production (completed on 2026-09-03)

1. **Live SCA:** run `scripts/run_sca.sh` in a network-enabled release job with `pip-audit` installed. Resolve or formally accept any relevant high/critical vulnerability before promotion.
2. **Real PostgreSQL:** run all seven `pytest -m postgres` integration tests against the supported PostgreSQL 18.6 test container/database (`scripts/run_postgres_tests.sh`).
3. **Final image scan:** scan the exact production container image, including OS/LibreOffice/PostgreSQL-client packages, with the organization-approved scanner (for example Trivy or Grype).
4. **Immutable image promotion:** record the registry digest and deploy with `image@sha256:<digest>`. For Compose, set `CIR_PRODUCTION_IMAGE` to that digest. For Kubernetes, promote an environment overlay that resolves to the same digest.

All four gates above were subsequently completed for the final `0.9.0-1` image. The immutable OCI index digest is `sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`; see `docs/RELEASE.md` for the final evidence summary.

## Round 18 verification result

Offline RC verification completed on 2026-09-02: **292 passed, 7 skipped, 0 failed**. SBOM generation, `pip check`, compilation, shell syntax and YAML parsing all passed. The seven skipped tests are exactly the opt-in real-PostgreSQL tests; Docker is unavailable in the analysis environment, so the external gates above remain pending rather than being reported as successful.

## RC R8 — final container security disposition

After R7, application/Python vulnerability findings are required to be zero. Residual Debian HIGH/CRITICAL findings are governed by `TRIVY_RISK_ACCEPTANCE_R8.json` and `docs/SECURITY.md`; this is a time-bounded exact allowlist, not a generic `--ignore-unfixed` policy.

Before production promotion, run the final multi-architecture image through:

```bash
./scripts/run_trivy_production_gate.sh IMAGE
```

The gate scans both amd64 and arm64 and fails on any Python HIGH/CRITICAL, new/unreviewed OS HIGH/CRITICAL, newly patchable accepted CVE, or expired acceptance. The exact image that passes must then be pinned by registry SHA-256 digest.

---

## Historical source: `PRODUCTION_RELEASE_0.9.0-1.md`

Release: `0.9.0-1`  
Build: `20260902`  
Baseline: `0.8.0` (build `20260718`)  
Promotion date: `2026-09-03`

## Production image

- Tag: `desalvo/cybersecurity-incident-registry:0.9.0-1`
- OCI index digest: `sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`
- Immutable reference: `desalvo/cybersecurity-incident-registry@sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`
- Platforms validated: `linux/amd64`, `linux/arm64`

The additional `unknown/unknown` manifests shown by Docker Buildx are attestation manifests associated with the two platform images; they are not extra runnable application platforms.

## Final validation gates

All release gates required by the Release Candidate process have been completed:

- Standard pytest suite: **295 passed, 7 skipped, 0 failed**.
- Real PostgreSQL suite: **7 passed, 295 deselected**.
- `python -m pip check`: **PASS — No broken requirements found**.
- Release consistency gate: **PASS**, version `0.9.0-1`, build `20260902`.
- Live SCA / `pip-audit`: **PASS — No known vulnerabilities found**.
- Trivy production gate on `linux/amd64`: **PASS**.
- Trivy production gate on `linux/arm64`: **PASS**.
- Residual OS risk acceptance: **30 reviewed CVEs**, governed by `TRIVY_RISK_ACCEPTANCE_R8.json`, valid until **2026-10-03**.
- Immutable registry digest recorded: **PASS**.

## Deployment requirement

Production deployments should use the immutable image reference:

```text
desalvo/cybersecurity-incident-registry@sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b
```

`k8s/kustomization.yaml` is pinned to this digest. Docker Compose production should set `CIR_PRODUCTION_IMAGE` to the same immutable reference.

## Residual-risk follow-up

The R8 acceptance is time-bounded. Before or on **2026-10-03**, rerun the production Trivy gate. The gate is designed to fail if an accepted CVE becomes patchable, a new HIGH/CRITICAL finding appears, a Python HIGH/CRITICAL appears, or the acceptance expires.

Version `0.8.0` is the functional baseline. All changes introduced in development/audit Rounds 1–18 and RC hardening R4–R8 belong to the single functional release `0.9.0-1`; those round/RC labels are internal development milestones, not intermediate functional releases.
## Kubernetes manifest hotfix - 2026-09-03

After production validation, a Kubernetes-only packaging defect was confirmed in the original manifest: separate PVCs mounted below `/data` were incompatible with Full Import atomic staging while `readOnlyRootFilesystem: true` was enabled. The manifest now mounts a single `cir-data` PVC at `/data`, preserving the read-only root filesystem while ensuring staging and destination directories share the same writable filesystem. Application code and the OCI production image are unchanged, therefore the immutable image digest above remains valid. See `docs/MIGRATION.md`.

## Application hotfix status - 2026-09-03

A PostgreSQL application hotfix was prepared after production migration testing. It fixes sequence alignment after Full Import and advisory-lock connection ownership. Because application code changed, the OCI digest recorded above describes the **pre-hotfix** production image only and must not be used as evidence that the hotfix is deployed.

At this historical stage the hotfix source package deliberately left the production digest unpinned and Kustomize temporarily referenced the version tag. The cumulative Hotfix 7 image was subsequently rebuilt, gated and promoted; the authoritative final digest is recorded in the Hotfix 7 final production record below.

## Pending cumulative Hotfix 2 - Alfresco (2026-09-03)

The package also contains the Alfresco parent-node resolution hotfix documented in `docs/ADMIN_ALFRESCO.md`. At this historical stage the old OCI digest could not be reused; cumulative Hotfix 1-7 was later rebuilt and validated, with the final immutable digest recorded below.

## Pending cumulative Hotfix 3 + Hotfix 4 - Alfresco storage and automatic incident reports (2026-09-03)

The current source package further includes the cumulative Alfresco storage changes documented in `docs/ADMIN_ALFRESCO.md` and the tenant-controlled automatic incident-report feature documented in `docs/ADMIN_ALFRESCO.md`.

For Hotfix 4, tenant policy controls whether the per-incident option `Genera e aggiorna automaticamente report su Alfresco` is exposed and whether it is enabled by default for newly created incidents. The package default is **visible = enabled** and **new-incident default = disabled**. The incident option is never rendered when the Alfresco plugin itself is disabled.

When enabled for an incident, CIR keeps one canonical PDF report directly below the corresponding Alfresco incident directory as `incident-<id>/incident-<id>-report.pdf`. Report-relevant mutations update the existing Alfresco node when possible; a missing remote node is recreated. A content fingerprint suppresses redundant updates, and safe GET requests do not trigger remote writes.

Because this is application code, the historical OCI digest at the top of this document remains pre-hotfix evidence only. Cumulative Hotfix 1-7 was later rebuilt and passed the complete production gate; the final immutable digest is recorded below.

## Pending cumulative Hotfix 5-7 - Alfresco, naming, security disposition and GitHub automation (2026-09-20)

The current source package also contains Hotfix 5 (tenant-scoped Alfresco configuration, remote deletion and read-only synchronization), Hotfix 6 (incident-name-aware Alfresco folder/report naming) and Hotfix 7 (temporary Debian Trixie security disposition plus GitHub Actions CI/release automation).

The original R8 acceptance of 30 CVEs through 2026-10-03 is historical evidence for the pre-hotfix image. Hotfix 7 supersedes the active policy with **47 explicitly reviewed CVEs**, including the five findings reviewed on 2026-09-20, and extends the time-bounded review deadline to **2026-10-20**. The new findings are package-scoped; util-linux findings are additionally constrained to the reviewed `2.41.5-0+deb13u1` version family. Any new HIGH/CRITICAL, Python HIGH/CRITICAL, out-of-scope package/version, available `FixedVersion`, or expired acceptance remains blocking.

The historical digest at the top of this file does not contain Hotfix 1-7. The GitHub workflow built the cumulative candidate, scanned its exact multi-architecture digest and promoted that same digest to `latest` only after all gates passed. The resulting immutable OCI index digest is recorded in the final production record below.

---

## Historical source: `RELEASE_NOTES_0.9.0-1.md`

**Release:** 0.9.0-1  
**Build:** 20260902  
**Baseline di partenza:** 0.8.0 (build 20260718)

## Genealogia della release

La 0.9.0-1 è la nuova versione funzionale successiva alla baseline 0.8.0. Tutti i cambiamenti introdotti durante i Round 1-18 appartengono cumulativamente alla 0.9.0-1. I round sono milestone interne di sviluppo, audit, hardening e verifica e **non** costituiscono release funzionali intermedie 0.8.x.

I nomi storici di alcuni artefatti di lavoro che contengono stringhe come `0.8.0-1`, `0.8.0-2-hardened-roundX` o simili descrivono esclusivamente pacchetti intermedi usati durante l'audit e non la genealogia ufficiale della release.

## Principali cambiamenti rispetto alla 0.8.0

### Sicurezza applicativa e autenticazione

- Rafforzati CSRF, cookie, header HTTP, session lifecycle e policy di produzione.
- Rafforzato il rate limiting del login e impedito lo spoofing di `X-Forwarded-For` quando il chiamante non appartiene a proxy esplicitamente fidati.
- Rafforzata la gestione delle password locali, delle credenziali bootstrap e dei segreti di configurazione.
- Le credenziali SMTP, LDAP e SSO non vengono più reimmesse in chiaro nell'HTML amministrativo.

### Isolamento multi-tenant

- Corrette query e operazioni amministrative non sufficientemente tenant-scoped.
- Template e tipi di notifica, knowledge base e contesto AI, scheduler, backup, audit log, destinatari e varie operazioni CRUD rispettano ora il tenant attivo/proprietario.
- Rafforzati import tenant e rimappatura degli identificativi per evitare collisioni o contaminazioni cross-tenant.

### Filesystem, upload e documenti

- Centralizzata la validazione dei percorsi derivati da metadata persistenti.
- Documenti, allegati, loghi e file AI sono confinati alle directory gestite e rifiutano traversal, path assoluti e nomi non canonici.
- Rafforzati validazione upload, permessi dei file, gestione degli archivi e cleanup.

### Outbound HTTP e plugin

- Rafforzata la protezione SSRF e la validazione delle destinazioni HTTP/HTTPS per motori AI e Alfresco.
- Disabilitati redirect impliciti dove potevano indebolire la validazione della destinazione.
- Ridotta l'esposizione di dettagli di eccezione nelle interfacce amministrative.

### Backup, import e crash recovery

- Il Full Import usa transazioni database e staging filesystem coordinati.
- Backup/import sono serializzati con advisory lock PostgreSQL appropriati.
- I restore possono ripristinare in modo atomico i volumi e correggere sequence/relazioni.
- Aggiunto un journal persistente con commit token DB per distinguere restore committati e non committati dopo crash.
- Test end-to-end terminano realmente un worker con `SIGKILL` prima e dopo il commit e verificano il recovery al riavvio.

### PostgreSQL e concorrenza

- Aggiunti test PostgreSQL reali opt-in tramite Docker Compose per advisory lock, rollback, sequence e crash recovery.
- Separati namespace e modalità shared/exclusive dei lock di manutenzione per evitare collisioni e backup concorrenti a restore distruttivi.

### Supply chain e deployment production

- PostgreSQL di riferimento aggiornato a 18.6 e runtime Python di riferimento a 3.12.14.
- Aggiunto `docker-compose.production.yml` con root filesystem read-only, `no-new-privileges`, capability ridotte e policy production fail-closed.
- Kubernetes usa seccomp `RuntimeDefault`, capability drop, filesystem applicativo read-only, service-account token disabilitato e Secret esterni.
- Aggiunto SBOM CycloneDX 1.6 transitive con hash SHA-256 delle wheel.
- Aggiunti gate SCA, verifica Release Candidate e checksum SHA-256 del pacchetto.

## Validazione production

La Release Candidate R8 è stata promossa a production il 3 settembre 2026 dopo il completamento di tutti i gate:

- suite standard: **295 passed, 7 skipped, 0 failed**;
- suite PostgreSQL reale: **7 passed, 295 deselected**;
- `pip check`: **PASS**;
- SCA live / `pip-audit`: **No known vulnerabilities found**;
- gate Trivy R8: **PASS su linux/amd64 e linux/arm64**;
- digest OCI immutabile registrato: `sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`.

L'immagine production è `desalvo/cybersecurity-incident-registry:0.9.0-1`; per i deployment production è raccomandato il riferimento immutabile `desalvo/cybersecurity-incident-registry@sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`. I 30 CVE OS residui sono coperti dalla policy R8 time-bounded, valida fino al **3 ottobre 2026**, e devono essere riesaminati entro tale data.

## Documentazione tecnica dei round

I file `docs/DEVELOPMENT_HISTORY.md` ... `docs/DEVELOPMENT_HISTORY.md` conservano la traccia tecnica delle singole fasi di audit. Devono essere letti come cronologia interna della costruzione della **0.9.0-1 a partire dalla 0.8.0**, non come elenco di release separate.

### Immagine Docker multi-arch

La release include `scripts/build_multiarch_image.sh`, che costruisce e pubblica per default `desalvo/cybersecurity-incident-registry:latest` come manifest multi-arch per `linux/amd64` e `linux/arm64` tramite Docker Buildx. Repository e tag sono configurabili separatamente con `--repository`/`--tag` o `CIR_DOCKER_REPOSITORY`/`CIR_DOCKER_TAG`; `--image`/`CIR_DOCKER_IMAGE` resta disponibile per impostare il riferimento completo. Prima dell'esecuzione è necessario autenticarsi al registry con `docker login`.

La migrazione operativa dalla baseline 0.8.0 è documentata in `docs/MIGRATION.md`, con le modifiche richieste a Docker Compose, Compose production, Kubernetes/Kustomize, Secret, PVC e variabili di sicurezza.
## Aggiornamento di sicurezza RC R4

Il gate SCA live eseguito sulla RC R3 ha rilevato vulnerabilità note nei pin `pypdf==6.10.2` e `cryptography==46.0.7`. La RC R4 aggiorna esclusivamente queste dipendenze a `pypdf==6.16.2` e `cryptography==50.0.1`. Non vengono introdotte modifiche funzionali o di schema. Poiché cambiano i binari delle dipendenze, tutti i gate production devono essere rieseguiti sulla R4 prima della promozione.

## Stabilizzazione test RC R5

Durante la validazione finale e stato stabilizzato il test esterno SIGKILL post-commit: il timeout del checkpoint del worker SQLite passa da 15 a 30 secondi ed e configurabile con `CIR_CRASH_TEST_CHECKPOINT_TIMEOUT`. La modifica riguarda esclusivamente l'harness di test; non cambia il comportamento runtime di CIR.

### RC R6 - hardening dell'immagine container

La RC R6 non modifica il comportamento applicativo. L'immagine runtime esclude SBOM e audit storici (che causavano falsi positivi nei container scanner), usa `libreoffice-writer-nogui` al posto dei pacchetti LibreOffice GUI, rimuove `curl` dall'healthcheck usando la standard library Python e applica gli aggiornamenti Debian disponibili durante la build. Dopo la build deve essere rieseguito Trivy sull'immagine pubblicata.

### RC R7 - minimizzazione finale container

- Dockerfile convertito a build multi-stage con virtualenv applicativo isolato.
- `pip`, `setuptools` e `wheel` rimossi dal runtime dopo l'installazione delle dipendenze.
- Eliminata dal runtime anche la SBOM incorporata in pip che Trivy poteva interpretare come pacchetti Python installati (`msgpack`/`setuptools`).
- Nessun finding Debian viene nascosto: lo scan OS completo resta un gate production esplicito.

### RC R8 - disposizione finale dei finding container

La RC R8 aggiunge una policy di rischio machine-readable e un gate Trivy fail-closed per i finding Debian residui della R7. Non vengono ignorati genericamente gli `unfixed`: sono ammessi temporaneamente solo i CVE già riesaminati, senza `FixedVersion`, fino al 3 ottobre 2026. Qualunque nuovo HIGH/CRITICAL, qualunque finding Python HIGH/CRITICAL o qualunque CVE accettato che diventi patchabile blocca la release. Il gate scansiona separatamente `linux/amd64` e `linux/arm64`.
## Hotfix manifest Kubernetes - Full Import

Il manifest Kubernetes production della 0.9.0-1 e stato corretto per montare un unico PVC `cir-data` su `/data`. La configurazione precedente con PVC separati sotto `/data/...` lasciava il parent `/data` sul root filesystem read-only e impediva la creazione delle directory di staging atomico del Full Import. La correzione non modifica il codice applicativo ne l'immagine OCI production: il digest resta invariato. Le installazioni che hanno gia creato i vecchi sette PVC devono migrare i dati nel nuovo claim prima del rollout; vedere `docs/MIGRATION.md`.

## Hotfix applicativa 2026-09-03 - PostgreSQL

- Il riallineamento delle sequence dopo Full Import forza ora il flush delle righe ORM con ID espliciti prima di calcolare `MAX(id)`, evitando sequence arretrate e successive duplicate key.
- Scheduler, bootstrap, backup, Full Import e recovery mantengono gli advisory lock PostgreSQL su connessioni dedicate e li rilasciano con `pg_advisory_unlock_all()`, eliminando gli unlock su sessioni diverse dopo commit/pooling.
- Il digest Docker precedente non contiene questa hotfix: deve essere rigenerato, riscadenzato da Trivy e ripinnato prima del rollout. Vedere `docs/RELEASE.md`.

## Hotfix 2 applicativa 2026-09-03 - Alfresco

- Eliminato il fallback di upload Alfresco basato sul pseudo-nodo `-root-`, che su alcune installazioni restituisce HTTP 404.
- Aggiunto `alfresco_parent_node_id`: se presente e usato direttamente come nodo padre; in alternativa un Site viene risolto tramite `/sites/{site}/containers/documentLibrary`.
- Gli upload usano ora `/nodes/{parentNodeId}/children`, mantenendo `target_path` e la sottocartella `incident-<id>`.
- Aggiunto **Salva e testa destinazione** alla pagina amministrativa e il nuovo campo anche al wizard iniziale.
- Mantenute policy SSRF, validazione URL, redirect disabilitati e gestione segreta delle credenziali.
- Come per Hotfix 1, il digest Docker deve essere rigenerato e ripinnato dopo test/SCA/Trivy. Vedere `docs/ADMIN_ALFRESCO.md`.

## Hotfix 3 - upload e storage Alfresco

- Aggiunte le estensioni `.zip` e `.gz` agli upload generali di documenti/allegati azioni, con verifica della signature iniziale.
- Aggiunte le modalità Solo CIR, CIR + Alfresco e Solo Alfresco.
- Ogni incidente usa una propria cartella Alfresco `incident-<id>`, con sottocartelle opzionali per tipo file abilitate per default.
- I documenti Solo Alfresco mantengono metadati CIR e node id remoto senza copia locale nel volume upload.

### Hotfix cumulativa Alfresco auto-report (2026-09-03)

- Aggiunta l'opzione per incidente **Genera e aggiorna automaticamente report su Alfresco**, visibile solo con plugin Alfresco abilitato e se consentita dalla policy del tenant.
- In **Admin -> Tenant** sono configurabili la visibilità dell'opzione (default ON) e il valore predefinito per i nuovi incidenti (default OFF).
- Il report PDF canonico viene creato in `incident-<id>/incident-<id>-report.pdf` e aggiornato sullo stesso nodo Alfresco quando cambiano dati rilevanti per il report.
- Il fingerprint del contenuto evita versioni Alfresco inutili; un nodo remoto eliminato viene ricreato nella cartella corretta dell'incidente.
- Gli errori Alfresco non annullano modifiche dell'incidente già committate; i dettagli restano nei log server.

## Hotfix 5 - Alfresco multi-tenant e sync

Configurazione Alfresco separata per tenant, cancellazione remota dei documenti mantenendo il record CIR, stato remoto sincronizzabile in sola lettura dalla sezione Documenti e documentazione admin aggiornata.

## Hotfix 7 - security disposition Debian e release automation GitHub

- Riesaminati il 20 settembre 2026 i nuovi finding Trixie `CVE-2026-76642`, `CVE-2026-78408`, `CVE-2026-78409`, `CVE-2026-78410` e `CVE-2026-16742` con acceptance temporanea e scoped per package fino al 20 ottobre 2026.
- Il gate resta fail-closed: nuovi HIGH/CRITICAL, finding Python HIGH/CRITICAL, package fuori scope, disponibilita di `FixedVersion` o scadenza della disposition producono FAIL.
- Aggiunta verifica automatica delle assunzioni di hardening runtime (`runAsNonRoot`, UID 10001, no privilege escalation, drop ALL, root filesystem read-only, seccomp RuntimeDefault).
- Aggiunta GitHub Actions CI/release: test completi, PostgreSQL reale, SCA, gate RC, packaging, build multi-arch, Trivy amd64/arm64 e promozione per digest.
- Push su `main` promuove `latest`; push di un tag Git promuove lo stesso tag Docker. Il tag finale viene creato solo dopo il PASS del gate Trivy sull'esatto digest candidato.

---

## Historical source: `RELEASE_NOTES_0.9.0-1_en.md`

**Release:** 0.9.0-1  
**Build:** 20260902  
**Starting baseline:** 0.8.0 (build 20260718)

Version 0.9.0-1 is the functional release following baseline 0.8.0. Every change introduced throughout Rounds 1-18 belongs cumulatively to 0.9.0-1. The rounds are internal development, audit, hardening and verification milestones and **are not** intermediate 0.8.x functional releases.

Historical working-artifact names containing strings such as `0.8.0-1`, `0.8.0-2-hardened-roundX` or similar identify intermediate audit packages only and do not define the official release lineage.

## Main changes from 0.8.0

### Application security and authentication

- Strengthened CSRF, cookies, HTTP security headers, session lifecycle and production policy.
- Hardened login rate limiting and prevented `X-Forwarded-For` spoofing unless the connection comes through explicitly trusted proxies.
- Strengthened local-password, bootstrap-credential and secret configuration handling.
- Stored SMTP, LDAP and SSO credentials are no longer reflected in administrative HTML.

### Multi-tenant isolation

- Corrected administrative queries and operations that were not sufficiently tenant-scoped.
- Notification templates/types, AI knowledge/database context, schedulers, backups, audit logs, recipients and several CRUD paths now consistently honor the active/owning tenant.
- Hardened tenant import and identifier remapping to prevent collisions and cross-tenant contamination.

### Filesystem, uploads and documents

- Centralized validation of filesystem paths derived from persistent metadata.
- Documents, attachments, logos and AI files are confined to managed directories and reject traversal, absolute paths and non-canonical stored names.
- Strengthened upload validation, file permissions, archive handling and cleanup.

### Outbound HTTP and plugins

- Strengthened SSRF protection and HTTP/HTTPS destination validation for AI engines and Alfresco.
- Disabled implicit redirects where they could weaken destination validation.
- Reduced raw exception disclosure in administrative workflows.

### Backup, import and crash recovery

- Full Import coordinates database transactions with staged filesystem activation.
- Backup/import maintenance is serialized with appropriate PostgreSQL advisory locks.
- Restore can atomically recover managed volumes and realign sequences/relations.
- Added a durable restore journal and DB commit token to distinguish committed from uncommitted restores after crashes.
- End-to-end tests actually terminate a worker with `SIGKILL` before and after commit and verify restart recovery.

### PostgreSQL and concurrency

- Added opt-in real PostgreSQL tests through Docker Compose for advisory locks, rollback, sequences and crash recovery.
- Separated maintenance lock namespaces and shared/exclusive modes to avoid collisions and prevent backups from overlapping destructive restores.

### Supply chain and production deployment

- Reference PostgreSQL updated to 18.6 and reference Python runtime to 3.12.14.
- Added `docker-compose.production.yml` with read-only root filesystem, `no-new-privileges`, reduced capabilities and fail-closed production policy.
- Kubernetes uses `RuntimeDefault` seccomp, dropped capabilities, read-only application root filesystem, disabled automatic service-account tokens and external Secrets.
- Added a transitive CycloneDX 1.6 SBOM with SHA-256 hashes of supplied wheels.
- Added SCA gates, Release Candidate verification and SHA-256 release-package checksums.

## Production validation

Release Candidate R8 was promoted to production on 3 September 2026 after all mandatory gates completed successfully:

- standard suite: **295 passed, 7 skipped, 0 failed**;
- real PostgreSQL suite: **7 passed, 295 deselected**;
- `pip check`: **PASS**;
- live SCA / `pip-audit`: **No known vulnerabilities found**;
- R8 Trivy production gate: **PASS on linux/amd64 and linux/arm64**;
- immutable OCI digest recorded: `sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`.

The production image tag is `desalvo/cybersecurity-incident-registry:0.9.0-1`. Production deployments should prefer `desalvo/cybersecurity-incident-registry@sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`. The 30 residual OS CVEs are governed by the time-bounded R8 risk policy through **3 October 2026** and must be re-reviewed by that date.

## Technical round documentation

`docs/DEVELOPMENT_HISTORY.md` ... `docs/DEVELOPMENT_HISTORY.md` retain the technical history of each audit phase. They must be read as the internal history of building **0.9.0-1 from the 0.8.0 baseline**, not as a list of separate releases.

### Multi-architecture Docker image

The release includes `scripts/build_multiarch_image.sh`, which builds and publishes `desalvo/cybersecurity-incident-registry:latest` by default as a Docker Buildx multi-architecture manifest for `linux/amd64` and `linux/arm64`. Repository and tag can be configured independently through `--repository`/`--tag` or `CIR_DOCKER_REPOSITORY`/`CIR_DOCKER_TAG`; `--image`/`CIR_DOCKER_IMAGE` remains available for a complete image reference. Authenticate to the registry with `docker login` before running it.

Operational migration from the 0.8.0 baseline is documented in `docs/MIGRATION.md`, including required changes to Docker Compose, production Compose, Kubernetes/Kustomize, Secrets, PVCs, and security variables.
## RC R4 security update

The live SCA gate executed against RC R3 found known vulnerabilities in the pinned `pypdf==6.10.2` and `cryptography==46.0.7`. RC R4 changes only these dependencies to `pypdf==6.16.2` and `cryptography==50.0.1`. No functional or database-schema change is introduced. Because dependency binaries change, all production gates must be rerun against R4 before promotion.

## RC R5 test stabilization

Final validation stabilized the external post-commit SIGKILL test: the SQLite worker checkpoint timeout is increased from 15 to 30 seconds and can be configured with `CIR_CRASH_TEST_CHECKPOINT_TIMEOUT`. This change affects only the test harness and does not change CIR runtime behavior.

### RC R6 - container image hardening

RC R6 does not change application behaviour. The runtime image excludes historical SBOM/audit artifacts (which caused false positives in container scanners), uses `libreoffice-writer-nogui` instead of GUI LibreOffice packages, removes `curl` from the healthcheck by using Python's standard library, and applies available Debian updates during the build. Trivy must be rerun against the published image after rebuilding.

### RC R7 - final container minimization

- Dockerfile converted to a multi-stage build with an isolated application virtualenv.
- `pip`, `setuptools`, and `wheel` are removed from runtime after dependency installation.
- The pip-embedded SBOM that Trivy could interpret as installed Python packages (`msgpack`/`setuptools`) is no longer present at runtime.
- No Debian finding is hidden: the complete OS scan remains an explicit production gate.

### RC R8 - final container finding disposition

RC R8 adds a machine-readable residual-risk policy and a fail-closed Trivy gate for the Debian findings remaining after R7. It does not generically ignore `unfixed` vulnerabilities: only specifically reviewed CVEs with no `FixedVersion` are temporarily accepted, through 3 October 2026. Any new HIGH/CRITICAL, any Python HIGH/CRITICAL, or any accepted CVE that becomes patchable blocks release. The gate scans `linux/amd64` and `linux/arm64` separately.
## Kubernetes manifest hotfix - Full Import

The 0.9.0-1 production Kubernetes manifest has been corrected to mount one `cir-data` PVC at `/data`. The previous layout with separate PVCs below `/data/...` left the `/data` parent on the read-only root filesystem and prevented creation of the atomic Full Import staging directories. This change does not modify application code or the production OCI image; the image digest is unchanged. Installations that already created the former seven PVCs must migrate their contents into the new claim before rollout; see `docs/MIGRATION.md`.

## Application Hotfix 2 - Alfresco - 2026-09-03

- Removed the Alfresco upload fallback based on the `-root-` pseudo-node, which returns HTTP 404 on some deployments.
- Added `alfresco_parent_node_id`: when present it is used directly as the parent node; otherwise a configured Site is resolved through `/sites/{site}/containers/documentLibrary`.
- Uploads now target `/nodes/{parentNodeId}/children`, preserving `target_path` and the `incident-<id>` subfolder.
- Added **Save and test destination** to the administration page and exposed the new field in the initial setup wizard.
- SSRF policy, URL validation, disabled redirects and secret credential handling remain enforced.
- As with Hotfix 1, the Docker image must be rebuilt, rescanned and repinned after the full production gates. See `docs/ADMIN_ALFRESCO.md`.

## Hotfix 3 - upload and Alfresco storage

- Added `.zip` and `.gz` to general incident/action attachment uploads with magic-signature validation.
- Added CIR-only, CIR + Alfresco, and Alfresco-only document storage modes.
- Every incident is stored in its own Alfresco `incident-<id>` folder, with optional file-type subfolders enabled by default.
- Alfresco-only documents retain CIR metadata and remote node id without a local upload copy.

### Cumulative Alfresco auto-report hotfix (2026-09-03)

- Added the per-incident **Automatically generate and update report on Alfresco** option, visible only when the Alfresco plugin is enabled and the tenant policy allows it.
- **Admin -> Tenant** controls option visibility (default ON) and the default value for newly created incidents (default OFF).
- The canonical incident PDF is created as `incident-<id>/incident-<id>-report.pdf` and updates the same Alfresco node whenever report-relevant data changes.
- A content fingerprint avoids unnecessary Alfresco versions; a remotely deleted report node is recreated in the proper incident directory.
- Alfresco synchronization failures do not undo already committed incident changes; technical details remain in server logs.

## Hotfix 5 - Alfresco multi-tenant and sync

Independent Alfresco configuration per tenant, remote document deletion while retaining CIR records, read-only remote-state synchronization from the Documents section, and updated admin documentation.

## Hotfix 7 - Debian security disposition and GitHub release automation

- Reviewed on 20 September 2026 the new Trixie findings `CVE-2026-76642`, `CVE-2026-78408`, `CVE-2026-78409`, `CVE-2026-78410`, and `CVE-2026-16742`, with package-scoped temporary acceptance through 20 October 2026.
- The gate remains fail-closed: new HIGH/CRITICAL findings, Python HIGH/CRITICAL findings, findings outside the approved package scope, an available `FixedVersion`, or an expired disposition all fail promotion.
- Added automated verification of runtime hardening assumptions (`runAsNonRoot`, UID 10001, no privilege escalation, drop ALL, read-only root filesystem, RuntimeDefault seccomp).
- Added GitHub Actions CI/release automation for the full tests, real PostgreSQL suite, SCA, RC checks, packaging, multi-arch build, amd64/arm64 Trivy gate and digest promotion.
- Pushes to `main` promote `latest`; Git tag pushes promote the same Docker tag. The final tag is created only after the exact candidate digest passes the Trivy gate.

---

## Historical source: `APPLICATION_HOTFIX_0.9.0-1.md`

Date: 2026-09-03

This hotfix keeps the functional version **0.9.0-1** and changes only PostgreSQL coordination/recovery code plus regression tests.

## Fixed: sequence alignment after Full Import

`align_all_table_sequences()` now executes `db.session.flush()` before calculating `MAX(id)` for application tables. Full Import restores many rows with explicit primary keys; without the flush, pending ORM rows could be absent from the `MAX(id)` query and the PostgreSQL sequence could remain behind the imported data. The next automatic INSERT could then fail with `duplicate key value violates unique constraint`, as observed on `audit_log_pkey`.

The existing sequence realignment remains inside the Full Import transaction. PostgreSQL sequence values are non-transactional, while the explicit flush ensures the calculation sees every restored row already queued in the ORM session.

## Fixed: PostgreSQL advisory lock ownership warnings

Scheduler locks previously used Flask-SQLAlchemy's scoped `db.session`. Scheduler work performs commits during a cycle; SQLAlchemy may return the physical connection to the pool after commit, so the later unlock could run on another PostgreSQL session and generate `WARNING: you don't own a lock of type ExclusiveLock`.

The hotfix now:

- holds scheduler advisory locks on a dedicated `db.engine.connect()` connection for the full cycle;
- applies the same dedicated-connection lifetime discipline to bootstrap, backup, Full Import and startup recovery;
- commits immediately after lock acquisition, because advisory locks are session-level, avoiding a long-lived idle/open SQL transaction;
- releases dedicated lock connections with `pg_advisory_unlock_all()`;
- invalidates the SQLAlchemy connection if advisory-lock cleanup fails, preventing a session with a leaked lock from returning to the pool.

## Image/digest status

This hotfix changes application code. The previously validated image digest
`sha256:ff734b8ed7cbc3a979081cd782396088ca0d1dea07092ebfb702efd5d48c8c9b`
does **not** contain this hotfix and must not be used to claim deployment of it.

At preparation time the production digest was intentionally left unpinned and Kubernetes Kustomize temporarily referenced tag `0.9.0-1`. The cumulative Hotfix 7 image has now been built, tested, scanned and promoted; `PRODUCTION_IMAGE_DIGEST` and Kustomize are pinned to the final immutable OCI index digest recorded below.

## Required external validation

1. `python -m pytest -q`
2. `./scripts/run_postgres_tests.sh`
3. `python scripts/verify_release_candidate.py`
4. `./scripts/run_sca.sh`
5. build/push `desalvo/cybersecurity-incident-registry:0.9.0-1` for amd64+arm64
6. `./scripts/run_trivy_production_gate.sh desalvo/cybersecurity-incident-registry:0.9.0-1`
7. obtain the new OCI index digest and pin it before rollout.

## Hotfix 2 cumulative update - Alfresco

The source package also includes the Alfresco destination-resolution fix documented in `docs/ADMIN_ALFRESCO.md`. The rebuilt image must therefore contain both Hotfix 1 (PostgreSQL sequence/advisory-lock lifecycle) and Hotfix 2 (Alfresco real parent-node resolution). A single new immutable multi-arch digest will cover the cumulative hotfix package after external validation.

---


## Hotfix 7 final production record — 2026-09-20

Functional version remains **0.9.0-1**. Hotfixes 1-7 are cumulative corrections to that release, not new functional versions.

The GitHub production pipeline completed the quality gates, real PostgreSQL tests, SCA, multi-architecture build and Trivy production gate before promotion. The scanned candidate was promoted without rebuilding.

- Published tag: `desalvo/cybersecurity-incident-registry:latest`
- OCI index digest: `sha256:37ad92c7437abce6f5a7b8504b8c440cab6f1ac5e38ecdaf287128bffbb9702a`
- Immutable production reference: `desalvo/cybersecurity-incident-registry@sha256:37ad92c7437abce6f5a7b8504b8c440cab6f1ac5e38ecdaf287128bffbb9702a`
- linux/amd64 manifest: `sha256:134b7eeccba5940b07c72e5116c9ab1626d079ed961ffce7884a568c9ee11e73`
- linux/arm64 manifest: `sha256:e8dd548dd1a81063aa609efe26d3d34b1dd8d7e035884cf45b462ec1d239c079`
- Additional `unknown/unknown` manifests are Buildx attestation manifests associated with the platform images, not runnable application platforms.
- Active Trivy risk acceptance remains time-bounded through **2026-10-20** and fail-closed for new HIGH/CRITICAL findings, Python HIGH/CRITICAL findings, accepted findings that become fixable, package/version scope changes, or expiry.

`PRODUCTION_IMAGE_DIGEST` and `k8s/kustomization.yaml` pin this same OCI index digest. Production deployment should use the immutable reference above rather than relying on the mutable `latest` tag.

**Historical metadata note:** the digest above belongs to the pre-bootstrap Hotfix 7 final2 image and is retained only as historical evidence. Later bootstrap/CI work changed source content and therefore required new production images and new OCI digests.

## Bootstrap export and protected-main release flow — consolidated 2026-09-20

The anonymized default-tenant bootstrap export is now part of the cumulative **0.9.0-1** source. It exports the reusable setup of tenant `default` while excluding operational/private data: incidents, actions, operational documents/attachments, people, external recipients, audit records, MFA material, AI knowledge-base content, backup jobs and non-bootstrap users are not exported. The archive keeps workflow/taxonomy configuration, notification configuration, sanitized technical settings and only the PDF templates required by the retained workflows/templates. Secrets are removed; SSO profiles retain non-secret structure but are disabled; the bootstrap admin is exported without a password hash and receives a fresh password from `ADMIN_INITIAL_PASSWORD` on the destination during Full Import.

Development RC1-RC11 hardened both this feature and the release pipeline. The cumulative RC series fixed bootstrap anonymization, GitHub-runner storage isolation, real-PostgreSQL crash tests, Trivy/SBOM false positives, OCI manifest verification, protected-branch digest recording, metadata-only rebuild suppression and Dependabot action updates. RC11 incorporates `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7` and the reviewed `aquasecurity/setup-trivy@81e514348e19b6112ce2a7e3ecbafe19c1e1f567` pin while keeping the Trivy scanner itself at `v0.74.0`.

`main` is protected: production digest bookkeeping is never pushed directly to it. After a production-impacting merge, CI builds the temporary candidate, runs the complete gates, promotes the approved OCI index, re-inspects and verifies the published manifest, writes the immutable digest into `PRODUCTION_IMAGE_DIGEST` and `k8s/kustomization.yaml` on an `automation/production-digest-*` branch, and opens the `chore: record promoted production OCI digest` pull request. CI explicitly dispatches checks for that metadata PR. When that PR is merged, metadata-only change detection skips the Docker build/scan/promotion job, preventing a digest loop. Git-tag releases remain non-mutating with respect to `main` production metadata.

The active Debian risk acceptance contains **47 explicitly reviewed CVEs** and expires on **2026-10-20**. The policy remains fail-closed: new HIGH/CRITICAL findings, every Python HIGH/CRITICAL finding, accepted findings with a reported `FixedVersion`, package/version mismatches, malformed scan input or expired acceptance block promotion.

### Final source-package state

This consolidated source archive intentionally carries `PRODUCTION_IMAGE_DIGEST=PENDING_HOTFIX_REBUILD` and the non-publishable Kustomize pending marker. The consolidation itself changes files included in the Docker build context, so reusing a digest from RC11 or an earlier `chore` would be incorrect. The authoritative final production digest is the digest written by the **next successful post-merge `chore: record promoted production OCI digest` PR** after this final source consolidation passes the complete production pipeline.


---

## RC12 import/bootstrap compatibility correction - 2026-10-01

This cumulative **0.9.0-1** maintenance candidate corrects first-install and Full Import behavior seen with Docker/Podman Compose.

- Fresh PostgreSQL databases no longer receive a query against `setting` before the application schema exists. Full Import crash recovery still runs before bootstrap, but first checks whether the table exists.
- Full Import and anonymized Bootstrap Import now support managed persistent directories that are independent container mountpoints. CIR never attempts to rename the mount root; staging, backup, promotion and rollback are performed inside that mounted filesystem.
- Recovery remains fail-safe if the process is interrupted part-way through moving old mountpoint contents: journal state distinguishes a partial old-data backup from a completed backup before deciding whether live entries may be discarded.
- Existing non-mountpoint behavior remains unchanged.

Because RC12 changes application source, any previously recorded OCI digest is historical for this candidate. The production pipeline must build, test, scan and promote a new multi-architecture image, then record the resulting immutable digest through the protected-main metadata PR flow.


## RC14 security review - 2026-10-01

The production Trivy gate detected three new Debian Trixie HIGH CVEs: `CVE-2026-93990` in `libexpat1`, `CVE-2026-88806` in `libx11-6`/`libx11-data`, and `CVE-2026-88807` in `libxrender1`. The reviewed Trixie package versions currently have no reported FixedVersion in the production scan. RC14 extends the temporary acceptance only to those exact binary packages and reviewed installed-version families. Any reported `FixedVersion`, package/version mismatch, new HIGH/CRITICAL finding, Python HIGH/CRITICAL finding, malformed report, or policy expiry remains blocking. The global and per-CVE review deadline remains **2026-10-20**. Trivy itself remains pinned to `v0.74.0`.


## RC15 Python dependency security update - 2026-10-01

The live `pip-audit` SCA gate detected eight known vulnerabilities in `pypdf==6.16.2`: `CVE-2026-102993`, `CVE-2026-102994`, `CVE-2026-102995`, `CVE-2026-102996`, `CVE-2026-102997`, `CVE-2026-102998`, `CVE-2026-102999`, and `CVE-2026-103000`. The highest minimum fix version across the set is `6.19.0`, so RC15 pins `pypdf==6.19.0`. No Python vulnerability acceptance is added. The SCA helper now prints a concise package/CVE/fix summary when `pip-audit` returns non-zero, while retaining the JSON report.


### 0.10.0-1 RC2: guida didattica e installazione multiarchitettura

Aggiunti il PDF di laboratorio guidato in sei fasi con cattura UI reale attestata da CI, la documentazione di installazione/bootstrap Docker, Podman, Kubernetes e OpenShift con diagramma originale e audit delle immagini incorporate nella presentazione. In sorgente il PDF dichiara esplicitamente che le catture reali sono in attesa della CI. Nessuna modifica DDL; procedura di upgrade dalla 0.9.0-1 invariata. La promozione resta soggetta ai gate production e alla revisione della risk acceptance scaduta.


### RC2 - audit brochure e media didattici

Le brochure bilingui impiegano esclusivamente la scena sintetica già distribuita con CIR, ritagliata per le pagine editoriali. Il processo di controllo verifica le immagini effettivamente incorporate nelle pagine PDF; il PowerPoint è verificato con SHA-256 degli asset locali autorizzati e delle schermate reali validate dalla CI. Non sono utilizzate immagini stock o persone. I loghi di Docker, Podman, Kubernetes, Helm, OpenShift e PostgreSQL sono marchi dei rispettivi titolari, non dichiarati privi di diritti o certificazioni.
