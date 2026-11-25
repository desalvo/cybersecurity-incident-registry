# CIR 0.10.0-1 RC72 - CI plugin discovery test hotfix

Date: 2026-11-25. Baseline: RC71 cumulative source (including the revised
87-slide presentation). Source of failure: `logs_123624448728.zip`.

## Observed failure

In the GitHub Actions `Tests, PostgreSQL, SCA and offline gates` job, the
complete Python suite ended with `1 failed, 1049 passed, 30 skipped`
(and 186 passing subtests). The sole failure was
`tests/test_visual_training_rc71.py::test_available_plugins_not_confused_with_core_features`.
The test enumerated every directory inside `app/plugins/`, including Python's
runtime `__pycache__`, and mistakenly treated that cache as an application plugin.

The real browser/documentation job completed successfully: 25 authenticated
screenshots, an 87-slide PowerPoint and a matching 87-page PDF passed its QA.
No runtime plugin defect or presentation content defect was evidenced.

## Change

The test now discovers only Python package directories containing an
`__init__.py` file. Runtime caches and unrelated folders are ignored, while a
new valid plugin package is still discovered and would need explicit coverage
in the expected-plugin assertion. AlBot and Alfresco registration and the five
AI engines remain checked.

A regression test creates both valid plugin packages and runtime/cache folders;
it verifies that `__pycache__` is excluded but a new valid package is included.
No runtime files, plugin settings, or slides were changed in RC72.

## Local verification

Run from the project root:

```bash
mkdir -p app/plugins/__pycache__
python -m pytest -q tests/test_visual_training_rc*.py
```

The 37 RC58-RC72 visual-training tests passed locally with the cache directory
present. Re-run the full GitHub Actions pipeline to confirm all gates for the
new commit; no claim of remote CI success is made by this local test.
