from datetime import datetime
import json
import re

from .models import Setting


def _setting_value(key, default=''):
    try:
        obj = Setting.query.get(key)
        return obj.value if obj and obj.value is not None else default
    except Exception:
        return default


def _setting_enabled(key, default=True):
    raw = _setting_value(key, '1' if default else '0')
    return str(raw).strip().lower() not in {'0', 'false', 'no', 'off', 'disabled'}


LEGACY_CONSEQUENCE_RULES = [
    {
        'code': 'credentials',
        'enabled_key': 'consequence_rule_credentials_enabled',
        'text_key': 'consequence_rule_credentials_text',
        'default_text': 'Possibile compromissione di credenziali, accessi non autorizzati e necessità di rotazione password.',
        'conditions': [{'field': 'category', 'operator': 'contains_any', 'value': 'credential, credenzial'}, {'field': 'data_type', 'operator': 'contains_any', 'value': 'password'}],
        'condition_mode': 'any',
    },
    {
        'code': 'phishing',
        'enabled_key': 'consequence_rule_phishing_enabled',
        'text_key': 'consequence_rule_phishing_text',
        'default_text': 'Possibile esposizione a messaggi fraudolenti, furto di informazioni o propagazione dell’attacco.',
        'conditions': [{'field': 'category', 'operator': 'contains_any', 'value': 'phishing'}],
        'condition_mode': 'all',
    },
    {
        'code': 'spam',
        'enabled_key': 'consequence_rule_spam_enabled',
        'text_key': 'consequence_rule_spam_text',
        'default_text': 'Possibile ricezione o invio di comunicazioni indesiderate e impatto sulla reputazione dei servizi.',
        'conditions': [{'field': 'category', 'operator': 'contains_any', 'value': 'spam'}],
        'condition_mode': 'all',
    },
    {
        'code': 'risk_rights_freedom',
        'enabled_key': 'consequence_rule_risk_rights_freedom_enabled',
        'text_key': 'consequence_rule_risk_rights_freedom_text',
        'default_text': 'Possibile rischio per diritti e libertà degli interessati.',
        'conditions': [{'field': 'risk_rights_freedom', 'operator': 'is_true', 'value': ''}, {'field': 'data_type', 'operator': 'contains_any', 'value': 'dati personali, rischio'}],
        'condition_mode': 'any',
    },
]


def _default_rules():
    rules = []
    for idx, rule in enumerate(LEGACY_CONSEQUENCE_RULES, start=1):
        code = rule['code']
        text = _setting_value(rule.get('text_key', ''), rule['default_text']) or rule['default_text']
        enabled = _setting_enabled(rule.get('enabled_key', ''), True)
        rules.append({
            'id': code,
            'code': code,
            'enabled': enabled,
            'order': idx,
            'condition_mode': rule.get('condition_mode', 'all'),
            'conditions': list(rule.get('conditions') or []),
            'text': text,
            'default_text': rule['default_text'],
        })
    return rules


def default_consequence_settings():
    values = {
        'consequence_fallback_text': 'Conseguenze da valutare sulla base dell’analisi dell’incidente.',
        'consequence_rules_json': json.dumps(_default_rules(), ensure_ascii=False),
    }
    for rule in LEGACY_CONSEQUENCE_RULES:
        values[rule['enabled_key']] = '1'
        values[rule['text_key']] = rule['default_text']
    return values


def _normalise_rule(raw, index=0):
    if not isinstance(raw, dict):
        raw = {}
    code = re.sub(r'[^a-zA-Z0-9_\-]+', '_', str(raw.get('code') or raw.get('id') or f'rule_{index + 1}')).strip('_').lower() or f'rule_{index + 1}'
    text = str(raw.get('text') or raw.get('default_text') or '').strip()
    mode = str(raw.get('condition_mode') or 'all').lower()
    if mode not in {'all', 'any'}:
        mode = 'all'
    conditions = []
    for cond in raw.get('conditions') or []:
        if not isinstance(cond, dict):
            continue
        field = str(cond.get('field') or '').strip()
        operator = str(cond.get('operator') or '').strip()
        value = str(cond.get('value') or '').strip()
        if field and operator:
            conditions.append({'field': field, 'operator': operator, 'value': value})
    return {
        'id': str(raw.get('id') or code),
        'code': code,
        'enabled': bool(raw.get('enabled', True)),
        'order': int(raw.get('order') or index + 1),
        'condition_mode': mode,
        'conditions': conditions,
        'text': text,
        'default_text': str(raw.get('default_text') or text),
        # Compatibility keys used by older templates/routes.
        'enabled_key': f'consequence_dynamic_{code}_enabled',
        'text_key': f'consequence_dynamic_{code}_text',
    }


def parse_consequence_rules_json(raw):
    try:
        loaded = json.loads(raw or '')
    except Exception:
        loaded = None
    if not isinstance(loaded, list):
        return _default_rules()
    rules = [_normalise_rule(item, idx) for idx, item in enumerate(loaded)]
    rules = [r for r in rules if r.get('text')]
    return sorted(rules, key=lambda r: (r.get('order') or 0, r.get('code') or '')) or _default_rules()


def configured_consequence_rules():
    return parse_consequence_rules_json(_setting_value('consequence_rules_json', ''))


def serialize_consequence_rules_from_form(form):
    codes = form.getlist('consequence_rule_code')
    enabled_flags = form.getlist('consequence_rule_enabled')
    texts = form.getlist('consequence_rule_text')
    modes = form.getlist('consequence_rule_condition_mode')
    cond_fields = form.getlist('consequence_rule_condition_field')
    cond_ops = form.getlist('consequence_rule_condition_operator')
    cond_values = form.getlist('consequence_rule_condition_value')
    enabled_set = set(enabled_flags)
    rules = []
    for idx, code in enumerate(codes):
        code = re.sub(r'[^a-zA-Z0-9_\-]+', '_', (code or f'rule_{idx + 1}').strip()).strip('_').lower() or f'rule_{idx + 1}'
        text = (texts[idx] if idx < len(texts) else '').strip()
        if not text:
            continue
        mode = (modes[idx] if idx < len(modes) else 'all').strip().lower()
        if mode not in {'all', 'any'}:
            mode = 'all'
        prefix = f'{idx}:'
        conditions = []
        for cidx, field_token in enumerate(cond_fields):
            if not field_token.startswith(prefix):
                continue
            field = field_token.split(':', 1)[1].strip()
            operator = (cond_ops[cidx].split(':', 1)[1] if cidx < len(cond_ops) and ':' in cond_ops[cidx] else '').strip()
            value = (cond_values[cidx].split(':', 1)[1] if cidx < len(cond_values) and ':' in cond_values[cidx] else '').strip()
            if field and operator:
                conditions.append({'field': field, 'operator': operator, 'value': value})
        rules.append(_normalise_rule({
            'id': code,
            'code': code,
            'enabled': str(idx) in enabled_set or code in enabled_set,
            'order': idx + 1,
            'condition_mode': mode,
            'conditions': conditions,
            'text': text,
            'default_text': text,
        }, idx))
    return json.dumps(rules, ensure_ascii=False)


def _values_for_field(inc, field):
    field = (field or '').strip()
    if field == 'category':
        return [(getattr(c, 'value', '') or '') for c in getattr(inc, 'categories', [])]
    if field == 'data_type':
        return [(getattr(d, 'value', '') or '') for d in getattr(inc, 'data_types', [])]
    if field == 'severity':
        return [getattr(getattr(inc, 'severity', None), 'value', '') or '']
    if field == 'status':
        return [getattr(getattr(inc, 'status', None), 'value', '') or '']
    if field == 'risk_rights_freedom':
        return ['true' if bool(getattr(inc, 'personal_data', False)) else 'false']
    if hasattr(inc, field):
        val = getattr(inc, field)
        if isinstance(val, bool):
            return ['true' if val else 'false']
        return [str(val or '')]
    return []


def _tokens(value):
    return [x.strip().lower() for x in re.split(r'[,;\n]+', value or '') if x.strip()]


def _condition_matches(inc, cond):
    field = cond.get('field')
    operator = cond.get('operator')
    values = [str(v or '').lower() for v in _values_for_field(inc, field)]
    wanted = _tokens(cond.get('value', ''))
    if operator == 'is_true':
        return any(v in {'1', 'true', 'yes', 'si', 'sì'} for v in values)
    if operator == 'is_false':
        return not any(v in {'1', 'true', 'yes', 'si', 'sì'} for v in values)
    if operator == 'is_empty':
        return not any(v.strip() for v in values)
    if operator == 'is_not_empty':
        return any(v.strip() for v in values)
    if not wanted:
        return False
    if operator == 'equals_any':
        return any(v == token for v in values for token in wanted)
    if operator == 'not_equals_any':
        return all(v != token for v in values for token in wanted)
    if operator == 'contains_any':
        return any(token in v for v in values for token in wanted)
    if operator == 'not_contains_any':
        return all(token not in v for v in values for token in wanted)
    return False


def _rule_matches(inc, rule):
    conditions = rule.get('conditions') or []
    if not conditions:
        return True
    results = []
    for cond in conditions:
        try:
            results.append(bool(_condition_matches(inc, cond)))
        except Exception:
            results.append(False)
    return any(results) if rule.get('condition_mode') == 'any' else all(results)


def incident_consequence_list(inc):
    out = []
    for rule in configured_consequence_rules():
        if not rule.get('enabled', True):
            continue
        if _rule_matches(inc, rule):
            text = (rule.get('text') or '').strip()
            if text and text not in out:
                out.append(text)

    explicit = []
    actions = sorted(getattr(inc, 'actions', []) or [], key=lambda x: (getattr(x, 'when_at', None) or datetime.min, getattr(x, 'id', 0) or 0))
    for action in actions:
        text = (getattr(action, 'consequence_text', None) or '').strip()
        if text and text not in explicit:
            explicit.append(text)
    out.extend([text for text in explicit if text not in out])

    if not out:
        fallback = (_setting_value('consequence_fallback_text', 'Conseguenze da valutare sulla base dell’analisi dell’incidente.') or '').strip()
        if fallback:
            out.append(fallback)
    return out


def incident_consequences_text(inc):
    return '\n'.join(incident_consequence_list(inc))
