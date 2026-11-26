# RC92 - Workflow lifecycle, shared default and incident UI

Version: 0.10.0-1 (release candidate RC92). Baseline: RC91.

## Workflow management

- Tenant administrators may use **Rinomina workflow** from the workflow administration page.
  Renaming changes the tenant-owned workflow name and its corresponding first-category
  label together, retaining stable IDs, steps, and incident associations.
- A requested name that already belongs to another workflow **or category** in that
  tenant (case-insensitively) is rejected. Explicit rename never invents `v2`, `v3`, etc.
- Imported workflow deletion removes its steps and lifecycle state and releases the
  copied category **only if** that category is not used by incidents, incident
  templates, or shared-default replication. Historical import receipts are retained
  for auditing but do not reserve the deleted name.
- Empty workflow states and safely removable orphan categories are cleaned at
  workflow-maintenance/import boundaries. The tenant default workflow is protected
  from deliberate deletion and its last step is protected from manual removal.
- On tenant setup and synchronized Tenants Default changes, the tenant's default
  workflow is copied from the Tenants Default default, resolving tenant-owned action
  labels. If an existing incident uses an incompatible historical default, the
  replacement is deferred and logged instead of rewriting incident history.
  Where the shared default has not been configured, initial tenant provisioning
  retains a generic three-step default until one is available.

## Incident categories

- The category palette shows a distinct amber chip with a text label **Senza
  workflow specifico** when a category has no category-specific workflow installed.
  Its tooltip explains that if this category is selected first, the tenant default
  workflow applies. The chip remains draggable and selectable.
- The status is derived from installed workflow steps, not simply whether the
  category originated in Tenants Default.

## Procedural step cards (modern incident UI)

- Workflow phase cards wrap to additional rows instead of requiring horizontal
  scrolling; cards are never compressed into an unreadable horizontal strip.
- Step order and activation remain unchanged. Connectors follow actual layout:
  right arrows within a row, diagonal connectors at row boundaries, and down
  arrows when consecutive cards share a column.
- The renderer recomputes connector placement on resize and expansion of the
  incident's workflow panel. The classic interface keeps its existing grid.

## Verification

Run the local regression tests (Flask from the offline Python 3.13 wheelhouse):

```sh
python -m pytest -q \
  tests/test_rc92_workflow_wrap.py \
  tests/test_workflow_lifecycle.py \
  tests/test_workflow_import_dedup.py \
  tests/test_tenant_defaults_core.py \
  tests/test_rc77_tenant_clone_default.py \
  tests/test_modern_ui_incident_albot.py
```

The browser layout test is skipped when Chromium or Playwright is not installed.
GitHub Actions should run the full test suite and browser/tenant-integration jobs.
