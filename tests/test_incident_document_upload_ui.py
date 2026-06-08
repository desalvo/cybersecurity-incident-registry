from pathlib import Path


def test_document_upload_button_disabled_until_file_selected_static():
    template = Path('app/templates/incident_detail.html').read_text(encoding='utf-8')
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    css = Path('app/static/style.css').read_text(encoding='utf-8')

    assert 'incident-document-upload-input' in template
    assert 'incident-document-upload-button' in template
    assert 'disabled aria-disabled="true"' in template
    assert 'initIncidentDocumentUploadButtons' in js
    assert 'fileInput.files && fileInput.files.length' in js
    assert 'event.preventDefault();' in js
    assert 'incident-document-upload-button:disabled' in css


def test_incident_section_top_icon_replaces_text_button_static():
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    css = Path('app/static/style.css').read_text(encoding='utf-8')

    assert 'section-scroll-top-icon' in js
    assert '⤒' in js
    assert 'Inizio pagina' not in js
    assert 'section.insertBefore(button, section.firstChild)' in js
    assert '.section-scroll-top-icon' in css
    assert '@media(max-width:820px)' in css
