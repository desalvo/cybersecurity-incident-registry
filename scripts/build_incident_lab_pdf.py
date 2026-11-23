#!/usr/bin/env python3
"""Build a truthful CIR incident laboratory handout.

Only a validated same-commit browser fixture may provide a current-UI screenshot.
The source edition is visibly marked as awaiting CI capture; it never ships mock
UI under the label of a screenshot. No production incident data is accessed.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from release_metadata import read_release_metadata
from documentation_cover import draw_documentation_cover

STEPS=[
 ("01", "Apertura e classificazione", "Creare un incidente di prova; compilare riferimento, nome, tipo e gravità. Verificare il tenant attivo e scegliere un workflow corrente.", "Incidente visibile nel registro e workflow associato."),
 ("02", "Presa in carico", "Aprire la prima fase operativa. Utilizzare il riquadro inferiore del task per registrare chi ha preso in carico il caso, quando e con quali azioni.", "Azione di presa in carico tracciata."),
 ("03", "Contenimento ed evidenze", "Eseguire il contenimento con gli strumenti aziendali. In CIR registrare tempi, attività, sistemi coinvolti e allegare evidenze non sensibili del laboratorio.", "Azioni e documenti associati al caso."),
 ("04", "Analisi e documentazione", "Proseguire sulle fasi indicate dalle frecce. Compilare i dati richiesti, verificare le condizioni di completamento e generare eventuali moduli dal template.", "Dati, documenti e task aggiornati."),
 ("05", "Notifica e verifica", "Preparare una notifica con destinatari dimostrativi. Verificare contenuto, documento e autorizzazioni prima dell'eventuale invio simulato.", "Tracciamento delle notifiche e dei relativi documenti."),
 ("06", "Chiusura e riesame", "Verificare checklist e attività residue. Registrare esito e raccomandazioni; eseguire la chiusura secondo il workflow effettivamente configurato.", "Incidente chiuso, storico consultabile e report disponibile se configurato."),
]

NAVY=colors.HexColor('#071a30'); TEAL=colors.HexColor('#007a8c'); GREY=colors.HexColor('#486072')

def fit_text(c, text, x, y, width, size=10, leading=15, maxlines=5):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words=text.split(); line=''; lines=[]
    for word in words:
        candidate=(line+' '+word).strip()
        if line and stringWidth(candidate,'Helvetica',size)>width:
            lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    if len(lines)>maxlines: raise ValueError('Incident lab line overflow: '+text[:50])
    for line in lines:c.drawString(x,y,line);y-=leading
    return y

def build(output:Path, screenshot:Path|None=None, source_commit:str|None=None):
    metadata=read_release_metadata(ROOT)
    if screenshot:
        if not source_commit or not screenshot.is_file(): raise ValueError('Real capture needs verified commit and image')
        im=ImageReader(str(screenshot)); iw,ih=im.getSize()
        if iw<900 or ih<450:raise ValueError('Real screenshot dimensions invalid')
    output.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
    c.setTitle('CIR - Laboratorio incidente: apertura e chiusura')
    draw_documentation_cover(c,root=ROOT,title='Laboratorio incidente',subtitle='Apertura, workflow e chiusura',metadata=metadata,
                             note='Dati sintetici; nessuna fotografia di persone o incidente reale.')
    c.showPage()
    W,H=landscape(A4)
    for index,(number,title,action,result) in enumerate(STEPS):
        c.setPageSize((W,H));c.setFillColor(colors.HexColor('#f7fafc'));c.rect(0,0,W,H,fill=1,stroke=0)
        c.setFillColor(NAVY);c.rect(0,H-83,W,83,fill=1,stroke=0)
        c.setFillColor(colors.white);c.setFont('Helvetica-Bold',19);c.drawString(34,H-42,'LABORATORIO OPERATIVO  /  '+number)
        c.setFont('Helvetica',10);c.drawString(35,H-64,'Cybersecurity Incident Registry   '+metadata.version+' · Build '+metadata.build)
        c.setFillColor(NAVY);c.setFont('Helvetica-Bold',19);c.drawString(36,H-119,title)
        c.setFont('Helvetica',10.5);c.setFillColor(GREY)
        bottom=fit_text(c,action,36,H-148,W-72,10.5,15,3)
        picture_top=bottom-16
        image_x,image_w=35,W-70
        image_h=min(277,picture_top-103)
        if screenshot:
            scale=min(image_w/iw,image_h/ih)
            dw,dh=iw*scale,ih*scale
            c.drawImage(str(screenshot),image_x+(image_w-dw)/2,picture_top-dh,width=dw,height=dh,mask='auto')
            c.setFont('Helvetica',8);c.setFillColor(GREY)
            c.drawString(36, picture_top-image_h-10,'UI reale di CIR · fixture sintetica CI · commit '+source_commit[:12]+' · medesima vista, diverse attività didattiche')
        else:
            c.setFillColor(colors.HexColor('#e6eff6'));c.roundRect(image_x,picture_top-image_h,image_w,image_h,9,stroke=0,fill=1)
            c.setFillColor(TEAL);c.setFont('Helvetica-Bold',14)
            c.drawCentredString(W/2,picture_top-image_h/2+10,'SCHERMATA REALE: ACQUISIZIONE CI IN ATTESA')
            c.setFillColor(GREY);c.setFont('Helvetica',10)
            c.drawCentredString(W/2,picture_top-image_h/2-14,'I riquadri del workflow e le frecce saranno acquisiti dalla UI effettiva.')
        c.setFillColor(TEAL);c.roundRect(35,51,W-70,40,6,fill=1,stroke=0)
        c.setFillColor(colors.white);c.setFont('Helvetica-Bold',10)
        fit_text(c,'Risultato atteso: '+result,48,75,W-98,10,13,2)
        c.setFillColor(GREY);c.setFont('Helvetica',7.5)
        c.drawString(35,26,'Le fasi mostrate dipendono dal workflow configurato: questo è un esempio didattico, non una sequenza universale obbligatoria.')
        c.showPage()
    c.save();return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'docs/CIR_Incident_Laboratory_IT.pdf')
    p.add_argument('--screenshot',type=Path);p.add_argument('--source-commit')
    a=p.parse_args();print(build(a.output,a.screenshot,a.source_commit))
