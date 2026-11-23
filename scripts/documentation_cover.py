#!/usr/bin/env python3
"""Native, selectable-text cover shared by CIR documentation and brochures.

The composition follows the approved documentation-v2 reference.  The synthetic
cybersecurity photograph is an illustration, never evidence of the running UI.
No text or platform marks are taken from the raster mockup.
"""
from __future__ import annotations

from pathlib import Path
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as canvas_module

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata

NAVY = "#061329"
TEAL = "#00788B"
BLUE = "#143E68"
MUTED = "#365469"
LINE = "#ACC2D2"


def _fit_size(text, width, *, maximum, minimum=7, font="Helvetica"):
    size = maximum
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > width:
        size -= .25
    if pdfmetrics.stringWidth(text, font, size) > width:
        raise ValueError(f"Cover text does not fit its reserved region: {text!r}")
    return size


def _text(canvas, text, x, y, *, width=None, size=11, bold=False, color=NAVY,
          truncate=False, minimum=7):
    font = "Helvetica-Bold" if bold else "Helvetica"
    if width is not None:
        try:
            size = _fit_size(text, width, maximum=size, minimum=minimum, font=font)
        except ValueError:
            if not truncate:
                raise
            size = minimum
            # Long configurable About strings stay bounded visually. Complete
            # identity remains in PDF metadata and in the clickable URI.
            while text and pdfmetrics.stringWidth(text+'...', font, size) > width:
                text = text[:-1]
            text = text.rstrip()+'...'
    canvas.setFillColor(colors.HexColor(color))
    canvas.setFont(font, size)
    canvas.drawString(x, y, text)
    return pdfmetrics.stringWidth(text, font, size), size


def _contained_image(canvas, path, x, y, width, height):
    image = ImageReader(str(path))
    iw, ih = image.getSize()
    scale = min(width / iw, height / ih)
    canvas.drawImage(image, x + (width-iw*scale)/2, y+(height-ih*scale)/2,
                     width=iw*scale, height=ih*scale, mask="auto")


def _platform_logo(canvas, path, x, y, width, height):
    if path.suffix.lower() == ".svg":
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        drawing = svg2rlg(str(path))
        if drawing is None or not drawing.width or not drawing.height:
            raise ValueError(f"Invalid platform logo: {path}")
        scale = min(width / drawing.width, height / drawing.height)
        canvas.saveState()
        canvas.translate(x + (width-drawing.width*scale)/2,
                         y + (height-drawing.height*scale)/2)
        canvas.scale(scale, scale)
        renderPDF.draw(drawing, canvas, 0, 0)
        canvas.restoreState()
    else:
        _contained_image(canvas, path, x, y, width, height)


def _identity(root):
    # Shared with About and the online documentation.  Fail if the authoritative
    # identity or verified technology assets are absent; do not invent marks.
    from application_identity import read_application_identity
    return read_application_identity(root)


def draw_documentation_cover(canvas, *, root=ROOT, title, subtitle,
                             language="it", metadata=None, identity=None,
                             category=None, note=None):
    """Draw one approved cover on the current canvas page.

    Coordinates are scaled from A4 to the current page size.  ``metadata`` is a
    ReleaseMetadata snapshot; ``identity`` is the shared About/branding mapping.
    Neither argument changes the source VERSION/BUILD files.
    """
    root = Path(root)
    metadata = metadata or read_release_metadata(root)
    identity = identity or _identity(root)
    en = language == "en"
    category = category or ("DOCUMENTATION" if en else "DOCUMENTAZIONE")
    canvas.setTitle(f"{identity['name']} - {title}")
    canvas.setAuthor(identity["author"])
    canvas.setSubject(f"{metadata.version} · Build {metadata.build}")
    page_width, page_height = canvas._pagesize
    width, height = A4
    canvas.saveState()
    canvas.scale(page_width / width, page_height / height)
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)

    logo = root / "app/static/help/app-logo.png"
    hero = root / "app/static/ui/cybersecurity-hero-v2.png"
    if not logo.is_file() or not hero.is_file():
        raise ValueError("Approved application logo and cybersecurity photograph are required")
    _contained_image(canvas, logo, 25, height-126, 99, 99)
    canvas.setStrokeColor(colors.HexColor(TEAL))
    canvas.setLineWidth(1.3)
    canvas.line(135, height-31, 135, height-120)
    name = identity["name"]
    if name == "Cybersecurity Incident Registry":
        brand_lines = ("Cybersecurity", "Incident Registry")
    else:
        words = name.split()
        midpoint = max(1, len(words)//2)
        brand_lines = (" ".join(words[:midpoint]), " ".join(words[midpoint:]))
    _text(canvas, brand_lines[0], 150, height-72, width=width-178, size=30,
          bold=True, truncate=True, minimum=16)
    _text(canvas, brand_lines[1], 150, height-106, width=width-178, size=29,
          bold=True, color=TEAL, truncate=True, minimum=16)
    label_width = pdfmetrics.stringWidth(category, "Helvetica-Bold", 9)
    _text(canvas, category, width-28-label_width, height-26, size=9, bold=True)
    canvas.line(width-96, height-35, width-28, height-35)

    _text(canvas, title, 28, height-193, width=width-56, size=53, bold=True)
    _text(canvas, subtitle, 29, height-232, width=width-58, size=20)

    photo_y, photo_height = height-535, 277
    photo = ImageReader(str(hero))
    iw, ih = photo.getSize()
    scale = max(width/iw, photo_height/ih)
    canvas.saveState()
    clipping = canvas.beginPath()
    clipping.rect(0, photo_y, width, photo_height)
    canvas.clipPath(clipping, stroke=0)
    # Anchor the photograph on its right: the server and breach console are
    # preserved while its intentionally empty left banner area is cropped.
    canvas.drawImage(photo, width-iw*scale, photo_y+(photo_height-ih*scale)/2,
                     width=iw*scale, height=ih*scale)
    canvas.restoreState()

    badge_y, badge_height = 267, 28
    version_text = ("Version " if en else "Versione ") + metadata.version
    build_text = "Build " + metadata.build
    version_width = max(150, pdfmetrics.stringWidth(version_text, "Helvetica-Bold", 14)+24)
    build_width = max(145, pdfmetrics.stringWidth(build_text, "Helvetica-Bold", 14)+24)
    for x, label, badge_width, fill in (
        (28, version_text, version_width, BLUE),
        (38+version_width, build_text, build_width, TEAL),
    ):
        canvas.setFillColor(colors.HexColor(fill))
        canvas.roundRect(x, badge_y, badge_width, badge_height, 5, fill=1, stroke=0)
        _text(canvas, label, x+12, badge_y+8, size=14, bold=True, color="#FFFFFF")

    _text(canvas, "Creator" if en else "Creatore", 28, 243, size=13, bold=True)
    _text(canvas, identity["author"], 28, 225, width=204, size=11,
          truncate=True, minimum=8)
    email_width, email_size = _text(canvas, identity["author_email"], 28, 209,
                                    width=204, size=10, color=TEAL,
                                    truncate=True, minimum=8)
    canvas.linkURL("mailto:"+identity["author_email"],
                   (28, 206, 28+email_width, 209+email_size), relative=1)
    canvas.setStrokeColor(colors.HexColor(LINE))
    canvas.setLineWidth(.8)
    canvas.line(242, 207, 242, 245)
    _text(canvas, "Project" if en else "Progetto", 260, 243, size=13, bold=True)
    project_width, project_size = _text(canvas, identity["project_url"], 260, 223,
                                        width=width-286, size=10, color=TEAL,
                                        truncate=True, minimum=8)
    canvas.linkURL(identity["project_url"],
                   (260, 220, 260+project_width, 223+project_size), relative=1)
    canvas.line(22, 189, width-22, 189)

    _text(canvas, "Supported platforms and technologies" if en else
          "Piattaforme e tecnologie supportate", 24, 168, width=width-48, size=16,
          bold=True)
    platforms = identity["platforms"]
    if len(platforms) != 6:
        raise ValueError("The approved cover requires all six supported technology logos")
    cell_width = (width-44)/len(platforms)
    for index, platform in enumerate(platforms):
        x = 22+index*cell_width
        asset = root / "app/static" / platform["logo"]
        if not asset.is_file():
            raise ValueError(f"Verified platform logo missing: {asset}")
        _platform_logo(canvas, asset, x+10, 97, cell_width-20, 53)
        name = platform["name"]
        size = _fit_size(name, cell_width-4, maximum=11.5, font="Helvetica-Bold")
        text_width = pdfmetrics.stringWidth(name, "Helvetica-Bold", size)
        _text(canvas, name, x+(cell_width-text_width)/2, 79, size=size, bold=True)
        if platform.get("url"):
            canvas.linkURL(platform["url"], (x+2, 76, x+cell_width-2, 151), relative=1)

    canvas.line(22, 56, width-22, 56)
    architectures = "  ·  ".join(identity["architectures"])
    arch_width = pdfmetrics.stringWidth(architectures, "Helvetica-Bold", 12)
    _text(canvas, architectures, (width-arch_width)/2, 34, size=12, bold=True)
    if note:
        note_size = _fit_size(note, width-48, maximum=6.5, minimum=5.5)
        note_width = pdfmetrics.stringWidth(note, "Helvetica", note_size)
        _text(canvas, note, (width-note_width)/2, 16, size=note_size, color=MUTED)
    canvas.restoreState()


def build_documentation_cover(path, *, root=ROOT, title, subtitle, language="it",
                              metadata=None, identity=None, category=None,
                              note=None, page_size=A4):
    """Write one native PDF cover; reusable by CI and presentation tooling."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = canvas_module.Canvas(str(path), pagesize=page_size, pageCompression=1)
    output.setTitle(f"Cybersecurity Incident Registry - {title}")
    draw_documentation_cover(output, root=root, title=title, subtitle=subtitle,
                              language=language, metadata=metadata,
                              identity=identity, category=category, note=note)
    output.save()
    return path
