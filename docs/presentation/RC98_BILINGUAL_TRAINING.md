# RC98 - Automatic bilingual training presentation

**AUTHORITATIVE SOURCE: ITALIAN ONLY.** The Italian slides and their
`visual_rc64_spec.json` / Italian addenda are the **single source of truth**.
English slides are always a derivative generated from that master, not an
independently maintained deck. Edit or rearrange the Italian slides first;
update the English translations only after the Italian changes are accepted.
Never edit the generated English PPTX or PDF directly.

The translation catalog carries a SHA-256 fingerprint of each Italian master
slide (title, bullet points, structure, speaker notes and reference number).
If an Italian slide changes, **the Italian build keeps working**, but the
English build fails explicitly until its translation and pinned fingerprint
are reviewed and updated. The pipeline must never publish an out-of-sync
English deck. Recompute fingerprints using:

```sh
CIR_DUMP_ITALIAN_MASTER_FINGERPRINTS=1 node scripts/build_training_visual_rc64.js
```

Review the diff and update `italian_master_fingerprints` in
`visual_rc98_english_slides.json` only alongside the corresponding English
translation update. CI always generates IT first and EN second, from the
same Italian source tree and screenshot manifest, and verifies equivalent
slide order, exact application-screenshot hashes, localized cartoon asset provenance, and gallery coverage.

CIR builds the **same visual training deck** in Italian and English. The
presentation sources and screenshot evidence remain shared; the English copy
uses checked-in translations, with no third-party translation service in CI.

| Locale | PowerPoint | PDF |
|---|---|---|
| IT | `CIR_Operational_Training_Visual.pptx` | `CIR_Operational_Training_Visual.pdf` |
| EN | `CIR_Operational_Training_Visual_EN.pptx` | `CIR_Operational_Training_Visual_EN.pdf` |

The same-run CI job creates both pairs, verifies the English content, page
count, native notes, and exact screenshot SHA-256 linkage, then seals separate
receipts. The publication job uploads all four artifacts (plus the operational deck and PDF screenshot gallery) directly to a **commit-scoped GitHub Release** after the main CI checks pass. Stable download links are at `https://github.com/desalvo/cybersecurity-incident-registry/releases/latest/download/` and the source checkout contains no generated presentation binaries. Documentation publication does not create an automatic chore PR; production image digest changes are handled independently.

Local reproduction (Node.js 22, PptxGenJS, Python/Pillow, LibreOffice):

```sh
CIR_TRAINING_LOCALE=it node scripts/build_training_visual_rc64.js /tmp/CIR_Operational_Training_Visual.pptx
python scripts/localize_cartoon_en.py
CIR_TRAINING_LOCALE=en node scripts/build_training_visual_rc64.js /tmp/CIR_Operational_Training_Visual_EN.pptx
libreoffice --headless --convert-to pdf --outdir /tmp /tmp/CIR_Operational_Training_Visual_EN.pptx
python scripts/verify_visual_training_en.py --pptx /tmp/CIR_Operational_Training_Visual_EN.pptx --pdf /tmp/CIR_Operational_Training_Visual_EN.pdf
```

Translation catalog: `visual_rc98_english_slides.json` (authored slide titles
and explanations) and `visual_rc98_english_labels.json` (diagram, caption and
UI explanatory text). Both are generated/pinned sources. **Actual application
screenshots and their UI text remain original**, because their provenance SHA-256
must not change. Chapter cartoons are now localized as artwork as well: the English version displays translated dialogue inside the speech balloons and a translated closing sign (Thank you!). The nine English images are SHA-256 pinned to their canonical Italian source images. This is the ONLY intentional cross-locale image difference; application screenshots remain byte-identical.
The approved anonymized sample document is retained unchanged.

CI status: only a GitHub run can confirm same-commit live screenshot capture and
publication. An offline editorial build is not represented as such a run.
