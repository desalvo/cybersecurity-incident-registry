'use strict';
// CIR / teaching edition: intentionally all slide content and diagrams are editable.
const fs=require('fs');const path=require('path');const crypto=require('crypto');
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
  // Match the authored helper on CI runners: crops must not silently stretch
  // the whole screenshot when the optional slide toolbox is unavailable.
  imageSizingCrop=(file,x,y,w,h,cx,cy,cw,ch)=>{
    const {width,height}=imageSize(fs.readFileSync(file));
    const aspect=width/height, target=w/h;
    if(cx===undefined||cy===undefined||cw===undefined||ch===undefined){
      cw=aspect>=target?target/aspect:1;
      ch=aspect>=target?1:aspect/target;
      cx=(1-cw)/2;cy=(1-ch)/2;
    }
    let virtualW=w/cw,virtualH=virtualW/aspect;
    if(Math.abs(virtualH*ch-h)>1e-6){virtualH=h/ch;virtualW=virtualH*aspect;}
    return {x,y,w:virtualW,h:virtualH,
      sizing:{type:'crop',x:cx*virtualW,y:cy*virtualH,w,h}};
  };
}
const root=process.env.CIR_REPO_ROOT||path.resolve(__dirname,'..');
const locale=(process.env.CIR_TRAINING_LOCALE||'it').toLowerCase();
if(!['it','en'].includes(locale))throw new Error('Unsupported training locale: '+locale);
const english=locale==='en';
const enData=english?JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc98_english_slides.json'),'utf8')):null;
const enLabels=english?JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc98_english_labels.json'),'utf8')):null;
if(english && (enData.schema!==1 || Object.keys(enData.slides).length!==95))
 throw new Error('English training translation catalog is incomplete');
function tr(text){
 if(!english||typeof text!=='string')return text;
 if(Object.prototype.hasOwnProperty.call(enLabels,text))return enLabels[text];
 // Text boxes may contain multi-line diagram labels; translate each token
 // without changing the required structural whitespace or arrow glyphs.
 if(text.includes('\n'))return text.split('\n').map(tr).join('\n');
 if(text.includes(' | '))return text.split(' | ').map(tr).join(' | ');
 let t=text;
 // These dynamic headings are generated for the current screenshot manifest.
 t=t.replace(/^Schermata (\d+) \/ (\d+) — /,'Screenshot $1 / $2 — ');
 t=t.replace('Notifica prima dell’invio','Notification before sending').replace('Documento PDF compilato','Completed PDF document');
 t=t.replace(/^INGRANDIMENTO · /,'ZOOM · ').replace(/^CONCETTO · /,'CONCEPT · ');
 t=t.replace(/^APPENDICE \/ /,'APPENDIX / ');
 t=t.replace(/^Cattura originale CIR con dati sintetici isolati/,'Original CIR capture with isolated synthetic data');
 t=t.replace(/^Cattura storica della vera applicazione CIR/,'Historical capture from the real CIR application');
 t=t.replace(/ · CATTURA CI AUTENTICA/g,' · AUTHENTIC CI CAPTURE');
 t=t.replace(/ · EVIDENZA STORICA/g,' · HISTORICAL EVIDENCE');
 t=t.replace(/^v0\.10\.0-1 · materiale didattico RC\d+$/,'v0.10.0-1 · training material RC103');
 t=t.replace(/VERSIONE 0\.10\.0-1/g,'VERSION 0.10.0-1').replace(/EDIZIONE EDITORIALE · CATTURE STORICHE/g,'EDITORIAL EDITION · HISTORICAL CAPTURES');
 t=t.replace(/SCREENSHOT CI/g,'CI SCREENSHOTS');
 return t;
}

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
const workflowIntro=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc88_workflow_intro.json'),'utf8'));
if(workflowIntro.insert_after_original!==38 || workflowIntro.slides.length!==5 ||
   workflowIntro.slides.some((row,i)=>row.index!==90+i || row.original!==90+i ||
      !['workflow','categories','steps','conditions','dependencies'].includes(row.workflow_intro)))
  throw new Error('Missing or out-of-order workflow terminology introduction');
const supportTicketsAddendum=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc109_support_tickets_addendum.json'),'utf8'));
if(supportTicketsAddendum.insert_after_original!==59 || supportTicketsAddendum.slides.length!==1 ||
   supportTicketsAddendum.slides[0].support_tickets!==true)
 throw new Error('Missing RC109 Support Tickets instructional slide');
const albotWorkflowAddendum=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/visual_rc105_albot_workflow_addendum.json'),'utf8'));
if(albotWorkflowAddendum.insert_after_original!==60 || albotWorkflowAddendum.slides.length!==1 ||
   albotWorkflowAddendum.slides[0].albot_workflow_authoring!==true)
 throw new Error('Missing RC105 workflow-authoring teaching slide');
const data=[];
for(const item of originalData){
 data.push(item);
 if(item.index===6){
  data.push(...archAddendum.slides);
  data.push({index:89,original:89,kind:'content',tag:'01 / ARCHITETTURA · ALERT',
    title:'Alert, scadenze e promemoria operativi',alert_architecture:true,
    bullets:[
      'Incidenti aperti: avvisi e riepiloghi periodici per mantenere visibili i casi da trattare; i digest generali sono un’estensione configurabile.',
      'Step incompleti: task obbligatori, prerequisiti, scadenze e promemoria automatici tramite scheduler.',
      'Promemoria personalizzati: scadenze specifiche per singolo incidente, invii programmati e storico degli esiti.',
      'Stato del sistema: errori scheduler, avvisi sui processi e anomalie critiche consultabili da amministratori autorizzati.'
    ],
    notes:'Distinguere le funzioni esistenti (avvisi procedurali, scadenze dei task, promemoria per incidente, stato scheduler) da una possibile estensione futura: un digest periodico unico degli incidenti aperti. Scheduler: deduplicazione per slot e stato inviato/errore. Le notifiche e i dettagli restano soggetti a permessi e tenant. Fonti: app/templates/notification_settings.html, app/templates/admin_status.html, app/routes.py, app/models.py.'});
 }

 if(item.index===14)data.push(...addendum.slides);
 if(item.index===38)data.push(...workflowIntro.slides);
 if(item.index===59){data.push(...albotWorkflowAddendum.slides);data.push(...supportTicketsAddendum.slides);}
}
const CONTENT_SLIDES=96;
const THANK_YOU_SLIDES=1;
const APPENDIX_BANNER_SLIDES=1;
const APPENDIX_PREVIEWS=2;
const BASE_SLIDES=CONTENT_SLIDES+THANK_YOU_SLIDES+APPENDIX_BANNER_SLIDES+APPENDIX_PREVIEWS;
const GALLERY_FIRST_SLIDE=CONTENT_SLIDES+THANK_YOU_SLIDES+APPENDIX_BANNER_SLIDES+1;
const HIDDEN_GALLERY_IDS=new Set(['classic-registry-desktop']);
const MANDATORY_GALLERY_IDS=new Set(['pdf-generated-preview','notification-preview']);
const ARCHIVED_GALLERY_ROOT=path.join(root,'app/static/help/ui-runtime');
// The editorial edition cannot claim same-run CI provenance. It still retains
// ALL legacy application captures (except classic UI), explicitly marked as
// historical evidence, so the gallery does not disappear between builds.
const ARCHIVED_GALLERY=fs.existsSync(ARCHIVED_GALLERY_ROOT)?
 fs.readdirSync(ARCHIVED_GALLERY_ROOT).filter(name=>/^[a-z0-9-]+\.(?:png|jpg)$/i.test(name) &&
 !HIDDEN_GALLERY_IDS.has(path.parse(name).name)).sort().map(name=>({
 id:path.parse(name).name,file:name,path:path.join(ARCHIVED_GALLERY_ROOT,name),archived:true
 })):[];

if(data.length!==CONTENT_SLIDES)throw new Error('Expected 96 instructional slides');
// ITALIAN MASTER RULE: the English deck has NO independent slide structure.
// Derive slide order, all images, and the original content from the Italian
// specifications. A per-slide fingerprint invalidates any stale translation
// whenever its Italian original changes. New Italian slides must first be
// added to the master and then translated before an EN build can succeed.
function italianMasterFingerprint(d){
 const source={kind:d.kind,index:d.index,original:d.original??null,
   title:d.title,bullets:d.bullets||[],notes:d.notes||''};
 return crypto.createHash('sha256').update(JSON.stringify(source)).digest('hex');
}
const italianFingerprints=Object.fromEntries(data.map((d,i)=>[String(i+1),italianMasterFingerprint(d)]));
if(process.env.CIR_DUMP_ITALIAN_MASTER_FINGERPRINTS==='1'){
 process.stdout.write(JSON.stringify(italianFingerprints,null,2)+'\n');
 process.exit(0);
}
if(english){
 if(enData.source_locale!=='it' || enData.schema!==1 ||
    !enData.italian_master_fingerprints)
  throw new Error('English translation must derive from a pinned Italian master');
 for(const [page,fingerprint] of Object.entries(italianFingerprints)){
  if(enData.italian_master_fingerprints[page]!==fingerprint)
   throw new Error('Italian master slide '+page+' has changed: update its English translation first');
 }
 if(Object.keys(enData.italian_master_fingerprints).length!==CONTENT_SLIDES)
  throw new Error('English translations do not cover the full Italian master');
}
if(english){
 for(let i=0;i<data.length;i++){
  const d=data[i], page=i+1;
  if(page===1)continue; // Cover text and notes are localized in the builder.
  const values=enData.slides[String(page)];
  if(!values)throw new Error('English slide translation missing for '+page);
  if(d.kind==='chapter'){
   d.title=String(d.title).split(' / ')[0]+' / '+values[0];
  }else{
   if(values.length!==1+(d.bullets||[]).length)
    throw new Error('English slide bullet count mismatch at '+page);
   d.title=values[0];
   d.bullets=values.slice(1);
  }
  // The English deck has full English notes; original screenshot references
  // remain in the provenance section, never translated or modified.
  d.notes=[d.title,...(d.bullets||[])].join('\n');
 }
}

for (const d of data) for(const media of (d.images||[])){
 const filename=String(media.file||'');
 if(!/^docs\/presentation\/visual_rc57_media\/[A-Za-z0-9._-]+$/.test(filename))throw new Error('External media disallowed: '+filename);
}
// Optional verified screenshot overlay: the CI's browser artifact is the only
// authoritative source for images that did not exist in the preceding run.
const manifestPath=process.env.CIR_SCREENSHOT_MANIFEST||null;
let ciManifest=null,ciById=new Map(), generatedPdfPreview=null;
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
if(ciManifest?.generated_pdf_preview){
 const record=ciManifest.generated_pdf_preview;
 const base=path.resolve(path.dirname(manifestPath))+path.sep;
 const pdf=path.resolve(path.dirname(manifestPath),String(record.pdf_file||''));
 const png=path.resolve(path.dirname(manifestPath),String(record.png_file||''));
 if(!pdf.startsWith(base)||!png.startsWith(base))throw new Error('PDF evidence path traversal');
 const sha=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
 if(!fs.readFileSync(pdf).subarray(0,5).equals(Buffer.from('%PDF-')) ||
    sha(pdf)!==record.pdf_sha256 || sha(png)!==record.png_sha256 ||
    record.source_kind!=='cir-generated-mapped-acroform')
      throw new Error('PDF generated preview provenance mismatch');
 generatedPdfPreview={path:png,pdf,record};
}
if(ciManifest && process.env.GITHUB_SHA && ciManifest.source_commit!==process.env.GITHUB_SHA)
  throw new Error('Screenshot di un commit diverso dalla build CI');
if(ciManifest && process.env.CIR_RELEASE_BUILD && ciManifest.build!==process.env.CIR_RELEASE_BUILD)
  throw new Error('Screenshot con build diversa dalla build CI');
if(process.env.CIR_REQUIRE_REAL_SCREENSHOTS==='1'){
  if(!ciManifest)throw new Error('Il manifest browser e obbligatorio nella CI');
  if(!generatedPdfPreview)throw new Error('Il PDF generato dall app e obbligatorio nella CI');
  if(ciManifest.source_kind!=='real-application-browser' || ciManifest.data_provenance!=='isolated-synthetic-fixture')
    throw new Error('La CI richiede evidenza browser reale su dati sintetici isolati');
  const required=['notification-preview','tenant-wizard-next-step','registry-closed-state','pdf-mapping-configuration','pdf-generated-preview',
    'alfresco-settings-desktop','alfresco-incident-documents',
    'spam-incident-config-labels','tenant-setup-wizard-desktop',
    'tenant-setup-wizard-panel'];
  const missing=required.filter(id=>!ciById.has(id));
  for (const ident of MANDATORY_GALLERY_IDS) {
    if(!ciManifest.screenshots.some(row=>row.id===ident))
      throw new Error('Gallery lacks authentic required preview: '+ident);
  }
  if(ciManifest.screenshots.some(row=>row.id==='classic-registry-desktop') &&
     !HIDDEN_GALLERY_IDS.has('classic-registry-desktop'))
    throw new Error('Classic UI cannot enter the teaching gallery');

  if(missing.length)throw new Error('Mancano screenshot autentici: '+missing.join(', '));
}
// Approved, anonymized example supplied for the training slides.
// It is NOT a screenshot produced by CIR or by the CI browser.
const USER_DOC_PREVIEW=path.join(root,'docs/presentation/rc95_user_supplied/data_breach_notification_anonymized.png');
const USER_DOC_SHA256='17898ab5874ae15ded91a0c8f2d022402eac9f6c5d212bd72b24dd213965a9ce';
if(!fs.existsSync(USER_DOC_PREVIEW) || crypto.createHash('sha256').update(fs.readFileSync(USER_DOC_PREVIEW)).digest('hex')!==USER_DOC_SHA256)
  throw new Error('Approved anonymized document image missing or changed');
const ciCommit=ciManifest?.source_commit||'919b027403ee55db05b2355cd2f8fbd09c7cf7b4';
const ciBuild=ciManifest?.build||'20261124';
const GALLERY_ITEMS=ciManifest?ciManifest.screenshots.filter(row=>!HIDDEN_GALLERY_IDS.has(row.id)).map(row=>({...row,path:ciById.get(row.id),archived:false})):
 ARCHIVED_GALLERY.map(row=>({...row,sha256:crypto.createHash('sha256').update(fs.readFileSync(row.path)).digest('hex')}));
const FINAL_SLIDES=BASE_SLIDES+GALLERY_ITEMS.length;

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
// Offline editorial images were checked into the application help area by
// earlier work. They are NOT evidence for the current source commit; they
// provide visible, honest examples of what the same-run CI callouts look like.
const ARCHIVED_UI={
 'login-desktop':'login-desktop.png','login-mobile':'login-mobile.png',
 'registry-desktop':'registry-desktop.png','registry-mobile':'registry-mobile.png',
 'incident-desktop':'incident-desktop.png','spam-incident-desktop':'spam-incident-desktop.png',
 'spam-workflow-steps':'spam-workflow-steps.png','workflow-steps-focused':'spam-workflow-steps.png',
 'spam-incident-config-labels':'spam-workflow-steps.png',
 'admin-sso-desktop':'admin-sso-desktop.png','admin-modules-desktop':'admin-modules-desktop.png',
 'assistant-panel-closeup':'assistant-desktop.png','assistant-mobile':'assistant-mobile.png',
 'documentation-admin-desktop':'documentation-admin-desktop.png'
};
function realUiImage(d){
 const id=d.kind==='preview'?'pdf-generated-preview':ciViewByOldSlide[d.original];
 if(!id)return null;
 if(ciManifest)return ciById.has(id)?{id,path:ciById.get(id),verified:true}:null;
 const name=ARCHIVED_UI[id];
 if(!name)return null;
 const file=path.join(root,'app/static/help/ui-runtime',name);
 return fs.existsSync(file)?{id,path:file,archived:true}:null;
}
const pptx=new pptxgen();pptx.layout='LAYOUT_WIDE';pptx.author='CIR - Cybersecurity Incident Registry';pptx.subject='CIR | Laboratorio e documentazione utente, amministratore e governance';pptx.title=english?'CIR — Operational Training RC103 (English)':'CIR — Presentazione didattica RC103';pptx.company='Cybersecurity Incident Registry';pptx.lang=english?'en-US':'it-IT';pptx.theme={headFontFace:'Arial',bodyFontFace:'Arial',lang:english?'en-US':'it-IT'};
const W=13.33333,H=7.5;
const C={bg:'F4F8FA',white:'FFFFFF',navy:'12324A',muted:'60798A',cyan:'00A8BE',teal:'147E8F',blue:'326C92',violet:'6264A3',green:'23896B',gold:'F6A23A',pink:'D46C75',line:'D9E5EB',ink:'143044',shadow:'EDF3F6',pale:'EAF6F8'};
// RC97: all nine original illustrations are pinned by SHA-256, including the
// closing thank-you artwork. They are never classified as application captures.
const cartoonProvenance=JSON.parse(fs.readFileSync(path.join(root,english?'docs/presentation/rc99_cartoon_en/provenance.json':'docs/presentation/rc97_cartoon/provenance.json'),'utf8'));
const canonicalCartoonProvenance=JSON.parse(fs.readFileSync(path.join(root,'docs/presentation/rc97_cartoon/provenance.json'),'utf8'));
const canonicalCartoons=new Map(canonicalCartoonProvenance.artwork.map(r=>[r.section,r]));
const cartoonRecords=new Map();
if(cartoonProvenance.artwork?.length!==9)throw new Error('Incomplete eight banners and final thank-you artwork');
for(const row of cartoonProvenance.artwork){
 const f=path.join(root,row.file);
 if(!row.file.startsWith(english?'docs/presentation/rc99_cartoon_en/':'docs/presentation/rc97_cartoon/') || row.real_people!==false ||
    row.contains_real_ui!==false || !fs.existsSync(f) ||
    crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')!==row.sha256)
    throw new Error('Unapproved or altered cartoon artwork: '+row.section);
  if(english){const original=canonicalCartoons.get(row.section);
    if(!original||row.source_sha256!==original.sha256||
       crypto.createHash('sha256').update(fs.readFileSync(path.join(root,original.file))).digest('hex')!==row.source_sha256)
      throw new Error('English cartoon is stale relative to the Italian master: '+row.section);}
 cartoonRecords.set(row.section,{path:f,sha256:row.sha256});
}
function cartoonFor(section){
 const record=cartoonRecords.get(section);
 if(!record)throw new Error('Missing approved artwork for section '+section);
 return record;
}
function rgb(hex){return '#'+hex;}
function addText(slide,t,o){slide.addText(tr(t),{fontFace:'Arial',...o})}
function rect(slide,x,y,w,h,fill,line=null,r=0.13){slide.addShape(pptx.ShapeType.roundRect,{x,y,w,h,rectRadius:r,rotate:0,line:{color:line||fill,width:line?0.65:0},fill:{color:fill},radius:r})}
function line(slide,x,y,w,h,color=C.line,width=1){slide.addShape(pptx.ShapeType.line,{x,y,w,h,line:{color,width}})}
function ellipse(slide,x,y,w,h,color){slide.addShape(pptx.ShapeType.ellipse,{x,y,w,h,line:{color,width:0},fill:{color}})}
function arrow(slide,x,y,w,dir='right',color=C.cyan){slide.addShape(pptx.ShapeType.chevron,{x,y,w,h:0.34,flipH:dir==='left',line:{color,width:0},fill:{color}})}
function imagePath(im){if(!im)return null;let f=path.basename(im.file||'');return path.join(root,'docs/presentation/visual_rc57_media',f)}
function notes(slide,d){
 if(english){
  const ids=(d.images||[]).map(x=>x.file).filter(Boolean);
  const real=realUiImage(d);
  let lines=[d.title||'CIR operational training',...(d.bullets||[])];
  lines.push('This presentation is a training resource; application captures use isolated synthetic data.');
  lines.push('[Sources]');
  if(real) lines.push('Application screenshot: '+real.id+'; archived='+!!real.archived+'.');
  if(ciManifest)lines.push('Same-run browser screenshot manifest; source commit '+ciCommit+'; build '+ciBuild+'.');
  else lines.push('Offline editorial version; screenshots are historical, not from the current CI run.');
  if(d.support_tickets)lines.push('Original synthetic 3D artwork: docs/presentation/rc109_support_tickets_art.png. Not a screenshot.');
  if(d.kind==='preview')lines.push('Approved anonymized document sample: docs/presentation/rc95_user_supplied/data_breach_notification_anonymized.png; SHA-256 '+USER_DOC_SHA256+'.');
  if(ids.length)lines.push('Supporting CIR artwork: '+ids.join('; ')+'.');
  lines.push('Source code: CIR version 0.10.0-1, English training edition RC109.');
  slide.addNotes(lines.join('\n'));
  return;
 }

 let n=(d.notes||'').replace(/\r/g,'');
 n+='\n\n[Sources]\n';
 const paletteCI=d.index===70 && realUiImage(d)?.id==='spam-incident-config-labels';
 const wizardCI=d.index===33 && realUiImage(d)?.id==='tenant-setup-wizard-panel';
 const labCategoryCI=d.index===62 && ciById.has('spam-incident-config-labels');
 const ids = labCategoryCI?['spam-incident-config-labels']:(wizardCI?['tenant-setup-wizard-panel']:(paletteCI?['spam-incident-config-labels']:(d.photo_art?[]:(d.original===56 && ciById.has('alfresco-incident-documents')
   ? ['alfresco-settings-desktop','alfresco-incident-documents']
   : (realUiImage(d)?[realUiImage(d).id]:[])))));
 if(d.kind==='preview')n+='Documento di esempio anonimizzato approvato, fornito per fini didattici: docs/presentation/rc95_user_supplied/data_breach_notification_anonymized.png. Non e una screenshot della CI; SHA-256 '+USER_DOC_SHA256+'.\n';
 if(d.arch_visual)n+='Illustrazione sintetica originale e diagramma nativo PowerPoint, senza persone, senza testo incorporato. Immagine verificata SHA-256.\n';
 if(d.support_tickets)n+='Illustrazione sintetica 3D: docs/presentation/rc109_support_tickets_art.png, non screenshot della CI.\n';
 if(d.index===59)n+='Avatar AlBot ufficiale dell applicazione: app/static/ai-chatbot/albot-avatar.png.\n';
 if(d.photo_art && !ids.length)n+='Immagine sintetica fotografica originale, senza persone reali, senza titolo e footer; non e una schermata dell applicazione.\n';

 if([27,61].includes(d.index))n+='Sfondo sintetico originale senza persone, nessuna foto stock.\n';
 if(d.report_pages)n+='Pagine di report dimostrativo sintetico; non si tratta di un export dall app.\n';
 if(d.training_flow==='incident-entry' && ciById.has('registry-desktop'))
   n+='Schermata autentica CIR catturata dal browser della build corrente: registry-desktop.\n';
 if(d.training_flow && d.training_flow!=='incident-entry')
   n+='Schemi didattici originali con forme PowerPoint modificabili.\n';
 if(ids.length && ciManifest){
   n+='Schermata/e autentica/e CIR della CI corrente '+ciCommit+': '+ids.join(', ')+'. Manifest Chromium vincolato tramite SHA-256.\n';
 }else if(realUiImage(d)?.archived){
   n+='Schermata storica dell interfaccia CIR inclusa nell applicazione, non attestata come cattura della CI corrente.\n';
 }else if((d.images||[]).length){
   n+='Media editoriale della precedente presentazione CIR, derivato da evidenze CI con dati fittizi. Nessuna cattura attuale rivendicata.\n';
 }
 n+='Sorgente CIR 0.10.0-1 RC105. I dati sono di esempio; diagrammi e schemi non rappresentano screenshot dell’applicazione.\n';
 if(!ciManifest)n+='Edizione editoriale offline: nessuna attestazione di catture dalla CI corrente.\n';
 slide.addNotes(n);
}
function footer(slide,n){line(slide,.62,7.04,12.1,0,C.line,.7);addText(slide,'CIR - Cybersecurity Incident Registry',{x:.72,y:7.1,w:7.7,h:.18,fontSize:7.6,bold:true,color:C.muted,margin:0});addText(slide,english?'v0.10.0-1 · training material RC109':'v0.10.0-1 · materiale didattico RC109',{x:8.05,y:7.10,w:3.35,h:.18,fontSize:7.2,color:C.muted,align:'right',margin:0});addText(slide,`${n} / ${BASE_SLIDES + GALLERY_ITEMS.length}`,{x:11.61,y:7.1,w:1.0,h:.18,fontSize:8.2,bold:true,color:C.teal,align:'right',margin:0});}
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
function addArchitectureLabels(slide){
 // Native editable labels annotate the conceptual objects, not the art pixels.
 const labels=[
  ['DB / dati',6.82,2.52,1.20],['SSO / MFA',8.16,1.78,1.18],
  ['Workflow',9.55,2.53,1.16],['PDF',11.13,2.14,.80],
  ['Plugin AI',6.93,3.44,1.15],['Container',7.09,4.45,1.05],
  ['Kubernetes',8.38,4.45,1.31],['Linux',9.91,4.45,.83],
  ['Cloud / storage',10.79,4.45,1.63]
 ];
 for(const [label,x,y,w] of labels){
   rect(slide,x,y,w,.25,'F3FBFE','247E98',.06);
   addText(slide,label,{x:x+.025,y:y+.038,w:w-.05,h:.17,fontSize:8.1,bold:true,color:C.navy,align:'center',margin:0,fit:'shrink'});
 }
}
function alertArchitecturePanel(slide,d,accent){
 const x=6.52;
 const blocks=[
   ['INCIDENTI APERTI','Elenco e solleciti periodici*','E7F2FA'],
   ['STEP / DEADLINE','Azioni mancanti, scadenze e condizioni','FFF3DD'],
   ['REMINDER PER INCIDENTE','Promemoria puntuali e personalizzati','E5F5ED'],
   ['STATO SISTEMA','Warning, errori scheduler e anomalie','F5EBF0']
 ];
 blocks.forEach(([a,b,fill],i)=>{
  const yy=1.69+i*1.11;
  rect(slide,x,yy,5.86,.90,fill,C.line);
  addText(slide,a,{x:x+.16,y:yy+.12,w:5.45,h:.24,fontSize:13.4,bold:true,color:C.navy,margin:0});
  addText(slide,b,{x:x+.16,y:yy+.46,w:5.47,h:.22,fontSize:10.9,color:C.muted,margin:0});
 });
 addText(slide,'*Il digest riepilogativo degli aperti è un’estensione possibile, non una funzione già disponibile.',
   {x:x+.04,y:6.25,w:5.75,h:.34,fontSize:9.4,italic:true,color:C.teal,margin:0,fit:'shrink'});
}
function modularArchitecturePanel(slide,d,accent){
 const row=modularArtByKind.get(d.arch_visual);
 if(!row || row.real_people!==false || row.contains_embedded_slide_chrome!==false)throw new Error('Untrusted modular artwork');
 const img=path.join(root,row.file);
 if(!fs.existsSync(img) || crypto.createHash('sha256').update(fs.readFileSync(img)).digest('hex')!==row.sha256)
    throw new Error('Modular artwork SHA-256 mismatch');
 slide.addImage({path:img,...imageSizingContain(img,6.43,1.55,6.14,d.arch_visual==='ecosystem'?3.52:2.74)});
 if(d.arch_visual==='ecosystem')addArchitectureLabels(slide);
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

// The source is an unmodified, SHA-256 verified image from the SAME CI manifest.
// The zoom is a native PowerPoint crop of the same embedded image. No invented UI.
// Focus ROIs are FULL-content regions of the original screenshot, not an aspect-ratio
// squeeze. Native PowerPoint crops preserve screenshot bytes and source provenance.
const CI_FOCUS={
 'login-desktop':[.53,.16,.43,.66,'Form di login completo'],
 'login-mobile':[.02,.10,.96,.48,'Form di autenticazione mobile'],
 'registry-desktop':[.13,.27,.84,.57,'Righe e comandi del registro'],
 'registry-closed-state':[.12,.29,.85,.54,'Stati e righe degli incidenti'],
 'registry-mobile':[.02,.13,.96,.42,'Ricerca e filtri su mobile'],
 'admin-sso-desktop':[.16,.12,.80,.51,'Profili SSO e campi di configurazione'],
 'admin-modules-desktop':[.16,.11,.81,.61,'Template e moduli PDF'],
 'incident-desktop':[.13,.15,.81,.65,'Dati e azioni incidente'],
 'pdf-mapping-configuration':[.05,.07,.91,.85,'Campi e associazioni PDF'],
 'alfresco-settings-desktop':[.17,.08,.79,.74,'Campi integrazione Alfresco'],
 'assistant-panel-closeup':[.03,.19,.94,.67,'Messaggi della chat AlBot'],
 'spam-incident-config-labels':[.03,.10,.94,.78,'Categorie e dati interessati'],
 'workflow-steps-focused':[.01,.03,.97,.87,'Step, frecce e pulsanti'],
 'statistics-desktop':[.03,.06,.94,.86,'Grafici e indicatori'],
 'spam-workflow-steps':[.03,.04,.93,.29,'Primi step del workflow'],
 'tenant-setup-wizard-panel':[.04,.08,.92,.83,'Campi e comandi del wizard']
};
const CI_FOCUS_PER_SLIDE={
 // Original slide numbers, invariant when new architecture slide is inserted.
 8:[.55,.19,.42,.60,'Username, password e accesso'],
 10:[.18,.11,.79,.53,'Provider, Client ID e impostazioni SSO'],
 11:[.15,.36,.82,.48,'Righe degli incidenti e icone di stato'],
 12:[.15,.36,.82,.48,'Righe degli incidenti aperti e chiusi'],
 13:[.02,.13,.96,.41,'Campo di ricerca e filtri mobile'],
 36:[.17,.10,.79,.66,'Campi della configurazione dei moduli'],
 37:[.17,.10,.79,.60,'Parametri SSO della form'],
 38:[.68,.015,.31,.14,'Nome e selettore del tenant attivo'],
 39:[.17,.10,.79,.59,'Form SSO e associazione identità'],
 52:[.16,.08,.80,.73,'Database, template e campi PDF'],
 53:[.04,.08,.92,.81,'Associazione campi e sorgenti'],
 54:[.04,.12,.92,.78,'Campi database e mapping PDF'],
 56:[.15,.07,.82,.79,'Endpoint e configurazione Alfresco'],
 60:[.02,.17,.95,.68,'Conversazione e risposta dell’assistente AlBot'],
 71:[.02,.10,.95,.82,'Categorie, dati interessati e selezioni']
};
function imageRatio(file){
 const {imageSize}=require('image-size');
 const sz=imageSize(fs.readFileSync(file));
 return sz.width/sz.height;
}
function addCiZoom(slide,shot,override=null,d=null){
 const [cx,cy,cw,ch,label]=override||(d&&CI_FOCUS_PER_SLIDE[d.original])||CI_FOCUS[shot.id]||[.10,.15,.80,.65,'Dettaglio operativo'];
 if([cx,cy,cw,ch].some(v=>!Number.isFinite(v)||v<0||v>1)||cx+cw>1.00001||cy+ch>1.00001||cw<.05||ch<.05)
   throw new Error('Invalid CI screenshot focus: '+shot.id);
 const bx=6.44,bw=6.12;
 rect(slide,bx,1.56,bw,5.09,C.white,C.line);
 addText(slide,shot.archived?'SCHERMATA COMPLETA · EVIDENZA STORICA':'SCHERMATA COMPLETA · CATTURA CI AUTENTICA',
   {x:bx+.17,y:1.65,w:bw-.34,h:.24,fontSize:9,bold:true,color:C.teal,margin:0});
 const p=imageSizingContain(shot.path,bx+.22,1.97,bw-.44,2.03);
 slide.addImage({path:shot.path,...p});
 // The outlined ROI and actual zoom use exactly the same rectangle. An ROI
 // is never narrowed to fill an arbitrary wide panel (the RC83 regression).
 slide.addShape(pptx.ShapeType.rect,{x:p.x+cx*p.w,y:p.y+cy*p.h,w:cw*p.w,h:ch*p.h,
   line:{color:'D46631',width:2.2},fill:{color:C.white,transparency:100}});
 addText(slide,'INGRANDIMENTO · '+label.toUpperCase(),
   {x:bx+.17,y:4.06,w:bw-.34,h:.25,fontSize:9.7,bold:true,color:C.teal,margin:0,fit:'shrink'});
 rect(slide,bx+.18,4.35,bw-.36,2.02,'EEF5F7','D46631');
 const aspect=imageRatio(shot.path)*cw/ch;
 const maxW=bw-.46,maxH=1.91;
 const zoomW=Math.min(maxW,maxH*aspect),zoomH=zoomW/aspect;
 const zx=bx+.23+(maxW-zoomW)/2,zy=4.40+(maxH-zoomH)/2;
 slide.addImage({path:shot.path,...imageSizingCrop(shot.path,zx,zy,zoomW,zoomH,cx,cy,cw,ch)});
 const topEnd=p.y+(cy+ch)*p.h;
 line(slide,p.x+(cx+cw*.5)*p.w,topEnd,0,Math.max(.035,4.035-topEnd),'D46631',1.0);
}


// RC91: use actual screenshot-pixel crops, not an oversized canvas squeezed to
// fit the lower panel. This is essential for tall page captures (3862px SPAM).
const os=require('os'),cp=require('child_process');
const roiDirectory=fs.mkdtempSync(path.join(os.tmpdir(),'cir-verified-training-rois-'));
function trainingRoi(pathToImage,rect){
 const key=crypto.createHash('sha256').update(fs.readFileSync(pathToImage))
  .update(JSON.stringify(rect)).digest('hex');
 const destination=path.join(roiDirectory,key+'.png');
 if(!fs.existsSync(destination)){
  const scriptPath=path.join(root,'scripts/training_image_roi.py');
  const command=process.env.CIR_PYTHON||'python3';
  const result=cp.spawnSync(command,[scriptPath,pathToImage,destination,...rect.map(String)],{encoding:'utf8'});
  if(result.status!==0)throw new Error('Lossless training image crop failed: '+(result.stderr||result.stdout));
 }
 return destination;
}
function preciseCiDetail(slide,shot,type){
 const bx=6.44,bw=6.12;
 rect(slide,bx,1.52,bw,5.15,C.white,C.line);
 const dims=require('image-size').imageSize(fs.readFileSync(shot.path));
 const isTall=dims.height>dims.width*1.28;
 // Only crop actual image data: all positions refer to fractional source pixels.
 // For archived full-page evidence, the workflow cards are near the top and
 // categories are far below; CI element screenshots have a tighter viewport.
 let regions;
 if(type==='steps')regions=isTall?
    [[.16,.098,.40,.118],[.56,.098,.41,.118]]:
    [[.00,.01,.52,.83],[.47,.01,.53,.83]];
 else regions=isTall?
    [[.15,.558,.82,.108],[.15,.664,.82,.106]]:
    [[.01,.02,.98,.46],[.01,.50,.98,.48]];
 addText(slide,shot.archived?'CATTURA STORICA DELL’APPLICAZIONE':'CATTURA AUTENTICA DELL’APPLICAZIONE',
  {x:bx+.16,y:1.66,w:bw-.34,h:.23,fontSize:9.2,bold:true,color:C.teal,margin:0});
 const captions=type==='steps'?['STEP INIZIALI · CARD, FRECCE E PULSANTI','STEP SUCCESSIVI · CARD E COMANDI']:
   ['CATEGORIE DISPONIBILI E SELEZIONATE','DATI INTERESSATI E PERSONALE'];
 for(let i=0;i<2;i++){
   const y=2.02+i*2.26;
   addText(slide,captions[i],{x:bx+.22,y,w:bw-.44,h:.23,fontSize:9.6,bold:true,color:C.teal,margin:0});
   rect(slide,bx+.18,y+.28,bw-.36,1.87,'EEF5F7','D46631');
   const roi=trainingRoi(shot.path,regions[i]);
   slide.addImage({path:roi,...imageSizingContain(roi,bx+.23,y+.34,bw-.46,1.75)});
 }
 // Original screenshot is included as an uncropped, strictly hash-checked
 // source reference; zoom PNGs are deterministically reconstructible from it.
 slide.addImage({path:shot.path,...imageSizingContain(shot.path,bx+5.72,1.65,.22,.24)});
 slide.addNotes(english?'Details cropped directly from the original screenshot pixels without resampling. No application UI has been invented.':'Ingrandimenti ritagliati senza ricampionamento dai pixel della schermata originale. Nessuna parte della UI è inventata.');
}
function focusedCiPanel(slide,d,accent){
 // Use authentic DOM-region screenshots from the current CI only. For offline
 // editorial export, diagrams/archived evidence are explicitly labelled.
 const shot=realUiImage(d);
 const x=5.72, w=6.97;
 rect(slide,x,1.48,w,5.22,C.white,C.line);
 if(shot){
   if(d.original===48)preciseCiDetail(slide,shot,'steps');
   else addCiZoom(slide,shot,null,d);
   return;
 }
 if(d.index===59){
   const avatar=path.join(root,'app/static/ai-chatbot/albot-avatar.png');
   if(!fs.existsSync(avatar))throw new Error('AlBot original avatar missing');
   slide.addImage({path:avatar,...imageSizingContain(avatar,x+.23,1.80,1.43,1.43)});
   addText(slide,'AlBot · anche «Alex»\nAssistente AI di CIR',
     {x:x+1.85,y:1.97,w:4.72,h:1.00,fontSize:17.3,bold:true,color:C.navy,margin:0,fit:'shrink'});
   if(shot){
     slide.addImage({path:shot.path,...imageSizingContain(shot.path,x+.45,3.40,6.12,2.79)});
   }else{
     boxNode(slide,'Pannello AlBot · riferimento operativo illustrativo',
       x+.41,3.81,6.15,1.14,'E9F3F9',C.navy,13);
   }
 }else if(shot){
   const above=d.index===56?'STATISTICHE / GRAFICI REALI':'WORKFLOW / CARD E FRECCE';
   addText(slide,above,{x:x+.2,y:1.70,w:w-.4,h:.28,fontSize:11.3,bold:true,color:C.teal,align:'center',margin:0});
   slide.addImage({path:shot.path,...imageSizingContain(shot.path,x+.18,2.06,w-.36,4.05)});
 }else{
   visual(slide,d,accent);
   addText(slide,'Schema didattico · non è una schermata dell’applicazione',
      {x:x+.21,y:6.27,w:w-.42,h:.26,fontSize:9.2,color:C.muted,align:'center',margin:0});
 }
 return;
}

// RC91: definitions precede the SPAM worked example. Editable native diagrams.
function introLabel(slide,text,x,y,w,h,fill='E7F2FA',size=13.5){
 boxNode(slide,text,x,y,w,h,fill,C.navy,size);
}
function workflowIntroPanel(slide,d,accent){
 const x=6.55;
 addText(slide,'CONCETTO · '+d.workflow_intro.toUpperCase(),
  {x:x+.18,y:1.70,w:5.6,h:.29,fontSize:10.1,bold:true,color:C.teal,margin:0});
 if(d.workflow_intro==='workflow'){
  introLabel(slide,'INCIDENTE\nSEGNALATO',x+.15,2.37,1.68,1.02,'E7F2FA',13.2);
  arrow(slide,x+1.96,2.70,.42,'right',accent);
  introLabel(slide,'WORKFLOW\nREGOLE + STEP',x+2.48,2.28,1.76,1.20,'E5F5ED',13.6);
  arrow(slide,x+4.32,2.70,.42,'right',accent);
  introLabel(slide,'CHIUSURA\nVERIFICATA',x+4.85,2.37,1.25,1.02,'EFEAF9',12.2);
  introLabel(slide,'Struttura configurata dagli admin del tenant',x+.62,4.34,5.10,.67,'F1F6F9',13);
 }else if(d.workflow_intro==='categories'){
  introLabel(slide,'1a CATEGORIA\nSPAM',x+.31,2.17,2.22,.96,'E5F5ED',14);
  arrow(slide,x+2.71,2.46,.55,'right',accent);
  introLabel(slide,'WORKFLOW\nSPAM',x+3.49,2.17,2.21,.96,'E7F2FA',14);
  introLabel(slide,'2a / 3a CATEGORIA\nClassificazione aggiuntiva',x+.31,3.67,3.00,.92,'F7F2E6',12.5);
  introLabel(slide,'NON aggiunge altri step',x+3.52,3.67,2.33,.92,'F1F6F9',12.2);
  addText(slide,'Senza workflow dedicato per la prima categoria: fallback default',
   {x:x+.19,y:5.31,w:5.92,h:.45,fontSize:11.0,bold:true,color:C.teal,align:'center',margin:0,fit:'shrink'});
 }else if(d.workflow_intro==='steps'){
  ['1  Presa in carico','2  Analisi','3  Azione','4  Verifica'].forEach((t,i)=>{
   const bx=x+.26+(i%2)*2.86,by=2.18+Math.floor(i/2)*1.44;
   introLabel(slide,t,bx,by,2.46,.81,i%2?'E6F5ED':'E7F2FA',14);
  });
  introLabel(slide,'Ordinati · richiesti / opzionali · tracciati',x+.52,5.44,5.13,.53,'F0F4FA',11.8);
 }else if(d.workflow_intro==='conditions'){
  introLabel(slide,'Condizione di rischio\nper diritti e liberta?',x+.76,2.11,4.77,.85,'F7F0E6',14.4);
  line(slide,x+3.10,2.97,0,.39,accent,1.8);
  line(slide,x+1.85,3.36,2.48,0,accent,1.8);
  line(slide,x+1.85,3.36,0,.40,accent,1.8);
  line(slide,x+4.33,3.36,0,.40,accent,1.8);
  introLabel(slide,'SI\nFasi condizionali',x+.52,3.89,2.68,.95,'E7F2FA',13.2);
  introLabel(slide,'NO\nPercorso ordinario',x+3.42,3.89,2.43,.95,'E7F5EE',13.2);
  addText(slide,'Solo le fasi applicabili devono essere soddisfatte',
   {x:x+.26,y:5.52,w:5.80,h:.31,fontSize:11.5,color:C.teal,bold:true,align:'center',margin:0});
 }else if(d.workflow_intro==='dependencies'){
  introLabel(slide,'STEP OPERATIVO',x+1.68,2.15,2.97,.77,'E7F2FA',15);
  line(slide,x+3.17,2.93,0,.54,accent,1.8);
  line(slide,x+1.22,3.47,3.87,0,accent,1.8);
  [x+1.22,x+3.17,x+5.09].forEach(v=>line(slide,v,3.47,0,.40,accent,1.8));
  introLabel(slide,'LABEL\nAzione',x+.20,4.01,1.94,1.06,'E6F3FA',12.3);
  introLabel(slide,'NOTIFICA\nTipo / modello',x+2.24,4.01,1.94,1.06,'E6F5EC',12.0);
  introLabel(slide,'PDF\nTemplate',x+4.30,4.01,1.92,1.06,'F6F0E8',12.3);
  addText(slide,'Dipendenze = risorse e requisiti; condizioni = applicabilita',
   {x:x+.23,y:5.66,w:5.85,h:.43,fontSize:11.0,bold:true,color:C.teal,align:'center',margin:0,fit:'shrink'});
 }
 addText(slide,'Diagramma didattico · forme PowerPoint modificabili',
  {x:x+.24,y:6.40,w:5.83,h:.24,fontSize:9.0,italic:true,color:C.muted,align:'center',margin:0});
}
function spamIntroPanel(slide,d,accent){
 const x=6.60;
 addText(slide,'ESEMPIO DI ASSOCIAZIONE',{x:x,y:1.73,w:5.77,h:.24,fontSize:10.2,bold:true,color:C.teal,margin:0});
 introLabel(slide,'CATALOGO DEL TENANT\nWorkflow SPAM corrente',x+.66,2.12,4.58,.87,'E7F2FA',14);
 introLabel(slide,'NUOVO INCIDENTE\n1a categoria: SPAM',x+.53,3.35,4.80,.94,'E6F5EE',14.5);
 arrow(slide,x+2.59,4.42,.57,'right',accent);
 introLabel(slide,'WORKFLOW APPLICATO\nStep SPAM ordinati',x+.66,5.00,4.58,.95,'E7F2FA',14.0);
 addText(slide,'Altre categorie: solo classificazione',
  {x:x+.63,y:6.25,w:4.70,h:.29,fontSize:11,color:C.teal,bold:true,align:'center',margin:0});
}

function albotWorkflowAuthoringPanel(slide,d,accent){
 const x=6.52;
 const en=english;
 addText(slide,en?'ALBOT / WORKFLOW DESIGN':'ALBOT / PROGETTAZIONE WORKFLOW',
   {x:x+.15,y:1.69,w:5.9,h:.25,fontSize:10,bold:true,color:C.teal,margin:0});
 introLabel(slide,en?'ADMIN INSTRUCTIONS\nSteps, dependencies, conditions':'ISTRUZIONI ADMIN\nStep, dipendenze, condizioni',
   x+.52,2.09,5.12,.86,'E7F2FA',13.4);
 slide.addShape(pptx.ShapeType.downArrow,{x:x+2.90,y:3.04,w:.34,h:.38,line:{color:accent,transparency:100},fill:{color:accent}});
 introLabel(slide,en?'ALBOT: PREVIEW\nValidated workflow definition':'ALBOT: ANTEPRIMA\nDefinizione workflow validata',
   x+.52,3.55,5.12,.83,'E6F5ED',13.4);
 line(slide,x+3.07,4.45,0,.38,accent,1.8);
 line(slide,x+1.76,4.83,2.62,0,accent,1.8);
 line(slide,x+1.76,4.83,0,.32,accent,1.8);
 line(slide,x+4.38,4.83,0,.32,accent,1.8);
 introLabel(slide,en?'CONFIRM IMPORT\nCurrent tenant':'CONFERMA IMPORT\nTenant corrente',
   x+.15,5.22,2.92,.88,'F2EDF9',12.7);
 introLabel(slide,en?'DOWNLOAD JSON\nNo database change':'SCARICA JSON\nNessuna modifica DB',
   x+3.18,5.22,2.92,.88,'F9F2E5',12.3);
 addText(slide,en?'Only authorized admins; no automatic write':'Solo amministratori autorizzati; nessuna scrittura automatica',
   {x:x+.25,y:6.28,w:5.75,h:.26,fontSize:10.0,bold:true,color:C.teal,align:'center',margin:0});
}
function supportTicketsPanel(slide,d,accent){
 const art=path.join(root,'docs/presentation/rc109_support_tickets_art.png');
 if(!fs.existsSync(art))throw new Error('Missing original Support Tickets illustration');
 rect(slide,6.45,1.63,6.13,4.18,'142B51');
 slide.addImage({path:art,...imageSizingContain(art,6.46,1.64,6.10,4.15)});
 addText(slide,english?'OPEN A TICKET • REPLY • ESCALATE':'APRI UN TICKET • RISPONDI • ESCALA',
   {x:6.54,y:5.96,w:5.92,h:.27,fontSize:11.2,bold:true,align:'center',color:C.teal,margin:0});
 addText(slide,english?'Illustrative 3D artwork · tickets remain private to authorized users':'Illustrazione sintetica 3D · ticket visibili solo agli utenti autorizzati',
   {x:6.54,y:6.34,w:5.92,h:.25,fontSize:9.2,color:C.muted,align:'center',margin:0});
}
function rightPanel(slide,d,accent){
 if([46,56,59].includes(d.index))return focusedCiPanel(slide,d,accent);
 rect(slide,6.27,1.46,6.47,5.32,C.white,C.line);
 if(d.arch_visual){modularArchitecturePanel(slide,d,accent);return;}
 if(d.alert_architecture){alertArchitecturePanel(slide,d,accent);return;}
 if(d.workflow_intro){workflowIntroPanel(slide,d,accent);return;}
 if(d.albot_workflow_authoring){albotWorkflowAuthoringPanel(slide,d,accent);return;}
 if(d.support_tickets){supportTicketsPanel(slide,d,accent);return;}
 if(d.spam_intro_case){spamIntroPanel(slide,d,accent);return;}
 if(d.kind==='preview'){
   addText(slide,'DOCUMENTO DPO · ESEMPIO ANONIMIZZATO',{x:6.54,y:1.66,w:6.0,h:.24,fontSize:9.6,bold:true,color:C.teal,margin:0});
   slide.addImage({path:USER_DOC_PREVIEW,...imageSizingContain(USER_DOC_PREVIEW,6.53,1.98,5.97,4.63)});
   return;
 }
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
     (incidentShot?'INCIDENTE REALE · CATTURA CI':'ESEMPIO DIDATTICO · MEDIA STORICO'),
     {x:6.56,y:5.19,w:5.86,h:.22,fontSize:8.3,bold:true,color:C.teal,align:'center',margin:0});
   boxNode(slide,'1ª CATEGORIA\nSPAM',6.68,5.53,2.33,.69,'E5F0F9',C.navy,13);
   arrow(slide,9.18,5.70,.45,'right',accent);
   boxNode(slide,'WORKFLOW\nSPAM',9.78,5.53,2.32,.69,'E6F5EB',C.navy,13);
   addText(slide,'Altre categorie: classificano il caso, non sommano nuovi workflow.',
     {x:6.64,y:6.46,w:5.78,h:.29,fontSize:9.7,color:C.muted,align:'center',margin:0});
   return;
 }
 if(d.index===33){
   const wizard=ciById.has('tenant-setup-wizard-desktop')?{id:'tenant-setup-wizard-desktop',path:ciById.get('tenant-setup-wizard-desktop')}:realUiImage(d);
   if(wizard?.id==='tenant-setup-wizard-desktop' || wizard?.id==='tenant-setup-wizard-panel'){
     addText(slide,'SEQUENZA DEGLI STEP DEL WIZARD', {x:6.56,y:1.62,w:5.89,h:.30,fontSize:10.2,color:C.teal,bold:true,margin:0});
     slide.addImage({path:wizard.path,...imageSizingContain(wizard.path,6.59,2.05,5.85,4.39)});
   }else{
     photoPanel(slide,d);
     rect(slide,6.49,6.38,5.97,.31,C.white,C.line);
     addText(slide,'Schema del wizard · illustrazione di supporto',
       {x:6.49,y:6.43,w:5.97,h:.20,fontSize:8.8,color:C.muted,align:'center',margin:0});
   }
   return;
 }
 if(d.index===70 && categoryPalette?.id==='spam-incident-config-labels'){
   preciseCiDetail(slide,categoryPalette,'categories');
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
 if(realUiImage(d)){
   if(d.original===57){
     const shot=realUiImage(d);
     addText(slide,'PANORAMICA COMPLETA · STATISTICHE', {x:6.58,y:1.66,w:5.83,h:.28,fontSize:10.3,bold:true,color:C.teal,margin:0});
     slide.addImage({path:shot.path,...imageSizingContain(shot.path,6.51,2.04,5.95,4.43)});
   }else addCiZoom(slide,realUiImage(d),null,d);
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
 const images=d.images||[];const src=images.find(i=>fs.existsSync(imagePath(i)));const real=realUiImage(d);const ciScreen=Boolean(real);
 if(src||real){const img=real?real.path:imagePath(src);const wide=Boolean(real && !d.report_pages);
   const ix=wide?5.85:6.52,iw=wide?6.72:5.99;
   rect(slide,ix,1.80,iw,4.48,'F6F9FA');slide.addImage({path:img,...imageSizingContain(img,ix+.02,1.83,iw-.04,4.37)});
   addText(slide,ciManifest&&ciScreen?'SCHERMATA CI / DATI DI PROVA':'MEDIA EDITORIALE CIR',{x:ix+.02,y:6.43,w:iw-.06,h:.24,fontSize:8.7,bold:true,color:C.teal,align:'center',margin:0});}
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
  addText(slide,'Schema di mapping · non è una schermata applicativa',{x:x+.22,y:y+3.75,w:5.32,h:.29,fontSize:9.2,italic:true,color:C.muted,align:'center',margin:0});
 } else if(/alfresco/.test(title)){
  boxNode(slide,'CONFIGURAZIONE\n(Amministratore)',x+.10,y+.34,2.5,1.0,'E6F0F9',C.navy,15);boxNode(slide,'REPOSITORY\nALFRESCO',x+3.11,y+.34,2.5,1.0,'EAF5F3',C.navy,15);arrow(slide,x+2.64,y+.65,.42,'right',accent);boxNode(slide,'INCIDENTE\n(operatori autorizzati)',x+1.10,y+2.12,3.7,.94,'F3F0FA',C.navy,14);line(slide,x+4.33,y+1.43,0,.6,accent,2);addText(slide,'Schema di integrazione · non è una schermata applicativa',{x:x+.48,y:y+3.56,w:4.8,h:.36,fontSize:10,color:C.muted,italic:true,align:'center',margin:0});
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
 } else if(d.original===24){
   // CROSS-TENANT example: PDF · CSV · JSON · XML. Native editable 3-D bubbles.
   // Numbers below are isolated, synthetic teaching values, NEVER CI/production evidence.
   const samples=[
     {label:'Tenant A\nSPAM',count:14,x:x+.58,y:y+.52,r:.80,c:'1778BC'},
     {label:'Tenant B\nSPAM',count:9,x:x+2.24,y:y+.34,r:.64,c:'9955C5'},
     {label:'Tenant A\nPhishing',count:8,x:x+3.85,y:y+.54,r:.62,c:'0BA891'},
     {label:'Tenant C\nCredenziali',count:6,x:x+.48,y:y+2.45,r:.54,c:'DE8231'},
     {label:'Tenant B\nMalware',count:4,x:x+2.14,y:y+2.57,r:.47,c:'D44F89'},
     {label:'Tenant C\nSPAM',count:3,x:x+3.74,y:y+2.53,r:.44,c:'4B8EB2'},
   ];
   addText(slide,english?'TEST DATA · TENANT + CATEGORY':'DATI DI TEST · TENANT + CATEGORIA',
     {x:x+.24,y:y+.02,w:5.6,h:.27,fontSize:11.5,bold:true,color:C.teal,margin:0});
   samples.forEach(b=>{
     const rr=b.r, xx=b.x, yy=b.y;
     slide.addShape(pptx.ShapeType.ellipse,{x:xx,y:yy,w:rr*2,h:rr*2,
       line:{color:b.c,width:.9},fill:{color:b.c},
       shadow:{type:'outer',color:'32435E',opacity:.29,blur:5,angle:45,distance:3}});
     slide.addShape(pptx.ShapeType.ellipse,{x:xx+rr*.21,y:yy+rr*.13,w:rr*.97,h:rr*.39,
       line:{color:'FFFFFF',transparency:100},fill:{color:'FFFFFF',transparency:69},rotate:346});
     addText(slide,String(b.count),{x:xx+rr*.12,y:yy+rr*.44,w:rr*1.76,h:rr*.39,
       fontSize:16.8,bold:true,align:'center',color:'FFFFFF',margin:0});
     const label=english?b.label.replace('Credenziali','Credentials'):b.label;
     addText(slide,label,{x:xx+rr*.09,y:yy+rr*.91,w:rr*1.82,h:rr*.50,
       fontSize:9.5,bold:true,align:'center',color:'FFFFFF',margin:0,fit:'shrink'});
   });
   addText(slide,english?'Illustrative values only · not from the application':'Valori illustrativi · non estratti dall’applicazione',
     {x:x+.16,y:y+4.02,w:5.46,h:.29,fontSize:9.8,color:C.muted,italic:true,align:'center',margin:0});
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
// RC91: large readable native training slides for workflow cards and
// category/data-type selectors. Each crop is losslessly sourced from verified
// application screenshot pixels; the original is also embedded as evidence.
function makeFullWidthFocus(slide,d,index,accent){
 const isSteps=d.original===48;
 const id=isSteps?(ciById.has('workflow-steps-focused') && ciManifest?.screenshots?.some(row=>row.id==='workflow-steps-focused' && row.step_card_rois) ? 'workflow-steps-focused' : ciById.has('spam-workflow-steps')?'spam-workflow-steps':'workflow-steps-focused'):
  'spam-incident-config-labels';
 let shot;
 if(ciManifest){
  const image=ciById.get(id);
  if(!image)throw new Error('Mandatory focus screenshot missing: '+id);
  shot={id,path:image,archived:false};
 }else{
  const legacy=isSteps?'spam-workflow-steps.png':'spam-workflow-steps.png';
  const image=path.join(ARCHIVED_GALLERY_ROOT,legacy);
  shot=fs.existsSync(image)?{id,path:image,archived:true}:null;
 }
 if(!shot)throw new Error('Missing full width workflow training capture');
 const dim=require('image-size').imageSize(fs.readFileSync(shot.path));
 const tall=dim.height>dim.width*1.28;
 // Step ROIs are measured from the browser DOM for new CI captures. The
 // checked-in archival image uses precisely measured, individual card bounds.
 // Each crop includes its own header, instructions, final command and border.
 const stepRow=ciManifest?.screenshots?.find(row=>row.id===id)||null;
 // Source screenshot is linked without mutation; every enlarged crop is
 // deterministically generated by training_image_roi.py (Pillow).
 if(isSteps){
  addText(slide,'Sei riquadri completi del workflow: intestazione, istruzioni e comando finale',
    {x:.78,y:1.47,w:11.82,h:.34,fontSize:12.7,color:C.teal,bold:true,margin:0});
  const command=process.env.CIR_PYTHON||'python3';
  const args=[path.join(root,'scripts/training_step_card_roi.py'),shot.path];
  const regionsResult=cp.spawnSync(command,args,{encoding:'utf8'});
  if(regionsResult.status!==0)throw new Error('Cannot determine workflow card crop geometry: '+regionsResult.stderr);
  let regions=JSON.parse(regionsResult.stdout);
  // A measured, browser-authenticated element ROI takes precedence over the
  // older static historical fallback, including on grid-wrapped layouts.
  if(stepRow?.step_card_rois){
    // Step geometry was validated when capturing the page and is revalidated
    // here by the shared geometry helper using the current screenshot size.
    const metadata=path.join(roiDirectory,'workflow-step-regions-'+crypto.createHash('sha256').update(JSON.stringify(stepRow.step_card_rois)).digest('hex')+'.json');
    if(!fs.existsSync(metadata))fs.writeFileSync(metadata,JSON.stringify(stepRow));
    const geometry=cp.spawnSync(command,[...args,metadata],{encoding:'utf8'});
    if(geometry.status!==0)throw new Error('Untrusted workflow card geometry: '+geometry.stderr);
    regions=JSON.parse(geometry.stdout);
  }
  if(regions.length!==6)throw new Error('Expected exactly six individual step cards');
  for(let i=0;i<6;i++){
    const x=.77+i*2.08;
    rect(slide,x,1.94,1.93,4.54,'FFFFFF','D9E5EB');
    addText(slide,'STEP '+(i+1),{x:x+.12,y:2.01,w:1.66,h:.24,fontSize:11.2,bold:true,color:C.teal,margin:0,align:'center'});
    const file=trainingRoi(shot.path,regions[i]);
    slide.addImage({path:file,...imageSizingContain(file,x+.07,2.32,1.79,3.85)});
  }
 }else{
  addText(slide,'La prima categoria determina il workflow; le altre classificano il caso',
    {x:.80,y:1.42,w:11.83,h:.29,fontSize:12.6,bold:true,color:C.teal,margin:0});
  const regions=tall?[[.15,.555,.83,.100],[.15,.654,.83,.112]]:
    [[.01,.01,.98,.47],[.01,.48,.98,.50]];
  const titles=['CATEGORIE: DISPONIBILI E SELEZIONATE','DATI INTERESSATI / PERSONALE'];
  for(let i=0;i<2;i++){
   const y=1.88+i*2.34;
   addText(slide,titles[i],{x:.85,y,w:11.56,h:.25,fontSize:10.4,bold:true,color:C.teal,margin:0});
   rect(slide,.81,y+.29,11.71,1.91,'EEF5F7','D46631');
   const file=trainingRoi(shot.path,regions[i]);
   slide.addImage({path:file,...imageSizingContain(file,.92,y+.35,11.49,1.78)});
  }
 }
 addText(slide,(shot.archived?'Cattura storica della vera app CIR: non del run CI corrente':'Screenshot dell’applicazione · dati di test · immagine originale verificata')+
  ' · ingrandimenti di pixel reali',
  {x:.80,y:6.56,w:11.67,h:.23,fontSize:9.3,color:C.muted,italic:true,margin:0,align:'center'});
 footer(slide,index);notes(slide,d);
}
function makeContent(slide,d,index){const accent=[C.cyan,C.teal,C.blue,C.violet,C.green][Math.floor((index-1)/15)%5];bgBase(slide,accent);
 addText(slide,(d.tag||'CIR / FORMAZIONE').toUpperCase(),{x:.74,y:.34,w:11.4,h:.24,fontSize:9.1,bold:true,charSpacing:1.12,color:accent,margin:0});
 const t=d.title||'';let font=t.length>77?20.5:t.length>56?23.0:27;
 addText(slide,t,{x:.73,y:.70,w:11.9,h:.61,fontSize:font,bold:true,color:C.navy,breakLine:false,margin:0,fit:'shrink'});
 if(d.original===48||d.original===71){makeFullWidthFocus(slide,d,index,accent);return;}
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
  addText(slide,ciById.has('registry-closed-state')?'Icone e stati verificati nella cattura CI della build corrente.':'Stati operativi rappresentati nello schema didattico.',{x:6.7,y:6.66,w:5.7,h:.21,fontSize:8.4,color:C.muted,italic:true,align:'center',margin:0});
 }
 footer(slide,index);notes(slide,d);
}
const comicDialog={
 '01':'“We had an incident!” — “Have you filed the CIR?”',
 '02':'“Can’t I just declare the case resolved?” — “Sure, after the other 112 steps!”',
 '03':'“Can I borrow your SPAM workflow?” — “The workflow, yes; the incidents stay with me and you own the mess!”',
 '04':'“Destination?” — “SPAM.” — “Great! Fasten your seat belt, traffic is heavy.”',
 '05':'“I just need a signature!” — “Mapping, template, preview first...” — “Maybe I should stay a TXT file!”',
 '06':'“It was just one innocent email!” — “And are those 2,598 sent messages your relatives?”',
 '07':'“Can I finally rest?” — “Of course. Until the next incident!”',
 '08':'“Is everyone here?” — “Wait for the PDF and notification!” — “Attachments always arrive last!”'
};
function comicCaption(slide,section,x=5.55,y=6.12){
 if(false && english)addText(slide,'Comic dialogue (English): '+comicDialog[section],{
  x,y,w:7.05,h:.53,fontSize:11.0,bold:false,color:'D5F6FC',
  align:'center',margin:0,fit:'shrink'});
}
function makeChapter(slide,d,index){
  // Original title stays as editable native PowerPoint text, while the
  // associated cartoon is a user-approved illustration with recorded SHA-256.
  const parts=(d.title||'').split('/'),nb=(parts[0]||'').trim();
  const name=parts.slice(1).join('/').trim()||d.title;
  const section=nb.padStart(2,'0');
  const art=cartoonFor(section);
  slide.background={color:C.navy};
  rect(slide,0,0,W,.13,C.cyan);
  rect(slide,.67,1.20,.11,4.94,C.cyan);
  addText(slide,english?'TRAINING • CIR':'FORMAZIONE • CIR',{x:1.03,y:1.08,w:4.16,h:.38,
    fontSize:14.7,bold:true,color:'B9EBF4',charSpacing:1.6,margin:0});
  addText(slide,nb,{x:1.02,y:1.79,w:4.15,h:1.09,fontSize:66,bold:true,color:'FFFFFF',margin:0});
  const isLong=name.length>38;
  addText(slide,name,{x:1.04,y:3.13,w:4.38,h:isLong?1.97:1.35,
    fontSize:isLong?25.3:32.0,bold:true,color:'FFFFFF',margin:0,
    valign:'mid',breakLine:false,fit:'shrink'});
  addText(slide,english?'A cartoon break before the next chapter':'Una pausa cartoon prima del prossimo capitolo',
    {x:1.04,y:5.80,w:4.20,h:.31,fontSize:11.4,color:'D5F6FC',margin:0});
  // Panoramic approved strips (07) should not be trapped in a tall white
  // frame; preserve their full aspect ratio and avoid blank filler panels.
  const wideStrip=section==='07';
  const panel=wideStrip?{x:5.52,y:2.04,w:7.20,h:2.79}:{x:5.52,y:1.39,w:7.20,h:4.64};
  rect(slide,panel.x,panel.y,panel.w,panel.h,'FFFFFF','65BFCB');
  slide.addImage({path:art.path,...imageSizingContain(art.path,panel.x+.11,panel.y+.10,panel.w-.22,panel.h-.20)});
  comicCaption(slide,section);
  addText(slide,`${index} / ${FINAL_SLIDES}`,{x:11.55,y:6.78,w:.97,h:.30,
    color:'FFFFFF',align:'right',fontSize:10,bold:true,margin:0});
  notes(slide,d);
  slide.addNotes((english?'[Sources] Approved original cartoon for chapter ':'[Sources] Vignetta originale approvata per la sezione ')+section+
    '; '+art.path.replace(root+path.sep,'')+'; SHA-256 '+art.sha256+(english?'. This is an original cartoon, not a CIR application screenshot.':'. Non e una screenshot CIR.'));
}
function thankYouSlide(){
 const slide=pptx.addSlide(),n=pptx._slides.length;
 const art=cartoonFor('grazie');
 slide.background={color:C.bg};
 rect(slide,.32,.28,12.69,6.75,'FFFFFF',C.line);
 slide.addImage({path:art.path,...imageSizingContain(art.path,.43,.39,12.47,6.48)});
 // The English artwork itself says 'Thank you!' on the held sign.
 addText(slide,`${n} / ${FINAL_SLIDES}`,{x:11.64,y:7.10,w:.98,h:.20,
   fontSize:8.7,color:C.teal,bold:true,align:'right',margin:0});
 slide.addNotes((english?'[Sources] English derivative of the Italian thank-you cartoon, with a Thank you! sign, ':'[Sources] Vignetta originale di ringraziamento con robot CIR e cartello Grazie!, ')+
   art.path.replace(root+path.sep,'')+'; SHA-256 '+art.sha256+'. ' +
   (english?'Synthetic non-photographic illustration, not an application screenshot.':'Illustrazione sintetica non fotografica, non uno screenshot dell applicazione.'));
}
function makeCover(slide,d,index){slide.background={color:C.navy};const img=imagePath(d.images[0]);if(fs.existsSync(img))slide.addImage({path:img,...imageSizingCrop(img,0,0,W,H)});slide.addShape(pptx.ShapeType.rect,{x:0,y:0,w:W,h:H,fill:{color:C.navy,transparency:19},line:{color:C.navy,transparency:100}});
 const logo=imagePath(d.images[1]);if(fs.existsSync(logo))slide.addImage({path:logo,...imageSizingContain(logo,.88,1.02,1.18,1.18)});
 addText(slide,'CYBERSECURITY INCIDENT REGISTRY',{x:2.33,y:1.24,w:9.9,h:.43,fontSize:19,color:'BCE7F0',bold:true,margin:0,charSpacing:1.7});
 addText(slide,'CIR',{x:.98,y:2.29,w:3.00,h:1.55,fontSize:90,bold:true,color:'FFFFFF',margin:0});
 addText(slide,'Cybersecurity\nIncident Registry',{x:4.16,y:2.62,w:7.35,h:1.04,fontSize:31.0,bold:true,color:'F8C66A',margin:0,breakLine:false,fit:'shrink',valign:'mid'});
 addText(slide,'Gestione degli incidenti e dei workflow procedurali',{x:1.01,y:4.18,w:10.95,h:.88,fontSize:28,bold:true,color:'FFFFFF',margin:0,fit:'shrink'});
 addText(slide,'Corso didattico · interfaccia reale · laboratorio didattico di esempio',{x:1.04,y:5.28,w:10.9,h:.38,fontSize:17.1,color:'D7F4FC',margin:0});
 rect(slide,1.02,6.30,11.24,.45,C.white);addText(slide,(ciManifest?`VERSIONE 0.10.0-1   |   RC109   |   SCREENSHOT CI ${ciCommit.slice(0,8)} / ${ciBuild}`:
   'VERSIONE 0.10.0-1   |   RC109   |   EDIZIONE EDITORIALE · CATTURE STORICHE'),{x:1.21,y:6.41,w:10.92,h:.21,fontSize:10.6,color:C.navy,bold:true,margin:0});notes(slide,d);
}
data.forEach((d,i)=>{let slide=pptx.addSlide();const n=i+1;if(d.kind==='cover')makeCover(slide,d,n);else if(d.kind==='chapter')makeChapter(slide,d,n);else makeContent(slide,d,n)});
// After the very last conclusion slide and before section 08 Appendici.
thankYouSlide();
// RC91 appendix: a true chapter divider, then all original application
// screenshots in manifest order (except the classic UI), followed by two
// dedicated, large-format previews. With 31 gallery captures, those previews
// are "Schermata 32" (compiled PDF) and "Schermata 33" (notification).
function appendixBanner(){
 const slide=pptx.addSlide(),n=pptx._slides.length;
 const art=cartoonFor('08');
 slide.background={color:C.navy};
 rect(slide,0,0,W,.13,C.teal);
 rect(slide,.67,1.20,.11,4.94,C.cyan);
 addText(slide,english?'TRAINING • CIR':'FORMAZIONE • CIR',{x:1.03,y:1.08,w:4.16,h:.38,
   fontSize:14.7,bold:true,color:'B9EBF4',charSpacing:1.6,margin:0});
 addText(slide,'08',{x:1.02,y:1.79,w:4.15,h:1.09,fontSize:66,
   bold:true,color:'FFFFFF',margin:0});
 addText(slide,english?'Appendices':'Appendici',{x:1.04,y:3.13,w:4.38,h:1.35,fontSize:32,
   bold:true,color:'FFFFFF',margin:0});
 addText(slide,english?'Authentic application screenshots\nSynthetic test data and verifiable integrity':"Screenshot autentiche dell'applicazione\nDati di prova e integrità verificabile",
   {x:1.05,y:5.37,w:4.22,h:.75,fontSize:13,color:'D5F6FC',margin:0});
 rect(slide,5.52,2.04,7.20,2.79,'FFFFFF','65BFCB');
 slide.addImage({path:art.path,...imageSizingContain(art.path,5.63,2.14,6.98,2.59)});
 comicCaption(slide,'08',5.55,5.20);
 addText(slide,`${n} / ${FINAL_SLIDES}`,{x:11.55,y:6.78,w:.97,h:.30,
   color:'FFFFFF',align:'right',fontSize:10,bold:true,margin:0});
 slide.addNotes((english?'[Sources] Approved original cartoon for chapter 08; ':'[Sources] Vignetta originale approvata per sezione 08; ')+
   art.path.replace(root+path.sep,'')+'; SHA-256 '+art.sha256+'. '+
   (ciManifest?(english?'Screenshot gallery sourced from the current CI run manifest.':'Screenshot della galleria da manifest del run corrente.'):
   (english?'Editorial gallery with historical application captures, not attested for the current CI run.':'Galleria editoriale con catture storiche dell applicazione, non attestate per il run CI corrente.'))+
   (english?' The classic UI is excluded. The final two slides show a completed PDF document and notification preview.':' La UI classica e esclusa. Le ultime due schermate sono dedicate al PDF compilato e alla notifica.'));
}
appendixBanner();

// Complete gallery: each visible capture appears in the original manifest
// order and is linked to its SHA-256-identical source PNG/JPEG. In a CI run
// this includes pdf-generated-preview and notification-preview; the final
// dedicated pages below offer a larger annotated view of these two subjects.
for(const [i,row] of GALLERY_ITEMS.entries()){
    const img=row.path;
    if(!fs.existsSync(img))throw new Error('Screenshot missing for appendix: '+row.id);
    const slide=pptx.addSlide();
    bgBase(slide,C.teal);
    addText(slide,"APPENDICE / SCREENSHOT AUTENTICHE DELL'APPLICAZIONE",
      {x:.73,y:.34,w:11.9,h:.3,fontSize:10.2,bold:true,color:C.teal,margin:0});
    addText(slide,'Schermata '+String(i+1)+' / '+String(GALLERY_ITEMS.length+APPENDIX_PREVIEWS)+' — '+row.id,
      {x:.73,y:.75,w:11.9,h:.48,fontSize:22,bold:true,color:C.navy,margin:0,fit:'shrink'});
    rect(slide,.63,1.39,12.07,5.20,'FFFFFF',C.line);
    slide.addImage({path:img,...imageSizingContain(img,.76,1.48,11.81,4.98)});
    addText(slide,row.archived?'Cattura storica della vera applicazione CIR · NON del run CI corrente':
      'Cattura originale CIR con dati sintetici isolati · SHA-256 '+row.sha256.slice(0,20)+'…',
      {x:.80,y:6.59,w:11.8,h:.27,fontSize:10,color:C.muted,margin:0});
    footer(slide,GALLERY_FIRST_SLIDE+i);
    slide.addNotes((row.archived?(english?'Historical application screenshot from bundled assets; not attested for this commit.':'Screenshot storica inclusa negli asset originali dell applicazione; non attestata per questo commit.'):
      (english?'Original CI screenshot taken from the application browser with isolated synthetic data.':'Screenshot originale della CI, prelevata dal browser dell applicazione con dati sintetici isolati.'))+
      ' ID '+row.id+'; SHA-256 '+row.sha256+'; '+(row.archived?'archivio del progetto':
      'commit '+ciCommit+'; build '+ciBuild)+(english?'. No classic-interface images.':'. Nessuna immagine dell interfaccia classica.'));
}

// The previews used to appear at positions 95 and 96 before the gallery.
// They now close the appendix as additional numbered learning screenshots.
// Current full CI manifests contain 31 permitted browser images, thus these
// are displayed as Schermata 32 and Schermata 33, respectively.
function appendixPreview(title,id,caption,serial){
 const slide=pptx.addSlide();const n=pptx._slides.length;
 bgBase(slide,C.teal);
 addText(slide,id==='generated-pdf'?'APPENDICE / DOCUMENTO DI ESEMPIO ANONIMIZZATO':"APPENDICE / SCREENSHOT AUTENTICHE DELL'APPLICAZIONE",
   {x:.75,y:.34,w:11.9,h:.29,fontSize:10.1,bold:true,color:C.teal,margin:0});
 addText(slide,`Schermata ${serial} / ${GALLERY_ITEMS.length+APPENDIX_PREVIEWS} — ${title}`,
   {x:.75,y:.75,w:11.85,h:.54,fontSize:22.5,bold:true,color:C.navy,margin:0,fit:'shrink'});
 rect(slide,.68,1.51,11.96,4.88,C.white,C.line);
 const image=id==='generated-pdf'?USER_DOC_PREVIEW:ciById.get(id);
 if(image){
  if(id==='generated-pdf'){
    // The approved anonymized document replaces the former blank/scratch
    // preview. In CI a second *real* generated PDF raster remains visibly
    // linked and SHA-256 verified, preserving the original evidence contract.
    if(generatedPdfPreview){
      addText(slide,'MODELLO ANONIMIZZATO · ESEMPIO DIDATTICO',
        {x:1.04,y:1.65,w:6.35,h:.19,fontSize:9.0,bold:true,color:C.teal,margin:0});
      slide.addImage({path:USER_DOC_PREVIEW,...imageSizingContain(USER_DOC_PREVIEW,1.05,1.96,6.37,4.23)});
      addText(slide,'PDF GENERATO DA CIR · EVIDENZA CI',
        {x:7.55,y:1.65,w:4.45,h:.19,fontSize:9.0,bold:true,color:C.teal,margin:0});
      slide.addImage({path:generatedPdfPreview.path,...imageSizingContain(generatedPdfPreview.path,7.51,1.96,4.70,4.23)});
    } else {
      slide.addImage({path:USER_DOC_PREVIEW,...imageSizingContain(USER_DOC_PREVIEW,.84,1.62,11.64,4.63)});
    }
  } else slide.addImage({path:image,...imageSizingContain(image,.84,1.62,11.64,4.63)});
  addText(slide,caption,{x:.90,y:6.49,w:11.46,h:.24,fontSize:10.1,
    color:C.teal,bold:true,margin:0,align:'center'});
  slide.addNotes('[Sources] '+(id==='generated-pdf'?
    (english?'User-approved anonymized document example, not an application screenshot; SHA-256 ':'Modello di notifica anonimizzato approvato dall utente, non screenshot dell applicazione; SHA-256 ')+USER_DOC_SHA256+'. '+
    (generatedPdfPreview?'Accanto, rasterizzazione autenticata del PDF realmente prodotto da CIR e verificata tramite manifesto SHA-256.':'Nessuna attestazione di PDF prodotto nel run editoriale.'):
    (english?'Browser screenshot from the real CIR interface showing notification subject, recipients and content; bytes checked against the current run SHA-256 manifest.':'Screenshot browser della vera interfaccia CIR, anteprima oggetto/destinatari/contenuto notifiche; byte verificati SHA-256 dal manifest del run corrente.'))+
    ' Commit '+ciCommit+'; build '+ciBuild+'.');
 }else{
  addText(slide,'Cattura autentica non disponibile in questa edizione editoriale.\nLa CI inserirà la schermata della vera applicazione.',
    {x:1.53,y:3.14,w:10.25,h:1.10,fontSize:19.5,bold:true,color:C.muted,
      align:'center',margin:0});
  slide.addNotes((english?'Offline editorial preview: no generated PDF or notification is simulated. ':'Anteprima editoriale: non contiene un PDF o una notifica simulati. ')+
    (english?'Authentic application images are incorporated only by the CI with verified manifest and SHA-256.':'La schermata autentica viene incorporata solo dalla CI con manifest e SHA-256.'));
 }
 footer(slide,n);
}
appendixPreview('Documento PDF compilato','generated-pdf',
 'Esempio didattico anonimizzato · anteprima PDF realmente generata da CIR verificata separatamente nella CI',
 GALLERY_ITEMS.length+1);
appendixPreview('Notifica prima dell’invio','notification-preview',
 'Anteprima della notifica · oggetto, destinatari, contenuto e allegati da verificare',
 GALLERY_ITEMS.length+2);

fs.mkdirSync(path.dirname(out),{recursive:true});pptx.writeFile({fileName:out}).then(()=>console.log('Created '+out+' slides='+(BASE_SLIDES+GALLERY_ITEMS.length))).catch(e=>{console.error(e);process.exit(1)});
