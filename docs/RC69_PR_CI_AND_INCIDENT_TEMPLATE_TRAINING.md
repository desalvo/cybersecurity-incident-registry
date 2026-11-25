# CIR 0.10.0-1 RC69 — automatic PR tests and incident opening training

## CI error
Automatic PR run `logs_123590726294.zip` fails two tests in
`tests/test_rc2_training_and_brochure_media.py`: multiple independently identified
screenshots in the generated receipt may resolve to the same embedded PPTX
media filename. This is legitimate when byte-identical media is reused by the
PowerPoint library. Each screenshot record, including its unique ID and SHA-256,
is now individually validated. Conflicting hashes, missing media, duplicate
screenshot IDs and unapproved media are rejected.

## Training addition
Six new slides are inserted immediately after section 02 begins (historical slide
14), preserving the original 79-slide `visual_rc64_spec.json` and image provenance
numbers. The resulting editable training presentation has 85 slides:

1. From the incident registry to the New Incident button (archived real UI screenshot,
   or verified current-run Chromium screenshot when available).
2. Creating an incident from scratch (editable form diagram, not a fake screenshot).
3. Selecting an existing incident template in the new incident form, then reviewing
   auto-populated fields before creation.
4. Difference between incident templates and workflow/PDF templates; role boundaries.
5. Admin creation/edit/delete actions in the dedicated configuration page.
6. Copying a reusable template from an existing incident without actions/documents.

All additional explanatory diagrams are editable PowerPoint objects. The new
photographic image is synthetic, without people, and has a pinned SHA-256 provenance
manifest. Manual/document screenshots remain authenticated real-CIR captures and
are never reconstructed or claimed to be new screenshots.

The original category palette evidence is physically slide 76 after insertion,
while its original editorial ID remains 70. The QA validator checks the actual
PPTX slide relationship, not just a media-pool entry.

The complete GitHub CI must rerun to confirm the new PR; local checks do not
establish a green PR automatically.
