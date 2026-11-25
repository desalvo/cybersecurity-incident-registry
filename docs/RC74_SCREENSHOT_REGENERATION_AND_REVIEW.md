# CIR RC74 — Screenshot, presentazioni e pubblicazione su `main`

La pipeline genera sempre, nella **stessa esecuzione**, le schermate dell’applicazione reale con dati sintetici isolati, il PowerPoint operativo, il PowerPoint didattico e il PDF visuale. Non riutilizza screenshot di un altro commit come nuove evidenze.

## Trigger automatici e manuali

- `pull_request`: test e generazione degli artefatti verificati prima del merge.
- `push` su `main` dopo modifiche ad applicazione, workflow, generatori, specifiche delle slide, documentazione sorgente o workflow CI: rigenerazione, controllo e apertura automatica della PR che installa solo i documenti correnti. La pubblicazione non richiede una nuova immagine Docker quando il cambiamento è documentale.
- `workflow_dispatch` sul branch `main`: rigenerazione forzata, senza build Docker non necessarie; utile quando si vuole rinnovare le schermate dopo modifiche ambientali, o semplicemente richiedere un nuovo set di evidenze.
- Merge della PR automatica di soli documenti generati: non apre un’altra PR identica (prevenzione del loop); non cambia i sorgenti della presentazione.

**Attenzione:** su repository con branch `main` protetto, la PR automatica va **approvata e integrata** per aggiornare i file presenti nel branch. La generazione riuscita come GitHub Actions artifact, da sola, non modifica `main`.

## Schermate aggiunte

1. `statistics-desktop`: pagina reale `/reports/stats`, prima scheda statistiche con indicatori e grafici del tenant sintetico.
2. `workflow-steps-focused`: scheda autentica del workflow SPAM con viewport ridotta a 1100 px, che mostra meno card contemporaneamente e le rende più leggibili nella slide 54.
3. `assistant-panel-closeup`: pannello AlBot reale acquisito come elemento del DOM, con risposta del provider locale di prova. La slide 67 usa anche l’avatar ufficiale proveniente dall’asset applicativo `app/static/ai-chatbot/albot-avatar.png`.

La pipeline rifiuta mancata acquisizione, cambiamenti di hash SHA-256, screenshot mancanti nelle slide focalizzate, screenshot mancanti in qualsiasi pagina dell’appendice dei due PowerPoint o screenshot non visibili nel PDF. Ogni screenshot viene associata a source commit/version/build.

## Classificazione e workflow

CIR applica il workflow associato alla **prima categoria** dell’incidente, se esiste; altrimenti quello predefinito del tenant. L’aggiunta di più categorie non unisce automaticamente i workflow delle diverse categorie: vedere `app/workflow_lifecycle.py::workflow_scope_for_categories`. La classificazione generale estesa di categorie/gravità è in fase di definizione: non viene presentata come funzione già rilasciata.

## Limiti della verifica locale

L’export editoriale offline dispone di 87 slide e 87 pagine, ma **non** contiene le nuove catture browser dell’esecuzione GitHub. La versione pubblicata da CI aggiunge una pagina per ogni cattura autentica (attualmente previste 28), ed è l’unica versione che può ottenere la verifica `--require-ci-images` e il sigillo di provenienza.
