#!/usr/bin/env python3
"""Render the isolated login-v2 proposal; never changes application pages.

Dependencies: ReportLab, PyMuPDF, Pillow. Uses local DejaVu fonts.
Outputs native design boards (not browser screenshots) and a standalone HTML.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
import re

import fitz
from PIL import Image
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PHOTO = HERE.parents[1] / 'visual-assets' / 'cybersecurity-login-v2.png'
LOGO = ROOT / 'app' / 'static' / 'cir-application-logo.svg'
ROOT_CSS = re.search(r':root\{([^}]+)\}', (HERE / 'styles.css').read_text()).group(1)
TOKENS = dict(re.findall(r'--([a-z]+):([^;}]+)', ROOT_CSS))
FONTS = Path('/usr/share/fonts/truetype/dejavu')
for name, file in [('UI','DejaVuSans.ttf'),('UIB','DejaVuSans-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONTS/file)))


def color(value):
    value = TOKENS.get(value,value)
    if re.fullmatch(r'#[a-fA-F0-9]{3}',value): value = '#'+''.join(ch*2 for ch in value[1:])
    return HexColor(value)


class Board:
    def __init__(self,c,width,height,label):
        self.c,self.w,self.h=c,width,height;c.setPageSize((width,height))
        self.rect(0,0,width,height,'paper')
        self.rect(0,0,width,37,'#eaf0f4')
        self.text('Mockup login · da approvare',24,24,11,'muted')
        self.text(label,width-24,24,10,'muted',anchor='right')

    def rect(self,x,y,w,h,fill,radius=0,stroke=None):
        self.c.setFillColor(color(fill));self.c.setStrokeColor(color(stroke or fill));self.c.setLineWidth(.8)
        self.c.roundRect(x,self.h-y-h,w,h,radius,fill=1,stroke=bool(stroke))

    def line(self,x,y,x2,y2,stroke='line',width=.8):
        self.c.setStrokeColor(color(stroke));self.c.setLineWidth(width);self.c.line(x,self.h-y,x2,self.h-y2)

    def text(self,s,x,y,size=14,fill='ink',bold=False,anchor='left'):
        self.c.setFillColor(color(fill));self.c.setFont('UIB' if bold else 'UI',size)
        fn={'left':self.c.drawString,'right':self.c.drawRightString,'center':self.c.drawCentredString}[anchor]
        fn(x,self.h-y,s)

    def wrap(self,s,x,y,width,size=14,fill='muted',leading=None,bold=False):
        line='';lines=[];font='UIB' if bold else 'UI';leading=leading or size*1.6
        for word in s.split():
            if line and pdfmetrics.stringWidth(line+' '+word,font,size)>width:lines.append(line);line=word
            else:line=(line+' '+word).strip()
        if line:lines.append(line)
        for i,line in enumerate(lines):self.text(line,x,y+i*leading,size,fill,bold)
        return y+len(lines)*leading

    def photo(self,x,y,w,h,radius=0,darkness=0,position=.5):
        iw,ih=Image.open(PHOTO).size;scale=max(w/iw,h/ih);dw,dh=iw*scale,ih*scale
        self.c.saveState();p=self.c.beginPath();p.roundRect(x,self.h-y-h,w,h,radius);self.c.clipPath(p,stroke=0,fill=0)
        self.c.drawImage(str(PHOTO),x+(w-dw)/2,self.h-y-h+(h-dh)*position,dw,dh)
        if darkness:
            self.c.setFillColor(Color(.02,.08,.13,alpha=darkness));self.c.rect(x,self.h-y-h,w,h,fill=1,stroke=0)
        self.c.restoreState()

    def logo(self,x,y,size=48):
        logo=fitz.open(stream=LOGO.read_bytes(),filetype='svg')
        image=logo[0].get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=True)
        self.c.drawImage(ImageReader(io.BytesIO(image.tobytes('png'))),x,self.h-y-size,size,size,mask='auto')

    def field(self,label,value,x,y,w,secret=False):
        self.text(label,x,y,14,'ink',True)
        self.rect(x,y+14,w,51,'white',7,'#c9d5e0')
        self.text('••••••••' if secret else value,x+15,y+47,16,'ink')

    def button(self,label,x,y,w,primary=False,h=51):
        self.rect(x,y,w,h,'blue' if primary else 'white',7,None if primary else '#c9d5e0')
        self.text(label,x+w/2,y+h/2+5,14,'white' if primary else 'ink',True,'center')

    def end(self):self.c.showPage()


def desktop(c):
    b=Board(c,1440,1000,'Desktop · tavola di progetto')
    b.photo(26,63,724,911,18,.14)
    # The photograph has intentional dark space at the top; text remains live vector content.
    b.line(71,119,96,119,'cyan',2);b.text('CIR / INCIDENT REGISTRY',110,123,10,'#b6d1df')
    b.text('Cybersecurity',71,228,47,'white',True)
    b.text('Incident Registry',71,285,47,'white',True)
    b.text('Gestione degli incidenti di sicurezza',71,355,27,'white')
    b.text('e tracciabilità delle attività.',71,397,27,'cyan')
    b.text('Coordina la risposta agli incidenti.',71,452,16,'#dae8ef')
    b.text('Collega ogni attività alle sue evidenze.',71,480,16,'#dae8ef')
    b.rect(72,929,6,6,'cyan',3);b.text('Incidenti · workflow · evidenze · notifiche',90,937,11,'#deedf3')
    x=890;w=398
    b.logo(x,122);b.text('CIR',x+63,147,26,'ink',True);b.text('Cybersecurity Incident Registry',x+63,168,10,'muted')
    b.text('ACCESSO ALL’APPLICAZIONE',x,252,10,'blue',True)
    b.text('Accedi a CIR.',x,300,37,'ink',True)
    b.text('Il tuo spazio per la gestione',x,339,15,'muted')
    b.text('degli incidenti di sicurezza.',x,364,15,'muted')
    b.field('Username','demo',x,417,w)
    b.field('Password','cir-demo',x,517,w,True)
    b.button('Accedi  →',x,610,w,True)
    b.text('Account locale o LDAP, secondo configurazione.',x+w/2,692,11,'muted',anchor='center')
    b.line(x,727,x+158,727);b.text('oppure',x+w/2,731,11,'muted',anchor='center');b.line(x+240,727,x+w,727)
    b.button('Accedi con SSO',x,757,w)
    b.text('Profilo configurato · esempio dimostrativo',x+w/2,834,10,'muted',anchor='center')
    b.line(x,859,x+w,859);b.text('Demo: demo / cir-demo',x,887,11,'muted');b.text('Usa solo credenziali dimostrative.',x,910,11,'muted')
    b.text('Cybersecurity Incident Registry',x,958,10,'muted');b.text('0.9.0-1',x+w,958,10,'muted',anchor='right')
    b.end()


def mobile(c):
    b=Board(c,390,1206,'Mobile')
    x=24;w=342
    b.logo(x,66,44);b.text('CIR',x+57,88,24,'ink',True);b.text('Cybersecurity Incident Registry',x+57,109,10,'muted')
    b.text('ACCESSO ALL’APPLICAZIONE',x,162,10,'blue',True)
    b.text('Accedi a CIR.',x,205,33,'ink',True)
    b.wrap('Il tuo spazio per la gestione degli incidenti di sicurezza.',x,239,w,14,'muted',22)
    b.field('Username','demo',x,312,w);b.field('Password','cir-demo',x,412,w,True)
    b.button('Accedi  →',x,506,w,True)
    b.wrap('Account locale o LDAP, secondo configurazione.',x+14,588,w-28,12,'muted',19)
    b.line(x,634,x+130,634);b.text('oppure',195,638,12,'muted',anchor='center');b.line(x+212,634,x+w,634)
    b.button('Accedi con SSO',x,659,w)
    b.text('Profilo configurato · esempio dimostrativo',195,738,11,'muted',anchor='center')
    b.line(x,766,x+w,766);b.text('Demo: demo / cir-demo',x,795,12,'muted');b.text('Usa solo credenziali dimostrative.',x,818,12,'muted')
    b.text('Cybersecurity Incident Registry',x,861,10,'muted');b.text('0.9.0-1',x+w,861,10,'muted',anchor='right')
    b.rect(18,888,354,76,'white',12)
    b.logo(31,903,44)
    b.text('Cybersecurity',88,918,19,'ink',True)
    b.text('Incident Registry',88,943,19,'ink',True)
    b.photo(18,964,354,220,12,.12,.58)
    b.end()


def standalone(output):
    html=(HERE/'index.html').read_text()
    css=(HERE/'styles.css').read_text();js=(HERE/'login.js').read_text()
    html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+css+'</style>')
    html=html.replace('<script src="login.js" defer></script>','')
    html=html.replace('</body>','<script>'+js+'</script></body>')
    html=html.replace('../../visual-assets/cybersecurity-login-v2.png','data:image/png;base64,'+base64.b64encode(PHOTO.read_bytes()).decode())
    html=html.replace('../../../app/static/cir-application-logo.svg','data:image/svg+xml;base64,'+base64.b64encode(LOGO.read_bytes()).decode())
    (output/'CIR_Login_v2.html').write_text(html)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    target=args.output/'CIR_Login_v2.pdf'
    c=canvas.Canvas(str(target));c.setTitle('CIR - Proposta login v2');c.setAuthor('Cybersecurity Incident Registry')
    desktop(c);mobile(c);c.save()
    doc=fitz.open(target)
    for page,name in zip(doc,('CIR_Login_v2_Desktop.png','CIR_Login_v2_Mobile.png')):
        page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(args.output/name)
    standalone(args.output)
    report={'scope':'login_only','approval':'layout accepted; revised copy and mobile photo header proposed','professional_copy':'Gestione degli incidenti di sicurezza e tracciabilità delle attività.','mobile_photo_header':'Existing CIR logo and full Cybersecurity Incident Registry name only; no slogan on photograph.','native_design_boards_not_browser_screenshots':True,'pages':2,'application_runtime_changed':False,'other_mock_pages_changed':False,'image':'cybersecurity-login-v2.png','no_people':True,'no_paper_records':True,'preserve_on_integration':['Configurable organization logo in addition to CIR branding.','Conditional list of enabled SSO profiles with optional provider logos.','Existing CSRF, rate limiting, account state and subsequent MFA checks.'],'future_constraints':['Preserve the existing list structure on the page the user called previsioni.','Preserve incident workflow blocks, arrows, buttons and text inside blocks.','The earlier incident timeline proposal was not approved.'],'dependencies':['ReportLab','PyMuPDF','Pillow','local DejaVu fonts']}
    (args.output/'login-v2-metadata.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
