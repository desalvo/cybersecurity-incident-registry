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
const out=process.argv[2]||'/mnt/data/CIR_Operational_Training_Visual.pptx';
const originalData=JSON.parse(fs.readFileSync(specFile,'utf8'));
const addendumPath=path.join(root,'docs/presentation/visual_rc69_addendum.json');
const addendum=JSON.parse(fs.readFileSync(addendumPath,'utf8'));
const archAddendum=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc71_architecture_addendum.json'),'utf8'));
if(archAddendum.insert_after_original!==6 || archAddendum.slides.length!==3 ||
   archAddendum.slides.some((row,i)=>row.index!==86+i || row.original!==86+i || !['modules','procedures','ecosystem'].includes(row.arch_visual)))
  throw new Error('Invalid modular architecture chapter addendum');
if(addendum.insert_after_original!==14 || addendum.slides.length!==6)
  throw new Error('Invalid incident-opening instructional addendum');
const expectedTeachingSequence = ['incident-entry', 'incident-blank', 'incident-model',
  'incident-admin', 'incident-from-existing', 'incident-template'];
if(addendum.slides.some((item,i)=>item.training_flow!==expectedTeachingSequence[i] ||
  item.index!==80+i || item.original!==80+i))
  throw new Error('The incident-opening chapter must explain manual entry, templates administration, then template-based entry');
const data=[];
for(const item of originalData){
 data.push(item);
 if(item.index===6)data.push(...archAddendum.slides);
 if(item.index===14)data.push(...addendum.slides);
}
if(data.length!==88)throw new Error('Expected 88 instructional slides');
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
    'spam-incident-config-labels','tenant-setup-wizard-desktop',
    'tenant-setup-wizard-panel'];
  const missing=required.filter(id=>!ciById.has(id));
  if(missing.length)throw new Error('Mancano screenshot autentici: '+missing.join(', '));
}
const ciCommit=ciManifest?.source_commit||'919b027403ee55db05b2355cd2f8fbd09c7cf7b4';
const ciBuild=ciManifest?.build||'20261124';
const ciViewByOldSlide={8:'login-desktop',9:'login-mobile',10:'admin-sso-desktop',
  11:'registry-desktop',12:'registry-closed-state',13:'registry-mobile',
  15:'incident-desktop',16:'incident-desktop',18:'incident-desktop',19:'incident-desktop',
  17:'incident-desktop',18:'spam-workflow-steps',20:'incident-desktop',
  21:'incident-desktop',23:'incident-desktop',36:'admin-modules-desktop',
  37:'admin-sso-desktop',
  35:'tenant-setup-wizard-panel',38:'registry-desktop',39:'admin-sso-desktop',48:'workflow-steps-focused',
  52:'pdf-mapping-configuration',53:'pdf-mapping-configuration',54:'pdf-mapping-configuration',
  55:'pdf-generated-preview',56:'alfresco-settings-desktop',
  56:'alfresco-settings-desktop',57:'statistics-desktop',
  58:'documentation-admin-desktop',59:'assistant-panel-closeup',
  60:'assistant-panel-closeup',61:'assistant-mobile',62:'spam-incident-desktop',63:'spam-incident-desktop',
  64:'spam-incident-desktop',65:'spam-workflow-steps',66:'spam-workflow-steps',
  67:'spam-workflow-steps',71:'spam-incident-config-labels'};
function realUiImage(d){
  const id=d.kind==='preview'?'pdf-generated-preview':ciViewByOldSlide[d.original];
  return id&&ciById.get(id)?{id,path:ciById.get(id)}:null;
}
const pptx=new pptxgen();pptx.layout='LAYOUT_WIDE';pptx.author='CIR - Cybersecurity Incident Registry';pptx.subject='CIR | Laboratorio e documentazione utente, amministratore e governance';pptx.title='CIR — Presentazione didattica RC77';pptx.company='Cybersecurity Incident Registry';pptx.lang='it-IT';pptx.theme={headFontFace:'Arial',bodyFontFace:'Arial',lang:'it-IT'};
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
 const paletteCI=d.index===70 && realUiImage(d)?.id==='spam-incident-config-labels';
 const wizardCI=d.index===33 && realUiImage(d)?.id==='tenant-setup-wizard-panel';
 const labCategoryCI=d.index===62 && ciById.has('spam-incident-config-labels');
 const ids = labCategoryCI?['spam-incident-config-labels']:(wizardCI?['tenant-setup-wizard-panel']:(paletteCI?['spam-incident-config-labels']:(d.photo_art?[]:(d.original===56 && ciById.has('alfresco-incident-documents')
   ? ['alfresco-settings-desktop','alfresco-incident-documents']
   : (realUiImage(d)?[realUiImage(d).id]:[])))));
 if(d.arch_visual)n+='Illustrazione sintetica originale e diagramma nativo PowerPoint, senza persone, senza testo incorporato. Immagine verificata SHA-256.\n';
 if(d.index===59)n+='Avatar AlBot ufficiale dell applicazione: app/static/ai-chatbot/albot-avatar.png.\n';
 if(d.photo_art && !ids.length)n+='Immagine sintetica fotografica originale, senza persone reali, senza titolo e footer; non e una schermata dell applicazione.\n';

 if([27,61].includes(d.index))n+='Sfondo sintetico originale senza persone, nessuna foto stock.\n';
 if(d.report_pages)n+='Pagine di report dimostrativo sintetico; non si tratta di un export dall app.\n';
 if(d.training_flow==='incident-entry' && ciById.has('registry-desktop'))
   n+='Schermata autentica CIR catturata dal browser della build corrente: registry-desktop.\n';
 if(d.training_flow && d.training_flow!=='incident-entry')
   n+='Schemi didattici originali con forme PowerPoint modificabili.\n';
 if(ids.length){
   n+='Schermata/e autentica/e CIR della CI corrente '+ciCommit+': '+ids.join(', ')+'. Manifest Chromium firmato da SHA-256.\n';
 }else if((d.images||[]).length){
   n+='Media editoriale della precedente presentazione CIR, derivato da evidenze CI con dati fittizi. Nessuna cattura attuale rivendicata.\n';
 }
 n+='Sorgente CIR 0.10.0-1 RC77. I dati sono di esempio; diagrammi e schemi non rappresentano screenshot dell’applicazione.\n';
 if(!ciManifest)n+='Le screenshot mancanti (chiusura completa, mapping, anteprima PDF, Alfresco) saranno acquisite da CI su interfaccia reale.\n';
 slide.addNotes(n);
}
function footer(slide,n){line(slide,.62,7.04,12.1,0,C.line,.7);addText(slide,'CIR - Cybersecurity Incident Registry',{x:.72,y:7.1,w:7.7,h:.18,fontSize:7.6,bold:true,color:C.muted,margin:0});addText(slide,'v0.10.0-1 · materiale didattico RC77',{x:8.05,y:7.10,w:3.35,h:.18,fontSize:7.2,color:C.muted,align:'right',margin:0});addText(slide,`${n} / ${data.length + (ciManifest?.screenshots?.length||0)}`,{x:11.61,y:7.1,w:1.0,h:.18,fontSize:8.2,bold:true,color:C.teal,align:'right',margin:0});}
function bgBase(slide,section){slide.background={color:C.bg};rect(slide,.0,.0,W,.12,section);rect(slide,.5,.48,.055,.68,section);}
function safeBullets(d){return (d.bullets||[]).map(s=>String(s).replace(/\\\s*$/,'').trim()).filter(Boolean)}
// Photographic artwork is independent of slide chrome: no title, labels or footer.
// Validate image provenance hashes at generation time, then insert the whole scene.
const photoProvenance=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc63_art/provenance.json'),'utf8'));
const newPhotoProvenance=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc64_art/provenance.json'),'utf8'));
const modularArtProv=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc71_art/provenance.json'),'utf8'));
const ecosystemArtProv=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc77_art/provenance.json'),'utf8'));
const modularArtByKind=new Map([...modularArtProv.artwork,...ecosystemArtProv.artwork].map(x=>[x.kind,x]));
const incidentArtProv=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc69_art/provenance.json'),'utf8'));
const incidentArtRecord=incidentArtProv.artwork[0];
const incidentArtPath=path.join(root,incidentArtRecord.file);
if(incidentArtRecord.human_people!==false ||
   crypto.createHash('sha256').update(fs.readFileSync(incidentArtPath)).digest('hex')!==incidentArtRecord.sha256)
 throw new Error('Invalid incident opening illustration provenance');
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
function incidentTrainingRight(slide,d,accent){
 const kind=d.training_flow;
 const x=6.40, y=1.58, w=6.21;
 function label(value,xx,yy,ww,hh,fill='E9F3FA',fs=12.5){boxNode(slide,value,xx,yy,ww,hh,fill,C.navy,fs)}
 function link(y0){arrow(slide,9.16,y0,.63,'right',accent)}
 if(kind==='incident-entry'){
  // Use this run's real browser screenshot if available. The older vetted
  // editorial screenshot is a clearly labelled fallback, never a simulation.
  const current=ciById.get('registry-desktop');
  const source=current||path.join(root,'docs/presentation/visual_rc57_media/2ae5becb321feb73.jpg');
  slide.addImage({path:source,...imageSizingContain(source,x+0.06,y+0.07,w-.12,3.65)});
  label('REGISTRO INCIDENTI',x+.19,5.37,2.58,.43,'E6F0F9',11.6);
  arrow(slide,9.23,5.43,.62,'right',accent);
  label('Nuovo incidente',x+3.49,5.37,2.47,.43,'E7F6EF',12.1);
  addText(slide,current?'Schermata autentica CIR della build CI corrente':'Schermata autentica CIR archiviata · dati di laboratorio',
   {x:x+.10,y:6.16,w:6.02,h:.24,fontSize:9.0,color:C.muted,align:'center',margin:0});
  return;
 }
 if(kind==='incident-blank'){
   label('NUOVO INCIDENTE · ESEMPIO DI CAMPI',x+.18,y+.14,5.86,.48,'DFEDF8',13.4);
   [['Nome *','Segnalazione phishing · esempio'],['Riferimento *','utenza.lab@example.invalid'],
    ['1ª categoria / gravità','SPAM (Tutorial) / Media'],['Dati interessati','Account, credenziali'],
    ['Data e ora di inizio','Impostate al momento corrente']].forEach(([a,b],i)=>{
       const yy=2.35+i*.70;label(a,x+.25,yy,2.02,.53,'E9F1F7',11.7);
       label(b,x+2.37,yy,3.60,.53,'FFFFFF',11.5);
    });
   label('1ª SPAM  →  workflow SPAM  →  Crea',x+.38,6.10,5.55,.48,'E3F4E8',12.2);
 } else if(kind==='incident-template'){
   slide.addImage({path:incidentArtPath,...imageSizingContain(incidentArtPath,x+.13,y+.08,5.98,2.15)});
   const boxes=[['1 · Scegli il modello','F2F6FB'],['2 · Campi precompilati','E5F3FA'],
    ['3 · SPAM prima tra le categorie','FDF4DF'],['4 · Crea → workflow SPAM','E5F6EB']];
   boxes.forEach(([txt,color],i)=>{
    label(txt,x+.34,3.94+i*.64,5.41,.52,color,13.2);
    if(i!==3)addText(slide,'↓',{x:8.99,y:4.43+i*.64,w:.52,h:.16,fontSize:13,color:accent,align:'center',margin:0});
   });
 } else if(kind==='incident-model'){
   label('MODELLO = DATI INIZIALI RIUTILIZZABILI',x+.21,1.90,5.83,.58,'DFEDF8',13.5);
   label('Campi · Classificazione · Destinatari',x+.45,2.80,5.36,.70,'E6F2FA',13.0);
   label('Nuovo incidente con i valori già proposti',x+.45,3.87,5.36,.70,'E6F5EB',12.9);
   label('Utilizzo: writer · admin · superuser',x+.42,5.15,5.39,.48,'F8F0DA',12.4);
   label('Gestione: admin · superuser',x+.42,5.77,5.39,.48,'EEE8F9',12.4);
 } else if(kind==='incident-admin'){
   label('ADMIN → MODELLI INCIDENTE',x+.22,1.95,5.75,.65,'E6F0F9',13.3);
   [['CREA','Definisci i campi → Salva modello'],['MODIFICA','Seleziona il modello → Salva'],
    ['CANCELLA','Seleziona → Conferma eliminazione']].forEach(([a,b],i)=>{
      const yy=3.13+i*1.02;
      label(a,x+.20,yy,1.57,.77,['E8F4EB','E7F2FB','FBEBE6'][i],14);
      label(b,x+1.89,yy,4.13,.77,'F8FAFC',12.4);
   });
 } else if(kind==='incident-from-existing'){
   label('CASO REGISTRATO',x+.63,2.05,4.95,.74,'E6F0F9',15);
   addText(slide,'↓',{x:8.90,y:2.94,w:.75,h:.34,fontSize:23,color:accent,align:'center',margin:0});
   label('Admin → Crea modello da incidente esistente',x+.36,3.42,5.59,.72,'E7F6EE',12.4);
   addText(slide,'↓',{x:8.9,y:4.24,w:.75,h:.34,fontSize:23,color:accent,align:'center',margin:0});
   label('Solo dati iniziali · senza azioni/documenti',x+.33,4.77,5.63,.83,'FBF2E7',12.8);
   label('MODELLO RIUTILIZZABILE NEL TENANT',x+.34,5.92,5.62,.49,'E5F3FA',11.8);
 }
 addText(slide,'Diagramma didattico modificabile · non è una screenshot dell’applicazione',
   {x:x+.12,y:6.56,w:5.97,h:.20,fontSize:8.6,italic:true,color:C.muted,align:'center',margin:0});
}
function modularArchitecturePanel(slide,d,accent){
 const row=modularArtByKind.get(d.arch_visual);
 if(!row || row.real_people!==false || row.contains_embedded_slide_chrome!==false)throw new Error('Untrusted modular artwork');
 const img=path.join(root,row.file);
 if(!fs.existsSync(img) || crypto.createHash('sha256').update(fs.readFileSync(img)).digest('hex')!==row.sha256)
    throw new Error('Modular artwork SHA-256 mismatch');
 slide.addImage({path:img,...imageSizingContain(img,6.43,1.55,6.14,d.arch_visual==='ecosystem'?3.52:2.74)});
 line(slide,6.58,d.arch_visual==='ecosystem'?5.12:4.38,5.77,0,C.line,1.1);
 if(d.arch_visual==='ecosystem'){
   // The picture is a standalone synthetic architectural illustration. The
   // platform names and feature matrix are separate, editable PPTX elements.
   addText(slide,'PLATTAFORME E DISTRIBUZIONE',{x:6.60,y:5.22,w:5.77,h:.24,fontSize:10.0,color:C.teal,bold:true,margin:0,align:'center'});
   boxNode(slide,'Docker / Podman',6.57,5.53,1.81,.66,'E5F2FA',C.navy,11.5);
   boxNode(slide,'Kubernetes / Helm',8.50,5.53,1.85,.66,'E6F5EE',C.navy,11.1);
   boxNode(slide,'OpenShift',10.48,5.53,1.84,.66,'F5EFFC',C.navy,11.5);
   addText(slide,'Flask / Gunicorn · PostgreSQL · workflow · PDF · AlBot · Alfresco',
    {x:6.58,y:6.41,w:5.81,h:.24,fontSize:9.25,color:C.teal,bold:true,align:'center',margin:0});
 }else if(d.arch_visual==='modules'){
   boxNode(slide,'PLUGIN 1  ·  AlBot (AI)',6.58,4.60,2.77,.72,'E4F2FA',C.navy,13.0);
   boxNode(slide,'PLUGIN 2  ·  Alfresco',9.57,4.60,2.77,.72,'E6F5ED',C.navy,13.0);
   boxNode(slide,'CORE  ·  SSO  |  email  |  PDF  |  report',6.58,5.43,5.76,.52,'EDF3F8',C.navy,11.2);
   addText(slide,'Moduli attuali · ulteriori plugin estendibili in futuro', {x:6.70,y:6.15,w:5.54,h:.26,fontSize:10.0,color:C.teal,bold:true,align:'center',margin:0});
 }else{
   const items=[['STEP','EAF3F9'],['CONDIZIONI','E9F4F4'],['VERIFICHE','EBF5ED']];
   items.forEach(([label,color],i)=>{
     const xx=6.59+i*1.96;
     boxNode(slide,label,xx,4.60,1.65,.59,color,C.navy,11.0);
     if(i!==2)arrow(slide,xx+1.70,4.74,.22,'right',accent);
   });
   boxNode(slide,'Campi obbligatori  ·  scadenze  ·  reminder pianificati',6.67,5.55,5.54,.63,'EDF3F8',C.navy,11.0);
   addText(slide,'Regole operative configurabili da super admin e admin autorizzati', {x:6.63,y:6.38,w:5.68,h:.18,fontSize:9.2,color:C.teal,italic:true,align:'center',margin:0});
 }
}
function focusedCiPanel(slide,d,accent){
 // Use authentic DOM-region screenshots from the current CI only. For offline
 // editorial export, diagrams/archived evidence are explicitly labelled.
 const shot=realUiImage(d);
 const x=5.72, w=6.97;
 rect(slide,x,1.48,w,5.22,C.white,C.line);
 if(d.index===59){
   const avatar=path.join(root,'app/static/ai-chatbot/albot-avatar.png');
   if(!fs.existsSync(avatar))throw new Error('AlBot original avatar missing');
   slide.addImage({path:avatar,...imageSizingContain(avatar,x+.23,1.80,1.43,1.43)});
   addText(slide,'AlBot · anche «Alex»\nAssistente AI di CIR',
     {x:x+1.85,y:1.97,w:4.72,h:1.00,fontSize:17.3,bold:true,color:C.navy,margin:0,fit:'shrink'});
   if(shot){
     slide.addImage({path:shot.path,...imageSizingContain(shot.path,x+.45,3.40,6.12,2.79)});
   }else{
     boxNode(slide,'Pannello conversazione AlBot: cattura reale richiesta alla CI',
       x+.41,3.81,6.15,1.14,'E9F3F9',C.navy,13);
   }
 }else if(shot){
   const above=d.index===56?'STATISTICHE / GRAFICI REALI':'WORKFLOW / CARD E FRECCE';
   addText(slide,above,{x:x+.2,y:1.70,w:w-.4,h:.28,fontSize:11.3,bold:true,color:C.teal,align:'center',margin:0});
   slide.addImage({path:shot.path,...imageSizingContain(shot.path,x+.18,2.06,w-.36,4.05)});
 }else{
   visual(slide,d,accent);
   addText(slide,'Illustrazione editoriale · la screenshot reale sarà integrata dalla CI',
      {x:x+.21,y:6.27,w:w-.42,h:.26,fontSize:9.2,color:C.muted,align:'center',margin:0});
 }
 return;
}
function rightPanel(slide,d,accent){
 if([46,56,59].includes(d.index))return focusedCiPanel(slide,d,accent);
 rect(slide,6.27,1.46,6.47,5.32,C.white,C.line);
 if(d.arch_visual){modularArchitecturePanel(slide,d,accent);return;}
 if(d.training_flow){incidentTrainingRight(slide,d,accent);return;}
 // Slide 70 documents tenant-specific category/data-type choices. In a CI
 // build, the authenticated browser capture MUST take precedence over the
 // editorial photo. Otherwise an attractive fallback silently hides evidence
 // from this run and the deck fails its mandatory screenshot provenance gate.
 const categoryPalette=realUiImage(d);
 // A dedicated laboratory slide makes the association rule legible: the
 // first selected category chooses the workflow, regardless of manual entry
 // or template pre-fill. Browser evidence is used only if verified this run.
 if(d.index===62){
   const categoryShot=ciById.get('spam-incident-config-labels');
   const incidentShot=ciById.get('spam-incident-desktop');
   const source=categoryShot||incidentShot||path.join(root,'docs/presentation/visual_rc57_media/3b344311551e0fc2.jpg');
   rect(slide,6.47,1.66,6.08,3.49,'F6F9FA',C.line);
   slide.addImage({path:source,...imageSizingContain(source,6.55,1.74,5.91,3.29)});
   addText(slide,categoryShot?'CATEGORIE REALI · CATTURA CI DELLA BUILD':
     (incidentShot?'INCIDENTE REALE · CATTURA CI':'ESEMPIO CIR · SCHERMATA EDITORIALE'),
     {x:6.56,y:5.19,w:5.86,h:.22,fontSize:8.3,bold:true,color:C.teal,align:'center',margin:0});
   boxNode(slide,'1ª CATEGORIA\nSPAM',6.68,5.53,2.33,.69,'E5F0F9',C.navy,13);
   arrow(slide,9.18,5.70,.45,'right',accent);
   boxNode(slide,'WORKFLOW\nSPAM',9.78,5.53,2.32,.69,'E6F5EB',C.navy,13);
   addText(slide,'Altre categorie: classificano il caso, non sommano nuovi workflow.',
     {x:6.64,y:6.46,w:5.78,h:.29,fontSize:9.7,color:C.muted,align:'center',margin:0});
   return;
 }
 if(d.index===33){
   const wizard=realUiImage(d);
   if(wizard?.id==='tenant-setup-wizard-panel'){
     rect(slide,6.43,1.67,6.15,4.92,'F6F9FA');
     slide.addImage({path:wizard.path,...imageSizingContain(wizard.path,6.55,1.77,5.91,4.70)});
     addText(slide,'WIZARD INIZIALE DEL TENANT · CATTURA CI VERIFICATA',
       {x:6.59,y:6.51,w:5.83,h:.23,fontSize:8.2,bold:true,color:C.teal,align:'center',margin:0});
   }else{
     photoPanel(slide,d);
     addText(slide,'Vista reale del Wizard integrata dalla CI dopo la cattura autenticata',
       {x:6.49,y:6.46,w:5.97,h:.27,fontSize:8.8,color:C.muted,align:'center',margin:0});
   }
   return;
 }
 if(d.index===70 && categoryPalette?.id==='spam-incident-config-labels'){
   rect(slide,6.48,1.67,6.04,4.91,'F6F9FA');
   slide.addImage({path:categoryPalette.path,
      ...imageSizingContain(categoryPalette.path,6.55,1.77,5.90,4.64)});
   addText(slide,'CATEGORIE E DATI INTERESSATI · SCHERMATA CI AUTENTICA',
      {x:6.62,y:6.52,w:5.72,h:.20,fontSize:8.0,bold:true,color:C.teal,
       align:'center',margin:0});
   return;
 }
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
 if(src||real){const img=real?real.path:imagePath(src);const wide=Boolean(real && !d.report_pages);
   const ix=wide?5.85:6.52,iw=wide?6.72:5.99;
   rect(slide,ix,1.80,iw,4.48,'F6F9FA');slide.addImage({path:img,...imageSizingContain(img,ix+.02,1.83,iw-.04,4.37)});
   addText(slide,ciScreen?'SCHERMATA CI / DATI DI PROVA':'VISUAL ORIGINALE CIR',{x:ix+.02,y:6.43,w:iw-.06,h:.24,fontSize:8.7,bold:true,color:C.teal,align:'center',margin:0});}
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
   const titles=/diritti|garante|rischi/.test(title)?['Valutazione\ndei rischi','Rischi\npresenti','Valuta\nGarante','Valuta\ninteressati']: /chiusura/.test(title)?['Azioni\ncompletate','global_check','close_without\n_warnings','Chiusura']:['Apertura','Analisi','Azioni','Verifica','Chiusura'];
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
 const screenshotWide=Boolean(realUiImage(d) && !d.photo_art && !d.training_flow && !d.arch_visual && !d.report_pages && ![11,12,21,55,70].includes(d.original));
 const bullets=safeBullets(d);let count=bullets.length;let baseY=1.51;
 const blockH=d.index===30?1.44:(count===5?.91:1.14);const g=d.index===30?.22:(count===5?.15:.12);if(d.index===30)baseY=1.61;
 bullets.forEach((b,i)=>{
   const focused=screenshotWide || [46,56,59].includes(d.index);
   const yy=baseY+i*(blockH+g);rect(slide,.70,yy,focused?4.76:5.29,blockH,C.white,C.line);rect(slide,.70,yy,.08,blockH,accent);
   const tc= focused?(b.length>122?11.35:b.length>100?11.9:12.35):(b.length>122?12.3:b.length>105?12.8:b.length>85?13.4:14.3);
   const url=b.match(/https?:\/\/[^\s]+/);
   const manualUrl=b.match(/(?:github\.com\/desalvo\/cybersecurity-incident-registry\/blob\/main\/docs\/[^\s]+)/);
   const linkUrl=url?url[0]:(manualUrl?'https://'+manualUrl[0]:null);
   addText(slide,b,{x:.94,y:yy+.08,w:focused?4.29:4.86,h:blockH-.15,fontSize:tc,color:C.ink,breakLine:false,margin:0,fit:'shrink',valign:'mid',lineSpacingMultiple:1.01,...(linkUrl?{hyperlink:{url:linkUrl},underline:{color:C.teal}}:{})});
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
 addText(slide,'CIR',{x:.98,y:2.29,w:3.00,h:1.55,fontSize:90,bold:true,color:'FFFFFF',margin:0});
 addText(slide,'Cybersecurity\nIncident Registry',{x:4.16,y:2.62,w:7.35,h:1.04,fontSize:31.0,bold:true,color:'F8C66A',margin:0,breakLine:false,fit:'shrink',valign:'mid'});
 addText(slide,'Gestione degli incidenti e dei workflow procedurali',{x:1.01,y:4.18,w:10.95,h:.88,fontSize:28,bold:true,color:'FFFFFF',margin:0,fit:'shrink'});
 addText(slide,'Corso didattico · interfaccia reale · laboratorio didattico di esempio',{x:1.04,y:5.28,w:10.9,h:.38,fontSize:17.1,color:'D7F4FC',margin:0});
 rect(slide,1.02,6.30,11.24,.45,C.white);addText(slide,`VERSIONE 0.10.0-1     |     RC77     |     SCHERMATE CI ${ciCommit.slice(0,8)} / BUILD ${ciBuild}`,{x:1.21,y:6.41,w:10.92,h:.21,fontSize:10.6,color:C.navy,bold:true,margin:0});notes(slide,d);
}
data.forEach((d,i)=>{let slide=pptx.addSlide();const n=i+1;if(d.kind==='cover')makeCover(slide,d,n);else if(d.kind==='chapter')makeChapter(slide,d,n);else makeContent(slide,d,n)});
// This appendix is authored only from the verified, same-run browser manifest.
// Every captured screenshot gets a visible, full-resolution-contained slide.
// Offline editorial decks remain the 88-slide source edition and never
// pretend that local example artwork is a fresh browser capture.
if(ciManifest){
  for(const [i,row] of ciManifest.screenshots.entries()){
    const img=ciById.get(row.id);
    if(!img)throw new Error('Screenshot CI non trovata: '+row.id);
    const slide=pptx.addSlide();
    bgBase(slide,C.teal);
    addText(slide,'APPENDICE / SCREENSHOT AUTENTICHE DELLA CI',{x:.73,y:.34,w:11.9,h:.3,fontSize:10.2,bold:true,color:C.teal,margin:0});
    addText(slide,'Schermata '+String(i+1)+' / '+String(ciManifest.screenshots.length)+' — '+row.id,
      {x:.73,y:.75,w:11.9,h:.48,fontSize:22,bold:true,color:C.navy,margin:0,fit:'shrink'});
    rect(slide,.63,1.39,12.07,5.20,'FFFFFF',C.line);
    slide.addImage({path:img,...imageSizingContain(img,.76,1.48,11.81,4.98)});
    addText(slide,'Screenshot reale CIR con dati sintetici isolati · SHA-256 '+row.sha256.slice(0,20)+'…',
      {x:.80,y:6.59,w:11.8,h:.27,fontSize:10,color:C.muted,margin:0});
    footer(slide,data.length+i+1);
    slide.addNotes('Screenshot browser originale della CI; identificativo '+row.id+
      '; SHA-256 '+row.sha256+'; commit '+ciCommit+'; build '+ciBuild+'. Nessuna modifica ai pixel della cattura.');
  }
}

fs.mkdirSync(path.dirname(out),{recursive:true});pptx.writeFile({fileName:out}).then(()=>console.log('Created '+out+' slides='+(data.length+(ciManifest?.screenshots?.length||0)))).catch(e=>{console.error(e);process.exit(1)});
