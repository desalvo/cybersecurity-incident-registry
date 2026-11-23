#!/usr/bin/env python3
"""Rebuild the compact Alfresco guide from its consolidated Markdown source.

Uses the existing ReportLab dependency.  The serif operational-guide layout is
retained; historical hotfix notes remain in the consolidated Markdown source.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata
from documentation_cover import draw_documentation_cover


def _inline(value: str) -> str:
    value = escape(value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    return re.sub(r"`([^`]+)`", r'<font name="Courier" size="8.7">\1</font>', value)


def build_pdf(output: Path) -> None:
    metadata = read_release_metadata(ROOT)
    source = (ROOT / "docs" / "ADMIN_ALFRESCO.md").read_text(encoding="utf-8")
    start = source.index("## 1. Ambito")
    end = source.index("\n---\n", start)
    normal = ParagraphStyle("AlfrescoBody", fontName="Times-Roman", fontSize=10,
                            leading=12, spaceAfter=7)
    title = ParagraphStyle("AlfrescoTitle", parent=normal, fontName="Times-Bold",
                           fontSize=14.35, leading=17.95, spaceAfter=14)
    heading = ParagraphStyle("AlfrescoHeading", parent=normal, fontName="Times-Bold",
                             fontSize=11.95, leading=14.35, spaceBefore=10,
                             spaceAfter=7, keepWithNext=True)
    bullet = ParagraphStyle("AlfrescoBullet", parent=normal, leftIndent=14,
                            firstLineIndent=-10, spaceAfter=2)
    nested = ParagraphStyle("AlfrescoNestedBullet", parent=bullet, leftIndent=34)
    code = ParagraphStyle("AlfrescoCode", parent=normal, fontName="Courier",
                          fontSize=8, leading=10)
    story = [Spacer(1, 1), PageBreak()]
    paragraph = []
    code_lines = None

    def flush_paragraph():
        if paragraph:
            story.append(Paragraph(_inline(" ".join(paragraph)), normal))
            paragraph.clear()

    for line in source[start:end].splitlines():
        if line.startswith("```"):
            flush_paragraph()
            if code_lines is None:
                code_lines = []
            else:
                story.append(Preformatted("\n".join(code_lines), code))
                story.append(Spacer(1, 4))
                code_lines = None
        elif code_lines is not None:
            code_lines.append(line)
        elif line.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(_inline(line[3:]), heading))
        elif not line.strip():
            flush_paragraph()
        elif re.match(r"^\s*(?:- |\d+\. )", line):
            flush_paragraph()
            content = line.strip()
            if content.startswith("- "):
                content = "• " + content[2:]
            story.append(Paragraph(_inline(content), nested if line.startswith(" ") else bullet))
        else:
            paragraph.append(line)
    flush_paragraph()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=125,
                                 rightMargin=125, topMargin=113, bottomMargin=105,
                                 title="Cybersecurity Incident Registry - Guida amministrativa Alfresco",
                                 author="Alessandro De Salvo",
                                 subject=f"{metadata.version} · Build {metadata.build}")

    def page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Roman", 10)
        canvas.drawCentredString(A4[0] / 2, 73, str(doc.page))
        canvas.restoreState()

    def first_page(canvas, doc):
        draw_documentation_cover(canvas, root=ROOT, title="Guida Alfresco",
                                  subtitle="Documenti, storage e integrazione per tenant",
                                  metadata=metadata,
                                  note="Illustrazione cybersecurity; guida operativa dell'integrazione.")

    document.build(story, onFirstPage=first_page, onLaterPages=page_number)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "ADMIN_ALFRESCO.pdf")
    args = parser.parse_args(argv)
    build_pdf(args.output)


if __name__ == "__main__":
    main()
