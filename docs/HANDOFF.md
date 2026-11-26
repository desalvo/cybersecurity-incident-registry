# CIR — Handoff di sviluppo

## RC83 — 26 novembre 2026 (baseline recuperata RC82, merge più recente confermato dall’utente)

L’utente conferma di aver effettuato commit e merge dell’ultimo avanzamento con CI verde, ma denuncia la mancata PR documentale e le 88 slide del PowerPoint ancora editoriali. RC83 aggiunge zoom nativi verificati della **medesima** screenshot del run Chromium, rimuove promesse di future catture dalle slide e inserisce un controllo bloccante sulle PR documentali saltate. Lo ZIP/PPTX editoriale locale non attesta l’ultima CI; per pubblicare la versione definitiva serve eseguire la pipeline su `main`, controllare il job di pubblicazione e poi integrare la PR dedicata. Nessuna PR remota viene rivendicata. Dettagli in `docs/RC83_CI_SCREENSHOT_FOCUS_AND_PUBLICATION.md`. Messaggio commit in inglese, una sola linea, cumulativo dalle modifiche successive al merge confermato.


## RC82 — 26 novembre 2026 (ultimo merge confermato: RC81)

L’utente ha confermato commit e merge della RC81 con CI verde, ma non si è aperta la PR documentale. La causa è il mismatch `publication_needed` / `documentation_needed`: la CI saltava silenziosamente il job di pubblicazione. RC82 corregge il nome dell’output, rende bloccanti gli output di scope assenti e vieta i segnaposto delle screenshot nei PowerPoint CI rigorosi. Le 88 slide editoriali non sono il risultato autenticato della CI; la PR successiva al merge deve pubblicare i documenti rigenerati e verificati, poi essere integrata su `main`. Commit in inglese, una sola linea, cumulativo dal merge RC81. Vedere `docs/RC82_DOCUMENTATION_PR_RECOVERY.md`.

## Stato attuale: 0.10.0-1 RC79 — 26 novembre 2026

Ultimo merge confermato: RC72 (CI verde); le modifiche RC73–RC79 non sono state dichiarate come committate. RC79 aggiunge l'eliminazione transazionale dei tipi di notifica nel tenant attivo: prima i template, poi il tipo, quindi ripristino immediato di tipo e template pubblicati in `Tenants Default`. Gli alias `_td` legacy vengono riconciliati con il codice condiviso (inclusi i riferimenti operativi locali); i tipi senza sostituzione condivisa restano protetti se ancora utilizzati. Nuovi test: `tests/test_rc79_notification_type_deletion.py` e `tests/test_rc79_notification_type_http.py`. La CI completa Flask/PostgreSQL deve ancora essere eseguita. La presentazione editoriale RC77/RC78 non cambia; il documento CI resta da rigenerare dal commit.

## Stato attuale: 0.10.0-1 RC69 — 25 novembre 2026

La PR della RC68 risulta **committata e integrata con CI verde**, come confermato dall'utente; il precedente riferimento all'ultimo commit RC55 è storico e non è più la baseline per i nuovi messaggi Git. Il run automatico successivo (`logs_123590726294.zip`) passa 1.039 test, ma fallisce due asserzioni nello stesso helper `tests/test_rc2_training_and_brochure_media.py`: più screenshot possono riferirsi allo stesso media PPTX de-duplicato. RC69 verifica ogni coppia ID/hash e consente lo stesso percorso soltanto se SHA-256 coincide; screenshot assenti o alterate restano vietate.

Il corso visivo passa da 79 a 85 slide: sei nuove pagine dopo la sezione 02 spiegano apertura dalla home, inserimento manuale, selezione di un modello, contenuti dei modelli, autorizzazioni, operazioni CRUD e creazione da incidente esistente. Il primo esempio usa la screenshot autentica del registro, oppure la cattura Chromium corrente in CI; gli altri usano schemi modificabili e un'immagine sintetica tracciata tramite hash. La screenshot delle palette del precedente modulo 70 è ora fisicamente nella slide 76, con associazione XML e hash ancora verificati. La CI completa RC69 richiede nuovo run.

Messaggi Git sempre in inglese e su un'unica linea; il prossimo commit contiene **solo** modifiche successive al merge RC68 confermato.

## Stato attuale: 0.10.0-1 RC66 — 25 novembre 2026

Log CI `logs_123402907608.zip`: la suite Python (1035 passati, 24 saltati, 182 subtest) e i 22 test PostgreSQL sono verdi; Playwright ha acquisito tutte le 25 immagini autentiche. Il fallimento e` nel successivo validatore offline: `spam-incident-config-labels` e` uno screenshot del solo elemento DOM `#incident-main .dnd-layout`, piu` stretto del viewport, che il validatore trattava impropriamente come cattura a pagina intera. RC66 distingue `viewport`, `full-page` ed `element`, registrando le dimensioni pixel del ritaglio e l'esatto selettore autorizzato, mantenendo intatti hash, provenienza, controlli sulle copertine e legame al commit. Test locali: 133 passati e 55 subtest; Chromium reale conferma il formato dell'immagine elemento. Nessuna modifica applicativa o grafica. Nuovo run CI richiesto prima della produzione. Dettagli: `docs/RC66_UI_EVIDENCE_GEOMETRY.md`. Messaggi Git sempre in inglese, su singola linea.

RC53: SPAM browser fixture enables personal_data to render both conditional steps (13 total); added regression coverage.

## Stato attuale: 0.10.0-1 RC62 — 25 novembre 2026

Baseline RC61: solo revisione didattica/media; logica applicativa Tenants Default invariata. Asset fotograficamente realistici ma originali/sintetici, nessuna persona reale e nessuna fotografia stock aggiunta. Sostituiti cinque visual con silhouette (slide 28/33/35/42/43) mediante immagine generata senza persone e diagrammi PowerPoint nativi; aggiornati sfondi delle aperture sezione 27 e 61. Prove locali: 54 test e 7 subtest passati, deck 79 slide e PDF 79 pagine, nessun overflow; nuovi SHA-256 e gate di provenienza aggiunti alla CI. Screenshot dell'applicazione da CI autentica vanno ancora rigenerate. La CI completa GitHub Actions NON e` stata eseguita in questa consegna. Dettagli: `docs/presentation/RC62_IMAGE_POLICY.md`.

Messaggi Git: sempre in inglese, su una sola linea e cumulativi dall'ultimo commit confermato. Ultimo commit confermato negli appunti di lavoro: RC55 (SHA ignoto).

## Stato precedente: 0.10.0-1 RC61 — 25 novembre 2026

Baseline RC60. Il corso visuale ora contiene 24 illustrazioni contestuali distinte nelle slide richieste, un esempio didattico di report PDF su due pagine alla slide 21, e le correzioni alle slide 34/39/44/47/55. La slide 70 **non** presenta più una vecchia screenshot con categorie duplicate: viene usata un'illustrazione concettuale fino al gate di screenshot reali in CI.

Riconciliazione Tenants Default estesa alle label `data_type`, non soltanto `category`, nella sincronizzazione e nelle palette degli incidenti. Le etichette semanticamente uguali compaiono una sola volta; gli ID e i riferimenti storici non vengono distrutti. La CI crea alias legacy sintetici in entrambe le palette e verifica nel browser che le scelte siano uniche, acquisendo la nuova vista `spam-incident-config-labels`. Il contratto di documentazione passa da 24 a 25 acquisizioni; il deck lungo è rigenerato sullo stesso commit e verificato con SHA-256.

QA locale: 50 test statici di presentazione/evidenza/screenshot e 7 subtest superati; 79 slide, 79 pagine, nessun overflow. Non eseguiti: suite Flask/PostgreSQL, acquisizione browser dell'app e job remoti GitHub Actions. La RC61 è un candidato sorgente, non un artefatto di CI verde. Dettagli in `docs/presentation/RC61_REVIEW_AND_CAPTURE.md`. Messaggi di commit solo **in inglese e su singola linea**. Ultimo commit confermato in archivio: RC55 (SHA ignoto).

## Stato precedente: RC60 — 25 novembre 2026

Baseline RC59. Nuova PR, log `logs_123309413943.zip`: job di qualita'
`1005 passed, 24 skipped, 182 subtests passed`; fallisce soltanto il gate
`Real UI screenshots and documentation` con `AssertionError:` senza traceback.
Il controllo browser RC59 si aspettava erroneamente che il PDF generato
conservasse i campi AcroForm `RIFERIMENTO`, ma la generazione corretta CIR
appiattisce i campi e li sostituisce con testo statico sulle pagine. RC60
verifica invece PDF statico senza widget e valore incidente stampato,
ricavato dalla fixture stessa. Sono stati aggiunti quattro test isolati e
traceback sanitizzato in `failure.json`/log CI per ogni futura anomalia.
Nessuna modifica al motore PDF, alla UI o alle 79 slide RC58: la CI deve
ancora produrre tutte le screenshot reali. Dettagli in
`docs/RC60_UI_CAPTURE_CI.md`. I job applicativi e di rilascio non vanno
considerati verdi fino alla verifica effettiva su GitHub Actions.
Messaggio commit sempre su una sola linea. Ultimo commit confermato nello
storico in archivio: RC55, SHA non disponibile; verificare la storia Git
prima di comporre commit cumulativi.

## Stato precedente: RC59 — 25 novembre 2026


La baseline e` RC58. Nel log `logs_123289927725.zip` i due gate falliti
sono: (1) `tests/test_workflow_lifecycle.py::test_defaults_workflow_uses_exact_replica_ids_after_numeric_and_name_collisions`, che ora verifica il remapping della categoria locale e mantiene le repliche indipendenti per gli altri tipi di label; (2) screenshot browser PDF, in cui il selettore usa ora la card visibile e verifica la selezione. Nessuna modifica al codice applicativo o ai 79 contenuti delle slide RC58: il job CI continua a ricostruire il deck RC58 con evidenze del medesimo run.

Verifiche locali: 4 test di presentazione/catture editoriali superati, sintassi
Python valida, test isolato Chromium con il CSS reale e checkbox nascosta
superato. **Da ripetere in PR**: la suite pytest completa e il job
`ui-documentation` con screenshot reali, seguito dai gate downstream.
Non dichiarare CI verde finche` GitHub Actions non conferma entrambi i job.
Il messaggio Git va sempre scritto su **un'unica linea**. L'ultimo commit
confermato rimane RC55 secondo lo storico disponibile, SHA non comunicato.

## Stato precedente: RC58 — 25 novembre 2026


Baseline recuperata: **RC57**; ultimo commit Git confermato nel report
RC57: **RC55** (SHA non disponibile). La versione funzionale resta
`0.10.0-1`, con `BUILD=20261124` nei materiali editoriali pre-CI.

- PowerPoint didattico RC58: 79 slide modificabili in
  `docs/presentation/CIR_Operational_Training_Visual.pptx`, versione PDF
  associata e fonte editabile in `visual_rc58_spec.json`. Le correzioni
  editoriali e la revisione sistematica dei workflow sono descritte in
  `docs/presentation/RC58_REVIEW_AND_CAPTURE.md`.
- Sono presenti da RC57 remapping di una categoria omonima già locale nel
  tenant, recupero di Tenants Default dopo restore legacy e mantenimento degli
  ID storici. RC58 integra nel picker una deduplicazione anche degli alias
  legacy `[Tenants Default]` non più mappati, preservando i record esistenti
  e indicando la provenienza locale/ereditata. Nuovi test regressione aggiunti.
- La CI browser contiene già la cattura di 24 viste, con incidenti realmente
  chiusi, PDF generato via CIR, mapping, Alfresco e dati sintetici. **RC58 ora
  costruisce anche il deck visuale e il PDF dalla stessa acquisizione**, con
  verifica degli SHA-256 delle cinque immagini obbligatorie, controllo immagini
  approvate/assenza UI classica, 79 slide/pagine e integrazione nel package.
- Test locali eseguiti: `tests/test_visual_training_rc58.py` **3 passed**;
  presentazione overflow **PASS**, parser YAML **PASS** e compilazione dei file
  Python modificati **PASS**. Non è disponibile l'ambiente Flask/SQLAlchemy:
  suite backend completa, PostgreSQL reale e Chromium CI **NON eseguiti**.
  Il package prodotto localmente è **SOURCE SMOKE** e non una release verde.
- Punto di ripartenza: eseguire il job `ui-documentation` della GitHub Actions
  sul commit corrente, controllare screenshot e PDF finali; verificare inoltre
  la suite `tests/test_tenant_defaults_core.py`, i restore di vecchi export e
  la pipeline completa prima della distribuzione.

## Stato storico RC4 (mantenuto come riferimento, non stato attuale)

Ultimo aggiornamento storico: **2026-11-23** (Europe/Rome). Versione funzionale
in sviluppo **0.10.0-1**, build generata **20261122**. Candidato cumulativo:
**0.10.0-1 / RC4 — correzioni preliminari CI (non validata)**.

## Addendum RC4 — primo intervento sui log CI (23 novembre 2026)

Baseline confermata dall'utente: RC3 committata. Il run GitHub Actions
`45086610196` ha registrato 22 fallimenti pytest (926 passati, 24 saltati)
e un blocco SCA nel job browser/documentazione. Questo candidato **non risolve
ancora tutti i fallimenti** e non deve essere promosso o presentato come CI verde.

- `requirements.txt`: Pillow 12.3.0 -> 13.0.0 e pypdf 6.19.0 -> 6.21.4,
  secondo le versioni correttive indicate dal log `pip-audit`. Disponibilita'
  dei pacchetti e compatibilita' applicativa da confermare in CI.
- `app/migration_manager.py`: il controllo del ledger durante il secondo
  bootstrap non deve forzare l'autoflush di dati applicativi pendenti.
- `docs/presentation/assets/sources.json`: esplicitata la natura fittizia
  della grafica sintetica della brochure, senza modificare le immagini.
- SBOM dichiarativa rigenerata dalle dipendenze correnti.

Bloccanti rimanenti: test Flask/integration non riproducibili localmente,
regressioni tenant/import/workflow, localizzazione, documenti PDF e verifica
SCA/Playwright su GitHub. Richiesto nuovo run CI dopo ulteriori correzioni.

## Addendum RC3 — verifica editoriale brochure (23 novembre 2026)

Candidato incrementale `0.10.0-1 RC3` sulla baseline RC2: il verificatore
`scripts/audit_documentation_media.py` esamina **tutte le immagini incorporate**
nei PDF delle brochure IT/EN, non soltanto la presenza del banner. Richiede
identità dei pixel con i nove asset locali ammessi, nessuna immagine ulteriore,
quattro pagine per lingua, contenuti delle tre sezioni, metadati/versione/build
in copertina e nei piè di pagina, e collegamento cliccabile al progetto.
Le due brochure sono state rigenerate con la dicitura RC3; il controllo
visivo ha inoltre eliminato la sovrapposizione del banner con i titoli; il controllo è
eseguito anche dal job di documentazione CI esistente. Le immagini di copertina
comprendono sei marchi di tecnologia: il controllo di provenienza locale non
conferisce diritti di marchio, certificazioni o endorsement.

Restano **non eseguiti** screenshot Chromium reali, gate PostgreSQL/Helm
completi, SCA remota, Trivy multiarch e pubblicazione production. Il digest
production resta `PENDING_HOTFIX_REBUILD`. Non attribuire la qualifica di
evidenza browser agli elementi illustrativi della presentazione.

## Punto da cui riprendere

Il cumulativo corrente è `cybersecurity-incident-registry-0.10.0-1-rc3.zip`,
con checksum e report RC3. La baseline incrementale documentata resta
`cybersecurity-incident-registry-0.10.0-1-rc2.zip`; la patch storica
RC1 → RC2 e il relativo report non attestano le modifiche RC3.
 La consegna è un candidato sorgente;
non è un PASS dei gate production né un'immagine pubblicata.

- Baseline esatta: `cybersecurity-incident-registry-0.9.0-1-ui-rc20.zip`.
- SHA-256 baseline: `163e7f80e68b01c775c3e0188d292f025f1850d75d2ce70f481d09807996b760`.
- Identità persistente baseline RC20: `libfile_65764dbd2f2c81a4bedf4595306c1106`.
- Identità persistente di questo Handoff: `libfile_5c29923dcfb481a490af761b31b88edc`.
- Commit locale della baseline per la patch: `c98a52ff1182217a427f5b826c6bc806e0b858c9`;
  è un riferimento di lavoro, non un commit confermato dall'utente.

L'utente ha confermato che il tag `0.9.0-1` esiste e ha richiesto esplicitamente
che lo sviluppo passi a `0.10.0-1`. Il tag precedente rimane invariato; la sola
conferma dell'esistenza del tag non identifica lo SHA corrente di main e non
azzera il checkpoint del messaggio di commit cumulativo.

### Contratto di versione e build

- `VERSION` contiene `0.10.0-1`; non rinominare le prove e i riferimenti storici.
- `release_metadata.py` centralizza validazione e lettura. Il generatore
  `scripts/prepare_release_metadata.py` produce `YYYYMMDD` nel fuso `Europe/Rome`.
  La CI calcola una sola build per esecuzione e la distribuisce a test, documenti,
  screenshot e immagine tramite `CIR_RELEASE_BUILD`. Per questa preparazione è
  stata congelata a `20261122` prima della rigenerazione dei documenti.
- I file VERSION/BUILD distribuiti prevalgono su vecchi `APP_VERSION`/`APP_BUILD`
  di Compose/Kubernetes: cambiare immagine aggiorna anche l'identità visualizzata.
  Un semplice riavvio non ricalcola la data dell'immagine.
- Il passaggio 0.9.0-1 → 0.10.0-1 usa il ledger automatico esistente. Nessun DDL
  aggiuntivo è richiesto dal solo cambio di versione; la revisione
  `20261122_01_legacy_bridge` resta immutata. Conservare backup, Secret/PVC e
  avvio iniziale coordinato con una sola replica come in [MIGRATION.md](MIGRATION.md#aggiornamento-a-0100-1-da-090-1).
- `PRODUCTION_IMAGE_DIGEST` resta `PENDING_HOTFIX_REBUILD`. Nessuna immagine è
  stata costruita/promossa. La disposition Debian scaduta il 2026-10-20 non
  è stata prorogata. PostgreSQL reale, browser, SCA e Trivy restano gate distinti.

### Documentazione approvata e applicata

Il 23 novembre 2026 l'utente ha approvato il mockup comune e autorizzato
l'applicazione a tutta la documentazione PDF e online, alle brochure e al
PowerPoint didattico. La decisione supera le note storiche “da approvare”.

- Copertina nativa condivisa: `scripts/documentation_cover.py`; HTML/CSS in
  `app/templates/documentation/` e `app/static/ui/documentation.css`. Il testo
  resta selezionabile. Logo e fotografia cybersecurity approvati non contengono
  persone. I sei marchi identificativi sono asset locali con provenienza in
  `app/static/branding/platforms/manifest.json`; non è dichiarata una certificazione
  o un'approvazione dei titolari dei marchi.
- `application_identity.py` alimenta About, PDF, web e materiali didattici:
  Alessandro De Salvo, Alessandro.DeSalvo@roma1.infn.it, URL del progetto
  https://github.com/desalvo/cybersecurity-incident-registry. APP_PROJECT_URL
  è configurabile e validato HTTP(S); VERSION/BUILD sono letti separatamente
  dall'identità pubblica e restano quelli distribuiti.
- Quattro manuali IT/EN, Alfresco e due brochure sono rigenerati con la nuova
  copertina. I tre download PDF legacy dell'app la applicano anche a runtime.
  Dieci guide consolidate sono consultabili e scaricabili in PDF da
  `/aiuto/guide/<slug>`; elenco chiuso, nessuna esecuzione di HTML nel Markdown,
  stessi controlli di sessione, MFA e lingua delle route esistenti.
- Navigazione documentale laterale nella UI moderna, navigazione compatta nella
  classica; menu operativi, ricerca, indici e contenuti precedenti conservati.
- PowerPoint **34 slide** modificabili, note del relatore, tutti i 21 argomenti
  originali, esercizi step-by-step, 5 prime pagine dei manuali realmente generate,
  piattaforme, NIS2/GDPR/AgID/WCAG/SSDF come riferimenti progettuali documentati
  e ciclo rilevare/valutare/correggere/verificare/promuovere/riesaminare. Nessuna
  certificazione o garanzia automatica di conformità dichiarata.
- Edizione PPTX sorgente: `real_screenshots: false`, 17 riquadri dichiarati
  “Acquisizione CI in attesa”. La CI genera l'edizione con screenshot reali
  dell'applicazione allo stesso commit, VERSION e BUILD. Nessun mock è usato come
  evidenza browser. I 5 PNG incorporati sono invece le effettive prime pagine PDF.
- Pipeline obbligatoria: 17 catture reali → 8 PDF → PPTX → ricevuta aggregata →
  validazione completa → installazione nel candidato. 15 artefatti finali vincolati
  a hash e metadati; analizzati anche media, slide e note effettive del PowerPoint.
  Deck, ricevuta e preview sono installati in `docs/presentation/`.
- `.github/workflows/security-review.yml`: lunedì 06:15 UTC e dispatch manuale
  su main, SCA dei requisiti correnti e Trivy separato amd64/arm64 sul digest
  production registrato. Non costruisce/promuove, non aggiorna eccezioni, non
  manda messaggi a terzi. Pending e disposition scaduta falliscono esplicitamente.

I riferimenti approvati sono [proposal-pdf.png](design/documentation-v2/proposal-pdf.png)
e [proposal-online.png](design/documentation-v2/proposal-online.png), stato
`approved-implemented` in [proposal.json](design/documentation-v2/proposal.json).
I mock UI storici approvati rimangono immutabili. Dropbox resta non caricato:
la precedente integrazione era disabilitata dall'amministratore; non aggirarla.

### Verifiche della 0.10.0-1 RC1

- 126 unittest dei metadati/build, pipeline screenshot, ricevute/installazione,
  builder PPTX e revisione periodica: PASS; 6 controlli container e un export
  workflow con app reale aggiuntivi: PASS. I test artificiali delle ricevute
  verificano il validatore e non sostituiscono le acquisizioni browser.
- 9 unittest HTTP reali della documentazione: PASS, comprendono 26 combinazioni
  lingua/pagina, 6 download PDF utente/admin/note, guida consolidata PDF,
  classica/moderna, asset, sessione/MFA, escaping ed elenco chiuso dei percorsi.
- 22 regressioni upgrade/schema con SQLite reale e ambiente compatibile: PASS;
  le verifiche PostgreSQL reali restano distinte.
- Renderer Markdown: 2 regressioni PASS su contenuti lunghi, tabelle, codice,
  Unicode, escaping e URL; tutte 10 guide renderizzate. Manuali/brochure e deck
  renderizzati e controllati visivamente. I report finali contengono i conteggi
  specifici senza sommare le riesecuzioni dello stesso test.
- Offline release verifier, security context, manifest YAML, controlli installer,
  struttura package, integrità ZIP, replay patch e confronto byte/permessi:
  esiti effettivi nel report esterno `cir-0.10.0-1-rc1-verification.json`.

Le prove applicative locali usano Python 3.13.5 / Flask 3.1.3 / SQLAlchemy 2.0.52 con
pypdf 6.10.2 e cryptography 46.0.7 disponibili offline: non sono i pin CI pypdf 6.19.0
e cryptography 50.0.1. I controlli stdlib/YAML/documenti usano anche Python 3.12.14.
Full pytest con pin esatti, PostgreSQL reale, rendering Helm reale, browser,
SCA remoto, Trivy e build container devono ancora essere eseguiti in CI.
L'accettazione scaduta non è stata rinnovata per far passare i gate. Il cumulativo
è completo come candidato sorgente, non come immagine production già approvata.

## Provenienza RC20 — record storico

La sezione seguente descrive la preparazione della precedente 0.9.0-1 RC20;
nomi, hash e risultati restano conservati come storia e non identificano la RC1.

Usare `cybersecurity-incident-registry-0.9.0-1-ui-rc20.zip`, il relativo file
`.zip.sha256` e `cir-0.9.0-1-rc20-verification.json`. La patch binaria è
`cir-0.9.0-1-design-review-rc19-to-ui-rc20.patch`.

- Baseline esatta: `cybersecurity-incident-registry-0.9.0-1-design-review-rc19.zip`.
- SHA-256 baseline: `10badfb6b5f70b17a45b8c40f9c6020a16727bb4b1f3ea0a1609793ac45a3331`.
- Identità persistente baseline RC19: `libfile_bbbe4740c26081a48879faff15a5e8e8`, versione 6.
- Baseline precedente RC18: `fc4ad0dad5ea918dfb7a6961d6b4288d90234ae6600f2e48e0dd64a7dfc199bc`.
- Fixture storica autentica RC16: package SHA-256
  `ce26e59072375475932596b8c6e76acee2b936b23a5c155d766c63251a794d41`;
  provenienza del membro in `tests/fixtures/rc16_schema/PROVENANCE.json`.
- Identità persistente di questo Handoff:
  `libfile_5c29923dcfb481a490af761b31b88edc`. Aggiornare lo stesso documento e
  conservarlo anche in `docs/HANDOFF.md` dentro ogni cumulativo.

Nessun push, merge, build o promozione Docker è stato effettuato in RC20.
`PRODUCTION_IMAGE_DIGEST` resta **PENDING_HOTFIX_REBUILD**. Le verifiche locali
comprendono ora HTTP/ORM/SQLite reali in un ambiente di compatibilità, ma **non
certificano l'intera suite con i pin CI, PostgreSQL o browser**. Limiti sotto.

## Decisioni UI e migrazione già applicate in RC20

1. Login v2, home v1, dettaglio incidente v1 e assistente v1 sono tutti approvati:
   implementare fedelmente, mantenendo liste e blocchi descrizione/task con frecce.
2. Switch globale per scegliere nuova UI o classica, **nuova UI attiva per default**.
   Questa istruzione supera esplicitamente il vecchio default OFF dei mock.
3. Aggiornare manuali con screenshot dell'interfaccia reale tramite CI; non usare
   mock o rendering progettuali come evidenza browser.
4. L'upgrade da 0.9.0-1 build20260902 avviene aggiornando l'immagine e ricreando il
   pod. Assicurare migrazioni automatiche fra le baseline supportate e predisporre
   un meccanismo generale per le revisioni future; documentare operazioni e limiti.
5. Nel checkpoint storico RC20 copertine e brochure erano ancora da approvare.
   La successiva approvazione 0.10.0-1 RC1, descritta sopra, le ha rese operative. Le fotografie nuove devono essere tecnologiche/cybersecurity,
   senza persone. Non introdurre fotografie amministrative generiche.

## Implementazione RC20

### Interfaccia approvata

- Login, sidebar desktop, menu mobile, registro, dettaglio incidente e AlBot
  integrati nei template reali, con gli endpoint e le verifiche esistenti.
- Registro a lista; filtri/ordinamenti/paginazione/azioni conservati. Incidente
  con riquadro descrittivo sopra e task/comando sotto, frecce quando configurate,
  senza introdurre un blocco sequenziale non previsto dal workflow.
- `app/ui_settings.py`: Setting fisico globale `global_ui_mode`, valori `modern`
  e `classic`, assenza/valore invalido → modern. Nessuna preferenza per browser
  o tenant può sovrascriverlo. Pagina `/admin/interface`, superuser soltanto,
  POST con CSRF e audit nella stessa transazione; efficace al caricamento seguente.
- `app/static/ui/ui.css`, `ui.js` e template `ui/`: fotografie runtime copiate
  byte-per-byte dagli asset approvati; destinazioni e permessi del menu preservati.
- Gli handler inline incompatibili con CSP passano a listener esterni. Non è
  stato aggiunto `unsafe-inline`, né disabilitata la CSP.
- AlBot inizialmente chiuso, pannello affiancato sui desktop ampi e vista dedicata
  sui piccoli schermi. Icona neutra senza volto. In Tenants Default, tenant solo
  configurativo, non vengono esposti chat e launcher operativi.
- L'API usa domanda, CSRF e binding tenant; sessione inattiva, MFA pendente,
  ruolo disabilitato o tenant cambiato vengono respinti prima del provider.
  Nessun invio automatico dell'incidente aperto o della cronologia visuale.
  Documentazione/KB/snapshot opzionale seguono le impostazioni reali del plugin.

### Migrazioni automatiche

- `app/migration_manager.py`: registro tecnico raw `cir_schema_migrations`
  esterno ai modelli ORM/export, indipendente da VERSION/BUILD. Revisione iniziale
  `20261122_01_legacy_bridge` per installazioni precedenti al registro.
- Preflight prima del recovery: storia sconosciuta, più recente, incompleta o
  riordinata blocca l'avvio. Il bootstrap ripete il controllo sotto il lock
  PostgreSQL, applica solo le revisioni mancanti e valida tabelle/colonne richieste.
- Marker registrati nella transazione finale dei dati di bootstrap, mai prima
  del successo. Le DDL legacy possono avere commit separati: possono restare
  modifiche parziali dopo un errore, riprese da callback idempotenti al retry.
- `app/migrate.py` viene eseguito da `docker-entrypoint.sh` dopo il passaggio
  all'utente runtime e prima dei worker HTTP/HTTPS. La migrazione non è soggetta
  al timeout di avvio di un worker Gunicorn; serve comunque un budget startupProbe
  adeguato nel cluster. `create_app()` mantiene anche i controlli per avvii esterni.
- Correzioni concrete: `auth_provider` prima del suo uso, nuova introspezione
  dopo DDL, date popolate al primo upgrade, ID tenant default non assunto uguale
  a 1, sequence riallineate prima degli INSERT legacy, flag/testi personalizzati
  e operazioni automatiche vuote conservati. Errori di vincoli obbligatori,
  duplicati e ownership orfana PostgreSQL bloccano senza cancellare dati.
- Il normale bootstrap dati continua a ogni avvio/import: saltare le DDL già
  registrate non salta le normalizzazioni applicative necessarie. Full Import
  non trasferisce né elimina il registro tecnico e crea i modelli correnti.
- Release future: appendere una revisione ordinata e callback, con test dalla
  precedente baseline supportata. Non riscrivere una revisione già pubblicata.
  Non promettere compatibilità con database arbitrariamente modificati, versioni
  future sconosciute o downgrade automatici. SQLite concorrente non supportato.

### Screenshot e documentazione CI

- Job obbligatorio **Real UI screenshots and documentation**: applicazione Flask
  reale su loopback, database/storage sintetici, CSRF e login reali, provider AI
  HTTP locale deterministico, browser Chromium gestito da Playwright.
- 13 catture: login desktop/mobile; registro desktop/mobile/menu mobile; incidente
  desktop/mobile; assistente desktop/mobile; interfaccia globale; registro
  classico; moduli; SSO. Errori JS, asset/rete esterni inattesi e assert bloccanti.
- Manifest lega commit, versione/build, viewport, modalità, origine reale,
  fixture dimostrativa e SHA-256. Installer verifica l'intero lotto, conserva
  manifest originale/ricevuta, installa le figure e i PDF prima del build candidate.
- Quattro manuali IT/EN e galleria `CIR_UI_Screenshots.pdf` generati dalla CI.
  Il cumulativo locale aggiorna il testo e le cover adottate, ma non contiene
  finte catture runtime. Le figure nuove verranno incorporate dal run CI.
- Il job Docker dipende da test/SCA/PG e da screenshot/doc. Artefatto dello
  stesso run, commit verificato, nessuna PR automatica per ogni screenshot.
  Metadata-only digest PR continua a non ricostruire l'immagine.
- Aggiungere **Real UI screenshots and documentation** ai required checks di main.

### Riferimenti grafici da preservare

`docs/design/login-v2/`, `home-v1/`, `incident-v1/`, `assistant-v1/` e le fotografie
approvate sono invariati rispetto alla RC19. La specifica e la provenienza
registrano l'implementazione runtime; gli asset di progetto restano esclusi
dall'immagine Docker. Le proposte iniziali superate e i loro renderer rimangono
come cronologia sotto `docs/design/`, non definiscono il comportamento corrente.
Login: «Gestione degli incidenti di sicurezza e tracciabilità delle attività.»;
mobile: logo e nome completo sopra l'immagine, senza slogan sull'immagine.

## Istruzioni persistenti

- La successiva richiesta esplicita dell'utente sposta lo sviluppo a **0.10.0-1**
  e ripristina la build automatica: supera il precedente vincolo VERSION 0.9.0-1 /
  BUILD 20260902. Hotfix 1–7 e RC precedenti restano storicamente nella 0.9.0-1.
  I candidati della nuova linea non cambiano la versione funzionale per il solo
  numero RC. Conservare Alfresco, import/export, bootstrap, recupero da crash,
  catalogo, UI e pipeline già inclusi nelle baseline.
- Conservare questo Handoff sia nel package sia come documento persistente.
- Salvare sempre il cumulativo nella Library prima della consegna e fornire
  il collegamento nativo al file, oltre all'eventuale copia locale. Aggiornare
  lo stesso file per correzioni documentali della medesima RC, conservandone
  identità e versioni. Non affidare il download al solo percorso temporaneo.
- Conservare al massimo i **20 package cumulativi CIR più recenti** nella
  Library. Dopo il salvataggio verificato del nuovo cumulativo, spostare nel
  Cestino quelli eccedenti, identificati tramite ID persistente e data di
  creazione. Il limite riguarda i ZIP sorgente cumulativi, non Handoff,
  documentazione, patch, checksum, installatori, chart o dipendenze offline.
  Non eliminare file di altri progetti o copie condivise non possedute.
  La nuova istruzione dell'utente sostituisce il precedente limite di 10:
  si applica dalla revisione RC18 del 2026-11-22 in avanti. Prima di RC20 erano attivi 11 cumulativi; con RC20 diventano 12 e con 0.10.0-1 RC1 diventano 13, entro il limite di 20;
  quelli già nel Cestino non sono stati ripristinati. Il ripristino dal Cestino
  richiede l'interfaccia utente, non essendo disponibile nell'API corrente.
- Ogni consegna deve includere un **messaggio di commit cumulativo in inglese,
  su una sola riga**, riferito a tutte le modifiche dopo l'ultimo commit/merge
  dichiarato dall'utente. Non azzerare l'accumulatore generando un package,
  proponendo un messaggio o creando un commit locale di preparazione.
  Aggiornare il checkpoint solo quando l'utente conferma il commit/merge,
  registrando SHA e consegna se disponibili; non inventare uno SHA mancante.
- Main è protetto: modifiche tramite PR, mai push diretto. I metadata digest
  usano una PR dedicata e il relativo merge non deve ricostruire l'immagine.
- CI fail-closed: pytest completo, PostgreSQL reale, pip check, SCA, verificatori,
  packaging, rendering Helm; candidate per digest, scan amd64 e arm64, poi
  promozione. Main → latest; Git tag → tag Docker corrispondente.
- Nessun `--ignore-unfixed`, nessuna accettazione HIGH/CRITICAL Python, nessun
  nuovo CVE OS accettato automaticamente. FixedVersion, scope inatteso, policy
  scaduta o hardening mancante restano bloccanti.
- La risk acceptance Debian della baseline è **scaduta il 2026-10-20**.
  La 0.10.0-1 RC1 non la proroga. Serve una nuova valutazione con evidenze attuali.
- Solo README.md e README_en.md in root; documenti in docs/, SBOM in sbom/.
  Niente cache, chiavi, log o scansioni temporanee nel package.
- L'utente preferisce lavoro autonomo e risultati concreti; non richiedere di
  nuovo autorizzazioni già date. Non inviare comunicazioni a terzi senza
  autorizzazione esplicita.


## Checkpoint del commit cumulativo

- `last_confirmed_commit_sha: unknown`.
- Ultima conferma esplicita: «Tutto fatto, mergiata anche chores», precedente agli
  interventi su import e Tenants Default. Nessuno SHA associabile con certezza.
- Il commit locale `172bc870c039d41cb29d6e56cd38553f6be27e85` serve soltanto come
  baseline RC19 della patch, **non è una conferma di commit dell'utente**.
- La consegna RC20, la preparazione 0.10.0-1 RC1, la conferma del tag precedente
  e l'approvazione dei mock non azzerano l'accumulatore.
- Accumulatore: primo avvio PostgreSQL e import/recovery mountpoint; dipendenze e
  CI; Tenants Default, mapping e workflow/lifecycle/export; Helm/OpenShift;
  formazione/brochure; UI approvata, switch globale default ON, AlBot; catture
  reali tramite CI; migrazioni automatiche versionate; passaggio a 0.10.0-1 e
  build automatica condivisa; copertine PDF/web approvate; PowerPoint con acquisizioni CI e riferimenti di compliance; revisione periodica delle vulnerabilità; Handoff e retention20.
- Messaggio proposto, non confermato come commit effettuato:

```text
feat: advance CIR to 0.10.0-1 with automatic builds, portable Tenants Default and workflow lifecycle, safer import recovery and migrations, updated dependencies and CI, Helm/OpenShift installers, the approved responsive UI and AI assistant, shared PDF/web documentation design, CI-backed training materials, periodic vulnerability reviews, and persistent release handoff
```

## Funzioni completate in RC18

### Tenants Default e propagazione

Tenants Default è una sorgente di configurazione speciale, distinta dal tenant
operativo `default`, configurabile dai superuser attraverso le normali pagine
Admin. Se assente, viene creata copiando la configurazione di `default` in una
transazione: label, notifiche, documenti, Settings, modelli e workflow.
Account, incidenti, persone operative e KB private non vengono copiati.
I riferimenti alle persone nei modelli vengono rimossi solo durante questo
seed interno. Una sorgente già presente, anche vuota, non viene ripopolata.
Le bozze copiate vengono pubblicate nel catalogo. Un tenant ordinario omonimo
non viene convertito tacitamente: il conflitto va risolto prima dell'avvio.

La sorgente comprende tutte le configurazioni di tenant: label di gravità,
categorie, tipi di dati, azioni, raccomandazioni, destinatari, modelli incidente,
notifiche e relativi PDF/mapping, backup, SSO/LDAP/SMTP/plugin, campi personalizzati,
pulsanti e altri Settings di tenant. I veri parametri globali restano globali.
I job della sorgente non eseguono backup; le copie hanno percorsi locali.

Le liste conservano provenienza UUID e chiavi locali indipendenti. Una collisione
di ID/nome/codice crea un elemento distinto e non sovrascrive quello preesistente.
Gli aggiornamenti raggiungono le repliche; le personalizzazioni vengono
conservate. I Settings seguono la precedenza: override locale esplicito, anche
vuoto; valore condiviso; valore iniziale. Solo `default` mantiene il fallback
alle proprie impostazioni legacy senza prefisso. Il seed copia le credenziali
configurate di default nella nuova sorgente: controllare quali integrazioni
rendere condivise prima di usare il setup in altri tenant.

### Workflow ripetibili e mapping esatto

Admin → Catalogo workflow: l'admin importa nel proprio tenant, il superuser può
scegliere qualsiasi tenant operativo. Ogni import crea una nuova struttura
modificabile con un nome distinto. Importare due volte la stessa revisione è
consentito. Le dipendenze condivise vengono risolte tramite UUID verso l'esatta
replica locale, anche quando l'ID sorgente coincide con un elemento locale
estraneo. Non usare la sola omonimia per risolvere una dipendenza condivisa.

L'azione **Personalizza parametri** crea copie indipendenti delle dipendenze di
quel workflow, conservando la provenienza per l'obsolescenza. Va eseguita prima
che il workflow sia usato da incidenti; altrimenti creare una nuova copia.
La struttura di ogni import è già indipendente. Le revisioni ordinarie della
struttura nel catalogo non riscrivono le copie installate.

Restano disponibili JSON e copia fra tenant. Il clone rimappa anche notifiche,
PDF/tag e condizioni. I nuovi JSON portano ID sorgente e provenienza delle label;
un riferimento numerico legacy non attribuibile viene rifiutato prima delle
mutazioni, con richiesta di riesportazione. Non reinterpretare un ID sorgente
come ID destinazione. Un'origine catalogo obsoleta non è aggirabile con un vecchio
export, con clone o con una voce di catalogo derivata da una copia.

### Corrente, obsoleto e protezione degli incidenti

Ogni workflow nasce **corrente**; possono essercene più di uno corrente. Questo
stato è distinto dal workflow di fallback con categoria nulla. Il runtime usa
la prima categoria nell'ordine dell'incidente se ha un flusso dedicato, altrimenti
il fallback; non somma più flussi di categorie diverse.

Un workflow obsoleto non può essere assegnato a nuovi incidenti, clonato per
creare un nuovo incidente o importato dal catalogo. Gli incidenti esistenti
conservano il flusso e restano modificabili. Il controllo copre anche i dati
legacy con tenant_id NULL, attribuiti al solo default operativo.

L'obsolescenza in Tenants Default rende obsolete tutte le copie, incluse quelle
personalizzate e le derivazioni. Crea avvisi persistenti nell'applicazione per
tutti gli admin di tenant e superuser, visibili anche cambiando tenant attivo.
La riattivazione della sorgente non riattiva automaticamente le copie; una
copia non può essere riattivata mentre la sorgente resta obsoleta.

Label, parametri e workflow usati da incidenti non sono cancellabili: il guard
precede la rimozione delle relazioni. Copre azioni storiche, categorie/gravità,
condizioni, documenti/notifiche, destinatari, campi personalizzati e modelli.
Per impostazioni/modelli legacy senza registro della provenienza d'uso, la
verifica è conservativa se esistono incidenti. Le repliche condivise si ritirano
dalla sorgente; quelle usate vengono conservate e segnalate.

### Export, bootstrap e nuova istanza

**Admin → Tenants Default → Esporta tutto Tenants Default** produce il bundle
portabile completo: configurazioni, catalogo, bozze, lifecycle, PDF/mapping,
loghi e immagini SSO. Il superuser lo importa nell'altra istanza con
**Importa configurazione in Tenants Default**. Le credenziali sono escluse per
impostazione iniziale; l'inclusione esplicita produce un archivio sensibile.
La destinazione ricifra i segreti con la propria chiave. Dimensione massima JSON
25 MiB con limiti ulteriori per PDF/asset. Elementi omessi non vengono cancellati.

Il Full Export globale comprende sorgente e metadati. Il bootstrap anonimizzato
comprende **default e Tenants Default**, conserva configurazioni/catalogo e
rimuove incidenti, persone, audit, KB e credenziali. L'unico admin viene ricreato
con identità neutra e password iniziale secondo il normale percorso bootstrap;
nessun hash privato viene trasferito. Le definizioni necessarie ai riferimenti
possono restare con placeholder anonimi; i job sono disabilitati e senza segreti.
I PDF riusabili richiedono revisione dei contenuti: non si promette la rimozione
automatica di ogni dato incorporato nei file binari.

Gli import globali validano il grafo prima della ricreazione distruttiva. Gli
import scoped rimappano la categoria e la provenienza pubblica dei workflow;
origine assente/inattiva/obsoleta viene conservata come obsoleta. Un ripristino
legacy privo di lifecycle non riattiva una precedente decisione di obsolescenza.
I vecchi archivi e i file PDF solo filesystem restano supportati nei limiti
illustrati in MIGRATION.md. Full Import sostituisce dati: usare backup/recovery.

## Installazione Kubernetes e OpenShift

Chart `charts/cybersecurity-incident-registry`, versione corrente **0.2.0-rc1**, appVersion
**0.10.0-1**, schema JSON e overlay OpenShift. La precedente coppia
0.1.0-rc18 / 0.9.0-1 appartiene alla baseline storica. PostgreSQL esterno per impostazione
iniziale; interno opzionale, PostgreSQL 18 per digest. Richiesti digest applicativo
approvato, Secret esistente, PVC e TLS production. Sorgente in stato pending non
fornisce un'immagine approvata implicitamente.

Non-root, root filesystem in sola lettura, allowPrivilegeEscalation false,
capabilities ALL rimosse, seccomp RuntimeDefault e token service account
non montato. OpenShift usa UID/GID/fsGroup assegnati dalla SCC, senza anyuid.
PostgreSQL usa PGDATA 18 sotto /var/lib/postgresql, startup budget 30 minuti,
PGCTLTIMEOUT 1800 e probe TCP che non accettano il server temporaneo initdb.
Liveness web TCP e graceful timeout evitano di trattare il solo worker occupato
durante Full Import come errore di vitalità.

`scripts/install_cluster.sh` rende i manifest per impostazione iniziale;
`--apply` verifica Secret e admission prima dell'installazione. Il Template
`openshift/cir-template.yaml` è importabile dalla console grafica. Per il catalogo
Helm grafico pubblicare chart/index.yaml su un repository HTTPS reale e registrarlo
con il manifest di esempio; non è stato pubblicato un repository remoto.

CI richiede Helm stabile major 3, >=3.14, e rendering reale obbligatorio.
La preparazione locale ha controllato struttura/schema/oggetti; non ha potuto
eseguire Helm o admission sul cluster. Guida completa: DEPLOYMENT.md.

## Formazione, brochure e Dropbox

- `docs/presentation/CIR_Operational_Training_IT.pptx`: **34 slide** modificabili,
  note del relatore, immagini cybersecurity senza persone, laboratorio fittizio
  di phishing con sei passaggi operativi e prova di varianti/obsolescenza.
  Conserva i 21 argomenti originali e aggiunge cinque prime pagine reali dei
  manuali, piattaforme, riferimenti di compliance e revisione delle vulnerabilità.
  L'edizione sorgente dichiara 17 acquisizioni CI in attesa; la CI le sostituisce
  con immagini reali verificate dello stesso commit, VERSION e BUILD.
- `docs/TRAINING.md`: preparazione, esercizi, risultati attesi e ricostruzione.
- Sorgenti: content_it.json, `scripts/build_training_presentation.py`, launcher
  build.mjs e asset con provenienza nella directory presentation. Nessun dato
  di incidente reale nelle slide; ricevuta con hash dei PDF e media incorporati.
- Brochure IT/EN: quattro pagine ciascuna. Manuali utente/amministratore IT/EN
  rigenerati, guide online aggiornate e contenuto EN riportato nel blocco renderizzato.
- Destinazione richiesta:
  `/INFN/cybersecurity-incident-registry/CIR_Operational_Training_IT.pptx` in Dropbox.
  **Caricamento remoto non eseguito**: connettore Dropbox disabilitato
  dall'amministratore del workspace (DISABLED_BY_ADMIN / NOT_AVAILABLE).
  Il file è consegnato separatamente e nel package. Non dichiararlo già caricato.

## Mappa del codice e regressioni da eseguire

- `tenant_defaults_seed.py`: seed idempotente dal default operativo.
- `tenant_defaults.py`, `tenant_default_settings.py`: propagazione/provenienza,
  override, collisioni, lock e avvisi.
- `workflow_lifecycle.py`, `workflow_catalog*.py`: stati, origine, copie,
  personalizzazione, ricevute e notifiche globali per utente.
- `configuration_usage.py`: guard read-only sulle dipendenze usate dagli incidenti.
- `tenant_defaults_bundle.py`, `tenant_defaults_bootstrap.py`,
  `tenant_defaults_scoped.py`, `tenant_defaults_archive.py`: portabilità, redazione,
  restore e validazione prima della sostituzione dei dati.
- `tenant_defaults_views.py`, `routes.py`: autorizzazioni e percorsi UI/legacy.
- `form_template_access.py`, `tenant_document_restore.py`: ownership, alias,
  nomi canonici e recupero documenti legacy.
- I servizi nuovi lasciano il commit al chiamante. Propagazione, lifecycle e
  notifiche devono condividere la transazione e un ordine di lock coerente.

Regressione richiesta sugli ID:
`tests/test_workflow_lifecycle.py::test_defaults_workflow_uses_exact_replica_ids_after_numeric_and_name_collisions`.
Anche `test_legacy_json_import_remaps_colliding_condition_ids_and_shared_notification_codes`
verifica il percorso JSON storico. Altri file fondamentali: `test_workflow_lifecycle.py`,
`test_tenant_defaults_rc18.py`, `test_tenant_defaults_http_and_ownership.py`,
`test_rc18_route_guards.py`, `test_cluster_installation_package.py` e
`test_rc18_training_package.py`. I test storici con query globali `.one()` sono
stati resi esplicitamente tenant-aware dopo il seed; le aspettative funzionali
sono conservate.

## Verifiche effettive e limiti RC20

Il report `cir-0.9.0-1-rc20-verification.json` conserva comandi, versioni, risultati
ed hash. Non sommare prove di natura diversa come se fossero una sola suite.

| Prova | Esito e ambito |
| --- | --- |
| Nucleo registro migrazioni | 21 unittest PASS, anche SQLite DB-API reale |
| Adapter SQLAlchemy | 12 unittest PASS, transazioni/rollback/no-op reali SQLite |
| Migrazioni legacy | 3 SQLite PASS, 10 PostgreSQL SKIP; baseline originale riproduce 2 failure e 1 errore |
| Upgrade storico e Full Import | 7 unittest PASS con modelli RC16 autentici e applicazione reale |
| HTTP UI/sessioni/CSRF | 21 controlli PASS sul vero test client Flask |
| Pipeline screenshot | 21 unittest PASS, senza eseguire browser |
| Validazione/installazione prove documentali | 32 unittest PASS |
| JavaScript runtime | 12 controlli shell e 23 AlBot PASS con Node e DOM minimo |
| Contratti UI legacy/nuovi | 43 controlli sorgente PASS, non test HTTP aggiuntivi |
| Package | File obbligatori/hash/permessi/pulizia e applicazione patch verificati nel report |
| PDF | Quattro manuali rigenerati; pagine finali/capitoli nuovi renderizzati e ispezionati |

Ambiente applicativo di compatibilità: Python **3.13.5**, Flask **3.1.3**,
Flask-SQLAlchemy **3.1.1**, SQLAlchemy **2.0.52**, Werkzeug **3.1.8**,
pypdf **6.10.2**, cryptography **46.0.7**. Creato da wheel offline già disponibili;
non modifica i pin del progetto e non è una configurazione production approvata.
Il canale accessibile non consente l'installazione completa dei requisiti esatti.

**Ancora necessari:** pytest completo Python 3.12 con dipendenze esatte, PostgreSQL
reale (nuovi test marcati `postgres`), browser/Playwright, SCA/pip-audit,
Helm reale/admission, build multiarch e Trivy. Nessun bypass di un blocco browser
locale (socket EPERM), nessun risultato Chromium dichiarato. Mancano un server
PostgreSQL e runtime Docker/Podman; non è stata costruita alcuna immagine.

La disposition Debian del 2026-10-20 è scaduta e resta bloccante. Il sorgente non
può essere chiamato release production approvata fino al PASS della CI reale.
I vecchi esiti RC18/RC19 restano storici in RELEASE/DEVELOPMENT_HISTORY e nei
rispettivi report, non vengono estesi automaticamente al codice RC20.

## Procedura operativa di upgrade e prossimi passi

1. Verificare il checksum del cumulativo **0.10.0-1 RC1**. Applicare la patch
   `cir-0.9.0-1-rc20-to-0.10.0-1-rc1.patch` solo sulla **RC20 esatta**, oppure
   usare il nuovo cumulativo; confrontare eventuali modifiche
   GitHub posteriori senza sovrascriverle. Lavorare su branch e PR.
2. Eseguire tutti i gate CI, inclusi PostgreSQL e screenshot/documentazione.
   Riesaminare la disposition scaduta con evidenze aggiornate. Costruire,
   scansionare e promuovere soltanto l'immagine che supera tutti i controlli;
   il digest viene registrato dalla PR dei metadata.
3. Provare l'upgrade su una copia del database/file di produzione. Prima
   dell'intervento preparare un backup coerente e fermare le vecchie repliche web.
   Nessun import/restore deve essere in corso. PostgreSQL rimane attivo.
4. Aggiornare al digest approvato, mantenendo DATABASE_URL, SECRET_KEY,
   SETTING_ENCRYPTION_KEY, PVC, mount e impostazioni operative. Avviare una sola
   replica con startupProbe adeguata; attendere completamento migrazione/readiness.
   Verificare admin, incidenti, workflow, file, integrazioni e interfaccia; poi
   ripristinare lo scaling compatibile con lo storage.
5. Non eseguire Full Import/bootstrap per aggiornare; non azzerare l'admin.
   Non cambiare contestualmente major PostgreSQL, PGDATA o layout PVC. Helm non
   adotta automaticamente i manifest esistenti. Non fare rolling misto vecchio/
   nuovo codice sullo stesso database, né downgrade cieco: rollback può richiedere
   backup dati + vecchia immagine. I binari precedenti a RC20 non conoscono il ledger.
6. Le copertine sono approvate e applicate. Verificare l'artefatto documentale CI
   completo, incluse le 17 schermate reali e il PPTX rigenerato. Il caricamento
   Dropbox resta non effettuato per connettore disabilitato; non dichiararlo
   disponibile a quella destinazione senza un trasferimento riuscito.
7. Aggiornare questo Handoff con risultati reali, SHA confermato e digest approvato,
   preservando identità/versioni e limite di venti cumulativi.

Guida completa: [MIGRATION.md](MIGRATION.md#aggiornamento-a-0100-1-da-090-1),
[DEPLOYMENT.md](DEPLOYMENT.md), [RELEASE.md](RELEASE.md),
[TESTING_AND_PRODUCTION.md](TESTING_AND_PRODUCTION.md).


## 0.10.0-1 RC2 — training media, incident lab, installation bootstrap
- Baseline RC1; functional version remains 0.10.0-1, build generated by CI.
- Audited 13 embedded images in the training PPTX: CIR synthetic server hero, CIR logo, six technology logos, five manual covers. None depicts people, and no third-party stock photograph was found. This is a manual visual audit; the new byte-level allowlist `scripts/audit_training_media.py` enforces asset provenance at authoring time for both source and CI builds.
- Added `docs/CIR_Incident_Laboratory_IT.pdf`: six walkthrough pages based on the real incident UI screenshot produced by the isolated CI browser. The source edition clearly marks the capture as pending; it never labels a mock as a real screenshot. The same workflow screenshot illustrates tasks from opening to closing without claiming each didactic step was actually executed.
- Administrator manuals (IT/EN, PDF and online) now document Docker/Podman Compose, Kubernetes Helm, OpenShift GUI/Helm, Secrets/PVC/TLS, initial bootstrap vs upgrade and a locally drawn architecture figure.
- CI document receipt includes the incident laboratory PDF and verifies its checksum. Source release remains unapproved for production until the exact CI gate passes; expiry of risk acceptance unchanged.
- Preserve 20 latest cumulative CIR ZIPs in Library; every delivery includes a one-line cumulative English commit message.


## Integrazione 0.10.0-1 RC2: laboratorio e audit immagini

- Il PDF didattico `docs/CIR_Incident_Laboratory_IT.pdf` descrive sei passaggi usando una vista reale degli step acquisita da `incident-desktop` in CI; l'edizione sorgente segnala correttamente l'attesa degli screenshot.
- `scripts/audit_training_media.py` controlla gli hash degli asset embedded nel PPTX contro le fonti approvate CIR (hero sintetico, logo, marchi locali, prime pagine dei manuali e screenshot CI). Non equivale a certificare la situazione giuridica dei marchi.
- `scripts/audit_documentation_media.py` controlla la presenza della stessa immagine sintetica CIR nelle otto pagine delle brochure IT/EN, con derivazione del ritaglio locale. Nessuna persona o fotografia stock viene aggiunta.
- Manuale amministrativo web/PDF IT/EN: capitolo installazione e bootstrap multiarchitettura, con diagramma originale CIR e comandi esemplificativi.
- Versione `0.10.0-1`, build automatica invariata. Restano pendenti prove CI complete, PostgreSQL, Playwright, SCA, Trivy, Helm reale e screenshot con evidenza dello stesso commit.

La suite `tests/test_rc2_training_and_brochure_media.py` e il job `ui-documentation` controllano gli asset delle brochure e che la cattura `incident-desktop` contenga tre frecce tra quattro riquadri. Non si considera completato il laboratorio finche la cattura browser reale non e attestata nella CI.

## RC6 — CI triage after committed RC5

- Regenerated declared SBOM_CURRENT.cdx.json from current pinned requirements.
- Screenshot fixture reuses existing action labels, avoiding duplicate tenant/kind/value.
- Updated obsolete static version test to the authoritative VERSION/BUILD contract.
- Focused local tests: 8 passed; offline verifier: PASS.
- Flask is unavailable locally; the remaining CI failures and real browser captures have NOT been validated or resolved. Do not promote.


## RC7 CI follow-up (after committed RC6)

- Screenshot capture now polls image readiness with a Playwright callable,
  avoiding the strict-CSP unsafe-eval rejection. CSP is not weakened.
- CI rebuilds both brochures after stamping the workflow BUILD and before
  running tests, preventing stale embedded build metadata.
- The 19 remaining pytest failures in the uploaded RC6 run are not all
  resolved by these changes. In particular tenant defaults, import/export,
  wizard, workflow and UI tests require further integration verification.
- No production approval or full CI pass is claimed.

## RC9 — verifica con wheel Python 3.13 (candidato non approvato)

- Il resolver delle configurazioni condivise sincronizza nel medesimo contesto transazionale le repliche dei tenant appena creati prima di risolvere un UUID, senza selezionare record per nome.
- Il test di conferma della rubrica esterna verifica il meccanismo CSP-safe `data-cir-confirm`, non l'obsoleto handler inline.
- Test mirati verificati: 4 PASS (clonazione tenant, assorbimento label legacy, wizard setup, conferma rubrica).
- Restano regressioni CI non risolte: workflow catalog, audit, import full, traduzioni/test UI e paginazione PDF. Non dichiarare PASS della CI o promuovere in produzione.
- Baseline Git confermata dall'utente: RC8. Nessun commit o push eseguito da questo ambiente.

## RC10 — CI remediation after committed RC9 (2026-11-23)

Baseline: user-confirmed committed RC9. Source candidate RC10 keeps VERSION 0.10.0-1.
The uploaded GitHub Actions logs show 14 pytest failures (934 passed, 24 skipped) and a separate browser documentation image assertion.

- Fixed the modern registry's Italian bulk-action label.
- Runtime administrator PDF now reserves space before chapter headings.
- Browser capture checks only images intersecting the viewport and reports exact failing image URLs; local browser execution is blocked by environment policy, so this requires CI verification.
- Updated regressions to explicitly negotiate Italian when checking Italian UI, assert the actual /incident/<id>/action route, preserve tenant-local workflow type isolation, avoid duplicate tenant settings fixtures, and check rejected import rollback via its actual error response.
- Corrected audit retention fixture to use current timestamps rather than 26-year-old rows intentionally eligible for purging.
- Distinguished table-of-contents continuation from orphaned headings in the PDF regression test.
- Targeted previously failing cases: 18 passed (parameterized cases included). Additional screenshot/documentation/catalog tests: 144 passed, 51 subtests passed. Offline release verifier PASS.
- Full pytest run did not complete in the available runtime; PostgreSQL, CI browser capture, SCA, Trivy, and production approval remain outstanding.

No CI-clean or production claim is made.

## 0.10.0-1 RC11: PostgreSQL CI hang diagnostics

The preceding CI run collected 22 PostgreSQL-marked tests, then produced no test progress for about 38 minutes before cancellation. The documentation screenshot job passed. RC11 bounds the PostgreSQL test runner to 900 seconds by default, emits test names and Python stack dumps on stalls, applies database query/lock timeouts, and captures PostgreSQL activity and logs on failure. These are diagnostics and bounded-failure protections, **not evidence that the underlying database hang is fixed**. The real PostgreSQL suite must be rerun to identify and repair its cause. The local environment did not have Flask or a PostgreSQL Docker service available to reproduce the hang. The RC10 commit was confirmed by the user; RC11 changes are not yet committed.


## RC12 — PostgreSQL self-lock fix

The PostgreSQL orphan-ownership test previously read expired ORM IDs after commit,
implicitly beginning a new SQLAlchemy session transaction. Its ACCESS SHARE lock
blocked the subsequent ALTER TABLE ACCESS EXCLUSIVE lock on a second connection.
The test now removes that session after capturing IDs and before DDL; the
PostgreSQL diagnostics additionally print pg_blocking_pids(). This is a targeted
fix based on the captured traceback, not a claim that the full PostgreSQL gate
was rerun locally. RC11 remains unconfirmed as committed; commit text must be
cumulative from the last confirmed RC10.

## RC13 production-security review checkpoint

- Trivy gate now scans both architectures and returns failure if either scan or policy evaluation fails; no bypass of expired acceptance.
- `scripts/summarize_trivy_findings.py` produces a normalized, non-approving findings inventory. Historical amd64 evidence and review procedure are in `docs/security-evidence/`.
- Runtime LibreOffice dependency retained because `app/form_generation.py` uses it. No speculative package removal or risk-acceptance renewal.
- Candidate requires updated real amd64/arm64 Trivy scans and human disposition before production promotion.


## RC14 — documentation restructure and production security evidence

README.md and README_en.md now introduce the application, features and deployment. Their prior complete contents are archived under docs/DEVELOPMENT_HISTORY_README_IT.md and docs/DEVELOPMENT_HISTORY_README_EN.md. Both Trivy architecture reports are summarized in docs/PRODUCTION_SECURITY_REVIEW_RC14.md. Production remains blocked; risk acceptance was not renewed. Last user-confirmed commit and merge: RC13.


## RC15: temporary security-only CI

A feature-branch/PR commit containing `[ci-security]` selects local-image Trivy checks on amd64 and arm64 and skips costly full CI jobs for that ref only. Main and tags always run the original full pipeline. No publishing, risk acceptance renewal, or promotion. See `docs/CI_SECURITY_FAST.md`. RC13 remains the last user-confirmed commit; RC14 README restructuring is included cumulatively.


## RC16 security automation

Permanent ci-security diagnostic (no temporary suffix), weekly source-image scans on main, existing Monday immutable production review, and actionable idempotent GitHub Issues alerts. No automatic risk acceptance or production promotion. Baseline committed RC13; RC14/RC15/RC16 remain cumulative and uncommitted until confirmed.


## RC17 security triage (uncommitted; last confirmed commit RC13)

Preserve all functionality. Reviewed the supplied amd64/arm64 Trivy report and created `docs/TRIVY_RC17_RISK_REVIEW.md` and `docs/TRIVY_RC17_REVIEW_MATRIX.csv`. No production approval, policy renewal or package removal was performed. RC14–RC17 remain cumulative changes since RC13.


## RC18 — evidence-only Trivy disposition

Cumulative from RC17 (committed on a feature branch, not merged). Added reproducible amd64/arm64 report comparison and per-package evidence matrix, with no automatic risk approval. All functionality preserved; production gate remains blocked. See docs/TRIVY_RC18_REMEDIATION_DECISION.md.


## RC19 security-only diagnostics

Added Debian package candidate/reverse-dependency evidence to the permanent `[ci-security]` workflow on both platforms, plus a JSON summarizer and RC19 risk-decision note. No runtime packages or risk acceptance changed. Last confirmed commit: RC17 on development branch; RC18 not confirmed committed. Production remains blocked.


## RC19 security-only diagnostics

Added Debian package candidate/reverse-dependency evidence to the permanent `[ci-security]` workflow on both platforms, plus a JSON summarizer and RC19 risk-decision note. No runtime packages or risk acceptance changed. Last confirmed commit: RC17 on development branch; RC18 not confirmed committed. Production remains blocked.


## 0.10.0-1 RC20 — security diagnostics repair

Latest [ci-security] run 45178795238 collected Trivy for both architectures (78 HIGH, 1 CRITICAL each), but Debian evidence was incomplete: `/bin/sh: Package: parameter not set` at the `dpkg-query -f` format. RC20 escapes the literal dpkg format variables, validates all three expected outputs and marks incomplete evidence explicitly in the summary. No runtime changes, risk acceptance updates, or promotion. Last confirmed Git commit is RC17; RC18 and RC19 remain unconfirmed as commits.


## RC21 - Debian APT evidence review

Both platform inventories from security-only run 45186139811 are complete. Installed and candidate versions match for nine priority Debian packages on both architectures. Added docs/TRIVY_RC21_APT_DECISION.md and CSV evidence. No runtime, security gate or risk acceptance changes; production remains blocked. The last confirmed Git commit is RC17 on the security branch; RC18-21 are not confirmed committed.


## RC22 — refreshed multiarch security evidence

CI run 45200319586: amd64 and arm64 each 81 HIGH, 1 CRITICAL, 33 unique CVEs, complete APT evidence, no Trivy FixedVersion. Added `TRIVY_RC22_EVIDENCE.csv`, `.json` and `TRIVY_RC22_RISK_DECISION.md`; risk acceptance unchanged and production remains blocked. Last confirmed Git commit: RC17 security branch (RC18–RC21 commit status not confirmed).


## RC23 — evidence-based Trivy applicability review

Added `docs/TRIVY_RC23_FORMAL_REVIEW.md`, `docs/TRIVY_RC23_DECISION_REGISTER.csv`, and `docs/TRIVY_RC23_DECISION_SUMMARY.json`, comparing the latest dual-architecture Trivy findings with the expired historical acceptance. All decisions remain NOT_APPROVED; no application behavior, Dockerfile, gate, or acceptance changed. RC17 is the last confirmed branch commit; RC18–RC23 remain cumulative unless the user confirms newer commits.

RC24: security CI hotfix: invoke Trivy gate with bash in fast, release and scheduled workflows; restore executable ZIP mode; preserve all security policy and runtime behavior. The 45216896624 run did not scan either architecture (exit 126); its empty reports are not vulnerability evidence.


## 0.10.0-1 RC25 — Trivy scanner and risk review

Pinned Trivy v0.76.2 in ci-security-fast, ci-release and security-review; SHA-pinned setup action unchanged. Latest supplied CI run 45221043225: 81 HIGH + 1 CRITICAL per architecture, 33 unique CVEs, no FixedVersion. `docs/TRIVY_RC25_DECISION_MATRIX.csv` and `docs/TRIVY_RC25_REVIEW.md` are evidence for review only. No risk acceptance, runtime dependencies or production gate were relaxed. RC17 is the last user-confirmed branch commit; later commits have not been confirmed.


## RC26 security review

RC25 remains the source baseline. Run 45224547175 shows 81 HIGH + 1 CRITICAL and 33 distinct CVEs on each architecture. Added formal unapproved review register and procedure. No risk acceptance or runtime change; production remains blocked.


## RC27 security decision register

The 2026-11-23 run 45227508842 produced matching 82 HIGH/CRITICAL package findings per architecture (81 HIGH, 1 CRITICAL; 33 distinct CVEs). RC27 adds a review register and a HOLD decision guide. It does not modify the runtime, acceptance policy or gate; the last confirmed commit remains RC17 on the security branch unless the user confirms otherwise.


## RC28 — 14-day risk review proposal

The user authorized preparing a 14-day assessment, not unconditional CVE approval. The RC28 package adds an exact 33-CVE proposed decision register and approval checklist. The historical risk acceptance and production gate are unchanged; no image was promoted. Last user-confirmed Git commit is RC17 on a development branch.


## RC29 — PR regression fixes after committed RC28

The full PR suite identified 11 regressions caused by tests assuming README release history, earlier workflow layout and missing executable bits. RC29 updates tests to follow the archived historical READMEs, preserves the permanent security-only workflow and issue notifier, fixes archived Markdown relative links, and restores executable permissions on the entrypoint and release packager. Full CI must be rerun before merge. No Trivy risk acceptance or production policy has been relaxed.


## RC30 - PostgreSQL CI permission fix

The RC29 PR run passed 958 application tests and the documentation pipeline but failed before PostgreSQL tests because `scripts/run_postgres_tests.sh` lacked its executable Git mode. RC30 restores mode 100755 and invokes the script through bash in ci-release.yml. This fixes only the execution error; the 22 PostgreSQL tests must be rerun in GitHub Actions. Last confirmed commit: RC29 on PR branch.


## RC31 — CI SCA executable permission hardening

The PR after RC30 passed the application suite, PostgreSQL and browser documentation, but failed with exit 126 invoking `scripts/run_sca.sh`. RC31 restores executable mode for `run_sca.sh` and `verify_production_release.sh`, invokes them via `bash` in release and periodic security workflows, and likewise protects packaging invocations. Focused workflow regressions: 28 passed, 8 subtests; offline release verifier PASS. Production promotion is still subject to Trivy and explicit risk acceptance. Last confirmed commit: RC30 (user reported a subsequent PR failure).


## RC32 — formal 14-day risk proposal

Added a non-operative, exact-package/version-scoped draft for 33 CVEs across both architectures from CI run 45227508842, with a per-finding approval matrix. The expired active policy is unchanged. Authorized risk-owner approval, exposure evidence, full production gates and digest promotion remain pending. RC31 is the latest user-confirmed merged baseline.


## RC33 conditional risk acceptance (2026-11-23)

RC32 was committed and merged per user confirmation. RC33 activates an explicitly scoped 14-day Debian residual-risk decision expiring 2026-12-07, limited to 33 CVEs and exact reviewed package versions. Both historical Trivy JSON reports are used as regression inputs; production remains gated by new CI, SCA, both architecture scans, and immutable digest. No application functionality removed.

## 0.10.0-1 RC34 — legacy notification kind repair

Production RC33 bootstrap failed when legacy notification templates used `kind=notifica_interna` but their tenant had only the canonical `NotificationType(code=internal)`. RC34 adds `app/legacy_notification_migration.py` and invokes it before Tenants Default initial seeding, inside the existing serialized bootstrap transaction. The only recognized alias is `notifica_interna -> internal`, and only if the tenant has `internal` and does not have an explicit custom `notifica_interna` type. A target-name collision or absent canonical type fails closed; no arbitrary type is synthesized. The operation changes only `NotificationTemplate.kind`, never body, subject, recipients, action label, or other fields. It is idempotent, never commits, and rolls back with the bootstrap transaction on any later exception. Unknown legacy cases still require explicit review. Do not manually patch production data before testing this release. Note: PostgreSQL DDL in older schema migration callbacks may have independent transaction boundaries; the guarantee here covers the new notification data normalization and bootstrap session, not an unconditional whole-database snapshot restore.

Local verification: 80 focused tests passed (including 5 new RC34 regression tests). Real production PostgreSQL startup and full CI still required. Last user-confirmed commit is RC33; use full CI, not `[ci-security]`.


## RC35: publish verified UI documentation after production promotion

On a production-impacting merge to main, the same-run verified manuals, brochures, training PowerPoint and real screenshots are staged with the promoted immutable digest in a protected-main PR. The PR is generated only after the image passes all gates and is promoted. A metadata/documentation-only merge is excluded from the Docker rebuild loop. No direct push to protected main; PR checks are explicitly dispatched. The repository content is not updated until the generated PR is reviewed and merged.


## RC36 — CI documentation publication regression

Updated the historical production metadata PR test to validate the renamed production digest **and documentation** PR step, the documentation publication verifier, and the exact staged screenshot/manual/presentation paths. No runtime or security policy changes. CI full suite remains required.

## 0.10.0-1 RC37 — documentation CI regression repair

- Fixed three tests from the 2026-11-24 GitHub PR run (960 passed, 3 failed, 24 skipped).
- Source presentation media are now checked against the immutable source receipt and approved local assets; the embedded manual preview bytes are verified against the receipt, not unconditionally against potentially regenerated first-page PNG files.
- Installed CI documentation continues to require the complete validated screenshot, manual and presentation provenance chain via `validate_installed_documentation`.
- Educational laboratory tests distinguish source placeholder pages from validated CI-generated pages; CI pages must not contain the pending-acquisition placeholder.
- Source packaging tests use an isolated source-only fixture. Actual release packaging still rejects installed documentation from another build or with invalid checksums.
- Local focused regression: 77 passed and 52 subtests passed. Full GitHub CI, PostgreSQL and real browser evidence still require a new run.
- Last user-confirmed Git commit: RC33. RC34–RC37 commit message remains cumulative unless a later commit is confirmed.


## RC38 — documentation regression isolation

The source-package test now compares staged source-only evidence against the staged fixture, not the original checkout. Training tests independently verify PPTX hashes and embedded media against presentation receipts even when the application CI job regenerates brochures for its current BUILD. The strict whole-bundle validator remains mandatory in the real-screenshot documentation job and distribution packaging; checksum mismatches are not suppressed there.

## RC39: generalized legacy PDF template cleanup

Before Tenants Default initial seeding, `app/legacy_template_cleanup.py` transactionally removes only missing-PDF form configurations without operational references, along with their internal field mappings, and writes an audit event. Referenced configurations are preserved with a warning. The rule is not tied to a filename. No filesystem deletions or independent commits. See `docs/LEGACY_DATA_CLEANUP.md`. Five dedicated tests cover deletion, audit, rollback, reference preservation and idempotency. Real PostgreSQL bootstrap and full CI are still required.
\n\n## RC40 — Legacy SVG and CI packaging\nSafe in-memory removal of inert SVG editor metadata during defaults export; strict SVG validation remains on import and on normalized export. Source-only packaging smoke now removes stale installed documentation receipts from its staging copy; distribution packaging remains strict. PostgreSQL bootstrap transaction and PVC originals are unchanged.\n

## RC41 — Legacy RDF title SVG compatibility

RC40 rejected an otherwise inert editor metadata `<title>` inside RDF/Work in the real INFN SSO SVG. RC41 allows this inert metadata element solely inside removable metadata containers, retains strict rejection of active content, and adds positive/negative regression tests. The original PVC asset remains unchanged. Full CI and the real Kubernetes bootstrap remain pending.


## RC42: static SVG style migration
Legacy SSO SVG logos with strictly validated inline `fill` and `fill-opacity` are normalized to SVG presentation attributes in memory. Arbitrary CSS, active content and external references remain rejected. No PVC writes or DB changes. Real INFN logo bytes not available for local test; verify on Kubernetes before rollout.


## RC43 – login, navigazione e presentazione estesa

Nuovo login semplificato con logo organizzazione centrato e footer versione/build, badge rossi sui contatori, pulsanti torna-su in flow senza sovrapposizioni, fonte didattica estesa a 58 slide. La presentazione estesa è un artefatto sorgente editabile: le screenshot reali devono ancora essere generate e attestate dalla CI. L’export workflow richiesto non è disponibile nella sessione e l’esempio è indicato come illustrativo.


## RC46 — formazione SPAM e governance tenant

Presentazione editabile a 80 slide: flusso SPAM a 13 step, import da Tenants Default, stati current/obsolete, parametri globali/condivisi/locali e limiti espliciti delle screenshot. La cattura browser reale del caso SPAM è **ancora da implementare e attestare**; le immagini esistenti non vanno etichettate come catture SPAM.


## RC52 — 2026-11-24
Idempotent SPAM category seeding; 19 capture IDs and corresponding source training slides; regenerated source presentation and provenance receipt; corrected release layout. Browser capture must still be executed in CI.

## RC56 — formazione visuale / JPEG / mapping + Alfresco
77 slide PPTX/PDF ottimizzate; screenshot CI JPEG q90 con validazione mista PNG/JPEG; nuova fixture offline con PDF AcroForm compilabile e configurazione Alfresco per tre nuove catture browser obbligatorie. Nuova CI completa necessaria.

## RC67 - Documentation presentation CI screenshot precedence

CI job `Real UI screenshots and documentation` failed during `verify_visual_training_rc64.py --require-ci-images` in the PR run from `logs_123409526558.zip`: `Screenshot CI non incorporata nel PPTX: spam-incident-config-labels`. The screenshot had already been acquired successfully. The generator inserted slide 70's pinned editorial `photo_art` first and returned before considering the authenticated screenshot. Updated `scripts/build_training_visual_rc64.js` to prioritize the verified `spam-incident-config-labels` on slide 70 and preserve the synthetic illustration as the no-CI fallback. Updated the QA verifier to require the screenshot hash in media actually referenced by slide 70. Added `tests/test_visual_training_rc67.py` with disposable image fixtures, a valid build/verify cycle, and a PPTX tampering rejection. Local documentation regression: 82 tests + 48 subtests passed; full Flask suite and GitHub CI not run here. The RC64 editorial PowerPoint/PDF remain unchanged; CI-generated PPTX/PDF will include the current real screenshot.

## RC68 - Visual PowerPoint provenance gate (2026-11-25)

The PR log `logs_123419120702.zip` showed the application/PostgreSQL jobs passed,
and the browser documentation job built 79 slides, but final QA rejected 11
PowerPoint media hashes. RC67's verifier had allowlisted only the six mandatory
browser screenshots even though the deck embeds additional captures from the
same validated manifest. RC68 extends byte-level provenance checking to all
manifest rows, preserves the slide 70 relationship test and rejects untracked
media. Added `tests/test_visual_training_rc68.py`; see
`docs/RC68_VISUAL_TRAINING_MEDIA_PROVENANCE.md`. Complete GitHub CI is not run
in this environment; do not mark the PR green until rerun.

### RC71 — Modular architecture and general workflow manager training (2026-11-25)
The 87-slide didactic deck expands CIR on the cover, clarifies modular architecture, registers AlBot and Alfresco as the currently implemented optional plugins, explains configurable cross-step/global checks and deadline/reminder scheduling, and distinguishes global super-admin authority from tenant-admin scope. Original people-free synthetic art and editable vector diagrams are audited by SHA-256. No application runtime behavior changed. Source: docs/presentation/RC71_MODULAR_ARCHITECTURE_TRAINING.md.

### RC72 - GitHub CI plugin inventory test fix (2026-11-25)

A PR based on the RC71 cumulative source failed only
`test_available_plugins_not_confused_with_core_features`: Python generated a
`__pycache__` directory under `app/plugins`, which the test's unfiltered
folder enumeration treated as an extra plugin. The test now requires a plugin
package `__init__.py` and has a regression with a real cache folder and a
new dummy plugin package. All other application code and the 87-slide/PDF
training assets are unchanged. See `docs/RC72_CI_PLUGIN_DISCOVERY.md`. The RC72 commit and PR merge were confirmed with green CI. RC73 development starts from that baseline.

### RC73 — Current-only GitHub training files and complete screenshot publication (2026-11-25)

GitHub no longer accumulates version-suffixed `CIR_Operational_Training_Visual_RCxx` PowerPoints/PDFs or their obsolete render directories. The canonical `CIR_Operational_Training_Visual.pptx` and `.pdf` are the only visual teaching artifacts; the editable `CIR_Operational_Training_IT.pptx` is also retained. Authoring provenance JSON, verified synthetic artwork and actual manuals remain intact.

The same-run browser manifest supplies every capture to an editable appendix in the visual presentation. The CI verifies all image bytes with SHA-256 and exact slide relationships, then renders the PDF and checks the resulting appendix pages against the original screenshots. The operational PPTX already embeds all required browser captures; the post-build publication verifier independently checks that each is referenced by an actual slide.

The documentation PR is now a separate successful-main job, and runs even if the production Docker job is skipped. A changed-source policy suppresses repetition when the prior generated-documentation PR is merged. The PR uses a verified same-run receipt, normalized stable filenames and staged deletions. This keeps the existing protected branch and PR review process rather than silently pushing to main. Local editorial snapshot: 87 slides/87 PDF pages; an actual CI run with 25 screenshots generates 112 slides/pages. Remote workflow validation remains pending.


RC74: see docs/RC74_SCREENSHOT_REGENERATION_AND_REVIEW.md for all screenshot captures, mandatory focused training-slide evidence, and the automatic/manual documentation publication workflow.


RC75: training uses plain-language risk-to-rights-and-freedoms wording, links the current CI-regenerated PDF, clarifies Continuous Improvement and AlBot/Alex, and restores the existing cartoon avatar in the modern UI. See `docs/RC75_TRAINING_TEXT_AND_AVATAR.md`.

RC75: training now documents the tenant configuration Wizard (Admin menu), accessible to tenant administrators and super administrators with server-enforced privilege separation.


RC76 documentation update: manual and template incident creation now explicitly selects the workflow through the first category, with tenant-default fallback. The Tutorial/SPAM lab slide explains importing SPAM from Tenants Default and putting SPAM first before creating the incident. CI must link verified `spam-incident-config-labels` evidence to both the lab-opening slide 70 and the category slide 78; current documents stay at stable filenames, with 87 editorial slides plus the same-run browser appendix. No application runtime change.


RC77 catalog import: the workflow name and category name form an identical independent scope (`SPAM`, `SPAM v2`, ...); existing tenant severities, including inherited replicas, are reused by name without overwrites. Navigation labels are standardized to Workflow incidenti. Existing installed copies are unchanged. See `docs/RC77_CATALOG_WORKFLOW_NAMES.md`. Full Flask and PostgreSQL CI tests remain mandatory.

RC77 tenant-cloning correction: clone configuration without source workflow definitions; seed exactly one independent three-step generic default. Administrators install specific workflows from the catalog afterward. Workflow selectors distinguish existing step-bearing scopes from categories without workflow definitions. Full Flask/database CI regression remains to be run.

RC77 training onboarding: clarify manual/Wizard setup, subsequent mandatory catalog imports for tenant-specific procedures, and the single usable generic default workflow; updated source slides 35/37/42 and generated PowerPoint/PDF.

RC77 visual architecture: add synthetic people-free photographic architecture illustration and editable platform diagrams; regenerate the 88-slide PowerPoint/PDF and update screenshot gallery numbering/provenance gates.

## RC78 (2026-11-26) - notification-template inheritance and bulk administration

New admin page `/notifiche/template/gestisci` appears under the Notifications menu for tenant admins/superusers in classic and modern navigation. It supports atomic multi-delete with safeguards against cross-tenant IDs, malformed selections, referenced templates and missing privileges; the action emits `admin:notification_template_bulk_delete`. Operational tenant overrides have priority over shared defaults. Removing the override restores the shared template if it exists. Built-in notification examples are now seeded once per tenant, so administrative deletion is not undone by the next page load. Actual Flask UI integration, PostgreSQL tests and GitHub Actions remain to be run. See `docs/RC78_NOTIFICATION_TEMPLATES.md`.

## RC80 - notification type retirement and tenant overrides

Removing a notification type from `Tenants Default` retires the inherited pristine and unused type/templates. **Tenant-customized types are retained unconditionally**, even without incident usage, together with their associated templates; tenant-customized templates and historically used notification types/templates are retained as well. A new shared type is propagated transactionally to existing tenants. The natural keys and provenance snapshots remain tenant-scoped. See `docs/RC80_NOTIFICATION_TYPE_RETIREMENT.md` and the RC80 isolated/full CI tests.
