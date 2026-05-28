from pathlib import Path


def test_incident_detail_does_not_expose_template_autofill_controls():
    template = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    assert 'Applica modello incidente' not in template
    assert 'incident-detail-template-payloads' not in template
    assert 'data-template-target-form="incident-main-form"' not in template


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


def test_incident_template_payloads_are_limited_to_new_incident_and_admin_template_pages():
    routes = Path('app/routes.py').read_text(encoding='utf-8')
    assert 'def incident_template_client_payload(template):' in routes
    assert routes.count('incident_template_payloads=incident_template_client_payloads()') == 3
    assert "render_template(\n        'incident_detail.html'" in routes
    detail_render = routes.split("render_template(\n        'incident_detail.html'", 1)[1].split(')', 1)[0]
    assert 'incident_template_payloads' not in detail_render
    assert 'incident_templates' not in detail_render
    assert 'category_id_list()' in routes
    assert 'recommendation_id_list()' in routes


def test_incident_anchor_opens_and_scrolls_target_section():
    script = Path('app/static/app.js').read_text(encoding='utf-8')
    assert 'function openInitialIncidentAnchor' in script
    assert "window.setTimeout(()=>scrollToIncidentSection(section), 0);" in script
    assert "window.setTimeout(()=>scrollToIncidentSection(section), 100);" in script
    assert "window.addEventListener('hashchange', openInitialIncidentAnchor);" in script
