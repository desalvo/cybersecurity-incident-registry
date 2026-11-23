#!/usr/bin/env python3
"""Rebuild the bilingual product brochures from versioned assets."""
from pathlib import Path
import sys
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'docs/presentation/assets'
sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata
from documentation_cover import draw_documentation_cover
RELEASE_METADATA=read_release_metadata(ROOT)
VERSION=RELEASE_METADATA.version
BUILD=RELEASE_METADATA.build
CANDIDATE='RC7'
NAVY='#091D31'; TEAL='#008F85'; INK='#12283E'; MUTED='#4C6173'; PAPER='#F7F7F2'
FONT='Helvetica'; BOLD='Helvetica-Bold'
regular=Path('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf')
if regular.exists():
 pdfmetrics.registerFont(TTFont('CIRNoto',str(regular)))
 pdfmetrics.registerFont(TTFont('CIRNotoBold',str(regular.with_name('NotoSans-Bold.ttf'))))
 pdfmetrics.registerFontFamily('CIRNoto',normal='CIRNoto',bold='CIRNotoBold')
 FONT='CIRNoto';BOLD='CIRNotoBold'
W,H=A4
BROCHURE_STRIP=ROOT/'app/static/help/cybersecurity-brochure-strip.png'

def paragraph(c,text,x,top,width,size=11,color=INK,bold=False):
 p=Paragraph(text,ParagraphStyle('cir',fontName=BOLD if bold else FONT,fontSize=size,leading=size*1.42,textColor=colors.HexColor(color),spaceAfter=0))
 _,height=p.wrap(width,H)
 if top+height>H-43: raise ValueError(f'Brochure text overflows: {text[:70]}')
 p.drawOn(c,x,H-top-height)
 return top+height

def page(c,num,kicker,title,en=False):
 c.setFillColor(colors.HexColor(PAPER));c.rect(0,0,W,H,fill=1,stroke=0)
 paragraph(c,kicker,42,34,W-84,9,TEAL,True)
 paragraph(c,title,42,76,W-84,27,INK,True)
 # All subsequent pages reuse only a crop of CIR's original synthetic
 # cybersecurity image. No photography or remote media are imported.
 strip=ImageReader(str(BROCHURE_STRIP))
 c.drawImage(strip,42,H-195,width=W-84,height=32,mask='auto')
 c.setStrokeColor(colors.HexColor('#CDD8DA'));c.line(42,40,W-42,40)
 c.setFont(FONT,8);c.setFillColor(colors.HexColor(MUTED));c.drawString(42,24,f'Cybersecurity Incident Registry  |  {VERSION} / {CANDIDATE}  |  Build {BUILD}');c.drawRightString(W-42,24,str(num))

def build(en=False, output_dir=None):
 out=Path(output_dir or ROOT/'docs')/('brochure_cybersecurity_incident_registry_en.pdf' if en else 'brochure_cybersecurity_incident_registry.pdf')
 out.parent.mkdir(parents=True, exist_ok=True)
 c=canvas.Canvas(str(out),pagesize=A4,pageCompression=1)
 c.setTitle('Cybersecurity Incident Registry - Product brochure' if en else 'Cybersecurity Incident Registry - Brochure')
 c.setAuthor('Cybersecurity Incident Registry')
 draw_documentation_cover(c, root=ROOT, title='Product overview' if en else 'Presentazione',
                          subtitle='Every incident. A clear path.' if en else 'Ogni incidente. Un percorso chiaro.',
                          language='en' if en else 'it', metadata=RELEASE_METADATA,
                          category='BROCHURE',
                          note='Synthetic cybersecurity illustration; no people.' if en else 'Illustrazione cybersecurity sintetica; nessuna persona.')
 c.showPage()
 # Operations.
 page(c,2,'OPERATIONAL CLARITY' if en else 'CHIAREZZA OPERATIVA','From a report<br/>to a documented response.' if en else 'Dalla segnalazione<br/>alla risposta documentata.',en)
 blocks_en=[('01  RECORD AND CLASSIFY','Create the incident, identify the tenant, classify severity and type, and maintain a consistent timeline.'),('02  FOLLOW THE WORKFLOW','Configurable steps, required actions, conditions and procedural warnings make expected work visible.'),('03  COLLECT EVIDENCE','Attach files, generate forms, prepare notifications and keep reports linked to the incident.'),('04  VERIFY AND CLOSE','Review outstanding requirements, record the outcome and retain the operational history.')]
 blocks_it=[('01  REGISTRA E CLASSIFICA','Crea l’incidente, identifica il tenant, assegna gravità e tipologia e mantieni una cronologia coerente.'),('02  SEGUI IL WORKFLOW','Step configurabili, azioni richieste, condizioni e avvisi procedurali rendono visibile il lavoro previsto.'),('03  RACCOGLI LE EVIDENZE','Allega file, genera moduli, prepara notifiche e conserva i report insieme all’incidente.'),('04  VERIFICA E CHIUDI','Controlla i requisiti ancora aperti, registra l’esito e conserva la storia operativa.')]
 for j,(head,body) in enumerate(blocks_en if en else blocks_it):
  y=213+j*104;paragraph(c,head,42,y,W-84,12,TEAL,True);paragraph(c,body,42,y+29,W-84,11)
 paragraph(c,'Integrated capabilities' if en else 'Funzioni integrate',42,638,W-84,15,INK,True)
 paragraph(c,'Interoperability and full configuration: SSO, audit, automatic notifications, custom workflow import and fillable PDFs. Optional AlBot knowledge base. Responsive desktop and mobile interface, accessibility features and Italian/English localization, with reference to AGID guidelines. CIR and Alfresco document storage. No certification is implied.' if en else 'Interfacciabilità e Configurabilità completa: SSO, audit, Notifiche automatiche, Import di workflow custom e PDF compilabili. Knowledge base opzionale per AlBot. Interfaccia responsive desktop e mobile, funzioni di accessibilità e localizzazione in italiano e inglese, con riferimento alle linee guida AGID. Storage CIR e Alfresco; nessuna certificazione implicita.',42,674,W-84,10.6)
 c.showPage()
 # Defaults.
 page(c,3,'REUSABLE WORKFLOWS' if en else 'WORKFLOW RIUSABILI','One shared catalogue.<br/>Many local variations.' if en else 'Un catalogo comune.<br/>Più varianti locali.',en)
 texts_en=[('TENANTS DEFAULT','A special configuration tenant, separate from operational default. When absent, it is initialized from default configuration; existing configuration is preserved.'),('SAFE REFERENCE MAPPING','Shared labels and parameters have durable provenance. Collisions allocate new local IDs; workflow imports resolve the correct destination records.'),('REPEATABLE IMPORTS','Import the same workflow repeatedly under different names. Edit local structures and explicitly customize parameter dependencies for independent variants.'),('CURRENT OR OBSOLETE','Source obsolescence blocks new imports and makes all installed copies obsolete, including customized ones. Administrators receive in-application notices; existing incidents retain their history.'),('PROTECTED DATA AND PORTABILITY','Records used by incidents cannot be deleted. Export all Tenants Default to another instance. Full and anonymized bootstrap exports also include the special tenant.')]
 texts_it=[('TENANTS DEFAULT','Un tenant speciale di configurazione, distinto dal default operativo. Se assente nasce dalla configurazione di default; una sorgente già presente viene conservata.'),('RIFERIMENTI COERENTI','Label e parametri condivisi mantengono la provenienza. Le collisioni assegnano nuovi ID locali e gli import dei workflow usano i record corretti della destinazione.'),('IMPORT RIPETIBILI','Importa lo stesso workflow più volte con nomi diversi. Modifica le strutture locali e personalizza esplicitamente le dipendenze per ottenere varianti indipendenti.'),('CORRENTE O OBSOLETO','L’obsolescenza della sorgente blocca nuovi import e rende obsolete tutte le copie, anche personalizzate. Gli admin ricevono avvisi nell’app; gli incidenti esistenti conservano il loro storico.'),('DATI PROTETTI E PORTABILITÀ','I record usati da incidenti non sono cancellabili. Esporta tutto Tenants Default verso un’altra istanza. Anche Full Export e bootstrap anonimizzato includono il tenant speciale.')]
 for j,(head,body) in enumerate(texts_en if en else texts_it):
  y=209+j*108;paragraph(c,head,42,y,W-84,11,TEAL,True);paragraph(c,body,42,y+26,W-84,10.8)
 c.showPage()
 # Deployment and training.
 page(c,4,'DEPLOY AND PRACTISE' if en else 'INSTALLARE E SPERIMENTARE','From configuration<br/>to the operational team.' if en else 'Dalla configurazione<br/>al gruppo operativo.',en)
 paragraph(c,'Docker Hub, Docker Compose, Kubernetes, OpenShift' if en else 'Docker Hub, Docker Compose, Kubernetes, OpenShift',42,211,W-84,16,INK,True)
 paragraph(c,'Helm chart, validated values schema and an OpenShift console Template. Existing Secrets, PostgreSQL and persistent storage; non-root containers, read-only filesystem and restricted privileges. A Helm repository must be published/configured before using the chart from the graphical catalogue.' if en else 'Chart Helm, schema dei valori e Template dalla console OpenShift. Secret esistenti, PostgreSQL e storage persistente; container non-root, filesystem in sola lettura e privilegi limitati. Per il catalogo grafico Helm occorre pubblicare e configurare il repository del chart.',42,251,W-84,11)
 paragraph(c,'A practical learning session' if en else 'Una sessione didattica concreta',42,380,W-84,16,INK,True)
 paragraph(c,'The included PowerPoint and training guide follow a fictitious phishing case: open, classify, contain, notify, document and close. A second exercise compares two local workflow variants and demonstrates source obsolescence.' if en else 'PowerPoint e guida inclusi seguono un caso fittizio di phishing: apertura, classificazione, contenimento, notifica, documentazione e chiusura. Un secondo esercizio confronta due varianti locali e mostra l’obsolescenza dalla sorgente.',42,420,W-84,11)
 paragraph(c,'Release with evidence' if en else 'Rilascio con evidenze',42,535,W-84,16,INK,True)
 paragraph(c,'Production promotion requires tests, real PostgreSQL, SCA and Trivy scans on amd64/arm64. RC7 is a source candidate, not a newly approved production image. Consult HANDOFF and verification results; the previous risk acceptance expired on 20 October 2026.' if en else 'La promozione production richiede test, PostgreSQL reale, SCA e scan Trivy amd64/arm64. RC7 è un candidato sorgente, non una nuova immagine production approvata. Consultare Handoff e verifiche; la precedente risk acceptance è scaduta il 20 ottobre 2026.',42,575,W-84,10.8)
 paragraph(c,'Open source and documentation' if en else 'Open source e documentazione',42,688,W-84,12,TEAL,True)
 paragraph(c,'European Union Public Licence (EUPL-1.2)<br/>Alessandro De Salvo - Alessandro.DeSalvo@roma1.infn.it<br/>https://github.com/desalvo/cybersecurity-incident-registry<br/>README - MIGRATION - DEPLOYMENT - TRAINING - HANDOFF',42,717,W-84,8.8)
 c.save()
 return out

if __name__=='__main__':
 for language in (False,True): print(build(language))
