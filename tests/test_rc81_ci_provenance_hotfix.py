"""Regression contracts for same-run Wizard crops and full-restore provenance.

No Flask application or database is required by these narrow, read-only tests.
The full application's import, browser and publishing flows remain CI gates.
"""
import json
import uuid

import pytest

from test_rc65_ci_regressions import _pure_archive_validator


def _notification_override_archive():
    type_source = str(uuid.uuid4())
    template_source = str(uuid.uuid4())
    type_shared = {'id': 10, 'tenant_id': 1, 'code': 'notice', 'label': 'Shared notice',
                   'description': '', 'enabled': True}
    type_local = {'id': 11, 'tenant_id': 2, 'code': 'notice', 'label': 'Tenant override',
                  'description': '', 'enabled': True}
    template_shared = {'id': 20, 'tenant_id': 1, 'kind': 'notice', 'name': 'Email',
                       'subject': 'Shared subject', 'body': '',
                       'linked_form_template_name': None, 'action_label_id': None,
                       'recipient_source': 'empty', 'recipient_value': '',
                       'recipient_editable': True, 'recipient_external_allowed': True,
                       'cc_source': 'empty', 'cc_value': '', 'cc_editable': True,
                       'cc_external_allowed': True, 'is_default': True}
    template_local = {**template_shared, 'id': 21, 'tenant_id': 2,
                      'subject': 'Tenant subject'}
    return {
        'tenants': [{'id': 1, 'name': 'Tenants Default', 'is_system_defaults': True},
                    {'id': 2, 'name': 'Tutorial', 'is_system_defaults': False}],
        'notification_types': [type_shared, type_local],
        'notification_templates': [template_shared, template_local],
        'tenant_default_sources': [
            {'id': type_source, 'source_type': 'notification_type', 'source_id': 10,
             'active': True, 'snapshot_json': json.dumps({k: v for k, v in type_shared.items() if k not in {'id', 'tenant_id'}})},
            {'id': template_source, 'source_type': 'notification_template', 'source_id': 20,
             'active': True, 'snapshot_json': json.dumps({k: v for k, v in template_shared.items() if k not in {'id', 'tenant_id'}})},
        ],
        'tenant_default_replicas': [
            {'id': 1, 'source_id': type_source, 'tenant_id': 2,
             'local_type': 'notification_type', 'local_id': 11,
             'snapshot_json': json.dumps({'code': 'notice', 'label': 'Tenant override',
                                          '__cir_existing_tenant_notification_type': True})},
            {'id': 2, 'source_id': template_source, 'tenant_id': 2,
             'local_type': 'notification_template', 'local_id': 21,
             'snapshot_json': json.dumps({'kind': 'notice', 'name': 'Email',
                                          'subject': 'Tenant subject',
                                          '__cir_existing_tenant_notification_template': True})},
        ],
    }


def test_valid_local_notification_overrides_survive_full_import_validation(monkeypatch):
    validate = _pure_archive_validator(monkeypatch)
    assert validate(_notification_override_archive()) is True


@pytest.mark.parametrize('change', ['false_marker', 'string_marker', 'wrong_marker_kind',
                                    'different_code', 'different_template_name',
                                    'foreign_owner'])
def test_forged_notification_override_provenance_fails_closed(monkeypatch, change):
    validate = _pure_archive_validator(monkeypatch)
    tables = _notification_override_archive()
    replica = tables['tenant_default_replicas'][0]
    snapshot = json.loads(replica['snapshot_json'])
    if change == 'false_marker':
        snapshot['__cir_existing_tenant_notification_type'] = False
    elif change == 'string_marker':
        snapshot['__cir_existing_tenant_notification_type'] = 'true'
    elif change == 'wrong_marker_kind':
        snapshot['__cir_existing_tenant_notification_template'] = True
    elif change == 'different_code':
        tables['notification_types'][1]['code'] = 'unrelated'
    elif change == 'different_template_name':
        tables['notification_templates'][1]['name'] = 'Unrelated'
    elif change == 'foreign_owner':
        replica['tenant_id'] = 1
    replica['snapshot_json'] = json.dumps(snapshot)
    with pytest.raises(ValueError, match='Archivio Tenants Default non valido'):
        validate(tables)
