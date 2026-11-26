#!/usr/bin/env python3
"""Build editable CIR training slides from public, reproducible tooling.

Source packages contain explicitly pending UI slots.  A CI presentation requires
the complete same-commit browser evidence and the intermediate PDF receipt;
screenshots cannot be substituted by illustrations or assets from another build.
The receipt binds the original PNG bytes to images actually embedded in slides.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application_identity import read_application_identity
from release_metadata import read_release_metadata
from scripts.presentation_evidence import MANUAL_PDFS, MANUAL_PREVIEWS, PRESENTATION_FILE, PRESENTATION_RECEIPT
from scripts.ui_documentation_evidence import (EvidenceError, REQUIRED_SCREENSHOTS, load_evidence,
                                              safe_artifact_path, sha256, validate_manuals)

# These are authoring dependencies only. They are not added to the CIR runtime.
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

WIDTH, HEIGHT = 40 / 3, 7.5
FONT = "Noto Sans"
NAVY, TEAL, INK = "071A30", "007A8C", "122C45"
MUTED, LINE, PAPER, WHITE = "425D70", "C4D4DF", "F8FAFC", "FFFFFF"
AMBER = "F4BB66"
MANUAL_ORDER = (
    "documentazione_utente.pdf", "documentazione_amministrativa.pdf",
    "user_documentation_en.pdf", "administrator_documentation_en.pdf", "ADMIN_ALFRESCO.pdf",
)
MANUAL_LABELS = {
    "documentazione_utente.pdf": "Manuale utente · IT",
    "documentazione_amministrativa.pdf": "Manuale amministratore · IT",
    "user_documentation_en.pdf": "User manual · EN",
    "administrator_documentation_en.pdf": "Administrator manual · EN",
    "ADMIN_ALFRESCO.pdf": "Amministrazione Alfresco · IT",
}


def _replace_tokens(value, tokens):
    if isinstance(value, str):
        for key, replacement in tokens.items():
            value = value.replace("{{" + key + "}}", replacement)
        return value
    if isinstance(value, list):
        return [_replace_tokens(item, tokens) for item in value]
    if isinstance(value, dict):
        return {key: _replace_tokens(item, tokens) for key, item in value.items()}
    return value


def load_content(root: Path, metadata):
    path = root / "docs/presentation/content_it.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    if content.get("version") != metadata.version:
        raise EvidenceError("Presentation source version does not match VERSION")
    slides = content.get("slides")
    if not isinstance(slides, list) or not 21 <= len(slides) <= 100:
        raise EvidenceError("Presentation must preserve the complete operational training")
    screenshot_ids, manuals = [], []
    for item in slides:
        if not isinstance(item, dict) or not item.get("title") or len(item.get("notes", "")) < 40:
            raise EvidenceError("Each authored slide needs a title and substantive speaker notes")
        screenshot_ids.extend(item.get("screenshots", []))
        manuals.extend(item.get("manuals", []))
    if set(screenshot_ids) != REQUIRED_SCREENSHOTS or len(screenshot_ids) != len(REQUIRED_SCREENSHOTS):
        raise EvidenceError("Presentation source must cover every required UI view exactly once")
    if set(manuals) != MANUAL_PDFS or len(manuals) != len(MANUAL_PDFS):
        raise EvidenceError("Presentation source must cover every manual first page exactly once")
    return _replace_tokens(content, {"version": metadata.version, "build": metadata.build,
                                     "candidate": str(content.get("candidate", ""))})


def _check_manual_metadata(path: Path, metadata):
    from pypdf import PdfReader
    try:
        reader = PdfReader(path)
        if reader.is_encrypted or not reader.pages:
            raise EvidenceError("Manual must be an unencrypted PDF with a first page")
        text = " ".join((reader.pages[0].extract_text() or "").split())
        if metadata.version not in text or metadata.build not in text:
            raise EvidenceError("Manual first page does not match the current VERSION/BUILD: " + path.name)
    except EvidenceError:
        raise
    except Exception as exc:
        raise EvidenceError("Manual first page is unreadable: " + path.name) from exc


def preflight(root: Path, documentation_dir: Path, screenshot_manifest: Path | None,
              source_commit: str | None, require_real_screenshots: bool):
    metadata = read_release_metadata(root)
    content = load_content(root, metadata)
    if require_real_screenshots and (screenshot_manifest is None or not source_commit):
        raise EvidenceError("Real screenshot mode requires --screenshot-manifest and --source-commit")
    if screenshot_manifest is not None and not source_commit:
        raise EvidenceError("A screenshot manifest requires the expected --source-commit")
    if source_commit is not None and not re.fullmatch(r"[a-f0-9]{40}(?:[a-f0-9]{24})?", source_commit):
        raise EvidenceError("Source commit must be a complete hexadecimal Git object ID")
    evidence, manifest_hash = None, None
    if screenshot_manifest is not None:
        evidence = load_evidence(screenshot_manifest, source_commit, metadata_root=root)
        manifest_hash = sha256(screenshot_manifest)
        receipt = validate_manuals(documentation_dir, source_commit, manifest_hash,
                                  metadata_root=root, require_presentation=False)
        pdf_paths = {name: receipt["_paths"][name] for name in MANUAL_ORDER}
    else:
        pdf_paths = {name: safe_artifact_path(documentation_dir, name) for name in MANUAL_ORDER}
    for path in pdf_paths.values():
        if path.stat().st_size > 80 * 1024 * 1024 or not path.read_bytes().startswith(b"%PDF-"):
            raise EvidenceError("Expected a bounded PDF manual: " + path.name)
        _check_manual_metadata(path, metadata)
    # The authoring pipeline never fetches or executes paths from a receipt.
    identity = read_application_identity(root)
    for relative in ("app/static/help/app-logo.png", "app/static/ui/cybersecurity-hero-v2.png"):
        safe_artifact_path(root, relative)
    for platform in identity["platforms"]:
        safe_artifact_path(root, "app/static/" + platform["logo"])
    if shutil.which("pdftoppm") is None:
        raise EvidenceError("Install Poppler (pdftoppm) to render the actual first pages of the manuals")
    return metadata, content, identity, evidence, manifest_hash, pdf_paths


def render_manual_first_pages(pdf_paths: dict[str, Path], destination: Path):
    paths = {}
    for name in MANUAL_ORDER:
        target = destination / MANUAL_PREVIEWS[name]
        prefix = target.with_suffix("")
        result = subprocess.run(["pdftoppm", "-f", "1", "-singlefile", "-png", "-r", "120",
                                 str(pdf_paths[name]), str(prefix)],
                                capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not target.is_file():
            raise EvidenceError("First-page PDF rendering failed: " + name + "\n" + result.stderr[-1200:])
        with Image.open(target) as image:
            width, height = image.size
            if image.format != "PNG" or not (400 <= width <= 4000 and 600 <= height <= 6000
                                              and .65 <= width / height <= .75):
                raise EvidenceError("Manual first page must be an A4-like portrait page: " + name)
        paths[name] = target
    return paths


class Deck:
    def __init__(self, root, metadata, identity, content, evidence, manual_previews):
        self.root, self.metadata, self.identity, self.content = root, metadata, identity, content
        self.evidence, self.manual_previews = evidence, manual_previews
        self.presentation = Presentation()
        self.presentation.slide_width = Inches(WIDTH)
        self.presentation.slide_height = Inches(HEIGHT)
        self.presentation._element.sldSz.set("type", "screen16x9")
        # The library's empty template contains machine-specific printer data.
        # Drop that unused relationship so no opaque binary enters the release.
        for relation in list(self.presentation.part.rels.values()):
            if relation.reltype.endswith("/printerSettings"):
                self.presentation.part.drop_rel(relation.rId)
        # The empty template also has a stock thumbnail unrelated to CIR. Leave
        # preview generation to the viewer instead of shipping a misleading one.
        for relation in list(self.presentation.part.package.iter_rels()):
            if relation.reltype.endswith("/metadata/thumbnail"):
                self.presentation.part.package.drop_rel(relation.rId)
        props = self.presentation.core_properties
        props.title = identity["name"] + " — Laboratorio operativo"
        props.subject = metadata.version + " · Build " + metadata.build
        props.author = identity["author"]
        props.keywords = "CIR, incident response, workflow, Tenants Default, training"
        props.comments = ("Same-build verified application screenshots" if evidence else
                          "Source edition: UI screenshots are explicitly pending the verified CI build")
        # Build dates are authoritative, so local timezone or system date cannot
        # accidentally label a reproducible batch as a different release.
        stamp = datetime.strptime(metadata.build, "%Y%m%d").replace(tzinfo=timezone.utc)
        props.created = stamp
        props.modified = stamp
        self.screenshot_media, self.manual_media = {}, {}
        self.rows = {item["id"]: item for item in evidence["screenshots"]} if evidence else {}

    def rect(self, slide, x, y, w, h, fill, *, line=None):
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(fill)
        if line:
            shape.line.color.rgb = RGBColor.from_string(line)
            shape.line.width = Pt(.6)
        else:
            shape.line.fill.background()
        for effect in shape._element.xpath(".//a:effectRef"):
            effect.set("idx", "0")
        return shape

    def text(self, slide, value, x, y, w, h, size=21, color=INK, bold=False, *, name=None,
             align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        shape.name = name or "Native text"
        frame = shape.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        frame.vertical_anchor = valign
        for index, line in enumerate(str(value).split("\n")):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.alignment = align
            paragraph.space_before = Pt(0)
            paragraph.space_after = Pt(0)
            paragraph.line_spacing = 1.08
            run = paragraph.add_run()
            run.text = line
            run.font.name = FONT
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = RGBColor.from_string(color)
        return shape

    def picture(self, slide, path, x, y, w, h, *, crop=False, alt=""):
        with Image.open(path) as source:
            iw, ih = source.size
        if crop:
            pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
            ratio, target = iw / ih, w / h
            if ratio > target:
                # Approved hero carries the incident console on its right side.
                pic.crop_left, pic.crop_right = 1 - target / ratio, 0
            else:
                fraction = max(0, 1 - ratio / target)
                # Preserve the access/data-transfer console in a shallow band.
                pic.crop_top, pic.crop_bottom = fraction * .3, fraction * .7
        else:
            scale = min(w / iw, h / ih)
            width, height = iw * scale, ih * scale
            pic = slide.shapes.add_picture(str(path), Inches(x + (w-width)/2), Inches(y + (h-height)/2),
                                           width=Inches(width), height=Inches(height))
        pic.name = alt or path.name
        pic._element.nvPicPr.cNvPr.set("descr", alt or path.name)
        return pic

    @staticmethod
    def media_file(slide, picture):
        part = slide.part.related_part(picture._pic.blipFill.blip.rEmbed)
        return str(part.partname).lstrip("/")

    def footer(self, slide, index, *, dark=False):
        color = "D1DEE8" if dark else MUTED
        self.rect(slide, .55, 7.06, 12.22, .008, "3B5267" if dark else LINE)
        self.text(slide, f"{self.metadata.version} · Build {self.metadata.build}", .55, 7.16, 4.1, .2,
                  10, color, name="Release footer")
        self.text(slide, "CIR  /  LABORATORIO OPERATIVO", 4.6, 7.16, 6.8, .2, 9.5, color)
        self.text(slide, f"{index+1:02d}", 12.22, 7.13, .53, .23, 11, color, True,
                  align=PP_ALIGN.RIGHT)

    def top(self, slide, item, index, *, dark=False):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string(NAVY if dark else PAPER)
        self.text(slide, item.get("kicker", "CYBERSECURITY INCIDENT REGISTRY"), .58, .34, 11.9, .28,
                  11, "73D3DE" if dark else TEAL, True)
        self.text(slide, item["title"], .58, .91, 12.05, 1.22, 32, WHITE if dark else INK, True,
                  name="Slide title")
        self.footer(slide, index, dark=dark)

    def bottom(self, slide, value, *, dark=False):
        self.text(slide, value, .58, 6.35, 12.05, .5, 17, "D1DEE8" if dark else MUTED)

    def cover(self, slide, item, index):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string(WHITE)
        self.picture(slide, self.root / "app/static/help/app-logo.png", .55, .29, .96, .96,
                     alt="Cybersecurity Incident Registry logo")
        self.rect(slide, 1.7, .38, .013, .8, TEAL)
        self.text(slide, self.identity["name"], 1.94, .39, 10.65, .81, 27, NAVY, True)
        self.text(slide, item["title"], .62, 1.52, 12, 1.42, 44, INK, True, name="Slide title")
        self.text(slide, item.get("subtitle", ""), .65, 3.0, 12, .45, 19, MUTED)
        self.picture(slide, self.root / "app/static/ui/cybersecurity-hero-v2.png", 0, 3.64, WIDTH, 2.2,
                     crop=True, alt="Synthetic cybersecurity infrastructure illustration, no people")
        edition = ("Schermate reali verificate della stessa build CI" if self.evidence else
                   "Edizione sorgente · schermate CI in attesa")
        self.text(slide, item.get("caption", "") + "\n" + edition, .62, 5.99, 12, .57, 14, TEAL, True)
        self.text(slide, self.identity["author"] + "  ·  " + self.identity["author_email"],
                  .62, 6.68, 12, .24, 11, MUTED)
        self.footer(slide, index)

    def columns(self, slide, item, index):
        self.top(slide, item, index)
        for n, (head, body) in enumerate(item["items"]):
            x = .62 + n * 4.16
            self.rect(slide, x, 2.58, .62, .045, TEAL)
            self.text(slide, head, x, 2.9, 3.8, .65, 21, INK, True)
            self.text(slide, body, x, 3.79, 3.65, 1.98, 22, MUTED)
        self.bottom(slide, item.get("bottom", ""))

    def split(self, slide, item, index):
        dark = item["type"] == "scenario"
        self.top(slide, item, index, dark=dark)
        self.text(slide, item["left"], .62, 2.78, 5.5, 2.55, 29, WHITE if dark else INK)
        self.rect(slide, 6.55, 2.6, .012, 2.9, "375269" if dark else LINE)
        for n, line in enumerate(item["right"]):
            y = 2.67 + n * 1.06
            self.rect(slide, 6.98, y, .4, .028, "73D3DE" if dark else TEAL)
            self.text(slide, line, 6.98, y + .16, 5.65, .84, 22, WHITE if dark else INK, True)
        self.bottom(slide, item.get("bottom", ""), dark=dark)

    def status(self, slide, item, index):
        self.top(slide, item, index, dark=True)
        for n, (head, body) in enumerate(item["items"]):
            x = .62 + n * 6.26
            color = AMBER if n else "73D3DE"
            self.rect(slide, x, 2.69, 5.65, .045, color)
            self.text(slide, head, x, 3.12, 5.65, .6, 28, color, True)
            self.text(slide, body, x, 4.05, 5.45, 1.42, 26, WHITE)
        self.bottom(slide, item.get("bottom", ""), dark=True)

    def journey(self, slide, item, index):
        self.top(slide, item, index)
        for n, (number, label) in enumerate(item["items"]):
            x, y = .62 + (n % 3) * 4.16, 2.7 + (n // 3) * 1.53
            self.text(slide, number, x, y, .8, .65, 34, TEAL, True)
            self.text(slide, label, x + .95, y + .12, 2.9, .62, 25, INK, True)
            self.rect(slide, x, y + 1.04, 3.55, .012, LINE)
        self.bottom(slide, item.get("bottom", ""))

    def step(self, slide, item, index):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string(PAPER)
        self.rect(slide, 0, 0, 3.08, 6.94, NAVY)
        self.text(slide, item["number"], .55, .59, 2.15, 1.28, 78, "73D3DE", True)
        self.text(slide, "LABORATORIO\nOPERATIVO", .58, 2.48, 2.1, .82, 20, WHITE, True)
        self.text(slide, item["location"], .58, 4.08, 2.02, 2.15, 19, "D1DEE8")
        self.text(slide, item["title"], 3.65, .67, 9.05, 1.12, 32, INK, True, name="Slide title")
        for n, line in enumerate(item["actions"]):
            y = 2.21 + n * 1.08
            self.text(slide, str(n+1), 3.68, y, .43, .4, 23, TEAL, True)
            self.text(slide, line, 4.25, y, 8.18, .93, 23, INK)
        self.rect(slide, 3.65, 5.75, 9.02, .032, TEAL)
        self.text(slide, item["result"], 3.65, 6.03, 9, .65, 21, INK, True)
        self.footer(slide, index)

    def platforms(self, slide, item, index):
        self.top(slide, item, index)
        self.text(slide, item["subtitle"], .62, 2.3, 12, .45, 24, TEAL, True)
        platforms = self.identity["platforms"]
        if len(platforms) != 6:
            raise EvidenceError("The supported technology overview requires six identified platforms")
        for n, platform in enumerate(platforms):
            x = .62 + n * 2.08
            self.picture(slide, self.root / "app/static" / platform["logo"], x+.25, 3.1, 1.23, .98,
                         alt=platform["name"] + " technology identifier")
            self.text(slide, platform["name"], x, 4.24, 1.79, .36, 17, INK, True, align=PP_ALIGN.CENTER)
        for n, line in enumerate(item["items"]):
            self.text(slide, line, .62 + n * 4.16, 5.12, 3.68, .82, 19, MUTED)
        self.bottom(slide, "Architetture: " + " · ".join(self.identity["architectures"]))

    def screenshot(self, slide, sid, x, y, w, h):
        caption = self.rows.get(sid, {}).get("caption_it", self.content["screenshot_captions"][sid])
        if self.evidence:
            pic = self.picture(slide, self.evidence["_paths"][sid], x, y, w, h, alt=caption)
            self.screenshot_media[sid] = self.media_file(slide, pic)
        else:
            self.rect(slide, x, y, w, h, "EEF3F7", line=LINE)
            narrow = w < 3.0
            self.text(slide, "SCHERMATA REALE", x+.18, y+h*.25, w-.36, .47, 14 if narrow else 19,
                      TEAL, True, align=PP_ALIGN.CENTER)
            self.text(slide, "Acquisizione CI\nin attesa", x+.18, y+h*.44, w-.36, 1.0,
                      17 if narrow else 25, INK, True, align=PP_ALIGN.CENTER)
            self.text(slide, sid, x+.14, y+h-.58, w-.28, .45, 9.5 if narrow else 13, MUTED,
                      align=PP_ALIGN.CENTER)
        self.text(slide, caption, x, y+h+.13, w, .58, 12.5 if w < 3 else 14, MUTED,
                  align=PP_ALIGN.CENTER)

    def screenshots(self, slide, item, index):
        self.top(slide, item, index)
        ids = item["screenshots"]
        if len(ids) == 4:
            # Four real images: keep both closed-status evidence and mobile
            # navigation without truncating the proof set in the CI edition.
            boxes = [(.62, 2.04, 5.80, 1.74), (6.84, 2.04, 5.80, 1.74),
                     (.62, 4.49, 5.80, 1.74), (6.84, 4.49, 5.80, 1.74)]
        elif len(ids) == 3:
            boxes = [(.62, 2.35, 7.75, 3.86), (8.65, 2.35, 1.96, 3.86), (10.83, 2.35, 1.96, 3.86)]
        elif all(sid.endswith("desktop") for sid in ids):
            boxes = [(.62, 2.38, 5.91, 3.68), (6.82, 2.38, 5.91, 3.68)]
        else:
            boxes = [(.62, 2.31, 8.93, 3.98), (10.06, 2.31, 2.28, 3.98)]
        for sid, box in zip(ids, boxes):
            self.screenshot(slide, sid, *box)
        label = ("Interfaccia reale · dati sintetici di laboratorio · stessa build CI" if self.evidence else
                 "Edizione sorgente: queste aree verranno completate con screenshot reali verificati dalla CI")
        self.text(slide, label, .62, 6.83, 12, .2, 10, TEAL)

    def manuals(self, slide, item, index):
        self.top(slide, item, index)
        names = item["manuals"]
        width, height = 2.75, 3.89
        gap = .92
        start = (WIDTH - len(names)*width - (len(names)-1)*gap) / 2
        for n, name in enumerate(names):
            x = start+n*(width+gap)
            pic = self.picture(slide, self.manual_previews[name], x, 2.24, width, height,
                               alt="Prima pagina reale: " + MANUAL_LABELS[name])
            self.manual_media[name] = self.media_file(slide, pic)
            self.text(slide, MANUAL_LABELS[name], x-.18, 6.29, width+.36, .39, 15, INK, True,
                      align=PP_ALIGN.CENTER)
        self.text(slide, "Prime pagine renderizzate dai PDF di questa build · testi e documenti completi nel package",
                  .62, 6.83, 12, .21, 10, TEAL)

    def references(self, slide, item, index):
        self.top(slide, item, index)
        for n, record in enumerate(item["items"]):
            y = 2.42+n*1.32
            self.text(slide, record[0], .62, y, 2.12, .92, 21, TEAL, True)
            self.text(slide, record[1], 3.02, y, 9.65, 1.03, 21, INK)
            if n < len(item["items"])-1:
                self.rect(slide, 3.02, y+1.1, 9.65, .008, LINE)
        self.text(slide, item["bottom"], .62, 6.47, 12, .39, 14, MUTED)
        # Plain native citations have no external package relationship. The full
        # source URLs and contextual limits are also recorded in speaker notes.
        self.text(slide, item["source_line"], .62, 6.89, 12, .13, 7.7, MUTED)

    def build(self):
        methods = {"cover": self.cover, "end": self.cover, "columns": self.columns,
                   "tenants": self.columns, "split": self.split, "scenario": self.split,
                   "status": self.status, "journey": self.journey, "step": self.step,
                   "platforms": self.platforms, "screenshots": self.screenshots,
                   "manuals": self.manuals, "references": self.references}
        for index, item in enumerate(self.content["slides"]):
            if item["type"] not in methods:
                raise EvidenceError("Unsupported presentation slide type: " + str(item["type"]))
            slide = self.presentation.slides.add_slide(self.presentation.slide_layouts[6])
            methods[item["type"]](slide, item, index)
            note = item["notes"]
            if item["type"] == "screenshots":
                note += ("\n\nLe schermate provengono dall'applicazione avviata dalla CI sul medesimo commit, "
                         "con dati sintetici. Illustrano la UI; non attestano l'esecuzione del distinto caso "
                         "DEMO-PHISH-001 del laboratorio." if self.evidence else
                         "\n\nEdizione sorgente: le aree vuote sono segnaposti espliciti, non mockup né "
                         "screenshot reali. Il materiale completo viene generato dalla CI dopo la verifica "
                         "di commit, versione, build e hash di tutte le acquisizioni del browser.")
            if item["type"] in {"cover", "end", "platforms"}:
                note += "\n\nProvenienza delle illustrazioni: docs/presentation/assets/sources.json. "
                note += "Identificativi delle tecnologie: app/static/branding/platforms/manifest.json."
            slide.notes_slide.notes_text_frame.text = note
        if self.evidence and set(self.screenshot_media) != REQUIRED_SCREENSHOTS:
            raise EvidenceError("Not all verified screenshots were embedded in the presentation")
        if set(self.manual_media) != MANUAL_PDFS:
            raise EvidenceError("Not all actual manual first pages were embedded in the presentation")
        return self.presentation


def build_presentation(*, root=ROOT, output=None, documentation_dir=None, screenshot_manifest=None,
                       source_commit=None, require_real_screenshots=False):
    root = Path(root).absolute()
    documentation_dir = Path(documentation_dir or root / "docs").absolute()
    output = Path(output or root / "docs/presentation" / PRESENTATION_FILE).absolute()
    screenshot_manifest = Path(screenshot_manifest).absolute() if screenshot_manifest is not None else None
    if output.name != PRESENTATION_FILE:
        raise EvidenceError("Presentation output must be named " + PRESENTATION_FILE)
    metadata, content, identity, evidence, manifest_hash, pdf_paths = preflight(
        root, documentation_dir, screenshot_manifest, source_commit, require_real_screenshots)
    # All input provenance is checked before creating any final artifact.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cir-presentation-", dir=output.parent) as temporary:
        staging = Path(temporary)
        previews = render_manual_first_pages(pdf_paths, staging)
        deck = Deck(root, metadata, identity, content, evidence, previews)
        candidate = staging / PRESENTATION_FILE
        deck.build().save(candidate)
        from scripts.audit_training_media import audit
        audit(candidate, root, previews, evidence)
        # Validate the actual embedded bytes, not just authoring declarations.
        from zipfile import ZipFile
        with ZipFile(candidate) as archive:
            for sid, media in deck.screenshot_media.items():
                if hashlib.sha256(archive.read(media)).hexdigest() != deck.rows[sid]["sha256"]:
                    raise EvidenceError("Screenshot bytes changed while embedding: " + sid)
            for name, media in deck.manual_media.items():
                if hashlib.sha256(archive.read(media)).hexdigest() != sha256(previews[name]):
                    raise EvidenceError("Manual preview bytes changed while embedding: " + name)
        receipt = {
            "schema_version": 1, "source_commit": source_commit,
            "functional_version": metadata.version, "build": metadata.build,
            "real_screenshots": evidence is not None,
            "screenshot_manifest_sha256": manifest_hash,
            "file": PRESENTATION_FILE, "sha256": sha256(candidate),
            "content_sha256": sha256(root / "docs/presentation/content_it.json"),
            "editable_text": True, "speaker_notes": True,
            "screenshots": [{"id": sid, "sha256": deck.rows[sid]["sha256"],
                              "media_file": deck.screenshot_media[sid]}
                             for sid in sorted(deck.screenshot_media)],
            "manual_first_pages": [{"pdf": name, "pdf_sha256": sha256(pdf_paths[name]),
                                     "png": MANUAL_PREVIEWS[name], "png_sha256": sha256(previews[name]),
                                     "media_file": deck.manual_media[name], "page": 1}
                                    for name in MANUAL_ORDER],
            "slides": len(content["slides"]),
        }
        if evidence is None:
            receipt["status"] = "source-edition-awaiting-verified-ci-screenshots"
        receipt_path = staging / PRESENTATION_RECEIPT
        receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for name, path in previews.items():
            os.replace(path, output.parent / MANUAL_PREVIEWS[name])
        os.replace(candidate, output)
        os.replace(receipt_path, output.parent / PRESENTATION_RECEIPT)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--documentation-dir", type=Path)
    parser.add_argument("--screenshot-manifest", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--require-real-screenshots", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = build_presentation(root=args.project_root, output=args.output,
                                     documentation_dir=args.documentation_dir,
                                     screenshot_manifest=args.screenshot_manifest,
                                     source_commit=args.source_commit,
                                     require_real_screenshots=args.require_real_screenshots)
    except (EvidenceError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print("Training presentation: FAIL: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"presentation": receipt["file"], "slides": receipt["slides"],
                      "real_screenshots": receipt["real_screenshots"],
                      "version": receipt["functional_version"], "build": receipt["build"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
