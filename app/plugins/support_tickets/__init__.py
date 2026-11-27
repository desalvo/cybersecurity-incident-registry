"""Optional collaborative, multi-tier Support Tickets plugin."""


def register_plugin(app):
    # Routes are imported only after app.__init__ finishes loading its models.
    from .routes import bp, is_enabled
    app.register_blueprint(bp)
    app.jinja_env.globals['support_tickets_plugin_enabled'] = is_enabled
