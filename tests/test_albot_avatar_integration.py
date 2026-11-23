from pathlib import Path
from html.parser import HTMLParser


def test_albot_avatar_asset_is_packaged():
    avatar = Path('app/static/ai-chatbot/albot-avatar.png')
    assert avatar.exists()
    assert avatar.stat().st_size > 1024
    assert avatar.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_classic_global_chatbot_retains_albot_name_and_avatar():
    template = Path('app/templates/base.html').read_text(encoding='utf-8')
    css = Path('app/static/style.css').read_text(encoding='utf-8')
    assert 'AlBot' in template
    assert 'Alex' in template
    assert "ai-chatbot/albot-avatar.png" in template
    assert "ai-chatbot/albot-avatar.png" in css
    assert '.ai-chatbot-message.bot::before' in css


def test_modern_global_chatbot_uses_neutral_conversation_symbol():
    template = Path('app/templates/ui/albot.html').read_text(encoding='utf-8')
    css = Path('app/static/ui/albot.css').read_text(encoding='utf-8')
    assert 'AlBot' in template
    assert '<svg' in template
    assert 'ai-chatbot/albot-avatar.png' not in template
    # The legacy full-page answer avatar is kept for the classic interface only.
    assert 'body.cir-modern .ai-chatbot-page-avatar{display:none}' in css


def test_albot_runtime_renders_one_widget_for_each_global_mode(monkeypatch, tmp_path):
    """Exercise real Flask rendering; CSS geometry remains a browser CI check."""
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'albot-modes.db'))
    for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
                'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR'):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv('SECRET_KEY', 'ALBOT-MODE-TEST-' * 5)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AlbotModeTestPassword123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.delenv('CIR_DISABLE_CSRF', raising=False)
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    from app import create_app
    from app.models import db, Setting, Tenant, User
    from app.ui_settings import GLOBAL_UI_MODE_KEY

    class Elements(HTMLParser):
        def __init__(self, html):
            super().__init__()
            self.elements = []
            self.feed(html)

        def handle_starttag(self, tag, attrs):
            self.elements.append((tag, dict(attrs)))

    app = create_app()
    app.config.update(TESTING=True)
    try:
        with app.app_context():
            tid = Tenant.query.filter_by(name='default').one().id
            uid = User.query.filter_by(username='admin', auth_provider='local').one().id
            db.session.merge(Setting(key=f'tenant:{tid}:plugin_ai_chatbot_enabled', value='1'))
            db.session.commit()
        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(uid)
            session['_fresh'] = True
            session['active_tenant_id'] = tid
            session['active_tenant_scope_enabled'] = True
        for mode in ('classic', 'modern'):
            with app.app_context():
                db.session.merge(Setting(key=GLOBAL_UI_MODE_KEY, value=mode))
                db.session.commit()
            for route in ('/', '/ai-chatbot'):
                response = client.get(route)
                assert response.status_code == 200, (mode, route)
                html = response.get_data(as_text=True)
                elements = Elements(html).elements
                ids = [attrs.get('id') for _tag, attrs in elements]
                assert ids.count('ai-chatbot-widget') == (1 if mode == 'classic' else 0)
                assert ids.count('cir-albot-panel') == (1 if mode == 'modern' else 0)
                assert ('ai-chatbot/albot-avatar.png' in html) == (mode == 'classic')
                assert 'AlBot' in html
                links = {attrs.get('href') for tag, attrs in elements if tag == 'a'}
                assert '/ai-chatbot/admin/plugins' in links
                assert '/alfresco/admin/plugins' in links
                if route == '/ai-chatbot':
                    assert any(tag == 'textarea' and attrs.get('id') == 'question'
                               and attrs.get('name') == 'question' for tag, attrs in elements)
                    assert any(tag == 'input' and attrs.get('name') == '_csrf_token'
                               and attrs.get('value') for tag, attrs in elements)
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def test_full_chat_page_uses_albot_avatar_next_to_answers():
    template = Path('app/plugins/ai_chatbot/templates/ai_chatbot_chat.html').read_text(encoding='utf-8')
    assert '<h2>AlBot</h2>' in template
    assert 'Risposta di AlBot' in template
    assert 'ai-chatbot-page-avatar' in template
    assert "ai-chatbot/albot-avatar.png" in template


def test_system_prompt_identifies_assistant_as_albot():
    source = Path('app/plugins/ai_chatbot/knowledge.py').read_text(encoding='utf-8')
    assert 'Sei AlBot' in source
    assert 'Alex' in source


def test_curated_albot_knowledge_base_is_packaged_and_prioritized():
    knowledge_doc = Path('docs/AI_CHATBOT_KNOWLEDGE.md')
    assert knowledge_doc.exists()
    text = knowledge_doc.read_text(encoding='utf-8')
    for fragment in (
        'Docker Compose',
        'Kubernetes',
        'Autenticazione configurabile',
        'Import workflow',
        'Full backup/full export',
        'Alessandro.DeSalvo@roma1.infn.it',
        'desalvo/cybersecurity-incident-registry',
        'European Union Public Licence',
    ):
        assert fragment in text
    source = Path('app/plugins/ai_chatbot/knowledge.py').read_text(encoding='utf-8')
    assert "'docs/AI_CHATBOT_KNOWLEDGE.md'" in source
    assert source.index("'docs/AI_CHATBOT_KNOWLEDGE.md'") < source.index("'docs/PROJECT_DESIGN.md'")
    assert 'def project_knowledge(max_chars=90000):' in source
