'use strict';
// CIR / teaching edition: intentionally all slide content and diagrams are editable.
const fs=require('fs');const path=require('path');
const pptxgen=require('pptxgenjs');
let imageSizingContain, imageSizingCrop;
try {
  ({imageSizingContain,imageSizingCrop}=require('/home/oai/skills/slides/pptxgenjs_helpers'));
} catch (_) {
  // Portable fallback for CI runners without the local slide-authoring toolbox.
  const {imageSize}=require('image-size');
  imageSizingContain=(file,x,y,w,h)=>{
    const {width,height}=imageSize(fs.readFileSync(file));
    const scale=Math.min(w/width,h/height);
    return {x:x+(w-width*scale)/2,y:y+(h-height*scale)/2,w:width*scale,h:height*scale};
  };
  // Full-bleed photography is decorative; a small stretch is acceptable in
  // this portable fallback, but actual interface screenshots use contain.
  imageSizingCrop=(_file,x,y,w,h)=>({x,y,w,h});
}
const root=process.env.CIR_REPO_ROOT||path.resolve(__dirname,'..');
const specFile=process.env.CIR_SPEC||path.join(root,'docs/presentation/visual_rc64_spec.json');
const out=process.argv[2]||'/mnt/data/CIR_Operational_Training_Visual_RC64.pptx';
const data=JSON.parse(fs.readFileSync(specFile,'utf8'));
for (const d of data) for(const media of (d.images||[])){
 const filename=String(media.file||'');
 if(!/^docs\/presentation\/visual_rc57_media\/[A-Za-z0-9._-]+$/.test(filename))throw new Error('External media disallowed: '+filename);
}
const crypto=require('crypto');
// Optional verified screenshot overlay: the CI's browser artifact is the only
// authoritative source for images that did not exist in the preceding run.
const manifestPath=process.env.CIR_SCREENSHOT_MANIFEST||null;
let ciManifest=null,ciById=new Map();
if(manifestPath){
  ciManifest=JSON.parse(fs.readFileSync(manifestPath,'utf8'));
  if(ciManifest.source_kind!=='real_browser' && !String(ciManifest.source_kind).includes('chromium')) {
    // Accept only actual CI browser fixtures. Never consume local mock art.
    if(!String(ciManifest.source_kind).includes('browser'))throw new Error('Manifest non proviene da browser reale');
  }
  for(const item of (ciManifest.screenshots||[])){
    const real=path.resolve(path.dirname(manifestPath),item.file);
    if(!real.startsWith(path.resolve(path.dirname(manifestPath))+path.sep))throw new Error('Screenshot path traversal');
    const digest=crypto.createHash('sha256').update(fs.readFileSync(real)).digest('hex');
    if(digest!==item.sha256)throw new Error('Checksum screenshot non valido: '+item.id);
    ciById.set(item.id,real);
  }
}
if(ciManifest && process.env.GITHUB_SHA && ciManifest.source_commit!==process.env.GITHUB_SHA)
  throw new Error('Screenshot di un commit diverso dalla build CI');
if(ciManifest && process.env.CIR_RELEASE_BUILD && ciManifest.build!==process.env.CIR_RELEASE_BUILD)
  throw new Error('Screenshot con build diversa dalla build CI');
if(process.env.CIR_REQUIRE_REAL_SCREENSHOTS==='1'){
  if(!ciManifest)throw new Error('Il manifest browser e obbligatorio nella CI');
  const required=['registry-closed-state','pdf-mapping-configuration','pdf-generated-preview',
    'alfresco-settings-desktop','alfresco-incident-documents',
    'spam-incident-config-labels'];
  const missing=required.filter(id=>!ciById.has(id));
  if(missing.length)throw new Error('Mancano screenshot autentici: '+missing.join(', '));
}
const ciCommit=ciManifest?.source_commit||'919b027403ee55db05b2355cd2f8fbd09c7cf7b4';
const ciBuild=ciManifest?.build||'20261124';
const ciViewByOldSlide={8:'login-desktop',9:'login-mobile',10:'admin-sso-desktop',
  11:'registry-desktop',12:'registry-closed-state',13:'registry-mobile',
  17:'incident-desktop',18:'spam-workflow-steps',20:'incident-desktop',
  21:'incident-desktop',23:'incident-desktop',36:'admin-modules-desktop',
  38:'registry-desktop',39:'admin-sso-desktop',48:'spam-workflow-steps',
  52:'pdf-mapping-configuration',53:'pdf-mapping-configuration',54:'pdf-mapping-configuration',
  55:'pdf-generated-preview',56:'alfresco-settings-desktop',
  58:'documentation-user-desktop',59:'documentation-admin-desktop',
  60:'assistant-desktop',61:'assistant-mobile',63:'spam-incident-desktop',
  64:'spam-incident-desktop',65:'spam-workflow-steps',66:'spam-workflow-steps',
  67:'spam-workflow-steps',71:'spam-incident-config-labels'};
function realUiImage(d){
  const id=d.kind==='preview'?'pdf-generated-preview':ciViewByOldSlide[d.original];
  return id&&ciById.get(id)?{id,path:ciById.get(id)}:null;
}
const pptx=new pptxgen();pptx.layout='LAYOUT_WIDE';pptx.author='CIR - Cybersecurity Incident Registry';pptx.subject='CIR | Laboratorio e documentazione utente, amministratore e governance';pptx.title='CIR — Presentazione didattica RC64';pptx.company='Cybersecurity Incident Registry';pptx.lang='it-IT';pptx.theme={headFontFace:'Arial',bodyFontFace:'Arial',lang:'it-IT'};
const W=13.33333,H=7.5;
const C={bg:'F4F8FA',white:'FFFFFF',navy:'12324A',muted:'60798A',cyan:'00A8BE',teal:'147E8F',blue:'326C92',violet:'6264A3',green:'23896B',gold:'F6A23A',pink:'D46C75',line:'D9E5EB',ink:'143044',shadow:'EDF3F6',pale:'EAF6F8'};
function rgb(hex){return '#'+hex;}
function addText(slide,t,o){slide.addText(t,{fontFace:'Arial',...o})}
function rect(slide,x,y,w,h,fill,line=null,r=0.13){slide.addShape(pptx.ShapeType.roundRect,{x,y,w,h,rectRadius:r,rotate:0,line:{color:line||fill,width:line?0.65:0},fill:{color:fill},radius:r})}
function line(slide,x,y,w,h,color=C.line,width=1){slide.addShape(pptx.ShapeType.line,{x,y,w,h,line:{color,width}})}
function ellipse(slide,x,y,w,h,color){slide.addShape(pptx.ShapeType.ellipse,{x,y,w,h,line:{color,width:0},fill:{color}})}
function arrow(slide,x,y,w,dir='right',color=C.cyan){slide.addShape(pptx.ShapeType.chevron,{x,y,w,h:0.34,flipH:dir==='left',line:{color,width:0},fill:{color}})}
function imagePath(im){if(!im)return null;let f=path.basename(im.file||'');return path.join(root,'docs/presentation/visual_rc57_media',f)}
function notes(slide,d){
 let n=(d.notes||'').replace(/\r/g,'');
 n+='\n\n[Sources]\n';
 const ids = d.photo_art?[]:(d.original===56 && ciById.has('alfresco-incident-documents')
   ? ['alfresco-settings-desktop','alfresco-incident-documents']
   : (realUiImage(d)?[realUiImage(d).id]:[]));
 if(d.photo_art && !ids.length)n+='Immagine sintetica fotografica originale, senza persone reali, senza titolo e footer; non e una schermata dell applicazione.\n';

 if([27,61].includes(d.index))n+='Sfondo sintetico originale senza persone, nessuna foto stock.\n';
 if(d.report_pages)n+='Pagine di report dimostrativo sintetico; non si tratta di un export dall app.\n';
 if(ids.length){
   n+='Schermata/e autentica/e CIR della CI corrente '+ciCommit+': '+ids.join(', ')+'. Manifest Chromium firmato da SHA-256.\n';
 }else if((d.images||[]).length){
   n+='Media editoriale della precedente presentazione CIR, derivato da evidenze CI con dati fittizi. Nessuna cattura attuale rivendicata.\n';
 }
 n+='Sorgente CIR 0.10.0-1 RC64. I dati sono di esempio; diagrammi e schemi non rappresentano screenshot dell’applicazione.\n';
 if(!ciManifest)n+='Le screenshot mancanti (chiusura completa, mapping, anteprima PDF, Alfresco) saranno acquisite da CI su interfaccia reale.\n';
 slide.addNotes(n);
}
function footer(slide,n){line(slide,.62,7.04,12.1,0,C.line,.7);addText(slide,'CIR - Cybersecurity Incident Registry',{x:.72,y:7.1,w:7.7,h:.18,fontSize:7.6,bold:true,color:C.muted,margin:0});addText(slide,'v0.10.0-1 · materiale didattico RC64',{x:8.05,y:7.10,w:3.35,h:.18,fontSize:7.2,color:C.muted,align:'right',margin:0});addText(slide,`${n} / ${data.length}`,{x:11.61,y:7.1,w:1.0,h:.18,fontSize:8.2,bold:true,color:C.teal,align:'right',margin:0});}
function bgBase(slide,section){slide.background={color:C.bg};rect(slide,.0,.0,W,.12,section);rect(slide,.5,.48,.055,.68,section);}
function safeBullets(d){return (d.bullets||[]).map(s=>String(s).replace(/\\\s*$/,'').trim()).filter(Boolean)}
// Photographic artwork is independent of slide chrome: no title, labels or footer.
// Validate image provenance hashes at generation time, then insert the whole scene.
const photoProvenance=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc63_art/provenance.json'),'utf8'));
const newPhotoProvenance=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc64_art/provenance.json'),'utf8'));
function photoPanel(slide,d,box={x:6.37,y:1.55,w:6.28,h:5.08}){
 const record=(d.photo_art.includes('/visual_rc64_art/')?newPhotoProvenance:photoProvenance).slides[String(d.index)];
 if(!record || record.file!==d.photo_art || record.real_people!==false)
   throw new Error('Invalid synthetic image provenance for slide '+d.index);
 const img=path.join(root,d.photo_art);
 if(!fs.existsSync(img))throw new Error('Missing synthetic photo '+img);
 const hash=crypto.createHash('sha256').update(fs.readFileSync(img)).digest('hex');
 if(hash!==record.sha256)throw new Error('Synthetic photo checksum mismatch: '+d.index);
 // The input photo is precomposed to the panel aspect ratio with a soft extension.
 // CONTAIN explicitly prevents invisible horizontal clipping.
 slide.addImage({path:img,...imageSizingContain(img,box.x,box.y,box.w,box.h)});
}
// A thematic photograph can occupy the upper part of the right column, with a
// separate *editable* vector diagram beneath it. Avoid diagram text in a photo.
function tenantInheritanceDiagram(slide){
 const x=6.57;
 addText(slide,'ESEMPIO · DESTINATARI DELLE NOTIFICHE',{x:x,y:3.82,w:5.84,h:.22,fontSize:9.2,bold:true,color:C.teal,margin:0,align:'center'});
 rect(slide,8.13,4.13,2.72,.57,'DDEEF9','AEC9DA');
 addText(slide,'TENANTS DEFAULT\nDestinatari standard',{x:8.23,y:4.19,w:2.52,h:.44,fontSize:11.6,bold:true,color:C.navy,align:'center',valign:'mid',margin:0,fit:'shrink'});
 line(slide,9.49,4.71,0,.16,C.teal,2);
 line(slide,7.99,4.87,3.00,0,C.teal,2);
 line(slide,7.99,4.87,0,.19,C.teal,2);
 line(slide,10.99,4.87,0,.19,C.teal,2);
 boxNode(slide,'SEDE A',6.71,5.09,2.64,.39,'E6F4FA',C.navy,12.2);
 boxNode(slide,'SEDE B',9.64,5.09,2.64,.39,'E7F5ED',C.navy,12.2);
 boxNode(slide,'Eredita i destinatari\nstandard',6.71,5.54,2.64,.63,'EAF5FA',C.navy,11.5);
 boxNode(slide,'Override locale:\ncontatti della sede',9.64,5.54,2.64,.63,'E8F6EF',C.navy,11.5);
 addText(slide,'La personalizzazione resta nel tenant e non cambia il valore comune.',{x:6.61,y:6.38,w:5.85,h:.24,fontSize:9.5,color:C.muted,italic:true,align:'center',margin:0});
}
function rightPanel(slide,d,accent){rect(slide,6.27,1.46,6.47,5.32,C.white,C.line);
 if(d.index===21 && Array.isArray(d.report_pages)){
  const src=(d.images||[]).find(i=>fs.existsSync(imagePath(i)));
  const fromCI=realUiImage(d);
  const action=src?imagePath(src):(fromCI?fromCI.path:null);
  addText(slide,'DOVE GENERARE IL REPORT',{x:6.57,y:1.57,w:5.84,h:.2,fontSize:9,bold:true,color:C.teal,align:'center',margin:0});
  if(action)slide.addImage({path:action,...imageSizingContain(action,6.54,1.79,5.93,.55)});
  line(slide,6.7,2.48,5.63,0,C.line,1);
  for(let i=0;i<2;i++){
   const name=path.join(root,d.report_pages[i]);
   const xx=6.91+i*2.86;
   rect(slide,xx,2.72,2.49,3.54,'F4F8FA',C.line);
   if(fs.existsSync(name))slide.addImage({path:name,...imageSizingContain(name,xx+.08,2.79,2.33,3.35)});
   addText(slide,'PAGINA '+(i+1)+' / 2',{x:xx,y:6.36,w:2.48,h:.19,fontSize:8.6,bold:true,color:C.teal,align:'center',margin:0});
  }
  return;
 }
 if(d.photo_art){
  if(d.right_diagram==='tenant_inheritance'){
    photoPanel(slide,d,{x:6.45,y:1.56,w:6.12,h:2.17});
    tenantInheritanceDiagram(slide);
  } else {
    photoPanel(slide,d);
  }
  return;
 }

 if(d.original===56 && ciById.has('alfresco-settings-desktop') && ciById.has('alfresco-incident-documents')){
  const entries=[['alfresco-settings-desktop','CONFIGURAZIONE ADMIN'],['alfresco-incident-documents','DOCUMENTI DELL’INCIDENTE']];
  entries.forEach((pair,i)=>{
    const yy=1.62+i*2.45;const img=ciById.get(pair[0]);
    addText(slide,pair[1],{x:6.53,y:yy,w:5.99,h:.25,fontSize:9.4,bold:true,color:C.teal,align:'center',margin:0});
    rect(slide,6.52,yy+.31,5.99,2.02,'F6F9FA');
    slide.addImage({path:img,...imageSizingContain(img,6.55,yy+.34,5.92,1.95)});
  });
  return;
 }
 const images=d.images||[];const src=images.find(i=>fs.existsSync(imagePath(i)));const real=realUiImage(d);const ciScreen=Boolean(real||(src&&(src.px||[])[0]>1000));
 if(src||real){const img=real?real.path:imagePath(src);rect(slide,6.52,1.80,5.99,4.48,'F6F9FA');slide.addImage({path:img,...imageSizingContain(img,6.52,1.83,5.99,4.37)});addText(slide,ciScreen?'SCHERMATA CI / DATI DI PROVA':'VISUAL ORIGINALE CIR',{x:6.57,y:6.43,w:5.83,h:.24,fontSize:8.7,bold:true,color:C.teal,align:'center',margin:0});}
 else {visual(slide,d,accent);}
 }
function boxNode(slide,txt,x,y,w,h,fill=C.pale,color=C.navy,size=13){rect(slide,x,y,w,h,fill);addText(slide,txt,{x:x+.13,y:y+.08,w:w-.26,h:h-.16,fontSize:size,color,bold:true,align:'center',valign:'mid',margin:0,breakLine:false,fit:'shrink'});}
function visual(slide,d,accent){const title=d.title.toLowerCase();const x=6.60,y=1.94,w=5.74,h=4.16;
 addText(slide,'SCHEMA OPERATIVO',{x:x,y:1.72,w:w,h:.22,color:accent,fontSize:9,bold:true,margin:0,charSpacing:1});
 if(d.original===47){
  const types=[['Registration','Registra azione'],['Execution','Esegui / notifica'],['Update','Modifica sezione'],['Operation','Documento / file']];
  types.forEach((a,i)=>{const yy=y+.14+i*.93;boxNode(slide,a[0],x+.04,yy,2.05,.65,['E6F2FA','E7F6F0','F3F0FA','FFF2DC'][i],C.navy,14);arrow(slide,x+2.20,yy+.18,.42,'right',accent);boxNode(slide,a[1],x+2.83,yy,2.78,.65,'F1F6F9',C.navy,13.7);});
 }else if(d.kind==='preview'||/mapping pdf|moduli pdf|documento dpo/.test(title)){
  // Native PDF/AcroForm map and explicit CI limitation (never simulate a screenshot).
  boxNode(slide,'Modulo PDF\nAcroForm',x+.10,y+.12,2.1,.95,'DFEDF4',C.navy,16);boxNode(slide,'Dati\ndell’incidente',x+3.29,y+.12,2.1,.95,'E6F4EE',C.navy,15);arrow(slide,x+2.38,y+.43,.62,'right',accent);
  boxNode(slide,'%REFERENCE% → RIFERIMENTO\n%NAME% → NOMINATIVO\n%START% → DATA',x+.31,y+1.38,5.1,1.16,'F2F7FA',C.navy,12.8);
  boxNode(slide,'PDF compilato → anteprima → download',x+.31,y+2.87,5.1,.66,'DBF2F2',C.navy,13);
  addText(slide,'Anteprima autentica da acquisire nella prossima CI',{x:x+.22,y:y+3.75,w:5.32,h:.29,fontSize:9.2,italic:true,color:C.muted,align:'center',margin:0});
 } else if(/alfresco/.test(title)){
  boxNode(slide,'CONFIGURAZIONE\n(Amministratore)',x+.10,y+.34,2.5,1.0,'E6F0F9',C.navy,15);boxNode(slide,'REPOSITORY\nALFRESCO',x+3.11,y+.34,2.5,1.0,'EAF5F3',C.navy,15);arrow(slide,x+2.64,y+.65,.42,'right',accent);boxNode(slide,'INCIDENTE\n(operatori autorizzati)',x+1.10,y+2.12,3.7,.94,'F3F0FA',C.navy,14);line(slide,x+4.33,y+1.43,0,.6,accent,2);addText(slide,'Cattura reale da acquisire in CI',{x:x+.48,y:y+3.56,w:4.8,h:.36,fontSize:10,color:C.muted,italic:true,align:'center',margin:0});
 } else if(d.original===49||d.original===50||/notific|template/.test(title)) {
   boxNode(slide,'Template notifica',x+.60,y+.28,4.55,.65,'E6F2FA',C.navy,15);
   boxNode(slide,'%NAME% · %REFERENCE% · %START%',x+.48,y+1.30,4.77,.73,'F2F5F9',C.navy,12.3);
   boxNode(slide,'Dati dell’incidente → testo compilato',x+.48,y+2.40,4.77,.72,'E7F6F1',C.navy,12.5);
   boxNode(slide,'Invio con tracciamento',x+.48,y+3.37,4.77,.62,'E9F3FA',C.navy,12.5);
 } else if(/workflow|fasi|stato|step|condizioni|dipendenze/.test(title)){
   const titles=/personal_data/.test(title)?['Incident\ndata','personal_data\n= sì','Notifica\nGarante','Notifica\nutente']: /chiusura/.test(title)?['Azioni\ncompletate','global_check','close_without\n_warnings','Chiusura']:['Apertura','Analisi','Azioni','Verifica','Chiusura'];
   const count=titles.length;const bw=count===5?1.0:1.19;const gx=count===5?.16:.31;const tx=x+.04;
   titles.forEach((t,i)=>{const xx=tx+i*(bw+gx);boxNode(slide,t,xx,y+1.17,bw,.93,i%2?'E3F4F1':'E7F0F8',C.navy,count===5?10.5:12);if(i<count-1)arrow(slide,xx+bw+.022,y+1.47,gx-.055,'right',accent)});
   boxNode(slide,'Definito dagli amministratori · visibile agli utenti autorizzati',x+.25,y+3.02,5.27,.65,'F1F6F8',C.muted,11);
 } else if(/tenant|eredit|utenti|sso|identit|parametri|ruoli|autorizz/.test(title)){
   boxNode(slide,'ISTANZA CIR',x+1.56,y+.34,2.66,.69,'E4ECF5',C.navy,16);line(slide,x+2.9,y+1.04,0,.6,accent,2);line(slide,x+1.44,y+1.63,3.0,0,accent,2);[0,1,2].forEach(i=>{line(slide,x+1.44+i*1.5,y+1.63,0,.39,accent,2);boxNode(slide,['Tenant A','Tenants Default','Tenant B'][i],x+.67+i*1.5,y+2.01,1.43,.82,i===1?'E8F6EF':'E6F2F9',C.navy,12.3)});boxNode(slide,'Permessi e dati separati · valori di default riutilizzabili',x+.44,y+3.30,5.07,.71,'F0F5F7',C.muted,10.8);
 } else if(/sicurezza|tracci|backup|disaster|recovery/.test(title)){
   [['Ruoli & SSO',x+.21,y+.28],['Audit trail',x+3.16,y+.28],['Integrità dati',x+.21,y+1.94],['Backup & restore',x+3.16,y+1.94]].forEach(([t,bx,by],i)=>boxNode(slide,t,bx,by,2.38,1.17,['E9F3FA','E8F6F0','F3F0FA','FDF3E8'][i],C.navy,15));
 } else if(/report|statistiche/.test(title)){
   boxNode(slide,'REPORT PDF\ndal dettaglio incidente',x+.12,y+.38,2.59,1.2,'E6F2FA',C.navy,14.5);boxNode(slide,'STATISTICHE\ndal menu Report',x+3.10,y+.38,2.5,1.2,'E7F6F0',C.navy,14.5);const vals=[1.24,2.00,1.46,2.47,1.87];vals.forEach((v,i)=>rect(slide,x+.74+i*.91,y+3.34-v*.40,.52,v*.4,['12AAC1','4996BE','63B0AB','6A91BD','84C9BA'][i]));line(slide,x+.50,y+3.4,4.94,0,C.line,1);
 } else if(/notific|template/.test(title)){
   boxNode(slide,'Modello notifica',x+.60,y+.28,4.55,.65,'E6F2FA',C.navy,15);boxNode(slide,'%NAME% · %REFERENCE% · %START%',x+.48,y+1.30,4.77,.73,'F2F5F9',C.navy,12.3);boxNode(slide,'Sostituzione variabili dal contesto incidente',x+.48,y+2.40,4.77,.72,'E7F6F1',C.navy,12.5);arrow(slide,x+2.68,y+3.43,.52,'right',accent);
 }else if(/sommario|sintesi|contributi|documentazione/.test(title)){
   const toks=['Operazioni','Governance','Workflow','Documenti','Integrazioni'];toks.forEach((t,i)=>boxNode(slide,t,x+.46+(i%2)*2.6,y+.3+Math.floor(i/2)*1.15,2.41,.86,['E6F2FA','E6F6F0','F3F0FA','FCEFD9','E8F3F4'][i],C.navy,13.5));
 }else{
   boxNode(slide,'CONFIGURAZIONE',x+.45,y+.25,4.99,.74,'E8F2F7',C.navy,17);boxNode(slide,'AMBIENTE OPERATIVO',x+.45,y+1.55,4.99,.74,'E5F5EF',C.navy,17);boxNode(slide,'TRACCIAMENTO & GOVERNANCE',x+.45,y+2.85,4.99,.74,'F0EDFA',C.navy,14.5);arrow(slide,x+2.65,y+1.06,.54,'right',accent);arrow(slide,x+2.65,y+2.36,.54,'right',accent);
 }
}
function makeContent(slide,d,index){const accent=[C.cyan,C.teal,C.blue,C.violet,C.green][Math.floor((index-1)/15)%5];bgBase(slide,accent);
 addText(slide,(d.tag||'CIR / FORMAZIONE').toUpperCase(),{x:.74,y:.34,w:11.4,h:.24,fontSize:9.1,bold:true,charSpacing:1.12,color:accent,margin:0});
 const t=d.title||'';let font=t.length>77?20.5:t.length>56?23.0:27;
 addText(slide,t,{x:.73,y:.70,w:11.9,h:.61,fontSize:font,bold:true,color:C.navy,breakLine:false,margin:0,fit:'shrink'});
 const bullets=safeBullets(d);let count=bullets.length;let baseY=1.51;
 const blockH=d.index===30?1.44:(count===5?.91:1.14);const g=d.index===30?.22:(count===5?.15:.12);if(d.index===30)baseY=1.61;
 bullets.forEach((b,i)=>{
   const yy=baseY+i*(blockH+g);rect(slide,.70,yy,5.29,blockH,C.white,C.line);rect(slide,.70,yy,.08,blockH,accent);
   const tc= b.length>122?12.3:b.length>105?12.8:b.length>85?13.4:14.3;
   const url=b.match(/https?:\/\/[^\s]+/);
   const manualUrl=b.match(/(?:github\.com\/desalvo\/cybersecurity-incident-registry\/blob\/main\/docs\/[^\s]+)/);
   const linkUrl=url?url[0]:(manualUrl?'https://'+manualUrl[0]:null);
   addText(slide,b,{x:.94,y:yy+.08,w:4.86,h:blockH-.15,fontSize:tc,color:C.ink,breakLine:false,margin:0,fit:'shrink',valign:'mid',lineSpacingMultiple:1.01,...(linkUrl?{hyperlink:{url:linkUrl},underline:{color:C.teal}}:{})});
 });
 rightPanel(slide,d,accent);
 if([11,12].includes(d.original)){
  boxNode(slide,'⚠ Azioni mancanti = avviso',6.58,6.13,2.76,.40,'FCF2D9','80561C',10.7);
  boxNode(slide,'✓ Chiuso e completo = verde',9.45,6.13,2.86,.40,'E4F5EB','13744D',10.3);
  addText(slide,ciById.has('registry-closed-state')?'Icone e stati verificati nella cattura CI della build corrente.':'Le icone ✓ reali saranno evidenziate nella nuova cattura CI.',{x:6.7,y:6.66,w:5.7,h:.21,fontSize:8.4,color:C.muted,italic:true,align:'center',margin:0});
 }
 footer(slide,index);notes(slide,d);
}
function makeChapter(slide,d,index){slide.background={color:C.navy};const first=d.images?.[0];const img=[27,61].includes(d.index)?path.join(root,'docs/presentation/visual_rc62_art/synthetic_cir_no_people.png'):(first&&imagePath(first));if(img&&fs.existsSync(img))slide.addImage({path:img,...imageSizingCrop(img,0,0,W,H)}); // retain source photo
 slide.addShape(pptx.ShapeType.rect,{x:0,y:0,w:W,h:H,line:{color:C.navy,transparency:100},fill:{color:C.navy,transparency:27}});
 rect(slide,.82,1.33,.11,4.35,C.cyan);
 addText(slide,'FORMAZIONE • CIR',{x:1.25,y:1.18,w:10.2,h:.35,color:'D5F6FC',fontSize:16,bold:true,charSpacing:1.8,margin:0});
 const parts=(d.title||'').split('/');let nb=(parts[0]||'').trim(),name=parts.slice(1).join('/').trim();
 addText(slide,nb,{x:1.22,y:2.10,w:10,h:1.20,fontSize:65,color:'FFFFFF',bold:true,margin:0});
 addText(slide,name||d.title,{x:1.25,y:3.43,w:10.4,h:1.25,fontSize:36,bold:true,color:'FFFFFF',margin:0,fit:'shrink'});
 addText(slide,`${index} / ${data.length}`,{x:11.55,y:6.78,w:.97,h:.30,color:'FFFFFF',align:'right',fontSize:10,bold:true,margin:0});notes(slide,d);
}
function makeCover(slide,d,index){slide.background={color:C.navy};const img=imagePath(d.images[0]);if(fs.existsSync(img))slide.addImage({path:img,...imageSizingCrop(img,0,0,W,H)});slide.addShape(pptx.ShapeType.rect,{x:0,y:0,w:W,h:H,fill:{color:C.navy,transparency:19},line:{color:C.navy,transparency:100}});
 const logo=imagePath(d.images[1]);if(fs.existsSync(logo))slide.addImage({path:logo,...imageSizingContain(logo,.88,1.02,1.18,1.18)});
 addText(slide,'CYBERSECURITY INCIDENT REGISTRY',{x:2.33,y:1.24,w:9.9,h:.43,fontSize:19,color:'BCE7F0',bold:true,margin:0,charSpacing:1.7});
 addText(slide,'CIR',{x:.98,y:2.29,w:7.2,h:1.55,fontSize:90,bold:true,color:'FFFFFF',margin:0});
 addText(slide,'Gestione degli incidenti e dei workflow procedurali',{x:1.01,y:4.18,w:10.95,h:.88,fontSize:28,bold:true,color:'FFFFFF',margin:0,fit:'shrink'});
 addText(slide,'Corso didattico · interfaccia reale · laboratorio SPAM',{x:1.04,y:5.28,w:10.9,h:.38,fontSize:17.1,color:'D7F4FC',margin:0});
 rect(slide,1.02,6.30,11.24,.45,C.white);addText(slide,`VERSIONE 0.10.0-1     |     RC64     |     SCHERMATE CI ${ciCommit.slice(0,8)} / BUILD ${ciBuild}`,{x:1.21,y:6.41,w:10.92,h:.21,fontSize:10.6,color:C.navy,bold:true,margin:0});notes(slide,d);
}
for(const d of data){let slide=pptx.addSlide();if(d.kind==='cover')makeCover(slide,d,d.index);else if(d.kind==='chapter')makeChapter(slide,d,d.index);else makeContent(slide,d,d.index)}
fs.mkdirSync(path.dirname(out),{recursive:true});pptx.writeFile({fileName:out}).then(()=>console.log('Created '+out+' slides='+data.length)).catch(e=>{console.error(e);process.exit(1)});
