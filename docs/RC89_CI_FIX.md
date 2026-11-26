# CIR 0.10.0-1 RC89 - CI evidence contract and training regressions

## Diagnosed failure

GitHub Actions PR logs `logs_123930416059.zip`, commit
`7827699c2111eb59974e72c68b9b68a091ba69d9`, run 45806252685:

- Real browser capture succeeded with 32 screenshots.
- The PDF/manual builder stopped in `ui_documentation_evidence.load_evidence`:
  `Unapproved screenshot element selector: tenant-wizard-next-step`.
- The Python quality job had 10 legacy slide-layout/source expectation failures
  (1179 passed, 35 skipped), most involving the newly inserted workflow
  introduction and the expanded screenshot gallery.

## RC89 corrections

1. Synchronize all 32 mandatory capture IDs between the browser capture set,
   the manifest verifier and the 61-slide operational presentation source.
   Preserve the genuine PDF and notification previews; continue to exclude
   the classic UI from the public visual-training gallery.
2. Pin the second-step wizard capture to `.setup-wizard-shell` and
   `/admin/setup-wizard` and verify intrinsic dimensions, SHA-256, mode,
   authenticated state and same-source commit. Do not relax the selector
   allowlist or accept arbitrary DOM crops.
3. Embed the new wizard and notification previews in actual screenshot slides
   in the secondary operational deck, with explicit captions; reject a
   screenshot that is declared in JSON but not rendered.
4. Update regression checks to target stable original slide IDs and current
   insertion offsets. The base visual deck contains 96 slides, followed by
   every visible sealed screenshot in the CI appendix. Tests still require
   source-linked images rather than unverified media in the ZIP.

## Validation

Run with a Python 3.13 environment installed from the offline wheelhouse
(`cir-wheels-py313.zip` at the root of the user's ChatGPT Library):

```bash
python -m pytest -q tests/test_ui_documentation_evidence.py \
  tests/test_training_presentation_builder.py \
  tests/test_rc89_visual_evidence_regression.py \
  tests/test_visual_training_rc69.py tests/test_visual_training_rc70.py \
  tests/test_visual_training_rc74.py tests/test_visual_training_rc76.py
```

On GitHub, review the `Real UI screenshots and documentation` job separately
from `Tests, PostgreSQL, SCA and offline gates`; the isolated capture must
produce 32 same-run images and the documentation builder must validate them.
Test-created images and manifests never count as CI screenshot evidence.

## Packaging

Cumulative `.tar.zst` distributions must contain only repository payload, not
`.git` or refs/heads/master. Validate the archive member list before release.
