# Support Tickets — service desk collaborativo di CIR (RC109)

**Stato iniziale:** disattivato. Il plugin non introduce servizi esterni o nuove dipendenze obbligatorie. L'amministratore globale può attivarlo da **Amministrazione → Plugins → Support Tickets**, anche da *Tenants Default*. Quando attivo appare **Supporto** nel menu degli utenti autenticati, nella UI classica e in quella moderna, su desktop e mobile.

## Aprire un ticket

Da **Supporto → Nuovo ticket**, scegli uno dei tenant ai quali hai accesso, oppure, se sei super admin, un tenant qualsiasi (eccetto il tenant speciale di configurazione). Scegli il destinatario: **admin del tenant** o **super admin**. Inserisci oggetto, priorità (urgente/alta/media/bassa), categoria (autorizzazione/incidenti/workflow/documentazione/altro), descrizione e allegati opzionali. L'app assegna un codice `SUP-000001`, registra autore e data/ora e imposta lo stato **Sottomesso** e il motivo dello stato vuoto.

La descrizione e le risposte supportano Markdown, elenchi, checkbox, link, blocchi di codice e tabelle, con escape dell'HTML non fidato. Ogni messaggio può avere fino a 5 allegati da 10 MB ciascuno (sempre nel limite generale di upload di CIR); gli allegati in preparazione possono essere rimossi uno a uno prima dell'invio. Sono supportati PDF, testo, JSON, CSV, immagini raster e documenti Office senza macro. Non sono accettati HTML, SVG, eseguibili e archivi. I file sono memorizzati in un percorso privato e sono scaricabili solo dopo una nuova verifica dei permessi. La cancellazione definitiva dei file dopo l'invio avviene assieme al ticket, esclusivamente dal super admin.

## Dashboard, ricerca e gestione

La dashboard mostra un ticket per riga, riepiloghi numerici, codice, oggetto, stato, priorità, categoria, tenant, assegnatario, richiedente, ultima attività e contatore dei messaggi. È possibile combinare filtri per testo/codice, stato, priorità, categoria, tenant, livello destinatario e ID del richiedente. Le conversazioni e gli allegati restano dentro la scheda del ticket.

Gli stati sono **Sottomesso, Aperto, Assegnato, In lavorazione, Completato, Rifiutato, Chiuso**; il motivo di cambio stato è facoltativo. Il richiedente vede, commenta, chiude e riapre soltanto i propri ticket. L'admin gestisce quelli del proprio tenant indirizzati al livello 1; il super admin può gestire tutti i ticket, compresa la cancellazione totale con doppia conferma (finestra + codice ticket). I ticket indirizzati direttamente al livello 2 non sono mostrati agli admin di tenant che non ne siano autori. L'admin può **coinvolgere i super admin** nello stesso ticket: cronologia e visibilità agli admin del tenant vengono preservate.

Le operazioni registrano un audit per l'utente e il tenant destinatario. La chiusura disabilita le risposte finché il ticket non viene riaperto.

## Email, rete e riservatezza

Alla creazione, alla risposta, al cambio di stato e all'escalation sono inviate email individuali in **HTML professionale**, con colore e pulsante di collegamento diretto. Il corpo del ticket e gli allegati non vengono inclusi nelle email: i destinatari devono autenticarsi in CIR. Il servizio usa le impostazioni SMTP del tenant destinatario e rispetta la policy di sicurezza sulle destinazioni in uscita (`CIR_OUTBOUND_PRIVATE_HOSTS`). Se SMTP non è configurato o non è raggiungibile, il ticket viene comunque salvato e l'errore è registrato nei log applicativi. Occorre configurare la chiave globale `application_external_url` per ottenere link assoluti corretti.

## Database, storage, backup e sicurezza

Nuova revisione schematica **`20261127_02_support_tickets`**, idempotente, con quattro tabelle dedicate. Lo storage privato è configurabile con `SUPPORT_TICKETS_DIR` (default `/data/support_tickets`), normalmente ospitato sul PVC `/data` preesistente. Il backup completo comprende le quattro tabelle e i file nel manifest persistente; l'import per tenant non può creare categorie globali e non esporta conversazioni private di altri tenant o dirette al livello 2. Un bootstrap anonimizzato non include i ticket. Non è consentita la cancellazione di un tenant che possieda ticket.

La modalità iniziale rimane **disattivata**, anche in un bootstrap ricreato. Testare l'invio SMTP con un indirizzo reale e verificare ruoli e tenancy prima di abilitare il plugin in produzione.
