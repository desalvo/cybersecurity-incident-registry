#!/usr/bin/env python3
"""Native review boards, not browser screenshots. Read mock data and CSS tokens.

Run after the approved preview image assets have been placed in visual-assets.
Requires reportlab, PyMuPDF and Pillow. This does not launch or modify the app.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

import fitz
from PIL import Image
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
ROOT_TOKENS = re.search(r':root\{([^}]+)\}', (HERE / 'styles.css').read_text()).group(1)
TOKENS = dict(re.findall(r"--([a-z]+):([^;}]+)", ROOT_TOKENS))
FONT_DIR = Path('/usr/share/fonts/truetype/dejavu')
pdfmetrics.registerFont(TTFont('UI', str(FONT_DIR / 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('UIB', str(FONT_DIR / 'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFont(TTFont('UII', str(FONT_DIR / 'DejaVuSans-Oblique.ttf')))


def mock_data():
    js = (HERE / 'mockup.js').read_text()
    expression = re.search(r'const state=(.*?);\nstate\.incidents', js, re.S).group(1)
    code = "const vm=require('vm');console.log(JSON.stringify(vm.runInNewContext(" + json.dumps('(' + expression + ')') + ", {URLSearchParams,previewEntry:{ui:'new',view:'dashboard'},initialView:'dashboard',location:{search:'?ui=new'}})));"
    return json.loads(subprocess.check_output(['node', '-e', code], text=True))


def col(token):
    value = TOKENS.get(token, token)
    if re.fullmatch(r'#[0-9a-fA-F]{3}', value): value = '#' + ''.join(ch*2 for ch in value[1:])
    return HexColor(value)


class Board:
    def __init__(self, c, width, height, title):
        self.c, self.w, self.h = c, width, height
        self.offset_y = 0
        c.setPageSize((width, height))
        self.rect(0, 0, width, height, 'paper')
        self.rect(0, 0, width, 55, 'deep')
        self.text('Mockup nuova interfaccia · da approvare', 24, 19, 10 if width > 700 else 9, '#cfdfd6', True)
        self.text(title, 24, 39, 13, '#ffffff', True)
        self.text('Tavola di progetto · dati dimostrativi', width - 24, 30, 10, '#b9d0c7', anchor='right') if width > 700 else None

    def rect(self, x, y, w, h, color='white', radius=0, stroke=None):
        y += self.offset_y
        c = self.c
        c.setFillColor(col(color))
        c.setStrokeColor(col(stroke or color))
        c.setLineWidth(.75)
        c.roundRect(x, self.h - y - h, w, h, radius, fill=1, stroke=bool(stroke))

    def line(self, x, y, x2, y2, color='line', width=.7):
        y += self.offset_y; y2 += self.offset_y
        self.c.setStrokeColor(col(color)); self.c.setLineWidth(width)
        self.c.line(x, self.h-y, x2, self.h-y2)

    def text(self, s, x, y, size=14, color='ink', bold=False, italic=False, anchor='left'):
        y += self.offset_y
        c = self.c
        c.setFillColor(col(color)); c.setFont('UIB' if bold else 'UII' if italic else 'UI', size)
        if anchor == 'right': c.drawRightString(x, self.h-y, str(s))
        elif anchor == 'center': c.drawCentredString(x, self.h-y, str(s))
        else: c.drawString(x, self.h-y, str(s))

    def wrap(self, s, x, y, width, size=14, color='muted', leading=None, bold=False, max_lines=None):
        leading = leading or size*1.55
        font = 'UIB' if bold else 'UI'
        line, lines = '', []
        for word in s.split():
            if line and pdfmetrics.stringWidth(line+' '+word, font, size) > width:
                lines.append(line); line = word
            else: line = (line+' '+word).strip()
        if line: lines.append(line)
        for i, l in enumerate(lines[:max_lines] if max_lines else lines): self.text(l, x, y+i*leading, size, color, bold)
        return y+len(lines)*leading

    def photo(self, name, x, y, w, h, radius=0, darkness=0):
        y += self.offset_y
        p = HERE.parent/'visual-assets'/name
        if not p.exists(): raise FileNotFoundError(p)
        iw, ih = Image.open(p).size
        scale = max(w/iw, h/ih); dw, dh = iw*scale, ih*scale
        c = self.c; c.saveState(); path = c.beginPath()
        path.roundRect(x, self.h-y-h, w, h, radius); c.clipPath(path, stroke=0, fill=0)
        c.drawImage(str(p), x+(w-dw)/2, self.h-y-h+(h-dh)/2, dw, dh)
        if darkness:
            c.setFillColor(Color(.02,.12,.15,alpha=darkness)); c.rect(x,self.h-y-h,w,h,fill=1,stroke=0)
        c.restoreState()

    def button(self, label, x, y, w=None, primary=False, size=12, h=44):
        w = w or pdfmetrics.stringWidth(label,'UIB',size)+30
        self.rect(x,y,w,h,'teal' if primary else 'white',7, None if primary else 'line')
        self.text(label,x+w/2,y+h/2+size/3,size,'white' if primary else 'ink',True,anchor='center')
        return w

    def pill(self, label,x,y,kind='current',size=10):
        bg,fg = {'current':('#e0eee5','#256153'),'high':('#f8e8e1','#9a493c'),'medium':('#f8efda','#886a2e'),'low':('#edf0ed','#506a60'),'neutral':('#edf0f1','#5e7078'),'obsolete':('#eeeae5','#6f645c')}.get(kind,('#e0eee5','#256153'))
        width=pdfmetrics.stringWidth(label,'UIB',size)+18
        self.rect(x,y,width,24,bg,5);self.text(label,x+9,y+16,size,fg,True)
        return width

    def sidebar(self, active='Panoramica', y=55, h=945):
        self.rect(0,y,232,h,'navy')
        self.text('CIR',30,y+51,32,'white',True)
        self.text('INCIDENT REGISTRY',31,y+71,9,'#aec5c4')
        yy=y+118
        groups=[('SPAZIO OPERATIVO',['Panoramica','Incidenti','Report e statistiche']),('PROCEDURE E RISORSE',['Catalogo workflow','Documenti e notifiche','Amministrazione']),('IL TUO SPAZIO',['Avvisi','Aiuto e formazione'])]
        for caption,items in groups:
            self.text(caption,28,yy,9,'#a6c0c3',True);yy+=15
            for item in items:
                if item==active: self.rect(17,yy,198,46,'mint',8)
                self.rect(31,yy+16,12,12,'#52736e' if item!=active else 'teal',3)
                self.text(item,56,yy+29,12,'#d4e1e5' if item!=active else '#173b39',item==active)
                yy+=49
            yy+=21
        self.rect(22,yy-1,188,44,'#1d3b47',8,'#4b6370')
        self.text('Tutte le funzioni  →',37,yy+27,12,'white',True)
        if h>850:
            self.photo('operations-editorial.png',22,y+h-185,188,123,10,.52)
            self.text('UN METODO CONDIVISO',35,y+h-145,8,'#d0dfd6',True)
            self.text('Procedure comuni.',35,y+h-116,14,'white',True)
            self.text('Decisioni nel tuo tenant.',35,y+h-95,12,'white')
        self.text('●  Ambiente dimostrativo',25,y+h-26,10,'#b5cbc8')
        self.text('0.9.0-1',205,y+h-26,9,'#b5cbc8',anchor='right')

    def chrome(self, active='Panoramica'):
        self.sidebar(active,h=self.h-55)
        self.rect(232,55,self.w-232,77,'#fafbf8')
        self.line(232,132,self.w,132)
        self.text('TENANT ATTIVO',267,82,8,'muted',True)
        self.text('Research Lab  ⌄',267,106,14,'ink',True)
        self.rect(self.w-486,75,310,39,'#fafbf8',7,'line')
        self.text('Cerca incidenti o funzioni        ⌘ K',self.w-472,100,11,'muted')
        self.rect(self.w-86,76,37,37,'mint',18)
        self.text('AM',self.w-67,101,11,'teal',True,anchor='center')
        self.rect(232,132,self.w-232,27,'#e9ede7')
        self.text('Mockup nuova interfaccia · da approvare',267,150,10,'#49695e')
        self.text('CIR 0.9.0-1 · dati dimostrativi',self.w-35,150,9,'muted',anchor='right')

    def mobile_chrome(self):
        self.rect(0,55,self.w,68,'#fafbf8')
        self.text('☰',19,96,20,'ink');self.text('TENANT ATTIVO',57,76,8,'muted',True)
        self.text('Research Lab  ⌄',57,102,14,'ink',True)
        self.rect(self.w-57,72,36,36,'mint',18);self.text('AM',self.w-39,97,11,'teal',True,anchor='center')
        self.rect(0,123,self.w,27,'#e9ede7')
        self.text('Anteprima · dati dimostrativi · da approvare',18,141,10,'#49695e')

    def mobile_dock(self,y):
        self.rect(0,y,self.w,66,'#fafcf9');self.line(0,y,self.w,y)
        for i,(symbol,label) in enumerate([('▦','Home'),('◇','Incidenti'),('⌘','Workflow'),('●','Avvisi'),('☰','Menu')]):
            x=self.w/5*(i+.5);self.text(symbol,x,y+26,19,'teal',anchor='center');self.text(label,x,y+49,10,'teal',anchor='center')

    def end(self): self.c.showPage()


def desktop_login(c,data):
    b=Board(c,1440,1020,'01 / Login · desktop')
    b.photo('operations-editorial.png',26,81,700,913,18,.54)
    b.text('CIR',74,159,39,'white',True);b.line(166,119,166,161,'#9dbab1')
    b.text('Cybersecurity',190,135,12,'#dbe6df');b.text('Incident Registry',190,156,12,'#dbe6df')
    b.text('DALLA SEGNALAZIONE ALLA CHIUSURA',74,245,10,'#d1dfc0',True)
    b.text('Ogni incidente.',74,316,53,'white',True)
    b.text('Una risposta',74,380,53,'white',True)
    b.text('organizzata.',74,448,53,'#dce3c9',italic=True)
    b.wrap('Il registro, le procedure e le evidenze che danno continuità alla gestione degli incidenti di sicurezza.',74,504,505,17,'#e1eae4',28)
    xx=72
    for label in ('Incidenti','Workflow','Documenti','Notifiche'):
        ww=pdfmetrics.stringWidth(label,'UI',12)+30;b.rect(xx,915,ww,40,'#193d45',20,'#809992');b.text(label,xx+15,940,12,'white');xx+=ww+11
    x=868;w=420
    b.rect(x,116,40,40,'#e4eee4',20);b.text('RL',x+20,142,12,'teal',True,anchor='center');b.text('Research Lab',x+54,142,16,'ink',True)
    b.text('◇  Cybersecurity Incident Registry',x,213,13,'muted')
    b.text('IL TUO SPAZIO DI LAVORO',x,265,10,'teal',True)
    b.text('Accedi a CIR.',x,310,38,'ink',True)
    b.wrap('Entra nello spazio operativo della tua organizzazione.',x,347,w,15,'muted',24)
    b.text('Username',x,409,14,'ink',True);b.rect(x,423,w,51,'white',7,'#cbd6ce');b.text('demo',x+16,455,16,'ink')
    b.text('Password',x,512,14,'ink',True);b.rect(x,526,w,51,'white',7,'#cbd6ce');b.text('••••••••',x+16,559,16,'ink')
    b.button('Accedi  →',x,604,w,True,size=15,h=51)
    b.text('Account locale o LDAP, secondo configurazione.',x+w/2,684,12,'muted',anchor='center')
    b.line(x,719,x+170,719);b.text('oppure',x+w/2,723,12,'muted',anchor='center');b.line(x+250,719,x+w,719)
    b.button('Accedi con Research Identity',x,747,w,size=14,h=51)
    b.text('Esempio di profilo SSO configurato.',x+w/2,822,11,'muted',anchor='center')
    b.line(x,847,x+w,847);b.text('Credenziali fittizie: demo / cir-demo.',x,875,12,'muted');b.text('Non inserire credenziali reali.',x,898,12,'muted')
    b.text('Esamina il passaggio MFA  →',x,935,12,'teal',True)
    b.text('Cybersecurity Incident Registry',x,981,10,'muted');b.text('0.9.0-1',x+w,981,10,'muted',anchor='right')
    b.end()


def mobile_login(c,data):
    b=Board(c,390,1110,'02 / Login · mobile')
    x=24;w=342
    b.rect(x,85,36,36,'#e4eee4',18);b.text('RL',x+18,109,11,'teal',True,anchor='center');b.text('Research Lab',x+49,109,15,'ink',True)
    b.text('◇  Cybersecurity Incident Registry',x,155,12,'muted')
    b.text('IL TUO SPAZIO DI LAVORO',x,195,10,'teal',True)
    b.text('Accedi a CIR.',x,239,33,'ink',True)
    b.wrap('Entra nello spazio operativo della tua organizzazione.',x,270,w,14,'muted',22)
    b.text('Username',x,337,14,'ink',True);b.rect(x,350,w,50,'white',7,'#cbd6ce');b.text('demo',x+15,382,16,'ink')
    b.text('Password',x,437,14,'ink',True);b.rect(x,450,w,50,'white',7,'#cbd6ce');b.text('••••••••',x+15,482,16,'ink')
    b.button('Accedi  →',x,526,w,True,size=15,h=50)
    b.wrap('Account locale o LDAP, secondo configurazione.',x+14,606,w-28,12,'muted',19)
    b.line(x,652,x+130,652);b.text('oppure',195,657,12,'muted',anchor='center');b.line(x+212,652,x+w,652)
    b.button('Accedi con Research Identity',x,679,w,size=14,h=50)
    b.text('Esempio di profilo SSO configurato.',195,756,11,'muted',anchor='center')
    b.line(x,781,x+w,781);b.text('Credenziali fittizie: demo / cir-demo.',x,808,12,'muted');b.text('Non inserire credenziali reali.',x,831,12,'muted')
    b.text('Esamina il passaggio MFA  →',x,870,12,'teal',True)
    b.text('Cybersecurity Incident Registry',x,909,10,'muted');b.text('0.9.0-1',x+w,909,10,'muted',anchor='right')
    b.photo('operations-editorial.png',18,937,354,150,12,.5)
    b.text('Ogni incidente.',37,973,24,'white',True);b.text('Una risposta',37,1007,23,'white',True);b.text('organizzata.',37,1040,23,'#e0e6d4',italic=True)
    b.end()


def desktop_dashboard(c,data):
    b=Board(c,1440,1050,'03 / Home · desktop');b.chrome();b.offset_y=-60
    x=267;w=1138
    b.text('IL TUO SPAZIO OPERATIVO',x,256,10,'teal',True)
    b.text('Una visione chiara.',x,294,32,'ink',True)
    b.text('22 novembre 2026 · Research Lab',x,321,13,'muted')
    b.button('+ Nuovo incidente',1221,273,184,True)
    b.rect(x,348,w,214,'#e6eee5',12)
    b.photo('operations-editorial.png',875,348,530,214,12)
    b.text('COORDINARE LA RISPOSTA',x+27,378,9,'teal',True)
    b.text('Ogni incidente.',x+27,424,34,'ink',True)
    b.text('Il prossimo passo.',x+27,463,34,'teal',italic=True)
    b.wrap('Registro, evidenze e procedure nello stesso spazio. Riprendi le attività che richiedono attenzione.',x+27,495,510,13)
    b.text('Apri lo spazio incidenti  →',x+27,544,12,'teal',True)
    metrics=[('Incidenti aperti','3','2 in gestione, 1 in verifica'),('Priorità alta','1','Richiede attenzione'),('Attività di oggi','4','2 da completare'),('Workflow correnti','2','Nel tenant Research Lab')]
    for i,(t,n,sub) in enumerate(metrics):
        xx=x+i*290;b.rect(xx,581,268,114,'white',10,'line');b.text(t,xx+20,608,12,'muted');b.text(n,xx+20,651,33,'ink',True);b.text(sub,xx+20,675,11,'muted')
    b.rect(x,715,781,232,'white',12,'line');b.text('Incidenti da seguire',x+22,747,19,'ink',True);b.text('Il lavoro aperto, a colpo d’occhio.',x+22,770,11,'muted')
    for i,item in enumerate(data['incidents'][:3]):
        yy=792+i*48;b.line(x+20,yy,x+760,yy);b.text(item['ref'],x+22,yy+16,9,'muted');b.text(item['title'],x+22,yy+35,12,'ink',True)
        b.pill({'high':'Alta','medium':'Media'}[item['severity']],x+534,yy+12,item['severity']);b.text(item['status'],x+624,yy+29,11,'muted')
    b.rect(1068,715,337,232,'white',12,'line');b.text('In agenda',1090,747,19,'ink',True)
    b.text('OGGI · 11:00',1090,783,9,'#937343',True);b.text('Verifica della compromissione',1090,806,13,'ink',True);b.text('INC-2026-042 · Evidenze',1090,828,11,'muted')
    b.line(1090,843,1383,843);b.text('OGGI · 15:30',1090,865,9,'teal',True);b.text('Conferma del ripristino',1090,888,13,'ink',True);b.text('2 avvisi da leggere  →',1090,922,11,'teal',True)
    for i,(n,title,sub) in enumerate([('01','Workflow condivisi','Un punto di partenza, più varianti.'),('02','Documenti e notifiche','Modelli pronti, comunicazioni coerenti.'),('03','Il tenant, sotto controllo','Configurazioni, accessi e integrazioni.')]):
        xx=x+i*386;b.photo('operations-editorial.png' if i==0 else 'infrastructure-editorial.png' if i==1 else 'cover-master.png',xx,967,366,115,10,.62)
        b.text(n+' / IL TUO AMBIENTE',xx+20,993,9,'#d1e1d5',True);b.text(title,xx+20,1024,18,'white',True);b.text(sub,xx+20,1054,11,'#e0ebe4')
    b.end()


def desktop_incident(c,data):
    b=Board(c,1440,1020,'05 / Incidente · desktop');b.chrome('Incidenti');b.offset_y=-60
    x=267;b.text('Incidenti  ›  '+data['incidents'][0]['ref'],x,256,11,'muted')
    b.text(data['incidents'][0]['title'],x,303,29,'ink',True)
    b.pill('Alta',x,324,'high');b.text('In gestione   ·   Phishing   ·   Research Lab',x+72,341,12,'muted')
    b.button('Report PDF',1146,326,112);b.button('+ Azione',1270,326,135,True)
    tabs=[('Workflow',True),('Dati',False),('Azioni',False),('Documenti',False),('Notifiche',False),('Attività',False)]
    tx=x
    for t,active in tabs:
        b.text(t,tx,400,13,'teal' if active else 'muted',active)
        if active:b.rect(tx,414,83,3,'teal')
        tx+=116
    b.line(x,418,1039,418)
    b.rect(x,438,772,92,'#e6efe5',10);b.rect(x+20,459,49,49,'teal',24)
    b.text('3/6',x+44,490,15,'white',True,anchor='center');b.text('Phishing · Research Lab',x+87,476,18,'ink',True);b.text('Un percorso operativo. Evidenze per ogni fase.',x+87,503,12,'muted');b.pill('Corrente',930,473)
    b.rect(x,550,772,485,'white',12,'line')
    steps=[('Segnalazione e presa in carico','Incidente registrato e assegnato al referente.','08:15'),('Valutazione iniziale','Gravità e perimetro confermati.','08:40'),('Contenimento','Sessioni revocate. Account interessato protetto.','09:10')]
    for i,(h,p,time) in enumerate(steps):
        yy=571+i*79;b.rect(x+22,yy,29,29,'mint',14);b.text('✓',x+36,yy+21,14,'teal',True,anchor='center');b.text(h,x+67,yy+18,15,'ink',True);b.text(p,x+67,yy+44,12,'muted');b.text(time,1008,yy+17,11,'muted',anchor='right')
        b.line(x+36,yy+32,x+36,yy+78,'#c6dacf',1.5)
    yy=815;b.rect(x+1,yy,770,158,'#f1f6ee',0);b.rect(x+22,yy+24,29,29,'teal',14);b.text('4',x+36,yy+45,14,'white',True,anchor='center')
    b.text('IL PROSSIMO PASSO',x+67,yy+29,9,'teal',True);b.text('Analisi delle evidenze',x+67,yy+56,18,'ink',True);b.text('Verifica i log di accesso e documenta l’esito dell’analisi.',x+67,yy+83,13,'muted')
    b.button('Registra esito',x+67,yy+101,150,True);b.button('Allega evidenza',x+229,yy+101,159)
    b.text('5  Comunicazione e ripristino',x+28,1012,14,'muted')
    b.rect(1061,438,344,425,'white',12,'line');b.text('Contesto dell’incidente',1082,472,17,'ink',True)
    for i,(label,value) in enumerate([('REFERENTE','Andrea Moretti'),('TENANT','Research Lab'),('PRIMA SEGNALAZIONE','22 novembre 2026, 08:15'),('SERVIZIO INTERESSATO','Posta istituzionale'),('WORKFLOW APPLICATO','Phishing · Research Lab')]):
        yy=507+i*61;b.text(label,1083,yy,9,'muted',True);b.text(value,1083,yy+24,13,'ink')
    b.text('Promemoria specifici  →',1083,838,12,'teal',True)
    b.rect(1061,880,344,120,'#fbf1dd',10)
    b.wrap('Il tenant resta bloccato mentre lavori sull’incidente. Per cambiarlo, torna alla lista.',1082,907,302,13,'#7c653a')
    b.end()


def mobile_dashboard(c,data):
    b=Board(c,390,1360,'04 / Home · mobile');b.mobile_chrome();b.offset_y=-70
    b.text('IL TUO SPAZIO OPERATIVO',18,263,10,'teal',True);b.text('Una visione chiara.',18,299,28,'ink',True);b.text('Research Lab · 22 novembre 2026',18,324,12,'muted')
    b.rect(18,346,354,287,'#e6eee5',10)
    b.photo('operations-editorial.png',180,346,192,287,10)
    b.rect(18,346,197,287,'#e6eee5',10)
    b.text('OGNI INCIDENTE.',36,376,9,'teal',True);b.text('Il prossimo',36,415,27,'ink',True);b.text('passo.',36,449,27,'teal',italic=True)
    b.wrap('Registro, evidenze e procedure nello stesso spazio.',36,482,170,14)
    b.button('Apri incidenti →',36,571,159,True,size=12)
    for i,(title,n,sub) in enumerate([('Incidenti aperti','3','2 in gestione'),('Priorità alta','1','Da seguire'),('Attività di oggi','4','2 da completare'),('Workflow correnti','2','Copie del tenant')]):
        xx=18+(i%2)*183; yy=651+(i//2)*122;b.rect(xx,yy,171,108,'white',8,'line');b.text(title,xx+15,yy+25,12,'muted');b.text(n,xx+15,yy+66,31,'ink',True);b.text(sub,xx+15,yy+90,11,'muted')
    b.rect(18,906,354,186,'white',10,'line');b.text('Incidenti da seguire',35,940,19,'ink',True);b.text(data['incidents'][0]['ref'],35,970,10,'muted')
    b.wrap(data['incidents'][0]['title'],35,997,315,15,'ink',22,True);b.pill('Alta',35,1047,'high');b.text('In gestione',353,1064,12,'muted',anchor='right')
    b.photo('infrastructure-editorial.png',18,1110,354,126,10,.57);b.text('01 / PROCEDURE',37,1141,10,'#d9e6dd',True);b.text('Workflow condivisi',37,1175,22,'white',True);b.text('Un punto di partenza, più varianti.',37,1208,13,'white')
    b.photo('operations-editorial.png',18,1250,354,100,10,.6);b.text('02 / EVIDENZE',37,1279,10,'#d9e6dd',True);b.text('Documenti e notifiche',37,1314,21,'white',True)
    b.mobile_dock(1364);b.end()


def mobile_incident(c,data):
    b=Board(c,390,1125,'06 / Incidente · mobile');b.mobile_chrome();b.offset_y=-70
    b.text('Incidenti  ›  INC-2026-042',18,264,12,'muted')
    yy=b.wrap(data['incidents'][0]['title'],18,303,354,27,'ink',34,True)
    b.pill('Alta',18,yy-9,'high');b.text('In gestione · Research Lab',88,yy+8,12,'muted')
    b.button('Report PDF',18,yy+32,144);b.button('+ Azione',176,yy+32,144,True)
    ty=yy+111
    for x,title in [(18,'Workflow'),(129,'Dati'),(192,'Azioni'),(273,'Documenti')]:b.text(title,x,ty,13,'teal' if x==18 else 'muted',x==18)
    b.line(18,ty+16,372,ty+16);b.rect(18,ty+14,85,3,'teal')
    y=ty+36;b.rect(18,y,354,126,'#e6efe5',9);b.rect(34,y+21,43,43,'teal',21);b.text('3/6',55,y+49,13,'white',True,anchor='center');b.text('Phishing · Research Lab',91,y+39,15,'ink',True);b.wrap('Un percorso operativo. Evidenze per ogni fase.',91,y+65,250,12);b.pill('Corrente',91,y+98,size=10)
    y+=146;b.rect(18,y,354,420,'white',10,'line')
    for i,(title,time) in enumerate([('Segnalazione e presa in carico','08:15'),('Valutazione iniziale','08:40'),('Contenimento','09:10')]):
        yy=y+20+i*67;b.rect(33,yy,26,26,'mint',13);b.text('✓',46,yy+19,13,'teal',True,anchor='center');b.wrap(title,72,yy+17,279,14,'ink',18,True);b.text(time,72,yy+40,11,'muted')
    yy=y+227;b.rect(19,yy,352,192,'#f1f6ee',9);b.text('IL PROSSIMO PASSO',36,yy+27,10,'teal',True);b.text('Analisi delle evidenze',36,yy+58,19,'ink',True);b.wrap('Verifica i log di accesso e documenta l’esito dell’analisi.',36,yy+86,311,14)
    b.button('Registra esito',36,yy+129,147,True);b.button('Allega evidenza',194,yy+129,160)
    b.mobile_dock(1129);b.end()


def global_settings(c,data):
    b=Board(c,1100,790,'08 / Interfaccia globale · solo super admin')
    b.text('AMMINISTRAZIONE / SISTEMA E INTEGRAZIONI',42,104,11,'teal',True)
    b.text('Una sola scelta, per tutta l’istanza.',42,154,34,'ink',True)
    b.wrap('Il nuovo design può essere acceso e spento globalmente. Il controllo appartiene ai super admin e si applica a ogni tenant.',42,192,1000,16)
    b.rect(42,250,1016,185,'white',12,'line');b.text('Nuova interfaccia CIR',69,293,24,'ink',True);b.text('Ambito globale · tutti i tenant · solo super admin',69,329,16,'muted')
    b.text('Valore iniziale predefinito: OFF. Attivabile solo dai super admin.',69,369,14,'teal',True);b.text('In questa tavola: ON per valutare la proposta.',69,399,14,'muted')
    b.rect(896,293,122,58,'teal',29);b.rect(962,300,44,44,'white',22);b.text('ON',926,331,17,'white',True,anchor='center')
    b.rect(42,460,491,220,'#e9f1e7',10);b.text('ON / Nuova UI',66,500,22,'teal',True);b.wrap('Navigazione fotografica, priorità operative e viste responsive. La scelta rimane unica cambiando tenant.',66,538,439,15)
    b.rect(555,460,503,220,'#f5eee0',10);b.text('OFF / Interfaccia legacy',579,500,22,'#725a2a',True);b.wrap('Ritorno al layout precedente. Dati, workflow, permessi e integrazioni rimangono invariati.',579,538,451,15)
    b.wrap('Mock dimostrativo: il valore è solo in memoria e si azzera al ricaricamento. Il parametro server e il cambio layout alla richiesta successiva saranno implementati soltanto dopo approvazione.',42,722,1016,13)
    b.end()


def mobile_menu(c,data):
    b=Board(c,390,1000,'07 / Menu aperto · mobile')
    b.rect(0,55,390,945,'#dae2dd');b.rect(0,55,328,945,'navy')
    b.text('CIR',27,112,33,'white',True);b.text('INCIDENT REGISTRY',28,136,10,'#afc4c5');b.text('×',296,99,27,'white')
    yy=181
    for caption,items in [('SPAZIO OPERATIVO',['Panoramica','Incidenti','Report e statistiche']),('PROCEDURE E RISORSE',['Catalogo workflow','Documenti e notifiche','Amministrazione']),('IL TUO SPAZIO',['Avvisi','Aiuto e formazione'])]:
        b.text(caption,28,yy,10,'#a6c0c3',True);yy+=17
        for t in items:
            if t=='Panoramica':b.rect(17,yy,294,45,'mint',8)
            b.text(t,38,yy+29,15,'teal' if t=='Panoramica' else '#d8e5e6',t=='Panoramica');yy+=49
        yy+=19
    b.button('Tutte le funzioni  →',23,yy,282,size=14);yy+=66
    b.photo('operations-editorial.png',23,yy,282,132,10,.54);b.text('PROCEDURE COMUNI',40,yy+30,10,'#d5e3d8',True);b.text('Decisioni nel tuo tenant.',40,yy+68,18,'white',True);b.text('Workflow, documenti e notifiche.',40,yy+100,12,'white')
    b.text('0.9.0-1 · Ambiente dimostrativo',25,972,11,'#b5cbc8');b.end()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'preview-boards')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    target=args.output/'CIR_UI_Design_Boards.pdf'
    data=mock_data();c=canvas.Canvas(str(target));c.setTitle('CIR - Tavole di progetto UI, da approvare');c.setAuthor('Cybersecurity Incident Registry')
    for fn in (desktop_login,mobile_login,desktop_dashboard,mobile_dashboard,desktop_incident,mobile_incident,mobile_menu,global_settings):fn(c,data)
    c.save();names=['desktop-login-board','mobile-login-board','desktop-dashboard-board','mobile-dashboard-board','desktop-incident-board','mobile-incident-board','mobile-menu-board','global-interface-board']
    doc=fitz.open(target)
    for page,name in zip(doc,names):page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(args.output/(name+'.png'))
    report={'kind':'native_design_boards','not_browser_screenshots':True,'approval':'pending','app_runtime_changed':False,'data_source':'docs/design/mockup.js','tokens_source':'docs/design/styles.css','pdf':target.name,'pages':len(doc),'new_interface_displayed':True,'interactive_default_enabled':False}
    (args.output/'design-boards-metadata.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
