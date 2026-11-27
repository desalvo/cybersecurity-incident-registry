"""RC77: workflow/category names are coupled; severity names are deduplicated."""
import ast
from pathlib import Path


def _catalog_source():
    return Path(__file__).resolve().parents[1] / 'app' / 'workflow_catalog.py'


def _functions(names):
    tree = ast.parse(_catalog_source().read_text(encoding='utf-8'))
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names}


def test_catalog_copy_name_collision_policy_without_flask():
    """Exercise the real pure naming function without importing Flask."""
    (node,) = _functions({'_catalog_copy_name'}).values()
    # The helper's import uses Flask models; in isolation stand-ins have the
    # same .query(...) result contract.
    node.body = [part for part in node.body if not isinstance(part, ast.ImportFrom)]
    mod = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))

    from types import SimpleNamespace

    class Query:
        def __init__(self, source):
            self.source = source

        def filter_by(self, **kwargs):
            return self

        def all(self):
            return [SimpleNamespace(**{self.source: x}) for x in data[self.source]]

    class ConfigLabel:
        query = Query('value')

    class TenantWorkflow:
        query = Query('name')

    data = {'value': [], 'name': []}
    import re
    ns = {'ConfigLabel': ConfigLabel, 'TenantWorkflow': TenantWorkflow, 're': re,
          '_available_workflow_category': lambda tenant_id, name: next(
              (SimpleNamespace(value=v) for v in data['value']
               if v.strip().casefold() == name.strip().casefold() and v not in data['assigned']), None)}
    data['assigned'] = []
    exec(compile(mod, '<workflow naming>', 'exec'), ns)
    choose = ns['_catalog_copy_name']
    assert choose('SPAM', 5) == 'SPAM'
    data['value'] = ['SPAM']
    assert choose('SPAM', 5) == 'SPAM'  # unassigned category can be reused
    data['name'] = ['SPAM']
    assert choose('SPAM', 5) == 'SPAM v2'
    data['name'] = ['SPAM', 'SPAM v2']
    assert choose('SPAM', 5) == 'SPAM v3'
    data['value'] = ['  spam  ', 'SPAM v2']
    data['name'] = []
    assert choose('SPAM', 5) == 'spam'  # category display name retained
    data['assigned'] = ['  spam  ']
    assert choose('SPAM', 5) == 'SPAM v2'  # v2 label is also free
    assert choose('Other', 5) == 'Other'
    data['value'] = ['X' * 160]
    data['name'] = ['X' * 160]
    assert choose('X' * 160, 5) == 'X' * 157 + ' v2'


def test_catalog_severity_resolution_and_unassigned_category_reuse():
    tree = _functions({'_materialize_workflow_payload', 'import_catalog_workflow'})
    materializer = ast.unparse(tree['_materialize_workflow_payload'])
    installer = ast.unparse(tree['import_catalog_workflow'])
    assert "item['kind'] == 'severity'" in materializer
    assert "item['ref'] == wf['category_ref']" in materializer
    assert '_catalog_copy_name(copy_name, target.id)' in installer
    assert "_available_workflow_category(target.id, copy_name)" in materializer


def test_catalog_severity_matching_preserves_original_record_without_flask():
    from types import SimpleNamespace

    (node,) = _functions({'_existing_tenant_severity'}).values()
    mod = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))

    critical = SimpleNamespace(id=42, value='Critical', description='Tenant setting', max_completion_hours=8)
    other = SimpleNamespace(id=43, value='High', description='Other tenant setting')

    class Query:
        def filter_by(self, **kwargs):
            assert kwargs == {'tenant_id': 9, 'kind': 'severity'}
            return self

        def order_by(self, field):
            return (critical, other)

    class ConfigLabel:
        id = object()
        query = Query()

    ns = {'ConfigLabel': ConfigLabel}
    exec(compile(mod, '<severity resolution>', 'exec'), ns)
    find = ns['_existing_tenant_severity']
    assert find(9, 'critical') is critical
    assert find(9, ' CRITICAL ') is critical
    assert find(9, 'high') is other
    assert find(9, 'Medium') is None
    assert critical.description == 'Tenant setting' and critical.max_completion_hours == 8
