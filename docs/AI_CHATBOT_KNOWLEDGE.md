# Knowledge base operativa AlBot/Alex

Questo documento sintetico è caricato automaticamente nel contesto interno del plugin AI Chatbot. Serve a mantenere AlBot, chiamabile anche Alex, allineato alle funzionalità e ai setup correnti di Cybersecurity Incident Registry 0.5.0-1.

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
- Motori supportati: ChatGPT/OpenAI, Claude, Gemini, Ollama e Perplexity, configurabili per endpoint, modello e API key.
- Le API key già presenti sono mostrate solo in forma offuscata; il valore reale non è reso nel markup HTML. Lasciando il campo vuoto si mantiene la chiave esistente, inserendo un nuovo valore la chiave viene sovrascritta.
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


## Aggiornamento 0.5.0-1

La versione 0.5.0-1 aggiunge la configurazione amministrativa “Layout campi incidenti” per scegliere i campi visibili nella form di nuovo incidente e i riquadri di ricerca visibili nella sezione Dati generali. La ricerca destinatari esterni e la ricerca utente LDAP sono opzioni separate. La release riorganizza le “Operazioni previste” in “Fasi procedurali” con descrizione del flusso separata dal task cliccabile, introduce pulsanti link sicuri nella sintassi Markdown tramite `{button:Etichetta|URL}`, consente di rendere obbligatoria per singolo task la “Descrizione operazioni compiute” e integra la ricerca LDAP nelle form di creazione/modifica incidente con filtro, attributi di ricerca e attributi di auto-fill configurabili per Riferimento ed E-mail destinatario.

Aggiornamento 0.5.0-1: la ricerca LDAP negli incidenti mostra tutti i risultati restituiti dalla query e, per ogni riga, tutti gli attributi configurati in “Attributi di ricerca incidenti”; l'utente seleziona la riga da usare per compilare Riferimento/Destinatario/E-mail. In “Layout campi incidenti”, in assenza di configurazioni salvate, tutte le voci sono selezionate per default. Nei “Flussi operativi incidenti” ogni step ha una “Tipologia di step”: le tipologie di default Conferma ed Esecuzione non sono eliminabili ma hanno descrizione modificabile, mentre tipologie personalizzate possono essere aggiunte, rinominate, descritte o cancellate. La descrizione della tipologia selezionata viene usata come intestazione del riquadro inferiore delle “Fasi procedurali”.

Aggiornamento 0.5.0-1: nella pagina **Flussi operativi incidenti** è possibile clonare un intero workflow scegliendo sorgente e destinazione tra flusso di default e categorie. Se la destinazione contiene già step, l'interfaccia richiede conferma di sovrascrittura e il server blocca la clonazione finché la conferma non è esplicita. Quando un incidente ha più categorie, il workflow applicabile è quello della prima categoria nell'ordine scelto con drag-and-drop; se tale categoria non ha workflow specifico, viene usato il flusso di default.
