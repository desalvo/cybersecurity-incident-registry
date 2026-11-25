# CIR 0.10.0-1 RC58 — Training visuale e riconciliazione categorie

## Stato editoriale

- PowerPoint 79 slide: `CIR_Operational_Training_Visual_RC58.pptx`.
- PDF 79 pagine: `CIR_Operational_Training_Visual_RC58.pdf`.
- File sorgente dei contenuti: `visual_rc58_spec.json` (percorsi media portabili).
- Builder JavaScript: `../../scripts/build_training_visual_rc58.js` (PptxGenJS 4.0.0).
- Il media riutilizzato è un sottoinsieme di `visual_rc57_media/`, derivato da
  screenshot browser CIR e grafica applicativa approvata. Il controllo di
  provenienza vieta screenshot dell'interfaccia classica e media esterni.
- La versione editoriale include una schermata vera di «Moduli · Configurazione»
  alla slide di origine 54; la vista dettagliata del mapping dei singoli campi
  attende una nuova acquisizione.
- La nuova CI usa screenshot con dati esclusivamente sintetici e non deve
  includere nominativi reali, credenziali, indirizzi di notifica reali o dati
  personali nelle evidenze.

## Evidenze reali richieste alla CI

Lo script esistente `scripts/capture_ui_screenshots.py` deve completare 24
catture browser autentiche. Cinque sono obbligatorie prima di considerare la
presentazione ricostruita con immagini fresche:

1. `registry-closed-state`: registro con incidenti conclusi e simbolo verde,
   insieme ad altri con avvisi.
2. `pdf-mapping-configuration`: moduli PDF e mapping effettivamente compilato.
3. `pdf-generated-preview`: esecuzione reale della route CIR di generazione
   AcroForm, lettura dei campi del PDF, poi screenshot dell'anteprima vera.
4. `alfresco-settings-desktop`: configurazione Alfresco con valori di fixture
   offline, senza accesso a un repository remoto.
5. `alfresco-incident-documents`: controlli reali nell'area documenti incidente.

Il job `.github/workflows/ci-release.yml` acquisisce i browser screenshot
nel medesimo commit che costruisce PowerPoint/PDF, verifica i loro SHA-256,
incorpora entrambe le schermate Alfresco nella slide di origine 56 e genera
l'evidenza stampabile. La validazione `scripts/verify_visual_training_rc58.py`
rifiuta artefatti privi di una delle cinque catture o contenenti immagini non
approvate; richiede 79 slide e 79 pagine PDF. Copia in repository e packaging
avvengono **dopo** la validazione, senza manomettere le ricevute dei manuali
relativi alla distinta presentazione didattica breve.

## Categorie, import e restore

- Quando esiste già «SPAM» nel tenant, la pubblicazione di «SPAM» in
  `Tenants Default` riconcilia la categoria mediante `TenantDefaultReplica`
  preservando l'ID e i riferimenti locali, anziché replicare `ConfigLabel`.
- Il selettore incidente mostra una sola scelta logica e la provenienza della
  categoria («Locale integrata» oppure «Ereditata da Tenants Default»).
  Anche vecchie categorie con suffisso `[Tenants Default]` vengono collassate
  **solo nell'elenco di scelta** se esiste la voce equivalente; nessuna
  eliminazione di record referenziati è eseguita in modo implicito.
- Se una replica legacy è inutilizzata, il sync può consolidarla sulla categoria
  locale con transazione; in presenza di riferimenti, emette un avviso e non
  cancella gli ID. Il restore di un export con schema precedente continua a
  ricostruire e riconciliare `Tenants Default` (logica introdotta in RC57).
- Le importazioni ripetute volutamente indipendenti dal catalogo dei workflow
  non vengono fuse indiscriminatamente: fonderle cambierebbe le dipendenze
  configurate in modo esplicito dagli amministratori.

## Verifiche eseguite e non eseguite

- PASS: generator PPTX 79 slide, PDF 79 pagine, verifica canvas senza overflow,
  checksum e allowlist dei media incorporati, assenza di UI classica,
  suite editoriale `tests/test_visual_training_rc58.py` (3 test).
- PASS: `python -m compileall` sul routing categorie e test aggiunti;
  controllo di struttura sintattica del workflow YAML.
- NON ESEGUITI qui: suite Flask/SQLAlchemy del database, ripristino PostgreSQL
  dal vivo, Chromium con vera applicazione, e job GitHub Actions esterno.
  Nessuna schermata o risultato CI non acquisito deve essere dichiarato ottenuto.

## Comandi

```sh
npm install --no-save pptxgenjs@4.0.0 image-size@1.2.0
node scripts/build_training_visual_rc58.js docs/presentation/CIR_Operational_Training_Visual_RC58.pptx
libreoffice --headless --convert-to pdf --outdir docs/presentation docs/presentation/CIR_Operational_Training_Visual_RC58.pptx
python scripts/verify_visual_training_rc58.py --pptx docs/presentation/CIR_Operational_Training_Visual_RC58.pptx --pdf docs/presentation/CIR_Operational_Training_Visual_RC58.pdf
```

Con `CIR_SCREENSHOT_MANIFEST` e `CIR_REQUIRE_REAL_SCREENSHOTS=1`, il builder
rifiuta manifest mancanti o diversi dal commit/build di CI; il validatore
`--require-ci-images` controlla l'incorporamento delle cinque immagini reali.
