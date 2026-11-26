# RC77 — Catalog workflow: naming, category scope, severity reuse

This change is based on the confirmed RC72 merge plus the incremental RC73–RC76 documentation updates. It changes **catalog import behavior** only for new imports; existing installed workflow categories and historical names are not renamed or migrated automatically.

## Import rules

- Importing the catalog entry `SPAM` into a tenant with no conflicting name creates a tenant workflow named **SPAM** and a category named **SPAM**. Neither receives the internal `[Catalogo ...]` suffix.
- The category is the workflow scope, not a shared severity. A new catalog copy **must not reuse an existing category**, even when it was inherited from Tenants Default. If `SPAM` is already a workflow name *or a category value* in the destination, the next free paired names are **SPAM v2**, **SPAM v3**, etc. This preserves previously created workflows and inherited categories without changing their steps.
- Only **severity** labels are reconciled by their visible name (case-insensitively) when importing the workflow dependency graph. An existing tenant severity is reused by ID, with its local description and configuration untouched. This includes existing Tenants Default replicas synchronized into the tenant.
- Unrelated action labels, affected-data labels, notifications, and PDF dependencies preserve the existing identity/provenance remapping and copy isolation; name-only deduplication is **not** expanded to those types.
- Workflow imports as the **tenant default** have no category scope and keep the existing default-workflow safeguards.
- Names shown in the modern and classic navigation menus are consistently **Workflow incidenti**. Existing route names and URLs are kept compatible.

## Tests and verification

`tests/test_workflow_catalog.py` exercises the actual database service for first imports, repeated `SPAM` imports, conflicting existing categories, mapping conditions to existing severity IDs, and preservation of pre-existing configuration. `tests/test_rc77_catalog_import_policy.py` includes an environment-independent naming contract regression.

Full Flask/database integration tests require the dependencies from `requirements.txt` and PostgreSQL integration tests require the configured CI database. The local execution environment in this session does not provide Flask or access to the package index, so only dependency-free tests and syntax checks can be completed here. GitHub CI must run the full regression suite before merging.

## Cloning a tenant: generic default only

- Creating a tenant from another operational tenant, or from Tenants Default, retains cloned tenant configuration but **does not copy category-specific workflow steps**. Workflow definitions are installed later by an administrator from the workflow catalog.
- A newly provisioned tenant always has a usable, independent default workflow comprising **Apertura → Analisi → Conclusione**, even when its source has no default or has a customized default. This is an actual `IncidentWorkflowStep` definition with `category_id = NULL`, not an empty placeholder.
- Re-running the clone operation is idempotent for the default workflow: it does not overwrite or replicate an already configured default. Existing manually imported category workflows in an established destination are not removed by a re-clone.
- Workflow export, source clone and deletion selectors show only workflows with actual steps; category labels without steps are not described as installed workflows. Empty categories remain available when explicitly choosing a destination scope to create a new workflow manually.
- The regular tenant administration form and the setup Wizard use the same cloning service and therefore enforce the same invariant.
