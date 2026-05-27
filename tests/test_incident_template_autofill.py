from pathlib import Path


def test_incident_detail_exposes_template_autofill_controls():
    template = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    assert 'Applica modello incidente' in template
    assert 'data-incident-template-select="1"' in template
    assert 'incident-detail-template-payloads' in template
    assert 'data-template-target-form="incident-main-form"' in template


def test_new_incident_template_selection_is_client_side_autofill():
    template = Path('app/templates/incident_form.html').read_text(encoding='utf-8')
    assert 'id="incident-create-form"' in template
    assert 'data-incident-template-select="1"' in template
    assert 'incident-template-payloads' in template
    assert 'onchange="this.form.submit()"' not in template


def test_incident_template_autofill_javascript_covers_core_fields_and_dnd():
    script = Path('app/static/app.js').read_text(encoding='utf-8')
    assert 'function initIncidentTemplateAutofill' in script
    for field in ['name', 'reference', 'recipient', 'recipient_email', 'description', 'severity_id', 'status', 'personal_data', 'data_subjects_count', 'data_volume']:
        assert field in script
    for target in ['categories', 'data_types', 'people', 'recommendations']:
        assert f"setDropzone('{target}'" in script
    assert 'Modello applicato al form' in script


def test_incident_template_payload_is_sanitized_for_client():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    assert 'def incident_template_client_payload(template):' in routes
    assert 'incident_template_payloads=incident_template_client_payloads()' in routes
    assert 'category_id_list()' in routes
    assert 'recommendation_id_list()' in routes

def test_incident_anchor_opens_and_scrolls_target_section():
    script = Path('app/static/app.js').read_text(encoding='utf-8')
    assert 'function openInitialIncidentAnchor' in script
    assert "window.setTimeout(()=>scrollToIncidentSection(section), 0);" in script
    assert "window.setTimeout(()=>scrollToIncidentSection(section), 100);" in script
    assert "window.addEventListener('hashchange', openInitialIncidentAnchor);" in script

