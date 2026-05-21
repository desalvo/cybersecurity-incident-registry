from .base import AIEngineError
from .chatgpt import ChatGPTEngine
from .claude import ClaudeEngine
from .gemini import GeminiEngine
from .ollama import OllamaEngine
from .perplexity import PerplexityEngine

ENGINE_CLASSES = {
    'chatgpt': ChatGPTEngine,
    'claude': ClaudeEngine,
    'gemini': GeminiEngine,
    'ollama': OllamaEngine,
    'perplexity': PerplexityEngine,
}

def get_engine(name, config):
    cls = ENGINE_CLASSES.get((name or '').lower())
    if not cls:
        raise AIEngineError('Motore AI non supportato o non configurato.')
    return cls(config)
