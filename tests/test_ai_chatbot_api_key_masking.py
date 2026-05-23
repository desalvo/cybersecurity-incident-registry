"""Regression tests for AI Chatbot API key masking and overwrite-only behavior."""
from pathlib import Path


def test_ai_chatbot_admin_template_never_renders_raw_api_key_value():
    template = Path('app/plugins/ai_chatbot/templates/ai_chatbot_admin_plugins.html').read_text(encoding='utf-8')
    assert 'value="{{ config.configs[engine].api_key }}"' not in template
    assert 'masked_api_key' in template
    assert 'type="password"' in template
    assert 'lascia vuoto per mantenere quella esistente' in template


def test_ai_chatbot_plugin_config_exposes_mask_metadata():
    source = Path('app/plugins/ai_chatbot/routes.py').read_text(encoding='utf-8')
    assert 'def _mask_secret' in source
    assert "'has_api_key'" in source
    assert "'masked_api_key'" in source
    assert 'Il valore reale non viene visualizzato' not in source


def test_ai_chatbot_empty_api_key_post_preserves_existing_secret():
    source = Path('app/plugins/ai_chatbot/routes.py').read_text(encoding='utf-8')
    assert 'Empty API key fields mean "keep the current secret"' in source
    assert "if value.strip():" in source
    assert 'set_setting_value(f\'ai_chatbot_{name}_{field}\', value.strip())' in source
