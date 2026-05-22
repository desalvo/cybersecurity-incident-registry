import requests
from ..security import validate_ai_endpoint
from .base import BaseEngine, AIEngineError

class ClaudeEngine(BaseEngine):
    name='claude'
    def generate(self, messages, system_context):
        api_key=self.config.get('api_key')
        model=self.config.get('model') or 'claude-3-5-sonnet-latest'
        endpoint=validate_ai_endpoint(self.config.get('endpoint') or 'https://api.anthropic.com/v1/messages', 'claude')
        if not api_key:
            raise AIEngineError('API key Claude non configurata.')
        user_text='\n\n'.join(m.get('content','') for m in messages if m.get('role')=='user')
        payload={'model':model,'max_tokens':1200,'system':system_context,'messages':[{'role':'user','content':user_text}]}
        r=requests.post(endpoint,json=payload,headers={'x-api-key':api_key,'anthropic-version':'2023-06-01'},timeout=60)
        if r.status_code>=400:
            raise AIEngineError(f'Errore Claude: {r.status_code} {r.text[:300]}')
        data=r.json().get('content') or []
        return '\n'.join(part.get('text','') for part in data if part.get('type')=='text')
