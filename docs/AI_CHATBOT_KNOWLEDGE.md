# Knowledge base operativa AlBot/Alex

Questo documento sintetico è caricato automaticamente nel contesto interno del plugin AI Chatbot. Serve a mantenere AlBot, chiamabile anche Alex, allineato alle funzionalità e ai setup correnti di Cybersecurity Incident Registry 0.6.0-3.

## Identità e scopo

- Nome assistente: AlBot, chiamabile anche Alex.
- Ruolo: helpdesk applicativo interno per utenti e amministratori della piattaforma.
- Lingua predefinita: italiano, con supporto alla documentazione e all'interfaccia anche in inglese.
- Scopo applicazione: registro operativo per incidenti di cybersecurity, con gestione end-to-end di incidenti, workflow, azioni, notifiche, documenti, moduli PDF compilabili, audit, report, backup ed export/import.

## Funzionalità utente principali

- Dashboard con incidenti, avvisi procedurali e stato operativo.
- Creazione e modifica incidenti con dati generali, gravità, stato, rischio per diritti e libertà, categorie, dati interessati, conseguenze, raccomandazioni e destinatari esterni.
- Modelli incidente selezionabili solo durante la creazione di un nuovo incidente: quando un modello viene scelto nella form di creazione, i campi principali vengono autocompilati lato client e salvati solo quando l'utente conferma con Salva. Gli incidenti già esistenti non espongono più il comando per applicare un modello.
- Timeline azioni incidente con allegati, note, utenti coinvolti e collegamento agli step procedurali.
- Chiusura automatica condizionata: se un'azione ha il tag "Chiusura del task in assenza di avvisi procedurali" e non restano avvisi procedurali attivi, l'incidente viene impostato a chiuso con data e ora correnti nella timezone applicativa.
- Reportistica con grafici e report PDF incidente.
- Export e import dati, inclusi workflow custom esterni.
- Interfaccia responsive desktop e mobile.

## Configurabilità amministrativa

- Autenticazione configurabile con account locali, LDAP/Active Directory, OAuth2/OpenID Connect/SSO e opzioni MFA quando abilitate.
- Ruoli, utenti, tassonomie, categorie, gravità, dati interessati, azioni, notifiche, loghi, dati titolare/responsabile e impostazioni applicative configurabili da amministrazione.
- Workflow incidenti configurabili con step ordinati, condizioni, azioni richieste, scadenze, avvisi procedurali e import/export mirato.
- Import workflow: gli elementi identici già presenti vengono rilevati, non duplicati e non mostrano avvisi di sovrascrittura; le sovrascritture sono richieste solo per elementi realmente diversi.
- Notifiche automatiche configurabili verso utenti, CSIRT, DPO e destinatari custom. Possono includere attachment automatici di documenti generati o PDF compilabili.
- Moduli PDF compilabili: mapping modulare tra campi del PDF e dati incidente; generazione/compilazione automatica dei documenti.
- Full backup/full export: include database, file persistenti, allegati e documenti della knowledge base del chatbot AI.

## Plugin AI Chatbot

- Il plugin si chiama AlBot nell'interfaccia; l'utente può chiamarlo anche Alex.
- Icona AlBot: usata nel launcher, nell'intestazione e accanto alle risposte del bot.
- Motori supportati: ChatGPT/OpenAI, Claude, Gemini, Ollama e Perplexity, configurabili per endpoint, modello e API key; nell'interfaccia il motore ChatGPT è mostrato con capitalizzazione corretta.
- Le API key già presenti sono mostrate solo in forma offuscata; il valore reale non è reso nel markup HTML. Lasciando il campo vuoto si mantiene la chiave esistente, inserendo un nuovo valore la chiave viene sovrascritta.
- La configurazione plugin consente il reset globale delle configurazioni backend AI ai valori di default: motore attivo ChatGPT, endpoint e modelli iniziali e API key vuote. Ogni singolo motore dispone inoltre di un reset dedicato che ripristina solo endpoint, modello e API key del backend selezionato, senza modificare motore attivo, altri backend, abilitazione plugin o opzione di contesto database.
- Endpoint AI validati per ridurre rischi SSRF/egress non controllato.
- Knowledge base chatbot: include documentazione progettuale, README, changelog, help utente/amministratore, questo documento operativo e documenti caricati dagli amministratori.
- Knowledge base caricabile: supporta documenti testuali e file validati; l'uso con dati anonimizzati è raccomandato.
- Contesto database opzionale: quando abilitato, AlBot riceve uno snapshot applicativo sanitizzato; sono esclusi dati sensibili/binari o gestiti da knowledge base dedicata.

## Markdown e notifiche

- Rendering Markdown sicuro server-side e client-side: titoli, elenchi, grassetto, corsivo, codice, link HTTP/HTTPS, pulsanti `{button:Etichetta|URL}` con URL assoluti o relativi/ancore, colori e dimensioni controllate.
- Sintassi colore supportata: `{color:red}testo{/color}`, `{color:#0b7285}testo{/color}`, `rgb(...)`, `hsl(...)` quando valida.
- Sintassi dimensione supportata: `{size:large}testo{/size}`, `{size:14px}testo{/size}`, `{size:1.2em}testo{/size}`, `{size:120%}testo{/size}` entro limiti controllati.
- Le formattazioni Markdown nelle notifiche schedulate vengono rimosse prima dell'invio email.

## Distribuzione e setup

- L'applicazione è disponibile come container Docker: `desalvo/cybersecurity-incident-registry` su Docker Hub.
- Sono supportati run con Docker standalone, Docker Compose e manifest Kubernetes inclusi nel pacchetto.
- Il container usa un entrypoint eseguibile e può montare volumi persistenti per database, allegati, documenti, knowledge base e backup.
- Variabili principali: `SECRET_KEY`, `DATABASE_URL`, configurazioni mail/SMTP, URL pubblico, dati autore/applicazione, impostazioni LDAP/SSO quando usate.
- È disponibile documentazione container in `docs/CONTAINER_ENVIRONMENT.md` e `docs/CONTAINER_ENVIRONMENT_en.md`.

## Documentazione e PDF

- I PDF statici ITA/ENG di documentazione utente e amministrativa sono generati e salvati in `docs/`.
- La brochure ITA/ENG è in formato A4 verticale, massimo 2 pagine, con background a tema cybersecurity.
- I PDF scaricabili dall'applicazione omettono elementi di navigazione, utente loggato, logout, menu e widget AlBot non utili alla stampa.
- Le figure nei PDF sono mantenute vicino al capitolo che le cita e i titoli di capitolo sono mantenuti con l'inizio del testo.

## Compliance, licenza e progetto

- Il progetto dichiara allineamento alle linee guida AGID per lo sviluppo sicuro tramite suite di test, controlli dinamici, Bandit e runner manuale Docker per pip-audit.
- I risultati AGID non vengono rigenerati automaticamente a ogni modifica: si salvano nuove evidenze solo se richiesto esplicitamente.
- Licenza: European Union Public Licence (EUPL).
- Creatore: Alessandro De Salvo, Alessandro.DeSalvo@roma1.infn.it.
- Repository GitHub: https://github.com/desalvo/cybersecurity-incident-registry.


## Aggiornamento 0.6.0-3

La versione 0.6.0-3 aggiunge la configurazione amministrativa “Layout campi incidenti” per scegliere i campi visibili nella form di nuovo incidente e i riquadri di ricerca visibili nella sezione Dati generali. La ricerca destinatari esterni e la ricerca utente LDAP sono opzioni separate. La release riorganizza le “Operazioni previste” in “Fasi procedurali” con descrizione del flusso separata dal task cliccabile, introduce pulsanti link sicuri nella sintassi Markdown tramite `{button:Etichetta|URL}`, consente di rendere obbligatoria per singolo task la “Descrizione operazioni compiute” e integra la ricerca LDAP nelle form di creazione/modifica incidente con filtro, attributi di ricerca e attributi di auto-fill configurabili per Riferimento ed E-mail destinatario.

Aggiornamento 0.6.0-3: la ricerca LDAP negli incidenti mostra tutti i risultati restituiti dalla query e, per ogni riga, tutti gli attributi configurati in “Attributi di ricerca incidenti”; l'utente seleziona la riga da usare per compilare Riferimento/Destinatario/E-mail. In “Layout campi incidenti”, in assenza di configurazioni salvate, tutte le voci sono selezionate per default. Nei “Flussi operativi incidenti” ogni step ha una “Tipologia di step”: le tipologie di default Conferma ed Esecuzione non sono eliminabili ma hanno descrizione modificabile, mentre tipologie personalizzate possono essere aggiunte, rinominate, descritte o cancellate. La descrizione della tipologia selezionata viene usata come intestazione del riquadro inferiore delle “Fasi procedurali”.

Aggiornamento 0.6.0-3: nella pagina **Flussi operativi incidenti** è possibile clonare un intero workflow scegliendo sorgente e destinazione tra flusso di default e categorie. Se la destinazione contiene già step, l'interfaccia richiede conferma di sovrascrittura e il server blocca la clonazione finché la conferma non è esplicita. Quando un incidente ha più categorie, il workflow applicabile è quello della prima categoria nell'ordine scelto con drag-and-drop; se tale categoria non ha workflow specifico, viene usato il flusso di default. I workflow sono sempre tenant-specifici: creazione, clonazione, import/export, modifica ed eliminazione operano solo sul tenant attivo. La stessa pagina consente anche di eliminare interamente un workflow selezionato, rimuovendo tutti gli step del flusso nel tenant attivo.

- Modelli incidente: il salvataggio mantiene l’ordine delle categorie selezionate tramite drag and drop, così la successiva modifica del modello ripropone le categorie nello stesso ordine operativo.
- Admin → Altre configurazioni: il pulsante "Cleanup documenti orfani" elimina da uploads solo i file generati dall’applicazione che non sono più collegati ad alcun incidente/documento/allegato, preservando gli allegati caricati manualmente.

- Nelle Fasi procedurali del dettaglio incidente, la prima fase non ancora completata è evidenziata con una grande freccia rossa. Nella lista incidenti le icone distinguono avvisi procedurali attivi, incidente finalizzato ma non chiuso e incidente chiuso senza avvisi attivi.

### Plugin Alfresco

È disponibile un plugin opzionale **Alfresco**, disabilitato per default, configurabile da **Admin → Plugins → Alfresco**. Il plugin usa le API REST di Alfresco per caricare e scaricare documenti degli incidenti. La configurazione comprende URL base, credenziali API, site opzionale, cartella destinazione, timeout e verifica TLS. Quando il plugin è abilitato, nella sezione **Documenti** di un incidente è possibile caricare i file anche su Alfresco o inviare ad Alfresco un documento già presente; i documenti collegati a un node id Alfresco espongono anche il download via API. La password/API secret è salvata come setting segreto e non viene mostrata in chiaro.


## Multi-tenancy

L'applicazione supporta tenant multipli. Il tenant default viene creato automaticamente; l'utente admin locale è sempre superuser e può gestire tutti i tenant. Ogni utente può appartenere a più tenant con ruoli differenti; gli utenti admin gestiscono, esportano e importano solo i tenant in cui hanno ruolo admin. Incidenti, workflow, liste, notifiche, plugin e configurazioni operative sono separati per tenant; moduli PDF, configurazioni dei moduli, HTTPS/SSL, URL applicazione e fuso orario applicazione sono condivisi.

Aggiornamento 0.6.0-3: la gestione multi-tenant è completa. Ogni utente può appartenere a più tenant con ruoli differenti; il tenant `default` viene creato automaticamente e non può essere cancellato. Gli utenti vedono incidenti, configurazioni operative e dati correlati del tenant attivo. I superuser, incluso l'utente locale `admin`, possono amministrare tutti i tenant, eseguire export/import globale e dispongono di un selettore “tenant attivo” nella barra superiore e nella pagina Admin → Tenant; lo switch filtra immediatamente la home sugli incidenti del tenant selezionato. Il tenant attivo determina quali configurazioni tenant-specifiche vengono lette e modificate: liste configurabili, workflow, modelli incidente, notifiche, destinatari esterni, backup e knowledge base/plugin AI. Restano condivisi fra tenant i moduli documento e le relative configurazioni, HTTPS/SSL, URL applicazione e time zone applicazione. Quando si crea un nuovo tenant è possibile clonare la configurazione da un tenant esistente; se non viene indicata una sorgente viene usato il tenant corrente/default.

- La pagina Admin -> Utenti usa record collassabili chiusi per default; per ogni utente non builtin admin consente aggiunta, rimozione e modifica dei tenant associati e del ruolo specifico nel tenant. Permette inoltre di impostare il tenant attivo predefinito dell’utente, usato al login o quando la sessione non ha ancora uno switch esplicito. Gli utenti con più tenant accessibili hanno un selettore nella barra superiore: scegliendo un tenant lo switch è immediato nella sessione corrente e aggiorna subito il perimetro degli incidenti visualizzati. L’utente locale admin resta sempre superuser globale e non espone modifiche tenant-specifiche.

- I superuser e l'utente locale admin possono spostare un incidente tra tenant dal dettaglio incidente. Durante lo spostamento l'applicazione riallinea etichette, persone, raccomandazioni e label delle azioni al tenant di destinazione, riusando elementi esistenti o clonandoli se mancanti.

- Admin -> Flussi operativi incidenti: i superuser possono clonare workflow tra tenant diversi. La destinazione può essere sovrascritta selezionando Sovrascrivi; le label operative e le condizioni vengono riallineate al tenant destinazione.

- Lo spostamento di incidenti tra tenant e disponibile solo ai superuser dalla pagina principale: il pulsante Sposta nella riga dell'incidente apre una lista ricercabile dei tenant di destinazione, escluso il tenant sorgente, e ricarica la lista dopo il trasferimento.

Aggiornamento workflow cross-tenant: nella sezione di clonazione dei flussi, quando un superuser seleziona il tenant sorgente vengono mostrati solo i workflow esistenti in quel tenant. Il tenant di destinazione mostra solo i workflow gia' definiti nel tenant selezionato piu' la voce "Nuovo workflow". Scegliendo "Nuovo workflow" viene creata nel tenant destinazione una nuova categoria workflow e vengono clonate le dipendenze operative dal tenant sorgente, incluse action label e condizioni basate sulle liste configurabili.


Aggiornamento 0.6.0-3: creazione tenant, clonazione tenant e clonazione workflow cross-tenant sono idempotenti. Prima di creare label, categorie, action label, notifiche, destinatari, template, raccomandazioni o altre dipendenze, l'applicazione cerca elementi equivalenti nel tenant destinazione e li riusa se presenti. Anche la voce "Nuovo workflow" riusa una categoria equivalente gia' presente nel tenant destinazione, evitando duplicazioni in operazioni ripetute.

Aggiornamento 0.6.0-3: dopo full import o restore PostgreSQL con ID espliciti, l’applicazione riallinea le sequence anche in una transazione successiva al commit e prima delle clonazioni tenant/workflow. Questo evita errori `duplicate key value violates unique constraint "config_label_pkey"` durante la creazione di un tenant clonato o la clonazione di workflow che crea nuove categorie/label.


- In Admin -> Utenti la sezione Cerca utenti consente filtri separati per username, nome, email, backend, ruolo e tenant di appartenenza. Il filtro tenant mostra gli account con membership attiva nel tenant selezionato e rispetta il perimetro dell'amministratore collegato.

- La clonazione tenant e la clonazione workflow sono idempotenti: label e dipendenze già presenti nel tenant destinazione vengono riusate. Le label legacy/globali importate da backup precedenti vengono assorbite o fuse nel tenant corretto per evitare duplicazioni.
- In Gestione label, anche un superuser vede e modifica le label del solo tenant attivo; per operare su un altro tenant deve prima selezionarlo dal menu.



## Gestione utenti - stato scheda e password locali

In Admin -> Utenti, dopo il salvataggio dei dati account o delle membership la pagina conserva i filtri applicati, torna al record modificato e lo riapre automaticamente. L'utente locale admin e i superuser possono reimpostare dalla scheda utente le password degli account con login locale; gli account LDAP e SSO mantengono la gestione password nel provider esterno.
