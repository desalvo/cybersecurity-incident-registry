# RC76 - Associare un incidente a un workflow mediante le categorie

La versione didattica mantiene 87 slide editoriali e aggiunge istruzioni esplicite nelle slide 17-19, 22 e 70, lasciando invariato il numero complessivo delle pagine. Le modifiche sono implementate nei sorgenti JSON e nel generatore PptxGenJS: saranno conservate dalla CI in ogni rigenerazione.

## Percorso manuale

In un tenant in cui un admin ha importato un workflow specifico di categoria, da **Incidenti -> Nuovo incidente -> Nessun modello** selezionare e ordinare le categorie. La **prima categoria** determina il workflow quando sono disponibili step specifici per quella categoria, altrimenti si usano gli step predefiniti del tenant. Le categorie aggiuntive non sommano workflow. Salvare con **Crea** e verificare nel dettaglio card e azioni.

## Percorso con modello

Da **Incidenti -> Nuovo incidente** selezionare un modello, verificare valori precompilati e soprattutto **ordine delle categorie**. Il modello **non assegna direttamente** un workflow autonomo: sono le categorie risultanti al momento di **Crea** a determinarne lo scope. E possibile modificarle prima del salvataggio; controllare poi le fasi dell'incidente.

## Laboratorio Tutorial / SPAM

Nella slide editoriale 70, dopo il titolo di capitolo SPAM, la procedura indica l'importazione dal catalogo **Tenants Default** a una copia corrente associata alla categoria SPAM nel tenant Tutorial, la creazione manuale o da modello, lo spostamento di SPAM al primo posto in **Categorie selezionate**, la conferma e la verifica degli step. Lo schema vettoriale nativo illustra `prima categoria SPAM -> workflow SPAM`; la screenshot a destra è la vera cattura autenticata `spam-incident-config-labels` quando disponibile in CI, altrimenti viene usato il media storico CIR senza dichiararlo nuova evidenza.

## Integrita e provenienza

La verifica stretta richiede che lo SHA-256 della schermata CI `spam-incident-config-labels` sia **collegato realmente** sia alla slide 70 (laboratorio) sia alla slide 78 (categorie e dati), oltre che all'appendice screenshot del run corrente. Nessuna screenshot di prova sintetica viene distribuita come evidenza autenticata.

Sorgenti funzionali: `app/workflow_lifecycle.py::workflow_scope_for_categories`, `app/routes.py::workflow_steps_for_incident`, `app/routes.py::incident_new`, `app/workflow_catalog.py`. Nessuna modifica al comportamento applicativo o alla CI di acquisizione: la cattura necessaria era già obbligatoria.
