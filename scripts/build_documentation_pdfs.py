#!/usr/bin/env python3
"""Build bilingual manuals, the Alfresco guide and verified UI documentation.

Release artifacts default to docs/ and share the approved photographic cover.
Figures stay close to the relevant chapter.  With a validated CI screenshot
manifest, build the real UI gallery and hash-bound PDF receipt as well.
"""
from __future__ import annotations

import re
import argparse
import hashlib
import json
import os
import sys
from html import unescape
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata
from documentation_cover import draw_documentation_cover

RELEASE_METADATA = read_release_metadata(ROOT)
TEMPLATES = ROOT / "app" / "templates"
STATIC_HELP = ROOT / "app" / "static" / "help"
DOCS = ROOT / "docs"
SCREENSHOT_EVIDENCE = None
SCREENSHOT_MANIFEST = None
SCREENSHOT_IDS = {
    'screenshot-dashboard.png': 'registry-desktop',
    'screenshot-incident-detail.png': 'incident-desktop',
    'screenshot-modules.png': 'admin-modules-desktop',
    'admin-screenshot-modules.png': 'admin-modules-desktop',
    'admin-screenshot-sso.png': 'admin-sso-desktop',
}


def _visual_path(filename):
    """Never represent a historical illustration as a current UI screenshot."""
    sid = SCREENSHOT_IDS.get(filename)
    if filename.startswith('ui:'):
        sid = filename[3:]
    if sid:
        return SCREENSHOT_EVIDENCE['_paths'].get(sid) if SCREENSHOT_EVIDENCE else None
    return STATIC_HELP / filename


def _is_documentation_noise(line: str) -> bool:
    """Return True for UI chrome or editorial notes that should not enter PDFs."""
    normalized = re.sub(r"\s+", " ", line).strip()
    if not normalized:
        return True
    exact_noise = {
        "Salta al contenuto principale",
        "Menu",
        "☰ Menu",
        "n Menu",
        "Alex",
        "Logout",
        "Scarica PDF",
        "Scarica PDF amministrativo",
        "Vai all’indice",
        "Vai all'indice",
        "Digita una parola per filtrare i capitoli.",
        "Go to index Download PDF",
        "Go to index Download administrator PDF",
    }
    if normalized in exact_noise:
        return True
    noise_fragments = (
        "Salta al contenuto principale",
        "Apri o chiudi menu",
        "Cerca nella documentazione",
        "Search administrator documentation",
        "Type a word to filter chapters",
        "Go to index",
        "Download PDF",
        "Download administrator PDF",
        "Nessun capitolo contiene il testo cercato",
        "No chapter contains the searched text",
        "Scarica PDF",
        "Vai all’indice",
        "Vai all'indice",
        "Logout",
        "Il logo presente in questa guida",
        "Questa guida riorganizza le funzioni amministrative",
        "Questa guida descrive lo stato operativo corrente",
        "AlBot anche Alex",
        "Helpdesk applicativo",
        "Ciao, sono AlBot",
        "Domanda per AlBot",
        "Invia",
    )
    if any(fragment in normalized for fragment in noise_fragments):
        return True
    # Header fragments inherited from the application shell are useful online but
    # noisy in printed documentation.
    if re.fullmatch(r"[A-Za-z0-9_.@ -]{2,80} · Logout", normalized):
        return True
    return False


def _text_lines_from_template(template_name: str) -> list[str]:
    html = (TEMPLATES / template_name).read_text(encoding="utf-8")
    # Only render the actual Jinja content block.  Some templates may contain
    # developer notes or legacy fragments after the block; they must not enter
    # the static PDF deliverables.
    block_match = re.search(r"\{%\s*block\s+content\s*%\}([\s\S]*?)\{%\s*endblock\s*%\}", html)
    if block_match:
        html = block_match.group(1)
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<figure[\s\S]*?</figure>", " ", html, flags=re.I)
    html = re.sub(r"<p[^>]*data-screenshot-pending[^>]*>[\s\S]*?</p>", " ", html, flags=re.I)
    html = re.sub(r"<nav[\s\S]*?</nav>", " ", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "\n• ", html, flags=re.I)
    html = re.sub(r"</(p|h1|h2|h3|tr|section|div)>", "\n", html, flags=re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    # Static documents have no Flask context: resolve known release metadata
    # before stripping other Jinja expressions, otherwise version/build vanish.
    release_values = {
        "version": RELEASE_METADATA.version,
        "build": RELEASE_METADATA.build,
        "name": "Cybersecurity Incident Registry",
        "author": "Alessandro De Salvo",
    }
    for key, value in release_values.items():
        html = re.sub(r"\{\{\s*app_info\." + key + r"\s*\}\}", value, html)
    html = re.sub(r"\{\{[\s\S]*?\}\}", "", html)
    html = re.sub(r"\{%[\s\S]*?%\}", "", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if not _is_documentation_noise(line)]




def _trim_english_preface_after_version_marker(lines: list[str], marker: str) -> list[str]:
    """Keep the English introductory notes compact in static PDFs.

    The online pages include operational update notes after the version line.
    For the printable English PDFs we keep the version statement and start the
    first chapter immediately after it, omitting the extra pre-chapter notes.
    """
    marker_idx = next((idx for idx, line in enumerate(lines) if marker in line), None)
    if marker_idx is None:
        return lines
    chapter_idx = next((idx for idx, line in enumerate(lines) if idx > marker_idx and re.match(r"^1\.\s+", line)), None)
    if chapter_idx is None or chapter_idx <= marker_idx + 1:
        return lines
    return lines[: marker_idx + 1] + lines[chapter_idx:]

def _fitted_image(path: Path, max_width=16.3 * cm, max_height=7.6 * cm) -> Image:
    try:
        iw, ih = ImageReader(str(path)).getSize()
        ratio = min(max_width / iw, max_height / ih)
        img = Image(str(path), width=iw * ratio, height=ih * ratio)
    except Exception:
        img = Image(str(path), width=max_width, height=max_height)
    img.hAlign = "CENTER"
    return img


def _build_pdf(kind: str, template_name: str, output_name: str, title: str, subtitle: str, callout: str, visuals_by_chapter: dict[str, list[tuple[str, str]]]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    output = DOCS / output_name
    lines = _text_lines_from_template(template_name)
    if template_name == "help_en.html":
        lines = _trim_english_preface_after_version_marker(
            lines,
            f"Version {RELEASE_METADATA.version} of the user guide, aligned with build",
        )
    elif template_name == "admin_help_en.html":
        lines = _trim_english_preface_after_version_marker(
            lines,
            f"Application version: {RELEASE_METADATA.version} · Version {RELEASE_METADATA.version} of the administrator guide.",
        )

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=1.55 * cm,
        leftMargin=1.55 * cm,
        topMargin=1.65 * cm,
        bottomMargin=1.55 * cm,
        title=f"Cybersecurity Incident Registry - {title}",
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(f"{kind}_normal", parent=styles["BodyText"], fontSize=9.2,
                            leading=12.1 if kind.endswith("_en") else 12.5,
                            alignment=TA_LEFT,
                            spaceAfter=3 if kind.endswith("_en") else 4,
                            allowWidows=0, allowOrphans=0)
    bullet = ParagraphStyle(f"{kind}_bullet", parent=normal, leftIndent=13, firstLineIndent=-8)
    h1 = ParagraphStyle(f"{kind}_h1", parent=styles["Heading1"], fontSize=20, leading=24, textColor=colors.HexColor("#0f172a"), spaceAfter=12, alignment=TA_CENTER)
    h2 = ParagraphStyle(f"{kind}_h2", parent=styles["Heading2"], fontSize=13.5, leading=17, textColor=colors.HexColor("#1d4ed8"), spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle(f"{kind}_h3", parent=styles["Heading3"], fontSize=11.2, leading=14, textColor=colors.HexColor("#334155"), spaceBefore=8, spaceAfter=4)
    caption = ParagraphStyle(f"{kind}_caption", parent=normal, fontSize=8.3, leading=10.5, textColor=colors.HexColor("#64748b"), alignment=TA_CENTER)
    callout_style = ParagraphStyle(f"{kind}_callout", parent=normal, backColor=colors.HexColor("#eef4ff"), borderColor=colors.HexColor("#bfdbfe"), borderWidth=0.7, borderPadding=7, spaceBefore=4, spaceAfter=8)

    # The cover is drawn once by the first-page callback; all operational content
    # remains in the flowable body, including the evidence status and callout.
    story = [Spacer(1, 1), PageBreak()]
    introductory_flows = [Paragraph(escape(callout), callout_style)]
    if SCREENSHOT_EVIDENCE:
        evidence_note = ('Real application screenshots captured in CI with isolated synthetic data. Source commit: '
                         if kind.endswith('_en') else
                         'Screenshot dell’applicazione reale acquisiti in CI con dati dimostrativi isolati. Commit sorgente: ')
        introductory_flows.append(Paragraph(escape(evidence_note + SCREENSHOT_EVIDENCE['source_commit']), caption))
    else:
        evidence_note = ('Current UI screenshots are generated by the required browser CI job; this source copy contains no substitute mock screenshots.'
                         if kind.endswith('_en') else
                         'Le schermate della UI corrente vengono generate dal job browser obbligatorio della CI. Questa copia sorgente non le sostituisce con mock.')
        introductory_flows.append(Paragraph(escape(evidence_note), caption))
    introductory_flows.append(Spacer(1, 0.2 * cm))

    chapters = [line for line in lines if re.match(r"^\d+\.\s+", line)]
    if chapters:
        toc_label = "Table of contents" if kind.endswith("_en") else "Indice"
        # A longer guide can have a multi-page index. Repeat its title so the
        # continuation remains identifiable and is not mistaken for body text.
        tbl = Table(
            [[Paragraph(toc_label, h2)]] + [[Paragraph(escape(c), normal)] for c in chapters],
            colWidths=[17.0 * cm], repeatRows=1,
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
        story.extend(introductory_flows)
        story.append(PageBreak())
    else:
        story.extend(introductory_flows)

    def _line_to_flowable(line: str):
        if line.startswith("• "):
            return Paragraph(escape(line), bullet)
        if len(line) < 90 and (line.startswith("Esempio") or line.startswith("Configurazione") or line.startswith("Procedura") or line in {"Accessibilità", "Checklist finale per un incidente", "Backup consigliato", "Checklist mensile", "Buone pratiche", "Statistiche", "Report PDF incidente"}):
            return Paragraph(escape(line), h3)
        return Paragraph(escape(line), normal)

    def _visual_flowables(chapter_number: str, inserted: set[str]) -> list:
        flows = []
        for label, filename in visuals_by_chapter.get(chapter_number, []):
            path = _visual_path(filename)
            if path is not None and path.exists() and label not in inserted:
                flows.extend([_fitted_image(path), Paragraph(escape(label), caption), Spacer(1, 0.2 * cm)])
                inserted.add(label)
        return flows

    inserted = set()
    chapter_chunks: list[tuple[str, str, list[str]]] = []
    current_title: str | None = None
    current_number: str | None = None
    current_body: list[str] = []
    for line in lines:
        if line.startswith("Documentazione") or line.startswith("Cybersecurity Incident Registry"):
            continue
        match = re.match(r"^(\d+)\.\s+", line)
        if match:
            if current_title and current_number:
                chapter_chunks.append((current_number, current_title, current_body))
            current_title = line
            current_number = match.group(1)
            current_body = []
        elif current_title:
            current_body.append(line)
        else:
            story.append(_line_to_flowable(line))
    if current_title and current_number:
        chapter_chunks.append((current_number, current_title, current_body))

    for chapter_number, chapter_title, body_lines in chapter_chunks:
        heading_flow = Paragraph(escape(chapter_title), h2)
        visual_flows = _visual_flowables(chapter_number, inserted)
        first_flows = []
        remaining_lines = body_lines[:]

        # Keep the chapter title with the first meaningful content so that no
        # chapter heading is left orphaned at the bottom of a page.  We keep
        # at most the first two short body items with the heading; the rest of
        # the chapter flows normally and can span pages.
        while remaining_lines and len(first_flows) < 2:
            candidate = remaining_lines.pop(0)
            first_flows.append(_line_to_flowable(candidate))
            if candidate.startswith("• "):
                break

        keep_block = [heading_flow] + visual_flows + first_flows
        story.append(KeepTogether(keep_block))
        i = 0
        while i < len(remaining_lines):
            line = remaining_lines[i]
            is_subheading = (
                re.match(r"^\d+[a-z]?\.\s+", line, flags=re.I)
                or (len(line) < 90 and (line.startswith("Esempio") or line.startswith("Configurazione") or line.startswith("Procedura") or line in {"Accessibilità", "Checklist finale per un incidente", "Backup consigliato", "Checklist mensile", "Buone pratiche", "Statistiche", "Report PDF incidente"}))
            )
            if is_subheading and i + 1 < len(remaining_lines):
                story.append(KeepTogether([_line_to_flowable(line), _line_to_flowable(remaining_lines[i + 1])]))
                i += 2
            else:
                story.append(_line_to_flowable(line))
                i += 1

    def page_canvas(canvas, doc_obj):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#1d4ed8"))
        canvas.rect(0, A4[1] - 0.65 * cm, A4[0], 0.65 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(1.55 * cm, A4[1] - 0.42 * cm, f"Cybersecurity Incident Registry - {title}")
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 8)
        page_label = "Page" if kind.endswith("_en") else "Pagina"
        canvas.drawRightString(A4[0] - 1.55 * cm, 0.8 * cm, f"{page_label} {doc_obj.page}")
        canvas.restoreState()

    cover_labels = {
        "user": ("Manuale utente", "Gestione degli incidenti di sicurezza"),
        "admin": ("Manuale amministratore", "Configurazione, sicurezza e operatività"),
        "user_en": ("User manual", "Security incident management"),
        "admin_en": ("Administrator manual", "Configuration, security and operations"),
    }

    def first_page(canvas, doc_obj):
        cover_title, cover_subtitle = cover_labels[kind]
        draw_documentation_cover(canvas, root=ROOT, title=cover_title,
                                  subtitle=cover_subtitle,
                                  language="en" if kind.endswith("_en") else "it",
                                  metadata=RELEASE_METADATA,
                                  note="Cybersecurity illustration / Illustrazione cybersecurity")

    doc.build(story, onFirstPage=first_page, onLaterPages=page_canvas)


def _brochure_image(path: Path, width: float, height: float) -> Image:
    try:
        iw, ih = ImageReader(str(path)).getSize()
        ratio = min(width / iw, height / ih)
        img = Image(str(path), width=iw * ratio, height=ih * ratio)
    except Exception:
        img = Image(str(path), width=width, height=height)
    img.hAlign = "CENTER"
    return img


def _draw_brochure_watermark(canvas, page_size) -> None:
    """Draw a subtle cybersecurity-themed watermark in the page background."""
    w, h = page_size
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#f4f8ff"))
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Decorative blue corner gradients approximated with translucent circles.
    try:
        canvas.setFillAlpha(0.11)
    except Exception:
        pass
    canvas.setFillColor(colors.HexColor("#1d4ed8"))
    canvas.circle(w - 1.8 * cm, h - 1.7 * cm, 5.8 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#0ea5e9"))
    canvas.circle(1.5 * cm, 2.0 * cm, 5.0 * cm, fill=1, stroke=0)

    # Circuit lines and nodes, intentionally light so text remains readable.
    try:
        canvas.setStrokeAlpha(0.12)
        canvas.setFillAlpha(0.12)
    except Exception:
        pass
    canvas.setStrokeColor(colors.HexColor("#0f172a"))
    canvas.setLineWidth(0.65)
    grid_y = [6.8 * cm, 9.1 * cm, 11.4 * cm, 13.7 * cm, 16.0 * cm, 18.3 * cm, 20.6 * cm]
    for idx, y in enumerate(grid_y):
        x0 = 1.1 * cm if idx % 2 else 2.0 * cm
        x1 = w - (1.2 * cm if idx % 2 else 2.2 * cm)
        canvas.line(x0, y, x1, y)
        for x in (x0 + 3.0 * cm, x0 + 7.1 * cm, x1 - 2.5 * cm):
            canvas.circle(x, y, 0.08 * cm, fill=1, stroke=0)
            canvas.line(x, y, x, y + (0.9 * cm if idx % 2 else -0.9 * cm))
            canvas.circle(x, y + (0.9 * cm if idx % 2 else -0.9 * cm), 0.07 * cm, fill=1, stroke=0)

    # Shield/lock watermark in the center.
    try:
        canvas.setStrokeAlpha(0.09)
        canvas.setFillAlpha(0.035)
    except Exception:
        pass
    canvas.setStrokeColor(colors.HexColor("#1e3a8a"))
    canvas.setFillColor(colors.HexColor("#1d4ed8"))
    cx, cy = w / 2.0, h / 2.0 + 0.4 * cm
    shield = canvas.beginPath()
    shield.moveTo(cx, cy + 5.0 * cm)
    shield.lineTo(cx + 4.0 * cm, cy + 3.3 * cm)
    shield.lineTo(cx + 3.2 * cm, cy - 1.6 * cm)
    shield.curveTo(cx + 2.5 * cm, cy - 3.2 * cm, cx + 1.2 * cm, cy - 4.1 * cm, cx, cy - 4.8 * cm)
    shield.curveTo(cx - 1.2 * cm, cy - 4.1 * cm, cx - 2.5 * cm, cy - 3.2 * cm, cx - 3.2 * cm, cy - 1.6 * cm)
    shield.lineTo(cx - 4.0 * cm, cy + 3.3 * cm)
    shield.close()
    canvas.drawPath(shield, fill=1, stroke=1)
    canvas.roundRect(cx - 1.55 * cm, cy - 0.8 * cm, 3.1 * cm, 2.35 * cm, 0.25 * cm, stroke=1, fill=0)
    canvas.arc(cx - 1.05 * cm, cy + 0.75 * cm, cx + 1.05 * cm, cy + 2.85 * cm, 0, 180)
    canvas.restoreState()


def _feature_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph("• " + escape(text), style)


def _build_brochure():
    from build_brochures import build
    return build(en=False, output_dir=DOCS)



def _build_brochure_en():
    from build_brochures import build
    return build(en=True, output_dir=DOCS)

def _build_screenshot_gallery():
    """One full browser viewport per page, with readable commit provenance."""
    from reportlab.pdfgen import canvas
    output = DOCS / 'CIR_UI_Screenshots.pdf'
    canvas_obj = canvas.Canvas(str(output), pageCompression=1)
    canvas_obj.setTitle('Cybersecurity Incident Registry - Real UI screenshots')
    canvas_obj.setPageSize(A4)
    draw_documentation_cover(canvas_obj, root=ROOT, title='Schermate della UI',
                              subtitle='Interfaccia reale · Evidenze CI',
                              metadata=RELEASE_METADATA,
                              note='Copertina illustrativa; le pagine successive sono catture reali della CI.')
    canvas_obj.showPage()
    for row in SCREENSHOT_EVIDENCE['screenshots']:
        page_size = A4 if row['viewport']['width'] < 800 else landscape(A4)
        width, height = page_size
        canvas_obj.setPageSize(page_size)
        canvas_obj.setFillColor(colors.HexColor('#0b2233'))
        canvas_obj.rect(0, height - 55, width, 55, fill=1, stroke=0)
        canvas_obj.setFillColor(colors.white)
        canvas_obj.setFont('Helvetica-Bold', 12)
        canvas_obj.drawString(28, height - 24, 'Cybersecurity Incident Registry')
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.drawString(28, height - 42, row['id'] + ' | ' + row['ui_mode'])
        image_path = SCREENSHOT_EVIDENCE['_paths'][row['id']]
        iw, ih = ImageReader(str(image_path)).getSize()
        ratio = min((width - 56) / iw, (height - 130) / ih)
        canvas_obj.drawImage(str(image_path), (width - iw * ratio) / 2,
                             height - 66 - ih * ratio, width=iw * ratio,
                             height=ih * ratio, mask='auto')
        canvas_obj.setFillColor(colors.HexColor('#334155'))
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawString(28, 47, 'CI / browser / dati dimostrativi - synthetic data')
        canvas_obj.drawString(28, 34, 'Source commit: ' + SCREENSHOT_EVIDENCE['source_commit'])
        canvas_obj.drawString(28, 21, 'Screenshot SHA-256: ' + row['sha256'])
        canvas_obj.showPage()
    canvas_obj.save()


def main(argv=None) -> None:
    global DOCS, SCREENSHOT_EVIDENCE, SCREENSHOT_MANIFEST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot-manifest', type=Path)
    parser.add_argument('--output-dir', type=Path, default=DOCS)
    parser.add_argument('--source-commit', default=os.environ.get('GITHUB_SHA'))
    parser.add_argument('--require-real-screenshots', action='store_true')
    parser.add_argument('--include-brochures', action='store_true',
                        help='Also rebuild both product brochures in the selected output directory.')
    args = parser.parse_args(argv)
    if args.require_real_screenshots and (not args.screenshot_manifest or not args.source_commit):
        parser.error('--require-real-screenshots requires --screenshot-manifest and --source-commit')
    SCREENSHOT_EVIDENCE = None
    SCREENSHOT_MANIFEST = args.screenshot_manifest
    if SCREENSHOT_MANIFEST:
        from ui_documentation_evidence import load_evidence
        SCREENSHOT_EVIDENCE = load_evidence(SCREENSHOT_MANIFEST, args.source_commit, metadata_root=ROOT)
    DOCS = args.output_dir
    _build_pdf(
        kind="user",
        template_name="help.html",
        output_name="documentazione_utente.pdf",
        title="Documentazione utente",
        subtitle="Documentazione utente completa",
        callout="Versione PDF statica della documentazione utente, aggiornata agli ultimi sviluppi dell’applicazione.",
        visuals_by_chapter={
            "1": [("Figura 1 - Flusso consigliato di gestione incidente", "flow-incident-lifecycle.png")],
            "3": [("Figura 2 - Pagina principale con avvisi procedurali", "screenshot-dashboard.png")],
            "5": [("Figura 3 - Dettaglio incidente e blocchi procedurali", "screenshot-incident-detail.png")],
            "10": [("Figura 4 - Configurazione moduli PDF e mapping", "screenshot-modules.png"), ("Figura 5 - Esempi di grafici di reportistica", "charts-reporting.png")],
            "20": [("Nuova interfaccia mobile con AlBot", "ui:assistant-mobile")],
        },
    )
    _build_pdf(
        kind="admin",
        template_name="admin_help.html",
        output_name="documentazione_amministrativa.pdf",
        title="Documentazione amministrativa",
        subtitle="Documentazione amministrativa completa",
        callout="Versione PDF statica della documentazione amministrativa, aggiornata agli ultimi sviluppi dell’applicazione.",
        visuals_by_chapter={
            "1": [("Figura 1 - Flusso amministrativo consigliato", "admin-flow.png")],
            "4": [("Figura 2 - Configurazione SSO e controllo connessione", "admin-screenshot-sso.png")],
            "11": [("Figura 3 - Configurazione template PDF e mapping", "admin-screenshot-modules.png")],
            "16": [("Figura 4 - Mappa delle aree di governance amministrativa", "admin-chart-governance.png")],
            "26": [("Scelta globale della UI per tutti i tenant", "ui:interface-settings-desktop")],
            "27": [("Architetture di installazione e bootstrap (diagramma originale CIR)", "installation-bootstrap-architecture.png")],
        },
    )
    _build_pdf(
        kind="user_en",
        template_name="help_en.html",
        output_name="user_documentation_en.pdf",
        title="User documentation",
        subtitle="Complete user documentation",
        callout="Static PDF version of the user documentation, updated with the latest application changes.",
        visuals_by_chapter={
            "1": [("Figure 1 - Recommended incident management workflow", "flow-incident-lifecycle.png")],
            "3": [("Figure 2 - Main page with procedural warnings", "screenshot-dashboard.png")],
            "5": [("Figure 3 - Incident detail and procedural blocks", "screenshot-incident-detail.png")],
            "10": [("Figure 4 - PDF form configuration and mapping", "screenshot-modules.png"), ("Figure 5 - Example reporting charts", "charts-reporting.png")],
            "17": [("New mobile interface with AlBot", "ui:assistant-mobile")],
        },
    )
    _build_pdf(
        kind="admin_en",
        template_name="admin_help_en.html",
        output_name="administrator_documentation_en.pdf",
        title="Administrator documentation",
        subtitle="Complete administrator documentation",
        callout="Static PDF version of the administrator documentation, updated with the latest application changes.",
        visuals_by_chapter={
            "1": [("Figure 1 - Recommended administration workflow", "admin-flow.png")],
            "4": [("Figure 2 - SSO configuration and connection test", "admin-screenshot-sso.png")],
            "9": [("Figure 3 - PDF template configuration and mapping", "admin-screenshot-modules.png")],
            "14": [("Figure 4 - Administrative governance area map", "admin-chart-governance.png")],
            "19": [("Global interface choice for all tenants", "ui:interface-settings-desktop")],
            "20": [("Installation and bootstrap architecture (original CIR diagram)", "installation-bootstrap-architecture.png")],
        },
    )
    from build_incident_lab_pdf import build as build_incident_lab
    screenshot = SCREENSHOT_EVIDENCE['_paths']['incident-desktop'] if SCREENSHOT_EVIDENCE else None
    build_incident_lab(DOCS / 'CIR_Incident_Laboratory_IT.pdf', screenshot,
                       SCREENSHOT_EVIDENCE['source_commit'] if SCREENSHOT_EVIDENCE else None)
    from build_alfresco_pdf import build_pdf as build_alfresco_pdf
    build_alfresco_pdf(DOCS / 'ADMIN_ALFRESCO.pdf')
    if args.include_brochures:
        _build_brochure()
        _build_brochure_en()
    if SCREENSHOT_EVIDENCE:
        _build_screenshot_gallery()
        names = ['documentazione_utente.pdf', 'documentazione_amministrativa.pdf',
                 'user_documentation_en.pdf', 'administrator_documentation_en.pdf',
                 'ADMIN_ALFRESCO.pdf', 'CIR_UI_Screenshots.pdf', 'CIR_Incident_Laboratory_IT.pdf']
        if args.include_brochures:
            names.extend(['brochure_cybersecurity_incident_registry.pdf',
                          'brochure_cybersecurity_incident_registry_en.pdf'])
        receipt = {
            'schema_version': 1, 'source_commit': SCREENSHOT_EVIDENCE['source_commit'],
            'functional_version': RELEASE_METADATA.version, 'build': RELEASE_METADATA.build,
            'real_screenshots': True,
            'screenshot_manifest_sha256': hashlib.sha256(SCREENSHOT_MANIFEST.read_bytes()).hexdigest(),
            'files': [{'file': name, 'sha256': hashlib.sha256((DOCS / name).read_bytes()).hexdigest()}
                      for name in names],
        }
        (DOCS / 'build-manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == "__main__":
    main()
