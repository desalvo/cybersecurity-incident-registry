"""RC77: tenant cloning never copies category workflows or leaves empty scopes."""
import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _fn(name):
    tree = ast.parse((ROOT / 'app/routes.py').read_text(encoding='utf-8'))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_generic_baseline_is_an_actual_workflow_and_idempotent_without_flask(monkeypatch):
    node = _fn('ensure_tenant_generic_default_workflow')
    code = compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<clone baseline>', 'exec')
    rows, actions = [], []

    class Lookup:
        def __init__(self, table): self.table = table
        def filter_by(self, **kwargs):
            self.kwargs = kwargs
            return self
        def first(self):
            source = rows if self.table == 'steps' else actions
            return next((x for x in source if all(getattr(x, k) == v for k, v in self.kwargs.items())), None)

    class ConfigLabel:
        query = Lookup('labels')
        def __init__(self, **kw): self.__dict__.update(kw); self.id = 0

    class IncidentWorkflowStep:
        query = Lookup('steps')
        def __init__(self, **kw): self.__dict__.update(kw)

    class Session:
        def add(self, row):
            if isinstance(row, ConfigLabel):
                if row not in actions:
                    row.id = len(actions) + 1
                    actions.append(row)
            else: rows.append(row)
        def flush(self): pass

    # Fallback to the neutral three-step workflow only when Tenants Default
    # has no published default. Normal provisioning now copies the shared one.
    import sys
    monkeypatch.setitem(sys.modules, 'app.workflow_defaults', SimpleNamespace(
        sync_tenant_default_workflow=lambda _tid: {'status': 'source_default_absent'}))
    ns = {'__name__': 'app.routes', '__package__': 'app',
          'IncidentWorkflowStep': IncidentWorkflowStep,
          'ConfigLabel': ConfigLabel, 'db': SimpleNamespace(session=Session()),
          'REGISTRATION_STEP_TYPE': 'registration'}
    exec(code, ns)
    ensure = ns['ensure_tenant_generic_default_workflow']
    ensure(45)
    assert [row.position for row in rows] == [10, 20, 30]
    assert [actions[row.action_label_id - 1].value for row in rows] == ['Apertura', 'Analisi', 'Conclusione']
    assert all(row.tenant_id == 45 and row.category_id is None and row.required for row in rows)
    ensure(45)
    assert len(rows) == 3 and len(actions) == 3
    ensure(46)
    assert len(rows) == 6 and len(actions) == 6


def test_tenant_clone_copies_no_workflow_definition_from_source():
    node = _fn('clone_tenant_config')
    source = ast.unparse(node)
    assert 'ensure_tenant_generic_default_workflow(dest_tenant_id)' in source
    assert 'for src in IncidentWorkflowStep.query' not in source
    assert 'IncidentWorkflowStep(tenant_id=dest_tenant_id' not in source
    assert 'sync_defaults_configuration()' in source


def test_workflow_selectors_do_not_present_empty_categories_as_installed_workflows():
    source = (ROOT / 'app/templates/admin_incident_workflows.html').read_text(encoding='utf-8')
    assert source.count('for opt in workflow_scope_options if opt.has_workflow %}') >= 2
    assert ' - vuoto' not in source
    # Administrative destinations remain able to accept an explicitly selected
    # category that currently has no workflow.
    assert 'name="category_id"' in source


def test_create_and_wizard_share_clone_policy():
    src = (ROOT / 'app/routes.py').read_text(encoding='utf-8')
    assert src.count('clone_tenant_config(source.id, tenant.id)') >= 2
    admin = (ROOT / 'app/templates/admin_tenants.html').read_text(encoding='utf-8')
    assert 'workflow predefinito generico' in admin
