# RC56 - immagini di mapping PDF e Alfresco nella CI didattica

La pipeline `ui-documentation` acquisisce ora tre viste addizionali
tramite Chromium e l applicazione CIR autentica. L ambiente e sempre
una istanza temporanea SQLite isolata, con TLS/CSRF e controlli applicativi reali.

- `pdf-mapping-configuration`: modulo PDF AcroForm **reale** con tre campi
  `RIFERIMENTO`, `DESCRIZIONE`, `DATA_INIZIO`, associati rispettivamente a
  `reference`, `description`, `start_date`.
- `alfresco-settings-desktop`: configurazione Alfresco del tenant con
  endpoint fittizio `https://alfresco.example.invalid`, credenziali non reali
  e nessuna richiesta inviata a un server remoto.
- `alfresco-incident-documents`: selettori e comandi dell archivio Alfresco
  nella scheda dell incidente, senza invio effettivo di documenti a terzi.

I tre screenshot sono obbligatori per manifest, provenienza e PowerPoint
prodotto dalla CI. I file `CIR_Operational_Training_Visual_RC56.pptx` e `.pdf`
contengono le immagini gia acquisite nel run precedente (19 screenshot).
Dopo il nuovo run CI, la presentazione generata dal workflow inserira anche
le tre nuove acquisizioni, senza immagini inventate.

Un test integrativo di upload verso Alfresco richiederebbe un server
repository mockato sulla loopback e un contratto di API REST separato; non
si contatta mai un Alfresco reale dalla fixture documentale.
