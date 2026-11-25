# CIR 0.10.0-1 RC60 — CI hotfix

## Evidence

`logs_123309413943.zip` from 2026-11-25: quality gate `python -m pytest -q` passed (1005 passed, 24 skipped, 182 subtests passed). Browser documentation job failed at `Capture and test the real application interface` with a bare `AssertionError:` after the RC59 checkbox fix.

## Cause

`capture_ui_screenshots.py` erroneously expected the generated PDF preview to still contain a field named `RIFERIMENTO` in `PdfReader.get_fields()`. However, `generate_pdf_from_template()` intentionally paints the incident values on the page canvas and strips the AcroForm widgets. Only the source PDF template remains editable. This was a CI assertion contract error, not a defect in the PDF generation implementation.

## Remediation

- Validate HTTP 200, valid PDF bytes and non-empty pages.
- Ensure generated PDF has no AcroForm fields or widget annotations.
- Extract text and confirm that the fixture-derived synthetic incident reference is printed on the final PDF page.
- Preserve existing checks that the source template has three mapped AcroForm controls.
- Emit sanitized Python traceback and completed screenshots in `failure.json` and CI stderr if the browser capture fails again.
- Add four independent regression tests for valid flattened PDF, missing value, interactive PDF and invalid PDF.

## Validation gates

This is a source release candidate. The full application browser capture, PostgreSQL checks and production publication must still pass the GitHub Actions run for the actual PR SHA. No screenshots were synthesized to bypass the gate.
