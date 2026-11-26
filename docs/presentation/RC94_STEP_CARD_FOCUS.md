# RC94 — Workflow card close-ups and notification variables

The slide 61 callout shows six **complete, separate** workflow step cards,
including their numbered header, explanatory text, action description,
status/deadline information and the final button. Previously the crops stopped
about 70 pixels before the bottom of each card, and successive crops drifted
rightward; the cropped image was not a complete picture of steps 2-6.

The checked-in historical SPAM screenshot contains 1920×3862 pixels. Each of
its six first-row cards spans approximately y=504–919 px, and the corrected
individual ROIs retain a small margin around each complete card. No new UI
pixel is synthesized or interpolated.

For current Chromium CI runs the `workflow-steps-focused` browser **element**
screenshot records `step_card_rois` measured directly from the real DOM for
its first six `.workflow-step-card` elements. This avoids assuming that the
responsive layout has the same six-column arrangement as the archived image.
The evidence validator bounds-checks and rejects overlapping or clipped ROIs;
PowerPoint generation and verification derive lossless PNGs from exactly those
regions and the SHA-256-verified source screenshot. The 13 original steps and
all other screenshots remain available in the authenticated gallery.

Slide 63 now explicitly notes that `%NAME%`, `%REFERENCE%` and `%START%` are
examples only, and that many additional notification template variables are
explained in the CIR manual. The speaker notes repeat this guidance.

This is a change to the visual training generator, capture metadata, validators,
regression tests and authored slide text, not a change to the workflow engine.
