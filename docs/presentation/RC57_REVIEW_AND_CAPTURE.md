# RC57 — Revisione del materiale didattico e categorie ereditate

- Presentazione visiva in italiano: 79 slide (77 di RC56, meno le due dedicate alla UI classica, più 4 nuove slide).
- Sono state uniformate terminologia, accenti, apostrofi, titoli di workflow, ruolo degli amministratori, tenant, notifiche, PDF AcroForm, Alfresco, AlBot e le 13 fasi del caso SPAM.
- Le schermate già presenti provengono dal run CI `919b027403ee55db05b2355cd2f8fbd09c7cf7b4` (fixture con dati sintetici). Il PDF e il PPTX RC57 sono distribuiti come materiali editoriali: non devono essere dichiarati screenshot di una build RC57 non ancora verificata.
- Nuovi screenshot obbligatori nella prossima CI: `registry-closed-state` e `pdf-generated-preview`, oltre ai tre nuovi screenshot introdotti in RC56 (`pdf-mapping-configuration`, `alfresco-settings-desktop`, `alfresco-incident-documents`); 24 in totale.
- La cattura `pdf-generated-preview` deve eseguire la vera generazione AcroForm, verificare il PDF e fotografare la vera schermata di anteprima, non un mockup.
- Import e provenance delle categorie: una categoria locale e una replica omonima da Tenants Default restano due record indipendenti con riferimenti storici immutati. Nel picker incidente ne viene mostrata una sola con indicazione della provenienza. La selezione privilegia workflow configurati, quindi la categoria locale se entrambe le versioni sono operative.
- Le installazioni ripetute dal catalogo workflow rimangono copie indipendenti per progettazione. Non vengono modificate né eliminate automaticamente le loro dipendenze. Evitare import ripetuti non necessari.
- La fixture dei sei incidenti ora completa le azioni workflow dei due incidenti chiusi, affinché la CI possa verificare le vere icone verdi ✓ contro gli avvisi ⚠.
- Le screenshot non ancora esistenti sono rappresentate nella versione editoriale da **schemi esplicitamente etichettati**, non screenshot sintetici spacciati per reali.

## Ricostruzione della presentazione visiva

Con Node.js, installare `pptxgenjs@4.0.0` e `image-size@1.2.0`, poi eseguire dalla root:

```sh
node scripts/build_training_visual_rc57.js docs/presentation/CIR_Operational_Training_Visual_RC57.pptx
```

Per utilizzare lo ZIP delle vere screenshot CI acquisite in un run successivo, impostare `CIR_SCREENSHOT_MANIFEST=/path/to/manifest.json`: il generatore controlla gli SHA-256 e sostituisce automaticamente le immagini corrispondenti. Gli asset editoriali sono in `docs/presentation/visual_rc57_media/`, la fonte editabile in `docs/presentation/visual_rc57_spec.json`.

Il PDF didattico si genera convertendo il PPTX con LibreOffice/Impress e deve essere verificato visivamente.

## Verifiche ancora richieste

- CI completa con Flask/Chromium/PostgreSQL e nuovo contratto a 24 immagini;
- Acquisizione effettiva icone ✓, mapping PDF, anteprima del PDF generato e schermate Alfresco;
- Validazione di browser, ruoli e tenant per la scelta deduplicata.
