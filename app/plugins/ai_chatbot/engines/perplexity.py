import requests
from .base import BaseEngine, AIEngineError

class PerplexityEngine(BaseEngine):
    name='perplexity'
    def generate(self, messages, system_context):
        api_key=self.config.get('api_key')
        model=self.config.get('model') or 'sonar'
        endpoint=self.config.get('endpoint') or 'https://api.perplexity.ai/chat/completions'
        if not api_key:
            raise AIEngineError('API key Perplexity non configurata.')
        payload={'model':model,'messages':[{'role':'system','content':system_context}]+messages,'temperature':0.2}
        r=requests.post(endpoint,json=payload,headers={'Authorization':f'Bearer {api_key}'},timeout=60)
        if r.status_code>=400:
            raise AIEngineError(f'Errore Perplexity: {r.status_code} {r.text[:300]}')
        return r.json()['choices'][0]['message']['content']
