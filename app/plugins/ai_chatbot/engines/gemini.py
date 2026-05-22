import requests
from ..security import validate_ai_endpoint
from .base import BaseEngine, AIEngineError

class GeminiEngine(BaseEngine):
    name='gemini'
    def generate(self, messages, system_context):
        api_key=self.config.get('api_key')
        model=self.config.get('model') or 'gemini-1.5-flash'
        endpoint=validate_ai_endpoint(self.config.get('endpoint') or f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent', 'gemini')
        if not api_key:
            raise AIEngineError('API key Gemini non configurata.')
        text=system_context+'\n\nDomanda utente:\n'+'\n'.join(m.get('content','') for m in messages if m.get('role')=='user')
        r=requests.post(endpoint,params={'key':api_key},json={'contents':[{'parts':[{'text':text}]}]},timeout=60)
        if r.status_code>=400:
            raise AIEngineError(f'Errore Gemini: {r.status_code} {r.text[:300]}')
        return r.json()['candidates'][0]['content']['parts'][0]['text']
