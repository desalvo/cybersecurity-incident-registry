from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chatbot_markdown_renderer_supports_buttons_and_relative_targets():
    app_js = (ROOT / 'app' / 'static' / 'app.js').read_text()
    assert r'\{button:([^|{}\n]{1,80})\|' in app_js
    assert "[^\\s{}<>\"']{1,300}" in app_js
    assert 'isSafeMarkdownLinkTarget' in app_js
    assert "target.startsWith('#')" in app_js
    assert "target.startsWith('?')" in app_js
    assert "target.startsWith('/')" in app_js
    assert 'safe-markdown-button' in app_js


def test_markdown_button_style_is_shared_between_workflow_and_chatbot():
    style_css = (ROOT / 'app' / 'static' / 'style.css').read_text()
    assert '.workflow-markdown .workflow-button-link' in style_css
    assert '.ai-chatbot-markdown .workflow-button-link' in style_css
    assert '.safe-markdown-button' in style_css
