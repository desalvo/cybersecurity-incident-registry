# CIR 0.10.0-1 RC67 - Same-run browser screenshot embedding on slide 70

The pull-request job from `logs_123409526558.zip` (25 November 2026) passed the Python application suite, real PostgreSQL integration and the browser capture step. The last documentation step built a 79-slide PowerPoint and a PDF, but `scripts/verify_visual_training_rc64.py` rejected the deck:

```
Visual training QA FAILED: Screenshot CI non incorporata nel PPTX: spam-incident-config-labels
```

## Root cause

In `scripts/build_training_visual_rc64.js`, the `rightPanel` renderer returned as soon as a slide had the `photo_art` field. Slide **70** still has its correctly pinned synthetic `visual_70.jpg` in the editorial specification, and also maps to the mandatory real browser screenshot `spam-incident-config-labels`. The early `photo_art` return prevented the screenshot from being embedded, although the screenshot manifest was valid and the image had been captured.

## Correction

* For slide 70 **only**, when the authenticated browser manifest provides `spam-incident-config-labels`, the renderer now displays the unmodified screenshot in the right panel using **contain** sizing. The synthetic illustration remains the local/offline fallback when the same-run screenshot has not been supplied.
* Speaker notes identify the screenshot's CI commit provenance when the screenshot is used; the fallback is still explicitly identified as synthetic artwork.
* The independent QA now inspects `ppt/slides/slide70.xml` and its relationship file, then compares the SHA-256 digest of the image **actually referenced by slide 70** with the verified browser manifest. A media file present somewhere in the PPTX but not linked to slide 70 cannot falsely satisfy the gate.
* Existing checks on browser origin, commit/build identity, SHA-256, screenshot path isolation, 79-slide/79-page structure, allowed synthetic media and the 5 other mandatory screenshots remain unchanged.

## Regression tests and CI contract

`tests/test_visual_training_rc67.py` contains source-priority and slide-image-relationship tests, plus an optional end-to-end PptxGenJS test using temporary synthetic test rasters. These rasters never become distributed slides or claimed application screenshots. The end-to-end test proves successful embedding, then deliberately unlinks the image from slide 70 while leaving the media bytes in the archive, and verifies that the QA rejects the tampered presentation.

The RC67 local documentation regression run passed **82 tests and 48 subtests**. The application tests are **not run locally** because Flask is absent in this environment. The real PR job remains the final proof of screenshot embedding with the current browser manifest. No application database, UI code, workflow, runtime, or official RC64 presentation content changed; the CI-generated same-run presentation will contain the updated screenshot on slide 70.
