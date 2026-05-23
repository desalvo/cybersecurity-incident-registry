# Test manuali di compliance AGID

Questa directory contiene gli strumenti per eseguire manualmente la suite di conformità AGID.

## Modalità completa con Docker, inclusa `pip-audit`

Questa è la modalità da usare per produrre evidenza completa su un sistema connesso a Internet.
Richiede:

- Docker o Podman compatibile con `docker` CLI;
- accesso Internet verso PyPI e il servizio vulnerabilità usato da `pip-audit`;
- esecuzione dalla radice del progetto estratto.

Comando consigliato:

```bash
./compliance/agid/run_docker_agid_compliance.sh
```

Lo script:

1. elimina le vecchie directory `compliance/agid/<RUN_ID>/` mantenendo solo l'ultima evidenza;
2. costruisce l'immagine dal file `compliance/agid/Dockerfile`;
3. esegue `pip check`, `compileall`, `pytest`, i test dinamici AGID, Bandit e `pip-audit`;
4. salva i risultati nella directory corrente del pacchetto, sotto `compliance/agid/<RUN_ID>/`.

Per impostare un identificativo run esplicito:

```bash
AGID_RUN_ID=manual-$(date -u +%Y%m%dT%H%M%SZ) ./compliance/agid/run_docker_agid_compliance.sh
```

Il run è conforme solo se `SUMMARY.md` riporta esito complessivo `PASS` e `status.tsv` contiene esito `0` per tutti i controlli bloccanti, incluso `pip_audit_json`.

## Modalità locale senza `pip-audit`

Per controlli rapidi offline o in CI non connessa è possibile usare:

```bash
./scripts/run_agid_compliance.sh
```

Questa modalità non esegue `pip-audit`: il controllo vulnerabilità delle dipendenze è limitato alla modalità manuale Docker per evitare falsi esiti dovuti a runner senza Internet.

## File prodotti

Ogni run crea una directory `compliance/agid/<RUN_ID>/` con:

- `SUMMARY.md`: report sintetico leggibile;
- `summary.json`: riepilogo macchina;
- `status.tsv`: codici di ritorno dei singoli controlli;
- `pytest_all.log`: test applicativi;
- `pytest_agid_dynamic.log`: test dinamici AGID;
- `bandit.json` e `bandit_threshold.log`: SAST e soglia HIGH/MEDIUM;
- `pip-audit.json` e `pip_audit_json.log`: solo nella modalità Docker completa;
- altri log tecnici dei controlli.

## Interpretazione

- `pytest`, test dinamici AGID, compilazione, `pip check` e Bandit HIGH/MEDIUM devono passare.
- Nella modalità Docker completa, anche `pip-audit` deve passare.
- In caso di vulnerabilità segnalate da `pip-audit`, aggiornare o mitigare le dipendenze e rieseguire il container.
- In caso di errori di rete, rieseguire su un sistema con connettività effettiva: l'errore di rete non costituisce evidenza di compliance totale.

### Nota Bandit

Il report JSON di Bandit viene generato con `--exit-zero`: la presenza di finding LOW non interrompe la generazione del report. La soglia bloccante AGID è applicata subito dopo con `scripts/check_bandit_threshold.py`, che fallisce il run solo in presenza di finding HIGH o MEDIUM. Questo evita falsi FAIL quando Bandit restituisce codice non zero per soli finding LOW.


Il runner standard registra `pip_audit_manual_docker_only` come passo informativo PASS: il controllo vulnerabilità tramite `pip-audit` viene eseguito solo dal runner Docker manuale completo.

### Output a video della suite AGID

Al termine dell’esecuzione degli script di compliance viene sempre stampato a video un riepilogo sintetico con:

- directory dei risultati;
- esito globale PASS/FAIL;
- esito dei singoli controlli (`pip_check`, `compileall`, `pytest`, test dinamici AGID, Bandit e, nella modalità Docker manuale, `pip-audit`);
- conteggio Bandit per severità;
- percorso dei report `SUMMARY.md` e `summary.json`.

Gli stessi dati sono salvati nella directory del run AGID, insieme ai log completi.

## Correzione ambiente Python del container

Il Dockerfile della compliance crea un virtual environment dedicato in `/opt/agid-venv` e installa esplicitamente:

- `bandit==1.7.10`;
- `pip-audit>=2.7,<3`.

Il runner containerizzato esegue sempre i comandi tramite `/opt/agid-venv/bin/python`, quindi i controlli:

```bash
python -m bandit
python -m pip_audit
```

non dipendono dal Python di sistema né da eventuali ambienti virtuali montati dal progetto.

Per evitare immagini Docker cache obsolete, lo script usa di default `docker build --pull`. Se serve forzare una ricostruzione completa:

```bash
AGID_DOCKER_BUILD_FLAGS="--pull --no-cache" ./compliance/agid/run_docker_agid_compliance.sh
```

Nel report vengono prodotti anche i passi `bandit_module_check` e `pip_audit_module_check`, utili a verificare immediatamente che i moduli siano disponibili nel container prima dei test effettivi.
