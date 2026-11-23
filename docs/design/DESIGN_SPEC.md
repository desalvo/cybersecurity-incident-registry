# CIR — Interfaccia approvata della 0.10.0-1

## Decisione applicata il 23 novembre 2026 — documentazione 0.10.0-1

Il mockup comune PDF e online in `documentation-v2/` è stato approvato ed è
implementato nei generatori, nelle guide web, nei PDF scaricabili dall'app e nelle
brochure. La copertina usa testo nativo, dati About condivisi, logo e fotografia
cybersecurity senza persone. Il PowerPoint mostra le prime pagine PDF effettive.
Le precedenti indicazioni “da approvare” nelle sezioni storiche sono superate da
questa decisione e non riguardano più la copertina documentale corrente.

Le fotografie di copertina sono illustrazioni. Gli screenshot dell'applicazione
sono acquisiti separatamente dalla CI e devono superare i controlli di provenienza.


La 0.10.0-1 conserva l'interfaccia già integrata in RC20. I mock approvati sono
riferimenti storici immutabili, compresi i loro vecchi numeri di versione/build.
Il runtime e la documentazione corrente mostrano i metadati VERSION/BUILD della
0.10.0-1; i mock non sono screenshot di questa nuova build.

## Implementazione di origine: RC20

**Login v2, home v1, incidente v1 e assistente v1 sono approvati.** RC20 integra
questi riferimenti nei template e negli asset dell'applicazione. I quattro
sottopercorsi approvati restano byte-identici alla consegna RC19, con le stesse
fotografie sintetiche senza persone. I primi mock amministrativi, la hero a
costellazione e la timeline grafica incidente sono proposte superate.

La richiesta finale stabilisce **nuova UI attiva per default**. Lo switch è ora
reale: Admin → Interfaccia globale, solo superuser, Setting condiviso nel database,
effetto su tutti i tenant/utenti/login al successivo caricamento. I vecchi switch
OFF presenti nei prototipi storici non definiscono più il default runtime.

## Criteri applicati

- Login: testo professionale approvato; su mobile nome completo e logo, form e
  immagine nella composizione approvata; autenticazione locale/LDAP, SSO e MFA reali.
- Home e pagine ordinarie: navigazione navy, accenti blu, superfici chiare,
  foto cybersecurity concreta, registro a lista con filtri e operazioni esistenti.
- Incidente: blocchi descrittivi sopra e task operativi sotto, frecce responsive,
  collegamenti alle sezioni, stato e vincoli dal backend; nessun nuovo blocco
  sequenziale non previsto dal workflow.
- AlBot: richiamo in testata, pannello da 360 px su viewport ampi (>=1800 px),
  vista dedicata sui più piccoli, chiusura/ritorno accessibili, icona senza persone.
  Domanda singola e contesto configurato, nessuna lettura implicita della pagina,
  cronologia provider o esecuzione automatica di azioni.
- Classic: ramo originale mantenuto, con gli stessi endpoint e controlli;
  le correzioni CSP dei listener operativi valgono in entrambe le modalità.

Gli screenshot effettivi sono prodotti solo dal job CI
**Real UI screenshots and documentation**. I file di design restano rendering
illustrativi; la loro approvazione non certifica il funzionamento del runtime.
Il candidato deve superare test HTTP, browser e gate production prima dell'uso.
Copertine e brochure fotografiche proposte restano un passo di revisione separato.

## Proposta web precedente, conservata come storico non approvato

Questa fase presenta **login, homepage e dettaglio incidente**, ciascuno su
desktop e mobile, con navigazione desktop e menu mobile aperto. Manuali e brochure
restano proposte separate: non sono il centro di questa revisione.

## Come aprire e valutare

Aprire `index.html` in un browser recente: il selettore globale parte **OFF**.
Aprire **Profilo → Nuova interfaccia · globale** e attivarla per vedere la proposta,
oppure aprire
`index.html?ui=new#dashboard` per una revisione diretta del nuovo design.
Per servire la root del progetto con
`python -m http.server 8794` e visitare `/docs/design/index.html`.
Il mock non usa CDN, account reali, cookie applicativi o chiamate a servizi esterni.
Le immagini provengono da `../visual-assets/` e hanno provenienza documentata.

Destinazioni per la revisione:

| Vista | Frammento URL | Cosa valutare |
|---|---|---|
| Login | `#login` | identità applicativa, credenziali locale/LDAP, provider SSO configurati |
| MFA | `#mfa` | passo TOTP già previsto dall’applicazione |
| Panoramica | `#dashboard` | priorità, accessi rapidi, menu fotografici |
| Registro | `#incidents` | ricerca, filtri, selezione, import/export |
| Incidente | `#incident/1/workflow` | prossimo passo, vincoli, contesto tenant |
| Documenti | `#incident/1/documents` | CIR/Alfresco, stato, tag, moduli |
| Catalogo | `#catalog` | import ripetuti, nomi, varianti, obsolescenza |
| Amministrazione | `#admin` | directory ricercabile, raggruppamento completo |
| Avvisi | `#notices` | obsolescenza e parametri condivisi in uso |
| Statistiche | `#reports` | organizzazione di filtri e report |

Il comando **Tutte le funzioni**, la ricerca in alto e `Ctrl/Cmd+K` raggiungono
le destinazioni amministrative, i trasferimenti dati, il profilo e l'aiuto.
Il profilo in alto a destra cambia il ruolo dimostrativo: superuser, admin,
writer, operator (propri incidenti), reader e disabled. Non è autenticazione reale.

## Direzione visiva e token da preservare

Tutte le immagini del mock devono essere **senza persone** e raccontare registro
incidenti, workflow, documenti, evidenze e notifiche; non immagini generiche di
data center. Non esistono fallback verso fotografie delle revisioni precedenti.

La composizione mette il lavoro operativo al centro. Le fotografie marcano gli
accessi alle aree, senza essere sfondo di tabelle, moduli o testi lunghi.
Navy e verde definiscono la navigazione; il colore ambra segnala attenzione.
Gravità e stato hanno sempre testo oltre al colore.

| Token | Valore | Uso |
|---|---|---|
| `--navy` | `#102b39` | navigazione e sezioni editoriali |
| `--deep` | `#0b212d` | profondità del marchio |
| `--paper` | `#f4f4ef` | sfondo operativo |
| `--white` | `#ffffff` | superfici dei dati |
| `--ink` | `#142a35` | testo principale |
| `--muted` | `#5e7078` | testo secondario |
| `--teal` | `#086d65` | azioni primarie e stato attivo |
| `--mint` | `#dff0e9` | selezione e contesto condiviso |
| `--amber` | `#e0aa65` | accenti e richiami |
| `--line` | `#dbe2de` | separatori |
| raggio superfici | 10–14 px | pannelli, foto, moduli |
| raggio controlli | 7–8 px | pulsanti, filtri, input |
| font | Inter / Aptos / Segoe UI / Arial / sans-serif | font locali, nessun download |
| sidebar desktop | 232 px, 206 px sotto 1190 px | navigazione persistente |
| breakpoint mobile | 760 px | drawer e barra rapida inferiore |

Su mobile i testi operativi sono 14–16 px e i pulsanti hanno un target minimo di
44 px. Etichette di metadati e indicatori sono più piccole ma distinte dal corpo.
La pagina scorre verticalmente: i controlli non vengono miniaturizzati per
simulare il desktop. Le fotografie restano presenti nei menu di accesso e nel drawer.
Focus visibile, skip-link, dialog nativi, Escape, ricerca da tastiera,
`prefers-reduced-motion` e navigazione touch fanno parte della proposta.

## Interruttore globale della nuova interfaccia

La proposta include un **unico parametro globale**, gestito solo dai super admin,
che abilita o disabilita la nuova interfaccia per tutti i tenant dell’istanza.
Il valore iniziale previsto è **OFF**. Anche dopo approvazione e implementazione,
la nuova UI si abilita solo con una scelta esplicita di un super admin.
Non è una preferenza personale e non è una configurazione tenant-specifica.

Nel mock, il controllo è raggiungibile dal profilo superuser autenticato
e da **Amministrazione → Sistema e integrazioni → Interfaccia globale**.
Il cambio è reversibile e resta in memoria: persiste cambiando tenant nella demo,
ma il ricaricamento riparte da OFF (salvo URL esplicito `?ui=new` di revisione).
Gli altri ruoli possono vedere lo stato; non possono modificarlo.
OFF mostra una **rappresentazione illustrativa legacy** per il confronto:
non è uno screenshot o una ricostruzione certificata dell’attuale applicazione.

Dopo approvazione: introdurre un flag server globale dedicato, validato lato server,
con modifica solo superuser e audit; conservare i template legacy; scegliere il
layout al rendering della richiesta successiva. OFF deve sempre riattivare il
layout legacy senza cambiare dati, workflow o autorizzazioni. Il nome del flag e
l’endpoint di gestione sono ancora di progetto: `demo.global_interface` non è un
endpoint applicativo.

**Nessun flag runtime o template applicativo è stato aggiunto in questa consegna.**
Le tre proposte — UI, copertina manuale e brochure — restano tutte da approvare.

## Riorganizzazione, senza perdita dei percorsi

- **Spazio operativo:** panoramica, incidenti, report e statistiche.
- **Procedure e risorse:** catalogo workflow, documenti/notifiche, amministrazione.
- **Il tuo spazio:** avvisi, aiuto, profilo, MFA e password locale.
- **Tutte le funzioni:** indice ricercabile di tutte le voci del menu precedente.
- **Dentro l'incidente:** workflow, dati, azioni, documenti, notifiche e attività.
- **Amministrazione:** dati/continuità, workflow/configurazioni, notifiche/documenti,
  organizzazione/accessi, sistema/integrazioni. Le voci dinamiche dei template
  devono continuare a essere generate dai dati del tenant.

`feature-map.json` elenca ogni riferimento `url_for` dei template globali,
registro, dettaglio, Tenants Default e catalogo/workflow locali, con il nuovo
punto di accesso. I percorsi contestuali indicano conservazione e collocazione,
non dichiarano che il mock esegua tutte le operazioni applicative.

Sono compresi CSV, Full Export/Import, bootstrap, backup, AlBot, Alfresco,
SSO/LDAP, MFA, dati organizzativi, SSL/logo, utenti/tenant, campi e layout,
azioni automatiche, moduli/PDF, notifiche, audit e documentazione IT/EN.
Nel dettaglio restano previsti clone/spostamento/eliminazione, promemoria,
azioni e relativi allegati, esportabilità, conseguenze/misure/raccomandazioni,
download/delete remoti distinti, tag e sync Alfresco read-only.

## Comportamenti dimostrabili

1. Ricerca incidenti e filtro per aperti, chiusi o gravità alta.
2. Apertura del dettaglio e passaggio fra tutte le sezioni.
3. Registrazione di un esito fittizio e avanzamento visuale della fase.
4. Import ripetuto dello stesso workflow con nomi distinti nel tenant scelto.
5. Rinomina, stato locale e personalizzazione di una copia.
6. Obsolescenza della sorgente: blocco degli import e propagazione alle copie.
7. Cambio del contesto tenant e visibilità secondo il ruolo dimostrativo.
8. Apertura di Tenants Default come area di configurazione: niente creazione incidenti.
9. Menu mobile, ricerca di funzioni, profilo, avvisi e moduli di conferma.
10. Download di un CSV contenente **solo dati fittizi** del tenant attivo nel mock.
11. Switch UI globale ON/OFF, solo superuser, reversibile tra rappresentazione
    legacy e nuova proposta.
12. Percorso esplicito per parametri ereditati, override e ripristino ereditarietà.

I tenant `Research Lab` e `default` usano dati separati nella sessione.
Le copie workflow hanno un `tenantId`; l'import in un altro tenant non inserisce
la copia nel tenant attivo. Tenants Default non compare come destinazione
operativa. L'operatore vede solo i propri incidenti dimostrativi.
Il superuser può selezionare la destinazione fra i tenant operativi.

Le modifiche sono in memoria e scompaiono ricaricando la pagina. La scelta di un
file legge solo il nome: non carica dati. I dialog amministrativi illustrano
la presentazione; non sono una sostituzione completa dei form già implementati.
I numeri di statistiche e agenda sono esempi editoriali, non misure prodotte dal server.

## Confini per l'implementazione dopo approvazione

- Conservare tutti gli endpoint, nomi dei campi, token CSRF e controlli di ruolo.
- Conservare campi dinamici, validazioni, flash per sezione, plugin e traduzioni.
- Non cambiare il modello di autorizzazione per ottenere il nuovo menu.
- Tenants Default resta distinto da `default` e non ospita incidenti operativi.
- Mantenere il blocco del selettore tenant su nuovo/dettaglio incidente.
- Connettere componenti visuali alle funzioni esistenti; nessuna simulazione nel runtime.
- Conservare gli ID/UUID e le regole di mapping, cancellazione, obsolescenza e recovery.
- Le varianti di workflow non devono condividere modifiche locali involontariamente.
- Migrare i componenti pagina per pagina, verificando desktop 1440/1280 e mobile
  390/360, tastiera, contrasto, moduli lunghi e ruoli diversi.
- Eseguire regressioni applicative, PostgreSQL e gate CI previsti dal progetto.

L'approvazione riguarda questo linguaggio visivo, la navigazione e le viste
proposte. Eventuali correzioni si applicano al mock prima dell'implementazione.

## Verifiche

`node --check mockup.js` verifica la sintassi JavaScript. `verify_mockup.mjs`
contiene un controllo browser ripetibile di navigazione, ricerca, import ripetuti,
obsolescenza, tenant, ruoli, immagini, overflow e screenshot desktop/mobile.
Richiede Playwright, Chromium e un server locale di file statici. Non richiede
Flask o PostgreSQL e non contatta servizi di produzione.

Nel primo tentativo dell'ambiente di preparazione Chromium ha rifiutato la
creazione del socket del profilo (`socket() failed: Operation not permitted`).
Non considerare quel tentativo una verifica visiva o interattiva superata.
I risultati effettivi eventualmente eseguiti in un runtime disponibile sono
registrati nel report separato di consegna.

## Tavole native di revisione

`render_design_boards.py` produce un PDF di otto tavole e i PNG corrispondenti
con ReportLab e PyMuPDF. Legge i token principali da `styles.css` e gli incidenti
dimostrativi da `mockup.js`; impiega le immagini senza persone della directory
visual-assets. Le tavole mostrano la nuova UI ON per la revisione.

Le tavole sono una composizione di progetto, **non screenshot del browser** e
non certificano che il CSS abbia già superato prove visuali in un browser.
La consegna distingue i controlli logici/statici completati dal test browser
bloccato dall’ambiente. Il menu mobile, l’incidente e il controllo globale
restano disponibili nel mock interattivo per la valutazione diretta.

Esempio di rigenerazione: `python docs/design/render_design_boards.py --output /tmp/cir-ui-boards`.
Dipendenze del renderer di design: ReportLab, PyMuPDF, Pillow e Node.js; non sono
nuove dipendenze runtime di CIR.

## Rigenerazione delle tre proposte

Eseguire dalla root del progetto. Gli output seguenti sono anteprime separate:
non sostituiscono manuali, brochure o template runtime adottati.

```bash
python docs/design/build_cover_mock.py --language it --output /tmp/cir-design-review/manual-cover-mock.pdf
python docs/design/build_brochure_mock.py --language it --output /tmp/cir-design-review/brochure-mock.pdf
python docs/design/render_design_boards.py --output /tmp/cir-design-review/ui-boards
```

Per copertina e brochure è disponibile anche `--language en`.
I builder usano **ReportLab, pypdf, Pillow e PyMuPDF**; le tavole UI richiedono
anche **Node.js** per leggere i dati dimostrativi dal sorgente JavaScript.
I font locali DejaVu sono usati per il rendering offline. Playwright e Chromium
servono solo per il distinto controllo browser `verify_mockup.mjs`.
Queste dipendenze appartengono agli strumenti di design: non devono essere
aggiunte al runtime dell’applicazione per eseguire CIR.

## Login e bootstrap della consegna web

Il layout login è ricavato da `app/templates/login.html` e dai percorsi
`main.login`, `main.sso_login` e `main.mfa_verify` della baseline. Mantiene
logo organizzativo configurabile e identità CIR, messaggi di errore, username
e password obbligatori, password mascherata e lista dei profili SSO attivi
con eventuale logo provider. Locale e LDAP usano **lo stesso form**. Non sono
introdotti registrazione, recupero password o opzione “ricordami”.

Il mock mostra un solo provider SSO fittizio; l’integrazione dovrà continuare
a rendere la lista dinamica e condizionale della baseline. Il passaggio TOTP
si presenta agli utenti locali/LDAP quando previsto dalla configurazione
esistente. CSRF, rate limit, stato account, MFA e autorizzazioni restano nel
backend attuale: il mock non li sostituisce.

Credenziali della demo: **demo / cir-demo**; codice TOTP dello scenario demo:
**123456**. Non inserire segreti reali. I form non inviano richieste e i dati
inseriti non sono registrati o esportati. L’azione SSO apre una spiegazione
dimostrativa, senza OAuth o redirect a provider esterni.

Il file di consegna **CIR_Web_UI_Mock.html** può aprirsi direttamente sul
login nuovo stile inserendo questo bootstrap prima di `mockup.js`:

```html
<script>window.CIR_DESIGN_PREVIEW = {ui: 'new', view: 'login'};</script>
```

È un’eccezione deliberata **solo per l’anteprima consegnata**, non una preferenza
persistente o una configurazione di produzione. Il sorgente `index.html` senza
bootstrap mantiene UI OFF e dashboard dimostrativa iniziale; il futuro parametro
server mantiene default OFF. Il mock preserva lo stato globale quando si cambia
tenant, ma il controllo non compare prima dell’accesso.

Tavole web in ordine: login desktop, login mobile, home desktop, home mobile,
incidente desktop, incidente mobile, menu mobile aperto, impostazione globale.
Le tavole sono composizioni native e non screenshot browser; il mock HTML è la
proposta interattiva da valutare, senza modifiche ai template dell’applicazione.
