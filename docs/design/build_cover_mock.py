#!/usr/bin/env python3
"""Create a photographic CIR manual-cover proposal for visual approval.

The CLI writes a clearly marked one-page proposal to an explicit output path;
it never modifies adopted manuals. The preparatory apply_cover/apply_all helpers
remain available for the later approved design: they retain all original pages,
printed numbering and links, replacing an existing cover without accumulation.
The photograph is a project-generated asset; titles remain searchable PDF text.
Requires ReportLab and pypdf only. No application imports or network access.
"""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
ASSET = DOCS / "visual-assets" / "cover-master.png"
COVER_REVISION = "CIR-photographic-cover-v1"
MANUALS = (
    ("documentazione_utente.pdf", "Manuale utente", "Gestione operativa degli incidenti", "it"),
    ("user_documentation_en.pdf", "User manual", "Operational incident management", "en"),
    ("documentazione_amministrativa.pdf", "Manuale amministratore", "Configurazione e governo dell'applicazione", "it"),
    ("administrator_documentation_en.pdf", "Administrator manual", "Application configuration and governance", "en"),
    ("ADMIN_ALFRESCO.pdf", "Guida Alfresco", "Documenti, storage e integrazione per tenant", "it"),
)
NAVY = "#071D2B"
TEAL = "#63DDCC"
FONT = "Helvetica"
BOLD = "Helvetica-Bold"
_regular = Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")
if _regular.is_file() and _regular.with_name("NotoSans-Bold.ttf").is_file():
    pdfmetrics.registerFont(TTFont("CIRCoverNoto", str(_regular)))
    pdfmetrics.registerFont(TTFont("CIRCoverNotoBold", str(_regular.with_name("NotoSans-Bold.ttf"))))
    FONT, BOLD = "CIRCoverNoto", "CIRCoverNotoBold"


def _paragraph(c, text, x, top, width, size, colour="#FFFFFF", bold=False):
    style = ParagraphStyle("cover", fontName=BOLD if bold else FONT,
                           fontSize=size, leading=size * 1.22,
                           textColor=colors.HexColor(colour))
    p = Paragraph(text, style)
    _, height = p.wrap(width, A4[1])
    p.drawOn(c, x, A4[1] - top - height)
    return top + height


def build_cover(title: str, subtitle: str, language: str, *, proposal=False) -> bytes:
    """Return one A4 cover page, with native text and the common photograph."""
    if not ASSET.is_file():
        raise FileNotFoundError(f"Required photographic cover asset: {ASSET}")
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=A4, pageCompression=1, invariant=1)
    c.setTitle(f"Cybersecurity Incident Registry - {title}" + (" - Graphic proposal" if proposal else ""))
    c.setAuthor("Alessandro De Salvo")
    w, h = A4
    image = ImageReader(str(ASSET))
    iw, ih = image.getSize()
    scale = max(w / iw, h / ih)
    c.drawImage(image, (w - iw * scale) / 2, (h - ih * scale) / 2,
                width=iw * scale, height=ih * scale, mask="auto")
    c.saveState()
    c.setFillColor(colors.HexColor(NAVY))
    c.setFillAlpha(0.88)
    c.rect(0, h - 358, w, 358, fill=1, stroke=0)
    c.setFillAlpha(0.95)
    c.rect(0, 0, w, 148, fill=1, stroke=0)
    c.restoreState()
    c.setFillColor(colors.HexColor(TEAL))
    c.rect(42, h - 43, 43, 3, fill=1, stroke=0)
    _paragraph(c, "DOCUMENTATION" if language == "en" else "DOCUMENTAZIONE", 99, 32, w - 141, 9, TEAL, True)
    _paragraph(c, "CIR", 40, 69, w - 80, 58, bold=True)
    _paragraph(c, "Cybersecurity<br/>Incident Registry", 44, 148, w - 88, 19)
    end = _paragraph(c, title, 42, 223, w - 84, 32, bold=True)
    _paragraph(c, subtitle, 44, end + 16, w - 88, 11.5, "#D8E7EB")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    _paragraph(c, f"{'Functional version' if language == 'en' else 'Versione funzionale'} {version}", 42, h - 115, w - 84, 10.5, TEAL, True)
    _paragraph(c, "Alessandro De Salvo", 42, h - 84, w - 84, 10)
    _paragraph(c, "Original illustrative image generated for CIR." if language == "en" else "Immagine illustrativa originale generata per CIR.", 42, h - 54, w - 84, 8.2, "#BBD0D7")
    if proposal:
        _paragraph(c, "Graphic proposal · pending approval" if language == "en" else "Proposta grafica · da approvare", 42, h - 32, w - 84, 8.2, TEAL, True)
    c.save()
    return stream.getvalue()


def _body_text_hash(pages) -> str:
    value = "\n\f\n".join(page.extract_text() or "" for page in pages)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def apply_cover(path: Path, title: str, subtitle: str, language: str) -> dict:
    """Prepend or replace one recognized cover without rebuilding the body."""
    original = path.read_bytes()
    reader = PdfReader(io.BytesIO(original))
    metadata = reader.metadata or {}
    had_cover = metadata.get("/CIRCoverRevision") == COVER_REVISION
    body_pages = list(reader.pages)[1:] if had_cover else list(reader.pages)
    if not body_pages:
        raise ValueError(f"The manual has no body pages: {path}")
    before_hash = _body_text_hash(body_pages)
    before_links = sum(len(page.get("/Annots", [])) for page in body_pages)
    writer = PdfWriter(clone_from=reader)
    if had_cover:
        writer.remove_page(0, clean=True)
    cover_reader = PdfReader(io.BytesIO(build_cover(title, subtitle, language)))
    writer.insert_page(cover_reader.pages[0], 0)
    writer.add_metadata({"/CIRCoverRevision": COVER_REVISION,
                         "/CIRCoverImageSHA256": hashlib.sha256(ASSET.read_bytes()).hexdigest(),
                         "/CIRBodyTextSHA256": before_hash,
                         "/Title": f"Cybersecurity Incident Registry - {title}"})
    # Removing a page alone leaves its image/font objects in the writer. Clone
    # the reachable document graph after serialization to discard detached
    # cover resources while retaining outlines, links and all body resources.
    # This also keeps rebuilds stable in byte size, not just page count.
    intermediate = io.BytesIO()
    writer.write(intermediate)
    compact = PdfWriter(clone_from=PdfReader(io.BytesIO(intermediate.getvalue())))
    output = io.BytesIO()
    compact.write(output)
    after = PdfReader(io.BytesIO(output.getvalue()))
    assert len(after.pages) == len(body_pages) + 1
    assert _body_text_hash(list(after.pages)[1:]) == before_hash
    assert sum(len(page.get("/Annots", [])) for page in list(after.pages)[1:]) == before_links
    temporary = path.with_suffix(".pdf.tmp")
    temporary.write_bytes(output.getvalue())
    temporary.replace(path)
    return {"file": path.name, "pages": len(after.pages), "body_pages": len(body_pages),
            "body_text_preserved": True, "annotations_preserved": before_links,
            "replaced_existing_cover": had_cover, "cover_revision": COVER_REVISION}


def apply_all() -> list[dict]:
    return [apply_cover(DOCS / name, title, subtitle, language)
            for name, title, subtitle, language in MANUALS]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="One-page proposal PDF, separate from adopted manuals.")
    parser.add_argument("--language", choices=("it", "en"), default="it")
    args = parser.parse_args()
    output = args.output.resolve()
    if output in {DOCS / name for name, *_ in MANUALS}:
        raise ValueError("The visual proposal must not replace an adopted manual.")
    output.parent.mkdir(parents=True, exist_ok=True)
    title = "User manual" if args.language == "en" else "Manuale utente"
    subtitle = "Operational incident management" if args.language == "en" else "Gestione operativa degli incidenti"
    output.write_bytes(build_cover(title, subtitle, args.language, proposal=True))
    print(output)
