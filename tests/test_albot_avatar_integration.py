from pathlib import Path


def test_albot_avatar_asset_is_packaged():
    avatar = Path('app/static/ai-chatbot/albot-avatar.png')
    assert avatar.exists()
    assert avatar.stat().st_size > 1024
    assert avatar.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_global_chatbot_uses_albot_name_and_avatar():
    template = Path('app/templates/base.html').read_text(encoding='utf-8')
    css = Path('app/static/style.css').read_text(encoding='utf-8')
    assert 'AlBot' in template
    assert 'Alex' in template
    assert "ai-chatbot/albot-avatar.png" in template
    assert "ai-chatbot/albot-avatar.png" in css
    assert '.ai-chatbot-message.bot::before' in css


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
