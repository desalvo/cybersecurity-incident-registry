"""Plugin AI Chatbot.

Il plugin resta isolato dal core applicativo: registra un blueprint, usa le
impostazioni generiche per la configurazione e delega ogni motore AI a un file
separato sotto engines/.
"""
from .routes import bp, is_enabled


def register_plugin(app):
    app.register_blueprint(bp)
    app.jinja_env.globals['ai_chatbot_plugin_enabled'] = is_enabled
