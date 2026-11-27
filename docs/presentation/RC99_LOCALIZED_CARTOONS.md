# RC99: Italian-master cartoon localization

The source of truth remains the **Italian** presentation and nine accompanying art assets in `rc97_cartoon`. Section 02 is now split into two speech bubbles: the incident asks if it can close, and the CIR shield responds about 112 remaining steps. Section 03 has two different speakers: Tenant A asks to borrow SPAM, Tenant B gives the reply.

`rc99_cartoon_en` holds nine paired English illustrations, including the translated `Thank you!` sign. English speech appears inside the images, not as an unrelated subtitle. The CI runs `scripts/localize_cartoon_en.py` before creating the English PPTX. The specialized slide 37 image uses an approved bilingual two-speaker artwork pair, pinned by SHA-256. Its Italian counterpart remains the canonical source.

The two variants must have the same number/order of slides, the same authenticated CI screenshots, and the same non-cartoon media. Only the localized nine cartoons may differ by pixel bytes, with a source/derivative SHA-256 mapping in the English artwork provenance. Any change to the Italian source invalidates that mapping until its English partner has been updated.
