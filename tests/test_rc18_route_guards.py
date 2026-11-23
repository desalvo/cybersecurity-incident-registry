"""Exercise RC18 usage and obsolescence guards through authenticated HTTP.

The shared integration fixture starts the actual application and its database.
Local test labels deliberately have no defaults provenance, so a refusal must
come from incident usage rather than the independent inherited-label guard.
"""
from datetime import datetime, timezone

import pytest

from test_tenant_defaults_integration import defaults_app, _client


@pytest.fixture
def guarded_workflows(defaults_app):
    from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep, db
    from app.workflow_lifecycle import ensure_workflow_state

    ids = dict(defaults_app.config['TEST_DEFAULTS_IDS'])
    with defaults_app.app_context():
        labels = {
            'severity': ConfigLabel(tenant_id=ids['operational'], kind='severity',
                                    value='RC18 HTTP severity'),
            'category': ConfigLabel(tenant_id=ids['operational'], kind='category',
                                    value='RC18 HTTP original workflow'),
            'current_category': ConfigLabel(tenant_id=ids['operational'], kind='category',
                                            value='RC18 HTTP other current workflow'),
            'action_label': ConfigLabel(tenant_id=ids['operational'], kind='action_label',
                                        value='RC18 HTTP historical action'),
        }
        db.session.add_all(labels.values())
        db.session.flush()
        steps = []
        for key in ('category', 'current_category'):
            step = IncidentWorkflowStep(
                tenant_id=ids['operational'], category_id=labels[key].id,
                action_label_id=labels['action_label'].id, position=10,
                description=f'Workflow for {key}', required=False,
            )
            db.session.add(step)
            steps.append(step)
        db.session.flush()
        for key in ('category', 'current_category'):
            ensure_workflow_state(ids['operational'], labels[key].id)
        original = Incident(
            tenant_id=ids['operational'], creator_id=ids['manager'],
            name='RC18 original incident', reference='RC18-HTTP-ORIGINAL',
            severity_id=labels['severity'].id, status='aperto',
            categories=[labels['category']], category_order=str(labels['category'].id),
        )
        current = Incident(
            tenant_id=ids['operational'], creator_id=ids['manager'],
            name='RC18 current incident', reference='RC18-HTTP-CURRENT',
            severity_id=labels['severity'].id, status='aperto',
            categories=[labels['current_category']],
            category_order=str(labels['current_category'].id),
        )
        db.session.add_all([original, current])
        db.session.flush()
        action = Action(
            incident_id=original.id, label_id=labels['action_label'].id,
            when_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            description='Historical action that must survive configuration changes',
        )
        db.session.add(action)
        db.session.commit()
        ids.update({key: label.id for key, label in labels.items()})
        ids.update(original_incident=original.id, current_incident=current.id,
                   action=action.id, original_step=steps[0].id,
                   current_step=steps[1].id)
    return defaults_app, ids


def _flashes(client):
    with client.session_transaction() as session:
        return [message for _category, message in session.get('_flashes', ())]


def _assert_original_relations(app, ids):
    from app.models import Action, ConfigLabel, Incident, IncidentWorkflowStep, db
    from app.workflow_lifecycle import get_workflow_state

    with app.app_context():
        incident = db.session.get(Incident, ids['original_incident'])
        assert incident is not None
        assert incident.severity_id == ids['severity']
        assert [label.id for label in incident.categories] == [ids['category']]
        assert incident.category_order == str(ids['category'])
        action = db.session.get(Action, ids['action'])
        assert action is not None
        assert action.incident_id == incident.id
        assert action.label_id == ids['action_label']
        step = db.session.get(IncidentWorkflowStep, ids['original_step'])
        assert step is not None
        assert step.category_id == ids['category']
        assert step.action_label_id == ids['action_label']
        assert get_workflow_state(ids['operational'], ids['category']) is not None
        for key in ('severity', 'category', 'action_label'):
            assert db.session.get(ConfigLabel, ids[key]) is not None


@pytest.mark.parametrize('label_key', ['severity', 'category', 'action_label'])
def test_http_delete_used_local_label_preserves_incident_relations(guarded_workflows, label_key):
    app, ids = guarded_workflows
    client = _client(app)
    response = client.post(f"/admin/labels/{ids[label_key]}/delete")

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/labels')
    assert any('Cancellazione non consentita' in message for message in _flashes(client))
    _assert_original_relations(app, ids)


@pytest.mark.parametrize('whole_workflow', [False, True], ids=['single-step', 'entire-workflow'])
def test_http_delete_used_workflow_preserves_steps_and_incident(guarded_workflows, whole_workflow):
    app, ids = guarded_workflows
    client = _client(app)
    if whole_workflow:
        response = client.post('/admin/incident-workflows', data={
            'action': 'delete_workflow', 'delete_scope': f"category:{ids['category']}",
        })
    else:
        response = client.post(f"/admin/incident-workflows/{ids['original_step']}/delete")

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/incident-workflows')
    assert any('workflow utilizzato' in message for message in _flashes(client))
    _assert_original_relations(app, ids)


def _obsolete_original_workflow(app, ids):
    from app.models import db
    from app.workflow_lifecycle import set_workflow_status

    with app.app_context():
        set_workflow_status(ids['operational'], ids['category'], 'obsolete')
        db.session.commit()


def _incident_form(ids, *, category_key='category', name='Rejected reassignment', reference='RC18-HTTP-NEW'):
    return {
        'name': name, 'reference': reference, 'status': 'aperto',
        'severity_id': str(ids['severity']), 'categories': [str(ids[category_key])],
        'start_date': '2026-01-15', 'start_time': '10:00',
    }


@pytest.mark.parametrize('operation', ['new', 'clone', 'reassign'])
def test_http_obsolete_workflow_rejects_new_assignment_without_mutating_incidents(guarded_workflows, operation):
    from app.models import Incident, db
    from app.workflow_lifecycle import workflow_status

    app, ids = guarded_workflows
    _obsolete_original_workflow(app, ids)
    with app.app_context():
        count_before = Incident.query.count()
    client = _client(app)
    if operation == 'new':
        response = client.post('/incident/new', data=_incident_form(ids))
    elif operation == 'clone':
        response = client.post(f"/incident/{ids['original_incident']}/clone")
    else:
        response = client.post(f"/incident/{ids['current_incident']}", data=_incident_form(ids))

    assert response.status_code == 302
    assert '/login' not in response.headers['Location']
    assert any('workflow selezionato è obsoleto' in message for message in _flashes(client))
    with app.app_context():
        assert Incident.query.count() == count_before
        original = db.session.get(Incident, ids['original_incident'])
        current = db.session.get(Incident, ids['current_incident'])
        assert original.name == 'RC18 original incident'
        assert original.reference == 'RC18-HTTP-ORIGINAL'
        assert current.name == 'RC18 current incident'
        assert current.reference == 'RC18-HTTP-CURRENT'
        assert [row.id for row in current.categories] == [ids['current_category']]
        assert current.category_order == str(ids['current_category'])
        assert workflow_status(ids['operational'], ids['category']) == 'obsolete'
    _assert_original_relations(app, ids)


@pytest.mark.parametrize('scope', ['explicit-tenant', 'legacy-default', 'legacy-other-active-tenant'])
def test_http_existing_incident_keeps_editable_obsolete_workflow(guarded_workflows, scope):
    from app.models import ConfigLabel, Incident, IncidentWorkflowStep, db
    from app.workflow_lifecycle import workflow_status

    app, ids = guarded_workflows
    if scope != 'explicit-tenant':
        with app.app_context():
            db.session.get(Incident, ids['original_incident']).tenant_id = None
            if scope == 'legacy-other-active-tenant':
                # These fully legacy rows remain visible through the old NULL
                # scope, but their workflow belongs to the operational default,
                # not whichever tenant a superuser happens to have selected.
                db.session.get(ConfigLabel, ids['category']).tenant_id = None
                db.session.get(IncidentWorkflowStep, ids['original_step']).tenant_id = None
            db.session.commit()
    _obsolete_original_workflow(app, ids)
    client = (_client(app, role='superuser', tenant=ids['other'])
              if scope == 'legacy-other-active-tenant' else _client(app))
    response = client.post(f"/incident/{ids['original_incident']}", data=_incident_form(
        ids, name='Edited incident retaining historical workflow', reference='RC18-HTTP-ORIGINAL',
    ))

    assert response.status_code == 302
    assert f"/incident/{ids['original_incident']}" in response.headers['Location']
    assert any(message == 'Incidente aggiornato' for message in _flashes(client))
    with app.app_context():
        incident = db.session.get(Incident, ids['original_incident'])
        assert incident.name == 'Edited incident retaining historical workflow'
        assert incident.reference == 'RC18-HTTP-ORIGINAL'
        assert workflow_status(ids['operational'], ids['category']) == 'obsolete'
    _assert_original_relations(app, ids)
