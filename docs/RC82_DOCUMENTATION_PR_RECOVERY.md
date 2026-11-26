# RC82 - Make main-branch UI documentation publication fail closed

## Symptom after merging RC81

The main-branch CI reported green and the real-browser documentation job could
produce valid screenshot artifacts, but no automatic documentation publication
pull request was opened. The checked-in editable visual training still showed
editorial notices indicating that screenshots would be added by a later CI run.

## Root cause

`release-scope` publishes `steps.diff.outputs.documentation_needed`, and
`documentation-publication` requires that value to equal `true`. In non-manual
main-branch pushes, `scripts/documentation_publication_policy.py` emitted a
**different key**, `publication_needed`. The publication job therefore saw an
empty value and was silently skipped. This was not a screenshot acquisition
failure and did not imply that the published PowerPoint/PDF were up to date.

## Fix and safeguards

- The policy CLI now emits `documentation_needed=true|false`, matching the
  workflow's actual output contract. Ordinary application, authored slide,
  generator, and workflow changes return `true`; merges containing only
  automatically generated documents and digest metadata return `false`.
- Manual dispatch on `main` always requests documentation publication and
  leaves Docker optional. Tag pushes explicitly report that no documentation
  PR is requested.
- `release-scope` fails when either production or documentation policy returns
  an empty/unrecognized output instead of letting a green pipeline skip the
  required publishing job.
- In strict CI mode, the visual PowerPoint verifier rejects visible captions
  promising that screenshots will be added in a future CI run. Editorial
  offline exports may retain their correctly labeled illustration placeholders.
- The normal strict CI validation still requires the exact same-run
  authenticated screenshot hash on a real slide, an appendix slide for each
  screenshot, and visual checks of every corresponding PDF page. The
  publication script checks the resulting receipt and operational PowerPoint.

## Expected sequence

1. Merge RC82's source changes into `main`.
2. The `push` run performs quality gates and authentic Chromium captures,
   builds the current operational and visual PowerPoints, and exports the PDF.
3. The `documentation-publication` job downloads the **same run**'s artifacts,
   verifies the documents and screenshots, and opens a separate PR updating
   only the current (non-RC-suffixed) GitHub documents.
4. Review and merge that PR to update `main`. Its generated-only merge must not
   create another documentation PR.
5. If a manual retry is needed, use **Actions -> CIR CI and Docker release ->
   Run workflow -> main**. This does not require a production Docker rebuild.

A GitHub Actions successful UI-documentation artifact does **not** imply files
were committed to the `main` branch. Only the reviewed publication PR merge
makes the verified documents available on `main`. The source release package
remains an editorial fallback until that pipeline runs; no synthetic test
fixture may be presented as an authentic browser screenshot.

## Verification

`tests/test_rc82_documentation_publication.py` exercises the policy's actual
CLI output contract for source and generated-only changes, checks the workflow
needs/guards, and rejects unresolved screenshot placeholders in strict mode.
A real GitHub run and a merge of the resulting publication PR are still
required to verify the end-to-end integration and update the actual repository.
