import requests
from .base import BaseEngine, AIEngineError

class OllamaEngine(BaseEngine):
    name='ollama'
    def generate(self, messages, system_context):
        endpoint=(self.config.get('endpoint') or 'http://localhost:11434/api/chat').rstrip('/')
        model=self.config.get('model') or 'llama3.1'
        payload={'model':model,'messages':[{'role':'system','content':system_context}]+messages,'stream':False}
        r=requests.post(endpoint,json=payload,timeout=120)
        if r.status_code>=400:
            raise AIEngineError(f'Errore Ollama: {r.status_code} {r.text[:300]}')
        return r.json().get('message',{}).get('content','')
