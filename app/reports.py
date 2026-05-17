import tempfile, os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table as RLTable, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
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
        when=a.when_at.strftime('%Y-%m-%d %H:%M') if a.when_at else ''
        action_text = f'{label}: {desc}'.strip() if desc else label
        rows.append(f'{action_text} - {when}'.strip(' -'))
    return rows or ['Nessuna misura registrata.']

def P(txt,style): return Paragraph(str(txt or ''), style)
def incident_pdf(inc):
    fd,path=tempfile.mkstemp(suffix='.pdf'); os.close(fd)
    styles=getSampleStyleSheet(); small=ParagraphStyle('small',parent=styles['BodyText'],fontSize=7,leading=8); body=ParagraphStyle('body',parent=styles['BodyText'],fontSize=9,leading=11)
    story=[Paragraph('Report incidente informatico',styles['Title']),Spacer(1,0.2*cm)]
    meta=[['Campo','Valore'],['Nome',inc.name],['Riferimento',inc.reference or ''],['Compilatore',inc.creator_name],['Email compilatore',inc.creator_email],['Gravità',inc.severity.value if inc.severity else ''],['Stato',inc.status],['Periodo',f'{inc.start_at} - {inc.end_at or ""}'],['Dati personali','Sì' if inc.personal_data else 'No'], ['Numero interessati', getattr(inc, 'data_subjects_count', '') or ''], ['Volume dati', getattr(inc, 'data_volume', '') or ''], ['Titolare',_setting_value('security_owner_name')], ['Ruolo titolare',_setting_value('security_owner_role')], ['Struttura',_setting_value('structure_name')], ['Responsabile',_setting_value('security_responsible_name')], ['Email responsabile',_setting_value('security_responsible_email')], ['Telefono responsabile',_setting_value('security_responsible_phone','-')], ['Funzione responsabile',_setting_value('security_responsible_function')]]
    story += [Paragraph('Sintesi',styles['Heading2']), wrap_table(meta, small), Spacer(1,0.3*cm), Paragraph('Descrizione',styles['Heading2']), P(inc.description,body)]
    story += [Paragraph('Categorie e dati interessati',styles['Heading2']), wrap_table([['Categorie',', '.join(x.value for x in inc.categories)],['Dati interessati',', '.join(x.value for x in inc.data_types)]], small)]
    story += [Paragraph('Conseguenze derivate',styles['Heading2']), wrap_table([['Conseguenze']] + [[x] for x in _incident_consequences(inc)], small, widths=[17*cm])]
    story += [Paragraph('Misure adottate',styles['Heading2']), wrap_table([['Misure']] + [[x] for x in _incident_measures(inc)], small, widths=[17*cm])]
    story += [Paragraph('Raccomandazioni',styles['Heading2']), wrap_table([['Raccomandazione']] + [[r.text] for r in inc.recommendations], small, widths=[17*cm])]
    people=sorted(inc.people,key=lambda p:p.name.lower())
    story += [Paragraph('Personale coinvolto',styles['Heading2']), wrap_table([['Nome','Email']]+[[p.name,p.email or ''] for p in people], small)]
    story += [Paragraph('Azioni intraprese',styles['Heading2'])]
    actions=[['Data e ora','Label','Persona','Descrizione']]+[[a.when_at, a.label.value if a.label else '', a.person_name, a.description or ''] for a in inc.actions]
    story.append(wrap_table(actions, small, widths=[3.1*cm,4.2*cm,3.2*cm,7.0*cm]))
    chart=actions_chart(inc)
    if chart: story += [Spacer(1,0.3*cm),Paragraph('Grafico azioni nel tempo',styles['Heading2']),Image(chart,width=17*cm,height=7*cm)]
    docs=[['Documento','Caricato il']]+[[d.filename,d.uploaded_at] for d in inc.documents]
    story += [Paragraph('Documenti',styles['Heading2']), wrap_table(docs, small)]
    SimpleDocTemplate(path,pagesize=A4,rightMargin=1*cm,leftMargin=1*cm,topMargin=1*cm,bottomMargin=1*cm).build(story)
    return path

def wrap_table(data, style, widths=None):
    if widths is None: widths=[4*cm,13*cm] if len(data[0])==2 else None
    wrapped=[[P(c,style) for c in row] for row in data]
    t=RLTable(wrapped,colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef7')),('VALIGN',(0,0),(-1,-1),'TOP'),('FONTSIZE',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3)]))
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
