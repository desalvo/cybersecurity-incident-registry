# Security, hardening and residual-risk policy

## 0.10.0-1 RC1: release identity and review status

The development release is **0.10.0-1**. Its build is generated once per CI run
in `Europe/Rome` and reused by the application, documentation and image. Changing
this identity does not renew a security review or approve a production image.
`PRODUCTION_IMAGE_DIGEST` remains `PENDING_HOTFIX_REBUILD` until the candidate
passes all required gates and is promoted by immutable digest.

`TRIVY_RISK_ACCEPTANCE_R8.json` names the current target release and records
`release_status: review_required`. Its `reviewed_baseline` explicitly preserves
the previously reviewed **0.9.0-1 / 20260902** image. The original top-level
`build`, `baseline_image`, review dates, 47 residual entries, package/version
scopes and hardening conditions remain historical evidence. They must not be
silently relabelled as a review of the new build.

The acceptance expired on **2026-10-20** and has **not** been extended. The gate
continues to reject expired acceptance, new HIGH/CRITICAL findings, every
HIGH/CRITICAL Python finding, a newly available `FixedVersion`, unexpected
packages/versions or missing production hardening. The informational review
status is not a substitute for those executable checks. The offline release
verifier checks structure and provenance; its PASS does not approve deployment.

### Current and historical dependency inventories

`sbom/SBOM_CURRENT.cdx.json` describes the current application's 19 direct
dependency declarations. It is explicitly marked `declared-requirements` and
`not-resolved`, carries the SHA-256 of `requirements.txt`, and does not invent
installed versions for version ranges or claim wheel hashes or a resolved
transitive dependency graph. It is generated with
`python scripts/generate_sbom.py --declared-only`.

After installing the pinned dependencies and running `pip check`, CI separately
generates and retains an installed-environment SBOM with the resolved dependency
graph. SCA and both architecture-specific Trivy scans remain required. The
`SBOM_ROUND*.cdx.json` files are unchanged historical inventories, not current
scan evidence. Real browser screenshots and their manuals likewise remain bound
to their captured commit, version and build; a later package date must not
silently relabel them.


### Revisione periodica delle vulnerabilità

`.github/workflows/security-review.yml` è eseguibile su main manualmente e ogni
lunedì alle 06:15 UTC. Un job esegue installazione, pip check e SCA dei requisiti
correnti. Due job indipendenti rieseguono il gate Trivy sul digest immutabile in
PRODUCTION_IMAGE_DIGEST, uno per linux/amd64 e uno per linux/arm64, con database
vulnerabilità aggiornato. Il fallimento di una piattaforma non annulla la scansione
dell'altra. L'esecuzione conserva report e riepiloghi per revisione umana.

Un digest PENDING, una policy scaduta o un nuovo finding non accettato producono
FAIL. Il workflow non rinnova eccezioni, non modifica sorgenti o digest, non
pubblica immagini e non manda automaticamente messaggi a terzi. Per correggere
un finding occorre una PR con motivazione, aggiornamento delle dipendenze o
valutazione esplicita e datata, test e un nuovo candidato scansionato prima della
promozione. Una review schedulata configurata non è prova di una review superata.

Le slide e la guida [TRAINING.md](TRAINING.md#riferimenti-di-sviluppo-conformità-e-manutenzione)
collegano i controlli applicativi e di sviluppo ai riferimenti NIS2/GDPR, AgID/WCAG
e NIST SSDF, citando le fonti primarie e distinguendo queste scelte progettuali
da certificazioni o garanzie automatiche di conformità dell'organizzazione.

## RC20: interfaccia globale e migrazioni controllate

La scelta dell'interfaccia è unica per istanza e modificabile solo da superuser,
con CSRF, validazione server e audit nella stessa transazione. Non altera i
permessi applicativi. AlBot verifica sessione, MFA, ruolo e tenant prima del
provider; il pannello nuovo non aggiunge automaticamente incidente o cronologia.
Gli handler compatibili con la CSP usano script esterni, senza introdurre
`unsafe-inline` o disabilitare la policy.

Il registro di migrazione è locale allo schema e separato dagli export dati.
Revisioni sconosciute o più recenti e drift delle colonne richieste bloccano
l'avvio. I marker condividono il commit finale del bootstrap; errori obbligatori
non vengono ignorati e duplicati/orfani non sono cancellati automaticamente.
Le DDL storiche sono ripetibili ma non costituiscono un'unica transazione globale:
backup coerente e primo avvio in manutenzione restano necessari. Il migratore
parte dopo il passaggio all'utente runtime e prima dei worker HTTP/HTTPS.

La disposition scaduta il **2026-10-20** non è stata prorogata in RC20. Nessuna
eccezione CVE o bypass dei gate è stata aggiunta. Le prove SQLite/HTTP locali
di compatibilità non sostituiscono la CI con pin esatti, PostgreSQL e Trivy.

## RC18: stato corrente e controlli aggiunti

Al **22 novembre 2026** la disposition con scadenza **2026-10-20 è scaduta**.
Non è stata prorogata e non sono stati aggiunti CVE accettati in RC18.
I gate reali mantengono l'orologio corrente e devono bloccare la promozione;
la data storica nei test delle vecchie disposition è isolata ai soli test.
I riferimenti alla review di settembre nelle sezioni successive sono storici.

Tenants Default è modificabile dai soli superuser. Admin di tenant possono
installare e modificare copie nel proprio tenant; le azioni e i riferimenti
cross-tenant vengono validati. Provenienza UUID, mapping locale e controllo delle
condizioni evitano il riuso di ID numerici di un altro tenant. La cancellazione
esegue il controllo d'uso prima di rimuovere relazioni; un errore del controllo
non concede la cancellazione. L'obsolescenza e gli avvisi condividono la transazione.

Export completi della sorgente escludono credenziali per impostazione iniziale;
l'inclusione esplicita richiede protezione del file. Il bootstrap redige anche
snapshot e metadati di provenienza, preservando stati e riferimenti. I documenti
binari riusabili richiedono revisione umana dei contenuti prima di condividerli.
Il seed iniziale copia la configurazione del default operativo, comprese le
integrazioni configurate: verificare quali parametri rendere condivisi.

Helm/OpenShift mantengono non-root, root filesystem read-only, nessuna escalation,
capabilities rimosse e seccomp RuntimeDefault. Il profilo OpenShift usa l'UID
assegnato dalla SCC senza richiedere anyuid. Gli installer richiedono Secret
esistenti e digest immutabili. Le verifiche offline non sostituiscono scan
multiarc, admission, avvio e prova dei volumi nel cluster reale.

Production security controls, temporary Debian risk acceptance, and the fail-closed Trivy policy for 0.9.0-1. The Hotfix 7 acceptance expires on 2026-10-20 and must be re-reviewed earlier if Debian publishes a fixed Trixie version.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `SECURITY_DISPOSITION_R8.md`
- `SECURITY_DISPOSITION_HOTFIX7.md`

---

## Historical source: `SECURITY_DISPOSITION_R8.md`

## Scope

This document records the production disposition of residual HIGH/CRITICAL operating-system findings after container minimization and the additional Debian Trixie review performed on **2026-09-20**. It does **not** waive Python/application vulnerabilities and is not a blanket `--ignore-unfixed` rule.

The machine-readable policy is `TRIVY_RISK_ACCEPTANCE_R8.json`.

## Release policy

Production promotion is permitted only when all of the following are true:

1. `pip-audit` reports no known application dependency vulnerabilities.
2. Real PostgreSQL tests pass.
3. The standard pytest suite passes.
4. `scripts/verify_security_gate_context.py` confirms the required container/Kubernetes hardening.
5. Both `linux/amd64` and `linux/arm64` image manifests pass `scripts/run_trivy_production_gate.sh`.
6. **No HIGH/CRITICAL Python finding is allowed.**
7. **No new/unreviewed HIGH/CRITICAL OS CVE is allowed.**
8. If an accepted CVE declares a package scope, a finding in any other package is rejected.
9. If an accepted CVE declares an installed-version scope, any version outside that scope is rejected and requires a new review.
10. If Trivy reports a `FixedVersion` for an accepted residual CVE, the gate fails and the image must be rebuilt/updated rather than continuing to accept it.
11. The temporary acceptance expires on **2026-10-20** and must then be renewed from a fresh scan and upstream review.
12. The final deployed image must be pinned by immutable registry SHA-256 digest.

## Hotfix 7 - Debian Trixie review

On 2026-09-20 Debian still reports Trixie `util-linux` `2.41.5-0+deb13u1` as vulnerable/no-DSA for:

- `CVE-2026-76642`
- `CVE-2026-78408`
- `CVE-2026-78409`
- `CVE-2026-78410`

The acceptance is limited to the exact util-linux binary package set recorded in the JSON policy and to the reviewed `2.41.5-0+deb13u1` source-version family (including binNMU suffixes). These issues concern local mount/nsenter/privilege-oriented paths that CIR does not expose in its hardened production runtime.

`CVE-2026-16742` is also accepted temporarily only for `libsystemd0` and `libudev1`. Debian reports it as a Trixie no-DSA issue in `systemd-homed`; CIR does not run systemd or systemd-homed inside the application container.

This is a temporary risk acceptance, not a statement that the vulnerabilities are absent.

## Required runtime hardening

The Hotfix 7 disposition depends on the production profile retaining:

- application process non-root (UID 10001);
- `allowPrivilegeEscalation: false`;
- all Linux capabilities dropped for the web container;
- read-only root filesystem;
- seccomp `RuntimeDefault`.

The Docker entrypoint drops bootstrap root privileges to `appuser` by default, while the Kubernetes production manifest directly runs the web container as UID/GID 10001. The optional compatibility fallback that may run as root is **not** part of the accepted Kubernetes production profile.

## Gate usage

After publishing a candidate image:

```bash
./scripts/run_trivy_production_gate.sh \
  desalvo/cybersecurity-incident-registry:0.9.0-1
```

The script first validates the security-gate context, then scans both architectures and evaluates each Trivy JSON report against the policy.

The gate fails if a Python HIGH/CRITICAL appears, a new OS HIGH/CRITICAL appears, a package/version falls outside a scoped acceptance, an accepted CVE gains a fixed version, or the time-bounded acceptance expires.

## GitHub Actions integration

`.github/workflows/ci-release.yml` runs the application, PostgreSQL, SCA and release gates. For release events it builds a multi-architecture candidate under `ci-<sha>`, scans the exact OCI digest, and only after PASS promotes that same digest to `latest` for `main` or to the Git tag for a tag push. See `docs/TESTING_AND_PRODUCTION.md`.

---

## Historical source: `SECURITY_DISPOSITION_HOTFIX7.md`

Data revisione: 2026-09-20  
Release funzionale: 0.9.0-1

## Nuovi CVE temporaneamente accettati

La policy R8 viene estesa in modo puntuale a:

- CVE-2026-76642
- CVE-2026-78408
- CVE-2026-78409
- CVE-2026-78410
- CVE-2026-16742

L'accettazione non è un `ignore-unfixed` generale. I quattro CVE util-linux sono ammessi solo per i pacchetti Debian esplicitamente elencati nella policy; CVE-2026-16742 è ammesso solo per `libsystemd0` e `libudev1`. Qualunque `FixedVersion` riportata da Trivy rende nuovamente il finding bloccante.

La revisione scade il **2026-10-20**. Restano bloccanti tutti i nuovi HIGH/CRITICAL non riesaminati e tutti i finding Python HIGH/CRITICAL.

## Condizioni di hardening

La risk acceptance dipende dal runtime CIR production:

- processo non-root UID 10001;
- `allowPrivilegeEscalation: false`;
- tutte le Linux capabilities eliminate;
- root filesystem read-only;
- seccomp `RuntimeDefault`.

`scripts/verify_security_gate_context.py` controlla queste invarianti nel Dockerfile e nel manifest Kubernetes e viene eseguito anche dal gate Trivy.

## GitHub Actions

La Hotfix 7 aggiunge `.github/workflows/ci-release.yml`. Pull request e push eseguono suite completa, PostgreSQL reale, SCA, verifica RC e packaging. Su push a `main` viene promosso `latest`; su push di un tag Git viene promosso lo stesso tag Docker. La promozione avviene solo dopo il gate Trivy amd64/arm64 sull'esatto digest candidato.

Vedere `docs/TESTING_AND_PRODUCTION.md` per configurazione di secrets/variables e flusso completo.

## Upstream references reviewed

- Debian util-linux tracker: https://security-tracker.debian.org/tracker/source-package/util-linux
- CVE-2026-76642: https://security-tracker.debian.org/tracker/CVE-2026-76642
- Debian systemd tracker: https://security-tracker.debian.org/tracker/source-package/systemd

---


## Hotfix 7 follow-up: 2026-09-20 Trivy refresh

The production gate was intentionally re-evaluated against a freshly downloaded Trivy database before image promotion. The refreshed scan surfaced two categories of findings. First, historical CycloneDX files under `sbom/` were being copied into the runtime image after the documentation/SBOM reorganization; Trivy correctly warned that third-party SBOMs can produce inaccurate package detection and reported stale Python package versions from those historical files. The runtime image now excludes the entire `sbom/` directory. Python HIGH/CRITICAL findings remain unconditionally forbidden by the gate.

Second, the refreshed Debian Trixie scan surfaced residual OS findings for Expat (`CVE-2026-76956`, `CVE-2026-76957`) and libxml2 (`CVE-2026-74860`, `CVE-2026-86138`, `CVE-2026-86139`, `CVE-2026-86140`, `CVE-2026-86142`, `CVE-2026-86143`, `CVE-2026-86144`). At review time Trixie has no fixed package for these findings. They are accepted only temporarily, only for the exact binary package and reviewed Trixie version, and only through 2026-10-20. Any Trivy `FixedVersion`, package mismatch, version mismatch, expiry, Python HIGH/CRITICAL, or new HIGH/CRITICAL remains a hard failure.

The util-linux disposition was also tightened to account for Debian epochs and the special `login` binary version (`1:4.16.0-2+really2.41.5-0+deb13u1`) using package-specific version expressions, rather than broadening the global version rule.


## RC14 security review - 2026-10-01

The production Trivy gate detected three new Debian Trixie HIGH CVEs: `CVE-2026-93990` in `libexpat1`, `CVE-2026-88806` in `libx11-6`/`libx11-data`, and `CVE-2026-88807` in `libxrender1`. The reviewed Trixie package versions currently have no reported FixedVersion in the production scan. RC14 extends the temporary acceptance only to those exact binary packages and reviewed installed-version families. Any reported `FixedVersion`, package/version mismatch, new HIGH/CRITICAL finding, Python HIGH/CRITICAL finding, malformed report, or policy expiry remains blocking. The global and per-CVE review deadline remains **2026-10-20**. Trivy itself remains pinned to `v0.74.0`.


## RC15 Python dependency security update - 2026-10-01

The live `pip-audit` SCA gate detected eight known vulnerabilities in `pypdf==6.16.2`: `CVE-2026-102993`, `CVE-2026-102994`, `CVE-2026-102995`, `CVE-2026-102996`, `CVE-2026-102997`, `CVE-2026-102998`, `CVE-2026-102999`, and `CVE-2026-103000`. The highest minimum fix version across the set is `6.19.0`, so RC15 pins `pypdf==6.19.0`. No Python vulnerability acceptance is added. The SCA helper now prints a concise package/CVE/fix summary when `pip-audit` returns non-zero, while retaining the JSON report.
# Tenants Default RC17 — controlli aggiunti

Aggiornamento del **2026-11-22**. La configurazione condivisa è modificabile dai
superuser; gli admin di tenant leggono il catalogo e installano copie soltanto nel
tenant attivo. MFA, sessioni e CSRF restano applicati ai nuovi endpoint. La sorgente
non è assegnabile come tenant operativo di utenti o incidenti e non esegue job.

I formati portabili hanno schema e limiti espliciti, riferimenti tipizzati e
rimappatura degli ID. I documenti delle nuove copie hanno un proprietario; lettura,
modifica e vecchi percorsi di import/export verificano l'ownership, inclusi alias
di nome PDF. La propagazione mantiene i record locali già presenti e conserva i
parametri ancora referenziati. Il Full Import valida i metadati prima del restore.

L'export completo esclude credenziali per default e le include solo su scelta
esplicita del superuser. I download usano `Cache-Control: no-store, private`.
Testi, indirizzi configurati e PDF sono contenuti di configurazione conservati,
non dati anonimizzati. I file con credenziali incluse richiedono la protezione di
un backup di segreti. L'import usa la chiave crittografica dell'istanza destinataria.
Gli asset referenziati sono limitati e validati; i nuovi percorsi non sovrascrivono
file esistenti e vengono ripuliti su rollback. I documenti ritirati con un tenant
restano inaccessibili anche se un file residuo esiste ancora nel volume.

**Stato del gate:** la risk acceptance presente scadeva il **2026-10-20** ed è
scaduta alla data di questa RC. Nessuna proroga o nuova accettazione è stata fatta.
Restano obbligatori i vincoli production preesistenti, inclusi rifiuto dei finding
Python HIGH/CRITICAL, dei CVE nuovi o con FixedVersion, hardening e scansioni
amd64/arm64. I test storici deterministici non alterano il clock del gate reale.
