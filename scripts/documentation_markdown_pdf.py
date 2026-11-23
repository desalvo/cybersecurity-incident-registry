#!/usr/bin/env python3
"""Render allowlisted Markdown guides with the common native CIR cover.

Only a small, explicit Markdown vocabulary is interpreted.  Raw HTML is printed
as text, never passed to ReportLab markup, and remote assets are never fetched.
Unsupported syntax remains visible instead of disappearing from the guide.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import textwrap
from urllib.parse import urlsplit
from xml.sax.saxutils import escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable, Image, LongTable, PageBreak, Paragraph, Preformatted,
    SimpleDocTemplate, Spacer, TableStyle,
)
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata
try:
    from documentation_cover import draw_documentation_cover
except ModuleNotFoundError:
    from scripts.documentation_cover import draw_documentation_cover

FONT, BOLD, MONO = 'Helvetica', 'Helvetica-Bold', 'Courier'
_font_dir = Path('/usr/share/fonts/truetype/dejavu')
if (_font_dir / 'DejaVuSans.ttf').is_file():
    # The runtime image already installs fonts-dejavu-core. Embedded Unicode
    # fonts preserve arrows, accented text and symbols in source guides.
    for name, filename in (
        ('CIRMarkdownSans', 'DejaVuSans.ttf'),
        ('CIRMarkdownBold', 'DejaVuSans-Bold.ttf'),
        ('CIRMarkdownItalic', 'DejaVuSans-Oblique.ttf'),
        ('CIRMarkdownBoldItalic', 'DejaVuSans-BoldOblique.ttf'),
        ('CIRMarkdownMono', 'DejaVuSansMono.ttf'),
    ):
        pdfmetrics.registerFont(TTFont(name, str(_font_dir / filename)))
    pdfmetrics.registerFontFamily('CIRMarkdownSans', normal='CIRMarkdownSans',
                                  bold='CIRMarkdownBold', italic='CIRMarkdownItalic',
                                  boldItalic='CIRMarkdownBoldItalic')
    FONT, BOLD, MONO = 'CIRMarkdownSans', 'CIRMarkdownBold', 'CIRMarkdownMono'


_INLINE_TOKEN = re.compile(
    r"(`+)(.+?)\1|!?\[([^\]]*)\]\(([^)]*)\)|\*\*([^*]+)\*\*|__([^_]+)__|"
    r"\*([^*]+)\*|_([^_]+)_|<(https?://[^>]+|mailto:[^>]+)>", re.DOTALL,
)


def _safe_link(target):
    if not target or any(ord(char) < 32 for char in target):
        return False
    try:
        parsed = urlsplit(target)
    except ValueError:
        return False
    return ((parsed.scheme in {"http", "https"} and bool(parsed.hostname))
            or (parsed.scheme == "mailto" and bool(parsed.path)))


def _inline(text):
    """Escape source first; only our own validated formatting can become markup."""
    result = []
    position = 0
    for match in _INLINE_TOKEN.finditer(text):
        result.append(escape(text[position:match.start()]))
        raw = match.group(0)
        if match.group(1):
            result.append(f'<font name="{MONO}" size="8.4">' + escape(match.group(2)) + '</font>')
        elif match.group(3) is not None:
            label, target = match.group(3), match.group(4).strip()
            # Link titles are retained as text unless the destination alone is
            # a valid URL. Relative references remain readable in a standalone PDF.
            if not raw.startswith("!") and _safe_link(target):
                result.append(f'<link href={quoteattr(target)} color="#00788B">{escape(label)}</link>')
            else:
                result.append(escape(f"{label} ({target})"))
        elif match.group(5) is not None or match.group(6) is not None:
            result.append('<b>' + escape(match.group(5) or match.group(6)) + '</b>')
        elif match.group(7) is not None or match.group(8) is not None:
            result.append('<i>' + escape(match.group(7) or match.group(8)) + '</i>')
        else:
            target = match.group(9)
            result.append(f'<link href={quoteattr(target)} color="#00788B">{escape(target)}</link>')
        position = match.end()
    result.append(escape(text[position:]))
    return ''.join(result)


def _table_cells(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|') and not line.endswith(r'\|'):
        line = line[:-1]
    return [part.strip().replace(r'\|', '|') for part in re.split(r'(?<!\\)\|', line)]


def _table_separator(line):
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells)


def _local_image(root, target, width):
    """Optional local figure, confined to the source tree; no remote I/O."""
    try:
        remote = bool(urlsplit(target).scheme)
    except ValueError:
        return None
    if remote or target.startswith(('/', '\\')):
        return None
    for candidate in (root / 'docs' / target, root / target):
        candidate = candidate.resolve()
        if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
            continue
        if candidate.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
            continue
        iw, ih = ImageReader(str(candidate)).getSize()
        scale = min(width / iw, 250 / ih)
        figure = Image(str(candidate), width=iw*scale, height=ih*scale)
        figure.hAlign = 'LEFT'
        return figure
    return None


def _flowables(text, *, root, width):
    normal = ParagraphStyle('MarkdownBody', fontName=FONT, fontSize=9.2,
                            leading=12.8, spaceAfter=7, splitLongWords=True)
    heading_styles = {
        level: ParagraphStyle(f'MarkdownHeading{level}', parent=normal,
                              fontName=BOLD, fontSize=19 if level == 1 else 15 if level == 2 else 11.5,
                              leading=23 if level == 1 else 19 if level == 2 else 15,
                              textColor=colors.HexColor('#0A2843'), spaceBefore=11,
                              spaceAfter=7, keepWithNext=True)
        for level in range(1, 7)
    }
    cell_style = ParagraphStyle('MarkdownTableCell', parent=normal, fontSize=8,
                                leading=10.5, spaceAfter=0)
    code_style = ParagraphStyle('MarkdownCode', fontName=MONO, fontSize=8.2,
                                leading=10.3, leftIndent=7, spaceBefore=4, spaceAfter=8)
    quote_style = ParagraphStyle('MarkdownQuote', parent=normal, leftIndent=12,
                                 borderColor=colors.HexColor('#ADC5D3'), borderPadding=6,
                                 textColor=colors.HexColor('#355267'))
    flows = []
    paragraph = []

    def flush():
        if paragraph:
            flows.append(Paragraph(_inline(' '.join(paragraph)), normal))
            paragraph.clear()

    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        fenced = re.match(r'^\s*(`{3,}|~{3,})(.*)$', line)
        if fenced:
            flush()
            delimiter = fenced.group(1)
            content = []
            index += 1
            while index < len(lines) and not re.fullmatch(r'\s*' + re.escape(delimiter[0]) + '{' + str(len(delimiter)) + r',}\s*', lines[index]):
                content.append(lines[index].expandtabs(4))
                index += 1
            # Wrap at character boundaries so a single long identifier or URL
            # cannot cross the frame. No source characters are discarded.
            maximum = max(20, int((width-14) / pdfmetrics.stringWidth('M', MONO, 8.2)))
            wrapped = []
            for code_line in content:
                wrapped.extend(textwrap.wrap(code_line, width=maximum,
                                              replace_whitespace=False, drop_whitespace=False,
                                              break_long_words=True, break_on_hyphens=False)
                               or [''])
            flows.append(Preformatted('\n'.join(wrapped), code_style))
        elif index+1 < len(lines) and '|' in line and _table_separator(lines[index+1]):
            flush()
            rows = [_table_cells(line)]
            index += 2
            while index < len(lines) and lines[index].strip() and '|' in lines[index]:
                rows.append(_table_cells(lines[index]))
                index += 1
            index -= 1
            count = max(len(row) for row in rows)
            cells = [[Paragraph(_inline(value), cell_style) for value in row+['']*(count-len(row))]
                     for row in rows]
            lengths = [max(12, min(65, max(len(row[col]) if col < len(row) else 0 for row in rows)))
                       for col in range(count)]
            total = sum(lengths)
            table = LongTable(cells, colWidths=[width*n/total for n in lengths],
                              repeatRows=1, hAlign='LEFT', splitByRow=1, splitInRow=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E9F2F7')),
                ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#C8D7DF')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            flows.extend([table, Spacer(1, 9)])
        elif not stripped:
            flush()
        elif re.fullmatch(r'(?:-{3,}|\*{3,}|_{3,})', stripped):
            flush()
            flows.extend([HRFlowable(width='100%', thickness=.6, color=colors.HexColor('#C8D7DF')),
                          Spacer(1, 8)])
        elif match := re.match(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line):
            flush()
            flows.append(Paragraph(_inline(match.group(2)), heading_styles[len(match.group(1))]))
        elif match := re.match(r'^\s*(!\[([^\]]*)\]\(([^)]*)\))\s*$', line):
            flush()
            figure = _local_image(root, match.group(3), width)
            if figure is not None:
                flows.append(figure)
            flows.append(Paragraph(_inline(match.group(1)), quote_style))
        elif match := re.match(r'^(\s*)([-+*]|\d+[.)])\s+(.+)$', line):
            flush()
            depth = min(6, len(match.group(1).expandtabs(4))//2)
            prefix = '•' if match.group(2) in {'-', '+', '*'} else match.group(2)
            style = ParagraphStyle(f'MarkdownBullet{depth}', parent=normal,
                                   leftIndent=13+depth*12, firstLineIndent=-9, spaceAfter=4)
            flows.append(Paragraph(escape(prefix)+' '+_inline(match.group(3)), style))
        elif stripped.startswith('>'):
            flush()
            flows.append(Paragraph(_inline(stripped[1:].lstrip()), quote_style))
        else:
            paragraph.append(stripped)
        index += 1
    flush()
    return flows


def build_markdown_pdf(output, text, *, root=ROOT, title, subtitle,
                        language='it', identity=None):
    """Build to a path or writable binary stream, retaining all textual content."""
    root = Path(root)
    metadata = read_release_metadata(root)
    target = output
    if isinstance(output, (str, Path)):
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = str(target)
    width = A4[0]-94
    body = _flowables(text, root=root, width=width-12)
    story = [Spacer(1, 1)] + ([PageBreak()]+body if body else [])
    document = SimpleDocTemplate(target, pagesize=A4, leftMargin=47, rightMargin=47,
                                 topMargin=50, bottomMargin=48)

    def cover(canvas, doc):
        draw_documentation_cover(canvas, root=root, title=title, subtitle=subtitle,
                                  language=language, metadata=metadata, identity=identity,
                                  note='Cybersecurity illustration / Illustrazione cybersecurity')

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#143E68'))
        canvas.rect(0, A4[1]-25, A4[0], 25, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica', 8)
        header = title if len(title) < 105 else title[:102]+'...'
        canvas.drawString(47, A4[1]-16, header)
        canvas.setFillColor(colors.HexColor('#607586'))
        canvas.setFont('Helvetica', 8)
        canvas.drawString(47, 27, f'{metadata.version} · Build {metadata.build}')
        canvas.drawRightString(A4[0]-47, 27, ('Page ' if language == 'en' else 'Pagina ')+str(doc.page))
        canvas.restoreState()

    document.build(story, onFirstPage=cover, onLaterPages=page)
    return output
