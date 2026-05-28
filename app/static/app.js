
function isAllowedSafeMarkdownColor(value){
  return /^(?:#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|[a-zA-Z][a-zA-Z0-9_-]{0,30}|rgb\(\s*(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\s*,\s*(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\s*,\s*(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\s*\)|hsl\(\s*(?:[0-9]|[1-9][0-9]|[12][0-9]{2}|3[0-5][0-9]|360)\s*,\s*(?:[0-9]|[1-9][0-9]|100)%\s*,\s*(?:[0-9]|[1-9][0-9]|100)%\s*\))$/.test((value || '').trim());
}

function isAllowedSafeMarkdownSize(value){
  return /^(?:xx-small|x-small|small|normal|medium|large|x-large|xx-large|[8-9]px|[1-4][0-9]px|5[0-6]px|0\.[5-9]em|[1-3](?:\.[0-9])?em|4(?:\.0)?em|0\.[5-9]rem|[1-3](?:\.[0-9])?rem|4(?:\.0)?rem|[5-9][0-9]%|[1-2][0-9]{2}%|300%)$/i.test((value || '').trim());
}

function applySafeMarkdownStyles(root){
  const scope = root || document;
  scope.querySelectorAll('[data-md-color]').forEach((node)=>{
    const color = (node.getAttribute('data-md-color') || '').trim();
    if(isAllowedSafeMarkdownColor(color)) node.style.color = color;
  });
  scope.querySelectorAll('[data-md-size]').forEach((node)=>{
    const size = (node.getAttribute('data-md-size') || '').trim().toLowerCase();
    if(isAllowedSafeMarkdownSize(size)) node.style.fontSize = size;
  });
}

function makeDnd(){
  const makeSelectedRemovable=()=>document.querySelectorAll('.dropzone .chip').forEach(chip=>{
    if(chip.dataset.removeReady==='true')return;
    chip.dataset.removeReady='true';
    chip.title='Clic per rimuovere dalla selezione';
    chip.addEventListener('click',ev=>{
      if(ev.target && ['INPUT','A','BUTTON','SELECT','TEXTAREA'].includes(ev.target.tagName))return;
      chip.remove();
    });
  });
  document.querySelectorAll('.chip[draggable=true]').forEach(el=>{
    el.addEventListener('dragstart',e=>{
      e.dataTransfer.setData('text/plain',JSON.stringify({id:el.dataset.id,text:el.dataset.text,target:el.dataset.target}));
    });
  });
  document.querySelectorAll('.dropzone').forEach(zone=>{
    zone.addEventListener('dragover',e=>{e.preventDefault();zone.style.background='#eef6ff'});
    zone.addEventListener('dragleave',()=>zone.style.background='');
    zone.addEventListener('drop',e=>{
      e.preventDefault();zone.style.background='';
      let d=JSON.parse(e.dataTransfer.getData('text/plain'));
      if(d.target!==zone.dataset.target)return;
      if(zone.querySelector('input[value="'+d.id+'"][name="'+zone.dataset.target+'"]'))return;
      const maxItems=parseInt(zone.dataset.maxItems||'0',10);
      if(maxItems>0 && zone.querySelectorAll('input[name="'+zone.dataset.target+'"]').length>=maxItems){
        alert('Numero massimo di elementi selezionabili raggiunto: '+maxItems);
        return;
      }
      let s=document.createElement('span');
      s.className='chip';
      s.textContent=d.text+' ×';
      let i=document.createElement('input');
      i.type='hidden';i.name=zone.dataset.target;i.value=d.id;if(zone.dataset.formId)i.setAttribute('form',zone.dataset.formId);
      s.appendChild(i);zone.appendChild(s);makeSelectedRemovable();
    });
  });
  makeSelectedRemovable();
}


function initIncidentTemplateAutofill(){
  document.querySelectorAll('[data-incident-template-select]').forEach(select=>{
    if(select.dataset.autofillReady==='true') return;
    select.dataset.autofillReady='true';
    const formId = select.dataset.templateTargetForm;
    const form = formId ? document.getElementById(formId) : select.closest('form');
    const payloadNodeId = select.dataset.templatePayload;
    const payloadNode = payloadNodeId ? document.getElementById(payloadNodeId) : null;
    let templates = [];
    try{ templates = JSON.parse(payloadNode ? payloadNode.textContent : '[]') || []; }catch(e){ templates = []; }
    const byId = new Map(templates.map(t=>[String(t.id), t]));
    function field(name){ return form ? form.querySelector('[name="'+name+'"]') : null; }
    function setValue(name, value){ const el = field(name); if(el) el.value = value || ''; }
    function setSelectValue(name, value){ const el = field(name); if(el) el.value = value == null ? '' : String(value); }
    function setCheckbox(name, value){ const el = field(name); if(el) el.checked = !!value; }
    function chipText(target, id){
      const source = document.querySelector('.palette .chip[data-target="'+target+'"][data-id="'+id+'"]');
      return source ? (source.dataset.text || source.textContent || id).trim() : id;
    }
    function setDropzone(target, ids){
      if(!form) return;
      const zone = form.querySelector('.dropzone[data-target="'+target+'"]');
      if(!zone) return;
      zone.innerHTML = '';
      (ids || []).forEach(raw=>{
        const id = String(raw);
        if(!id || zone.querySelector('input[value="'+CSS.escape(id)+'"][name="'+target+'"]')) return;
        const span = document.createElement('span');
        span.className = 'chip';
        span.textContent = chipText(target, id) + ' ×';
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = target;
        input.value = id;
        if(zone.dataset.formId) input.setAttribute('form', zone.dataset.formId);
        span.appendChild(input);
        zone.appendChild(span);
      });
    }
    function refreshDndHandlers(){
      if(typeof makeDnd === 'function') makeDnd();
    }
    select.addEventListener('change', ()=>{
      const tmpl = byId.get(String(select.value));
      if(!tmpl || !form) return;
      setValue('name', tmpl.incident_name);
      setValue('reference', tmpl.reference);
      setValue('recipient', tmpl.recipient);
      setValue('recipient_email', tmpl.recipient_email);
      setValue('description', tmpl.incident_description);
      setSelectValue('severity_id', tmpl.severity_id);
      setSelectValue('status', tmpl.status || 'aperto');
      setCheckbox('personal_data', tmpl.personal_data);
      setValue('data_subjects_count', tmpl.data_subjects_count);
      setValue('data_volume', tmpl.data_volume);
      setDropzone('categories', tmpl.category_ids);
      setDropzone('data_types', tmpl.data_type_ids);
      setDropzone('people', tmpl.people_ids);
      setDropzone('recommendations', tmpl.recommendation_ids);
      refreshDndHandlers();
      const noticeId = select.dataset.templateNotice;
      const notice = noticeId ? document.getElementById(noticeId) : null;
      if(notice){
        notice.hidden = false;
        notice.textContent = 'Modello applicato al form: ' + (tmpl.name || 'modello selezionato') + '. Salvare per confermare le modifiche.';
      }
    });
  });
}

function makeAccessibleMenus(){
  const dropdowns=[...document.querySelectorAll('.dropdown')];
  const closeAll=(except=null)=>dropdowns.forEach(d=>{if(d!==except){d.classList.remove('open');const b=d.querySelector('.dropbtn');if(b)b.setAttribute('aria-expanded','false');}});
  dropdowns.forEach(drop=>{
    const btn=drop.querySelector('.dropbtn');
    const menu=drop.querySelector('.dropdown-content');
    if(!btn||!menu)return;
    const items=[...menu.querySelectorAll('a')];
    btn.addEventListener('click',ev=>{ev.preventDefault();const open=!drop.classList.contains('open');closeAll(drop);drop.classList.toggle('open',open);btn.setAttribute('aria-expanded',String(open));});
    btn.addEventListener('keydown',ev=>{
      if(['ArrowDown','Enter',' '].includes(ev.key)){ev.preventDefault();closeAll(drop);drop.classList.add('open');btn.setAttribute('aria-expanded','true');items[0]?.focus();}
      if(ev.key==='Escape'){drop.classList.remove('open');btn.setAttribute('aria-expanded','false');btn.focus();}
    });
    items.forEach((item,idx)=>item.addEventListener('keydown',ev=>{
      if(ev.key==='ArrowDown'){ev.preventDefault();items[(idx+1)%items.length].focus();}
      if(ev.key==='ArrowUp'){ev.preventDefault();items[(idx-1+items.length)%items.length].focus();}
      if(ev.key==='Home'){ev.preventDefault();items[0].focus();}
      if(ev.key==='End'){ev.preventDefault();items[items.length-1].focus();}
      if(ev.key==='Escape'){ev.preventDefault();drop.classList.remove('open');btn.setAttribute('aria-expanded','false');btn.focus();}
    }));
  });
  document.addEventListener('click',ev=>{if(!ev.target.closest('.dropdown'))closeAll();});
}

document.addEventListener('DOMContentLoaded',()=>{makeDnd();initIncidentTemplateAutofill();makeAccessibleMenus();});


function makeMobileMenu(){
  const btn=document.querySelector('.mobile-menu-toggle');
  const nav=document.getElementById('main-nav');
  if(!btn||!nav)return;
  btn.addEventListener('click',()=>{
    const open=!nav.classList.contains('mobile-open');
    nav.classList.toggle('mobile-open',open);
    btn.setAttribute('aria-expanded',String(open));
  });
  nav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{
    if(window.matchMedia('(max-width: 820px)').matches){
      nav.classList.remove('mobile-open');
      btn.setAttribute('aria-expanded','false');
    }
  }));
}

document.addEventListener('DOMContentLoaded',makeMobileMenu);


function makeDeleteConfirmations(){
  const defaultMessage='Confermi la cancellazione? L’operazione non potrà essere annullata.';
  document.querySelectorAll('form').forEach(form=>{
    const action=(form.getAttribute('action')||'').toLowerCase();
    const formLooksDelete=action.includes('/delete') || form.hasAttribute('data-confirm-delete');
    const hasDeleteControl=!!form.querySelector('button.danger, input[type="submit"].danger, input[name="action"][value="delete"], button[name="action"][value*="delete"]');
    if(!formLooksDelete && !hasDeleteControl)return;
    if(form.dataset.confirmAttached==='true')return;
    form.dataset.confirmAttached='true';
    form.addEventListener('submit',ev=>{
      if(form.dataset.confirmed==='true')return;
      const submitter=ev.submitter;
      const submitterAction=(submitter && submitter.getAttribute('value') || '').toLowerCase();
      const submitterIsDelete=!!(submitter && (submitter.classList.contains('danger') || submitterAction.includes('delete') || submitterAction.includes('del_')));
      const mustConfirm=formLooksDelete || submitterIsDelete;
      if(!mustConfirm)return;
      const msg=form.getAttribute('data-confirm-delete') || defaultMessage;
      if(!window.confirm(msg))ev.preventDefault();
      else form.dataset.confirmed='true';
    });
  });
}

document.addEventListener('DOMContentLoaded',makeDeleteConfirmations);


function makeDocumentationSearch(){
  const input=document.getElementById('doc-search-input');
  const count=document.getElementById('doc-search-count');
  const noResults=document.getElementById('doc-no-results');
  if(!input)return;
  const chapters=[...document.querySelectorAll('.doc-chapter')];
  const normalize=s=>(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  const resetHighlights=()=>document.querySelectorAll('.doc-highlight').forEach(span=>span.replaceWith(document.createTextNode(span.textContent)));
  input.addEventListener('input',()=>{
    resetHighlights();
    const q=normalize(input.value.trim());
    let visible=0;
    chapters.forEach(ch=>{
      const hay=normalize(ch.textContent+' '+(ch.dataset.docTitle||''));
      const show=!q || hay.includes(q);
      ch.hidden=!show;
      if(show)visible++;
    });
    if(!q){count.textContent='Digita una parola per filtrare i capitoli.'; if(noResults)noResults.hidden=true; return;}
    count.textContent=visible===1 ? '1 capitolo trovato.' : visible+' capitoli trovati.';
    if(noResults)noResults.hidden=visible!==0;
  });
}

document.addEventListener('DOMContentLoaded',makeDocumentationSearch);

function makeFormMappingDnd(){
  document.querySelectorAll('.draggable-token[draggable=true]').forEach(el=>{
    el.addEventListener('dragstart',e=>{
      e.dataTransfer.setData('text/plain', el.dataset.value || '');
    });
  });
  document.querySelectorAll('input.drop-target').forEach(input=>{
    input.addEventListener('dragover',e=>{e.preventDefault(); input.classList.add('drag-over');});
    input.addEventListener('dragleave',()=>input.classList.remove('drag-over'));
    input.addEventListener('drop',e=>{
      e.preventDefault(); input.classList.remove('drag-over');
      const value=e.dataTransfer.getData('text/plain');
      if(value) input.value=value;
    });
  });
}
document.addEventListener('DOMContentLoaded',makeFormMappingDnd);

// Selezione template PDF nelle pagine incidente: card cliccabili e navigabili da tastiera.
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.template-select-card').forEach(function (card) {
    const input = card.querySelector('.template-select-input');
    if (!input) return;
    const sync = function () { card.classList.toggle('selected', input.checked); };
    input.addEventListener('change', sync);
    card.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        input.checked = !input.checked;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    sync();
  });
});

function preserveIncidentFormAnchor(){
  document.querySelectorAll('form[data-scroll-anchor]').forEach(form=>{
    if(form.dataset.anchorReady==='true')return;
    form.dataset.anchorReady='true';
    form.addEventListener('submit',()=>{
      const anchor=(form.dataset.scrollAnchor||'').replace(/^#/, '');
      if(!anchor)return;
      let input=form.querySelector('input[name="scroll_anchor"]');
      if(!input){
        input=document.createElement('input');
        input.type='hidden';
        input.name='scroll_anchor';
        form.appendChild(input);
      }
      input.value=anchor;
    });
  });
}
document.addEventListener('DOMContentLoaded', preserveIncidentFormAnchor);


function openIncidentSection(section){
  if(!section)return;
  if(section.tagName && section.tagName.toLowerCase()==='details') section.open = true;
  const parent = section.closest && section.closest('details.incident-section-collapsible');
  if(parent) parent.open = true;
}

function scrollToIncidentSection(section){
  if(!section)return;
  openIncidentSection(section);
  section.scrollIntoView({behavior:'smooth', block:'start'});
}

function openInitialIncidentAnchor(){
  const hash=(window.location.hash || '').replace(/^#/, '');
  if(!hash)return;
  const section=document.getElementById(hash);
  if(!section)return;
  openIncidentSection(section);
  window.setTimeout(()=>scrollToIncidentSection(section), 0);
  window.setTimeout(()=>scrollToIncidentSection(section), 100);
}

document.addEventListener('DOMContentLoaded', openInitialIncidentAnchor);
window.addEventListener('hashchange', openInitialIncidentAnchor);

function makeIncidentWorkflowStepsClickable(){
  const actionForm=document.querySelector('#incident-actions form[action*="/actions/add"], #incident-actions form[data-scroll-anchor="incident-actions"]');
  const actionSelect=document.getElementById('new-action-label-id');
  if(!actionForm || !actionSelect)return;
  const description=actionForm.querySelector('textarea[name="description"]');
  const activate=(step)=>{
    if(step.dataset.documentGenerationUrl){
      window.location.href = step.dataset.documentGenerationUrl;
      return;
    }
    if(step.dataset.requiresNotification === '1'){
      if(step.dataset.notificationDocsReady !== '1'){
        const message = step.dataset.notificationDocsMessage || 'Prima dell’invio della notifica sono necessari documenti generati o taggati per questo tipo di notifica.';
        window.alert(message);
        const sectionId = step.dataset.notificationDocsSection || 'incident-forms';
        const section = document.getElementById(sectionId);
        scrollToIncidentSection(section);
        return;
      }
      if(step.dataset.notificationUrl){
        window.location.href = step.dataset.notificationUrl;
        return;
      }
    }
    const labelId=step.dataset.actionLabelId || '';
    if(labelId){
      actionSelect.value=labelId;
      actionSelect.dispatchEvent(new Event('change', {bubbles:true}));
    }
    const target=document.getElementById('incident-actions');
    scrollToIncidentSection(target);
    setTimeout(()=>{
      if(description) description.focus();
      else actionSelect.focus();
    }, 250);
  };
  document.querySelectorAll('.workflow-step-action').forEach(step=>{
    step.addEventListener('click',event=>{
      if(event.target.closest('a')) return;
      activate(step);
    });
    step.addEventListener('keydown',event=>{
      if(event.key==='Enter' || event.key===' '){
        event.preventDefault();
        activate(step);
      }
    });
  });
}
document.addEventListener('DOMContentLoaded', makeIncidentWorkflowStepsClickable);
function initActionDescriptionRequirement(){
  const select=document.getElementById('new-action-label-id');
  const description=document.getElementById('new-action-description');
  const notice=document.getElementById('new-action-description-required-notice');
  if(!select || !description) return;
  function sync(){
    const option=select.selectedOptions && select.selectedOptions[0];
    const required=!!(option && option.dataset.descriptionRequired === '1');
    description.required=required;
    if(notice) notice.hidden=!required;
  }
  select.addEventListener('change', sync);
  sync();
}
document.addEventListener('DOMContentLoaded', initActionDescriptionRequirement);


function initAIChatbotWidget(){
  const widget = document.getElementById('ai-chatbot-widget');
  if(!widget) return;
  const panel = document.getElementById('ai-chatbot-panel');
  const fab = document.getElementById('ai-chatbot-fab');
  const mobileOpen = document.getElementById('ai-chatbot-mobile-open');
  const minimize = document.getElementById('ai-chatbot-minimize');
  const form = document.getElementById('ai-chatbot-form');
  const questionInput = document.getElementById('ai-chatbot-question');
  const messages = document.getElementById('ai-chatbot-messages');
  const askUrl = widget.dataset.askUrl;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

  function adjustWidgetPosition(){
    if(!widget) return;
    if(window.matchMedia && window.matchMedia('(max-width: 820px)').matches){
      widget.classList.remove('collision-adjusted');
      widget.style.removeProperty('--ai-chatbot-safe-bottom');
      widget.style.removeProperty('--ai-chatbot-safe-right');
      return;
    }
    const margin = 18;
    const gap = 16;
    let safeBottom = 128;
    let safeRight = margin;
    const cornerLogo = document.querySelector('.app-corner-logo');
    if(cornerLogo){
      const logoStyle = window.getComputedStyle(cornerLogo);
      const logoVisible = logoStyle.display !== 'none' && logoStyle.visibility !== 'hidden' && cornerLogo.offsetWidth > 0 && cornerLogo.offsetHeight > 0;
      if(logoVisible){
        const rect = cornerLogo.getBoundingClientRect();
        safeBottom = Math.max(safeBottom, Math.round(window.innerHeight - rect.top + gap));
        safeRight = Math.max(margin, Math.round(window.innerWidth - rect.right + margin));
      }
    }
    const maxBottom = Math.max(margin, window.innerHeight - 320);
    safeBottom = Math.min(safeBottom, maxBottom);
    widget.style.setProperty('--ai-chatbot-safe-bottom', safeBottom + 'px');
    widget.style.setProperty('--ai-chatbot-safe-right', safeRight + 'px');
    widget.classList.add('collision-adjusted');
  }

  function setOpen(open){
    if(!panel) return;
    adjustWidgetPosition();
    panel.hidden = !open;
    widget.classList.toggle('open', open);
    if(fab) fab.setAttribute('aria-expanded', open ? 'true' : 'false');
    if(mobileOpen) mobileOpen.setAttribute('aria-expanded', open ? 'true' : 'false');
    if(open){
      setTimeout(adjustWidgetPosition, 80);
    }
    if(open && questionInput) setTimeout(()=>questionInput.focus(), 80);
  }

  function escapeHTML(value){
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function isAllowedMarkdownColor(value){
    return isAllowedSafeMarkdownColor(value);
  }

  function isAllowedMarkdownSize(value){
    return isAllowedSafeMarkdownSize(value);
  }


  function isSafeMarkdownLinkTarget(target){
    target = String(target || '').trim();
    if(!target || /\s/.test(target)) return false;
    const lower = target.toLowerCase();
    if(lower.startsWith('javascript:') || lower.startsWith('data:') || lower.startsWith('vbscript:') || lower.startsWith('file:')) return false;
    if(target.startsWith('//')) return false;
    if(/^[a-z][a-z0-9+.-]*:/i.test(target)){
      return lower.startsWith('http://') || lower.startsWith('https://');
    }
    if(target.startsWith('#') || target.startsWith('?') || target.startsWith('/') || target.startsWith('./') || target.startsWith('../')) return true;
    return /^[A-Za-z0-9._~!$&'()*+,;=:@%/-]+(?:[?#][A-Za-z0-9._~!$&'()*+,;=:@%/?-]*)?$/.test(target);
  }

  function isExternalMarkdownLinkTarget(target){
    const lower = String(target || '').toLowerCase();
    return lower.startsWith('http://') || lower.startsWith('https://');
  }

  function renderInlineChatMarkdown(value){
    return value
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
      .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
      .replace(/\{button:([^|{}\n]{1,80})\|([^\s{}<>"']{1,300})\}/gi, function(match, label, target){
        label = String(label || '').trim();
        target = String(target || '').trim();
        if(!isSafeMarkdownLinkTarget(target)) return label;
        const externalAttrs = isExternalMarkdownLinkTarget(target) ? ' target="_blank" rel="noopener noreferrer"' : '';
        return '<a class="workflow-button-link safe-markdown-button" href="' + target + '"' + externalAttrs + '>' + label + '</a>';
      })
      .replace(/\{color:([^}]+)\}([\s\S]+?)\{\/color\}/gi, function(match, color, body){
        color = (color || '').trim();
        return isAllowedMarkdownColor(color) ? '<span class="safe-markdown-color workflow-markdown-color" data-md-color="' + color.replace(/&quot;/g, '') + '">' + body + '</span>' : body;
      })
      .replace(/\{size:([^}]+)\}([\s\S]+?)\{\/size\}/gi, function(match, size, body){
        size = (size || '').trim().toLowerCase();
        return isAllowedMarkdownSize(size) ? '<span class="safe-markdown-size workflow-markdown-size" data-md-size="' + size.replace(/&quot;/g, '') + '">' + body + '</span>' : body;
      })
      .replace(/(^|\s)(https?:\/\/[^\s<]+)(?=\s|$)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
  }

  function renderChatMarkdown(text){
    const source = escapeHTML(text || '').replace(/\r\n?/g, '\n');
    const lines = source.split('\n');
    const out = [];
    let paragraph = [];
    let listType = null;
    let inCode = false;
    let codeLines = [];

    function flushParagraph(){
      if(paragraph.length){
        out.push(`<p>${renderInlineChatMarkdown(paragraph.join(' '))}</p>`);
        paragraph = [];
      }
    }
    function closeList(){
      if(listType){
        out.push(`</${listType}>`);
        listType = null;
      }
    }

    lines.forEach(line=>{
      if(/^```/.test(line.trim())){
        if(inCode){
          out.push(`<pre><code>${codeLines.join('\n')}</code></pre>`);
          codeLines = [];
          inCode = false;
        }else{
          flushParagraph();
          closeList();
          inCode = true;
        }
        return;
      }
      if(inCode){
        codeLines.push(line);
        return;
      }
      const trimmed = line.trim();
      if(!trimmed){
        flushParagraph();
        closeList();
        return;
      }
      const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed);
      if(heading){
        flushParagraph();
        closeList();
        const level = Math.min(6, Math.max(3, heading[1].length + 2));
        out.push(`<h${level}>${renderInlineChatMarkdown(heading[2])}</h${level}>`);
        return;
      }
      const bullet = /^[-*]\s+(.+)$/.exec(trimmed);
      if(bullet){
        flushParagraph();
        if(listType !== 'ul'){
          closeList();
          out.push('<ul>');
          listType = 'ul';
        }
        out.push(`<li>${renderInlineChatMarkdown(bullet[1])}</li>`);
        return;
      }
      const number = /^\d+\.\s+(.+)$/.exec(trimmed);
      if(number){
        flushParagraph();
        if(listType !== 'ol'){
          closeList();
          out.push('<ol>');
          listType = 'ol';
        }
        out.push(`<li>${renderInlineChatMarkdown(number[1])}</li>`);
        return;
      }
      closeList();
      paragraph.push(trimmed);
    });
    if(inCode) out.push(`<pre><code>${codeLines.join('\n')}</code></pre>`);
    flushParagraph();
    closeList();
    return out.join('') || '<p></p>';
  }


  function appendMessage(text, type){
    if(!messages) return null;
    const node = document.createElement('div');
    node.className = 'ai-chatbot-message ai-chatbot-markdown ' + (type || 'bot');
    if((type || '').includes('pending') || (type || '').includes('error')){
      node.textContent = text;
    }else{
      node.innerHTML = renderChatMarkdown(text);
    }
    messages.appendChild(node);
    applySafeMarkdownStyles(node);
    messages.scrollTop = messages.scrollHeight;
    return node;
  }


  adjustWidgetPosition();
  window.addEventListener('resize', adjustWidgetPosition);
  window.addEventListener('orientationchange', adjustWidgetPosition);

  if(fab) fab.addEventListener('click', ()=>setOpen(true));
  if(mobileOpen) mobileOpen.addEventListener('click', ()=>setOpen(true));
  if(minimize) minimize.addEventListener('click', ()=>setOpen(false));

  if(form){
    form.addEventListener('submit', async (event)=>{
      event.preventDefault();
      const question = (questionInput?.value || '').trim();
      if(!question) return;
      appendMessage(question, 'user');
      if(questionInput) questionInput.value = '';
      const pending = appendMessage('Sto elaborando la risposta...', 'bot pending');
      try{
        const response = await fetch(askUrl, {
          method: 'POST',
          headers: {'Content-Type':'application/json', 'X-CSRFToken': csrf},
          body: JSON.stringify({question})
        });
        const data = await response.json().catch(()=>({ok:false,error:'Risposta non valida dal server.'}));
        if(pending) pending.remove();
        appendMessage(data.ok ? data.answer : (data.error || 'Errore durante la risposta del chatbot.'), data.ok ? 'bot' : 'bot error');
      }catch(err){
        if(pending) pending.remove();
        appendMessage('Errore di comunicazione con il chatbot.', 'bot error');
      }
    });
  }
}
document.addEventListener('DOMContentLoaded', ()=>{
  applySafeMarkdownStyles(document);
  initAIChatbotWidget();
});

function initLdapRecipientLookup(){
  document.querySelectorAll('.ldap-recipient-loader').forEach(box=>{
    const input=box.querySelector('.ldap-recipient-query');
    const button=box.querySelector('.ldap-recipient-search-button');
    const results=box.querySelector('.ldap-recipient-results');
    function setValue(id, value){ const el=id ? document.getElementById(id) : null; if(el && value) el.value=value; }
    async function search(){
      const q=(input && input.value || '').trim();
      if(q.length < 2){ results.innerHTML='<p class="muted">Inserire almeno 2 caratteri.</p>'; return; }
      results.innerHTML='<p class="muted">Ricerca LDAP in corso...</p>';
      try{
        const response=await fetch(box.dataset.searchUrl + '?q=' + encodeURIComponent(q), {credentials:'same-origin', headers:{'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}});
        const contentType=(response.headers.get('content-type') || '').toLowerCase();
        let data={ok:false,error:'Risposta non valida dal server.'};
        if(contentType.includes('application/json')){
          data=await response.json().catch(()=>({ok:false,error:'Risposta JSON non valida dal server.'}));
        }else{
          const text=await response.text().catch(()=>'');
          const loginHint=/login|accedi|password/i.test(text) ? ' Sessione scaduta o accesso richiesto: ricaricare la pagina ed effettuare di nuovo il login.' : '';
          throw new Error('La ricerca LDAP non ha restituito JSON valido.' + loginHint);
        }
        if(!response.ok || !data.ok){ throw new Error(data.error || 'Ricerca non riuscita'); }
        if(!data.entries || !data.entries.length){ results.innerHTML='<p class="muted">Nessun utente LDAP trovato.</p>'; return; }
        results.innerHTML='';
        const attrOrder=Array.isArray(data.attribute_order) ? data.attribute_order : [];
        data.entries.forEach(entry=>{
          const row=document.createElement('div'); row.className='ldap-recipient-result ldap-recipient-result-expanded';
          const details=document.createElement('div'); details.className='ldap-recipient-result-details';
          const title=document.createElement('strong'); title.textContent=(entry.reference || entry.recipient || entry.dn || 'Utente LDAP') + (entry.email ? ' <' + entry.email + '>' : '');
          details.appendChild(title);
          const attrs=entry.attributes || {};
          const keys=attrOrder.length ? attrOrder : Object.keys(attrs);
          if(keys.length){
            const table=document.createElement('table'); table.className='ldap-recipient-attributes compact-table';
            const tbody=document.createElement('tbody');
            keys.forEach(key=>{
              if(!Object.prototype.hasOwnProperty.call(attrs, key))return;
              const tr=document.createElement('tr');
              const th=document.createElement('th'); th.textContent=key;
              const td=document.createElement('td'); td.textContent=attrs[key] || '—';
              tr.appendChild(th); tr.appendChild(td); tbody.appendChild(tr);
            });
            table.appendChild(tbody); details.appendChild(table);
          }
          const use=document.createElement('button'); use.type='button'; use.className='secondary small'; use.textContent='Seleziona';
          use.addEventListener('click', ()=>{ setValue(box.dataset.referenceTarget, entry.reference); setValue(box.dataset.recipientTarget, entry.recipient || entry.reference); setValue(box.dataset.emailTarget, entry.email); results.innerHTML=''; if(input) input.value=''; });
          row.appendChild(details); row.appendChild(use); results.appendChild(row);
        });
      }catch(e){ results.innerHTML='<p class="error">'+String(e.message || e)+'</p>'; }
    }
    if(button) button.addEventListener('click', search);
    if(input) input.addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); search(); }});
  });
}
document.addEventListener('DOMContentLoaded', initLdapRecipientLookup);
