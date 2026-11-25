# CIR 0.10.0-1 RC65 — PR CI remediation

This is a focused correction to the RC64 source candidate, not a functional release or a production sign-off.

The 2026-11-25 pull-request log (`logs_123393223579.zip`) reports two failing jobs:

* **Tests, PostgreSQL, SCA and offline gates**: five failed Python tests. A shared-label provenance check rejected `data_type` adoption even though the publishing/synchronization code correctly reused existing tenant data labels; the workflow lifecycle test likewise assumed an independent replica. The frozen original training deck lacked the final RC61 speaker-note sentence for authored slide 46.
* **Real UI screenshots and documentation**: Playwright searched for visible text `Alfresco`, but its first match was an invisible HTML `<option>`; the documentation capture now verifies the actual `Destinazione` select, selects `CIR + Alfresco`, and verifies the visible `Sync Alfresco` control.

## Changes

1. Validate provenance markers for pre-existing **category** and **data_type** labels only. Still enforce exact label kind, semantic value, source identity, tenant ownership, marker Boolean type and all other archive checks.
2. Update lifecycle assertions to expect reuse of both pre-existing choice labels; other workflow dependencies keep independent provenance and IDs.
3. Synchronize the frozen editable source PowerPoint's authored speaker notes from `content_it.json` (slide 46) and refresh its receipt SHA-256. Other presentation elements and media were not regenerated.
4. Correct the Playwright locator and add offline test cases for valid and forged inherited-label ownership, presentation-note alignment and browser-selector provenance. Expand the real-database test to validate a full exported archive with reused affected-data labels.

## Verification

Local Python 3.13 environment: `python -m pytest -q tests/test_rc65_ci_regressions.py tests/test_rc18_training_package.py tests/test_visual_training_rc63.py tests/test_visual_training_rc64.py`: **23 passed**. Modified Python modules compiled successfully. The full Flask/database/Chromium CI jobs must still run in GitHub Actions: Flask is unavailable locally. No passing CI status or production readiness is claimed.

The generated `CIR_Operational_Training_Visual_RC64.pptx` and PDF in the package remain RC64, since these failures did not require altering their visual content. The frozen source `CIR_Operational_Training_IT.pptx` receives the speaker-note fix only.
