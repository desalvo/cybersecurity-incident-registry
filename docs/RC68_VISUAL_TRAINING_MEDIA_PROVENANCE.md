# RC68 - Same-run browser media provenance in visual training

## CI failure and cause

The 2026-11-25 pull-request run recorded in `logs_123419120702.zip`
completed application tests, PostgreSQL integration tests and browser capture,
then produced the 79-slide visual PowerPoint and its PDF. The final
`verify_visual_training_rc64.py --require-ci-images` gate failed with:

`Visual training QA FAILED: Media del PowerPoint senza provenienza CIR: 11 file`

The verifier accepted the SHA-256 hashes of the six mandatory screenshots only,
but the generator also embeds additional same-run browser screenshots including
login, registry, workflow and documentation captures. Those images are not
unlicensed images: they come from the same verified browser manifest.

## Correction

Every screenshot listed by the current browser manifest must first pass:

- unique, validated screenshot ID and relative image path;
- file existence, containment within the manifest directory, and no symlinks;
- exact SHA-256 match against the manifest row;
- same Git commit/build in the GitHub CI environment;
- isolated synthetic fixture provenance on CI browser manifests.

After validation its digest may appear in the PowerPoint media pool. Images not
traced to checked-in CIR assets, approved synthetic artwork, or the validated
same-run screenshot manifest still fail the provenance gate.

The six mandatory screenshots must still be embedded, including the specific
`spam-incident-config-labels` image linked to **slide 70** rather than merely
present in the PPTX media directory. Obsolete artistic slide-like images and
classic UI imagery remain rejected.

## Regression and limitations

The RC67 fixture previously hid this issue because it supplied the same six
screenshots that the verifier allowed. RC68 adds a disposable 25-capture
end-to-end fixture plus negative tests for altered hashes, unsafe image paths,
foreign PPTX media, and mismatched commit/build metadata. No mock screenshot
is used in release deliverables.

Only the provenance verifier, its tests, and development notes change. No
application, tenant inheritance, slide content or illustration is changed.
A full PR run with actual Chromium screenshots remains required to confirm the
fix in GitHub Actions.
