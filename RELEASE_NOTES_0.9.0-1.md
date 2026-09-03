# Note di rilascio - Cybersecurity Incident Registry 0.9.0-1

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

I file `SECURITY_AUDIT_ROUND2.md` ... `SECURITY_AUDIT_ROUND18.md` conservano la traccia tecnica delle singole fasi di audit. Devono essere letti come cronologia interna della costruzione della **0.9.0-1 a partire dalla 0.8.0**, non come elenco di release separate.

### Immagine Docker multi-arch

La release include `scripts/build_multiarch_image.sh`, che costruisce e pubblica per default `desalvo/cybersecurity-incident-registry:latest` come manifest multi-arch per `linux/amd64` e `linux/arm64` tramite Docker Buildx. Repository e tag sono configurabili separatamente con `--repository`/`--tag` o `CIR_DOCKER_REPOSITORY`/`CIR_DOCKER_TAG`; `--image`/`CIR_DOCKER_IMAGE` resta disponibile per impostare il riferimento completo. Prima dell'esecuzione è necessario autenticarsi al registry con `docker login`.

La migrazione operativa dalla baseline 0.8.0 è documentata in `MIGRATION_0.8.0_TO_0.9.0.md`, con le modifiche richieste a Docker Compose, Compose production, Kubernetes/Kustomize, Secret, PVC e variabili di sicurezza.
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
