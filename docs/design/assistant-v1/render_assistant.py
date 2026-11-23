#!/usr/bin/env python3
"""Native design boards for the isolated AlBot assistant proposal.

Approved design renderers are read only.  Their native PDF geometry supplies
the underlying pages; this renderer adds the proposed assistant shell without
editing application files or approved images.  These are not browser captures.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys

import fitz
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location('approved_incident_renderer', HERE.parent/'incident-v1/render_incident.py')
inc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inc)
home = inc.home
PHOTO = home.PHOTO
LOGO = home.LOGO
TEXT_LOG = []


class Board(inc.Board):
    def __init__(self, c, w, h, label):
        self.c, self.w, self.h, self.label = c, w, h, label
        c.setPageSize((w, h))

    def text(self, s, x, y, size=12, fill='ink', bold=False, anchor='left'):
        s = str(s)
        width = pdfmetrics.stringWidth(s, 'UIB' if bold else 'UI', size)
        left = x - (width/2 if anchor == 'center' else width if anchor == 'right' else 0)
        if left < -.5 or left+width > self.w+.5 or y > self.h-.5 or y-size < -.5:
            raise ValueError(f'Text outside {self.label}: {s!r} at {left}, {y}')
        TEXT_LOG.append({'page': self.label, 'text': s, 'x': round(left,2), 'y': round(y,2), 'width': round(width,2), 'size': size})
        home.Board.text(self, s, x, y, size, fill, bold, anchor)

    def chat_icon(self, x, y, size=30, dark=False):
        self.rect(x, y, size, size, '#dff2f6' if not dark else '#163b50', 8)
        col = '#23687b' if not dark else '#9bd5df'
        self.rect(x+size*.22, y+size*.25, size*.56, size*.39, '#ffffff' if not dark else '#163b50', 4, col)
        self.line(x+size*.37, y+size*.64, x+size*.29, y+size*.77, col, 1.2)
        self.line(x+size*.29, y+size*.77, x+size*.49, y+size*.64, col, 1.2)
        for dx in (.36,.5,.64):
            self.rect(x+size*dx-1, y+size*.44-1, 2, 2, col, 1)


def bar(b, key, data):
    b.rect(0,0,1920,34,'#eaf0f4')
    b.text('Assistente AI · proposta',26,22,11,'muted')
    b.text(('Dettaglio incidente' if key=='incident' else 'Registro incidenti')+' · desktop con assistente aperto',1894,22,10,'muted',anchor='right')
    home.sidebar(b)
    b.rect(246,34,1314,84,'white')
    b.line(246,118,1560,118)
    b.text('Incidenti',278,81,12,'muted')
    if key=='incident':
        b.text('/',343,81,12,'#afbdc8')
        b.text('INC-2026-0048',367,81,12,'ink',True)
    b.text('Tenant attivo',846,81,11,'muted')
    b.rect(931,57,128,39,'white',6,'#cad6e0')
    b.text('default',944,81,12)
    b.chevron(1042,77)
    b.rect(1075,57,139,39,'#e7f1f8',6,'#aacbdc')
    b.chat_icon(1083,64,25)
    b.text(data['assistant']['entry_label'],1117,81,11.5,'#205474',True)
    b.rect(1240,59,34,34,'#ebf1f8',17,'#c6d7e9')
    b.text('AO',1257,81,11,'blue',True,'center')
    b.text('Admin operativo',1284,73,12)
    b.text('Super admin',1284,90,9.5,'muted')
    b.chevron(1515,77)
    b.rect(1536,118,24,b.h-118,'paper')


def conversation(b, data, key, x, y, w, mobile=False):
    talk=data['conversations'][key]
    fs=12.5 if mobile else 12
    leading=19 if mobile else 18
    qw=w-30
    qlines=inc.lines(talk['question'],qw-26,fs)
    qh=28+len(qlines)*leading
    b.rect(x+w-qw,y,qw,qh,'#e7f1fc',12)
    b.para(talk['question'],x+w-qw+13,y+22,qw-26,fs,'#234f7a',leading=leading)
    yy=y+qh+20
    top=yy
    # Calculate the body before drawing the background, so height follows text.
    body_h=83+len(inc.lines(talk['intro'],w-28,fs))*leading
    for item in talk['steps']:
        body_h+=max(1,len(inc.lines(item,w-60,fs)))*leading+15
    body_h+=len(inc.lines(talk['outro'],w-28,11))*16+35
    b.rect(x,top,w,body_h,'white',10,'#dbe4ec')
    b.chat_icon(x+13,top+12,24)
    b.text(data['assistant']['name'],x+46,top+29,12,'ink',True)
    b.text('Risposta dimostrativa',x+w-13,top+29,9,'muted',anchor='right')
    yy=b.para(talk['intro'],x+14,top+59,w-28,fs,'ink',leading=leading)+12
    for idx,item in enumerate(talk['steps']):
        b.rect(x+14,yy-12,21,21,'#edf4fb',10.5)
        b.text(str(idx+1),x+24.5,yy+3,10,'blue',True,'center')
        yy=b.para(item,x+45,yy+3,w-60,fs,'ink',leading=leading)+15
    b.line(x+14,yy-2,x+w-14,yy-2,'#e2e8ef')
    yy=b.para(talk['outro'],x+14,yy+19,w-28,11,'muted',leading=16)
    if yy > top+body_h-10:
        raise ValueError('Conversation body exceeds measured card')
    return top+body_h


def assistant(b,data,key,x,y,w,h,mobile=False):
    a=data['assistant']
    b.rect(x,y,w,h,'#f6f9fc')
    b.line(x,y,x,y+h,'#cbd9e5',1)
    hh=85 if not mobile else 101
    b.rect(x,y,w,hh,'white')
    if mobile:
        b.text('‹',x+17,y+27,25,'blue')
        b.text(a['mobile_back_incident'] if key=='incident' else a['mobile_back_home'],x+37,y+24,11,'blue',True)
        b.chat_icon(x+18,y+43,34)
        b.text(a['name'],x+64,y+60,16,'ink',True)
        b.text(a['subtitle'],x+64,y+80,10.5,'muted')
        b.text('×',x+w-22,y+65,22,'muted',anchor='center')
    else:
        b.chat_icon(x+18,y+24,34)
        b.text(a['name'],x+64,y+42,16,'ink',True)
        b.text(a['subtitle'],x+64,y+62,10.5,'muted')
        # Match the interactive prototype: expand to focus view, or close the
        # dock while preserving the underlying page and its scroll position.
        cx,cy=x+w-61,y+39
        b.line(cx-5,cy+5,cx+5,cy-5,'muted',1.2)
        b.line(cx+5,cy-5,cx+5,cy,'muted',1.2)
        b.line(cx+5,cy-5,cx,cy-5,'muted',1.2)
        b.line(cx-5,cy+5,cx-5,cy,'muted',1.2)
        b.line(cx-5,cy+5,cx,cy+5,'muted',1.2)
        b.text('×',x+w-25,y+46,22,'muted',anchor='center')
    b.line(x,y+hh,x+w,y+hh)
    yy=y+hh+17
    b.pill('Tenant: '+a['tenant'],x+18,yy,'#e9f1f7','#3b637e',10)
    b.text('Contesto',x+w-36,yy+17,10,'#537089',anchor='right')
    b.rect(x+w-30,yy+6,13,13,'#e7eef4',6.5,'#afc1ce')
    b.text('i',x+w-23.5,yy+16.2,9,'#537089',True,'center')
    yy+=45
    b.text(a['knowledge_label'],x+18,yy,10.2,'#4c657b',True)
    note=a['context_note'] if key=='incident' else a['home_context_note']
    yy=b.para(note,x+18,yy+20,w-36,10.5,'muted',leading=16)+18
    end=conversation(b,data,key,x+18,yy,w-36,mobile)
    suggestions_y=end+25
    b.text('Altre domande',x+18,suggestions_y,10,'muted',True)
    suggestions_y+=11
    labels=[r['label'] for r in data['suggestions'] if r['answer_key'] not in (key,)][:2]
    for label in labels:
        b.button(label,x+18,suggestions_y,w-36,32,False,10.5)
        suggestions_y+=39
    composer_h=174 if mobile else 177
    composer_y=y+h-composer_h
    if suggestions_y>composer_y-14:
        raise ValueError(f'Assistant content overlaps composer {key}: {suggestions_y} > {composer_y-14}')
    b.rect(x,composer_y,w,composer_h,'white')
    b.line(x,composer_y,x+w,composer_y,'#d5e1eb')
    b.text('Domanda per AlBot',x+18,composer_y+24,10.5,'muted')
    b.rect(x+18,composer_y+36,w-36,62,'#fbfcfe',8,'#c4d3df')
    b.text(a['composer_placeholder'],x+31,composer_y+62,12,'#7b8f9f')
    b.button('Invia',x+w-98,composer_y+108,80,34,True,11)
    b.text('Nuova domanda',x+18,composer_y+130,10,'blue')
    b.text(a['footer_note'],x+18,composer_y+161,9,'muted')


def desktop_overlay(data,key):
    mem=io.BytesIO(); c=canvas.Canvas(mem,invariant=1)
    b=Board(c,1920,1140,key+' desktop')
    bar(b,key,data)
    assistant(b,data,key,1560,34,360,1106)
    b.end();c.save()
    return fitz.open(stream=mem.getvalue(),filetype='pdf')


def mobile_closed_overlay(data):
    mem=io.BytesIO();c=canvas.Canvas(mem,invariant=1)
    b=Board(c,430,1036,'mobile closed')
    b.rect(0,0,430,34,'#eaf0f4')
    b.text('Mockup assistente AI · chiuso',16,22,9,'muted')
    b.rect(0,34,430,74,'white');b.line(0,108,430,108)
    for yy in (64,70,76):b.line(19,yy,35,yy,'ink',1.5)
    b.text('Menu',47,77,12)
    b.rect(127,55,121,39,'#eaf2f8',7,'#b8d1e0')
    b.chat_icon(135,62,25)
    b.text(data['assistant']['entry_label'],167,79,10.6,'#205474',True)
    b.text('Tenant attivo',265,61,8,'muted')
    b.text('default',265,81,12)
    b.chevron(347,76)
    b.rect(380,55,31,31,'#ebf1f8',15.5,'#c6d7e9')
    b.text('AO',395.5,75.5,10,'blue',True,'center')
    b.end();c.save()
    return fitz.open(stream=mem.getvalue(),filetype='pdf')


def mobile_open(data):
    mem=io.BytesIO();c=canvas.Canvas(mem,invariant=1)
    b=Board(c,430,1036,'mobile open')
    b.rect(0,0,430,1036,'#f6f9fc')
    b.rect(0,0,430,34,'#eaf0f4')
    b.text('Mockup assistente AI · aperto',16,22,9,'muted')
    assistant(b,data,'incident',0,34,430,1002,True)
    b.end();c.save()
    return fitz.open(stream=mem.getvalue(),filetype='pdf')


def mobile_plate():
    mem=io.BytesIO();c=canvas.Canvas(mem,invariant=1)
    b=Board(c,940,1140,'mobile comparison')
    b.rect(0,0,940,1140,'#edf2f6')
    b.text('Assistente AI su mobile',24,29,17,'ink',True)
    b.text('Due stati della stessa pagina · dati dimostrativi',916,29,10,'muted',anchor='right')
    b.text('1. Pagina incidente · accesso dalla testata',24,58,11,'#41607a',True)
    b.text('2. Conversazione · ritorno immediato all’incidente',486,58,11,'#41607a',True)
    b.rect(23,69,432,1038,'white',0,'#c8d5e0')
    b.rect(485,69,432,1038,'white',0,'#c8d5e0')
    b.text('Il workflow conserva tutta la larghezza quando l’assistente è chiuso.',24,1127,10,'muted')
    b.end();c.save()
    return fitz.open(stream=mem.getvalue(),filetype='pdf')


def approved_bases():
    data=json.loads((HERE.parent/'incident-v1/fixtures.json').read_text())
    mem=io.BytesIO();c=canvas.Canvas(mem,invariant=1)
    inc.desktop(c,data);home.desktop(c);inc.mobile(c,data);c.save()
    return fitz.open(stream=mem.getvalue(),filetype='pdf')


def create_boards(output,data):
    bases=approved_bases();pdf=fitz.open()
    for idx,key in enumerate(('incident','home')):
        page=pdf.new_page(width=1920,height=1140)
        page.draw_rect(page.rect,color=None,fill=(.96,.97,.985))
        page.show_pdf_page(fitz.Rect(0,0,1536,1140),bases,idx,clip=fitz.Rect(0,0,1536,1140))
        layer=desktop_overlay(data,key)
        page.show_pdf_page(page.rect,layer,0)
    closed=fitz.open();p=closed.new_page(width=430,height=1036)
    p.show_pdf_page(p.rect,bases,2,clip=fitz.Rect(0,0,430,1036))
    overlay=mobile_closed_overlay(data);p.show_pdf_page(p.rect,overlay,0)
    opened=mobile_open(data);plate=mobile_plate()
    page=pdf.new_page(width=940,height=1140)
    page.show_pdf_page(page.rect,plate,0)
    page.show_pdf_page(fitz.Rect(24,70,454,1106),closed,0)
    page.show_pdf_page(fitz.Rect(486,70,916,1106),opened,0)
    target=output/'CIR_Assistant_v1.pdf'
    pdf.set_metadata({'title':'Cybersecurity Incident Registry - Assistente AI: proposta desktop e mobile','author':'Cybersecurity Incident Registry','subject':'Native design boards, not browser screenshots'})
    pdf.save(target,garbage=4,deflate=True)
    pdf.close();pdf=fitz.open(target)
    names=['CIR_Assistant_v1_Incident_Desktop.png','CIR_Assistant_v1_Home_Desktop.png','CIR_Assistant_v1_Mobile.png']
    for page,name in zip(pdf,names):
        page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(output/name)
    return pdf,names


def standalone(output):
    """Embed the builder's isolated frame package and original approved assets."""
    html=(HERE/'index.html').read_text()
    css=(HERE/'styles.css').read_text()
    js=(HERE/'assistant.js').read_text()
    asset_map="const ASSETS = {logo: '../../../app/static/cir-application-logo.svg', hero: '../../visual-assets/cybersecurity-hero-v2.png'};"
    assert js.count(asset_map)==1, 'Builder ASSETS hook changed; inspect before bundling'
    embedded_assets={
        'logo':'data:image/svg+xml;base64,'+base64.b64encode(LOGO.read_bytes()).decode(),
        'hero':'data:image/png;base64,'+base64.b64encode(PHOTO.read_bytes()).decode(),
    }
    # Only replace the map. Approved PAGE_SOURCES and the source-path search
    # literals in resolveAssets must remain byte-for-byte unchanged.
    js=js.replace(asset_map,'const ASSETS = '+json.dumps(embedded_assets)+';')
    assert '<link rel="stylesheet" href="styles.css">' in html
    html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+css+'</style>')
    assert '<script src="assistant.js" defer></script>' in html
    html=html.replace('<script src="assistant.js" defer></script>','')
    js=re.sub(r'</script',lambda _: '<\\/script',js,flags=re.I)
    html=html.replace('</body>','<script>'+js+'</script></body>')
    # PAGE_SOURCES intentionally retains original relative strings, which the
    # clone builder resolves at runtime from the embedded ASSETS map.
    assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\'](?!data:)',html.split('<script>',1)[0])
    (output/'CIR_Assistant_v1.html').write_text(html)


def verify_deliverables(output, pdf, names, include_html):
    """Record reproducible native-page bounds and final artifact checksums."""
    page_checks=[]
    for page,name in zip(pdf,names):
        spans=[span for block in page.get_text('dict')['blocks'] if 'lines' in block
               for line in block['lines'] for span in line['spans']]
        outside=[span['text'] for span in spans
                 if not (page.rect+(-1,-1,1,1)).contains(fitz.Rect(span['bbox']))]
        assert not outside, f'Text outside PDF page: {outside}'
        expected=(int(page.rect.width),int(page.rect.height))
        with Image.open(output/name) as img:
            assert img.size==expected
        text=page.get_text()
        assert 'AlBot' in text and 'Guida all’applicazione' in text
        page_checks.append({'image':name,'dimensions':list(expected),
                            'text_spans':len(spans),'outside_page_text':outside})
    artifacts=names+['CIR_Assistant_v1.pdf','assistant-v1-metadata.json','assistant-v1-text-geometry.json']
    if include_html:
        artifacts.append('CIR_Assistant_v1.html')
    report={
        'status':'PASS', 'native_pages':page_checks,
        'visual_inspection':'All three native boards reviewed by renderer and root; no overlapping text or obscured action controls observed.',
        'viewport_excerpt':'The incident viewport is deliberately shorter than the scrollable approved page. The autonomous HTML retains all page fields and workflow blocks.',
        'artifact_sha256':{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in artifacts},
        'not_browser_screenshots':True,
        'production_or_application_changes':False,
    }
    (output/'assistant-v1-render-qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--boards-only',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    data=json.loads((HERE/'fixtures.json').read_text())
    pdf,names=create_boards(args.output,data)
    if not args.boards_only:standalone(args.output)
    source_files=['fixtures.json','styles.css','assistant.js','index.html','render_assistant.py']
    metadata={
        'scope':'isolated_assistant_ui_mock_only','approval':'AI assistant layout pending; login/home/incident approved and preserved',
        'native_design_boards_not_browser_screenshots':True,'application_runtime_changed':False,
        'functional_version':'0.9.0-1','pages':3,'dimensions':[[int(p.rect.width),int(p.rect.height)] for p in pdf],
        'layout':data['layout'],'assistant':data['assistant'],'data_source':'docs/design/assistant-v1/fixtures.json',
        'photo_asset':'docs/visual-assets/cybersecurity-hero-v2.png','photo_sha256':hashlib.sha256(PHOTO.read_bytes()).hexdigest(),
        'source_hashes':{f:hashlib.sha256((HERE/f).read_bytes()).hexdigest() for f in source_files if (HERE/f).is_file()},
        'dependencies':['ReportLab','PyMuPDF','Pillow','local DejaVu fonts'],
        'mobile_board':'Two labeled states, each430px: approved incident viewport with header entry, dedicated assistant with return control',
        'viewport_excerpts':'Desktop incident and closed mobile show scrollable viewport excerpts; remaining approved fields and steps continue below the view and remain available in the autonomous HTML.',
        'ai_boundaries':data['boundaries'],
    }
    (args.output/'assistant-v1-metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    (args.output/'assistant-v1-text-geometry.json').write_text(json.dumps(TEXT_LOG,ensure_ascii=False,indent=2)+'\n')
    verify_deliverables(args.output,pdf,names,not args.boards_only)
    print(json.dumps(metadata,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
