"""Static invariants for child resources that do not carry tenant_id directly."""
import ast
from pathlib import Path

ROUTES_PATH = Path(__file__).resolve().parents[1] / 'app' / 'routes.py'
CHILD_MODELS = {'IncidentReminder', 'Action', 'ActionAttachment', 'Document'}


def _route_functions():
    source = ROUTES_PATH.read_text(encoding='utf-8')
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        decorators = [ast.get_source_segment(source, dec) or '' for dec in node.decorator_list]
        if any('.route' in dec for dec in decorators):
            yield source, node


def test_child_resource_routes_guard_parent_incident_visibility():
    unguarded = []
    for source, node in _route_functions():
        uses_child = False
        for call in ast.walk(node):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != 'model_or_404':
                continue
            if call.args and isinstance(call.args[0], ast.Name) and call.args[0].id in CHILD_MODELS:
                uses_child = True
                break
        if uses_child:
            body = ast.get_source_segment(source, node) or ''
            if 'visible(Incident.query)' not in body:
                unguarded.append(node.name)
    assert not unguarded, f'Child-resource routes missing parent tenant visibility guard: {unguarded}'


def test_generated_form_preview_is_bound_to_session_and_incident():
    source = ROUTES_PATH.read_text(encoding='utf-8')
    assert 'safe not in _allowed_generated_form_previews(iid)' in source
    assert 'allowed_preview_files = _allowed_generated_form_previews(iid)' in source
    assert '_register_generated_form_previews(inc.id' in source
