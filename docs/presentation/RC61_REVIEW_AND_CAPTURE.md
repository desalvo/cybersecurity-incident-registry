# CIR 0.10.0-1 RC61 — aggiornamenti didattici e deduplicazione dati

## Materiale di formazione

- `CIR_Operational_Training_Visual_RC61.pptx`: 79 slide modificabili; PDF omonimo a 79 pagine.
- Contenuti editabili: `visual_rc61_spec.json`; builder: `scripts/build_training_visual_rc61.js` con PptxGenJS 4.0.0.
- Le slide **3-7, 28-33, 35, 39-44, 73 e 75-79** hanno 24 illustrazioni diverse a destra, con sfondo fotografico sintetico e grafica tematica specifica (nessuna fotografia stock o screenshot simulata).
- La slide **21** mostra la barra applicativa con l'azione «Report PDF» e due pagine leggibili di un report **sintetico esplicitamente dimostrativo**. Non è l'output reale di una richiesta effettuata nella CI.
- Slide **34**: mapping AcroForm↔dati dell'incidente mediante drag & drop durante la configurazione amministrativa, con esempi `RIFERIMENTO`/`DATA_INIZIO`.
- Slide **39**: la categoria SPAM, lo step Blocco account, le condizioni e le dipendenze sono un **esempio interamente configurabile**. Slide **44 e 47**: anticipazione del caso SPAM, approfondito in seguito.
- Slide **55**: spiega chiaramente la differenza tra configurazione Alfresco da parte dell'admin e impiego nella sezione Documenti da parte degli utenti autorizzati.
- Slide **70**: rimosso il vecchio ritaglio con scelte duplicate. Nell'edizione editoriale è presente un'illustrazione **concettuale**, non una screenshot ritoccata; durante la CI viene sostituita con la screenshot Chromium autentica `spam-incident-config-labels` dal tenant di prova.
- I file sotto `visual_rc61_art/` e `provenance.json` tracciano immagini sintetiche, esempio di report e hash degli asset. `scripts/generate_training_rc61_art.py` riproduce le composizioni da una base grafica locale già approvata.

## Fix applicativo «Tenants Default»

- La riconciliazione transazionale di una label condivisa equivalente a una già locale ora riguarda **`category` e `data_type`**. Mantiene l'ID locale, i campi personalizzati e le associazioni già esistenti.
- `incident_config_label_choices` restituisce un solo elemento per nome logico nella palette del tenant e mostra la provenienza. Le vecchie etichette con suffisso `[Tenants Default]` sono consolidate solo nelle scelte quando esiste la corrispondente base, senza eliminazione implicita di record in uso.
- La UI `dnd_fields.html` mostra nome normalizzato e provenienza anche per «Dati interessati disponibili».
- Non viene imposto un merge distruttivo degli incidenti, dei workflow o delle condizioni contenenti riferimenti a vecchi ID; il restore legacy introdotto in precedenza resta valido e va verificato in PostgreSQL.

## Evidenze reali della CI

- `scripts/seed_ui_documentation.py` inserisce intenzionalmente due label legacy con suffisso `[Tenants Default]` nel tenant sintetico (categoria SPAM, dato «E-mail didattica»).
- `scripts/capture_ui_screenshots.py` rifiuta eventuali nomi logici duplicati in **entrambe** le palette e genera una screenshot dell'area con i controlli realmente visualizzati dal browser.
- `scripts/ui_documentation_evidence.py`, `content_it.json`, il builder della presentazione breve, l'elenco delle screenshot obbligatorie e il gate dei 79 slide sono stati allineati a **25 screenshot obbligatorie**.
- `scripts/verify_visual_training_rc61.py --require-ci-images` richiede sei evidenze reali, compresa quella per la slide 70, e verifica gli hash SHA-256 incorporati nel PPTX.

## QA locale (non equivale a una CI verde)

- 50 test di presentazione/evidenza/screenshot **superati**, con 7 subtest; builder 79 slide, PDF 79 pagine, controlli fuori margine superati.
- Compilazione Python e verifica del media consentito effettuate.
- Da eseguire nella PR: suite applicativa Flask+SQLAlchemy, browser Chromium con server reale, test PostgreSQL e restore di export precedenti a Tenants Default, tutti gli altri job GitHub Actions.
- Non dichiarare una screenshot «reale della RC61» prima della cattura CI con hash verificato.

## Comandi principali

```sh
node scripts/build_training_visual_rc61.js docs/presentation/CIR_Operational_Training_Visual_RC61.pptx
libreoffice --headless --convert-to pdf --outdir docs/presentation docs/presentation/CIR_Operational_Training_Visual_RC61.pptx
python scripts/verify_visual_training_rc61.py --pptx docs/presentation/CIR_Operational_Training_Visual_RC61.pptx --pdf docs/presentation/CIR_Operational_Training_Visual_RC61.pdf
python -m pytest -q tests/test_visual_training_rc61.py tests/test_visual_training_rc58.py tests/test_training_presentation_builder.py tests/test_ui_screenshot_pipeline.py
```

Messaggi Git commit: **sempre in inglese e su una sola linea**. Ultimo commit esplicitamente accertato nelle informazioni recuperate: RC55, SHA non comunicato.
