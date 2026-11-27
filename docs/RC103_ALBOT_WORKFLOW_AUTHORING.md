# CIR 0.10.0-1 RC103 — AlBot workflow authoring

## Scope

AlBot can produce a reviewed workflow from a tenant administrator’s natural-language description. It supports both a new workflow and a modification to an explicitly named existing workflow. The super admin can operate within **Tenants Default**. The system-generated proposal is never executed as code and is never imported automatically.

- **Draft/preview:** user question → configured AI provider → restricted declarative JSON schema → local validation → expiring, owner/session/tenant-bound preview. The preview displays names, ordered steps, types, required flags, descriptions, deadlines, descriptive obligations, conditions, prerequisite completion links, available notification types, document templates and section targets.
- **Export:** downloadable `cybersecurity-incident-registry.workflow-catalog.v1` JSON; no write is performed. Export-only drafts cannot be imported via the confirmation endpoint.
- **Import/update:** POST, normal CIR CSRF validation plus explicit confirmation checkbox, active-tenant admin authorization, super admin only for Tenants Default, optimistic fingerprint/staleness checks and workflow-scoped database lock. The step replacement, action-label creation and audit occur in the same transaction.
- **Prevent destructive changes:** updates cannot overwrite workflows currently associated with incidents. Generate a separately named version instead. Unrequested removal/rename of old steps is rejected. Other tenant workflows and shared action-label metadata cannot be overwritten.
- **Step prerequisites:** `step_completed` action-label references are accepted by the portable catalog validator only when they target a prior step. References are mapped upon catalog copying/import and Tenants Default propagation. The incident display shows blocked prereqs, and manual execution routes check that the prerequisite action exists. Visibility conditions based on severity, personal-data risk or data type remain distinct from step completion.
- **Safety:** no direct LLM database tools, SQL, code execution, or cross-tenant resource lookups. 32-hex random draft token, 30-minute expiry, owner/session/tenant validation, no mutation on GET; secure file permissions. The AI model is not relied on for authorization or referential integrity.

## Example prompts

Create: "Crea il workflow Verifica avviso con tre step: Ricezione (obbligatorio), Analisi (dopo Ricezione, solo se dati personali), Chiusura (dopo Analisi); mostra l'anteprima."

Update: "Aggiorna il workflow Verifica avviso: aggiungi Verifica evidenze dopo Analisi e fai dipendere Chiusura da Verifica evidenze; mantieni gli altri step. Mostra l'anteprima."

JSON only: "Genera e scarica soltanto il JSON del workflow Revisione segnalazione, con step apertura, controllo, archiviazione; nessuna importazione."

## Validation and release status

- Python syntax/compile checks, PptxGenJS builds and PDF render checks are local gates.
- Flask integration tests in `tests/test_albot_workflow_authoring.py` and regression checks in `tests/test_modern_ui_incident_albot.py` require the project Python dependencies and configured CI environment. A source-only build is **not** a substitute for real backend/CI execution.
- Presentation PDFs and PPTX files are distributed separately; avoid reintroducing large generated binaries into the main Git history.
