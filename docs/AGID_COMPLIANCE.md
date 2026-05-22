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
