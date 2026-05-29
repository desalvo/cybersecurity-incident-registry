from pathlib import Path


def test_admin_menu_groups_plugin_configurations_under_plugins():
    template = Path('app/templates/base.html').read_text(encoding='utf-8')
    assert '<summary>Plugins</summary>' in template
    assert '>Chatbot AI</a>' in template
    assert '>Alfresco</a>' in template
    assert '>Plugin Alfresco</a>' not in template
    assert '<a role="menuitem" href="{{ url_for(\'ai_chatbot.admin_plugins\') }}">Plugins</a>' not in template


def test_chatbot_configuration_page_is_not_generic_plugins_page():
    template = Path('app/plugins/ai_chatbot/templates/ai_chatbot_admin_plugins.html').read_text(encoding='utf-8')
    assert '<h2>Chatbot AI</h2>' in template
    assert 'Salva configurazione Chatbot AI' in template
    assert 'Configura plugin Alfresco' not in template


def test_alfresco_configuration_page_uses_plugins_submenu_label():
    template = Path('app/plugins/alfresco/templates/alfresco_admin_plugins.html').read_text(encoding='utf-8')
    assert '<h2>Alfresco</h2>' in template
    docs = Path('app/templates/admin_help.html').read_text(encoding='utf-8')
    first_card = docs.split('</section>', 1)[0]
    assert 'Plugin Alfresco' not in first_card
    assert 'Admin → Plugins → Alfresco' in docs
