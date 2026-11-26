# CIR 0.10.0-1 RC83 — leggibilità screenshot e pubblicazione CI

## Motivazione e provenienza

Il pacchetto sorgente recuperato è RC82. Le 88 slide del PowerPoint editoriale mostrano anche i ritagli
ingranditi delle catture storiche presenti negli asset help, ma non dimostrano, da sole, una cattura nel run GitHub corrente; gli asset del
repository possono contenere evidenze storiche autentiche, ma **non devono essere
spacciati per screenshot nuove della CI**. La versione che fa fede è costruita
in `ui-documentation` con il manifest Chromium e i rispettivi SHA-256,
source commit e build, verificati e pubblicati da un'altra PR. In
modalità CI rigorosa sono ammessi esclusivamente manifest
`real-application-browser` con provenienza `isolated-synthetic-fixture`.

## Modifiche RC83

1. Il generatore PptxGenJS privilegia, per le slide con capture disponibili,
   l'immagine del medesimo run rispetto a una fotografia tematica o uno schema.
   Il riquadro mostra una miniatura del contesto, un bordo sul punto d'interesse,
   un collegamento visivo e un vero ritaglio PowerPoint ingrandito. Le regioni
   di fuoco sono per identificativo (`CI_FOCUS`); non vengono inventati pixel.
2. Lo zoom è realizzato tramite crop nativo della stessa immagine già verificata:
   il PDF e il PowerPoint conservano la schermata sorgente originale senza
   modifiche ai byte. La variante senza toolkit locale usa le medesime regole
   di crop, anziché deformare l'immagine. Il verificatore CI richiede sia la
   visione originale sia un crop reale della stessa sorgente nelle slide
   didattiche focalizzate del Wizard, del workflow, delle statistiche e di AlBot.
3. I testi visibili dell'edizione editoriale non promettono più una cattura
   nella «prossima CI». Dove non esiste un manifest verificato, un esempio storico resta
   etichettato «evidenza storica» e uno schema «non è una schermata».
4. Il workflow pubblica un risultato esplicito (`pr-opened` o
   `already-current`), e un nuovo job di accountability in `always()` fallisce
   se la documentazione era richiesta ma il job di pubblicazione è stato
   saltato, non è riuscito oppure non ha dichiarato un risultato valido.
5. La PR rimane un passaggio necessario: un artifact CI allegato al run non
   equivale a un commit su `main`. La policy evita la ricorsione per i soli
   file generati; un cambiamento ai generatori avvia invece la pubblicazione.

## Sequenza operativa in GitHub dopo il merge

- Avviare `ci-release.yml` su `main` mediante push o `workflow_dispatch`.
- Accertare che `ui-documentation` produca screenshot browser reali ed entrambi
  i PPTX; il deck visuale deve superare `--require-ci-images` e il verificatore
  PDF delle immagini catturate.
- Controllare `documentation-publication` e
  `documentation-publication-accountability`: il primo deve generare una PR
  oppure dichiarare `already-current`, il secondo non deve essere saltato.
- Se la PR fallisce per autorizzazione, verificare **Settings → Actions →
  General → Workflow permissions → Allow GitHub Actions to create and approve
  pull requests** e la policy del token del repository.
- Dopo la revisione, eseguire il merge della PR documentale. La CI del merge
  che contiene solo file autogenerati non deve aprire PR ricorsive.

## Verifiche e limiti

La verifica offline prova sintassi Python/JS, generazione dell'edizione
editoriale (88 slide), validazione dello ZIP PowerPoint e assenza di overflow,
oltre a esportazione PDF (88 pagine) e controlli visuali su callout workflow e AlBot,
con test separati per il collegamento al ritaglio originale. L'anteprima
editoriale **non costituisce un'evidenza della CI più recente**: soltanto il
run GitHub autorizzato può legare il manifest al commit effettivo e produrre
la versione definitiva. La connessione GitHub non è disponibile nel presente
ambiente: nessuna PR remota viene dichiarata creata da RC83.
