(function(){
  if ((window.CIR_LANG || 'it') !== 'en') return;
  const D = {
    'Salta al contenuto principale':'Skip to main content','Apri o chiudi menu':'Open or close menu','Menu principale':'Main menu','Utente corrente':'Current user',
    'Incidenti':'Incidents','Export incidenti in CSV':'Export incidents to CSV','Export completo':'Full export','CSV import':'CSV import','Full import':'Full import','Report':'Reports','Statistiche':'Statistics',
    'Notifiche':'Notifications','Tipi di notifica':'Notification types','Aggiungi template':'Add template','Moduli':'Forms','Configurazione':'Configuration','Impostazioni':'Settings','Cambio password':'Change password','Multi-factor authentication':'Multi-factor authentication',
    'Admin':'Admin','Liste configurabili':'Configurable lists','Personale':'Personnel','Logo':'Logo','Utenti':'Users','Dati titolare':'Controller data','Struttura':'Structure','Dati responsabile':'Responsible person data','Raccomandazioni':'Recommendations','Altre configurazioni':'Other settings',
    'Aiuto':'Help','Documentazione':'Documentation','Scarica documentazione PDF':'Download documentation PDF','Documentazione amministrativa':'Administrator documentation','Scarica documentazione amministrativa PDF':'Download administrator documentation PDF','Info':'Info','Applicazione':'Application',
    'Nuovo incidente':'New incident','Modifica incidente':'Edit incident','Salva':'Save','Salva configurazione':'Save settings','Annulla':'Cancel','Elimina':'Delete','Cerca':'Search','Filtra':'Filter','Reset':'Reset','Azioni':'Actions','Documenti':'Documents','Stato':'Status','Descrizione':'Description','Nome':'Name','Riferimento':'Reference','Destinatario':'Recipient','Gravità':'Severity','Categorie':'Categories','Dati interessati':'Affected data','Dati personali':'Personal data','Data inizio':'Start date','Ora inizio':'Start time','Data fine':'End date','Ora fine':'End time','Aperto':'Open','Chiuso':'Closed',
    'Avvisi procedurali':'Procedural warnings','Timeline azioni':'Action timeline','Aggiungi azione':'Add action','Label azioni':'Action labels','Tempo massimo (ore)':'Maximum time (hours)','Esportabile per default':'Exportable by default','Esportabile':'Exportable','Ritenzione audit log':'Audit log retention','Mesi':'Months','Giorni':'Days','Ore':'Hours','Minuti':'Minutes','Time zone applicazione':'Application time zone','URL applicazione':'Application URL','Lingua interfaccia':'Interface language','Automatica dal browser':'Automatic from browser','Italiano':'Italian','Inglese':'English',
    'Data e ora':'Date and time','Tipo operazione':'Operation type','Utente':'User','Origine':'Source','Dettagli':'Details','Da':'From','A':'To','Tutte':'All','Risultati':'Results','Nessun risultato':'No result',
    'Accedi':'Sign in','Username':'Username','Password':'Password','Logout':'Logout','Password attuale':'Current password','Nuova password':'New password','Conferma nuova password':'Confirm new password'
  };
  function tr(s){ const k=(s||'').replace(/\s+/g,' ').trim(); return D[k] || null; }
  function walk(n){
    if (['SCRIPT','STYLE','TEXTAREA','CODE','PRE'].includes(n.nodeName)) return;
    if (n.nodeType===3){ const t=tr(n.nodeValue); if(t) n.nodeValue=n.nodeValue.replace(n.nodeValue.trim(),t); return; }
    if (n.nodeType===1){ ['title','aria-label','placeholder','value'].forEach(a=>{ if(n.hasAttribute(a)){ const t=tr(n.getAttribute(a)); if(t) n.setAttribute(a,t); }}); }
    Array.from(n.childNodes).forEach(walk);
  }
  document.addEventListener('DOMContentLoaded',()=>walk(document.body));
})();
