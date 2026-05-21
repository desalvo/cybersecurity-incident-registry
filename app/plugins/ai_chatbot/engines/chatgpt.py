import requests
from .base import BaseEngine, AIEngineError

class ChatGPTEngine(BaseEngine):
    name='chatgpt'
    def generate(self, messages, system_context):
        api_key=self.config.get('api_key')
        model=self.config.get('model') or 'gpt-4o-mini'
        endpoint=self.config.get('endpoint') or 'https://api.openai.com/v1/chat/completions'
        if not api_key:
            raise AIEngineError('API key ChatGPT non configurata.')
        payload={'model':model,'messages':[{'role':'system','content':system_context}]+messages,'temperature':0.2}
        r=requests.post(endpoint,json=payload,headers={'Authorization':f'Bearer {api_key}'},timeout=60)
        if r.status_code>=400:
            raise AIEngineError(f'Errore ChatGPT: {r.status_code} {r.text[:300]}')
        return r.json()['choices'][0]['message']['content']
