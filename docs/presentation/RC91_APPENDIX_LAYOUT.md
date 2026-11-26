# CIR 0.10.0-1 RC91: Visual training appendix and slide-copy corrections

The instructional sequence ends on slide 94. Slide 95 is the native PowerPoint
chapter separator **08 Appendici**. All authentic application-browser images
in the verified manifest, except `classic-registry-desktop`, then appear in
manifest order beginning at slide 96. The two dedicated, full-size previews
of a CIR-generated mapped PDF and a notification are moved from their former
positions 95-96 to the *end* of the appendix.

With the required 32 browser captures, 31 are visible: the dedicated preview
pages are now **Schermata 32 / 33 - Documento PDF compilato** (slide 127) and
**Schermata 33 / 33 - Notifica prima dell'invio** (slide 128). The full build
therefore contains 128 slides. Both preview captures also remain in the
complete screenshot gallery; their last-two-slide treatment provides extra
context rather than removing evidence. Only the classic UI is omitted.

In the editorial source edition, the 18 historical application screenshots
are retained, so the total is 115 slides. The final two preview pages are
clearly marked pending the next authentic browser CI capture rather than
showing synthetic placeholders falsely labelled as production screenshots.

The published receipt records a first gallery slide of 96 and an overall
expected count of `97 + visible_browser_captures`; independent same-run and
published validators check both the contents and the exact source SHA-256
of the preview images. On the CI build, the original generated PDF and its
raster are additionally validated together.

Editorial corrections retained:
- Slide 15: "La screenshot documenta due incidenti chiusi".
- Slide 16: "i casi chiusi non dovrebbero mai avere avvisi attivi.".

This directory's PptxGenJS builder is the source of truth for future CI runs;
manual PowerPoint edits alone are not sufficient.
