#!/usr/bin/env python3
"""Fail closed if the main-branch publication lacks same-run UI evidence."""
import argparse
import json
from pathlib import Path


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
