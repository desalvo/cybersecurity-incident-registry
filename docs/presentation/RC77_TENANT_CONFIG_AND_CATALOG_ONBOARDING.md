# RC77: tenant setup and workflow catalog onboarding (slides 39–48)

The training deck explains a three-phase tenant onboarding process:

1. The tenant admin (or a super admin) configures the tenant's own parameters from Admin pages or through the repeatable/resumable setup Wizard. Only a super admin may create or clone tenants.
2. The admin imports one or more specific workflows from the Tenants Default catalog for each required operational process, e.g. SPAM. The import creates an equally named category. Import collisions select `SPAM v2`, then `SPAM v3`; matching tenant severity labels are reused.
3. The admin verifies the resulting category, workflow steps, conditions, dependencies, notifications and roles before operators create incidents.

**Important distinction:** The new tenant always starts with a real, usable generic default workflow (`Apertura → Analisi → Conclusione`), not a set of empty workflow placeholders. Catalog import is necessary for the intended **specialized procedures**, not a precondition to using CIR's minimal generic incident workflow. Cloning another tenant does not transfer its specialized workflow definitions.

Original CIR slide 35 (physical slide 41) illustrates the Wizard via the authenticated CI screenshot; original slides 37 and 42 reinforce the responsibilities and catalog sequence. Generated PowerPoint and PDF must be rebuilt from this specification after every relevant application or documentation change.

### Exact workflow catalog navigation

Modern UI: **Amministrazione → Workflow e catalogo → Catalogo workflow**. Classic UI: **Admin → Anagrafiche e workflow → Catalogo workflow**. Choose a current Tenants Default workflow, verify the destination tenant, and click **Crea una nuova copia nel tenant**. The workflow and category receive the same conflict-free name; existing severity labels are reused.
