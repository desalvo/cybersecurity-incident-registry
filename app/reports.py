import tempfile, os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table as RLTable, TableStyle, Image, PageBreak, KeepTogether, CondPageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
try:
    from flask import current_app
except Exception:
    current_app = None
try:
    from svglib.svglib import svg2rlg
except Exception:
    svg2rlg = None
import matplotlib.pyplot as plt
try:
    from .models import Setting
except Exception:
    Setting=None

def _setting_value(key, default=''):
    if not Setting:
        return default
    obj=Setting.query.get(key)
    return obj.value if obj and obj.value is not None else default

def _incident_consequences(inc):
    explicit=[a.consequence_text.strip() for a in sorted(inc.actions, key=lambda x: x.when_at) if getattr(a, 'consequence_text', None) and a.consequence_text.strip()]
    if explicit:
        return explicit
    cats=[(c.value or '').lower() for c in inc.categories]
    data=[(d.value or '').lower() for d in inc.data_types]
    out=[]
    if any('credential' in c or 'credenzial' in c for c in cats) or any('password' in d for d in data): out.append('Possibile compromissione di credenziali e accessi non autorizzati.')
    if any('phishing' in c for c in cats): out.append('Possibile esposizione a messaggi fraudolenti o furto di informazioni.')
    if any('spam' in c for c in cats): out.append('Possibile impatto sulla reputazione dei servizi e comunicazioni indesiderate.')
    if inc.personal_data or any('dati personali' in d for d in data): out.append('Possibile coinvolgimento di dati personali.')
    return out or ['Conseguenze da valutare.']

def _incident_measures(inc):
    rows=[]
    for a in sorted([x for x in inc.actions if getattr(x, 'exportable', True)], key=lambda x: x.when_at):
        label=(a.label.description or a.label.value) if a.label else 'azione'
        desc=a.description or ''
        when=_format_pdf_datetime(a.when_at) if a.when_at else ''
        action_text = f'{label}: {desc}'.strip() if desc else label
        rows.append(f'{action_text} - {when}'.strip(' -'))
    return rows or ['Nessuna misura registrata.']

def P(txt,style): return Paragraph(str(txt or ''), style)


def _safe_static_folder():
    try:
        if current_app:
            return current_app.static_folder
    except RuntimeError:
        pass
    return os.path.join(os.path.dirname(__file__), 'static')


def _pdf_logo_flowable(path, max_width=4.2*cm, max_height=1.8*cm):
    """Restituisce un flowable immagine scalato per intestazioni PDF."""
    if not path or not os.path.exists(path):
        return None
    ext=os.path.splitext(path)[1].lower()
    try:
        if ext == '.svg' and svg2rlg:
            drawing=svg2rlg(path)
            if not drawing:
                return None
            scale=min(max_width/float(drawing.width or max_width), max_height/float(drawing.height or max_height), 1.0)
            drawing.width=float(drawing.width or max_width)*scale
            drawing.height=float(drawing.height or max_height)*scale
            drawing.scale(scale, scale)
            return drawing
        img=Image(path)
        iw, ih = float(img.imageWidth or max_width), float(img.imageHeight or max_height)
        scale=min(max_width/iw, max_height/ih, 1.0)
        img.drawWidth=iw*scale
        img.drawHeight=ih*scale
        return img
    except Exception:
        return None


def _report_logos_table(styles):
    """Logo applicativo e logo caricato da GUI, quando presente, per la prima pagina del report.

    Il logo caricato da GUI non viene mai etichettato come "logo custom" nel PDF.
    Se non è stato caricato nessun logo da GUI, il relativo spazio viene omesso.
    """
    static_dir=_safe_static_folder()
    app_logo=os.path.join(static_dir, 'cir-application-logo.svg')
    gui_logo=_setting_value('logo_path', '')
    app_flow=_pdf_logo_flowable(app_logo, max_width=5.0*cm, max_height=2.0*cm)
    gui_flow=_pdf_logo_flowable(gui_logo, max_width=5.0*cm, max_height=2.0*cm)
    cells=[]
    labels=[]
    if app_flow:
        cells.append(app_flow); labels.append('Logo applicativo')
    if gui_flow:
        cells.append(gui_flow); labels.append('Logo applicativo')
    if not cells:
        return None
    t=RLTable([cells, [P(x, styles['small-muted']) for x in labels]], colWidths=[7.5*cm]*len(cells), hAlign='CENTER')
    t.setStyle(TableStyle([
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('BOTTOMPADDING',(0,0),(-1,0),4),('TOPPADDING',(0,1),(-1,1),0),
        ('TEXTCOLOR',(0,1),(-1,1),colors.HexColor('#666666')),
    ]))
    return t


def _numbered_canvas(canvas, doc):
    canvas.saveState()
    page=str(canvas.getPageNumber())
    footer=f'Pagina {page}'
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#666666'))
    canvas.drawRightString(A4[0]-doc.rightMargin, 0.55*cm, footer)
    canvas.drawString(doc.leftMargin, 0.55*cm, 'Registro incidenti informatici')
    canvas.restoreState()


def _section_title(title, styles, min_height=3.0*cm):
    return [CondPageBreak(min_height), Paragraph(title, styles['section-heading'])]


def _add_section(story, title, content, styles, min_height=3.0*cm):
    block=_section_title(title, styles, min_height=min_height)
    if isinstance(content, list):
        block.extend(content)
    else:
        block.append(content)
    story.extend(block)
    story.append(Spacer(1, 0.22*cm))

def _format_pdf_datetime(value):
    """Formatta date/ore dei PDF incidente con secondi interi.

    Il report non deve mostrare microsecondi o frazioni di secondo; quando un
    valore datetime/time è disponibile, i secondi vengono sempre espressi come
    componente intera nel formato HH:MM:SS.
    """
    if not value:
        return ''
    if hasattr(value, 'replace') and hasattr(value, 'strftime'):
        try:
            value = value.replace(microsecond=0)
        except TypeError:
            pass
        if hasattr(value, 'date'):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return value.strftime('%H:%M:%S')
    return str(value)

def _format_upload_datetime(value):
    return _format_pdf_datetime(value)

def _format_incident_period(inc):
    start=_format_pdf_datetime(getattr(inc, 'start_at', None))
    end=_format_pdf_datetime(getattr(inc, 'end_at', None))
    return f'{start} - {end}' if end else start

def _format_incident_duration(inc):
    value=getattr(inc, 'effective_duration', None)
    if value is None:
        return ''
    total_seconds=int(value.total_seconds())
    days, remainder=divmod(total_seconds, 86400)
    hours, remainder=divmod(remainder, 3600)
    minutes, seconds=divmod(remainder, 60)
    if days:
        return f'{days} giorni, {hours:02d}:{minutes:02d}:{seconds:02d}'
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
def incident_pdf(inc):
    fd,path=tempfile.mkstemp(suffix='.pdf'); os.close(fd)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle('report-title', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=colors.HexColor('#1f3a5f'), alignment=1, spaceAfter=8))
    styles.add(ParagraphStyle('report-subtitle', parent=styles['BodyText'], fontSize=9, leading=12, alignment=1, textColor=colors.HexColor('#555555')))
    styles.add(ParagraphStyle('section-heading', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=colors.white, backColor=colors.HexColor('#1f3a5f'), borderPadding=(4, 5, 4), spaceBefore=8, spaceAfter=6, keepWithNext=True))
    styles.add(ParagraphStyle('small-muted', parent=styles['BodyText'], fontSize=7, leading=9, textColor=colors.HexColor('#666666'), alignment=1))
    small=ParagraphStyle('small',parent=styles['BodyText'],fontSize=7.5,leading=9)
    body=ParagraphStyle('body',parent=styles['BodyText'],fontSize=9,leading=12)

    story=[]
    logos=_report_logos_table(styles)
    if logos:
        story += [logos, Spacer(1,0.45*cm)]
    story += [Paragraph('Report incidente informatico',styles['report-title'])]
    story += [Paragraph(f"{inc.name or ''} - riferimento {inc.reference or '-'}", styles['report-subtitle']), Spacer(1,0.5*cm)]

    index_rows=[['Indice sintetico'],['Sintesi'],['Descrizione'],['Categorie e dati interessati'],['Conseguenze derivate'],['Misure adottate'],['Raccomandazioni'],['Personale coinvolto'],['Azioni intraprese'],['Grafico azioni nel tempo'],['Documenti']]
    story += [Paragraph('Indice sintetico', styles['section-heading']), wrap_table(index_rows, small, widths=[17.5*cm]), Spacer(1,0.25*cm)]

    meta=[['Campo','Valore'],['Nome',inc.name],['Riferimento',inc.reference or ''],['Compilatore',inc.creator_name],['Email compilatore',inc.creator_email],['Gravità',inc.severity.value if inc.severity else ''],['Stato',inc.status],['Periodo',_format_incident_period(inc)],['Durata',_format_incident_duration(inc) or ''],['Dati personali','Sì' if inc.personal_data else 'No'], ['Numero interessati', getattr(inc, 'data_subjects_count', '') or ''], ['Volume dati', getattr(inc, 'data_volume', '') or ''], ['Titolare',_setting_value('security_owner_name')], ['Ruolo titolare',_setting_value('security_owner_role')], ['Struttura',_setting_value('structure_name')], ['Responsabile',_setting_value('security_responsible_name')], ['Email responsabile',_setting_value('security_responsible_email')], ['Telefono responsabile',_setting_value('security_responsible_phone','-')], ['Funzione responsabile',_setting_value('security_responsible_function')]]
    _add_section(story, 'Sintesi', wrap_table(meta, small), styles)
    _add_section(story, 'Descrizione', P(inc.description,body), styles)
    _add_section(story, 'Categorie e dati interessati', wrap_table([['Categorie',', '.join(x.value for x in inc.categories)],['Dati interessati',', '.join(x.value for x in inc.data_types)]], small), styles)
    _add_section(story, 'Conseguenze derivate', wrap_table([['Conseguenze']] + [[x] for x in _incident_consequences(inc)], small, widths=[17.5*cm]), styles)
    _add_section(story, 'Misure adottate', wrap_table([['Misure']] + [[x] for x in _incident_measures(inc)], small, widths=[17.5*cm]), styles)
    _add_section(story, 'Raccomandazioni', wrap_table([['Raccomandazione']] + [[r.text] for r in inc.recommendations], small, widths=[17.5*cm]), styles)
    people=sorted(inc.people,key=lambda p:p.name.lower())
    _add_section(story, 'Personale coinvolto', wrap_table([['Nome','Email']]+[[p.name,p.email or ''] for p in people], small), styles)
    actions=[['Data e ora','Label','Persona','Descrizione']]+[[_format_pdf_datetime(a.when_at), a.label.value if a.label else '', a.person_name, a.description or ''] for a in inc.actions]
    _add_section(story, 'Azioni intraprese', wrap_table(actions, small, widths=[3.2*cm,4.0*cm,3.1*cm,7.2*cm]), styles, min_height=4.0*cm)
    chart=actions_chart(inc)
    if chart:
        _add_section(story, 'Grafico azioni nel tempo', Image(chart,width=17.5*cm,height=7*cm), styles, min_height=8.5*cm)
    docs=[['Documento','Caricato il']]+[[d.filename,_format_upload_datetime(d.uploaded_at)] for d in inc.documents]
    _add_section(story, 'Documenti', wrap_table(docs, small, widths=[14.0*cm,3.5*cm]), styles)
    doc=SimpleDocTemplate(path,pagesize=A4,rightMargin=1.1*cm,leftMargin=1.1*cm,topMargin=1.1*cm,bottomMargin=1.1*cm)
    doc.build(story, onFirstPage=_numbered_canvas, onLaterPages=_numbered_canvas)
    return path

def wrap_table(data, style, widths=None):
    if widths is None: widths=[4*cm,13*cm] if len(data[0])==2 else None
    wrapped=[[P(c,style) for c in row] for row in data]
    t=RLTable(wrapped,colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dbe6f3')),('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#1f3a5f')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('VALIGN',(0,0),(-1,-1),'TOP'),('FONTSIZE',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#f7f9fc')])]))
    return t

def actions_chart(inc):
    acts=list(inc.actions)
    if not acts: return None
    path=tempfile.mktemp(suffix='.png')
    labels=[a.label.value if a.label else 'azione' for a in acts]
    xs=[a.when_at for a in acts]
    ys=list(range(1,len(acts)+1))
    plt.figure(figsize=(10,4)); plt.plot(xs,ys,marker='o'); plt.yticks(ys,labels,fontsize=7); plt.xticks(rotation=25,fontsize=7); plt.tight_layout(); plt.savefig(path,dpi=150); plt.close(); return path

# --- Report PDF statistiche -------------------------------------------------
def _safe_label(value):
    return str(value or 'Non specificato')


def _incident_duration_hours(incident):
    seconds = getattr(incident, 'effective_duration_seconds', None)
    if seconds is not None:
        return max(0, seconds / 3600)
    return None


def _count_values(values):
    counts = {}
    for value in values:
        key = _safe_label(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())))


def _count_many(incidents, relation_name):
    values = []
    for incident in incidents:
        for label in getattr(incident, relation_name, []) or []:
            values.append(getattr(label, 'value', None))
    return _count_values(values)


def _bar_chart(counts, title):
    if not counts:
        return None
    path = tempfile.mktemp(suffix='.png')
    labels = list(counts.keys())[:12]
    values = [counts[k] for k in labels]
    plt.figure(figsize=(8.5, 4.4))
    plt.bar(range(len(labels)), values)
    plt.title(title)
    plt.xticks(range(len(labels)), labels, rotation=35, ha='right', fontsize=8)
    plt.ylabel('Numero incidenti')
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return path


def _pie_chart(counts, title):
    if not counts:
        return None
    path = tempfile.mktemp(suffix='.png')
    labels = list(counts.keys())[:10]
    values = [counts[k] for k in labels]
    plt.figure(figsize=(6.8, 4.4))
    plt.pie(values, labels=labels, autopct='%1.0f%%', textprops={'fontsize': 8})
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return path


def _wrap_stats_table(rows, style, widths=None):
    if not rows:
        rows = [['Voce', 'Valore'], ['Nessun dato disponibile', '']]
    wrapped = [[P(c, style) for c in row] for row in rows]
    t = RLTable(wrapped, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef7')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _period_statistics(name, incidents, start=None, end=None):
    durations = [_incident_duration_hours(i) for i in incidents]
    durations = [d for d in durations if d is not None]
    actions_count = sum(len(getattr(i, 'actions', []) or []) for i in incidents)
    docs_count = sum(len(getattr(i, 'documents', []) or []) for i in incidents)
    return {
        'name': name,
        'start': start,
        'end': end,
        'incidents': incidents,
        'count': len(incidents),
        'avg_duration': (sum(durations) / len(durations)) if durations else 0,
        'min_duration': min(durations) if durations else 0,
        'max_duration': max(durations) if durations else 0,
        'actions_count': actions_count,
        'documents_count': docs_count,
        'categories': _count_many(incidents, 'categories'),
        'data_types': _count_many(incidents, 'data_types'),
        'severity': _count_values([(i.severity.value if i.severity else None) for i in incidents]),
        'status': _count_values([i.status for i in incidents]),
        'personal_data': _count_values(['Sì' if i.personal_data else 'No' for i in incidents]),
        'creators': _count_values([i.creator_name for i in incidents]),
        'action_labels': _count_values([(a.label.value if a.label else None) for i in incidents for a in (i.actions or [])]),
    }


def statistics_pdf(periods):
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    styles = getSampleStyleSheet()
    small = ParagraphStyle('stats-small', parent=styles['BodyText'], fontSize=7, leading=8)
    body = ParagraphStyle('stats-body', parent=styles['BodyText'], fontSize=9, leading=11)
    story = [Paragraph('Report statistiche incidenti', styles['Title']), Spacer(1, 0.25*cm)]
    story.append(Paragraph('Il report aggrega gli incidenti per finestra temporale e usa categorie, dati interessati, gravità, stato, dati personali, compilatore, azioni, documenti e durata dove disponibili.', body))
    story.append(Spacer(1, 0.35*cm))
    summary_rows = [['Finestra', 'Incidenti', 'Durata media (ore)', 'Azioni', 'Documenti']]
    for p in periods:
        summary_rows.append([p['name'], p['count'], f"{p['avg_duration']:.2f}", p['actions_count'], p['documents_count']])
    story += [Paragraph('Riepilogo generale', styles['Heading2']), _wrap_stats_table(summary_rows, small, widths=[6*cm, 2.5*cm, 3.5*cm, 2.5*cm, 2.5*cm]), Spacer(1, 0.35*cm)]

    for p in periods:
        story.append(Paragraph(p['name'], styles['Heading1']))
        period_desc = []
        if p.get('start'):
            period_desc.append(f"dal {p['start']}")
        if p.get('end'):
            period_desc.append(f"al {p['end']}")
        if period_desc:
            story.append(Paragraph('Periodo: ' + ' '.join(period_desc), body))
        kpi = [
            ['Indicatore', 'Valore'],
            ['Incidenti', p['count']],
            ['Durata media', f"{p['avg_duration']:.2f} ore"],
            ['Durata minima', f"{p['min_duration']:.2f} ore"],
            ['Durata massima', f"{p['max_duration']:.2f} ore"],
            ['Azioni registrate', p['actions_count']],
            ['Documenti allegati', p['documents_count']],
        ]
        story.append(_wrap_stats_table(kpi, small, widths=[7*cm, 10*cm]))
        story.append(Spacer(1, 0.2*cm))

        for title, counts in [
            ('Incidenti per categoria', p['categories']),
            ('Incidenti per dati interessati', p['data_types']),
            ('Incidenti per gravità', p['severity']),
            ('Incidenti per stato', p['status']),
            ('Incidenti con dati personali', p['personal_data']),
            ('Incidenti per compilatore', p['creators']),
            ('Azioni per label', p['action_labels']),
        ]:
            rows = [[title, 'Numero']] + [[k, v] for k, v in counts.items()]
            story.append(Paragraph(title, styles['Heading2']))
            story.append(_wrap_stats_table(rows, small, widths=[12*cm, 5*cm]))
            bar = _bar_chart(counts, title)
            pie = _pie_chart(counts, title)
            if bar:
                story.append(Spacer(1, 0.15*cm))
                story.append(Image(bar, width=17*cm, height=8.8*cm))
            if pie:
                story.append(Spacer(1, 0.15*cm))
                story.append(Image(pie, width=14*cm, height=9*cm))
            story.append(Spacer(1, 0.25*cm))

    SimpleDocTemplate(path, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm).build(story)
    return path
