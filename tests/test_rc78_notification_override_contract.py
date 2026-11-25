"""Dependency-free source contract checks; full DB integration runs in CI."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _functions(filename):
    return {node.name: ast.unparse(node) for node in ast.parse((ROOT / filename).read_text()) .body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_shared_notification_keys_are_adopted_without_suffixes():
    funcs = _functions('app/tenant_defaults.py')
    sync = funcs['_sync_source_to_tenant']
    assert "if source.source_type in _LOCAL_NOTIFICATION_MARKERS" in sync
    assert '_notification_identity_matches' in sync
    assert '_local_notification_snapshot' in sync
    assert 'candidate.id' in sync and 'TenantDefaultReplica(' in sync
    assert 'dict(mapped)' in sync


def test_local_notification_edits_and_deletion_restore_default():
    funcs = _functions('app/tenant_defaults.py')
    assert '_locally_owned_notification_replica(replica)' in funcs['_sync_source_to_tenant']
    assert 'replica.snapshot_json = _local_notification_snapshot' in funcs['_sync_source_to_tenant']
    assert '_locally_owned_notification_replica(replica)' in funcs['_retire_source']
    assert '_locally_owned_notification_replica(replica)' in funcs['inherited_configuration_record']
    routes = _functions('app/routes.py')
    assert "kind != 'notification_template'" in routes['_shared_configuration_delete_blocked']
    assert "restored = current_tenant_notification_template_query(kind)" in routes['notification_template']


def test_cloning_preserves_destination_notification_overrides():
    code = _functions('app/routes.py')['_copy_notification_template_to_tenant']
    assert 'if existing:' in code
    assert 'return existing' in code
    branch = code.split('if existing:', 1)[1].split('clone = NotificationTemplate', 1)[0]
    assert 'setattr(existing' not in branch


def test_notification_matching_is_scoped_to_kind_and_name():
    funcs = _functions('app/tenant_defaults.py')
    f = funcs['_notification_identity_matches']
    assert 'row.kind == data[\'kind\']' in f
    assert '_category_equivalent(row.name, data[\'name\'])' in f
    assert '_category_equivalent(row.code, data[\'code\'])' in f
