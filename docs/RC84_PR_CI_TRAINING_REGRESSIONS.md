# CIR 0.10.0-1 RC84 — PR CI regression fix

## Evidence

The user-supplied GitHub Actions archive `logs_123747275266.zip` from 26 November 2026
shows the `Tests, PostgreSQL, SCA and offline gates` job failing at `Run complete pytest suite`:

- `tests/test_rc75_tenant_wizard_training.py::test_tenant_wizard_is_captured_from_authenticated_browser_and_embedded`
- `tests/test_visual_training_rc67.py::test_browser_palette_has_precedence_over_the_original_photo`

Actual CI summary: **2 failed, 1,155 passed, 34 skipped, 188 subtests passed**.
The failures are static source assertions requiring the RC75/RC67 direct image insertion
`slide.addImage({path:wizard.path` and `slide.addImage({path:categoryPalette.path`.
RC83 introduced `addCiZoom` to preserve source screenshot bytes while embedding both
an overview and a PowerPoint-native crop, so these old assertions no longer identify
correct behavior. The builder logic remains unchanged by RC84.

`Real UI screenshots and documentation` completed its bundle seal with
`Documentation bundle: PASS (16 verified artifacts; ...)` in the supplied log.
This is evidence of that PR job only, *not* evidence that a publication PR has
been opened or that the entire pipeline is green.

## Changes

1. Update the RC75 wizard regression to require the verified wizard dispatch into
   `addCiZoom(slide,wizard)` and source preservation through both native PPTX
   image insertions.
2. Update the RC67 category palette regression to require preferential CI screenshot
   dispatch into `addCiZoom(slide,categoryPalette)` before editorial fallback.
3. Update the optional RC67 end-to-end fixture from obsolete `real_browser` manifest
   syntax to RC83's strict `real-application-browser` and
   `isolated-synthetic-fixture` contract. Fixture pixels remain synthetic and disposable,
   never release documentation screenshots. The existing validator still requires
   same-run source checksum linkage and rejects detached images on slide 79 and the
   instructional laboratory slide 71.

No application logic, generator behavior, workflows, screenshots, PPTX, or PDF were
modified. The CI will regenerate its own source-commit-bound, authenticated browser
documentation after the changes are pushed.

## Validation and limitations

Local targeted suite: **15 passed**, including the Node/PptxGenJS end-to-end test
and RC83 native zoom + publication accountability tests. Full local pytest collection
was also attempted but cannot run in this runtime due to missing Flask/Werkzeug
and related application dependencies (15 import errors at collection time).
The GitHub Actions runner installs these dependencies and previously ran 1,155 tests
successfully. No subsequent GitHub CI or GitHub documentation PR is claimed.

## PR workflow

Apply RC84 as an incremental patch on top of RC83 in the existing PR branch.
Rerun CI. Before merging, confirm both the quality-gates and documentation jobs are
green. Following the merge to `main`, check `documentation-publication` and the
`documentation-publication-accountability` fail-closed gate: the publisher must
return `pr-opened` or `already-current`; a job marked skipped or failed is unacceptable
when publication is required.
