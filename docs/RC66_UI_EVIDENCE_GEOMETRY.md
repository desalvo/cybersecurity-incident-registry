# CIR 0.10.0-1 RC66 - Element screenshot evidence geometry fix

The pull-request CI log `logs_123402907608.zip` (25 November 2026) shows that **the full Python suite passed** (`1035 passed, 24 skipped, 182 subtests passed`), **real PostgreSQL integration passed** (`22 passed`), and **the browser captured all 25 screenshots**. The `Real UI screenshots and documentation` job then failed in `scripts/ui_documentation_evidence.py:191`, during the offline validation of the screenshot `spam-incident-config-labels`:

```
ui_documentation_evidence.EvidenceError:
Screenshot dimensions do not match viewport: spam-incident-config-labels
```

## Root cause and correction

Playwright intentionally captures the `#incident-main .dnd-layout` element containing the real CIR category and affected-data palettes, rather than a full viewport; it is narrower than the browser's 1920px desktop viewport. The evidence validator previously enforced the full viewport width for *every* screenshot and therefore rejected a valid element screenshot even though the capture job passed.

RC66 makes the capture geometry explicit and verifiable:

- `viewport` and `full-page` screenshots continue to require exact browser width. `viewport` screenshots also require exact browser height; `full-page` captures permit a larger height within the existing safety limit.
- Only the specifically approved `spam-incident-config-labels` screenshot may declare `capture_area=element` and the real CSS selector `#incident-main .dnd-layout`.
- The capture records `element_size` from the encoded JPEG dimensions. The offline validator compares those exact pixel dimensions to the manifest, checks the selector, requires a substantial bounded crop, and verifies that the region does not exceed the viewport width.
- The existing SHA-256, isolation, same-commit, release identity, route, mode, authentication, and first-fold documentation-cover requirements remain in place.
- The screenshot still depicts the real, unretouched CIR UI and is not replaced with generated or synthetic browser content.

## Tests and release gate

Local tests: `133 passed, 55 subtests passed` across screenshot provenance, real-browser capture contracts, training presentation, RC64/RC65 regressions and packaged documentation. A standalone Chromium capture of a 650x720 element within a 1920x1140 viewport confirmed the expected image dimensions. Python compilation completed successfully. This source candidate **has not yet been exercised through the full CI documentation build** and is not declared production-ready.

No application functionality, incident data, workflow state, or training artwork was altered. The visual PowerPoint/PDF RC64 remains the current presentation content; only the CI evidence pipeline and its tests were changed.
