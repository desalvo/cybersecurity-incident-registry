# CIR 0.10.0-1 RC88 — workflow terminology and complete screenshot appendix

The first five slides in chapter **04 — Workflow e cataloghi** teach, in order,
what a workflow is, what incident categories are, what steps are, how conditional
steps work and which configuration resources depend on those steps. Only after
these concepts does the SPAM example appear. The first selected category SPAM
selects that tenant's SPAM workflow, if present; otherwise the configured
fallback/default workflow is used. Later categories classify the incident but
do not combine multiple independent workflows.

Workflow-card and category/data-type close-ups use lossless pixel crops from the
same application captures used for the training gallery. The six workflow
cards appear individually for readability; the two category/data-type regions
are shown at full slide width. Crops are reproducible by
`scripts/training_image_roi.py` from original screenshots and fractional ROIs.
The original bytes are not modified or retouched.

The final appendix has **both** dedicated preview slides (compiled PDF and an
unsent notification) **plus all** browser screenshots in the CI manifest,
including `pdf-generated-preview` and `notification-preview` as gallery items.
The only excluded screenshot is `classic-registry-desktop`. Every gallery slide
links to exactly the checked/hashed original browser file. The current CI run
must provide the populated app-generated PDF (validated separately as a PDF and
as a rasterized page) and the genuine unsent notification preview.

The offline editorial version includes every checked-in historic CIR
application screenshot except the classic UI and explicitly says these are
**historical** images. They are not presented as captures of the current CI
commit. The dedicated PDF/notification preview pages remain empty in this
edition when their current-run authenticated evidence is not available, rather
than replacing them with fabricated UI. GitHub Actions must generate and
cryptographically verify the final complete version.

The intended title is **SCREENSHOT AUTENTICHE DELL'APPLICAZIONE**, not
"SCREENSHOT AUTENTICHE DELLA CI". Source-commit and SHA-256 remain in notes,
manifests and publication receipts.
