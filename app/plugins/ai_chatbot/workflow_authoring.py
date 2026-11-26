"""AlBot workflow authoring: untrusted model output -> validated preview -> explicit tenant-scoped write.

No AI output is a database command.  The only persistence operation is apply_draft(),
called by an authenticated, CSRF-checked POST after a human review.  Both exports and
updates use CIR's existing portable workflow-catalog.v1 schema.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import time
import uuid
from pathlib import Path

from flask import current_app, session
from flask_login import current_user

from ...models import (db, ConfigLabel, Incident, IncidentWorkflowStep, NotificationType,
                       FormTemplateConfig, FormTemplateBinary, FormFieldMapping, Tenant)
from ...workflow_catalog import (CATALOG_FORMAT, MAX_PDF_BYTES, SECTION_TARGETS,
                                 STANDARD_STEP_TYPES, validate_catalog_payload)
from ...workflow_lifecycle import ensure_workflow_state, get_workflow_state, lock_workflow_configuration
from ...configuration_usage import workflow_incident_usage
from ...routes import current_tenant_id, is_superuser, can_admin, labels as visible_labels

DRAFT_LIFETIME = 30 * 60
MAX_QUESTION = 15000
MAX_STEPS = 80
_AUTHOR_COMMAND = re.compile(r'\b(crea(?:re|mi)?|genera(?:re|mi)?|progett(?:a|are|ami)|'
                             r'defini(?:sci|re)|aggiung(?:i|ere)|modific(?:a|are)|aggiorn(?:a|are)|'
                             r'esport(?:a|are)|scaric(?:a|are)|costrui(?:sci|re)|'
                             r'create|generate|design|define|update|modify|export|download)\b', re.I)
_WORKFLOW_WORD = re.compile(r'\b(workflow|flusso\s+di\s+lavoro|flusso\s+operativo|procedura\s+operativa)\b', re.I)
_INFO_ONLY = re.compile(r'^\s*(come|how|what|quali|qual\s+è|perch[eé]|spiega|illustrami)\b', re.I)
_EXPORT = re.compile(r'\b(json|scaric(?:a|are)|esport(?:a|are)|download|export)\b', re.I)
_NAME = re.compile(r'^[^<>\x00-\x1f]{1,160}$')
_KEY = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')


def is_authoring_intent(text):
    """Do not intercept help questions just because they contain 'workflow'."""
    return bool(isinstance(text, str) and _AUTHOR_COMMAND.search(text) and
                _WORKFLOW_WORD.search(text) and not _INFO_ONLY.search(text))


def request_is_export_only(question):
    text = question or ''
    if re.search(r'\b(importa|importare|salva|salvare|applica|applicare|apply|save|install)\b', text, re.I):
        return False
    return bool(_EXPORT.search(text))


def require_workflow_admin():
    if not getattr(current_user, 'is_authenticated', False) or not can_admin():
        raise PermissionError('Solo un amministratore del tenant può preparare o importare workflow.')
    tenant = db.session.get(Tenant, int(current_tenant_id()))
    if tenant is None:
        raise ValueError('Tenant corrente non valido.')
    if tenant.is_system_defaults and not is_superuser():
        raise PermissionError('Tenants Default è gestibile esclusivamente dai super admin.')
    return tenant


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _value(value, name, length=255, required=True):
    if not isinstance(value, str) or len(value) > length or '\x00' in value:
        raise ValueError(f'{name}: testo non valido.')
    if required and not value.strip():
        raise ValueError(f'{name}: testo obbligatorio.')
    return value.strip()


def _flag(obj, field, default=False):
    v = obj.get(field, default)
    if type(v) is not bool:
        raise ValueError(f'{field} deve essere vero o falso.')
    return v


def _number(obj, field, default=0, high=100000):
    v = obj.get(field, default)
    if type(v) is not int or not 0 <= v <= high:
        raise ValueError(f'{field}: numero non valido.')
    return v


def _existing_label(tenant_id, kind, name):
    return ConfigLabel.query.filter_by(tenant_id=tenant_id, kind=kind, value=name).first()


def _workflow_scope(tenant_id, name):
    """Resolve an explicit named category; never silently edit the fallback/default flow."""
    category = _existing_label(tenant_id, 'category', name)
    if category is not None:
        return category
    from ...workflow_catalog_models import TenantWorkflow
    state = TenantWorkflow.query.filter_by(tenant_id=tenant_id, name=name).first()
    if state and state.category_id is not None:
        return ConfigLabel.query.filter_by(tenant_id=tenant_id, id=state.category_id, kind='category').first()
    return None


def workflow_fingerprint(tenant_id, category):
    if category is None:
        return None
    rows = IncidentWorkflowStep.query.filter_by(tenant_id=tenant_id, category_id=category.id).order_by(
        IncidentWorkflowStep.position, IncidentWorkflowStep.id).all()
    state = get_workflow_state(tenant_id, category.id)
    snap = {'category': {'id': category.id, 'name': category.value},
            'workflow': {'id': state.id, 'name': state.name, 'status': state.status} if state else None,
            'steps': [{'id': row.id, 'position': row.position, 'label_id': row.action_label_id,
                       'description': row.description, 'type': row.step_type, 'conditions': row.conditions,
                       'required': row.required, 'requires_notification': row.requires_notification,
                       'document_generation_enabled': row.document_generation_enabled,
                       'notification': row.required_notification_type, 'document': row.document_template_name,
                       'section': row.section_target}
                      for row in rows]}
    return hashlib.sha256(_canonical(snap).encode('utf-8')).hexdigest()


def _workflow_use_blocker(tenant, category):
    """Protect old incidents including a category that still uses fallback steps.

    A category with no dedicated steps currently resolves to the fallback flow,
    so the ordinary resolved-workflow guard would miss incidents whose behavior
    changes the moment a dedicated workflow is installed for that category.
    """
    reason = workflow_incident_usage(tenant.id, category.id)
    if reason:
        return reason
    already_defined = IncidentWorkflowStep.query.filter_by(
        tenant_id=tenant.id, category_id=category.id).first()
    if already_defined is not None:
        return ''
    query = Incident.query.filter(Incident.categories.any(ConfigLabel.id == category.id))
    if tenant.is_default and not tenant.is_system_defaults:
        from sqlalchemy import or_
        query = query.filter(or_(Incident.tenant_id == tenant.id, Incident.tenant_id.is_(None)))
    else:
        query = query.filter_by(tenant_id=tenant.id)
    used = query.first()
    return f'categoria già selezionata dall’incidente #{used.id}' if used else ''


def _read_json(raw):
    if not isinstance(raw, str) or len(raw) > 400000:
        raise ValueError('La risposta AI non è un documento JSON valido.')
    raw = raw.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, count=1, flags=re.I)
        raw = re.sub(r'\s*```$', '', raw, count=1)
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError('AlBot non ha restituito un JSON strutturato. Riprovare indicando chiaramente nome e step.') from exc
    if not isinstance(obj, dict):
        raise ValueError('La definizione deve essere un oggetto JSON.')
    return obj


def _existing_workflows(tenant_id):
    from ...workflow_catalog_models import TenantWorkflow
    names = {label.value for label in ConfigLabel.query.filter_by(tenant_id=tenant_id, kind='category').all()}
    names.update(state.name for state in TenantWorkflow.query.filter_by(tenant_id=tenant_id).all() if state.category_id is not None)
    return sorted(names)[:120]


def _requested_workflow_context(question, tenant_id):
    """Provide current configuration only for explicitly named workflows in this tenant."""
    rows = []
    for name in _existing_workflows(tenant_id):
        if name.casefold() not in question.casefold():
            continue
        category = _workflow_scope(tenant_id, name)
        if category is None:
            continue
        source = IncidentWorkflowStep.query.filter_by(tenant_id=tenant_id, category_id=category.id).order_by(
            IncidentWorkflowStep.position, IncidentWorkflowStep.id).limit(MAX_STEPS+1).all()
        if len(source) > MAX_STEPS:
            raise ValueError('Il workflow esistente è troppo lungo per la modifica assistita; usarne l’editor amministrativo.')
        by_label = {step.action_label_id: f's{i+1:02}' for i, step in enumerate(source)}
        steps = []
        for index, step in enumerate(source):
            label = step.action_label
            conds, depends = [], []
            for token in step.condition_tokens():
                negate = token.startswith('!')
                base = token[1:] if negate else token
                if base == 'personal_data':
                    conds.append({'kind': 'personal_data', 'negated': negate})
                elif ':' in base:
                    kind, raw_id = base.split(':', 1)
                    try:
                        label_id = int(raw_id)
                    except ValueError:
                        continue
                    if kind == 'step_completed':
                        if label_id in by_label:
                            depends.append(by_label[label_id])
                    elif kind in ('severity', 'data_type'):
                        row = ConfigLabel.query.filter_by(tenant_id=tenant_id, kind=kind, id=label_id).first()
                        if row:
                            conds.append({'kind': kind, 'value': row.value, 'negated': negate})
            steps.append({'key': f's{index+1:02}', 'name': label.value if label else f'Step {index+1}',
                          'description': step.description or '',
                          'step_type': step.step_type or 'registration',
                          'required': bool(step.required),
                          'description_required': bool(label.description_required) if label else False,
                          'max_completion_hours': int(label.max_completion_hours or 0) if label else 0,
                          'depends_on': depends, 'conditions': conds,
                          'requires_notification': bool(step.requires_notification),
                          'required_notification_type': step.required_notification_type or '',
                          'document_generation_enabled': bool(step.document_generation_enabled),
                          'document_template_name': step.document_template_name or '',
                          'section_target': step.section_target or ''})
        rows.append({'existing_name': name, 'steps': steps})
        if len(rows) >= 3:
            break
    return rows


def generate_proposal(question, engine):
    """Ask the configured LLM for declarative data only. Never give it DB access."""
    tenant = require_workflow_admin()
    if not question or len(question) > MAX_QUESTION:
        raise ValueError('Descrizione troppo lunga o vuota.')
    context = '''Sei AlBot, progettista di workflow CIR. Trasforma la richiesta in UN SOLO oggetto JSON valido;
non usare Markdown, non includere testo extra. Non eseguire operazioni. I nomi e gli step devono provenire
esclusivamente dalla richiesta dell'utente: non inventare autorizzazioni o invii automatici.
Schema JSON esatto:
{"operation":"create|update","name":"Nome workflow desiderato", "existing_name":"nome precedente solo se update",
 "steps":[{"key":"step_a","name":"Nome azione univoco","description":"Istruzioni operative",
 "step_type":"registration|execution|update_section|operation","required":true,
 "description_required":false,"max_completion_hours":0,"depends_on":[],
 "conditions":[{"kind":"personal_data","negated":false},{"kind":"severity","value":"Alta","negated":false},
               {"kind":"data_type","value":"Dati personali","negated":false}],
 "requires_notification":false,"required_notification_type":"", "document_generation_enabled":false,
 "document_template_name":"", "section_target":""}]}.
I campi conditions e depends_on possono essere [] e gli altri opzionali tranne key/name. Dipendenze
sono chiavi di step PRECEDENTI, senza cicli. Non usare "step_completed" in conditions: usa depends_on.
Valorizza requires_notification e document_generation_enabled solo quando sono richiesti esplicitamente.
Usa operation=update solo se l'utente chiede esplicitamente di modificare un workflow ESISTENTE.
Se modifichi un workflow esistente, restituisci tutti i suoi step con le proprietà esistenti
preservate, più le modifiche richieste. Non eliminare o rinominare step non esplicitamente indicati.
In caso di impossibilità a ricostruire step e nome, produci {"error":"spiegazione"}.
Non produrre ID database, SQL, codici eseguibili o allegati. I workflow esistenti sono forniti SOLO
per disambiguare, non per sovrascrivere altri workflow.'''
    context += '\nTenant attivo: ' + tenant.name + '\nNomi workflow disponibili: ' + _canonical(_existing_workflows(tenant.id))
    context += '\nDefinizioni esistenti dei workflow citati nella richiesta (sola lettura): ' + _canonical(_requested_workflow_context(question, tenant.id))
    return _read_json(engine.generate([{'role': 'user', 'content': question}], context))


def _label_definition(existing, kind, value, ref, **overrides):
    result = {'ref': ref, 'kind': kind, 'value': value, 'group': 'default',
              'description': '', 'max_completion_hours': 0, 'default_exportable': True,
              'description_required': False, 'automatic_operations': ''}
    if existing:
        result.update({k: getattr(existing, k) for k in ('group', 'description', 'max_completion_hours',
                      'default_exportable', 'description_required', 'automatic_operations')})
        result['group'] = result['group'] or 'default'
        result['description'] = result['description'] or ''
        result['automatic_operations'] = result['automatic_operations'] or ''
    result.update(overrides)
    return result


def _form_dependency(tenant, name):
    """Portable PDF dependency using only an already configured, readable tenant form."""
    from ...workflow_catalog import _form_name
    _form_name(name)
    cfg = FormTemplateConfig.query.filter_by(template_name=name).first()
    base_name = Path(name).stem
    if cfg is None:
        cfg = FormTemplateConfig.query.filter_by(template_name=base_name).first()
    if cfg and cfg.owner_tenant_id not in (None, tenant.id):
        raise ValueError(f'Il modello PDF {name} non appartiene al tenant selezionato.')
    binary = FormTemplateBinary.query.filter_by(template_name=base_name).first()
    data = bytes(binary.pdf_data) if binary is not None and binary.pdf_data else None
    if data is None:
        base = Path(current_app.config['FORM_TEMPLATE_DIR']).resolve()
        original_path = base / (base_name + '.pdf')
        path = original_path.resolve()
        if path.parent != base or not path.is_file() or original_path.is_symlink():
            raise ValueError(f'Il modello PDF {name} non è presente; configurarlo prima con un amministratore.')
        if path.stat().st_size > MAX_PDF_BYTES:
            raise ValueError('Il PDF richiesto è troppo grande.')
        data = path.read_bytes()
    if not data.startswith(b'%PDF-') or len(data) > MAX_PDF_BYTES:
        raise ValueError('Modello PDF non valido.')
    tags = list(cfg.notification_tag_list) if cfg else []
    return {'template_name': name, 'font_family': cfg.font_family if cfg else 'Helvetica',
            'font_size': cfg.font_size if cfg else 10, 'notification_tags': tags,
            'mappings': [{'template_field': m.template_field, 'db_field': m.db_field} for m in
                         FormFieldMapping.query.filter_by(template_name=cfg.template_name if cfg else base_name).all()],
            'binary': {'filename': base_name+'.pdf', 'pdf_base64': base64.b64encode(data).decode('ascii')}}


def prepare_draft(spec, tenant=None, *, export_only=False, request_text=''):
    """Whitelist + cross-ref validation (zero configuration writes)."""
    tenant = tenant or require_workflow_admin()
    if not isinstance(spec, dict):
        raise ValueError('Definizione del workflow assente.')
    if spec.get('error'):
        raise ValueError(_value(spec['error'], 'Descrizione incompleta', 500))
    operation = spec.get('operation', 'create')
    if operation not in ('create', 'update'):
        raise ValueError('Operazione non supportata: scegliere create o update.')
    name = _value(spec.get('name'), 'Nome workflow', 160)
    if not _NAME.fullmatch(name):
        raise ValueError('Nome del workflow non valido.')
    old_name = _value(spec.get('existing_name') or name, 'Nome workflow esistente', 160)
    existing = _workflow_scope(tenant.id, old_name)
    conflicting = _workflow_scope(tenant.id, name)
    if operation == 'create' and conflicting is not None:
        raise ValueError('Esiste già un workflow con questo nome: richiedere esplicitamente un aggiornamento.')
    if operation == 'update' and existing is None:
        raise ValueError('Workflow da aggiornare non trovato nel tenant corrente: indicare il nome esistente.')
    if operation == 'update' and conflicting is not None and conflicting.id != existing.id:
        raise ValueError('Il nuovo nome è già usato da un altro workflow del tenant.')
    if operation == 'update' and existing is not None:
        reason = _workflow_use_blocker(tenant, existing)
        if reason:
            raise ValueError('Aggiornamento bloccato: '+reason+'. Creare una nuova versione con un nome diverso.')
    steps = spec.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError('Il workflow richiede da 1 a 80 step.')
    if operation == 'update':
        existing_steps = IncidentWorkflowStep.query.filter_by(tenant_id=tenant.id, category_id=existing.id).all()
        old_names = {step.action_label.value.casefold() for step in existing_steps if step.action_label}
        proposed_names = {str(row.get('name') or '').strip().casefold() for row in steps if isinstance(row, dict)}
        missing = old_names - proposed_names
        removal_request = re.search(r'\b(elimina|eliminare|rimuovi|rimuovere|cancella|cancellare|'
                                    r'rinomina|rinominare|sostituisci|sostituire|remove|delete|rename|replace)\b',
                                    request_text or '', re.I)
        if missing and not removal_request:
            raise ValueError('La proposta omette step già esistenti (' + ', '.join(sorted(missing)[:8]) +
                             '). AlBot deve conservare tutti gli step non esplicitamente rimossi o rinominati.')
    labels, label_refs, exported, prepared, seen = [], {}, [], [], set()
    notification_types, forms = {}, {}

    def add_label(kind, value, **overrides):
        ref = label_refs.get((kind, value))
        if ref:
            return ref
        current = _existing_label(tenant.id, kind, value)
        ref = 'label_'+str(len(labels)+1)
        labels.append(_label_definition(current, kind, value, ref, **overrides))
        label_refs[(kind, value)] = ref
        return ref

    add_label('category', name)
    for index, item in enumerate(steps):
        if not isinstance(item, dict):
            raise ValueError(f'Step {index+1}: struttura non valida.')
        key = _value(item.get('key'), 'Identificativo step', 64)
        if not _KEY.fullmatch(key) or key in seen:
            raise ValueError(f'Step {index+1}: chiave assente, duplicata o non valida.')
        task = _value(item.get('name'), 'Nome step', 160)
        if any(x['name'].casefold() == task.casefold() for x in prepared):
            raise ValueError(f'Nome step duplicato ({task}); ogni step deve avere una label univoca per le dipendenze.')
        description = _value(item.get('description', ''), 'Descrizione step', 10000, required=False)
        kind = item.get('step_type', 'registration')
        if kind not in STANDARD_STEP_TYPES:
            raise ValueError(f'Step {task}: tipo {kind} non supportato senza configurazione.')
        hours = _number(item, 'max_completion_hours', 0, 100000)
        required_description = _flag(item, 'description_required')
        ref = add_label('action_label', task)
        label = next(x for x in labels if x['ref'] == ref)
        original = _existing_label(tenant.id, 'action_label', task)
        if original:
            if 'max_completion_hours' in item and hours != int(original.max_completion_hours or 0):
                raise ValueError(f'La label azione {task} è già condivisa e ha un diverso tempo limite: usare un nuovo nome.')
            if 'description_required' in item and required_description != bool(original.description_required):
                raise ValueError(f'La label azione {task} è condivisa e ha altri requisiti di descrizione: usare un nuovo nome.')
        else:
            label['max_completion_hours'] = hours
            label['description_required'] = required_description
            label['description'] = description
        depends = item.get('depends_on', [])
        if not isinstance(depends, list) or any(not isinstance(d, str) or d not in seen for d in depends):
            raise ValueError(f'Step {task}: le dipendenze devono riferirsi a step precedenti del workflow.')
        if len(set(depends)) != len(depends):
            raise ValueError(f'Step {task}: dipendenze duplicate.')
        conds = [{'kind': 'step_completed', 'label_ref': next(x['ref'] for x in prepared if x['key'] == d),
                  'negated': False} for d in depends]
        raw_conditions = item.get('conditions', [])
        if not isinstance(raw_conditions, list) or len(raw_conditions) > 64:
            raise ValueError(f'Step {task}: condizioni non valide.')
        for cond in raw_conditions:
            if not isinstance(cond, dict) or cond.get('kind') not in ('personal_data', 'severity', 'data_type'):
                raise ValueError(f'Step {task}: condizione sconosciuta.')
            ck = cond['kind']
            row = {'kind': ck, 'negated': _flag(cond, 'negated')}
            if ck != 'personal_data':
                condition_name = _value(cond.get('value'), 'Valore condizione', 255)
                # Severity/data-type conditions must target an actual tenant
                # value. Never silently create a duplicate ("Alta" vs "alta")
                # that makes the proposed step inapplicable to real incidents.
                matches = [x for x in visible_labels(ck)
                           if x.value.casefold() == condition_name.casefold()]
                if not matches or len({x.value.casefold() for x in matches}) != 1:
                    raise ValueError(f'Step {task}: valore {ck} "{condition_name}" non presente o ambiguo nel tenant; configurarlo prima.')
                row['label_ref'] = add_label(ck, matches[0].value)
            conds.append(row)
        notification = _value(item.get('required_notification_type', ''), 'Tipo notifica', 40, required=False)
        wants_notification = _flag(item, 'requires_notification')
        if wants_notification and not notification:
            raise ValueError(f'Step {task}: specificare il codice del tipo notifica.')
        if notification:
            nt = NotificationType.query.filter_by(tenant_id=tenant.id, code=notification, enabled=True).first()
            if nt is None:
                raise ValueError(f'Step {task}: tipo notifica {notification} non abilitato nel tenant.')
            notification_types[notification] = {'code': nt.code, 'label': nt.label,
                                                'description': nt.description or '', 'enabled': True}
        form_name = _value(item.get('document_template_name', ''), 'Nome modello PDF', 255, required=False)
        generates = _flag(item, 'document_generation_enabled')
        if generates and not form_name:
            raise ValueError(f'Step {task}: indicare il nome di un PDF esistente.')
        if form_name and form_name not in forms:
            forms[form_name] = _form_dependency(tenant, form_name)
            for code in forms[form_name]['notification_tags']:
                nt = NotificationType.query.filter_by(tenant_id=tenant.id, code=code, enabled=True).first()
                if nt is None:
                    raise ValueError(f'Il modulo {form_name} richiede il tipo notifica {code} non disponibile nel tenant.')
                notification_types[code] = {'code': nt.code, 'label': nt.label,
                                            'description': nt.description or '', 'enabled': True}
        section = _value(item.get('section_target', ''), 'Sezione target', 80, required=False)
        if section and (kind not in ('operation', 'update_section') or section not in SECTION_TARGETS):
            raise ValueError(f'Step {task}: sezione target non valida.')
        exported.append({'position': (index+1)*10, 'action_label_ref': ref, 'description': description,
                         'step_type': kind, 'required': _flag(item, 'required', True),
                         'conditions': conds, 'requires_notification': wants_notification,
                         'required_notification_type': notification,
                         'document_generation_enabled': generates,
                         'document_template_name': form_name, 'section_target': section})
        prepared.append({'key': key, 'ref': ref, 'name': task, 'depends_on': depends,
                         'depends_on_names': [next(x['name'] for x in prepared if x['key'] == d) for d in depends],
                         'conditions': conds, 'description': description, 'required': exported[-1]['required'],
                         'step_type': kind, 'max_completion_hours': label['max_completion_hours'],
                         'description_required': label['description_required'],
                         'requires_notification': wants_notification, 'required_notification_type': notification,
                         'document_generation_enabled': generates, 'document_template_name': form_name,
                         'section_target': section})
        seen.add(key)
    readable = {item['ref']: item['value'] for item in labels}
    for entry in prepared:
        entry['condition_labels'] = [
            ('NON ' if cond['negated'] else '') + (
                'Dopo: ' + readable[cond['label_ref']] if cond['kind'] == 'step_completed'
                else 'Gravità: ' + readable[cond['label_ref']] if cond['kind'] == 'severity'
                else 'Dati: ' + readable[cond['label_ref']] if cond['kind'] == 'data_type'
                else 'Rischio per diritti e libertà')
            for cond in entry['conditions']]
    payload = validate_catalog_payload({'format': CATALOG_FORMAT,
        'workflow': {'category_ref': label_refs[('category', name)], 'steps': exported},
        'dependencies': {'labels': labels, 'notification_types': list(notification_types.values()),
                         'notification_templates': [], 'form_templates': list(forms.values()), 'step_types': []}})
    return {'operation': operation, 'name': name, 'existing_name': old_name, 'tenant_id': tenant.id,
            'tenant_name': tenant.name, 'owner_id': current_user.id,
            'fingerprint': workflow_fingerprint(tenant.id, existing) if operation == 'update' else None,
            'payload': payload, 'steps': prepared, 'export_only': bool(export_only), 'created_at': int(time.time())}


def _draft_dir():
    base = Path(current_app.config['AI_CHATBOT_DOC_DIR']).resolve() / 'workflow_drafts'
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    return base


def save_draft(draft):
    token = uuid.uuid4().hex
    path = _draft_dir() / (token + '.json')
    # Exclusive create and unguessable identifier, never a user-supplied pathname.
    with os.fdopen(os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as file:
        json.dump(draft, file, ensure_ascii=False)
    known = list(session.get('albot_workflow_tokens') or [])[-7:]
    known.append(token)
    session['albot_workflow_tokens'] = known
    return token


def read_draft(token):
    require_workflow_admin()
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
        raise ValueError('Identificativo anteprima non valido.')
    if token not in (session.get('albot_workflow_tokens') or []):
        raise PermissionError('Questa anteprima non appartiene alla sessione corrente.')
    path = _draft_dir() / (token + '.json')
    if path.is_symlink() or not path.is_file():
        raise ValueError('Anteprima non più disponibile.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (data.get('owner_id') != current_user.id or data.get('tenant_id') != current_tenant_id()):
        raise PermissionError('La sessione o il tenant attivo sono cambiati: richiesta non autorizzata.')
    if int(time.time()) - data.get('created_at', 0) > DRAFT_LIFETIME:
        path.unlink(missing_ok=True)
        raise ValueError('Anteprima scaduta: generare nuovamente il workflow con AlBot.')
    data['payload'] = validate_catalog_payload(data['payload'])
    return data


def discard_draft(token):
    if re.fullmatch(r'[a-f0-9]{32}', token):
        (_draft_dir() / (token+'.json')).unlink(missing_ok=True)
    session['albot_workflow_tokens'] = [x for x in (session.get('albot_workflow_tokens') or []) if x != token]


def apply_draft(draft):
    """Only call after explicit confirmation; one transaction, same-tenant, race-aware."""
    tenant = require_workflow_admin()
    if tenant.id != draft['tenant_id'] or current_user.id != draft['owner_id']:
        raise PermissionError('Il contesto autorizzato dell’anteprima è cambiato.')
    payload = validate_catalog_payload(draft['payload'])
    lock_workflow_configuration()
    tenant = Tenant.query.filter_by(id=tenant.id).with_for_update().first()
    old_name, new_name, operation = draft['existing_name'], draft['name'], draft['operation']
    category = _workflow_scope(tenant.id, old_name)
    conflict = _workflow_scope(tenant.id, new_name)
    if operation == 'create':
        if conflict is not None:
            raise ValueError('Il workflow è stato creato da un’altra operazione; rigenerare la proposta.')
    elif category is None or workflow_fingerprint(tenant.id, category) != draft['fingerprint']:
        raise ValueError('Il workflow è stato modificato dall’anteprima: rigenerare la proposta prima del salvataggio.')
    if operation == 'update':
        if conflict is not None and conflict.id != category.id:
            raise ValueError('Il nome di destinazione è già utilizzato.')
        reason = _workflow_use_blocker(tenant, category)
        if reason:
            raise ValueError('Aggiornamento non sicuro: ' + reason)
    definition_by_ref = {item['ref']: item for item in payload['dependencies']['labels']}
    if operation == 'update' and category.value != new_name:
        category.value = new_name
    if category is None:
        category = ConfigLabel(tenant_id=tenant.id, kind='category', value=new_name,
                               description='Workflow preparato con AlBot')
        db.session.add(category)
        db.session.flush()
    label_ids = {payload['workflow']['category_ref']: category.id}
    for label in payload['dependencies']['labels']:
        if label['ref'] in label_ids:
            continue
        current = _existing_label(tenant.id, label['kind'], label['value'])
        if current is None:
            current = ConfigLabel(tenant_id=tenant.id, **{field: label[field] for field in (
                'kind','group','value','description','max_completion_hours',
                'default_exportable','description_required','automatic_operations')})
            db.session.add(current)
            db.session.flush()
        elif label['kind'] == 'action_label':
            if (int(current.max_completion_hours or 0) != label['max_completion_hours'] or
                    bool(current.description_required) != label['description_required']):
                raise ValueError('I requisiti della label sono cambiati; rigenerare la proposta.')
        label_ids[label['ref']] = current.id
    # PDF and notifications are only linked to existing configured tenant resources.
    for item in payload['dependencies']['notification_types']:
        if NotificationType.query.filter_by(tenant_id=tenant.id, code=item['code'], enabled=True).first() is None:
            raise ValueError('Notifica non più disponibile: '+item['code'])
    for item in payload['dependencies']['form_templates']:
        _form_dependency(tenant, item['template_name'])
    if operation == 'update':
        for step in IncidentWorkflowStep.query.filter_by(tenant_id=tenant.id, category_id=category.id).all():
            db.session.delete(step)
        db.session.flush()
    for item in payload['workflow']['steps']:
        conditions=[]
        for cond in item['conditions']:
            token=cond['kind']
            if 'label_ref' in cond:
                token += ':'+str(label_ids[cond['label_ref']])
            conditions.append(('!' if cond['negated'] else '') + token)
        step = IncidentWorkflowStep(
            tenant_id=tenant.id, category_id=category.id, action_label_id=label_ids[item['action_label_ref']],
            position=item['position'], description=item['description'], required=item['required'],
            step_type=item['step_type'], requires_notification=item['requires_notification'],
            required_notification_type=item['required_notification_type'] or None,
            document_generation_enabled=item['document_generation_enabled'],
            document_template_name=item['document_template_name'] or None, section_target=item['section_target'] or None)
        step.set_condition_tokens(conditions)
        db.session.add(step)
    state = ensure_workflow_state(tenant.id, category.id, name=new_name)
    if operation == 'update':
        state.personalized = True
    db.session.flush()
    return {'name': new_name, 'tenant_id': tenant.id, 'category_id': category.id,
            'count': len(payload['workflow']['steps']), 'operation': operation}


def json_download(draft):
    """Only the portable catalog schema is exported, never session/auth metadata."""
    from flask import send_file
    payload = validate_catalog_payload(draft['payload'])
    filename = re.sub(r'[^a-zA-Z0-9_-]+', '_', draft['name']).strip('_')[:70] or 'workflow'
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    return send_file(io.BytesIO(raw), mimetype='application/json', as_attachment=True,
                     download_name='CIR_AlBot_'+filename+'.json')
