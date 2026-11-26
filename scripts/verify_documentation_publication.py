#!/usr/bin/env python3
"""Fail closed if the main-branch publication lacks same-run UI evidence."""
import argparse
import json
import hashlib
import re
import sys
from zipfile import ZipFile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def verify(root: Path, commit: str) -> None:
    docs = root / "docs"
    ui = root / "app/static/help/ui-runtime"
    required = [docs / "UI_SCREENSHOTS_BUILD.json", docs / "UI_SCREENSHOTS_SOURCE.json", ui / "manifest.json"]
    for item in required:
        if not item.is_file() or item.stat().st_size == 0:
            raise ValueError(f"Missing real UI evidence: {item}")
    build = json.loads(required[0].read_text())
    source = json.loads(required[1].read_text())
    runtime = json.loads(required[2].read_text())
    # The installation script has already performed cryptographic verification
    # of the original manifests; this check also prevents empty publication.
    for obj, label in [(build, "build"), (source, "source"), (runtime, "runtime")]:
        if not isinstance(obj, dict):
            raise ValueError(f"Invalid {label} evidence")
    screenshots = runtime.get("screenshots", [])
    if not isinstance(screenshots, list) or not screenshots:
        raise ValueError("No real screenshots to publish")
    for item in screenshots:
        name = item.get("file", "")
        if not name or Path(name).name != name or not (ui / name).is_file():
            raise ValueError(f"Missing or invalid screenshot: {name}")
    pdfs = list(docs.glob("*.pdf"))
    slides = list((docs / "presentation").glob("*.pptx"))
    if not pdfs or not slides:
        raise ValueError("Missing generated manuals, brochures or PowerPoint")
    # Do not accept a repository containing older dated/RC presentations.
    presentation = docs / 'presentation'
    expected = {'CIR_Operational_Training_IT.pptx', 'CIR_Operational_Training_Visual.pptx'}
    if {p.name for p in presentation.glob('*.pptx')} != expected:
        raise ValueError('Repository must contain only the current training PowerPoints')
    if {p.name for p in presentation.glob('*.pdf')} != {'CIR_Operational_Training_Visual.pdf'}:
        raise ValueError('Repository must contain only the current visual training PDF')
    if list(presentation.glob('CIR_Operational_Training_Visual_RC*')):
        raise ValueError('Historical presentation versions must be removed')
    visual_receipt = json.loads((presentation / 'visual-training-receipt.json').read_text(encoding='utf8'))
    if visual_receipt.get('source_commit') != commit:
        raise ValueError('Published training is not bound to current commit')
    screenshots = visual_receipt.get('screenshots')
    if not isinstance(screenshots, list) or len(screenshots) != len(runtime['screenshots']):
        raise ValueError('Published training does not cover all browser screenshots')
    pptx = presentation / visual_receipt['pptx_file']
    pdf = presentation / visual_receipt['pdf_file']
    for file, key in ((pptx, 'pptx_sha256'), (pdf, 'pdf_sha256')):
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != visual_receipt[key]:
            raise ValueError('Published document changed since same-run verification: ' + file.name)
    manifest_hashes = {item['id']: item['sha256'] for item in runtime['screenshots']}
    from scripts.verify_visual_training_rc64 import linked_slide_image_digests
    with ZipFile(pptx) as presentation_zip:
        for index, row in enumerate(screenshots):
            if manifest_hashes.get(row.get('id')) != row.get('sha256'):
                raise ValueError('Screenshot provenance differs from published manifest')
            slide = visual_receipt['screenshot_gallery_first_slide'] + index
            if row['sha256'] not in linked_slide_image_digests(presentation_zip, slide):
                raise ValueError('Screenshot missing from published PowerPoint slide ' + str(slide))
    # The separate editable operational deck must show every same-run browser
    # capture as well; its receipt alone cannot prove visible slide linkage.
    operational = presentation / 'CIR_Operational_Training_IT.pptx'
    operational_receipt = json.loads((presentation / 'presentation-receipt.json').read_text(encoding='utf8'))
    operational_rows = operational_receipt.get('screenshots', [])
    if ({row.get('id') for row in operational_rows} != set(manifest_hashes) or
            len(operational_rows) != len(manifest_hashes)):
        raise ValueError('Operational PowerPoint is missing browser screenshots')
    with ZipFile(operational) as operational_zip:
        visible_hashes = set()
        for slide in range(1, operational_receipt['slides']+1):
            visible_hashes.update(linked_slide_image_digests(operational_zip, slide))
        for row in operational_rows:
            checksum = manifest_hashes.get(row['id'])
            if checksum != row['sha256'] or checksum not in visible_hashes:
                raise ValueError('Operational PowerPoint screenshot not visible: ' + row['id'])
    if visual_receipt['pdf_screenshots_visually_verified'] != len(screenshots):
        raise ValueError('PDF has not been visually verified against all screenshots')
    # Bind publication to current commit using the validated receipt.
    evidence_text = json.dumps(build, ensure_ascii=False) + json.dumps(source, ensure_ascii=False)
    if commit not in evidence_text:
        raise ValueError("UI documentation is not bound to the triggering commit")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    verify(args.root, args.source_commit)


if __name__ == "__main__":
    main()
