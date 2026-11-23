#!/usr/bin/env python3
"""Render the isolated home proposal as native design boards, not browser screenshots.

ReportLab, PyMuPDF, Pillow and local DejaVu fonts are required. The incident
fixtures, palette, icon paths and standalone preview come from the adjacent
prototype files. No application or approved login file is changed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re

import fitz
from PIL import Image
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PHOTO = HERE.parents[1] / 'visual-assets' / 'cybersecurity-hero-v2.png'
LOGO = ROOT / 'app/static/cir-application-logo.svg'
CSS = (HERE / 'styles.css').read_text()
TOKENS = dict(re.findall(r'--([a-z]+):([^;}]+)', re.search(r':root\{([^}]+)\}', CSS).group(1)))
FONTS = Path('/usr/share/fonts/truetype/dejavu')
for name, file in [('UI','DejaVuSans.ttf'),('UIB','DejaVuSans-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
FIXTURES = sorted([r for r in json.loads((HERE/'fixtures.json').read_text()) if r['tenant']=='default'], key=lambda r:r['start_at'], reverse=True)
JS = (HERE/'home.js').read_text()
ICON_SOURCE = re.search(r'const ICONS=\{(.*?)\};', JS, re.S).group(1)
ICONS = dict(re.findall(r"([a-z]+):'([^']+)'", ICON_SOURCE))
PHOTO_SIZE = Image.open(PHOTO).size
LOGO_DOC = fitz.open(stream=LOGO.read_bytes(), filetype='svg')
LOGO_IMAGE = ImageReader(io.BytesIO(LOGO_DOC[0].get_pixmap(matrix=fitz.Matrix(1,1), alpha=True).tobytes('png')))


def color(name):
    value=TOKENS.get(name,name)
    if len(value)==4 and value.startswith('#'):value='#'+''.join(ch*2 for ch in value[1:])
    return HexColor(value)


def fmt(value):
    if not value:return '—'
    date,time=value.split('T')
    return '/'.join(date.split('-')[::-1])+' '+time


class Board:
    def __init__(self,c,w,h,label):
        self.c,self.w,self.h=c,w,h
        c.setPageSize((w,h))
        self.rect(0,0,w,h,'paper')
        self.rect(0,0,w,34,'#eaf0f4')
        self.text('Mockup pagina principale · da approvare',18 if w<500 else 26,22,9 if w<500 else 11,'muted')
        self.text(label,w-18 if w<500 else w-26,22,9 if w<500 else 10,'muted',anchor='right')

    def rect(self,x,y,w,h,fill,radius=0,stroke=None):
        self.c.setFillColor(color(fill));self.c.setStrokeColor(color(stroke or fill));self.c.setLineWidth(.8)
        self.c.roundRect(x,self.h-y-h,w,h,radius,fill=1,stroke=bool(stroke))

    def line(self,x,y,x2,y2,stroke='line',width=.8):
        self.c.setStrokeColor(color(stroke));self.c.setLineWidth(width)
        self.c.line(x,self.h-y,x2,self.h-y2)

    def text(self,s,x,y,size=12,fill='ink',bold=False,anchor='left'):
        self.c.setFillColor(color(fill));self.c.setFont('UIB' if bold else 'UI',size)
        fn={'left':self.c.drawString,'right':self.c.drawRightString,'center':self.c.drawCentredString}[anchor]
        fn(x,self.h-y,s)

    def wrap(self,s,x,y,width,size=12,fill='ink',bold=False,leading=None):
        font='UIB' if bold else 'UI';leading=leading or size*1.45
        line='';lines=[]
        for word in s.split():
            candidate=(line+' '+word).strip()
            if line and pdfmetrics.stringWidth(candidate,font,size)>width:lines.append(line);line=word
            else:line=candidate
        if line:lines.append(line)
        for i,line in enumerate(lines):self.text(line,x,y+i*leading,size,fill,bold)
        return y+len(lines)*leading

    def logo(self,x,y,s=42):
        self.c.drawImage(LOGO_IMAGE,x,self.h-y-s,s,s,mask='auto')

    def photo(self,x,y,w,h,radius=10,mobile=False):
        # Keep real hardware/monitor recognizable instead of cropping a 3:1
        # scene to the full 10:1 desktop banner. Right aligned, height based.
        iw,ih=PHOTO_SIZE
        scale=h*(1 if mobile else 1.32)/ih;dw,dh=iw*scale,ih*scale
        self.c.saveState();p=self.c.beginPath();p.roundRect(x,self.h-y-h,w,h,radius);self.c.clipPath(p,stroke=0,fill=0)
        self.c.setFillColor(color('deep'));self.c.rect(x,self.h-y-h,w,h,fill=1,stroke=0)
        self.c.drawImage(str(PHOTO),x+w-dw,self.h-y-h+(h-dh)/2,dw,dh)
        stops=[(0,.98),(.45,.86),(.65,.35),(1,.05)] if mobile else [(0,.98),(.56,.98),(.76,.25),(1,0)]
        steps=110
        for i in range(steps):
            t=i/(steps-1)
            for (a,av),(z,zv) in zip(stops,stops[1:]):
                if a<=t<=z:
                    alpha=av+(zv-av)*(t-a)/(z-a);break
            self.c.setFillColor(Color(.031,.11,.17,alpha=alpha))
            self.c.rect(x+i*w/steps,self.h-y-h,w/steps+.5,h,fill=1,stroke=0)
        self.c.restoreState()

    def icon(self,name,x,y,size=18,fill='#c8d9e5'):
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 24 24"><path d="{ICONS[name]}" stroke="{TOKENS.get(fill,fill)}" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        d=fitz.open(stream=svg.encode(),filetype='svg')
        pix=d[0].get_pixmap(alpha=True)
        self.c.drawImage(ImageReader(io.BytesIO(pix.tobytes('png'))),x,self.h-y-size,size,size,mask='auto')

    def button(self,label,x,y,w,h=38,primary=False,size=11,muted=False):
        self.rect(x,y,w,h,'blue' if primary else ('#f7f9fb' if muted else 'white'),6,None if primary else '#c9d6e2')
        self.text(label,x+w/2,y+h/2+size*.35,size,'white' if primary else ('#91a0ad' if muted else 'ink'),True,anchor='center')

    def checkbox(self,x,y,size=14):self.rect(x,y,size,size,'white',3,'#bccbd7')

    def search_icon(self,x,y,size=17):
        self.c.setStrokeColor(color('#647f92'));self.c.setLineWidth(1.4)
        self.c.circle(x+size*.4,self.h-y-size*.4,size*.3,fill=0,stroke=1)
        self.line(x+size*.63,y+size*.63,x+size*.95,y+size*.95,'#647f92',1.4)

    def state(self,row,x,y):
        closed=row['status']=='Chiuso'
        self.rect(x,y,55 if closed else 54,23,'#e5f3eb' if closed else '#fff3dc',4)
        self.text(row['status'],x+(27.5 if closed else 27),y+15,10,'#2a7254' if closed else '#875a17',anchor='center')

    def workflow(self,state,x,y,size=18):
        bg={'warning':'#fff0ce','ok':'#e3f2e9','finalized':'#e9f0fb'}[state]
        fg={'warning':'#9c6509','ok':'#23704e','finalized':'#36659e'}[state]
        self.rect(x,y,size,size,bg,size/2)
        self.text({'warning':'!','ok':'✓','finalized':'◆'}[state],x+size/2,y+size*.73,size*.6,fg,True,anchor='center')

    def end(self):self.c.showPage()


def sidebar(b,mobile=False):
    width=340 if mobile else 246
    b.rect(0,34,width,b.h-34,'deep')
    b.rect(21,62,42,42,'white',9);b.logo(22,63,40)
    b.text('Cybersecurity',75,78,13,'#edf4f8',True)
    b.text('Incident Registry',75,97,13,'#edf4f8',True)
    if mobile:b.text('×',312,86,24,'#b2c8d6',anchor='center')
    b.text('AREA OPERATIVA',32,145,9,'#7e9aad')
    y=162
    entries=[('Incidenti','list'),('Statistiche','chart'),('Notifiche','bell'),('Moduli','file'),('Import / Export','arrows'),('AMMINISTRAZIONE',None),('Workflow e catalogo','workflow'),('Configurazione tenant','gear'),('Tenants Default','layers'),('Utenti e accessi','users'),('Stato e audit','shield'),('SUPPORTO',None),('Aiuto','help'),('Impostazioni','gear')]
    rowheight=49 if mobile else 49
    for label,name in entries:
        if name is None:
            y+=18;b.text(label,32,y+12,9,'#7e9aad');y+=28;continue
        if label=='Incidenti':
            b.rect(18,y,width-36,43,'#234f83',8)
            b.rect(18,y+9,3,25,'cyan',1.5)
        b.icon(name,32,y+12,18,'#ffffff' if label=='Incidenti' else '#c8d9e5')
        b.text(label,63,y+28,14 if mobile else 12.5,'#ffffff' if label=='Incidenti' else '#c8d9e5',label=='Incidenti')
        if label!='Incidenti':b.text('›',width-34,y+28,16,'#86a4b9',anchor='right')
        y+=rowheight
    foot=max(y+36,b.h-44)
    if foot>b.h-30:foot=b.h-36
    b.line(31,foot-24,width-31,foot-24,'#234157')
    b.rect(32,foot-4,5,5,'cyan',2.5);b.text('CIR  0.9.0-1',45,foot+1,10,'#93aab9')
    b.text('Info',width-32,foot+1,10,'#b6c7d3',anchor='right')


def banner(b,x,y,w,mobile=False):
    b.photo(x,y,w,113 if mobile else 122,10 if mobile else 12,mobile=mobile)
    b.text('REGISTRO DEGLI INCIDENTI DI SICUREZZA',x+(17 if mobile else 26),y+28,7 if mobile else 8,'#a0ccd6')
    if mobile:
        b.text('Cybersecurity',x+17,y+55,22,'white',True)
        b.text('Incident Registry',x+17,y+80,22,'white',True)
        # The compact mobile brand banner shows identity only. The professional
        # caption remains in the desktop banner and the approved login.
    else:
        b.text('Cybersecurity Incident Registry',x+26,y+66,27,'white',True)
        b.text('Gestione degli incidenti di sicurezza e tracciabilità delle attività.',x+26,y+94,12,'#d3e8ee')


def desktop(c):
    b=Board(c,1536,1140,'Desktop · dati dimostrativi')
    sidebar(b)
    b.rect(246,34,1290,84,'white');b.line(246,118,1536,118)
    b.text('Area operativa',278,82,12,'muted');b.text('/',380,82,12,'#afbdc8');b.text('Incidenti',404,82,12,'ink',True)
    b.text('Tenant attivo',1043,81,11,'muted')
    b.rect(1130,57,137,39,'white',6,'#cad6e0');b.text('default',1143,81,12);b.text('⌄',1250,80,13,'muted')
    b.rect(1291,59,34,34,'#ebf1f8',17,'#c6d7e9');b.text('AD',1308,81,11,'blue',True,'center')
    b.text('Admin demo',1335,73,12,'ink');b.text('Super admin',1335,90,10,'muted');b.text('⌄',1497,81,13,'muted')
    x=278;w=1226
    banner(b,x,143,w)
    b.text('Incidenti registrati',x,309,27,'ink',True)
    b.text(f'{len(FIXTURES)} incidenti · visualizzati 1–{len(FIXTURES)}',x,332,12,'muted')
    b.button('+  Nuovo incidente',x+w-180,288,180,42,True,12)
    b.rect(x,353,w,126,'white',10,'line')
    b.rect(x+18,368,w-142,39,'white',6,'#c9d6e2');b.search_icon(x+30,379,17);b.text('Cerca per parola chiave…',x+60,392,12,'#7a8c9b')
    b.button('Filtri  ⌄',x+w-112,368,94,39)
    fields=[('Label azione','Tutte le label',x+18,395),('Da','gg/mm/aaaa  --:--',x+427,255),('A','gg/mm/aaaa  --:--',x+696,255)]
    for label,value,fx,fw in fields:
        b.text(label,fx,428,10,'#4a6174');b.rect(fx,435,fw,32,'white',5,'#c9d6e2');b.text(value,fx+10,456,11,'#7a8c9b')
    b.button('Cerca',x+w-158,435,77,32,True,11);b.text('Reset',x+w-44,456,11,'blue',True,'center')
    b.checkbox(x+3,503);b.text('Seleziona pagina',x+26,515,11,'muted')
    b.button('Azioni selezionati  ⌄',x+163,495,154,32,False,10.5,True)
    b.text('Per pagina',x+w-140,515,11,'muted');b.rect(x+w-73,495,73,32,'white',5,'#cad6e0');b.text('20',x+w-57,516,11);b.text('⌄',x+w-18,515,12,'muted')
    ty=542;rh=74;hh=43
    b.rect(x,ty,w,hh+rh*len(FIXTURES),'white',10,'line')
    b.rect(x+1,ty+1,w-2,hh-1,'#edf2f7',9)
    widths=[34,291,158,150,173,110,104,106]
    bounds=[x]
    for width in widths:bounds.append(bounds[-1]+width)
    headers=['','Nome dell’incidente  ↕','Inizio / fine  ↓','Riferimento  ↕','Personale coinvolto  ↕','Stato  ↕','Durata  ↕','Azioni']
    for i,heading in enumerate(headers):b.text(heading,bounds[i]+8,ty+27,10,'#587086',True)
    for index,row in enumerate(FIXTURES):
        y=ty+hh+index*rh
        b.line(x,y,x+w,y,'#e5ecf1')
        b.checkbox(x+12,y+30,13)
        b.workflow(row['workflow'],bounds[1]+8,y+21)
        b.wrap(row['name'],bounds[1]+33,y+31,widths[1]-48,12,'#1c416a',True,18)
        b.text(fmt(row['start_at']),bounds[2]+8,y+31,10.5,'#3e566a')
        if row['end_at']:b.text(fmt(row['end_at']),bounds[2]+8,y+49,10.5,'#8796a3')
        b.text(row['reference'],bounds[3]+8,y+38,10.5,'#3e566a')
        b.wrap(row['people'],bounds[4]+8,y+31,widths[4]-19,11,'#3e566a',leading=18)
        b.state(row,bounds[5]+8,y+25)
        b.text(row['duration'],bounds[6]+8,y+39,11,'#3e566a')
        b.rect(bounds[7]+8,y+25,37,25,'#f3f7fb',4,'#dce5ed');b.text('PDF',bounds[7]+26.5,y+42,10,'#385b7d',anchor='center')
        b.text('⋯',bounds[7]+69,y+44,21,'#496579',anchor='center')
    ly=ty+hh+rh*len(FIXTURES)+28
    for sx,state,label in [(x,'warning','Task da completare'),(x+176,'finalized','Workflow finalizzato'),(x+354,'ok','Chiuso senza avvisi')]:
        b.workflow(state,sx,ly-11,14);b.text(label,sx+20,ly,9,'muted')
    b.button('‹',x+w-100,ly-20,29,29,size=18,muted=True);b.text('1 / 1',x+w-49,ly,11,'muted',anchor='center');b.button('›',x+w-29,ly-20,29,29,size=18,muted=True)
    b.line(x,1090,x+w,1090);b.text('Cybersecurity Incident Registry · 0.9.0-1',x,1115,9,'#8091a0');b.text('Documentazione e supporto',x+w,1115,9,'#61798d',anchor='right')
    b.end()


def mobile_top(b):
    b.rect(0,34,430,74,'white');b.line(0,108,430,108)
    b.text('☰',18,79,19);b.text('Menu',46,78,13)
    b.text('Tenant attivo',276,62,8,'muted');b.text('default  ⌄',276,80,12)
    b.rect(380,55,31,31,'#ebf1f8',15.5,'#c6d7e9');b.text('AD',395.5,75.5,10,'blue',True,'center')
    banner(b,16,126,398,True)


def mobile(c):
    b=Board(c,430,1628,'Mobile')
    mobile_top(b)
    b.text('Incidenti registrati',16,284,22,'ink',True)
    b.text(f'{len(FIXTURES)} incidenti · visualizzati 1–{len(FIXTURES)}',16,307,11,'muted')
    b.button('+ Nuovo',338,262,76,35,True,10.5)
    b.rect(16,327,398,65,'white',8,'line')
    b.rect(28,340,286,39,'white',6,'#c9d6e2');b.search_icon(39,351,17);b.text('Cerca per parola chiave…',64,365,12,'#7a8c9b')
    b.button('Filtri  ⌄',322,340,80,39,False,11)
    b.checkbox(18,411);b.text('Seleziona pagina',40,422,10,'muted')
    b.button('Azioni ⌄',153,404,70,29,False,10,True)
    b.text('Per pagina',298,422,10,'muted');b.rect(356,404,58,29,'white',5,'#cad6e0');b.text('20  ⌄',368,424,10)
    b.line(16,444,414,444,'#e0e8ed');b.text('Ordina',18,465,10,'muted');b.text('Più recenti  ⌄',408,465,11,'ink',anchor='right')
    ty=484;first_h=326;other_h=128;total_h=first_h+other_h*5
    b.rect(16,ty,398,total_h,'white',8,'line')
    for idx,row in enumerate(FIXTURES):
        y=ty if idx==0 else ty+first_h+(idx-1)*other_h
        h=first_h if idx==0 else other_h
        if idx:b.line(16,y,414,y,'#e0e8ef')
        b.workflow(row['workflow'],31,y+21,17)
        b.wrap(row['name'],56,y+35,307,13,'#1c416a',True,19)
        b.text('⌃' if idx==0 else '⌄',391,y+35,13,'#7d91a0')
        b.text(fmt(row['start_at']),56,y+80,10,'#6c8295')
        b.state(row,342,y+64)
        if idx==0:
            b.line(56,y+102,399,y+102,'#e1e9ef')
            fields=[('Riferimento',row['reference']),('Inizio / fine',fmt(row['start_at'])+' · in corso'),('Personale',row['people']),('Durata',row['duration'])]
            fy=y+125
            for label,value in fields:
                b.text(label,56,fy,11,'#6c8192');b.wrap(value,167,fy,228,11,'#25435b',leading=17)
                fy+=37 if label=='Inizio / fine' else 30
            bx=56
            for label,ww in [('PDF',46),('Clona',63),('Sposta',67),('Elimina',69)]:
                b.button(label,bx,y+252,ww,32,False,10);bx+=ww+7
        sy=y+h-24
        b.checkbox(56,sy-12,13);b.text('Seleziona incidente',76,sy-1,10,'#637b8e')
    ly=ty+total_h+28
    b.workflow('warning',16,ly-10,13);b.text('Task da completare',34,ly,8,'muted')
    b.workflow('finalized',158,ly-10,13);b.text('Workflow finalizzato',176,ly,8,'muted')
    b.workflow('ok',16,ly+13,13);b.text('Chiuso senza avvisi',34,ly+23,8,'muted')
    b.button('‹',314,ly+6,29,29,size=18,muted=True);b.text('1 / 1',364,ly+26,10,'muted',anchor='center');b.button('›',385,ly+6,29,29,size=18,muted=True)
    b.line(16,1571,414,1571);b.text('Cybersecurity Incident Registry · 0.9.0-1',16,1596,8,'#8091a0');b.text('Documentazione',414,1591,8,'#61798d',anchor='right');b.text('e supporto',414,1605,8,'#61798d',anchor='right')
    b.end()


def mobile_menu(c):
    b=Board(c,430,1050,'Menu mobile')
    mobile_top(b)
    b.text('Incidenti registrati',16,284,22,'ink',True)
    b.rect(16,327,398,65,'white',8,'line')
    b.rect(16,484,398,566,'white',8,'line')
    for y in [610,738,866,994]:b.line(16,y,414,y)
    b.c.setFillColor(Color(.024,.106,.173,alpha=.72));b.c.rect(0,0,430,b.h-34,fill=1,stroke=0)
    sidebar(b,True)
    b.end()


def standalone(output):
    html=(HERE/'index.html').read_text()
    css=(HERE/'styles.css').read_text();js=(HERE/'home.js').read_text()
    html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+css+'</style>')
    html=html.replace('<script src="home.js" defer></script>','')
    html=html.replace('</body>','<script>'+js+'</script></body>')
    html=html.replace('../../visual-assets/cybersecurity-hero-v2.png','data:image/png;base64,'+base64.b64encode(PHOTO.read_bytes()).decode())
    html=html.replace('../../../app/static/cir-application-logo.svg','data:image/svg+xml;base64,'+base64.b64encode(LOGO.read_bytes()).decode())
    (output/'CIR_Home_v1.html').write_text(html)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    target=args.output/'CIR_Home_v1.pdf'
    c=canvas.Canvas(str(target));c.setTitle('CIR - Proposta pagina principale');c.setAuthor('Cybersecurity Incident Registry')
    desktop(c);mobile(c);mobile_menu(c);c.save()
    pdf=fitz.open(target)
    for page,name in zip(pdf,['CIR_Home_v1_Desktop.png','CIR_Home_v1_Mobile.png','CIR_Home_v1_Menu_Mobile.png']):
        page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(args.output/name)
    standalone(args.output)
    report={'scope':'main_page_and_navigation_only','approval':'hero revision pending; overall graphics accepted in general','approved_login_changed':False,'application_runtime_changed':False,'native_design_boards_not_browser_screenshots':True,'pages':3,'dimensions':[[1536,1140],[430,1628],[430,1050]],'default_demo':{'role':'superuser','tenant':'default','rows':len(FIXTURES),'sort':'start_at DESC','per_page':20},'photo_sha256':hashlib.sha256(PHOTO.read_bytes()).hexdigest(),'photo_asset':str(PHOTO.relative_to(ROOT)),'hero_revision':'physical server/network hardware and security console; no constellation/node graph','photo_layout':{'desktop':'right aligned, height132%, vertically centered; monitor alert and transfer labels fully retained','mobile':'right aligned, height100%; full scene height retained'},'data_source':'docs/design/home-v1/fixtures.json','common_style_scope':'Non-incident-detail pages; preserve procedural blocks and arrows for future incident-detail proposal.','dependencies':['ReportLab','PyMuPDF','Pillow','local DejaVu fonts']}
    (args.output/'home-v1-metadata.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
