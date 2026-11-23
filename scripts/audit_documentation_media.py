#!/usr/bin/env python3
"""Fail closed on unapproved images and stale metadata in both CIR brochures.

Pixel identity is checked after PDF extraction, so an unauthorized embedded image
cannot pass simply because the correct synthetic strip is also present.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BROCHURES = (
    ("brochure_cybersecurity_incident_registry.pdf", "Presentazione", "REGISTRA E CLASSIFICA", "TENANTS DEFAULT", "INSTALLARE E SPERIMENTARE"),
    ("brochure_cybersecurity_incident_registry_en.pdf", "Product overview", "RECORD AND CLASSIFY", "TENANTS DEFAULT", "DEPLOY AND PRACTISE"),
)


def _pixels(image):
    rgb = image.convert("RGB")
    return rgb.size, rgb.tobytes()


def check(root: Path = ROOT, docs: Path | None = None):
    from application_identity import read_application_identity
    from release_metadata import read_release_metadata

    root = Path(root)
    docs = Path(docs) if docs is not None else root / "docs"
    identity = read_application_identity(root)
    release = read_release_metadata(root)
    logo_paths = [root / "app/static/help/app-logo.png", root / "app/static/ui/cybersecurity-hero-v2.png"]
    logo_paths += [root / "app/static" / p["logo"] for p in identity["platforms"]]
    strip_path = root / "app/static/help/cybersecurity-brochure-strip.png"
    approved_paths = logo_paths + [strip_path]
    for p in approved_paths:
        if not p.is_file():
            raise AssertionError(f"Approved asset missing: {p}")
    approved = {_pixels(Image.open(p)): p.name for p in approved_paths}
    strip = _pixels(Image.open(strip_path))
    hero = Image.open(logo_paths[1])
    if strip[0][0] != hero.width or not 50 <= strip[0][1] < hero.height:
        raise AssertionError("Brochure strip has invalid dimensions")
    results = {}
    for name, cover, operation, catalogue, deployment in BROCHURES:
        pdf_path = docs / name
        reader = PdfReader(str(pdf_path))
        if len(reader.pages) != 4:
            raise AssertionError(f"{name}: expected four pages, found {len(reader.pages)}")
        texts = [p.extract_text() or "" for p in reader.pages]
        for page_no, (page, text) in enumerate(zip(reader.pages, texts), 1):
            images = list(page.images)
            if not images:
                raise AssertionError(f"{name}, page {page_no}: no images")
            for item in images:
                if _pixels(item.image) not in approved:
                    raise AssertionError(f"{name}, page {page_no}: unapproved embedded image {item.name}")
            if page_no == 1:
                expected_cover = {_pixels(Image.open(p)) for p in logo_paths}
                embedded = {_pixels(item.image) for item in images}
                if embedded != expected_cover:
                    raise AssertionError(f"{name}: missing or unexpected cover images")
                for required in (cover, release.version, release.build, identity["author"], identity["project_url"]):
                    if required not in text:
                        raise AssertionError(f"{name}: missing cover metadata {required!r}")
                urls = {annotation.get_object()['/A'].get('/URI') for annotation in page.get('/Annots', []) if annotation.get_object().get('/A')}
                if identity["project_url"] not in urls:
                    raise AssertionError(f"{name}: project hyperlink not active")
            else:
                if len(images) != 1 or _pixels(images[0].image) != strip:
                    raise AssertionError(f"{name}, page {page_no}: image must be the CIR synthetic strip only")
                if release.version not in text or release.build not in text:
                    raise AssertionError(f"{name}, page {page_no}: stale release identity")
        for page_idx, required in ((1, operation), (2, catalogue), (3, deployment)):
            if required not in texts[page_idx]:
                raise AssertionError(f"{name}, page {page_idx + 1}: missing expected content {required}")
        if not any(x in texts[3].lower() for x in ("risk acceptance", "accettazione", "risk disposition")):
            raise AssertionError(f"{name}: missing expired risk disposition caveat")
        results[name] = {"pages": 4, "embedded_images": sum(len(p.images) for p in reader.pages), "approved_only": True,
                         "version": release.version, "build": release.build}
    return {"brochures": len(BROCHURES), "pages": 8, "files": results,
            "asset_allowlist": sorted(set(approved.values()))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(docs=args.docs), ensure_ascii=False, indent=2))
