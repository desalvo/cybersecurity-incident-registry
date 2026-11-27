"""RC104: ensure templates are compilable and the CI provisions Node before PPTX tests."""
from pathlib import Path

from jinja2 import Environment
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_all_application_and_plugin_templates_compile():
    env = Environment()
    templates = sorted((ROOT / 'app/templates').rglob('*.html'))
    templates += sorted((ROOT / 'app/plugins').rglob('*.html'))
    assert len(templates) >= 70
    for template in templates:
        env.parse(template.read_text(encoding='utf-8'))


def test_quality_gates_install_pinned_pptx_dependencies_before_pytest():
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci-release.yml').read_text(encoding='utf-8'))
    quality = workflow['jobs']['quality-gates']
    steps = quality['steps']
    install = next(i for i, s in enumerate(steps) if s.get('name') == 'Install pinned presentation generator dependencies for pytest')
    pytest_idx = next(i for i, s in enumerate(steps) if s.get('name') == 'Run complete pytest suite')
    assert install < pytest_idx
    assert 'pptxgenjs@4.0.0 image-size@1.2.0' in steps[install]['run']
    pytest_step = steps[pytest_idx]
    assert pytest_step['env']['NODE_PATH'].endswith('/cir-visual-build-deps/node_modules')
    assert 'CIR_RELEASE_VERSION' in quality['env'] and 'CIR_RELEASE_BUILD' in quality['env']


def test_tenants_default_albot_only_under_existing_superadmin_guard():
    source = (ROOT / 'app/tenant_defaults_views.py').read_text(encoding='utf-8')
    assert 'if not is_superuser():' in source
    for route in ('ai_chatbot.chat', 'ai_chatbot.widget_ask', 'ai_chatbot.workflow_preview',
                  'ai_chatbot.workflow_download', 'ai_chatbot.workflow_apply'):
        assert repr(route) in source
    for template in ('app/templates/ui/header.html', 'app/templates/ui/navigation.html'):
        content = (ROOT / template).read_text(encoding='utf-8')
        assert 'current_user_is_superuser' in content


def test_ci_yaml_has_no_duplicate_mapping_keys_or_invalid_runner_in_job_env():
    class StrictLoader(yaml.SafeLoader):
        pass

    def disallow_duplicate_mapping(loader, node):
        pairs = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in pairs:
                raise AssertionError(f'Duplicate YAML key: {key!r}')
            pairs[key] = loader.construct_object(value_node, deep=True)
        return pairs

    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, disallow_duplicate_mapping)
    workflow = yaml.load((ROOT / '.github/workflows/ci-release.yml').read_text(encoding='utf-8'), Loader=StrictLoader)
    assert 'runner.temp' not in str(workflow['jobs']['quality-gates'].get('env', ''))
