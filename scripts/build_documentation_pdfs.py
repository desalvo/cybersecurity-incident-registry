#!/usr/bin/env python3
"""Build static PDF copies of the user and administrator documentation.

The generated files are release artifacts saved under docs/.  The script keeps
figures close to the chapter that references them, matching the online help.
"""
from __future__ import annotations

import re
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
TEMPLATES = ROOT / "app" / "templates"
STATIC_HELP = ROOT / "app" / "static" / "help"
DOCS = ROOT / "docs"


def _is_documentation_noise(line: str) -> bool:
    """Return True for UI chrome or editorial notes that should not enter PDFs."""
    normalized = re.sub(r"\s+", " ", line).strip()
    if not normalized:
        return True
    exact_noise = {
        "Menu",
        "Logout",
        "Scarica PDF",
        "Scarica PDF amministrativo",
        "Vai all’indice",
        "Vai all'indice",
        "Digita una parola per filtrare i capitoli.",
    }
    if normalized in exact_noise:
        return True
    noise_fragments = (
        "Cerca nella documentazione",
        "Nessun capitolo contiene il testo cercato",
        "Scarica PDF",
        "Vai all’indice",
        "Vai all'indice",
        "Logout",
        "Il logo presente in questa guida",
        "Questa guida riorganizza le funzioni amministrative",
        "Questa guida descrive lo stato operativo corrente",
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
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<figure[\s\S]*?</figure>", " ", html, flags=re.I)
    html = re.sub(r"<nav[\s\S]*?</nav>", " ", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "\n• ", html, flags=re.I)
    html = re.sub(r"</(p|h1|h2|h3|tr|section|div)>", "\n", html, flags=re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"\{\{[\s\S]*?\}\}", "", html)
    html = re.sub(r"\{%[\s\S]*?%\}", "", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [
        line.replace("Versione applicativa: 0.4.0-4 · Build: · Autore: .", "Versione applicativa: 0.4.0-4 · Build: 20260522 · Autore: Alessandro De Salvo.")
        for line in lines
    ]
    return [line for line in lines if not _is_documentation_noise(line)]


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
    DOCS.mkdir(exist_ok=True)
    output = DOCS / output_name
    lines = _text_lines_from_template(template_name)

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
    normal = ParagraphStyle(f"{kind}_normal", parent=styles["BodyText"], fontSize=9.2, leading=12.5, alignment=TA_LEFT, spaceAfter=4)
    bullet = ParagraphStyle(f"{kind}_bullet", parent=normal, leftIndent=13, firstLineIndent=-8)
    h1 = ParagraphStyle(f"{kind}_h1", parent=styles["Heading1"], fontSize=20, leading=24, textColor=colors.HexColor("#0f172a"), spaceAfter=12, alignment=TA_CENTER)
    h2 = ParagraphStyle(f"{kind}_h2", parent=styles["Heading2"], fontSize=13.5, leading=17, textColor=colors.HexColor("#1d4ed8"), spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle(f"{kind}_h3", parent=styles["Heading3"], fontSize=11.2, leading=14, textColor=colors.HexColor("#334155"), spaceBefore=8, spaceAfter=4)
    caption = ParagraphStyle(f"{kind}_caption", parent=normal, fontSize=8.3, leading=10.5, textColor=colors.HexColor("#64748b"), alignment=TA_CENTER)
    callout_style = ParagraphStyle(f"{kind}_callout", parent=normal, backColor=colors.HexColor("#eef4ff"), borderColor=colors.HexColor("#bfdbfe"), borderWidth=0.7, borderPadding=7, spaceBefore=4, spaceAfter=8)

    story = []
    logo_path = STATIC_HELP / "app-logo.png"
    if logo_path.exists():
        logo = Image(str(logo_path), width=3.0 * cm, height=3.0 * cm)
        logo.hAlign = "CENTER"
        story.append(logo)
    story.append(Paragraph("Cybersecurity Incident Registry", h1))
    story.append(Paragraph(escape(subtitle), ParagraphStyle(f"{kind}_subtitle", parent=normal, alignment=TA_CENTER, fontSize=12, leading=15, textColor=colors.HexColor("#475569"))))
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph(escape(callout), callout_style))
    story.append(PageBreak())

    chapters = [line for line in lines if re.match(r"^\d+\.\s+", line)]
    if chapters:
        story.append(Paragraph("Indice", h2))
        tbl = Table([[Paragraph(escape(c), normal)] for c in chapters], colWidths=[17.0 * cm])
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
        story.append(PageBreak())

    inserted = set()
    for line in lines:
        if line.startswith("Documentazione") or line.startswith("Cybersecurity Incident Registry"):
            continue
        match = re.match(r"^(\d+)\.\s+", line)
        if match:
            story.append(Paragraph(escape(line), h2))
            for label, filename in visuals_by_chapter.get(match.group(1), []):
                path = STATIC_HELP / filename
                if path.exists() and label not in inserted:
                    story.append(KeepTogether([_fitted_image(path), Paragraph(escape(label), caption), Spacer(1, 0.2 * cm)]))
                    inserted.add(label)
            continue
        if line.startswith("• "):
            story.append(Paragraph(escape(line), bullet))
            continue
        if len(line) < 90 and (line.startswith("Esempio") or line.startswith("Configurazione") or line.startswith("Procedura") or line in {"Accessibilità", "Checklist finale per un incidente", "Backup consigliato", "Checklist mensile", "Buone pratiche", "Statistiche", "Report PDF incidente"}):
            story.append(Paragraph(escape(line), h3))
            continue
        story.append(Paragraph(escape(line), normal))

    def page_canvas(canvas, doc_obj):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#1d4ed8"))
        canvas.rect(0, A4[1] - 0.65 * cm, A4[0], 0.65 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(1.55 * cm, A4[1] - 0.42 * cm, f"Cybersecurity Incident Registry - {title}")
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 1.55 * cm, 0.8 * cm, f"Pagina {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_canvas, onLaterPages=page_canvas)


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


def _build_brochure() -> None:
    """Create a concise two-page, portrait marketing brochure for the application."""
    DOCS.mkdir(exist_ok=True)
    output = DOCS / "brochure_cybersecurity_incident_registry.pdf"
    page_size = A4
    doc = SimpleDocTemplate(
        str(output),
        pagesize=page_size,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.0 * cm,
        bottomMargin=0.95 * cm,
        title="Cybersecurity Incident Registry - Brochure",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("brochure_title", parent=styles["Title"], fontSize=23, leading=26, textColor=colors.white, alignment=TA_LEFT, spaceAfter=5)
    subtitle = ParagraphStyle("brochure_subtitle", parent=styles["BodyText"], fontSize=10.2, leading=12.6, textColor=colors.HexColor("#dbeafe"), alignment=TA_LEFT)
    h2 = ParagraphStyle("brochure_h2", parent=styles["Heading2"], fontSize=13.6, leading=16.5, textColor=colors.HexColor("#1d4ed8"), spaceBefore=4, spaceAfter=5)
    h3 = ParagraphStyle("brochure_h3", parent=styles["Heading3"], fontSize=10.4, leading=12.7, textColor=colors.HexColor("#0f172a"), spaceAfter=2)
    normal = ParagraphStyle("brochure_normal", parent=styles["BodyText"], fontSize=8.55, leading=10.8, textColor=colors.HexColor("#0f172a"), spaceAfter=4)
    bullet = ParagraphStyle("brochure_bullet", parent=normal, leftIndent=10, firstLineIndent=-7, spaceAfter=3.2)
    small = ParagraphStyle("brochure_small", parent=normal, fontSize=7.6, leading=9.2, textColor=colors.HexColor("#475569"), spaceAfter=2)
    white_small = ParagraphStyle("brochure_white_small", parent=normal, fontSize=7.8, leading=9.4, textColor=colors.white)
    chip = ParagraphStyle("brochure_chip", parent=normal, fontSize=7.7, leading=9.4, textColor=colors.HexColor("#1e3a8a"), backColor=colors.HexColor("#dbeafe"), borderPadding=3, borderRadius=4, alignment=TA_CENTER)

    logo_path = STATIC_HELP / "app-logo.png"
    hero_path = STATIC_HELP / "screenshot-dashboard.png"
    flow_path = STATIC_HELP / "flow-incident-lifecycle.png"
    detail_path = STATIC_HELP / "screenshot-incident-detail.png"
    charts_path = STATIC_HELP / "charts-reporting.png"
    modules_path = STATIC_HELP / "screenshot-modules.png"

    logo = _brochure_image(logo_path, 1.8 * cm, 1.8 * cm) if logo_path.exists() else Paragraph("", normal)
    hero = _brochure_image(hero_path, 17.4 * cm, 6.0 * cm) if hero_path.exists() else Paragraph("", normal)
    flow = _brochure_image(flow_path, 7.9 * cm, 4.3 * cm) if flow_path.exists() else Paragraph("", normal)
    detail = _brochure_image(detail_path, 7.9 * cm, 4.3 * cm) if detail_path.exists() else Paragraph("", normal)
    charts = _brochure_image(charts_path, 7.9 * cm, 4.3 * cm) if charts_path.exists() else Paragraph("", normal)
    modules = _brochure_image(modules_path, 7.9 * cm, 4.3 * cm) if modules_path.exists() else Paragraph("", normal)

    story = []
    header = Table(
        [[logo, [
            Paragraph("Cybersecurity Incident Registry", title),
            Paragraph("Versione applicativa 0.4.0-4 - Registro operativo per incidenti cyber, workflow, notifiche, audit e documentazione probatoria.", subtitle),
        ]]],
        colWidths=[2.25 * cm, 15.9 * cm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("BOX", (0, 0), (-1, -1), 0, colors.HexColor("#0f172a")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.20 * cm))

    intro = Table(
        [[
            [
                Paragraph("Scopo dell'applicazione", h2),
                Paragraph("Cybersecurity Incident Registry supporta la gestione end-to-end degli incidenti informatici: dalla registrazione iniziale alla chiusura, con workflow configurabili, tracciamento delle azioni, notifiche, documenti, audit e reportistica.", normal),
                Paragraph("La soluzione aiuta a raccogliere evidenze, tempi, responsabilità e comunicazioni in un unico registro operativo, pronto per verifiche interne, audit e rendicontazione.", normal),
            ]
        ]],
        colWidths=[18.15 * cm],
    )
    intro.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(intro)
    story.append(Spacer(1, 0.16 * cm))
    hero_box = Table([[hero], [Paragraph("Esempio di interfaccia operativa per il monitoraggio e la gestione degli incidenti.", small)]], colWidths=[18.15 * cm])
    hero_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(hero_box)
    story.append(Spacer(1, 0.12 * cm))
    story.append(Paragraph("Funzionalità principali", h2))
    feature_left = [
        _feature_paragraph("Registro incidenti con stati, gravità, categorie, dati coinvolti, conseguenze e raccomandazioni operative.", bullet),
        _feature_paragraph("Interfacciabilità con vari meccanismi di autenticazione: account locali, LDAP/Active Directory, SSO OAuth2/OpenID Connect e MFA.", bullet),
        _feature_paragraph("Configurabilità completa di azioni, step di workflow, tassonomie, notifiche, template, loghi, ruoli e opzioni operative.", bullet),
        _feature_paragraph("Notifiche automatiche configurabili verso utenti, CSIRT, DPO e altre entità custom, con attachment automatici di documenti generati o compilati.", bullet),
    ]
    feature_right = [
        _feature_paragraph("Import di workflow custom esterni con controllo degli elementi già presenti.", bullet),
        _feature_paragraph("Analisi e configurazione modulare per la compilazione automatica dei PDF compilabili.", bullet),
        _feature_paragraph("Compliance con le linee guida AGID sul software sicuro, con test dinamici periodici a ogni nuova release.", bullet),
        _feature_paragraph("Knowledge base opzionale per chatbot AI AlBot/Alex con dati anonimizzati; licenza European Union Public Licence (EUPL).", bullet),
    ]
    feature_table = Table([[feature_left, feature_right]], colWidths=[8.95 * cm, 8.95 * cm])
    feature_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbe3ef")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(feature_table)
    story.append(PageBreak())

    story.append(Paragraph("Governance, automazione e tracciabilità", h2))
    cards = []
    for img, heading, text in [
        (flow, "Workflow guidato", "Azioni e step configurabili accompagnano l'incidente dalla rilevazione alla chiusura."),
        (detail, "Timeline ed evidenze", "Cronologia, allegati, destinatari, documenti e campi strutturati restano consultabili in un unico punto."),
        (modules, "Moduli PDF", "Mapping dei campi e compilazione automatica dei PDF compilabili partendo dai dati incidente."),
        (charts, "Reportistica", "Grafici e report aiutano a monitorare volumi, stati, gravità e tempi di gestione."),
    ]:
        card = Table([[img], [Paragraph(heading, h3)], [Paragraph(text, small)]], colWidths=[8.65 * cm])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        cards.append(card)
    story.append(Table([[cards[0], cards[1]], [cards[2], cards[3]]], colWidths=[8.95 * cm, 8.95 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(Spacer(1, 0.14 * cm))
    chips = Table([[
        Paragraph("Workflow custom", chip),
        Paragraph("Notifiche automatiche", chip),
        Paragraph("PDF compilabili", chip),
        Paragraph("Audit AGID", chip),
    ]], colWidths=[4.43 * cm] * 4)
    chips.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(chips)
    story.append(Spacer(1, 0.12 * cm))
    value = Table(
        [[
            [Paragraph("Output principali", h2), Paragraph("Report PDF, moduli compilati, audit CSV, backup completi, evidenze documentali, export/import dei dati e workflow esterni importabili.", normal)],
            [Paragraph("Riferimenti", h2), Paragraph("Creatore: Alessandro De Salvo - braket71@gmail.com<br/>GitHub: https://github.com/desalvo/cybersecurity-incident-registry", normal)],
        ]],
        colWidths=[8.95 * cm, 8.95 * cm],
    )
    value.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4ff")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#bfdbfe")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bfdbfe")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(value)

    def brochure_canvas(canvas, doc_obj):
        _draw_brochure_watermark(canvas, page_size)
        canvas.saveState()
        w, h = page_size
        canvas.setFillColor(colors.HexColor("#0f172a"))
        canvas.rect(0, h - 0.22 * cm, w, 0.22 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(w - 1.25 * cm, 0.45 * cm, f"Cybersecurity Incident Registry - Brochure - Pagina {doc_obj.page}/2")
        canvas.restoreState()

    doc.build(story, onFirstPage=brochure_canvas, onLaterPages=brochure_canvas)

def main() -> None:
    _build_pdf(
        kind="user",
        template_name="help.html",
        output_name="documentazione_utente.pdf",
        title="Documentazione utente",
        subtitle="Documentazione utente completa",
        callout="Versione PDF statica della documentazione utente. Le figure sono mantenute vicino al capitolo che le introduce.",
        visuals_by_chapter={
            "1": [("Figura 1 - Flusso consigliato di gestione incidente", "flow-incident-lifecycle.png")],
            "3": [("Figura 2 - Pagina principale con avvisi procedurali", "screenshot-dashboard.png")],
            "5": [("Figura 3 - Dettaglio incidente e timeline azioni", "screenshot-incident-detail.png")],
            "10": [("Figura 4 - Configurazione moduli PDF e mapping", "screenshot-modules.png"), ("Figura 5 - Esempi di grafici di reportistica", "charts-reporting.png")],
        },
    )
    _build_pdf(
        kind="admin",
        template_name="admin_help.html",
        output_name="documentazione_amministrativa.pdf",
        title="Documentazione amministrativa",
        subtitle="Documentazione amministrativa completa",
        callout="Versione PDF statica della documentazione amministrativa. Le figure sono mantenute vicino al capitolo che le introduce.",
        visuals_by_chapter={
            "1": [("Figura 1 - Flusso amministrativo consigliato", "admin-flow.png")],
            "4": [("Figura 2 - Configurazione SSO e controllo connessione", "admin-screenshot-sso.png")],
            "11": [("Figura 3 - Configurazione template PDF e mapping", "admin-screenshot-modules.png")],
            "16": [("Figura 4 - Mappa delle aree di governance amministrativa", "admin-chart-governance.png")],
        },
    )
    _build_brochure()


if __name__ == "__main__":
    main()
