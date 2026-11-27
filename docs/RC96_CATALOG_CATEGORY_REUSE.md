# RC96 — Importazione workflow su categorie esistenti senza procedura

## Comportamento

In RC95 `_catalog_copy_name()` riservava indiscriminatamente ogni nome di
categoria, anche quando era disponibile una label `SPAM` ereditata da Tenants
Default e priva di workflow. Importando `SPAM` dal catalogo si otteneva quindi
`SPAM v2` e una seconda categoria. Questa non è una collisione di workflow.

In RC96 la destinazione viene risolta nel tenant attivo, dopo la sincronizzazione
ordinaria e la pulizia degli stati vuoti:

- Se la categoria `SPAM` non esiste, il catalogo crea la categoria e il workflow
  con lo stesso nome `SPAM`.
- Se esiste **una sola** categoria `SPAM`, ma non ha step né stato workflow
  specifico, l'importer aggiunge gli step **a quella categoria**, preservandone
  `id`, group, descrizione, configurazione, provenienza e replica di Tenants
  Default. Gli incidenti già classificati con la categoria iniziano quindi
  a utilizzare il workflow associato alla prima categoria.
- Se `SPAM` ha già uno specifico workflow (anche senza record lifecycle legacy),
  una nuova importazione è installata come `SPAM v2`; la versione seguente usa
  `SPAM v3`, e così via. I nomi vengono confrontati senza distinzione di case.
- Un nome con più categorie equivalenti per casefold è ambiguo: non si riutilizza
  nessuna label arbitrariamente. Si sceglie invece il primo suffisso libero.
- Un workflow importato e poi eliminato libera il proprio nome. Le categorie
  create dall'importer sono marcate con group `catalogo workflow` e possono
  essere ripulite in sicurezza. Quelle preesistenti (locali o ereditate) NON
  sono cancellate insieme agli step. Per prudenza, le vecchie categorie
  importate senza marcatore vengono conservate, ma non riservano il nome se
  non hanno più un workflow.

Il confronto del nome considera solo i workflow e le categorie del tenant
operativo di destinazione, non quelli di altri tenant. Le severità continuano
ad avere la propria distinta logica di riutilizzo; gli altri tipi di dipendenza
continuano a seguire le regole di provenienza preesistenti.

## Sicurezza e limiti

Il riutilizzo della categoria ereditata non autorizza a modificarne il nome
come fosse locale. La rinomina di un workflow associato a una label condivisa
resta bloccata dalla regola di immutabilità Tenants Default; una rinomina
richiede un percorso esplicito di distacco dalla label condivisa.

Non sono richieste migrazioni del database. Le ricevute di importazione
rimangono immutabili e continuano a registrare categoria e workflow per ID.
La CI deve eseguire i test di catalogo, lifecycle e defaults.

## Verifica

`python -m pytest -q tests/test_workflow_catalog.py tests/test_workflow_lifecycle.py tests/test_rc77_catalog_import_policy.py`

I test coprono categoria locale senza workflow, replica ereditata, importazione
ripetuta, associazione tramite prima categoria, legacy workflow con step senza
record lifecycle, cancellazione/reimportazione e conservazione delle label.
