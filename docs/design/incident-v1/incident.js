'use strict';
/* Isolated review prototype: data and interactions stay in memory.
   Embedded fixtures match fixtures.json. Shared menus match the approved home. */
const FIXTURE = {
  "schema_version": 1,
  "mock": true,
  "snapshot_at": "2026-11-22T12:00:00+01:00",
  "user": {
    "username": "admin.operativo",
    "name": "Admin operativo",
    "initials": "AO",
    "role": "superuser",
    "role_label": "Super admin",
    "auth_provider": "local"
  },
  "capabilities": {
    "modules_enabled": true,
    "alfresco_enabled": true,
    "chatbot_enabled": true,
    "alfresco_auto_report_visible": true
  },
  "incident": {
    "id": 48,
    "tenant": "default",
    "creator": "admin.operativo",
    "creator_name": "Operatore A",
    "creator_email": "operatore-a@example.invalid",
    "name": "Esfiltrazione sospetta da server applicativo",
    "reference": "INC-2026-0048",
    "status": "aperto",
    "status_label": "Aperto",
    "severity": "Alta",
    "severity_id": 3,
    "start_at": "2026-11-22T09:42",
    "end_at": "",
    "duration": "2h 18m",
    "people": "Operatore A, Analista B",
    "description": "Rilevato un trasferimento di dati non atteso dal server applicativo di test. Sono in corso la conservazione delle evidenze e la valutazione dei dati coinvolti.",
    "recipient": "Responsabile del servizio · demo",
    "recipient_email": "responsabile@example.invalid",
    "personal_data": true,
    "data_subjects_count": "In corso di valutazione",
    "data_volume": "Quantità e tipologia dei dati in corso di valutazione.",
    "deadline_notifications_muted": false,
    "alfresco_auto_report_enabled": true,
    "categories": [
      "Accesso non autorizzato",
      "Esfiltrazione sospetta"
    ],
    "data_types": [
      "Dati applicativi"
    ],
    "recommendations": [
      "Verificare e limitare le autorizzazioni di accesso."
    ]
  },
  "workflow": {
    "name": "Gestione data breach · esempio",
    "lifecycle": "current",
    "ordered": true,
    "completed": 1,
    "total": 4,
    "steps": [
      {
        "id": 101,
        "number": 1,
        "flow_title": "Presa in carico",
        "flow_description": "Registrare la conoscenza iniziale della violazione e le prime informazioni disponibili.",
        "task_description": "Registrazione azione",
        "task_name": "Informazione iniziale",
        "action_label_id": 101,
        "status": "completed",
        "status_label": "Completata",
        "detail": "Registrata il 22/11/2026 alle 09:42",
        "required": true,
        "done": true,
        "first_incomplete": false,
        "expired": false,
        "deadline": null,
        "action": {
          "kind": "action",
          "target": "incident-actions",
          "label": "Apri azioni",
          "route": "main.add_action"
        }
      },
      {
        "id": 102,
        "number": 2,
        "flow_title": "Conservazione delle evidenze",
        "flow_description": "Raccogliere log e riscontri tecnici e descrivere le operazioni effettuate per conservarli.",
        "task_description": "Registrazione azione",
        "task_name": "Conservazione delle evidenze",
        "action_label_id": 102,
        "status": "current",
        "status_label": "Prima fase da completare",
        "detail": "Descrizione operazioni richiesta",
        "required": true,
        "done": false,
        "first_incomplete": true,
        "expired": false,
        "deadline": {
          "hours": 4,
          "due_at": "22/11/2026 13:42",
          "due_short": "13:42",
          "remaining": "1h 42m",
          "label": "Scadenza configurata"
        },
        "action": {
          "kind": "action",
          "target": "incident-actions",
          "label": "Registra azione",
          "route": "main.add_action"
        }
      },
      {
        "id": 103,
        "number": 3,
        "flow_title": "Valutazione e documentazione",
        "flow_description": "Riepilogare la valutazione dei dati coinvolti e predisporre il documento per la notifica.",
        "task_description": "Generazione documento",
        "task_name": "Scheda di valutazione",
        "action_label_id": 103,
        "status": "pending",
        "status_label": "Da completare",
        "detail": "Template: scheda-valutazione",
        "required": true,
        "done": false,
        "first_incomplete": false,
        "expired": false,
        "document_template_name": "scheda-valutazione",
        "deadline": null,
        "action": {
          "kind": "generation",
          "target": "incident-forms",
          "label": "Genera documento",
          "route": "main.workflow_step_generate_document"
        }
      },
      {
        "id": 104,
        "number": 4,
        "flow_title": "Comunicazione al responsabile",
        "flow_description": "Verificare destinatari e allegati prima di procedere con la notifica prevista dal workflow.",
        "task_description": "Notifica richiesta",
        "task_name": "Notifica al responsabile",
        "action_label_id": 104,
        "status": "pending",
        "status_label": "Documento richiesto",
        "detail": "Manca la scheda di valutazione",
        "required": true,
        "done": false,
        "first_incomplete": false,
        "expired": false,
        "notification_done": false,
        "notification_kind": "responsabile",
        "notification_docs_ready": false,
        "notification_docs_section": "incident-forms",
        "document_template_name": "scheda-valutazione",
        "deadline": null,
        "action": {
          "kind": "notification",
          "target": "incident-notifications",
          "label": "Apri percorso guidato",
          "route": "main.notify_preview"
        }
      }
    ],
    "warnings": [
      "Conservazione delle evidenze: azione richiesta non ancora registrata.",
      "Scheda di valutazione: documento da generare.",
      "Notifica al responsabile: documento richiesto non ancora disponibile."
    ],
    "deadline_note": "Tempi configurati per questo esempio; il conteggio parte dall’azione di informazione iniziale."
  },
  "actions": [
    {
      "id": 301,
      "label": "Informazione iniziale",
      "when_at": "2026-11-22T09:42",
      "person": "Operatore A",
      "description": "Segnalato un trasferimento di dati non atteso dal server applicativo di test. Avviata la presa in carico.",
      "consequence": "Possibile accesso non autorizzato a dati applicativi; valutazione in corso.",
      "exportable": true,
      "attachments": []
    },
    {
      "id": 302,
      "label": "Isolamento preventivo",
      "when_at": "2026-11-22T10:10",
      "person": "Analista B",
      "description": "Limitate le connessioni in uscita del servizio di test e annotate le modifiche effettuate.",
      "consequence": "Servizio di test temporaneamente limitato.",
      "exportable": true,
      "attachments": [
        {
          "id": 411,
          "name": "nota-intervento-demo.txt"
        }
      ]
    }
  ],
  "documents": [
    {
      "id": 501,
      "name": "estratto-log-demo.zip",
      "uploaded_at": "22/11/2026 10:24",
      "size": "2,4 MB",
      "storage": "CIR + Alfresco",
      "local": true,
      "alfresco": true,
      "alfresco_status": "Presente",
      "tags": [],
      "generated_template": null,
      "download_allowed": true
    },
    {
      "id": 502,
      "name": "nota-tecnica-demo.pdf",
      "uploaded_at": "22/11/2026 10:36",
      "size": "184 KB",
      "storage": "Solo CIR",
      "local": true,
      "alfresco": false,
      "alfresco_status": "Non inviato",
      "tags": [],
      "generated_template": null,
      "download_allowed": true
    }
  ],
  "reminders": [
    {
      "id": 601,
      "scheduled_at": "2026-11-22T13:15",
      "message": "Verificare la conservazione delle evidenze e aggiornare la valutazione.",
      "cc_emails": "",
      "status": "Da inviare"
    }
  ],
  "forms": [
    {
      "name": "scheda-valutazione",
      "title": "Scheda di valutazione",
      "description": "Valutazione dei dati coinvolti e delle conseguenze.",
      "required_for_notification": true,
      "selected": true
    },
    {
      "name": "verbale-intervento",
      "title": "Verbale di intervento",
      "description": "Riepilogo delle operazioni svolte e delle misure adottate.",
      "required_for_notification": false,
      "selected": false
    }
  ],
  "notifications": [
    {
      "kind": "responsabile",
      "title": "Notifica al responsabile",
      "description": "Documento richiesto: scheda di valutazione.",
      "ready": false,
      "button": "Apri percorso guidato"
    },
    {
      "kind": "aggiornamento",
      "title": "Aggiornamento operativo",
      "description": "Verifica destinatari, testo e allegati nell’anteprima.",
      "ready": true,
      "button": "Anteprima notifica"
    }
  ],
  "owner": {
    "name": "Organizzazione dimostrativa",
    "email": "titolare@example.invalid",
    "contact": "Segreteria · demo"
  },
  "responsible": {
    "name": "Responsabile operativo · demo",
    "email": "responsabile@example.invalid",
    "contact": "Servizio sistemi · demo"
  },
  "sections": [
    {
      "id": "incident-workflow",
      "title": "Fasi procedurali",
      "short": "Fasi",
      "open": true
    },
    {
      "id": "incident-procedural-alerts",
      "title": "Avvisi procedurali",
      "short": "Avvisi",
      "count": 3,
      "open": false
    },
    {
      "id": "incident-main",
      "title": "Dati generali",
      "short": "Dati generali",
      "open": true
    },
    {
      "id": "incident-owner",
      "title": "Dati titolare e responsabile",
      "short": "Titolare e responsabile",
      "open": false
    },
    {
      "id": "incident-consequences",
      "title": "Conseguenze, misure e raccomandazioni",
      "short": "Conseguenze e misure",
      "open": false
    },
    {
      "id": "incident-actions",
      "title": "Azioni",
      "short": "Azioni",
      "count": 2,
      "open": false
    },
    {
      "id": "incident-reminders",
      "title": "Promemoria specifici",
      "short": "Promemoria",
      "count": 1,
      "open": false
    },
    {
      "id": "incident-documents",
      "title": "Documenti",
      "short": "Documenti",
      "count": 2,
      "open": false
    },
    {
      "id": "incident-forms",
      "title": "Generazione moduli",
      "short": "Moduli",
      "open": false
    },
    {
      "id": "incident-notifications",
      "title": "Notifiche",
      "short": "Notifiche",
      "open": false
    }
  ]
};
const MENUS = {
 export:[['Export incidenti in CSV','main.export_csv'],['Export completo','main.export_full'],['Export bootstrap anonimizzato','main.export_full?mode=bootstrap','superuser'],['Import CSV','main.import_csv'],['Import completo','main.import_full']],
 notifications:[['Tipi di notifica','main.notification_types'],['Aggiungi template','main.notification_template_new'],['Template notifica iniziale · esempio','main.notification_template?kind=initial']],
 modules:[['Configurazione moduli','main.modules_configuration']],
 workflows:[['Catalogo workflow','main.admin_workflow_catalog'],['Flussi operativi incidenti','main.admin_incident_workflows'],['Avvisi defaults','main.admin_tenant_defaults_alerts'],['Avvisi workflow','main.admin_workflow_catalog_notices'],['Modelli incidente','main.admin_incident_templates'],['Liste configurabili','main.admin_labels'],['Layout campi incidenti','main.admin_incident_form_fields'],['Azioni automatiche pulsanti','main.admin_incident_button_actions']],
 configuration:[['Configurazione generale',null],['Wizard setup iniziale','main.admin_setup_wizard'],['Altre configurazioni','main.admin_other_configurations'],['Campi personalizzati','main.admin_incident_custom_fields'],['Logo','main.admin_logo'],['HTTPS / SSL','main.admin_ssl'],['Backup','main.admin_backups'],['Struttura','main.admin_structure'],['Dati titolare','main.admin_security_owner'],['Dati responsabile','main.admin_security_responsible'],['Anagrafiche',null],['Personale','main.admin_people'],['Destinatari esterni','main.admin_external_recipients'],['Raccomandazioni','main.admin_recommendations'],['Plugin',null],['Chatbot AI','ai_chatbot.admin_plugins'],['Alfresco','alfresco.admin_plugins']],
 access:[['Tenant','main.admin_tenants','superuser'],['Utenti','main.admin_users'],['LDAP','main.ldap_settings'],['SSO','main.sso_settings_admin']],
 audit:[['Stato applicazione','main.admin_status'],['Audit','main.admin_audit']],
 help:[['Documentazione utente','main.help_page'],['Documentazione amministrativa','main.admin_help_page'],['Note di rilascio','main.release_notes'],['AlBot · plugin opzionale','ai_chatbot.chat']],
 settings:[['Cambio password','main.change_password'],['Autenticazione a più fattori','main.mfa_settings'],['Notifiche','main.notification_settings','admin'],['Destinatari esterni','main.settings_external_recipients','writer'],['Interfaccia globale · anteprima','preview.global_ui','superuser']],
 account:[['Impostazioni','menu.settings'],['Informazioni applicazione','main.app_info'],['Logout','main.logout']]
};
const ICONS={list:'M4 5h16M4 12h16M4 19h16',chart:'M4 20V9m8 11V4m8 16V12',bell:'M5 17h14l-2-3V9a5 5 0 0 0-10 0v5l-2 3M10 21h4',file:'M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6',arrows:'M4 7h15l-4-4M20 17H5l4 4',workflow:'M4 4h6v6H4zM14 14h6v6h-6zM7 10v7h7',gear:'M12 4l2 3 4 1-1 4 1 4-4 1-2 3-2-3-4-1 1-4-1-4 4-1zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',layers:'M3 8l9-5 9 5-9 5zM3 13l9 5 9-5M3 18l9 5 9-5',users:'M8 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8M2 21v-3a6 6 0 0 1 12 0v3M17 4a4 4 0 0 1 0 8m1 3a5 5 0 0 1 4 5',shield:'M12 3l8 3v7c0 5-8 8-8 8s-8-3-8-8V6zM8 12l3 3 5-6',help:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4M12 17h.01'};
const INCIDENT_ENDPOINTS = {
  "main.add_action": {
    "route": "/incident/<int:iid>/action",
    "methods": [
      "POST"
    ],
    "line": 4631
  },
  "main.add_incident_reminder": {
    "route": "/incident/<int:iid>/reminder/add",
    "methods": [
      "POST"
    ],
    "line": 4414
  },
  "main.clone": {
    "route": "/incident/<int:iid>/clone",
    "methods": [
      "POST"
    ],
    "line": 4505
  },
  "main.confirm_generated_forms": {
    "route": "/incident/<int:iid>/forms/confirm",
    "methods": [
      "POST"
    ],
    "line": 14190
  },
  "main.del_action": {
    "route": "/action/<int:aid>/delete",
    "methods": [
      "POST"
    ],
    "line": 4693
  },
  "main.del_action_attachment": {
    "route": "/action-attachment/<int:att_id>/delete",
    "methods": [
      "POST"
    ],
    "line": 4721
  },
  "main.del_doc": {
    "route": "/document/<int:did>/delete",
    "methods": [
      "POST"
    ],
    "line": 4933
  },
  "main.delete_doc_from_alfresco": {
    "route": "/document/<int:did>/alfresco/delete",
    "methods": [
      "POST"
    ],
    "line": 4870
  },
  "main.delete_incident_reminder": {
    "route": "/incident/reminder/<int:rid>/delete",
    "methods": [
      "POST"
    ],
    "line": 4467
  },
  "main.download_action_attachment": {
    "route": "/action-attachment/<int:att_id>/download",
    "methods": [
      "GET"
    ],
    "line": 4713
  },
  "main.download_doc": {
    "route": "/document/<int:did>/download",
    "methods": [
      "GET"
    ],
    "line": 4811
  },
  "main.download_doc_from_alfresco": {
    "route": "/document/<int:did>/alfresco/download",
    "methods": [
      "GET"
    ],
    "line": 4852
  },
  "main.generate_incident_forms": {
    "route": "/incident/<int:iid>/forms/generate",
    "methods": [
      "POST"
    ],
    "line": 14145
  },
  "main.incident_delete": {
    "route": "/incident/<int:iid>/delete",
    "methods": [
      "POST"
    ],
    "line": 4496
  },
  "main.incident_detail": {
    "route": "/incident/<int:iid>",
    "methods": [
      "GET",
      "POST"
    ],
    "line": 4194
  },
  "main.notify_preview": {
    "route": "/incident/<int:iid>/notify/<kind>/preview",
    "methods": [
      "GET"
    ],
    "line": 10462
  },
  "main.notify_send": {
    "route": "/incident/<int:iid>/notify/<kind>/send",
    "methods": [
      "POST"
    ],
    "line": 10501
  },
  "main.pdf": {
    "route": "/incident/<int:iid>/pdf",
    "methods": [
      "GET"
    ],
    "line": 12303
  },
  "main.preview_generated_form_file": {
    "route": "/incident/<int:iid>/forms/preview-file/<path:stored_name>",
    "methods": [
      "GET"
    ],
    "line": 14178
  },
  "main.sync_incident_alfresco_documents": {
    "route": "/incident/<int:iid>/alfresco/sync-documents",
    "methods": [
      "POST"
    ],
    "line": 4897
  },
  "main.update_action": {
    "route": "/action/<int:aid>/update",
    "methods": [
      "POST"
    ],
    "line": 4658
  },
  "main.update_document_notification_tags": {
    "route": "/document/<int:did>/notification-tags",
    "methods": [
      "POST"
    ],
    "line": 4947
  },
  "main.update_incident_reminder": {
    "route": "/incident/reminder/<int:rid>/update",
    "methods": [
      "POST"
    ],
    "line": 4440
  },
  "main.upload": {
    "route": "/incident/<int:iid>/upload",
    "methods": [
      "POST"
    ],
    "line": 4734
  },
  "main.upload_doc_to_alfresco": {
    "route": "/document/<int:did>/alfresco/upload",
    "methods": [
      "POST"
    ],
    "line": 4836
  },
  "main.workflow_step_generate_document": {
    "route": "/incident/<int:iid>/workflow-step/<int:sid>/document",
    "methods": [
      "GET"
    ],
    "line": 14111
  }
};


const state = {tenant: 'default', role: 'superuser', user: 'admin.operativo', previewNewUI: true, dialogContext: null, lastDestination: null, notificationDocsReady: false, missingGenerationFields: [], capabilities: {...FIXTURE.capabilities}, selectedLabels: {}};
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const admin = () => ['superuser','admin'].includes(state.role);
const superuser = () => state.role === 'superuser';
const availableTenantIds = () => superuser() ? ['default','laboratorio','defaults'] : state.role === 'disabled' ? [] : ['default'];
const canView = () => availableTenantIds().includes(state.tenant) && state.tenant === FIXTURE.incident.tenant && ['superuser','admin','writer','reader','operator'].includes(state.role) && (state.role !== 'operator' || FIXTURE.incident.creator === state.user);
const canWrite = () => canView() && ['superuser','admin','writer'].includes(state.role);
const canNotify = () => canWrite() && state.user !== 'admin';
const fmt = value => {if (!value) return '—'; const [d,t] = value.split('T'); return d.split('-').reverse().join('/') + (t ? ' ' + t : '');};
const icon = name => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="'+ICONS[name]+'"/></svg>';
const badge = (label,kind='neutral') => '<span class="pill '+kind+'">'+esc(label)+'</span>';
const endpointButton = (label,endpoint,css='secondary small',attrs='') => '<button type="button" class="'+css+'" data-endpoint="'+endpoint+'" '+attrs+'>'+esc(label)+'</button>';
const sectionButton = (label,target,css='secondary small') => '<button type="button" class="'+css+'" data-section="'+target+'">'+esc(label)+'</button>';
const routeAttrs = params => Object.entries(params).map(([key,value]) => 'data-'+key+'="'+esc(value)+'"').join(' ');
const field = (label,input,wide='') => '<label class="field '+wide+'"><span>'+esc(label)+'</span>'+input+'</label>';
const input = (name,value,type='text',attrs='') => '<input name="'+name+'" value="'+esc(value)+'" type="'+type+'" '+attrs+'>';
const area = (name,value) => '<textarea name="'+name+'">'+esc(value)+'</textarea>';
const select = (name,options,value,attrs='') => '<select name="'+name+'" '+attrs+'>'+options.map(o=>'<option value="'+esc(o[0])+'" '+(String(value)===String(o[0])?'selected':'')+'>'+esc(o[1])+'</option>').join('')+'</select>';
const tags = items => '<div class="tag-row">'+items.map(value=>'<span class="tag">'+esc(value)+'</span>').join('')+'</div>';
const fixedNow = () => FIXTURE.snapshot_at.slice(0,16);

function section(id,body) {
  const spec = FIXTURE.sections.find(s=>s.id===id);
  return '<details class="section-card" id="'+id+'" '+(spec.open?'open':'')+'><summary><h2>'+esc(spec.title)+'</h2>'+(spec.count?'<span class="count">'+spec.count+'</span>':'')+(id==='incident-workflow'?'<span class="summary-detail">'+FIXTURE.workflow.completed+' / '+FIXTURE.workflow.total+' completate</span>':'')+'</summary><div class="section-body">'+body+'</div></details>';
}
function nav() {
  const entries=[['Incidenti','list','registry','all'],['Statistiche','chart','stats','all'],['Notifiche','bell','notifications','admin'],['Moduli','file','modules','admin'],['Import / Export','arrows','export','all'],['AMMINISTRAZIONE'],['Workflow e catalogo','workflow','workflows','admin'],['Configurazione tenant','gear','configuration','admin'],['Tenants Default','layers','defaults','superuser'],['Utenti e accessi','users','access','admin'],['Stato e audit','shield','audit','admin'],['SUPPORTO'],['Aiuto','help','help','all'],['Impostazioni','gear','settings','all']];
  $('nav-items').innerHTML=entries.filter(e=>e.length===1?(e[0]!=='AMMINISTRAZIONE'||admin()):((e[2]!=='modules'||state.capabilities.modules_enabled)&&(state.role!=='disabled'||['help','settings'].includes(e[2]))&&(e[3]==='all'||e[3]==='admin'&&admin()||e[3]==='superuser'&&superuser()))).map(e=>e.length===1?'<div class="nav-section-label">'+e[0]+'</div>':'<button type="button" class="nav-item '+(e[2]==='registry'?'active':'')+'" data-action="'+e[2]+'" '+(e[2]==='registry'?'aria-current="page"':'')+'>'+icon(e[1])+'<span>'+e[0]+'</span>'+(e[2]==='registry'?'':'<span class="arrow">›</span>')+'</button>').join('');
}
function workflowHTML() {
  const steps=FIXTURE.workflow.steps;
  return '<p class="section-intro">'+esc(FIXTURE.workflow.name)+' · Descrizione del flusso in alto, task e comando operativo nel riquadro inferiore.</p><div class="progress-line"><span class="progress-track" role="progressbar" aria-label="Fasi completate" aria-valuemin="0" aria-valuemax="'+steps.length+'" aria-valuenow="'+FIXTURE.workflow.completed+'"><span style="width:'+(100*FIXTURE.workflow.completed/steps.length)+'%"></span></span><span class="progress-label">'+FIXTURE.workflow.completed+' di '+steps.length+' fasi completate</span></div><div class="workflow-steps">'+steps.map((s,idx)=>(idx&&FIXTURE.workflow.ordered?'<span class="workflow-arrow" aria-hidden="true"></span>':'')+'<article class="workflow-block '+s.status+(s.first_incomplete?' first-incomplete':'')+(s.expired&&!s.done?' expired':'')+'" aria-label="Fase '+s.number+': '+esc(s.flow_title)+'"><div class="workflow-flow"><div class="workflow-topline"><span class="step-number">'+s.number+'</span>'+(s.first_incomplete?'<span class="first-marker"><span aria-hidden="true">➜</span> Prima fase da completare</span>':'<span class="step-status">'+(s.done?'✓ ':'○ ')+esc(s.status_label)+'</span>')+'</div><h3>'+esc(s.flow_title)+'</h3><p>'+esc(s.flow_description)+'</p></div><div class="workflow-task" ' +(canWrite()?'data-step="'+s.id+'"':'')+'><p class="task-type">'+esc(s.task_description)+'</p><h4>'+esc(s.task_name)+'</h4><p>'+esc(s.detail)+'</p>'+(s.deadline&&!s.done?'<p class="deadline">'+esc(s.deadline.label)+': <strong>'+esc(s.deadline.due_short)+'</strong><br>'+s.deadline.hours+' ore · Restano <strong>'+esc(s.deadline.remaining)+'</strong>'+(s.expired?' · <strong>Critico</strong>':'')+'</p>':'')+'<div class="task-button-space"></div>'+(canWrite()?'<button type="button" class="'+(s.first_incomplete?'primary':'secondary')+'" data-step="'+s.id+'">'+esc(s.action.label)+'</button>':sectionButton('Visualizza sezione',s.action.target,'secondary'))+'</div></article>').join('')+'</div><div class="workflow-caption"><span>Le fasi seguono le condizioni e i tempi configurati nel workflow.</span><button type="button" data-section="incident-procedural-alerts">! '+FIXTURE.workflow.warnings.length+' avvisi procedurali</button></div>';
}
function generalHTML() {
  const i=FIXTURE.incident;
  const top=field('Riferimento',input('reference',i.reference,'text','required'))+field('Gravità',select('severity_id',[[1,'Bassa'],[2,'Media'],[3,'Alta']],i.severity_id))+field('Stato',select('status',[['aperto','Aperto'],['in lavorazione','In lavorazione'],['chiuso','Chiuso']],i.status))+field('Inizio violazione',input('start_summary',fmt(i.start_at),'text','readonly aria-label="Inizio; modifica data e ora negli altri dati"'))+field('Descrizione',area('description',i.description),'full');
  const dates=[['Data inizio','start_date','date',i.start_at.slice(0,10),'incident-start-date'],['Ora inizio','start_time','time',i.start_at.slice(11),'incident-start-time'],['Data fine','end_date','date','','incident-end-date'],['Ora fine','end_time','time','','incident-end-time']].map(([label,name,type,value,id])=>field(label,'<span class="input-with-button">'+input(name,value,type,'id="'+id+'"')+'<button type="button" class="secondary" data-now="'+(name.startsWith('start')?'start':'end')+'">Adesso</button></span>')).join('');
  const advanced=field('Nome',input('name',i.name,'text','required'),'full')+field('Destinatario',input('recipient',i.recipient),'wide')+field('E-mail destinatario',input('recipient_email',i.recipient_email,'email'),'wide')+'<div class="field full"><div class="button-row"><button type="button" class="secondary small" data-local="external-recipient">Cerca destinatario esterno</button><button type="button" class="secondary small" data-local="ldap-recipient">Cerca in LDAP</button></div><span class="muted">Ricerca disponibile secondo la configurazione del tenant.</span></div>'+dates+'<div class="field full"><label class="checkbox-line"><input type="checkbox" name="personal_data" '+(i.personal_data?'checked':'')+'> Rischio per diritti e libertà</label></div><div class="field full"><label class="checkbox-line"><input type="checkbox" name="deadline_notifications_muted" '+(i.deadline_notifications_muted?'checked':'')+'> Silenzia notifiche email per task in scadenza su questo incidente</label></div>'+(state.capabilities.alfresco_enabled&&state.capabilities.alfresco_auto_report_visible?'<div class="field full"><label class="checkbox-line"><input type="checkbox" name="alfresco_auto_report_enabled" '+(i.alfresco_auto_report_enabled?'checked':'')+'> Genera e aggiorna automaticamente report su Alfresco</label></div>':'')+field('Numero di interessati',input('data_subjects_count',i.data_subjects_count),'wide')+field('Volume dati',area('data_volume',i.data_volume),'wide')+'<div class="field full"><h3 class="section-subheading">Campi personalizzati · esempi</h3></div>'+field('Servizio interessato',input('custom_servizio','Servizio applicativo di test'),'wide')+field('Data verifica',input('custom_verifica','2026-11-22T11:30','datetime-local'),'wide')+field('Codice riservato · dimostrativo','<span class="input-with-button">'+input('custom_codice','DEMO-NON-SEGRETO','password','id="custom-demo-secret" autocomplete="off"')+'<button type="button" class="secondary" data-reveal="custom-demo-secret">Mostra</button></span>','wide')+'<div class="field wide"><label class="checkbox-line"><input type="checkbox" name="custom_verificato"> Verifica completata</label></div>';
  return '<p class="section-intro">Compilatore: '+esc(i.creator_name)+' · '+esc(i.creator_email)+'</p>'+(!canWrite()?'<div class="read-only-note">Consultazione: il ruolo attivo non può modificare l’incidente.</div>':'')+'<form id="incident-main-form" data-form="general"><fieldset class="edit-fields" '+(!canWrite()?'disabled':'')+'><div class="form-grid">'+top+'</div><details class="advanced-fields"><summary>Altri dati e campi personalizzati</summary><div class="form-grid">'+advanced+'</div></details></fieldset><dl class="metadata-strip"><div><dt>Categorie</dt><dd>'+tags(i.categories)+'</dd></div><div><dt>Personale coinvolto</dt><dd>'+esc(i.people)+'</dd></div><div><dt>Dati interessati</dt><dd>'+tags(i.data_types)+'</dd></div></dl><div class="form-footer">'+(canWrite()?'<button type="button" class="secondary" data-local="labels">Label, personale e raccomandazioni</button><button type="submit" class="primary">Salva dati generali</button>':'')+'</div></form>';
}
function actionsHTML() {
  const actionForm=canWrite()?'<form data-form="action" id="action-form"><div class="form-grid">'+field('Data e ora','<span class="input-with-button">'+input('when_at',fixedNow(),'datetime-local','id="new-action-when-at" required')+'<button type="button" class="secondary" data-local="refresh-action-time" aria-label="Aggiorna data e ora">↻</button></span>','wide')+field('Operatore',input('person_name','Operatore A'),'wide')+field('Label azione',select('label_id',[[101,'Informazione iniziale'],[102,'Conservazione delle evidenze'],[105,'Isolamento preventivo'],[106,'Conclusione']],102,'id="new-action-label-id"'),'full')+field('Descrizione delle operazioni',area('description',''),'wide')+field('Conseguenze',area('consequence_text',''),'wide')+field('Allegati',input('action_files','','file','multiple'),'full')+'</div><div class="form-footer"><p id="action-description-hint" class="muted">Per la conservazione delle evidenze è richiesta una descrizione.</p><button type="submit" class="primary">Registra azione</button></div></form>':'<p class="section-intro">Le azioni sono consultabili. Il ruolo attivo non può registrarle o modificarle.</p>';
  return actionForm+'<h3 class="section-subheading">Azioni registrate <span class="count">'+FIXTURE.actions.length+'</span></h3>'+FIXTURE.actions.map(a=>'<details class="item-card"><summary><span>'+esc(a.label)+'</span><span class="muted">'+fmt(a.when_at)+' · '+esc(a.person)+'</span></summary><div class="item-body"><p>'+esc(a.description)+'</p><p class="item-meta">Conseguenze: '+esc(a.consequence)+' · Esportabile: '+(a.exportable?'Sì':'No')+'</p>'+a.attachments.map(att=>'<div class="button-row">'+endpointButton(att.name,'main.download_action_attachment','file-link',routeAttrs({'attachment-id':att.id}))+(canWrite()?endpointButton('Elimina allegato','main.del_action_attachment','plain small',routeAttrs({'attachment-id':att.id})):'' )+'</div>').join('')+(canWrite()?'<div class="button-row">'+endpointButton('Modifica azione','main.update_action','secondary small',routeAttrs({'action-id':a.id}))+endpointButton('Elimina azione','main.del_action','plain small',routeAttrs({'action-id':a.id}))+'</div>':'')+'</div></details>').join('');
}
function remindersHTML() {
  return '<p class="section-intro">Promemoria legati a questo incidente, con data, messaggio e destinatari in copia.</p>'+(canWrite()?'<form data-form="reminder"><div class="form-grid">'+field('Data e ora',input('scheduled_at','2026-11-22T13:15','datetime-local','required'),'wide')+field('Indirizzi in CC',input('cc_emails','','text','placeholder="Indirizzi separati da virgola"'),'wide')+field('Messaggio',area('message',''),'full')+'</div><div class="form-footer"><span></span><button type="submit" class="primary">Aggiungi promemoria</button></div></form>':'')+FIXTURE.reminders.map(r=>'<details class="item-card"><summary><span>'+fmt(r.scheduled_at)+'</span>'+badge(r.status,'neutral')+'</summary><div class="item-body"><p>'+esc(r.message)+'</p><p class="item-meta">CC: '+esc(r.cc_emails||'Nessuno')+'</p>'+(canWrite()?'<div class="button-row">'+endpointButton('Modifica','main.update_incident_reminder','secondary small',routeAttrs({'reminder-id':r.id}))+endpointButton('Elimina','main.delete_incident_reminder','plain small',routeAttrs({'reminder-id':r.id}))+'</div>':'')+'</div></details>').join('');
}
function documentButtons(d) {
  const attr=routeAttrs({'document-id':d.id});
  return (d.local&&d.download_allowed?endpointButton('Scarica','main.download_doc','secondary small',attr):'')+(d.alfresco&&state.capabilities.alfresco_enabled&&d.download_allowed?endpointButton('Da Alfresco','main.download_doc_from_alfresco','secondary small',attr):'')+(canWrite()?'<button type="button" class="secondary small" data-document-menu="'+d.id+'" aria-label="Azioni documento '+esc(d.name)+'">⋯</button>':'');
}
function documentsHTML() {
  return '<div class="section-toolbar"><p class="section-intro">Documenti e allegati dell’incidente.</p><div class="button-row">'+(canWrite()&&state.capabilities.alfresco_enabled?endpointButton('↻ Sync Alfresco','main.sync_incident_alfresco_documents','secondary small'):'')+sectionButton('Generazione moduli','incident-forms')+'</div></div>'+(state.capabilities.alfresco_enabled?'<p class="section-intro">Sync Alfresco verifica lo stato dei documenti senza caricarli o modificarli su Alfresco.</p>':'')+(canWrite()?'<div class="upload-box"><form data-form="upload"><div class="form-grid">'+field('Documenti da caricare',input('files','','file','multiple required'))+field('Archiviazione',select('storage_mode',state.capabilities.alfresco_enabled?[['local','Solo CIR'],['both','CIR + Alfresco'],['alfresco','Solo Alfresco']]:[['local','Solo CIR']],'both'))+'<button type="submit" class="primary">Carica documenti</button></div><p class="muted" style="margin-top:10px">Selezione multipla; supporto ZIP / GZIP secondo la configurazione.</p></form></div>':'')+'<div class="table-wrap"><table class="document-table"><thead><tr><th>Documento</th><th>Archiviazione</th><th>Tag notifica / template</th><th>Comandi</th></tr></thead><tbody>'+FIXTURE.documents.map(d=>'<tr><td><div class="document-name">'+esc(d.name)+'</div><p class="muted">'+esc(d.uploaded_at)+' · '+esc(d.size)+'</p></td><td>'+badge(state.capabilities.alfresco_enabled?d.storage:'CIR')+'<p class="muted">'+(state.capabilities.alfresco_enabled?'Alfresco: '+esc(d.alfresco_status):'Documento locale')+'</p></td><td>'+tags(d.tags.length?d.tags:['Nessun tag'])+'<p class="muted">Template: '+esc(d.generated_template||'Nessuno')+'</p></td><td><div class="button-row">'+documentButtons(d)+'</div></td></tr>').join('')+'</tbody></table></div><div class="document-mobile">'+FIXTURE.documents.map(d=>'<article><p class="document-name">'+esc(d.name)+'</p><p class="muted">'+esc(d.uploaded_at)+' · '+esc(d.size)+'</p>'+badge(state.capabilities.alfresco_enabled?d.storage:'CIR')+'<p class="muted">'+(state.capabilities.alfresco_enabled?'Alfresco: '+esc(d.alfresco_status)+' · ':'')+'Template: '+esc(d.generated_template||'Nessuno')+'</p>'+tags(d.tags.length?d.tags:['Nessun tag'])+'<div class="button-row" style="margin-top:12px">'+documentButtons(d)+'</div></article>').join('')+'</div>';
}
function formsHTML() {
  if (!state.capabilities.modules_enabled) return '<p class="section-intro">La generazione moduli è disattivata nella configurazione del tenant.</p>';
  return '<p class="section-intro">Seleziona i modelli da generare. La procedura mostra l’anteprima e richiede conferma prima di allegare i documenti.</p><form data-form="generation"><fieldset class="edit-fields" '+(!canWrite()?'disabled':'')+'><div class="template-grid">'+FIXTURE.forms.map(f=>'<label class="template-card"><input type="checkbox" name="templates" value="'+esc(f.name)+'" '+(f.selected?'checked':'')+'><span><strong>'+esc(f.title)+'</strong><span>'+esc(f.description)+'</span>'+(f.required_for_notification?'<span>Richiesto per la notifica al responsabile</span>':'')+'</span></label>').join('')+'</div></fieldset>'+(canWrite()?'<div class="form-footer"><span></span><button type="submit" class="primary">Genera documenti</button></div>':'')+'</form>';
}
function notificationsHTML() {
  return '<p class="section-intro">Il comando apre la verifica di destinatari, testo e allegati. L’invio richiede una conferma separata.</p><div class="notification-grid">'+FIXTURE.notifications.map(n=>'<article class="notification-card"><h3>'+esc(n.title)+'</h3><p>'+esc(n.description)+'</p>'+(canNotify()?endpointButton(n.ready?n.button:'Apri percorso guidato','main.notify_preview','secondary',routeAttrs({'notification-kind':n.kind})):badge(state.user==='admin'?'Invio non disponibile per admin incorporato':'Solo consultazione'))+'</article>').join('')+'</div>';
}
function render() {
  nav();
  $('tenant-select').innerHTML=availableTenantIds().map(id=>'<option value="'+id+'" '+(id===state.tenant?'selected':'')+'>'+({default:'default',laboratorio:'Laboratorio · demo',defaults:'Tenants Default'}[id])+'</option>').join('');
  $('tenant-select').disabled=availableTenantIds().length<=1;
  $('role-label').textContent={superuser:'Super admin',admin:'Admin tenant',writer:'Writer',reader:'Reader',operator:'Operator',disabled:'Disabilitato'}[state.role]||'Consultazione';
  $('scope-message').hidden=canView();
  if (!canView()) {
    $('incident-content').innerHTML='';
    $('scope-message').textContent=state.tenant==='defaults'?'Tenants Default contiene configurazioni e cataloghi. Gli incidenti sono gestiti nei tenant operativi.':state.role==='disabled'?'Il ruolo disabilitato non dispone dell’accesso agli incidenti.':'Questo incidente non è disponibile nel tenant o per l’utente attivo. Torna al registro o seleziona un tenant autorizzato.';
    return;
  }
  const i=FIXTURE.incident;
  $('incident-content').innerHTML='<section class="incident-banner" aria-labelledby="incident-page-title-heading"><img src="../../visual-assets/cybersecurity-hero-v2.png" alt="" aria-hidden="true"><div><p class="eyebrow">DETTAGLIO INCIDENTE</p><h1 id="incident-page-title-heading">'+esc(i.name)+'</h1><p><span>'+esc(i.reference)+'</span><span>Tenant '+esc(i.tenant)+'</span></p></div></section><div class="incident-toolbar"><div class="incident-meta">'+badge(i.status_label,'open')+badge('Gravità '+i.severity,'high')+'<span>Inizio '+fmt(i.start_at)+'</span><span>Durata '+esc(i.duration)+'</span></div><div class="toolbar-actions">'+endpointButton('Report PDF','main.pdf','secondary')+(canWrite()?sectionButton('＋ Registra azione','incident-actions','primary')+'<button type="button" class="secondary more-control" data-local="incident-more" aria-label="Altre azioni incidente">⋯</button>':'')+'</div></div><nav class="section-nav" aria-label="Sezioni dell’incidente">'+FIXTURE.sections.map(s=>'<button type="button" data-section="'+s.id+'">'+esc(s.short)+(s.count?'<span class="count">'+s.count+'</span>':'')+'</button>').join('')+'</nav>'+section('incident-workflow',workflowHTML())+section('incident-procedural-alerts','<div class="alert-strip">La chiusura richiede il completamento dei task obbligatori e la risoluzione degli avvisi procedurali.</div><ul class="alert-list">'+FIXTURE.workflow.warnings.map(w=>'<li>'+esc(w)+'</li>').join('')+'</ul><p class="muted" style="margin-top:14px">'+esc(FIXTURE.workflow.deadline_note)+'</p>')+section('incident-main',generalHTML())+section('incident-owner','<div class="contact-grid">'+[['Titolare',FIXTURE.owner],['Responsabile',FIXTURE.responsible]].map(([title,p])=>'<div class="contact-panel"><h3>'+title+'</h3><p>'+esc(p.name)+'<br>'+esc(p.contact)+'<br>'+esc(p.email)+'</p></div>').join('')+'</div>')+section('incident-consequences','<h3 class="section-subheading">Conseguenze rilevate</h3><ul class="consequence-list">'+FIXTURE.actions.map(a=>'<li>'+esc(a.consequence)+'</li>').join('')+'</ul><h3 class="section-subheading">Misure adottate</h3><p class="section-intro">'+esc(FIXTURE.actions[1].description)+'</p><h3 class="section-subheading">Raccomandazioni selezionate</h3><ul class="consequence-list">'+i.recommendations.map(r=>'<li>'+esc(r)+'</li>').join('')+'</ul>')+section('incident-actions',actionsHTML())+section('incident-reminders',remindersHTML())+section('incident-documents',documentsHTML())+section('incident-forms',formsHTML())+section('incident-notifications',notificationsHTML());
}
function dialog(title,html,context=null) {
  state.dialogContext=context;
  $('dialog-title').textContent=title;
  $('dialog-body').innerHTML=html;
  if (!$('action-dialog').open) $('action-dialog').showModal();
}
function closeDialog() { $('action-dialog').close(); $('dialog-body').innerHTML=''; state.dialogContext=null; }
function announce(message) { $('announcement').textContent=message; }
function demo(title,message='Questa anteprima mostra il punto di accesso alla funzione.') {
  dialog(title,'<p>'+esc(message)+'</p><p class="dialog-note">Mockup dimostrativo: nessun dato viene salvato, inviato, scaricato o cancellato.</p>');
}
function openSection(id,focusSelector=null) {
  if (!canView() || !FIXTURE.sections.some(s=>s.id===id)) return false;
  const el=$(id); if (!el) return false;
  el.open=true;
  el.scrollIntoView({behavior:'smooth',block:'start'});
  const focusTarget=focusSelector?el.querySelector(focusSelector):el.querySelector('summary');
  if (focusTarget) focusTarget.focus({preventScroll:true});
  state.lastDestination=id;
  return true;
}
function generationPreview(template='scheda-valutazione') {
  if (!canWrite()||!state.capabilities.modules_enabled||!FIXTURE.forms.some(f=>f.name===template)) return false;
  openSection('incident-forms');
  if (state.missingGenerationFields.length) {
    openSection('incident-main');
    dialog('Completa i dati richiesti','<p>Il modello richiede i seguenti campi:</p><ul>'+state.missingGenerationFields.map(f=>'<li>'+esc(f)+'</li>').join('')+'</ul><p class="dialog-note">La generazione resta sospesa fino al completamento dei campi.</p>'); return false;
  }
  const form=FIXTURE.forms.find(f=>f.name===template);
  dialog('Anteprima di generazione','<p>'+esc(form.title)+'</p><div class="dialog-paper"><h3>'+esc(form.title)+'</h3><p><strong>'+esc(FIXTURE.incident.reference)+'</strong><br>'+esc(FIXTURE.incident.name)+'</p><p>'+esc(FIXTURE.incident.description)+'</p></div><div class="button-row">'+endpointButton('Visualizza documento','main.preview_generated_form_file','secondary',routeAttrs({'template':template}))+endpointButton('Conferma allegato · demo','main.confirm_generated_forms','primary',routeAttrs({'template':template}))+'</div><p class="dialog-note">Anteprima grafica del passaggio di conferma; nessun PDF viene generato o allegato.</p>',{type:'generation',template});
  state.lastDestination='main.workflow_step_generate_document'; return true;
}
function notifyPreview(kind) {
  if (!canNotify()) return false;
  const notice=FIXTURE.notifications.find(n=>n.kind===kind); if (!notice) return false;
  if (!notice.ready&&!state.notificationDocsReady) {
    openSection('incident-forms');
    dialog('Documento richiesto per la notifica','<p>Prima della notifica al responsabile occorre generare la <strong>scheda di valutazione</strong>.</p><p>Il percorso guidato conduce al modello configurato nel workflow.</p><div class="button-row"><button type="button" class="primary" data-local="required-document">Apri generazione moduli</button></div><p class="dialog-note">Nessuna notifica è stata inviata.</p>');
    state.lastDestination='incident-forms'; return false;
  }
  dialog('Anteprima · '+notice.title,'<div class="dialog-paper"><p><strong>A:</strong> '+esc(FIXTURE.incident.recipient_email)+'</p><p><strong>Oggetto:</strong> '+esc(FIXTURE.incident.reference)+' · Aggiornamento incidente</p><p>'+esc(FIXTURE.incident.description)+'</p><p><strong>Allegati:</strong> selezione limitata ai documenti di questo incidente.</p></div><div class="button-row">'+endpointButton('Conferma invio · demo','main.notify_send','primary',routeAttrs({'notification-kind':kind}))+'</div><p class="dialog-note">Anteprima dimostrativa: il pulsante non invia messaggi e non registra il task come completato.</p>',{type:'notification',kind});
  state.lastDestination='main.notify_preview'; return true;
}
function activateStep(id) {
  if (!canWrite()) return false;
  const step=FIXTURE.workflow.steps.find(s=>s.id===Number(id)); if (!step) return false;
  // Priority mirrors the existing incident page. Order alone never disables a future step.
  if (step.section_target) return openSection(step.section_target);
  if (step.action.kind==='generation') return generationPreview(step.document_template_name);
  if (step.action.kind==='notification'&&!step.notification_done) return notifyPreview(step.notification_kind);
  if (step.global_check&&FIXTURE.workflow.steps.some(s=>s.number<step.number&&!s.done)) {
    dialog('Verifica globale richiesta','<p>Questo task è configurato con una verifica globale: completa prima le fasi precedenti.</p>'); return false;
  }
  openSection('incident-actions','#new-action-label-id');
  if ($('new-action-label-id')) $('new-action-label-id').value=String(step.action_label_id);
  if ($('action-description-hint')) $('action-description-hint').textContent=step.id===102?'Per la conservazione delle evidenze è richiesta una descrizione.':'Verifica i dati dell’azione prima di registrarla.';
  return true;
}
function documentMenu(id) {
  if (!canWrite()) return false;
  const d=FIXTURE.documents.find(x=>x.id===Number(id)); if (!d) return false;
  const attr=routeAttrs({'document-id':d.id});
  dialog(d.name,endpointButton('Tag di notifica','main.update_document_notification_tags','menu-link',attr)+(state.capabilities.alfresco_enabled?(d.alfresco?endpointButton('Elimina da Alfresco','main.delete_doc_from_alfresco','menu-link danger',attr):endpointButton('Invia ad Alfresco','main.upload_doc_to_alfresco','menu-link',attr)):'')+endpointButton('Elimina documento da CIR','main.del_doc','menu-link danger',attr)+'<p class="dialog-note">Le operazioni sono dimostrative. Il file e il record restano invariati.</p>'); return true;
}
function endpoint(name,params={}) {
  const info=INCIDENT_ENDPOINTS[name];
  if (!info) return sharedEndpoint(name);
  if (!canView()) return false;
  const writes=info.methods.includes('POST')||['main.notify_preview','main.workflow_step_generate_document','main.preview_generated_form_file'].includes(name);
  if (writes&&!canWrite()) return false;
  if (name.includes('alfresco')&&!state.capabilities.alfresco_enabled) return false;
  if (['main.workflow_step_generate_document','main.generate_incident_forms','main.confirm_generated_forms','main.preview_generated_form_file'].includes(name)&&!state.capabilities.modules_enabled) return false;
  const did=Number(params.documentId), aid=Number(params.actionId), rid=Number(params.reminderId), attid=Number(params.attachmentId);
  if (['main.download_doc','main.download_doc_from_alfresco','main.upload_doc_to_alfresco','main.delete_doc_from_alfresco','main.del_doc','main.update_document_notification_tags'].includes(name)&&!FIXTURE.documents.some(d=>d.id===did)) return false;
  if (['main.update_action','main.del_action'].includes(name)&&!FIXTURE.actions.some(a=>a.id===aid)) return false;
  if (['main.download_action_attachment','main.del_action_attachment'].includes(name)&&!FIXTURE.actions.some(a=>a.attachments.some(att=>att.id===attid))) return false;
  if (['main.update_incident_reminder','main.delete_incident_reminder'].includes(name)&&!FIXTURE.reminders.some(r=>r.id===rid)) return false;
  if (['main.download_doc','main.download_doc_from_alfresco'].includes(name)&&!FIXTURE.documents.find(d=>d.id===did).download_allowed) return false;
  if (name==='main.notify_preview') return notifyPreview(params.notificationKind);
  if (name==='main.notify_send') {
    if (!canNotify()||state.dialogContext?.type!=='notification'||state.dialogContext.kind!==params.notificationKind) return false;
    demo('Conferma di invio','Il passaggio di conferma è mostrato a scopo dimostrativo. Nessun messaggio è stato inviato e il workflow non cambia.'); return true;
  }
  if (name==='main.workflow_step_generate_document'||name==='main.generate_incident_forms') return generationPreview(params.template||'scheda-valutazione');
  if (name==='main.confirm_generated_forms'||name==='main.preview_generated_form_file') {
    if (state.dialogContext?.type!=='generation'||state.dialogContext.template!==params.template) return false;
    demo(name==='main.confirm_generated_forms'?'Conferma allegato':'Visualizzazione documento','Questo passaggio è solo un’anteprima. Nessun documento viene generato, scaricato o allegato.'); return true;
  }
  if (name==='main.sync_incident_alfresco_documents') {demo('Sync Alfresco','Nell’applicazione viene verificato lo stato remoto dei documenti. Non vengono caricati o modificati file su Alfresco. In questo mockup la sincronizzazione non viene eseguita.');return true;}
  if (name==='main.update_document_notification_tags') {
    const d=FIXTURE.documents.find(x=>x.id===did);
    dialog('Tag di notifica · '+d.name,'<form data-form="document-tags"><input type="hidden" name="document_id" value="'+d.id+'"><p>Associa i tipi di notifica pertinenti al documento.</p>'+FIXTURE.notifications.map(n=>'<label class="checkbox-line"><input type="checkbox" name="notification_tags" value="'+n.kind+'"> '+esc(n.title)+'</label>').join('')+'<div class="form-footer"><span></span><button type="submit" class="primary">Salva tag · demo</button></div></form><p class="dialog-note">La selezione locale rappresenta anche l’alternativa accessibile al trascinamento dei tag.</p>'); return true;
  }
  if (name==='main.update_action') {
    const a=FIXTURE.actions.find(x=>x.id===aid);
    dialog('Modifica azione','<form data-form="action-edit"><input type="hidden" name="action_id" value="'+a.id+'"><div class="form-grid">'+field('Data e ora',input('when_at',a.when_at,'datetime-local'),'wide')+field('Operatore',input('person_name',a.person),'wide')+field('Label azione',input('label_id',a.label),'full')+field('Descrizione',area('description',a.description),'full')+field('Conseguenze',area('consequence_text',a.consequence),'full')+'<div class="field full"><label class="checkbox-line"><input type="checkbox" name="exportable" '+(a.exportable?'checked':'')+'> Includi nel report</label></div>'+field('Aggiungi allegati',input('action_files','','file','multiple'),'full')+'</div><div class="form-footer"><span></span><button type="submit" class="primary">Salva modifiche · demo</button></div></form>'); return true;
  }
  if (name==='main.update_incident_reminder') {
    const r=FIXTURE.reminders.find(x=>x.id===rid);
    dialog('Modifica promemoria','<form data-form="reminder-edit"><input type="hidden" name="reminder_id" value="'+r.id+'"><div class="form-grid">'+field('Data e ora',input('scheduled_at',r.scheduled_at,'datetime-local'),'wide')+field('CC',input('cc_emails',r.cc_emails),'wide')+field('Messaggio',area('message',r.message),'full')+'<div class="field full"><label class="checkbox-line"><input type="checkbox" name="reset_sent"> Consenti nuovo invio se già inviato</label></div></div><div class="form-footer"><span></span><button type="submit" class="primary">Salva modifiche · demo</button></div></form>'); return true;
  }
  if (name==='main.clone'&&FIXTURE.workflow.lifecycle==='obsolete') {demo('Workflow obsoleto','Il workflow esistente resta utilizzabile nell’incidente corrente. Per un nuovo incidente o una clonazione occorre un workflow corrente.');return false;}
  const titles={'main.pdf':'Report PDF','main.clone':'Clona incidente','main.incident_delete':'Elimina incidente','main.del_action':'Elimina azione','main.del_action_attachment':'Elimina allegato','main.del_doc':'Elimina documento da CIR','main.delete_doc_from_alfresco':'Elimina da Alfresco','main.upload_doc_to_alfresco':'Invia ad Alfresco','main.delete_incident_reminder':'Elimina promemoria','main.download_action_attachment':'Scarica allegato','main.download_doc':'Scarica documento','main.download_doc_from_alfresco':'Scarica da Alfresco','main.add_action':'Registra azione','main.add_incident_reminder':'Aggiungi promemoria','main.upload':'Carica documenti','main.incident_detail':'Salva dati generali'};
  demo(titles[name]||'Operazione incidente',name==='main.delete_doc_from_alfresco'?'Nell’applicazione questa funzione elimina il documento remoto mantenendo il record CIR. Il mockup non cancella nulla.':'Anteprima del comando. Nell’applicazione si applicano i permessi, i controlli e le conferme previsti.');
  state.lastDestination=name;return true;
}
function menuAllowed(key) {
  if (state.role==='disabled') return ['help','settings','account'].includes(key);
  if (['notifications','modules','workflows','configuration','access','audit'].includes(key)&&!admin()) return false;
  return key!=='modules'||state.capabilities.modules_enabled;
}
function menuItems(key) {
  if (!MENUS[key]||!menuAllowed(key)) return [];
  return MENUS[key].filter(e=>(!e[2]||e[2]==='superuser'&&superuser()||e[2]==='admin'&&admin()||e[2]==='writer'&&state.role==='writer')&&(e[1]!=='ai_chatbot.chat'||state.capabilities.chatbot_enabled)&&(e[1]!=='main.change_password'||FIXTURE.user.auth_provider==='local'));
}
function menu(key,title) {
  const items=menuItems(key); if(!items.length) return false;
  dialog(title,items.map(e=>e[1]?endpointButton(e[0],e[1],'menu-link'):'<p class="menu-group">'+esc(e[0])+'</p>').join('')+'<p class="dialog-note">Menu dimostrativo · tenant '+esc(state.tenant)+'</p>');return true;
}
function sharedEndpoint(name) {
  if (name==='preview.global_ui') {
    if (!superuser()) return false;
    dialog('Interfaccia globale','<label class="global-toggle"><input id="global-ui-demo" type="checkbox" '+(state.previewNewUI?'checked':'')+'> Nuova interfaccia</label><p>Impostazione unica per tutti i tenant, gestita dai super admin.</p><p class="dialog-note">Anteprima esplicitamente attiva in questo mockup. Valore iniziale previsto nell’applicazione: disattivata. Il confronto semplificato non è la UI storica e non modifica impostazioni reali.</p>'); return true;
  }
  if (name==='menu.settings') return menu('settings','Impostazioni');
  const allowed=Object.keys(MENUS).flatMap(menuItems).find(e=>e[1]===name);
  if (!allowed) return false;
  demo(allowed[0]);return true;
}
function action(key) {
  if (state.role==='disabled'&&!['help','settings','account','info'].includes(key)) return false;
  closeMenu();
  if(MENUS[key]) return menu(key,({export:'Import / Export',notifications:'Notifiche',modules:'Moduli',workflows:'Workflow e catalogo',configuration:'Configurazione tenant',access:'Utenti e accessi',audit:'Stato e audit',help:'Aiuto',settings:'Impostazioni',account:'Account'}[key]));
  if (key==='defaults'&&!superuser()) return false;
  if (['registry','stats','defaults','info'].includes(key)) {demo(({registry:'Registro incidenti',stats:'Statistiche',defaults:'Tenants Default',info:'Informazioni applicazione'}[key]));return true;}
  return false;
}
function labelsDialog() {
  if(!canWrite())return false;
  const groups=[['categories','Categorie',FIXTURE.incident.categories],['data_types','Dati interessati',FIXTURE.incident.data_types],['people','Personale coinvolto',FIXTURE.incident.people.split(', ')],['recommendations','Raccomandazioni',FIXTURE.incident.recommendations]];
  dialog('Label, personale e raccomandazioni','<p>La selezione delle categorie conserva l’ordine da cui dipende il workflow. Le raccomandazioni rispettano il limite configurato.</p><form data-form="labels"><div class="dialog-labels">'+groups.map(([key,title,values])=>'<section><h3>'+title+'</h3>'+values.map((v,i)=>'<label class="checkbox-line"><input type="checkbox" name="'+key+'" value="'+esc(v)+'" checked> '+esc(v)+'</label>'+(key==='categories'?'<button type="button" class="plain small" data-label-move="'+i+'">'+(i?'↑ Sposta prima':'↓ Sposta dopo')+'</button>':'')).join('')+(key==='recommendations'?'<p class="muted">Massimo selezionabile: 3 nell’esempio.</p>':'')+'</section>').join('')+'</div><div class="form-footer"><span></span><button type="submit" class="primary">Conferma selezione · demo</button></div></form><p class="dialog-note">Selezione locale da tastiera e touch; l’integrazione conserverà anche il trascinamento.</p>');return true;
}
function localAction(key) {
  if (!canView())return false;
  if (key==='incident-more'&&canWrite()) {dialog('Azioni incidente',endpointButton('Clona incidente','main.clone','menu-link')+endpointButton('Elimina incidente','main.incident_delete','menu-link danger')+'<p class="dialog-note">Le operazioni sono dimostrative e non modificano l’incidente.</p>');return true;}
  if (key==='labels')return labelsDialog();
  if (key==='required-document'&&canWrite()) {closeDialog();openSection('incident-forms');return true;}
  if (key==='refresh-action-time'&&canWrite()&&$('new-action-when-at')) {$('new-action-when-at').value=fixedNow();announce('Data e ora dell’esempio aggiornate.');return true;}
  if (['external-recipient','ldap-recipient'].includes(key)&&canWrite()) {demo(key==='external-recipient'?'Ricerca destinatari esterni':'Ricerca LDAP','Nell’applicazione il selettore segue configurazione e autorizzazioni del tenant. I contatti del mockup sono esclusivamente dimostrativi.');return true;}
  return false;
}
function openMenu() {
  const n=$('navigation');n.inert=false;n.classList.add('open');n.setAttribute('role','dialog');n.setAttribute('aria-modal','true');$('backdrop').hidden=false;$('open-menu').setAttribute('aria-expanded','true');document.querySelector('.workspace').inert=true;$('close-menu').focus();
}
function closeMenu() {
  const wasOpen=$('navigation').classList.contains('open');$('navigation').classList.remove('open');$('navigation').removeAttribute('role');$('navigation').removeAttribute('aria-modal');$('navigation').inert=matchMedia('(max-width:760px)').matches;$('backdrop').hidden=true;$('open-menu').setAttribute('aria-expanded','false');document.querySelector('.workspace').inert=false;if(wasOpen)$('open-menu').focus();
}
$('open-menu').addEventListener('click',openMenu);
$('close-menu').addEventListener('click',closeMenu);
$('backdrop').addEventListener('click',closeMenu);
$('close-dialog').addEventListener('click',closeDialog);
$('action-dialog').addEventListener('cancel',()=>{state.dialogContext=null;});
$('tenant-select').addEventListener('change',()=>{const tenant=$('tenant-select').value;if(!availableTenantIds().includes(tenant))return;closeDialog();state.tenant=tenant;state.lastDestination=null;render();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();if(e.key==='Tab'&&$('navigation').classList.contains('open')){const f=[...$('navigation').querySelectorAll('button:not([disabled])')];if(e.shiftKey&&document.activeElement===f[0]){e.preventDefault();f[f.length-1].focus();}else if(!e.shiftKey&&document.activeElement===f[f.length-1]){e.preventDefault();f[0].focus();}}});
document.addEventListener('click',e=>{
  let t=e.target.closest('[data-action]');if(t){action(t.dataset.action);return;}
  t=e.target.closest('[data-section]');if(t){openSection(t.dataset.section);return;}
  t=e.target.closest('[data-step]');if(t){activateStep(t.dataset.step);return;}
  t=e.target.closest('[data-endpoint]');if(t){endpoint(t.dataset.endpoint,t.dataset);return;}
  t=e.target.closest('[data-document-menu]');if(t){documentMenu(t.dataset.documentMenu);return;}
  t=e.target.closest('[data-local]');if(t){localAction(t.dataset.local);return;}
  t=e.target.closest('[data-reveal]');if(t&&canWrite()){const secret=$(t.dataset.reveal);if(secret){secret.type=secret.type==='password'?'text':'password';t.textContent=secret.type==='password'?'Mostra':'Nascondi';}return;}
  t=e.target.closest('[data-now]');if(t&&canWrite()){const prefix=t.dataset.now;if(!['start','end'].includes(prefix))return;$('incident-'+prefix+'-date').value=fixedNow().slice(0,10);$('incident-'+prefix+'-time').value=fixedNow().slice(11);announce('Impostata data e ora della simulazione.');return;}
  t=e.target.closest('[data-label-move]');if(t&&canWrite()){const label=t.previousElementSibling;if(label?.matches('.checkbox-line')){const parent=label.parentNode;const labels=[...parent.querySelectorAll('.checkbox-line')];if(labels.length===2){parent.insertBefore(labels[1],labels[0]);announce('Ordine locale delle categorie modificato. Nessun salvataggio.');}}}
});
document.addEventListener('change',e=>{
  if(e.target.id==='global-ui-demo'&&superuser()){state.previewNewUI=e.target.checked;document.body.classList.toggle('preview-classic',!state.previewNewUI);announce(state.previewNewUI?'Anteprima della nuova interfaccia attiva.':'Confronto semplificato attivo. Nessuna impostazione applicativa modificata.');}
  if(e.target.id==='new-action-label-id'&&canWrite()&&$('action-description-hint')){$('action-description-hint').textContent=e.target.value==='102'?'Per la conservazione delle evidenze è richiesta una descrizione.':'Verifica i dati dell’azione prima di registrarla.';}
});
document.addEventListener('submit',e=>{
  const form=e.target.closest('[data-form]');if(!form)return;e.preventDefault();if(!canWrite())return;
  const values=new FormData(form);const kind=form.dataset.form;
  if(kind==='general'&&values.get('status')==='chiuso'&&FIXTURE.workflow.warnings.length){dialog('Chiusura non disponibile','<p>Ci sono ancora task obbligatori e avvisi procedurali da risolvere.</p><ul class="alert-list">'+FIXTURE.workflow.warnings.map(w=>'<li>'+esc(w)+'</li>').join('')+'</ul><p class="dialog-note">Lo stato dell’incidente non è stato modificato.</p>');return;}
  if(kind==='action'&&values.get('label_id')==='102'&&!String(values.get('description')||'').trim()){dialog('Descrizione richiesta','<p>Descrivi le operazioni svolte per conservare le evidenze prima di registrare questa azione.</p>');return;}
  if(kind==='action'&&values.get('label_id')==='106'&&FIXTURE.workflow.warnings.length){dialog('Conclusione non disponibile','<p>La conclusione dell’incidente richiede la risoluzione degli avvisi procedurali.</p>');return;}
  if(kind==='generation'){const chosen=values.getAll('templates');if(!chosen.length){dialog('Seleziona un modello','<p>Seleziona almeno un modello da generare.</p>');return;}generationPreview(chosen[0]);return;}
  if(kind==='labels'&&values.getAll('recommendations').length>3){dialog('Limite raccomandazioni','<p>Nell’esempio sono consentite al massimo tre raccomandazioni.</p>');return;}
  demo('Anteprima del comando','La compilazione mostra il comportamento del modulo. Nessun dato viene salvato, nessun file caricato e nessuna attività viene segnata come completata.');
});
if(matchMedia('(max-width:760px)').matches)$('navigation').inert=true;
matchMedia('(max-width:760px)').addEventListener('change',closeMenu);
// Test/review-only API. Not a login, access-control or privilege-changing feature.
window.CIRIncidentReview={state,fixture:FIXTURE,menus:MENUS,canView,canWrite,canNotify,activateStep,endpoint,openSection,render,menuItems,action,
  setRole(role,user=FIXTURE.user.username){if(!['superuser','admin','writer','reader','operator','disabled'].includes(role))return false;closeDialog();state.role=role;state.user=user;state.tenant=availableTenantIds()[0]||'default';state.lastDestination=null;render();return true;},
  setTenant(tenant){if(!availableTenantIds().includes(tenant))return false;closeDialog();state.tenant=tenant;state.lastDestination=null;render();return true;},
  setCapabilities(values){state.capabilities={...state.capabilities,...values};closeDialog();render();},
  setNotificationDocsReady(ready){state.notificationDocsReady=Boolean(ready);},
  setMissingGenerationFields(fields){state.missingGenerationFields=[...fields];}
};
render();
