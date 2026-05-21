from datetime import datetime

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


CONSEQUENCE_RULES = [
    {
        'code': 'credentials',
        'enabled_key': 'consequence_rule_credentials_enabled',
        'text_key': 'consequence_rule_credentials_text',
        'default_text': 'Possibile compromissione di credenziali, accessi non autorizzati e necessità di rotazione password.',
        'matches': lambda inc, cats, data: any('credential' in c or 'credenzial' in c for c in cats) or any('password' in d for d in data),
    },
    {
        'code': 'phishing',
        'enabled_key': 'consequence_rule_phishing_enabled',
        'text_key': 'consequence_rule_phishing_text',
        'default_text': 'Possibile esposizione a messaggi fraudolenti, furto di informazioni o propagazione dell’attacco.',
        'matches': lambda inc, cats, data: any('phishing' in c for c in cats),
    },
    {
        'code': 'spam',
        'enabled_key': 'consequence_rule_spam_enabled',
        'text_key': 'consequence_rule_spam_text',
        'default_text': 'Possibile ricezione o invio di comunicazioni indesiderate e impatto sulla reputazione dei servizi.',
        'matches': lambda inc, cats, data: any('spam' in c for c in cats),
    },
    {
        'code': 'risk_rights_freedom',
        'enabled_key': 'consequence_rule_risk_rights_freedom_enabled',
        'text_key': 'consequence_rule_risk_rights_freedom_text',
        'default_text': 'Possibile rischio per diritti e libertà degli interessati.',
        'matches': lambda inc, cats, data: bool(getattr(inc, 'personal_data', False)) or any('dati personali' in d or 'rischio' in d for d in data),
    },
]


def default_consequence_settings():
    values = {
        'consequence_fallback_text': 'Conseguenze da valutare sulla base dell’analisi dell’incidente.',
    }
    for rule in CONSEQUENCE_RULES:
        values[rule['enabled_key']] = '1'
        values[rule['text_key']] = rule['default_text']
    return values


def configured_consequence_rules():
    rows = []
    for rule in CONSEQUENCE_RULES:
        rows.append({
            'code': rule['code'],
            'enabled_key': rule['enabled_key'],
            'text_key': rule['text_key'],
            'enabled': _setting_enabled(rule['enabled_key'], True),
            'text': _setting_value(rule['text_key'], rule['default_text']) or rule['default_text'],
            'default_text': rule['default_text'],
        })
    return rows


def incident_consequence_list(inc):
    cats = [(getattr(c, 'value', '') or '').lower() for c in getattr(inc, 'categories', [])]
    data = [(getattr(d, 'value', '') or '').lower() for d in getattr(inc, 'data_types', [])]
    out = []
    for rule in CONSEQUENCE_RULES:
        if not _setting_enabled(rule['enabled_key'], True):
            continue
        try:
            matches = bool(rule['matches'](inc, cats, data))
        except Exception:
            matches = False
        if matches:
            text = (_setting_value(rule['text_key'], rule['default_text']) or rule['default_text']).strip()
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
