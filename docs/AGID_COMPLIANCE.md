# Conformità AGID per lo sviluppo sicuro

Questa documentazione descrive la suite riproducibile inclusa nel pacchetto per verificare i controlli applicativi collegati alle *Linee guida per lo sviluppo sicuro* AGID.

## Ambito dei controlli

La suite copre i controlli tecnici principali applicabili al progetto Flask:

- configurazione sicura di produzione e assenza di segreti deboli;
- disabilitazione HTTP TRACE/TRACK;
- protezione CSRF server-side;
- header HTTP di sicurezza e cookie `HttpOnly`/`SameSite`/`Secure` in produzione;
- autenticazione con messaggi non enumerativi e lockout server-side;
- controllo accessi sulle aree amministrative;
- escaping dell'output utente per mitigare XSS;
- validazione upload centralizzata, incluso il plugin AI Chatbot;
- mitigazione SSRF sugli endpoint AI configurabili;
- controlli statici Bandit con soglia bloccante per finding HIGH/MEDIUM;
- regressione packaging container per garantire che `docker-entrypoint.sh` sia eseguibile nell’immagine Docker;
- controllo dipendenze con `pip check` e `pip-audit` quando la rete consente l'accesso al database vulnerabilità.

## File inclusi

- `tests/test_agid_compliance_dynamic.py`: test dinamici Flask con database SQLite temporaneo.
- `tests/test_security_smoke.py`: smoke test di sicurezza e configurazione.
- `tests/test_container_packaging.py`: test di regressione sui permessi dell’entrypoint Docker e sul Dockerfile.
- `scripts/run_agid_compliance.sh`: entry point unico per eseguire tutti i controlli.
- `scripts/check_bandit_threshold.py`: verifica che Bandit non riporti finding HIGH o MEDIUM.
- `scripts/summarize_agid_results.py`: genera `summary.json` e `SUMMARY.md` con l'esito del run.
- `compliance/agid/<RUN_ID>/`: directory delle evidenze prodotte dai run.

## Esecuzione

Da root repository:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
./scripts/run_agid_compliance.sh
```

Per fissare un identificativo di run e una directory risultati:

```bash
AGID_RUN_ID=manual-$(date -u +%Y%m%dT%H%M%SZ) ./scripts/run_agid_compliance.sh
```

Esecuzione in ambiente senza rete, mantenendo evidenza della limitazione:

```bash
AGID_SKIP_PIP_AUDIT=1 AGID_RUN_ID=offline-$(date -u +%Y%m%dT%H%M%SZ) ./scripts/run_agid_compliance.sh
```

Il comando termina con codice `0` se i controlli bloccanti passano. Sono bloccanti:

- `pip check`;
- compilazione Python di `app` e `tests`;
- tutta la suite `pytest`;
- test dinamici AGID;
- soglia Bandit: `0 HIGH` e `0 MEDIUM`.

`pip-audit` è eseguito e salvato tra le evidenze. In ambienti senza DNS/accesso Internet può fallire o andare in timeout: il fallimento viene registrato come limitazione ambientale in `pip-audit-note.txt` e deve essere rieseguito in CI con rete prima del rilascio in produzione. Il timeout è configurabile con `AGID_PIP_AUDIT_TIMEOUT` e, solo per ambienti offline, è possibile registrare lo skip controllato con `AGID_SKIP_PIP_AUDIT=1`.

## Risultati prodotti

Ogni run crea una directory:

```text
compliance/agid/<RUN_ID>/
```

con:

- `status.tsv`: return code dei passi eseguiti;
- `*.log`: log completi;
- `bandit.json`: risultato Bandit machine-readable;
- `pip-audit.json`, se disponibile;
- `summary.json`: sintesi strutturata;
- `SUMMARY.md`: sintesi leggibile.

Questi file devono essere conservati nel pacchetto di rilascio come evidenza di conformità.

## Aggiornamenti futuri

Ogni modifica funzionale o correttiva del progetto deve includere:

1. aggiornamento dei test AGID se il perimetro cambia;
2. esecuzione di `./scripts/run_agid_compliance.sh`;
3. salvataggio nel pacchetto della nuova directory `compliance/agid/<RUN_ID>/`;
4. aggiornamento della documentazione e del changelog con l'esito dei controlli.

## Limiti della suite

La suite non sostituisce penetration test infrastrutturali, DAST su deployment reale, verifica TLS/reverse proxy, hardening database, scansione container e audit organizzativo. Questi controlli devono essere eseguiti nell'ambiente di rilascio o nella pipeline CI/CD dell'ente.

### Controllo Markdown e notifiche schedulate

La suite include test dedicati per verificare che il Markdown esteso consenta solo valori controllati di colore e dimensione e che le notifiche schedulate vengano convertite in testo semplice prima dell’invio. Questo riduce il rischio XSS sul rendering e impedisce l’invio di marker di formattazione Markdown nei messaggi automatici.

## Esecuzione in CI con rete e `pip-audit` bloccante

La suite AGID esegue `pip-audit` in modalità bloccante per impostazione predefinita (`AGID_PIP_AUDIT_STRICT=1`). In una pipeline con accesso a Internet il comando da usare è:

```bash
AGID_PIP_AUDIT_STRICT=1 AGID_PIP_AUDIT_TIMEOUT=300 ./scripts/run_agid_compliance.sh
```

Il workflow GitHub Actions `.github/workflows/agid-compliance.yml` installa le dipendenze, esegue la suite completa e pubblica le evidenze come artifact. Un fallimento di `pip-audit` per vulnerabilità rilevate, assenza del tool, timeout o problemi di accesso al database vulnerabilità produce esito non conforme in CI.

## Conservazione delle evidenze

A ogni esecuzione ordinaria `scripts/run_agid_compliance.sh` rimuove le directory precedenti in `compliance/agid/` e conserva solo `compliance/agid/<RUN_ID>/`, così il pacchetto di rilascio contiene esclusivamente l'ultima versione dei risultati. Per confronti locali temporanei è possibile impostare `AGID_KEEP_PREVIOUS_RESULTS=1`, ma tale opzione non deve essere usata per produrre pacchetti di rilascio.

## Resolver DNS locale per `pip-audit`

Per evitare fallimenti di `pip-audit` dovuti a resolver DNS non funzionanti nel runner o nel container, il pacchetto include `scripts/configure_local_dns.sh`. Lo script configura preferibilmente il resolver stub locale di `systemd-resolved` su `127.0.0.53`, imposta upstream espliciti tramite `resolvectl` e verifica la risoluzione di `pypi.org` e `api.osv.dev`.

Esecuzione manuale:

```bash
AGID_DNS_UPSTREAMS="1.1.1.1 8.8.8.8" ./scripts/configure_local_dns.sh
AGID_USE_LOCAL_DNS=1 AGID_PIP_AUDIT_STRICT=1 ./scripts/run_agid_compliance.sh
```

In CI il workflow `.github/workflows/agid-compliance.yml` esegue questa configurazione prima dell'installazione delle dipendenze e la riapplica prima di `pip-audit`. Se il resolver locale non viene configurato correttamente, il job fallisce quando `AGID_LOCAL_DNS_STRICT=1`.

## Ultimo run incluso nel pacchetto

La suite standard esegue pytest tramite `scripts/run_pytest_offline_safe.sh`, che isola ogni modulo di test in un processo dedicato, disabilita l'autoload dei plugin pytest esterni e forza l'uscita deterministica dei processi solo nel runner Docker/offline. Questo evita hang di chiusura dovuti a risorse o plugin del container senza modificare il comportamento produttivo. `pip-audit` è parte del flusso standard e resta bloccante nei run con rete; con `AGID_OFFLINE=1` lo skip viene registrato come limitazione ambientale e deve essere recuperato in CI con rete prima del rilascio.

## Script manuale incluso nella directory compliance

Oltre allo script principale `scripts/run_agid_compliance.sh`, il pacchetto include anche:

- `compliance/agid/run_manual_agid_compliance.sh`
- `compliance/agid/ISTRUZIONI_TEST_MANUALI_AGID.md`

Lo script manuale è pensato per un sistema connesso a Internet: crea un virtual environment dedicato, installa le dipendenze da `requirements-dev.txt`, esegue la suite AGID completa e mantiene nel pacchetto solo l'ultima directory di risultati. Per usarlo:

```bash
./compliance/agid/run_manual_agid_compliance.sh
```

Se il sistema richiede il bootstrap del resolver locale prima di `pip-audit`:

```bash
AGID_USE_LOCAL_DNS=1 ./compliance/agid/run_manual_agid_compliance.sh
```

Le istruzioni operative dettagliate sono nel file `compliance/agid/ISTRUZIONI_TEST_MANUALI_AGID.md`.

## Esecuzione manuale completa con Docker

A partire da questa versione, `pip-audit` è parte della suite standard `scripts/run_agid_compliance.sh` ed è bloccante per impostazione predefinita (`AGID_PIP_AUDIT_STRICT=1`). La modalità Docker resta disponibile per produrre evidenze complete in un ambiente isolato con rete.

Per produrre evidenza completa su un sistema connesso a Internet:

```bash
./compliance/agid/run_docker_agid_compliance.sh
```

Il comando costruisce `compliance/agid/Dockerfile`, esegue tutti i controlli AGID inclusi Bandit e `pip-audit`, e salva i risultati nella directory corrente del pacchetto sotto `compliance/agid/<RUN_ID>/`. Prima del run vengono eliminate le vecchie directory di evidenza, così il pacchetto mantiene solo l'ultimo risultato AGID.

Le istruzioni operative dettagliate sono in `compliance/agid/ISTRUZIONI_TEST_MANUALI_AGID.md`.

### Nota Bandit

Il report JSON di Bandit viene generato con `--exit-zero`: la presenza di finding LOW non interrompe la generazione del report. La soglia bloccante AGID è applicata subito dopo con `scripts/check_bandit_threshold.py`, che fallisce il run solo in presenza di finding HIGH o MEDIUM. Questo evita falsi FAIL quando Bandit restituisce codice non zero per soli finding LOW.


### Output a video della suite AGID

Al termine dell’esecuzione degli script di compliance viene sempre stampato a video un riepilogo sintetico con:

- directory dei risultati;
- esito globale PASS/FAIL;
- esito dei singoli controlli (`pip_check`, `compileall`, `pytest`, test dinamici AGID, Bandit e, nella modalità Docker manuale, `pip-audit`);
- conteggio Bandit per severità;
- percorso dei report `SUMMARY.md` e `summary.json`.

Gli stessi dati sono salvati nella directory del run AGID, insieme ai log completi.

### Runner Docker manuale: Bandit e pip-audit

La modalità manuale Docker usa un virtual environment dedicato (`/opt/agid-venv`) creato durante la build dell'immagine. In tale ambiente vengono installati esplicitamente `bandit` e `pip-audit` e tutti i controlli vengono eseguiti tramite quel Python, evitando errori del tipo `No module named bandit` o `No module named pip_audit` dovuti al Python di sistema.

Per forzare una build pulita del runner:

```bash
AGID_DOCKER_BUILD_FLAGS="--pull --no-cache" ./compliance/agid/run_docker_agid_compliance.sh
```

## Nota dipendenze runtime

La suite di compliance è stata aggiornata per verificare il progetto con `Flask==3.1.3`, `Werkzeug==3.1.6`, `Pillow==12.2.0`, `python-dotenv==1.2.2`, `pypdf==6.10.2`, `requests==2.33.0`, `cryptography==46.0.7` e `pytest==9.0.3`. La modalità Docker manuale resta necessaria per eseguire anche `pip-audit` con accesso Internet.


## Copertura backup AI Chatbot

La suite di regressione include `test_full_backup_includes_ai_chatbot_knowledge_base_files`, che verifica che il full backup/full export includa anche i documenti fisici caricati nella knowledge base dell’AI Chatbot sotto `files/persistent/ai_chatbot_docs/`, oltre ai record database `ai_chatbot_document`.


## Protezione API key AI Chatbot

La configurazione del plugin AI Chatbot applica una gestione overwrite-only delle API key: le chiavi presenti sono mostrate agli amministratori solo in forma offuscata, il valore reale non viene renderizzato nei template HTML e un campo vuoto mantiene il segreto esistente. La sovrascrittura è possibile solo inserendo una nuova API key. Questa scelta riduce il rischio di information disclosure e mantiene la tracciabilità dell'operazione senza registrare segreti nei log.


## Ambiente Python isolato per i controlli

Per evitare falsi fallimenti di `pip check` causati da pacchetti non appartenenti all'applicazione gia' presenti nell'ambiente globale, la suite AGID locale crea e usa per default un virtual environment dedicato `.venv-agid`. E' possibile indicarne uno esistente con `AGID_PYTHON=/percorso/bin/python` oppure forzare l'ambiente corrente con `AGID_USE_CURRENT_ENV=1`. Il pin `pypdf==6.10.2` non viene modificato.
