#!/usr/bin/env python3
"""Generate translated cartoon artwork from the canonical Italian master."""
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1];ART=ROOT/'docs/presentation/rc97_cartoon';EN=ROOT/'docs/presentation/rc99_cartoon_en'
# Do not read any previous release; derive exclusively from the pinned IT images.
FONT='/usr/share/fonts/opentype/comic-neue/ComicNeue-Bold.otf'
F={ '01':'01_Perche_CIR.png','02':'02_Le_funzioni_operative.png','03':'03_Utenti_e_tenant.png','04':'04_Workflow_e_cataloghi.png','05':'05_Documenti_integrazioni_supporto.png','06':'06_Laboratorio_SPAM.png','07':'07_Conclusioni.png','08':'08_Appendici.png','grazie':'09_Grazie_CIR.png'}
# ellipses coordinates and the tip of each tail, in original illustration pixel space.
B={
'01':[((205,-15,835,215),(330,281),'We had an\nincident!'),((995,-15,1555,215),(1160,271),'Did you file it\nin CIR?')],
'02':[((25,-13,654,338),(178,420),'Can’t I just\nmark this case\nresolved?'),((660,-14,1370,334),(1150,397),'Sure! Once you\ncomplete the other\n112 steps!')],
'03':[((435,-5,990,315),(548,437),'Can I borrow your\nSPAM workflow?'),((987,-5,1540,315),(1080,420),'The workflow, sure!\nIncidents stay with\nme; you own the\nconsequences!')],
'04':[((100,18,642,182),(612,260),'Destination?'),((177,215,514,366),(413,417),'SPAM.'),((620,-12,1258,260),(868,319),'Great! Buckle up,\ntraffic is heavy!')],
'05':[((27,6,518,242),(348,296),'I just need\na signature!'),((550,-10,1160,266),(736,341),'First mapping,\nthen the template,\nthen the preview...'),((561,641,1055,884),(594,629),'Maybe I should\nstay a TXT file!')],
'06':[((75,98,532,354),(366,446),'It was just one\ninnocent email!'),((731,87,1347,350),(1012,407),'Sure. And are the\n2,598 emails sent\nafterward your\nrelatives?')],
'07':[((402,-9,764,228),(531,248),'I can finally\nrelax!'),((1102,-12,1530,261),(1198,286),'Of course!\nUntil the next\nincident!')],
'08':[((292,-13,681,144),(466,201),'Everybody here?'),((672,-10,1034,203),(877,242),'Wait! We’re missing\nthe completed PDF\nand notification!'),((1062,-12,1439,219),(1158,262),'As always,\nattachments arrive\nlast!')],
}

def bubble(img,bb,tip,lines,phase):
 d=ImageDraw.Draw(img);x0,y0,x1,y1=bb;cx=(x0+x1)//2;by=y1-14
 tw=(x1-x0)*0.17
 if phase=='shape':
  d.polygon(((cx-tw,by-10),(cx+tw*.7,by-10),tip),fill='white')
  d.line(((cx-tw,by-10),tip,(cx+tw*.7,by-10)),fill=(8,29,47),width=9,joint='curve')
  d.ellipse(bb,fill=(255,255,255),outline=(8,29,47),width=10)
  return
 text=lines.split('\n')
 fw=(x1-x0)*.84;fh=(y1-y0)*.77
 size=int(min(78,(fh/max(1,len(text)))/1.08))
 while size>15:
  ft=ImageFont.truetype(FONT,size)
  maxline=max(d.textbbox((0,0),t,font=ft)[2] for t in text)
  if maxline<=fw:break
  size-=1
 ft=ImageFont.truetype(FONT,size)
 height=len(text)*size*1.05
 y=(y0+y1-height)/2-size*.03
 for line in text:
  d.text((cx,y),line,font=ft,fill=(12,34,60),anchor='mt')
  y+=size*1.05

# Derive all English graphics from the current Italian canonical graphics.
for s,n in F.items():
 # Section 03 is an approved bilingual redraw of the same canonical Italian
 # composition. Keep the English translation paired with its source hash.
 if s=='03': continue
 im=Image.open(ART/n).convert('RGB')
 if s=='grazie':
  d=ImageDraw.Draw(im)
  d.rounded_rectangle((555,34,1307,263),radius=28,fill=(255,248,228))
  d.text((931,150),'Thank you!',font=ImageFont.truetype(FONT,120),fill=(7,34,78),anchor='mm')
 else:
  for bb,tip,text in B[s]:bubble(im,bb,tip,text,'shape')
  for bb,tip,text in B[s]:bubble(im,bb,tip,text,'text')
  if s=='06':
   d=ImageDraw.Draw(im)
   d.rounded_rectangle((142,7,1620,85),radius=6,fill=(10,54,82))
   d.text((880,44),'Hands-on lab: a SPAM incident example',font=ImageFont.truetype(FONT,52),fill='white',anchor='mm')
  if s=='07':
   d=ImageDraw.Draw(im);d.rounded_rectangle((18,109,248,195),radius=4,fill=(24,83,126))
   d.text((135,150),'Conclusions',font=ImageFont.truetype(FONT,34),fill='white',anchor='mm')
  if s=='08':
   d=ImageDraw.Draw(im);d.rounded_rectangle((18,108,248,194),radius=4,fill=(24,83,126))
   d.text((135,150),'Appendices',font=ImageFont.truetype(FONT,34),fill='white',anchor='mm')
 im.save(EN/n,optimize=True)
manifest={'schema':1,'master_locale':'it','derived_locale':'en','source':'Italian master art translated with in-balloon English lettering','artwork':[]}
it=json.loads((ART/'provenance.json').read_text())
for row in it['artwork']:
 s=row['section'];src=ART/F[s];dst=EN/F[s]
 if hashlib.sha256(src.read_bytes()).hexdigest()!=row['sha256']:
  raise ValueError('Italian cartoon changed without an updated canonical hash: '+s)
 manifest['artwork'].append({'section':s,'source_file':row['file'],'source_sha256':row['sha256'],'file':'docs/presentation/rc99_cartoon_en/'+F[s],'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'real_people':False,'contains_real_ui':False})
(EN/'provenance.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
print('Generated 9 English derivatives from canonical Italian cartoons')
