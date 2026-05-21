class AIEngineError(RuntimeError):
    pass


class BaseEngine:
    name = 'base'
    def __init__(self, config):
        self.config = config or {}
    def generate(self, messages, system_context):
        raise NotImplementedError
