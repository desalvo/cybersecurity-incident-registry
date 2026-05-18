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
      i.type='hidden';i.name=zone.dataset.target;i.value=d.id;
      s.appendChild(i);zone.appendChild(s);makeSelectedRemovable();
    });
  });
  makeSelectedRemovable();
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

document.addEventListener('DOMContentLoaded',()=>{makeDnd();makeAccessibleMenus();});


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
    const hasDeleteAction=action.includes('/delete');
    const hasDeleteButton=!!form.querySelector('button.danger, input[type="submit"].danger, input[name="action"][value="delete"]');
    if(!hasDeleteAction && !hasDeleteButton)return;
    if(form.dataset.confirmAttached==='true')return;
    form.dataset.confirmAttached='true';
    form.addEventListener('submit',ev=>{
      if(form.dataset.confirmed==='true')return;
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
