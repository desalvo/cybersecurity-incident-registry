# RC79 — Cancellazione dei tipi di notifica e fallback Tenants Default

## Comportamento amministrativo

Da **Notifiche → Tipi di notifica** l'admin del tenant (o il super admin nel
contesto del tenant attivo) può eliminare anche tipi ereditati e alias
legacy con suffisso `_td`, dopo una conferma esplicita. L'operazione è
limitata al tenant attivo, non a tutti i tenant dell'istanza.

L'eliminazione è **atomica**:

1. Risoluzione del tipo locale e del corrispondente tipo pubblicato in
   `Tenants Default` (quando esiste), mediante provenienza registrata o
   confronto sicuro del codice di un alias legacy.
2. Eliminazione di **tutti i template del tipo nel tenant attivo**, poi
   eliminazione del tipo e della sua provenienza obsoleta. Nessun template
   condiviso viene modificato nella sorgente.
3. Per gli alias `_td` riconducibili a una definizione pubblicata,
   riallineamento al codice originario dei riferimenti locali in workflow,
   documenti, notifiche pianificate, configurazioni dei moduli e impostazioni JSON dei workflow del tenant.
4. **Nella stessa transazione**, sincronizzazione con `Tenants Default`.
   Il tipo pubblicato viene ricreato o associato al tipo omonimo del tenant;
   tutti i template pubblicati del tipo vengono ripristinati o riassociati.
   Nessuna copia suffissata né duplicato creato intenzionalmente.
5. Traccia audit della cancellazione e commit; su errore rollback integrale.

Un tipo realmente locale, assente da `Tenants Default`, viene rimosso
insieme ai suoi template e **non** ricreato. Se esistono riferimenti
operativi a un tipo non sostituibile, la cancellazione fallisce con un
messaggio esplicito per evitare riferimenti orfani.

## Dati e permessi

- Un amministratore di un tenant non cancella mai i template o i tipi degli
  altri tenant; la UI risolve gli ID solo nel tenant attivo.
- La sorgente `Tenants Default` non viene cancellata quando si elimina una
  replica o un override locale.
- Le eventuali personalizzazioni degli altri tipi o tenant rimangono intatte.
- Se un admin modifica l'override, il suo contenuto prevale fino alla
  cancellazione; dopo la cancellazione torna il testo condiviso.
- Eliminare direttamente un tipo dalla **sorgente** `Tenants Default` è una
  modifica diversa: la sincronizzazione ritira la definizione condivisa.

## Regressioni

`tests/test_rc79_notification_type_deletion.py` esercita il servizio
transazionale reale con SQLAlchemy SQLite, senza simulare la semantica della
funzione di sincronizzazione. Comprende reintegrazione immediata dei template,
adozione dell'override locale, riferimenti `_td`, cross-tenant, casi privati
e rollback su fallimento.

`tests/test_rc79_notification_type_http.py` verifica permessi e risposta della
rotta Flask nella CI completa; non è eseguibile nell'ambiente locale senza
Flask. Eseguire il job GitHub Actions prima di pubblicare la release.
