from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from hashlib import sha256
import json, math
ROOT=Path(__file__).resolve().parents[1]
AS=ROOT/'docs/presentation/visual_rc61_art'; AS.mkdir(exist_ok=True)
src=AS/'generated_photo_source.png'
FR='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FB='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def f(size,bold=False):return ImageFont.truetype(FB if bold else FR,size)
photo=Image.open(src).convert('RGB')
PW,PH=photo.size
photos=[]
for i in range(6):
 x=(i%2)*PW/2; y=(i//2)*PH/3
 photos.append(photo.crop((round(x)+3,round(y)+3,round(x+PW/2)-3,round(y+PH/3)-3)))

slides = {
3:('TRACCIABILITÀ','Da evento a evidenza',['Segnalazione','Trattamento','Audit'],0,'flow'),
4:('UN REGISTRO UNICO','Informazioni coordinate',['E-mail isolate','Pratica CIR','Decisioni tracciate'],1,'flow'),
5:('FUNZIONI INTEGRATE','Dal registro ai servizi',['Workflow','Notifiche e PDF','Report e statistiche'],2,'hub'),
6:('ARCHITETTURA','Servizi a più livelli',['Browser / mobile','Applicazione CIR','Database + archivio'],3,'stack'),
7:('DISTRIBUZIONE','Ambienti orchestrati',['Container','Kubernetes / OpenShift','Backup e verifiche'],4,'flow'),
34:('MAPPING PDF','Impostazione admin via drag & drop',['Campo RIFERIMENTO','Trascina e associa','Dato incidente'],2,'flow'),
28:('RUOLI DISTINTI','Responsabilità e permessi',['Super admin','Admin tenant','Operatori / lettori'],5,'columns'),
29:('ISOLAMENTO TENANT','Perimetri autorizzati',['Tenant A','CIR condiviso','Tenant B'],3,'columns'),
30:('CATALOGO CONDIVISO','Tenants Default',['Definizioni centrali','Distribuzione','Tenant autorizzati'],2,'flow'),
31:('EREDITÀ E OVERRIDE','Una sola scelta logica',['Definizione condivisa','ID locale riutilizzato','Override conservati'],1,'stack'),
32:('PARAMETRI GLOBALI','Unica istanza CIR',['URL e timezone','TLS e certificati','Limiti upload'],3,'grid'),
33:('CONFIGURAZIONE LOCALE','Personalizzazioni per tenant',['Workflow e cataloghi','Template / PDF','Plugin / AI'],5,'grid'),
35:('MATRICE DEI PRIVILEGI','Modifica o consultazione',['Super admin','Admin tenant','Operatore / lettore'],5,'columns'),
39:('ESEMPIO DIDATTICO','Workflow configurabile: SPAM',['Categoria SPAM','Blocco account','Condizione personal_data'],0,'flow'),
40:('IMPORT AMMINISTRATIVO','Workflow pubblicato nel tenant',['Catalogo','Import admin','Uso operatori'],4,'flow'),
41:('ISTRUZIONI LOCALI','Ogni step può avere risorse',['Step del flusso','Link procedura locale','Azione guidata'],2,'stack'),
42:('CICLO DI VITA','Definizioni correnti e obsolete',['Corrente','Storico conservato','Obsoleto'],3,'columns'),
43:('GOVERNANCE WORKFLOW','Sorgente e copia tenant',['Tenants Default','Variante locale','Stato gestito'],5,'flow'),
44:('CASO SPAM DIDATTICO','Panoramica, dettagli più avanti',['Contenimento','Notifiche e DPO','Chiusura'],0,'flow'),
70:('NESSUNA SCELTA DOPPIA','Categorie e dati interessati',['SPAM · una scelta','Dati · una scelta','Origine visibile'],2,'columns'),
73:('LABORATORIO SPAM','Cosa impariamo dal caso',['Step configurabili','Evidenze e condizioni','Decisioni umane'],0,'hub'),
75:('CIR IN SINTESI','Piattaforma generalizzabile',['Incidenti e procedure','Multi-tenant e ruoli','EUPL Open Source'],2,'hub'),
76:('PERCORSO DIDATTICO','Dal login alla chiusura',['Accesso e registro','Workflow e documenti','Audit e integrazioni'],0,'flow'),
77:('SERVIZIO CENTRALE','Accesso istituzionale',['Credenziali SSO','Istanza CIR','Sedi e tenant'],3,'stack'),
78:('DOCUMENTAZIONE','Manuali e repository',['Guida utente','Guida amministratore','Repository EUPL'],2,'columns'),
79:('CONTRIBUTI','Feedback e miglioramenti',['Segnalazioni','Suggerimenti','Open Source EUPL'],1,'hub'),
}

def cover_fit(im,w,h):
 ratio=max(w/im.width,h/im.height); img=im.resize((round(im.width*ratio),round(im.height*ratio)),Image.Resampling.LANCZOS)
 l=(img.width-w)//2;t=(img.height-h)//2
 return img.crop((l,t,l+w,t+h))
def rr(d,b,fill,r=22,outline=None,width=2): d.rounded_rectangle(b,radius=r,fill=fill,outline=outline,width=width)
def multiline_center(d,box,text,ft,color,spacing=8):
 x0,y0,x1,y1=box
 lines=text.split('\n'); lh=ft.size+spacing
 for j,line in enumerate(lines):
  bb=d.textbbox((0,0),line,font=ft);tw=bb[2]-bb[0];cx=(x0+x1-tw)//2;cy=int((y0+y1-lh*len(lines))/2+j*lh)
  d.text((cx,cy),line,font=ft,fill=color)
def arrow(d,x0,y0,x1,y1,col=(57,226,240,255)):
 d.line((x0,y0,x1,y1),fill=col,width=9,joint='curve');a=math.atan2(y1-y0,x1-x0)
 sz=22;d.polygon([(x1,y1),(x1-sz*math.cos(a-.6),y1-sz*math.sin(a-.6)),(x1-sz*math.cos(a+.6),y1-sz*math.sin(a+.6))],fill=col)
def node(d,xy,txt,c=(22,93,122,220),font=31):
 x,y,w,h=xy;rr(d,(x,y,x+w,y+h),c,24,outline=(113,220,232,170),width=3)
 ff=font
 while ff>17 and d.textbbox((0,0),txt,font=f(ff,True))[2]>w-24:
  ff-=1
 multiline_center(d,(x+9,y+7,x+w-9,y+h-5),txt,f(ff,True),(241,252,255,255))

def render(idx,rec):
 head,subtitle,labels,base_idx,style=rec
 W,H=1400,950
 bg=cover_fit(photos[base_idx],W,H).filter(ImageFilter.GaussianBlur(3)).convert('RGBA')
 gradient=Image.new('RGBA',(W,H));pix=gradient.load()
 for y in range(H):
  for x in range(W):
   alpha=int(104+58*(y/H)+45*(1-x/W))
   pix[x,y]=(3,24,45,max(0,min(215,alpha)))
 bg=Image.alpha_composite(bg,gradient)
 glow=Image.new('RGBA',(W,H));gd=ImageDraw.Draw(glow)
 gd.ellipse((W-490,0,W+160,550),fill=(0,187,220,50))
 glow=glow.filter(ImageFilter.GaussianBlur(120));bg=Image.alpha_composite(bg,glow)
 d=ImageDraw.Draw(bg,'RGBA')
 d.rectangle((0,0,W,18),fill=(34,209,223,255))
 d.text((76,66),head,font=f(44,True),fill=(180,243,250,255))
 d.text((76,135),subtitle,font=f(33),fill=(245,250,255,245))
 d.line((70,205,1330,205),fill=(163,232,240,125),width=2)
 if style=='flow':
  xx=[72,508,944]; yy=[488,488,488]
  for j,lab in enumerate(labels):node(d,(xx[j],yy[j],381,168),lab,font=28)
  for j in [0,1]:arrow(d,xx[j]+395,570,xx[j+1]-18,570)
 elif style=='stack':
  yy=[285,475,665]
  for j,lab in enumerate(labels):node(d,(265,yy[j],870,138),lab,font=31)
  for j in [0,1]:arrow(d,695,yy[j]+145,695,yy[j+1]-13)
 elif style=='columns':
  for j,lab in enumerate(labels):
   x=70+j*438
   rr(d,(x,314,x+390,746),(13,65,90,215),28,outline=(65,204,221,170),width=3)
   d.ellipse((x+145,370,x+245,470),fill=[(36,195,207,245),(57,151,234,245),(42,215,163,245)][j])
   multiline_center(d,(x+14,485,x+378,710),lab,f(30,True),(255,255,255,255))
 elif style=='grid':
  loc=[(84,328),(732,328),(408,635)]
  for j,(x,y) in enumerate(loc):node(d,(x,y,560,160),labels[j],font=29)
  arrow(d,645,520,712,520)
 elif style=='hub':
  d.ellipse((520,290,870,640),fill=(13,92,128,215),outline=(116,239,246,222),width=7)
  multiline_center(d,(552,355,836,565),'CIR',f(74,True),(241,253,255,255))
  loc=[(60,275),(980,275),(508,682)]
  for j,(x,y) in enumerate(loc):node(d,(x,y,360,135),labels[j],font=26)
  arrow(d,420,365,520,410);arrow(d,880,412,977,360);arrow(d,694,640,694,679)
 d.text((78,H-68),'ILLUSTRAZIONE CONCETTUALE  ·  DATI DI ESEMPIO',font=f(19),fill=(178,214,227,255))
 out=AS/f'visual_{idx:02d}.jpg'; bg.convert('RGB').save(out,quality=88,optimize=True)
 return out
for idx,rec in slides.items(): render(idx,rec)

# A two-page example of a report, explicitly synthetic. Based on the
# incident-report headings in app/reports.py; not a screenshot or an app export.
DOC_W,DOC_H=780,1110

def report_page(number):
 im=Image.new('RGB',(DOC_W,DOC_H),'#ffffff');d=ImageDraw.Draw(im)
 d.rectangle((0,0,DOC_W,20),fill='#123b59')
 d.rounded_rectangle((50,49,148,125),radius=14,fill='#0b7891');d.text((72,67),'CIR',font=f(31,True),fill='white')
 d.text((164,63),'Cybersecurity Incident Registry',font=f(18,True),fill='#14435b')
 d.text((50,165),'Report dell’incidente' if number==1 else 'Azioni, evidenze e chiusura',font=f(28,True),fill='#12324a')
 d.text((50,211),'ESEMPIO DIDATTICO  •  DATI SINTETICI',font=f(15,True),fill='#a46219')
 d.line((50,254,729,254),fill='#ccdee8',width=3)
 if number==1:
  meta=[('Nome','Segnalazione SPAM - utenza dimostrativa'),('Riferimento','DEMO-SPAM-2026-0001'),('Categoria','SPAM (workflow di esempio)'),('Stato','Chiuso'),('Data inizio','01/12/2026 09:15'),('Data chiusura','01/12/2026 15:40')]
  for i,(label,value) in enumerate(meta):
   yy=281+i*82
   if i%2==0: d.rounded_rectangle((49,yy-7,731,yy+60),radius=8,fill='#f3f8fa')
   d.text((66,yy+7),label,font=f(18,True),fill='#426377')
   d.text((255,yy+7),value,font=f(18),fill='#12324a')
  d.text((52,819),'Sintesi',font=f(22,True),fill='#175d77')
  for j,line in enumerate(['Messaggio SPAM analizzato e classificato;','account protetto, evidenze conservate;','comunicazioni previste dal workflow completate.']):
   d.text((56,864+j*31),line,font=f(18),fill='#12324a')
 else:
  d.text((53,284),'Cronologia operativa',font=f(22,True),fill='#175d77')
  steps=[('09:15','Registrazione dell’incidente'),('09:48','Analisi della segnalazione'),('10:21','Blocco account e conservazione prove'),('11:05','Notifica informativa user alert'),('13:30','Verifica delle condizioni privacy'),('15:40','Controlli finali e chiusura')]
  for j,(when,what) in enumerate(steps):
   yy=338+j*81
   d.ellipse((59,yy+3,76,yy+20),fill='#0b9f97')
   d.text((92,yy),when,font=f(18,True),fill='#155d75')
   d.text((198,yy),what,font=f(17),fill='#12324a')
   if j<len(steps)-1:d.line((67,yy+23,67,yy+79),fill='#0b9f97',width=3)
  d.text((53,845),'Documenti e allegati',font=f(22,True),fill='#175d77')
  d.text((61,900),'• Riscontro tecnico (dati di prova)',font=f(19),fill='#12324a')
  d.text((61,943),'• Scheda conclusiva generata',font=f(19),fill='#12324a')
 d.line((50,1046,730,1046),fill='#d6e4eb',width=2)
 d.text((51,1060),'CIR · Esempio formativo non proveniente da un incidente reale',font=f(13),fill='#577383')
 d.text((657,1060),f'{number} / 2',font=f(15,True),fill='#0b7891')
 out=AS/f'example_report_page_{number}.png';im.save(out,optimize=True)
 return out
rp=[report_page(1),report_page(2)]
from reportlab.lib.utils import ImageReader
pdfname=AS/'example_report_synthetic.pdf'
c=canvas.Canvas(str(pdfname),pagesize=A4)
for im in rp:
 c.drawImage(ImageReader(str(im)),0,0,width=A4[0],height=A4[1]);c.showPage()
c.save()
files=[AS/f'visual_{idx:02d}.jpg' for idx in slides]+rp+[pdfname]
receipt={'source': 'Synthetic photorealistic artwork generated specifically for CIR training, then composited with authored technical diagrams; not an application screenshot.', 'source_image_sha256':sha256(src.read_bytes()).hexdigest(),'slides':{str(i):{'path':f'docs/presentation/visual_rc61_art/visual_{i:02d}.jpg','title':slides[i][0],'sha256':sha256((AS/f'visual_{i:02d}.jpg').read_bytes()).hexdigest()} for i in slides},'example_report':'Synthetic two-page illustrative report, derived from CIR report section structure but not emitted by the CIR Flask route.', 'assets_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in files}}
(AS/'provenance.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')
print('Generated artworks',len(slides),'and report',pdfname)
