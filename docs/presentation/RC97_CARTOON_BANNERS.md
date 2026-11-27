# RC97 — Cartoon chapter banners and thank-you illustration

- Seven original approved chapter cartoons replace chapter background-only slides while preserving editable section titles at slides **2, 18, 37, 48, 64, 76, and 89**.
- A standalone cartoon **Grazie!** slide is inserted as slide **95**, after the final conclusion and before the appendix.
- The **08 Appendici** divider is now slide **96**, with its own cartoon illustration. The verified application screenshot gallery begins at **97**.
- The editorial package includes 116 slides (98 base slides including the new closer, plus 18 historical application screenshots). The complete CI version contains the number of current-run manifest screenshots minus the classic UI.
- `rc97_cartoon/provenance.json` pins every approved original illustration by SHA-256, including the thank-you illustration; neither these cartoons nor the approved anonymized document are authenticated browser captures.
- The current browser screenshot manifest remains mandatory in CI, and the publication receipts and all screenshot/gallery validation are still enforced.
- The composite artwork is packaged in `docs/presentation/rc97_cartoon`; no photographs or licensed third-party characters are included.

## Updating the material

Edit `scripts/build_training_visual_rc64.js`, never only the rendered PPTX. Regenerate using Node/PptxGenJS and verify with `scripts/verify_visual_training_rc64.py`. Keep `scripts/published_visual_training.py` and the PDF gallery verifier aligned when adding slides.
