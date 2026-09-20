# Alfresco administration

Consolidated tenant-scoped Alfresco administration guide covering parent-node resolution, Site/documentLibrary fallback resolution, storage modes, delete/sync behavior, automatic incident reports, and incident directory/report naming.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `docs/ADMIN_ALFRESCO.md`
- `ALFRESCO_HOTFIX_0.9.0-1.md`
- `ALFRESCO_STORAGE_HOTFIX_0.9.0-1.md`
- `ALFRESCO_TENANT_SYNC_HOTFIX_0.9.0-1.md`
- `ALFRESCO_AUTO_REPORT_HOTFIX_0.9.0-1.md`
- `ALFRESCO_INCIDENT_NAMING_HOTFIX_0.9.0-1.md`

---

## Historical source: `docs/ADMIN_ALFRESCO.md`

Versione applicativa: **0.9.0-1 Hotfix 6**

## 1. Ambito

Il plugin Alfresco integra i documenti degli incidenti CIR con Alfresco Content Services tramite REST API. Ogni tenant CIR ha una configurazione Alfresco indipendente: abilitazione, endpoint, credenziali, destinazione e opzioni non sono condivise con gli altri tenant.

## 2. Configurazione per tenant

1. Selezionare il tenant da configurare come tenant attivo.
2. Aprire **Admin -> Plugins -> Alfresco**.
3. Verificare il nome mostrato in **Tenant configurato**.
4. Abilitare il plugin.
5. Inserire URL base Alfresco, username e password/API secret.
6. Configurare una destinazione con uno dei due metodi:
   - **Parent Node ID**: UUID della cartella Alfresco padre; ha precedenza sul Site.
   - **Site Alfresco**: CIR risolve automaticamente il container `documentLibrary` del Site.
7. Impostare la cartella destinazione relativa, ad esempio `Cybersecurity Incident Registry`.
8. Usare **Salva e testa destinazione**.

Per tenant diversi ripetere la procedura. I tenant non-default non ereditano credenziali Alfresco legacy non scoped.

## 3. Account e permessi Alfresco

Usare preferibilmente un account tecnico dedicato al tenant. Assegnare solo i permessi necessari sulla cartella destinazione: lettura, creazione/aggiornamento documenti e cancellazione se si vuole utilizzare la funzione **Elimina da Alfresco**.

Mantenere **Verifica certificato TLS** attiva. Se Alfresco risolve a un indirizzo privato, aggiungere l'hostname autorizzato a `CIR_OUTBOUND_PRIVATE_HOSTS` nel deployment CIR.

## 4. Struttura documentale

Ogni incidente usa una directory dedicata:

```text
<target_path>/
  incident-<id> - <nome-incidente>/
```

Se il raggruppamento per tipo è attivo, i documenti ordinari vengono collocati in sottocartelle come `pdf`, `office`, `images`, `archives`, `data` e `other`.

Il report PDF automatico dell'incidente, se abilitato, rimane direttamente in `incident-<id> - <nome-incidente>` con nome `incident-<id> - <nome-incidente> - report.pdf`.

## 5. Operazioni documentali

Quando il plugin è attivo per il tenant, CIR supporta:

- upload in **Solo CIR**;
- upload in **CIR + Alfresco**;
- upload in **Solo Alfresco**;
- download da Alfresco;
- upload/ripristino manuale verso Alfresco;
- cancellazione del nodo remoto con **Elimina da Alfresco** mantenendo il record CIR.

La cancellazione remota non viene forzata come permanente: il comportamento effettivo dipende dalla policy/cestino configurati sul server Alfresco.

## 6. Sync Alfresco

Nella sezione **Documenti** dell'incidente è disponibile il pulsante **Sync Alfresco** per utenti con permesso di scrittura, ma solo se il plugin del tenant è attivo.

Il Sync è intenzionalmente **read-only verso Alfresco**. Per ogni documento CIR che possiede un `alfresco_node_id`:

- verifica l'esistenza del nodo remoto;
- marca il documento come `present`, `missing` oppure `unknown`;
- aggiorna data e ora dell'ultima verifica;
- non effettua upload;
- non ricrea file mancanti;
- non modifica o cancella contenuti remoti.

Questo consente di rilevare file cancellati direttamente tramite l'interfaccia web Alfresco senza introdurre modifiche automatiche al repository.

## 7. Report automatico incidente

La visibilità e il default dell'opzione **Genera e aggiorna automaticamente report su Alfresco** sono configurabili per tenant da **Admin -> Tenant**. Il checkbox è visibile nel singolo incidente solo quando il plugin Alfresco del tenant attivo è abilitato.

Quando attivo, CIR aggiorna lo stesso nodo report se il contenuto cambia; se il nodo report non esiste più, il normale meccanismo di aggiornamento può ricrearlo alla successiva modifica rilevante dell'incidente. Il pulsante **Sync Alfresco** dei documenti non effettua questa ricreazione.

## 8. Diagnostica

Se **Salva e testa destinazione** fallisce, verificare:

- URL base e raggiungibilità dalla rete del pod CIR;
- `CIR_OUTBOUND_PRIVATE_HOSTS` per host privati;
- credenziali del tenant corretto;
- Parent Node ID o Site;
- permessi Alfresco sull'albero di destinazione;
- certificato TLS.

Per distinguere una cancellazione remota da un problema di rete, usare **Sync Alfresco**: HTTP 404/410 viene registrato come `missing`, mentre altri errori di comunicazione vengono registrati come `unknown` e dettagliati nei log server.

## Nomi delle cartelle incidente e dei report

CIR usa un nome leggibile derivato dal nome corrente dell'incidente e mantiene anche l'ID per evitare collisioni. Esempio per l'incidente 42 denominato `Phishing account amministratore`:

```text
Cybersecurity Incident Registry/
+-- incident-42 - Phishing account amministratore/
    +-- incident-42 - Phishing account amministratore - report.pdf
    +-- ...
```

I caratteri non utilizzabili in un path/nome file vengono normalizzati in modo sicuro; lettere accentate e spazi restano leggibili. Il medesimo schema viene usato per gli upload documentali e per il report automatico.

---

## Historical source: `ALFRESCO_HOTFIX_0.9.0-1.md`

Date: 2026-09-03

## Problem

Alcune installazioni Alfresco restituiscono HTTP 404 per upload verso il pseudo-nodo `-root-`, ad esempio `Unable to locate resource ... :-root-`. Il client CIR precedente costruiva la destinazione di upload partendo sempre da `-root-`, anche quando era configurato un Site.

## Correzione

La Hotfix 2 elimina l'uso operativo di `-root-` e risolve la cartella padre in modo esplicito:

1. se `alfresco_parent_node_id` e configurato, CIR usa direttamente quel node id;
2. altrimenti, se `alfresco_site` e configurato, CIR chiama `GET /sites/{site}/containers/documentLibrary` e usa l'id reale restituito dalla REST API;
3. se nessuno dei due e configurato, l'upload fallisce in modo fail-closed con un errore di configurazione, senza tentare un nodo implicito.

L'upload viene quindi eseguito su `POST /nodes/{parentNodeId}/children` mantenendo `relativePath` per la struttura `target_path/incident-<id>`.

## Configurazione amministrativa

La pagina **Admin -> Plugins -> Alfresco** aggiunge:

- `Parent Node ID opzionale`, con precedenza sul Site;
- `Salva e testa destinazione`, che salva i parametri e verifica che il nodo risolto sia accessibile con le credenziali configurate.

Il wizard iniziale espone anche il nuovo `alfresco_parent_node_id`.

## Sicurezza

- Base URL e URL finale continuano a passare dalla outbound/SSRF policy di CIR.
- I redirect HTTP restano disabilitati.
- Site e node id non vengono concatenati come percorsi arbitrari: il Site viene URL-encoded e il node id e validato prima dell'uso.
- Gli errori dettagliati restano nei log server; la UI amministrativa espone un messaggio generico in caso di test fallito.

## Compatibilita

- Le configurazioni che specificano gia un Site non richiedono necessariamente il Parent Node ID: CIR risolve automaticamente la `documentLibrary` del Site.
- Per repository/cartelle non appartenenti a un Site, configurare il node id UUID della cartella padre.
- Il campo `target_path` resta invariato.

## Verifica locale della hotfix

I test mirati Alfresco/wizard/outbound piu i test Hotfix 1 sono eseguiti prima del packaging. Poiche questa hotfix modifica il codice applicativo, l'immagine Docker deve essere ricostruita e sottoposta nuovamente ai gate production; `PRODUCTION_IMAGE_DIGEST` resta `PENDING_HOTFIX_REBUILD` fino alla nuova promozione.

---

## Historical source: `ALFRESCO_STORAGE_HOTFIX_0.9.0-1.md`

## Scope

Cumulative over Hotfix 1 (PostgreSQL advisory locks/sequences) and Hotfix 2 (Alfresco destination resolution). This hotfix is applied before rebuilding the production image.

## Changes

- General incident-document and action-attachment uploads now accept `.zip` and `.gz`. ZIP and gzip magic signatures are checked before saving. Specialized upload areas (logos, PDF form templates, AI knowledge parsing) retain their narrower format lists.
- Incident document upload exposes three storage modes when Alfresco is enabled: `Solo CIR`, `CIR + Alfresco`, and `Solo Alfresco`.
- In `Solo Alfresco`, the uploaded bytes are staged under `/tmp` only for the outbound transfer and deleted immediately afterwards. CIR keeps the `Document` record, filename, Alfresco node id/path and timestamp, but `stored_name` stays empty.
- A normal document download transparently redirects remote-only documents to the authenticated Alfresco download route.
- Every Alfresco upload is placed below `<target_path>/incident-<id>`.
- Optional `alfresco_group_by_type` (enabled by default) adds one safe fixed subfolder: `pdf`, `office`, `images`, `archives`, `data`, or `other`.
- Existing Hotfix 2 Parent Node ID / Site `documentLibrary` resolution remains unchanged; the unsafe/incompatible `-root-` fallback is not restored.

## Security

- `.zip` and `.gz` are treated as opaque uploaded attachments; CIR does not automatically extract them.
- Existing upload size limits remain enforced.
- Zip/gzip magic bytes are validated.
- Alfresco-only temporary files use restricted permissions and are removed in a `finally` block.
- Outbound SSRF policy, TLS verification policy and redirect blocking remain in force.

## Validation performed in the packaging environment

- Python syntax/compile checks: PASS.
- Static Hotfix 3 regression suite: 9 passed.
- Full dependency-backed suite must still be rerun on the release host before image rebuild.
- Real PostgreSQL suite, SCA and Trivy multi-arch gate remain mandatory before production promotion.

---

## Historical source: `ALFRESCO_TENANT_SYNC_HOTFIX_0.9.0-1.md`

Cumulative over Hotfix 4.

## Changes
- Alfresco configuration is strictly tenant scoped; non-default tenants do not inherit legacy unscoped credentials or destinations.
- Incident documents linked to Alfresco can be removed remotely while keeping their CIR record.
- Document records track Alfresco state (`present`, `missing`, `unknown`, `not_linked`) and last check time.
- Each incident exposes **Sync Alfresco** when the active tenant plugin is enabled. Sync only checks existing remote node IDs and updates CIR metadata; it performs no upload, recreation or remote mutation.
- Admin documentation now explains per-tenant setup, Parent Node ID/Site resolution, permissions, delete behavior and sync semantics.

## Deployment
This hotfix changes application code/schema. Rebuild and rescan the multi-arch image before production promotion. `PRODUCTION_IMAGE_DIGEST` intentionally remains `PENDING_HOTFIX_REBUILD`.

## Hotfix 6 - naming incidente Alfresco

Le cartelle Alfresco e il report canonico riportano ora il nome specifico dell'incidente mantenendo anche l'ID per unicità. Formato: `incident-<id> - <nome>` e `incident-<id> - <nome> - report.pdf`. I caratteri non sicuri per path/file vengono normalizzati.

---

## Historical source: `ALFRESCO_AUTO_REPORT_HOTFIX_0.9.0-1.md`

This hotfix is cumulative with Hotfix 1 (PostgreSQL advisory locks/sequences), Hotfix 2 (Alfresco destination resolution) and Hotfix 3 (ZIP/GZIP, Alfresco-only document storage and incident/type folders). The functional application version remains **0.9.0-1**.

## Automatic incident PDF report on Alfresco

When the Alfresco plugin is enabled, each incident can expose the option:

**Genera e aggiorna automaticamente report su Alfresco**

If enabled for the incident, CIR creates the canonical PDF report as:

`<alfresco target path>/incident-<id>/incident-<id>-report.pdf`

The report intentionally lives directly in the incident directory, independently of the optional `pdf/office/images/archives/data/other` grouping used by ordinary incident documents.

On subsequent report-relevant changes CIR computes a stable fingerprint of the data rendered by the incident report. A new Alfresco version is uploaded only when that fingerprint changes. If CIR already knows the report node ID it updates `/nodes/{nodeId}/content`; if the node was removed remotely (HTTP 404/410), it recreates the report in the configured incident directory.

Synchronization is triggered after successful incident creation/update/clone, action changes, relevant automatic actions, document upload/delete and generated-form confirmation. Alfresco failures are logged but do not roll back an already committed incident transaction.

## Tenant policy

Two tenant-scoped settings are available from **Admin -> Tenant**:

- **Mostra opzione nei singoli incidenti** - default: ON.
- **Attiva per default sui nuovi incidenti** - default: OFF.

The per-incident checkbox is rendered only when both conditions are true:

1. the Alfresco plugin is enabled for the active tenant;
2. the tenant policy allows the option to be visible.

If the tenant hides the option, the previously stored incident value is preserved. This allows a tenant to enforce a hidden default policy without a normal incident edit silently changing it.

## Persisted incident metadata

The incident table gains idempotent schema migrations for:

- `alfresco_auto_report_enabled`
- `alfresco_report_node_id`
- `alfresco_report_path`
- `alfresco_report_updated_at`
- `alfresco_report_fingerprint`

Full Export/Import automatically carries these fields through the existing model-driven serialization.

## Security and HTTP semantics

- No report synchronization is performed by the incident GET page; remote/database mutations remain tied to mutating application operations.
- Existing Alfresco outbound URL/SSRF validation remains active.
- Redirect following remains disabled.
- Existing remote report updates use the official Alfresco `PUT /nodes/{nodeId}/content` endpoint.
- A missing remote report is recreated using the already validated parent node/site destination logic.

## Image status

This hotfix changes application code. `PRODUCTION_IMAGE_DIGEST` remains `PENDING_HOTFIX_REBUILD`; the previously validated production image digest does not contain this hotfix.

---

## Historical source: `ALFRESCO_INCIDENT_NAMING_HOTFIX_0.9.0-1.md`

## Obiettivo

Le cartelle Alfresco dedicate agli incidenti e il report PDF canonico riportano ora il nome specifico dell'incidente, mantenendo anche l'ID CIR per garantire unicita e tracciabilita.

## Formato

Per l'incidente ID 42 denominato `Phishing account amministratore`:

```text
Cybersecurity Incident Registry/
+-- incident-42 - Phishing account amministratore/
    +-- incident-42 - Phishing account amministratore - report.pdf
```

Gli altri documenti dell'incidente usano la stessa cartella di base e, se configurato, le sottocartelle per tipo file.

## Sicurezza del nome

Il nome viene normalizzato NFKC, i caratteri di controllo e i separatori/caratteri incompatibili con i path vengono sostituiti, gli spazi vengono normalizzati e la parte descrittiva viene limitata a una lunghezza conservativa. Lettere accentate e spazi restano leggibili.

La versione funzionale resta `0.9.0-1`. La Hotfix 6 e cumulativa delle Hotfix 1-5. Non cambia il database e non richiede migrazioni schema aggiuntive.

Per documenti/report gia presenti su Alfresco con il vecchio naming, CIR non esegue una migrazione distruttiva automatica: i nuovi upload e le nuove creazioni usano il nuovo schema. Un report gia collegato continua a essere aggiornato tramite il suo Node ID Alfresco.

---
