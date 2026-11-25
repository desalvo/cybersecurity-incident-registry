"""RC71 coverage: architecture, optional plugins, timing and permission framing."""
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'docs/presentation'
NS='{http://schemas.openxmlformats.org/drawingml/2006/main}'


def _plugin_packages(root: Path) -> set[str]:
    """Find Python plugin packages, not incidental runtime directories."""
    return {entry.name for entry in root.iterdir()
            if entry.is_dir() and (entry / '__init__.py').is_file()}


def test_architecture_addendum_and_role_scoping():
    arch=json.loads((P/'visual_rc71_architecture_addendum.json').read_text())
    spec=json.loads((P/'visual_rc64_spec.json').read_text())
    assert arch['insert_after_original']==6 and len(arch['slides'])==2
    assert [x['arch_visual'] for x in arch['slides']]==['modules','procedures']
    assert all(len(x['bullets'])==4 for x in arch['slides'])
    text=' '.join(' '.join(x['bullets']) for x in arch['slides'])
    for phrase in ('AlBot','Alfresco','ChatGPT','Claude','Gemini','Ollama','Perplexity',
                   'controlli', 'promemoria', 'scadenze', 'notifiche'):
        assert phrase.lower() in text.lower()
    assert 'modulare' in spec[5]['title'].lower()
    roles=' '.join(spec[34]['bullets']).lower()
    assert 'super admin' in roles and 'admin di tenant' in roles and 'operatori' in roles


def test_available_plugins_not_confused_with_core_features():
    directories=_plugin_packages(ROOT/'app/plugins')
    assert directories=={'ai_chatbot','alfresco'}
    source=(ROOT/'app/__init__.py').read_text()
    assert 'register_ai_chatbot_plugin(app)' in source
    assert 'register_alfresco_plugin(app)' in source
    engines=(ROOT/'app/plugins/ai_chatbot/engines/__init__.py').read_text()
    for name in ('chatgpt','claude','gemini','ollama','perplexity'):assert name in engines
    cfg=(ROOT/'app/templates/notification_settings.html').read_text()
    assert 'notification_deadline_schedule_mode' in cfg
    assert 'notification_incident_reminder_poll_seconds' in cfg


def test_plugin_package_discovery_ignores_runtime_and_non_plugin_folders(tmp_path):
    plugin_root = tmp_path / 'plugins'
    plugin_root.mkdir()
    for name in ('ai_chatbot', 'alfresco'):
        package = plugin_root / name
        package.mkdir()
        (package / '__init__.py').write_text('', encoding='utf-8')
    (plugin_root / '__pycache__').mkdir()
    (plugin_root / '__pycache__' / '__init__.cpython-312.pyc').write_bytes(b'cache')
    (plugin_root / 'generated').mkdir()
    assert _plugin_packages(plugin_root) == {'ai_chatbot', 'alfresco'}

    # A new real plugin must still be discovered rather than silently ignored.
    extension = plugin_root / 'future_extension'
    extension.mkdir()
    (extension / '__init__.py').write_text('', encoding='utf-8')
    assert _plugin_packages(plugin_root) == {'ai_chatbot', 'alfresco', 'future_extension'}


def test_presentation_cover_acronym_and_section_structure():
    pptx=P/'CIR_Operational_Training_Visual_RC71.pptx'
    with ZipFile(pptx) as z:
        names=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml') and '/_rels/' not in n]
        assert len(names)==87
        def txt(i):return ''.join(x.text or '' for x in ET.fromstring(z.read(f'ppt/slides/slide{i}.xml')).iter(NS+'t'))
        assert 'CIR' in txt(1) and 'Cybersecurity' in txt(1) and 'Incident Registry' in txt(1)
        assert 'laboratorio didattico di esempio' in txt(1)
        assert 'laboratorio SPAM' not in txt(1)
        assert 'laboratorio didattico di esempio' in (ROOT/'scripts/build_training_visual_rc64.js').read_text()
        assert 'Architettura modulare' in txt(6)
        assert 'Plugin disponibili' in txt(7)
        assert 'workflow manager generico' in txt(8)
        assert 'Aprire un incidente:' in txt(17)
        assert 'Aprire un incidente usando un modello' in txt(22)
