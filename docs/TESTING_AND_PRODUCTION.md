# Testing, CI and production promotion

## RC104 correction verification (27 November 2026)

The RC103 PR run `45914128899` failed with 32 pytest failures and a failing
real-UI documentation capture. Root causes and fixes are recorded in
`docs/RELEASE.md`, section RC104. Local checks use Python 3.13 and the offline
wheel bundle from the project library; successful checks include Flask request
regressions for AlBot authoring, superadmin Tenants Default access and modern UI,
CSP/template parsing and bilingual PptxGenJS source tests. The full CI matrix,
real PostgreSQL suite, Chromium UI evidence, SCA and Docker/Trivy gates must be
rerun on GitHub; local successes do not certify the release. The preexisting
production-image digest and risk-acceptance rules are unchanged.

## 0.10.0-1 / RC1: metadati e verifiche della nuova linea

`VERSION` identifica la release funzionale 0.10.0-1. Il job iniziale di CI calcola
una sola build `YYYYMMDD` nel fuso `Europe/Rome` con
`scripts/prepare_release_metadata.py`, quindi ogni job la applica tramite
`--build "$CIR_RELEASE_BUILD" --write`. Test, prove UI, receipt dei manuali ed
etichette OCI devono riferirsi agli stessi file VERSION/BUILD. La rigenerazione
deve avvenire prima delle verifiche; non si trasferiscono prove di una build diversa.

Il packaging scrive la build nella directory di staging senza modificare il
checkout. Docker genera automaticamente la data, ma rifiuta screenshot e manuali
installati con metadati diversi. Per ricostruire lo stesso candidato conservando
le sue prove già validate, passare `--build-arg CIR_RELEASE_BUILD="$(cat BUILD)"`;
per una nuova build, lasciare che la CI rigeneri catture e PDF con il valore unico
dell'esecuzione.

Le prove screenshot registrano versione, build, commit e checksum. I documenti
che non hanno ancora screenshot validati sono esplicitamente provvisori: i mock
storici non possono essere promossi ad evidenza della UI. I gate continuano a
richiedere pytest completo, PostgreSQL reale, SCA e scan Trivy amd64/arm64.
La scadenza della disposition Debian (2026-10-20) non viene prorogata.

Con le copertine documentali approvate, il contratto corrente comprende **17
viewport reali**: alle 13 catture della baseline si aggiungono le aperture delle
guide utente e amministratore, entrambe su desktop e mobile. La copertina
fotografica nativa è un elemento editoriale; i render delle prime pagine dei PDF
restano distinti dalle catture browser dell'applicazione. La galleria conserva
una pagina per ogni viewport verificato, oltre alla copertina comune.

Il tag Git della nuova release sarà `0.10.0-1` solo quando il commit da rilasciare
sarà approvato e verificato; il precedente tag `0.9.0-1` resta invariato.
Il repository conserva `PENDING_HOTFIX_REBUILD` fino alla promozione del nuovo
digest. I controlli realmente eseguiti per questo cumulativo sono nel report di
verifica e in [HANDOFF.md](HANDOFF.md). Le sezioni RC20/RC18/RC17 seguenti
riportano risultati storici e non costituiscono nuovi PASS della 0.10.0-1.


### Bundle documentale corrente e nuovi controlli

La sequenza obbligatoria è: catturare 17 viste dell'applicazione reale con fixture
isolate; generare i quattro manuali IT/EN, Alfresco, due brochure e la galleria;
generare il PowerPoint da screenshot verificati e prime pagine PDF; finalizzare
la ricevuta aggregata; validare l'intero batch prima di installarlo nell'immagine.
La ricevuta include 8 PDF, PPTX, 5 preview dei manuali e ricevuta della presentazione.
Le verifiche leggono i media e i testi realmente incorporati nel PPTX; un campo
`real_screenshots: true` privo delle prove corrispondenti non supera il gate.
Commit, VERSION e BUILD devono essere identici per tutte le fasi dello stesso run.

Le nuove regressioni coprono copertine e navigazione autenticata IT/EN,
compatibilità UI classica, PDF runtime con identità About, sessione/MFA, elenco
chiuso delle guide, escaping Markdown, link e file locali delle piattaforme.
I renderer sono verificati con input lunghi e metadati di build alternativi.
I test dei validatori usano fixture artificiali dichiarate: non sono acquisizioni
browser né prove PostgreSQL. Le verifiche visuali finali dell'app sono nel job CI.

La review periodica è separata dalla pipeline di rilascio: `.github/workflows/security-review.yml`
(lunedì 06:15 UTC, o workflow_dispatch da main) controlla dipendenze e digest
production su entrambe le architetture. PENDING o risk acceptance scaduta falliscono
esplicitamente; nessun aggiornamento automatico delle eccezioni o promozione.

## RC20: screenshot reali e documentazione come gate

La nuova UI è abilitata per default, con ritorno globale alla modalità classica.
I test HTTP aggiunti coprono impostazione condivisa, ruoli, CSRF, persistenza,
login, menu, lista, blocchi incidenti e confini del pannello AI. I test storici
restano validi per la modalità classica; i nuovi verificano quella moderna.

Il job obbligatorio **Real UI screenshots and documentation** esegue l'applicazione
reale con SQLite/storage temporanei e dati esclusivamente sintetici. Playwright
usa il Chromium abbinato alla versione fissata in `requirements-ui.txt`. Login,
CSRF, impostazioni, cambio tenant e chat attraversano i veri endpoint Flask.
La risposta AI dimostrativa proviene da un server HTTP locale compatibile con il
provider di test; non viene sostituita nel browser e non chiama servizi esterni.

La cattura comprende login, registro, menu mobile, incidente, AlBot, impostazioni
UI, confronto classico, moduli e SSO: **13 viewport**. Falliscono errori JavaScript,
asset mancanti, richieste esterne inattese o controlli operativi non superati.
`manifest.json` contiene commit, versione/build, browser, dati fittizi dichiarati,
risultati dei controlli e checksum delle immagini. Nessun mock viene accettato
come screenshot dell'applicazione.

Riproduzione su un ambiente con dipendenze e Chromium disponibili:

```bash
python -m pip install -r requirements-dev.txt -r requirements-ui.txt
python -m playwright install --with-deps chromium
python scripts/capture_ui_screenshots.py --output /tmp/cir-ui-evidence --source-commit "$(git rev-parse HEAD)"
python scripts/build_documentation_pdfs.py --screenshot-manifest /tmp/cir-ui-evidence/manifest.json --output-dir /tmp/cir-ui-evidence/documentation --require-real-screenshots --source-commit "$(git rev-parse HEAD)"
python scripts/install_ui_documentation.py --manifest /tmp/cir-ui-evidence/manifest.json --documentation-dir /tmp/cir-ui-evidence/documentation --source-commit "$(git rev-parse HEAD)"
```

La cattura richiede un checkout pulito del commit dichiarato. L'installer valida
l'intero lotto prima di scrivere, installa i PNG sotto `app/static/help/ui-runtime`
e conserva manifest originale e ricevuta sotto `docs/`. I quattro manuali PDF e
la galleria sono legati a quelle immagini. Nel sorgente preparato senza browser,
le guide indicano l'assenza delle figure reali: il generatore senza manifest non
le sostituisce con immagini dimostrative.

Su ogni PR e push il job carica `ui-documentation-<sha>` con screenshot, PDF e
sorgente cumulativo. Il job Docker dipende sia da questo job sia da
**Tests, PostgreSQL, SCA and offline gates**; scarica l'artefatto della stessa
esecuzione, verifica digest e commit e lo installa prima del build candidate.
Qualsiasi failure impedisce build/promozione. Per main protetto aggiungere
**Real UI screenshots and documentation** ai required status checks, mantenendo
quelli esistenti. Le PR e i merge dei soli metadati del digest eseguono comunque
le verifiche e continuano a evitare build Docker ricorsivi.

Verifiche locali di RC20: i test unittest del pipeline e delle prove documentali,
i controlli JavaScript con DOM minimo, i contratti indipendenti dalle dipendenze,
la sintassi, i verificatori offline e il packaging sono registrati nel report.
In aggiunta, un ambiente isolato Python **3.13.5** creato con wheel già disponibili
ha eseguito Flask/SQLAlchemy/SQLite reali: **7** casi di upgrade/import da modelli
RC16, **3** regressioni di migrazione legacy, **12** casi transazionali dell'adapter
SQLAlchemy e **21** controlli HTTP con sessioni, CSRF e switch globale. I **21**
test del nucleo di migrazione usano anche transazioni SQLite reali senza Flask.

Questi esiti sono prove di compatibilità, **non pytest completo con i pin CI**.
L'ambiente contiene, fra gli altri, SQLAlchemy 2.0.52, pypdf 6.10.2 e
cryptography 46.0.7; non è un ambiente production approvato e non modifica i
requisiti del progetto. L'installazione dei pin esatti per Python 3.12 resta
indisponibile. I test PostgreSQL sono aggiunti al marker `postgres`, ma non sono
stati eseguiti localmente. Browser, SCA, Trivy e rendering Helm restano da
eseguire in CI; nessun risultato JavaScript con DOM minimo equivale a Chromium.

### Contratto CI delle migrazioni automatiche

`tests/fixtures/rc16_schema/models.py` conserva i modelli storici autentici con
provenienza e checksum. La regressione crea quel database prima di avviare il
codice nuovo: non simula un upgrade avviando una base già aggiornata. Verifica
incidente, password, configurazioni, file, inizializzazione unica di Tenants
Default, riavvio, errore prima del commit finale, retry e import completo.
Le prove PostgreSQL usano schemi di test isolati sul servizio reale della CI.

Ogni release con modifiche di schema deve appendere una revisione in
`app/migration_manager.py` e il callback corrispondente in `app/__init__.py`,
senza riscrivere le revisioni pubblicate, e aggiungere una fixture/test di
upgrade dalla precedente baseline supportata. Il test deve controllare che
il secondo avvio non ripeta la migrazione, che gli errori non registrino un
successo e che password/configurazioni/documenti persistenti sopravvivano.
La compatibilità schema futuro/rollback è fail-closed; rollback del container
e rollback del database sono operazioni distinte. Vedere [MIGRATION.md](MIGRATION.md).

La risk acceptance è scaduta il 2026-10-20, non prorogata; la promozione production
resta bloccata fino a una revisione valida e al superamento di tutti i gate.
Nessun nuovo digest viene impostato nel sorgente preparato.

## RC18: stato delle verifiche al 22 novembre 2026

La RC18 mantiene VERSION 0.9.0-1 e BUILD 20260902. Il dettaglio riprendibile e
la baseline esatta sono in [HANDOFF.md](HANDOFF.md); il report finale separato
`cir-0.9.0-1-rc18-verification.json` registra comandi, limiti e checksum.

Sono stati aggiunti test per seed idempotente, mapping UUID dopo collisione,
import ripetuti e personalizzazione, obsolescenza propagata con avvisi per tutti
gli amministratori, protezione delle cancellazioni, dati legacy NULL,
portabilità fra istanze e restore Full/Bootstrap/Scoped. I test HTTP coprono
creazione, clonazione, riassegnazione e modifica di incidenti con workflow obsoleti.
La regressione ID esatta è
`test_defaults_workflow_uses_exact_replica_ids_after_numeric_and_name_collisions`
in `tests/test_workflow_lifecycle.py`.

La CI richiede inoltre rendering reale Helm 3.14+ nella major 3, schema dei valori,
Template OpenShift, packaging degli installer e verifica del materiale didattico.
`python scripts/check_installation_package.py --require-helm` non degrada a un
controllo statico se Helm manca. I test dei documenti confrontano slide e note con
il sorgente e richiedono guide e PPTX nel package.

Nell'ambiente di preparazione mancano pytest/Flask/SQLAlchemy/PostgreSQL, Helm e
un runtime container; i tentativi di download sono bloccati da HTTP 403.
**Non è stato dichiarato il PASS della suite applicativa o dei gate production.**
Le invocazioni dirette di funzioni autonome (224 PASS, 3 BLOCKED), i test unittest
SQLite (5 PASS), installer (24 PASS, 1 SKIP Helm) e documenti (5 PASS), oltre ai
validatori puri, sono evidenze limitate e distinte dalla suite pytest.

Non sono stati costruiti o promossi container. `PRODUCTION_IMAGE_DIGEST` resta
`PENDING_HOTFIX_REBUILD`; la risk acceptance del 2026-10-20 è scaduta e deve
continuare a bloccare il gate reale. Le sezioni successive conservano procedure
ed evidenze storiche, non un'approvazione della RC18.

Testing and production evidence requirements for 0.10.0-1, including GitHub Actions, real PostgreSQL tests, SCA, multi-architecture builds, Trivy gates, immutable digest promotion and Docker Hub secrets.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `GITHUB_ACTIONS_RELEASE.md`

---

## Historical source: `GITHUB_ACTIONS_RELEASE.md`

La workflow `.github/workflows/ci-release.yml` automatizza la validazione e la pubblicazione della release CIR.

## Trigger

- Pull request: esegue tutti i gate applicativi, PostgreSQL, SCA e packaging, ma non pubblica immagini.
- Push su `main`: dopo tutti i gate costruisce e pubblica l'immagine multi-arch e, solo dopo il PASS Trivy, promuove il digest a `latest`.
- Push di un tag Git: dopo tutti i gate promuove il digest allo stesso tag, ad esempio il tag Git `0.10.0-1` produce `desalvo/cybersecurity-incident-registry:0.10.0-1`.

Il tag Git deve essere anche un tag Docker valido (`[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}`).

## Docker Hub secrets e variabili

Configurare in GitHub `Settings -> Secrets and variables -> Actions`:

- secret `DOCKERHUB_USERNAME`: username Docker Hub con permesso push;
- secret `DOCKERHUB_TOKEN`: access token Docker Hub, non la password dell'account;
- variable opzionale `CIR_DOCKER_REPOSITORY`: repository destinazione. Se assente usa `desalvo/cybersecurity-incident-registry`.

## Gate eseguiti

1. installazione delle dipendenze di test e `pip-audit`;
2. `python -m pip check`;
3. `python -m pytest -q`;
4. `./scripts/run_postgres_tests.sh` con PostgreSQL reale in Docker Compose;
5. `python scripts/verify_release_candidate.py`;
6. `python scripts/verify_security_gate_context.py`;
7. `./scripts/run_sca.sh`;
8. packaging smoke test con `scripts/package_release.sh`;
9. build multi-arch `linux/amd64,linux/arm64` con base image aggiornata e senza cache;
10. Trivy production gate CIR sul digest candidato esatto;
11. promozione dello stesso digest al tag finale solo dopo PASS.

I report SCA e Trivy vengono conservati come artifact GitHub Actions per 30 giorni.

## Strategia di pubblicazione fail-closed

La build viene prima pubblicata con un tag temporaneo `ci-<commit-sha>`. Il gate Trivy scansiona l'esatto digest OCI prodotto. Solo se entrambe le piattaforme superano la policy viene creato il tag finale (`latest` o il tag Git) sul medesimo digest. Un candidato che fallisce non modifica quindi il tag production.

I tag `ci-*` sono evidenza tecnica e possono essere rimossi dal registry in base alla retention policy scelta per Docker Hub.

## Risk acceptance temporanea Debian

La workflow usa `TRIVY_RISK_ACCEPTANCE_R8.json`. L'allowlist resta fail-closed: Python HIGH/CRITICAL, nuovi CVE OS, CVE fuori dallo scope di package approvato, CVE con `FixedVersion` disponibile o acceptance scaduta bloccano la promozione.

La disposition aggiunta il 20 settembre 2026 per i CVE util-linux/systemd scade il 20 ottobre 2026 e dipende dall'hardening runtime verificato da `scripts/verify_security_gate_context.py`.

---

## Automatic production-digest recording

For a production-impacting push to `main`, the workflow promotes the approved candidate to `latest`, re-inspects the registry and verifies that all immutable OCI child descriptors (amd64, arm64 and attestations) match the candidate that passed the Trivy gate. The published top-level OCI index digest is then written by `scripts/record_production_digest.py` into `PRODUCTION_IMAGE_DIGEST` and `k8s/kustomization.yaml`.

The workflow does **not** push that metadata directly to protected `main`. Instead it creates a dedicated branch named `automation/production-digest-<digest-prefix>` and opens a pull request titled `chore: record promoted production OCI digest`. This keeps the repository ruleset intact: every update to `main`, including production digest bookkeeping, can pass through the configured pull-request and status-check policy. The job uses the standard `GITHUB_TOKEN` with job-scoped `contents: write`, `pull-requests: write` and `actions: write`; no personal access token is required.

Because branches and pull requests created with `GITHUB_TOKEN` do not recursively start the workflow, CI explicitly dispatches `ci-release.yml` on the metadata branch after opening the pull request. That dispatched run executes the quality gates on the exact metadata commit but cannot enter the Docker release job, which remains restricted to `push` events. Repository/organization Actions settings must therefore allow GitHub Actions to create pull requests and to dispatch workflows.

A push to `main` that changes only `PRODUCTION_IMAGE_DIGEST` and `k8s/kustomization.yaml` is detected as metadata-only. Quality gates may still run, but the Docker build/scan/promotion job is skipped, preventing the digest-recording PR merge from rebuilding the image and generating a new digest. Any additional changed path makes the update production-impacting and restores the full fail-closed Docker pipeline.

Tag-triggered releases never create or update the production digest PR for `main`; they publish and report their own immutable tag digest only. If branch creation or PR creation is forbidden by repository/organization policy, the workflow fails after promotion instead of claiming that repository metadata was synchronized.
# Evidenze storiche RC17 Tenants Default

Il candidato del **2026-11-22** mantiene versione funzionale **0.9.0-1** e build
**20260902**. Consultare [HANDOFF.md](HANDOFF.md) per le evidenze e i controlli
ancora da eseguire. Il package deve includere quel file; il verificatore offline
e lo script di packaging ne richiedono la presenza.

La copertura aggiunta riguarda propagazione, collisioni e cancellazioni in uso,
rollback, ereditarietà dei parametri, accessi cross-tenant, MFA/CSRF, importazioni
ripetute del catalogo, documenti indipendenti, formati ostili, asset, reimport di
bundle e cifratura con chiavi diverse. La suite PostgreSQL include nuove prove
reali su migrazione dei destinatari, propagazione/rollback e copie del catalogo.

L'ambiente di preparazione dispone di Python 3.12.14, ma non delle dipendenze
Flask/SQLAlchemy/pytest/PostgreSQL; il tentativo di installazione ha restituito
HTTP 403. Docker e Podman non sono disponibili. I controlli statici e le funzioni
pure eseguite separatamente non sostituiscono quindi i seguenti gate CI:

```bash
python -m pip install -r requirements-dev.txt pip-audit
python -m pip check
python -m pytest -q
./scripts/run_postgres_tests.sh
python scripts/verify_release_candidate.py
python scripts/verify_security_gate_context.py
./scripts/run_sca.sh
./scripts/package_release.sh /tmp/cir-rc17-package.zip
```

Usare le variabili di directory isolate già presenti nel workflow GitHub Actions;
non creare `/data` con privilegi di root per far passare i test. I file shell devono
conservare i bit eseguibili anche nell'indice Git. Se il checkout locale li ha persi:

```bash
git update-index --chmod=+x docker-entrypoint.sh scripts/*.sh
```

I test della disposition storica isolano soltanto il proprio clock al 2026-10-01.
Un test distinto esegue il CLI reale e verifica la scadenza effettiva. La policy
di produzione resta scaduta dal 2026-10-20 e deve bloccare il gate live finché non
viene effettuata una nuova valutazione. Questa RC non aggiorna dipendenze, SBOM o
acceptance per simulare l'esito di una scansione non eseguita.


## RC57: Full Import legacy e categorie Tenants Default

In caso di Full Import da un export storico senza `Tenants Default`, l'import
ricrea nella stessa transazione il tenant condiviso dal `default` operativo.
Le categorie già presenti nei tenant non vengono duplicate: la provenienza
condivisa viene rimappata agli ID esistenti e i campi personalizzati rimangono
locali. La ripetizione dell'avvio/sync non ripubblica nuove etichette omonime.
In presenza di vecchi duplicati già associati a incidenti o workflow CIR
conserva il record per non alterare lo storico ed emette un avviso; un
consolidamento amministrativo di quei riferimenti richiede una procedura
controllata e un backup. Verificare prima del rollout su copia del database
con casi pre-tenant, replica coincidente, override locale e workflow storico.
