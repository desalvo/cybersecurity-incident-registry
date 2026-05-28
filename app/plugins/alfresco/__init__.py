"""Plugin Alfresco document storage.

Optional plugin disabled by default. It exposes helpers and a small admin
configuration page while the core incident document UI checks whether it is
enabled before offering Alfresco upload/download actions.
"""
from .routes import bp, is_enabled


def register_plugin(app):
    app.register_blueprint(bp)
    app.jinja_env.globals['alfresco_plugin_enabled'] = is_enabled
