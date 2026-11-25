# CIR visual training RC63 - photographic illustration review

The 26 conceptual right-hand panels were fully rebuilt from three **original synthetic, people-free** CGI image sheets created specifically for CIR. Every source and derived panel has a pinned SHA-256 digest in `visual_rc63_art/provenance.json`.

## Layout policy
- The photographs contain **no slide titles, no captions, no header/footer and no page numbers**.
- All image compositions are shown in full. The 1.25:1 panoramas have a blurred photo extension where necessary rather than cutting left/right content.
- Images are bright, photo-realistic, artistic CGI. No real people and no stock photos are intentionally used.
- **Real CIR UI screenshot provenance is retained separately**, with hash verification in CI. Synthetic artwork is not presented as UI evidence.
- This change is purely editorial: incident data and application logic are unchanged.

Run `python scripts/check_training_visual_sources_rc63.py` and `node scripts/build_training_visual_rc63.js <destination.pptx>` to build.

No generated photograph contains a presentation title or presentation footer; the presentation itself retains its regular navigation chrome.
