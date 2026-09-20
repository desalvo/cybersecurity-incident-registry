# Release and Hotfix lifecycle

Release-candidate, production-release and cumulative Hotfix documentation for 0.9.0-1. Hotfixes correct the same functional version and do not create new functional releases.

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

The original R8 acceptance of 30 CVEs through 2026-10-03 is historical evidence for the pre-hotfix image. Hotfix 7 supersedes the active policy with **44 explicitly reviewed CVEs**, including the five findings reviewed on 2026-09-20, and extends the time-bounded review deadline to **2026-10-20**. The new findings are package-scoped; util-linux findings are additionally constrained to the reviewed `2.41.5-0+deb13u1` version family. Any new HIGH/CRITICAL, Python HIGH/CRITICAL, out-of-scope package/version, available `FixedVersion`, or expired acceptance remains blocking.

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

The active Debian risk acceptance contains **44 explicitly reviewed CVEs** and expires on **2026-10-20**. The policy remains fail-closed: new HIGH/CRITICAL findings, every Python HIGH/CRITICAL finding, accepted findings with a reported `FixedVersion`, package/version mismatches, malformed scan input or expired acceptance block promotion.

### Final source-package state

This consolidated source archive intentionally carries `PRODUCTION_IMAGE_DIGEST=PENDING_HOTFIX_REBUILD` and the non-publishable Kustomize pending marker. The consolidation itself changes files included in the Docker build context, so reusing a digest from RC11 or an earlier `chore` would be incorrect. The authoritative final production digest is the digest written by the **next successful post-merge `chore: record promoted production OCI digest` PR** after this final source consolidation passes the complete production pipeline.
