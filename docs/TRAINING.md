# Laboratorio operativo e presentazione CIR

Materiale per **0.10.0-1 / RC1**, aggiornato il **22 novembre 2026**.
Durata suggerita: 45-60 minuti, inclusa esercitazione. Le tempistiche sono una
proposta didattica, non una misura delle prestazioni applicative.

La presentazione modificabile è [CIR_Operational_Training_IT.pptx](presentation/CIR_Operational_Training_IT.pptx),
34 slide con note del relatore, testo e diagrammi modificabili. Le illustrazioni
sintetiche mostrano infrastrutture e sicurezza informatica senza persone, usando
l'identità grafica approvata per l'interfaccia e i manuali. La descrizione delle
funzioni si basa sul codice e sulle guide del package; 0.10.0-1 RC2 è un candidato
da sottoporre ai gate indicati in [TESTING_AND_PRODUCTION.md](TESTING_AND_PRODUCTION.md).

L'**edizione sorgente** include il laboratorio completo e le prime pagine dei
cinque manuali PDF realmente generati. Le aree destinate alle schermate riportano
«Acquisizione CI in attesa»: non sono mockup né acquisizioni dell'applicazione.
L'**edizione generata dalla CI** incorpora tutte le 17 viste desktop/mobile
verificate sullo stesso commit, VERSION e BUILD: login, registro e menu, incidente,
AlBot, switch globale e stile classico, moduli, SSO, guide online utente e admin.
Le acquisizioni usano solo i dati sintetici del seed dimostrativo. Il caso di
esfiltrazione presente nelle immagini illustra la UI; l'esercizio
`DEMO-PHISH-001` descritto sotto resta un caso didattico separato da eseguire.

## Preparazione del facilitatore

Usare un'istanza di laboratorio isolata, un tenant operativo **Laboratorio
didattico**, un admin di tenant e un superuser di prova. Verificare tenant attivo,
fuso orario, accesso ai documenti e configurazione delle notifiche. Usare una
casella SMTP di prova o la conferma senza invio prevista dall'applicazione.
Il materiale della lezione non richiede invii a terzi.

Il superuser prepara un workflow corrente **Phishing - laboratorio** nel catalogo
di Tenants Default. Preparare gli step seguenti con le rispettive label azione;
i nomi sono un esempio, non un nuovo workflow obbligatorio preinstallato:

| Ordine | Step | Configurazione proposta | Evidenza attesa |
|---|---|---|---|
| 10 | Informazione iniziale | Azione di registrazione, richiesta | Segnalazione e orario |
| 20 | Analisi | Registrazione, richiesta | Valutazione e sistemi interessati |
| 30 | Contenimento | Registrazione, richiesta | Attività operativa e suo esito |
| 40 | Notifica laboratorio | Notifica e template di prova | Documento e conferma/invio di prova |
| 50 | Verifica evidenze | Controllo documenti | Allegati pertinenti e report |
| 60 | Conclusione | Registrazione e controllo procedurale | Esito, avvisi risolti, stato chiuso |

Importare il workflow nel tenant didattico, senza sostituire flussi in uso.
Predisporre un PDF valido e un allegato fittizio. Non introdurre password, token,
recapiti personali o evidenze di incidenti reali nella sessione condivisa.

## Esercizio 1 - Gestione dell'incidente

Scenario interamente fittizio: alle 09:10 un operatore segnala un accesso anomalo
successivo a un messaggio di phishing a un account di laboratorio.

1. **Incidenti → Nuovo incidente.** Inserire nome `Phishing - account laboratorio`,
   riferimento `DEMO-PHISH-001`, descrizione della segnalazione e data/ora.
   Selezionare la categoria del workflow corrente importato. Salvare e annotare
   ID e tenant. Il riferimento è obbligatorio.
2. **Dati generali.** Verificare gravità, tipo, persone di prova e descrizione.
   La prima categoria nell'ordine determina il flusso dedicato, se presente;
   altrimenti vale il flusso di default. Le categorie non sommano più workflow.
3. **Operazioni previste / Azioni.** Registrare Informazione iniziale e Analisi.
   Eseguire il contenimento con gli strumenti autorizzati del laboratorio, poi
   registrarlo in CIR con orario, descrizione ed evidenza. CIR non revoca da solo
   credenziali e non isola automaticamente un endpoint.
4. **Step Notifica laboratorio.** Aprire il percorso guidato, scegliere il
   template, verificare contenuto e destinatari di prova. Usare il canale di test
   o la conferma senza invio prevista. Verificare l'associazione al caso.
   I destinatari istituzionali e le scadenze reali dipendono dalla procedura locale;
   questo esempio non stabilisce obblighi normativi.
5. **Documenti / Report.** Caricare l'allegato fittizio, controllare il PDF e lo
   storage scelto. Se disponibile Alfresco, verificare cartella e report con ID e
   nome incidente e usare Sync per leggere lo stato. Il laboratorio può essere
   svolto anche usando lo storage CIR senza un Alfresco remoto.
6. **Conclusione.** Verificare gli avvisi, completare le azioni richieste,
   registrare esito e indicazioni di miglioramento e impostare lo stato chiuso.
   Se la chiusura è bloccata, individuare l'avviso reale: non eliminare parametri
   o step per aggirare il controllo. Verificare cronologia e report finale.

Risultato atteso: un caso chiuso con classificazione coerente, azioni datate,
documenti collegati e traccia delle decisioni. Il facilitatore chiede a ogni
partecipante di ritrovare almeno una decisione e la relativa evidenza.

## Esercizio 2 - Varianti e obsolescenza

1. Un admin di tenant importa due volte la stessa voce corrente del catalogo:
   **Phishing A** e **Phishing B**. Un superuser può scegliere un altro tenant;
   un admin di tenant non può farlo.
2. Prima di usare B in un incidente, eseguire **Personalizza parametri** su B.
   Modificare una dipendenza o un parametro della variante B e verificare che A
   conservi i propri riferimenti. La struttura dei workflow è già separata dopo
   ogni import; la personalizzazione esplicita separa anche le dipendenze.
3. Creare un incidente di prova che usa A. Verificare che la cancellazione di
   workflow, label e altri elementi in uso sia rifiutata senza perdere relazioni.
4. Il superuser imposta obsoleta la sorgente in Tenants Default. Verificare gli
   avvisi per tutti gli admin e superuser e lo stato obsoleto di entrambe le copie,
   inclusa B personalizzata. La voce non deve essere importabile di nuovo.
5. Tentare un nuovo incidente con A: il sistema deve rifiutare l'assegnazione.
   Aprire invece il vecchio incidente di A: il flusso e lo storico restano.
6. Se si prova la riattivazione, riattivare prima la sorgente; le copie non
   tornano correnti automaticamente. L'admin decide esplicitamente la riattivazione.

La collisione degli ID viene verificata dalla regressione automatica RC18:
crea un elemento locale collidente, propaga il nuovo elemento Defaults e importa
un workflow che lo referenzia. L'asserzione richiede l'esatto ID della replica
locale, non l'ID sorgente né quello del vecchio elemento. Non manipolare gli ID
a mano sul database di un'istanza operativa durante la lezione.

## Esercizio 3 - Portabilità controllata

Esportare tutto Tenants Default con il bundle dedicato. In un'altra istanza di
laboratorio caricarlo nella pagina amministrativa della sorgente e verificare
catalogo, stati, documenti e mapping. I segreti sono esclusi per impostazione
iniziale; configurare le integrazioni nella destinazione. Il bundle completo non
è un export anonimizzato dei contenuti binari.

Il bootstrap anonimizzato include `default` e Tenants Default ed è importato
attraverso il Full Import. Il Full Import sostituisce il database e i file
applicativi: usarlo su un'istanza di prova o dopo un backup verificato. Non usare
un import totale per aggiungere un singolo workflow; usare il catalogo o il JSON.

## Materiali, ricostruzione e consegna

- Contenuto delle slide: [presentation/content_it.json](presentation/content_it.json).
- Asset e provenienza: [presentation/assets/sources.json](presentation/assets/sources.json).
- Manuali PDF e brochure IT/EN sono rigenerabili con
  `python scripts/build_documentation_pdfs.py --include-brochures` (ReportLab).
- La guida compatta Alfresco si rigenera dal testo operativo consolidato con
  `python scripts/build_alfresco_pdf.py`, usando la stessa dipendenza ReportLab.
  Le note storiche complete restano in [ADMIN_ALFRESCO.md](ADMIN_ALFRESCO.md).
- I materiali statici di questa consegna sono stati generati dopo aver fissato
  VERSION `0.10.0-1` e BUILD `20261122`. I generatori leggono quei file; per una
  build successiva rigenerare i materiali, senza cambiare l'identità delle prove
  screenshot già acquisite per una build precedente.
- La presentazione si rigenera con il tool pubblico
  [build_training_presentation.py](../scripts/build_training_presentation.py),
  `python-pptx` e Poppler (`pdftoppm`). Le dipendenze Python per la documentazione
  sono in [requirements-docs.txt](../requirements-docs.txt); gli strumenti di
  authoring non vengono aggiunti all'immagine applicativa. Il vecchio comando
  `node docs/presentation/build.mjs /percorso/progetto` rimane un launcher
  compatibile del medesimo generatore Python, senza librerie private.
- La generazione estrae la pagina 1 dai cinque PDF con Poppler. Le immagini
  incorporate nel PPTX sono gli esatti PNG ottenuti dal rendering dei PDF;
  non vengono usate copertine simulate o ricostruite a parte.
- `presentation-receipt.json` registra versione, build, commit, provenienza,
  hash del PPTX, screenshot incorporati e prime pagine PDF/PNG. La validazione
  legge i media effettivi dentro lo ZIP PowerPoint, il testo nativo e le note
  di ogni slide; una dichiarazione nella ricevuta da sola non basta.
- Destinazione richiesta per il PowerPoint: Dropbox
  `/INFN/cybersecurity-incident-registry/CIR_Operational_Training_IT.pptx`.
  Il file è incluso nel package. Durante la preparazione RC18 l'integrazione
  Dropbox risultava disabilitata dall'amministratore del workspace: il caricamento
  remoto resta da effettuare da un contesto autorizzato, senza considerarlo già
  completato.

Per rigenerare l'edizione sorgente dopo i PDF:

```bash
python -m pip install -r requirements-docs.txt
python scripts/build_training_presentation.py \
  --documentation-dir docs \
  --output docs/presentation/CIR_Operational_Training_IT.pptx
```

Poppler deve essere installato sul sistema. La CI prepara prima le acquisizioni
verificate e i PDF con la loro ricevuta intermedia; quindi esegue:

```bash
python scripts/build_training_presentation.py \
  --documentation-dir artifacts/ui/documentation \
  --output artifacts/ui/documentation/CIR_Operational_Training_IT.pptx \
  --screenshot-manifest artifacts/ui/manifest.json \
  --source-commit "$GITHUB_SHA" \
  --require-real-screenshots
```

I percorsi devono corrispondere a quelli effettivamente scelti dal workflow.
Il modo rigoroso rifiuta screenshot mancanti o alterati, commit/versione/build
diversi, ricevute PDF non legate allo stesso manifest e prime pagine con metadati
di un'altra build. Lo stesso BUILD del job resta valido per l'intero batch:
non lo si ricalcola tra screenshot, PDF, PPTX e immagine container. Al termine
la CI completa la ricevuta aggregata prima di installare i materiali nel package.

## Riferimenti di sviluppo, conformità e manutenzione

Le slide distinguono il supporto applicativo alla procedura dalla conformità
dell'organizzazione. Registro, segregazione tenant, workflow, audit e documenti
sono strumenti utili per attuare procedure locali; non determinano automaticamente
l'applicabilità di una norma, i suoi destinatari o gli adempimenti di un ente.
Non viene dichiarata una certificazione NIS2, GDPR, AgID, WCAG o SSDF.

I riferimenti primari riportati nelle slide e nelle note sono:

- [Direttiva (UE) 2022/2555 — NIS2](https://eur-lex.europa.eu/eli/dir/2022/2555/oj),
  per gestione del rischio e degli incidenti e segnalazioni nel relativo ambito.
- [Regolamento (UE) 2016/679 — GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj),
  per protezione dei dati e gestione delle violazioni dei dati personali.
- [Linee guida AgID per il design dei servizi digitali](https://www.agid.gov.it/it/design-servizi/linee-guida-design-servizi-digitali-pa.html)
  e [requisiti di progettazione](https://docs.italia.it/italia/design/lg-design-servizi-web/it/versione-corrente/requisiti.html).
- [Linee guida AgID sull'accessibilità degli strumenti informatici per la PA](https://www.agid.gov.it/sites/agid/files/2024-06/Linee%20Guida%20sull%27accessibilit%C3%A0%20degli%20strumenti%20informatici%20-%20PA.pdf)
  e [WCAG 2.2](https://www.w3.org/TR/WCAG22/), come riferimenti per progettare
  e verificare tastiera, focus, etichette, contrasto e navigazione mobile.
- [NIST SSDF, SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final),
  come indirizzo per sviluppo sicuro e risposta alle vulnerabilità.

Le acquisizioni desktop/mobile aiutano la regressione visiva ma non sostituiscono
un audit di accessibilità o la valutazione manuale con tecnologie assistive.
L'applicabilità e la versione dei requisiti obbligatori vanno verificate nel
contesto dell'istanza e dell'organizzazione.

La sezione sulla sicurezza illustra il ciclo **rilevare, valutare, correggere,
verificare, promuovere e riesaminare**. Il workflow periodico di sicurezza può
rieseguire SCA e Trivy con i database di vulnerabilità aggiornati; la sua
configurazione non prova che una revisione sia stata completata con successo.
Nuove vulnerabilità, una `FixedVersion` disponibile o la scadenza della risk
acceptance richiedono una nuova valutazione. La revisione non promuove immagini:
una correzione segue PR, test e gate sul digest candidato prima del rilascio.
La scadenza della disposition del package resta quella documentata in
[SECURITY.md](SECURITY.md), senza rinnovi impliciti generando i materiali.

Fonti applicative: [MIGRATION.md](MIGRATION.md), [ADMIN_ALFRESCO.md](ADMIN_ALFRESCO.md),
[DEPLOYMENT.md](DEPLOYMENT.md), `app/routes.py`, `app/workflow_lifecycle.py`,
`app/workflow_catalog.py` e la guida online inclusa nell'applicazione.


## Laboratorio PDF e provenienza delle immagini (0.10.0-1 RC2)

`docs/CIR_Incident_Laboratory_IT.pdf` contiene sei pagine didattiche (apertura, presa in carico, contenimento, analisi, notifica e chiusura) con i risultati attesi. La stessa vista dei quattro riquadri e delle frecce proviene esclusivamente da `incident-desktop`, catturata dal browser sulla vera applicazione con record sintetici e vincolata al commit. Le pagine rappresentano attivita didattiche differenti, **non** sei stati realmente eseguiti o fotografati, per evitare di simulare un completamento non verificato. Nel package sorgente la zona screenshot indica chiaramente l'attesa della CI. Il processo CI genera la versione con screenshot reale prima della pubblicazione.

Audit media: l'illustrazione fotografica e stata generata per CIR; i loghi sono quelli usati nell'applicazione. Il PowerPoint non deve importare foto stock, immagini di persone o immagini remote. Il test `scripts/audit_training_media.py` verifica che gli asset embedded appartengano all'insieme locale autorizzato.
