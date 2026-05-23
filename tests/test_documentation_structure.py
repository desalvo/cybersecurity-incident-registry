from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_template(name: str) -> str:
    return (ROOT / "app" / "templates" / name).read_text(encoding="utf-8")


def test_user_documentation_sections_are_inside_template_block():
    html = _read_template("help.html")
    assert html.rstrip().endswith("{% endblock %}")
    assert html.count("{% endblock %}") == 1
    assert "### Rendering Markdown" not in html
    assert "14. Operazioni previste dell’incidente" in html
    assert "16. Rendering Markdown sicuro" in html
    assert html.index("Figura 1 - Flusso operativo consigliato") > html.index("1. Panoramica")


def test_admin_documentation_sections_are_numbered_and_inside_card():
    html = _read_template("admin_help.html")
    assert html.rstrip().endswith("{% endblock %}")
    assert html.count("{% endblock %}") == 1
    assert "### Rendering Markdown" not in html
    assert "6. Flussi operativi incidenti" in html
    assert "20. Destinatari esterni nei dati incidente" in html
    assert html.index("Figura 1 - Sequenza consigliata") > html.index("1. Responsabilità")
    assert html.index("20. Destinatari esterni nei dati incidente") < html.rindex("</div>")


def test_static_documentation_pdfs_are_packaged_and_regenerable():
    script = ROOT / "scripts" / "build_documentation_pdfs.py"
    user_pdf = ROOT / "docs" / "documentazione_utente.pdf"
    admin_pdf = ROOT / "docs" / "documentazione_amministrativa.pdf"
    assert script.exists(), "release packages must include the static PDF builder"
    assert user_pdf.exists() and user_pdf.stat().st_size > 50_000
    assert admin_pdf.exists() and admin_pdf.stat().st_size > 50_000


def test_pdf_generation_keeps_figures_near_referenced_chapters():
    routes = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")
    assert "visual_paths_by_chapter" in routes
    assert "'3': [('Figura 2 - Pagina principale" in routes
    assert "'11': [('Figura 3 - Configurazione template PDF" in routes
    assert "visual_inserted = False" not in routes


def test_docs_package_omits_source_model_docx_files():
    docs_dir = ROOT / "docs"
    assert not list(docs_dir.rglob("*.docx"))
    assert not (docs_dir / "source_models").exists()


def test_printable_documentation_filters_ui_chrome_and_editorial_notes():
    script = (ROOT / "scripts" / "build_documentation_pdfs.py").read_text(encoding="utf-8")
    routes = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")
    for text in (script, routes):
        assert "Menu" in text
        assert "Logout" in text
        assert "Il logo presente in questa guida" in text
        assert "Questa guida riorganizza le funzioni amministrative" in text
    for name in ("help.html", "admin_help.html"):
        html = _read_template(name)
        assert "Il logo presente in questa guida" not in html
        assert "Questa guida riorganizza le funzioni amministrative" not in html


def test_summary_brochure_pdf_is_packaged():
    brochure = ROOT / "docs" / "brochure_cybersecurity_incident_registry.pdf"
    assert brochure.exists()
    assert brochure.stat().st_size > 80_000


def test_summary_brochure_is_portrait_two_pages_and_has_required_features():
    from pypdf import PdfReader

    brochure = ROOT / "docs" / "brochure_cybersecurity_incident_registry.pdf"
    reader = PdfReader(str(brochure))
    assert len(reader.pages) <= 2
    for page in reader.pages:
        box = page.mediabox
        assert float(box.height) > float(box.width)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required_fragments = [
        "Interfacciabilità",
        "Configurabilità completa",
        "Notifiche automatiche",
        "Import di workflow custom",
        "PDF compilabili",
        "linee guida AGID",
        "Knowledge base opzionale",
        "European Union Public Licence",
        "Alessandro De Salvo",
        "https://github.com/desalvo/cybersecurity-incident-registry",
    ]
    for fragment in required_fragments:
        assert fragment in text


def test_release_notes_template_has_single_main_container():
    for name in ("release_notes.html", "release_notes_en.html"):
        html = _read_template(name)
        stripped = html.lstrip()
        assert stripped.startswith("{% extends 'base.html' %}")
        assert html.rstrip().endswith("{% endblock %}")
        assert html.count("{% block content %}") == 1
        assert html.count("{% endblock %}") == 1
        assert html.count("release-notes-text") == 1
        assert "{{ changelog }}" in html
        prefix = html.split("{% block content %}", 1)[0]
        assert "<section" not in prefix and "<div" not in prefix


def test_documentation_pages_expose_pdf_download_buttons():
    checks = {
        "help.html": "url_for('main.help_pdf')",
        "help_en.html": "url_for('main.help_pdf')",
        "admin_help.html": "url_for('main.admin_help_pdf')",
        "admin_help_en.html": "url_for('main.admin_help_pdf')",
        "release_notes.html": "url_for('main.release_notes_pdf')",
        "release_notes_en.html": "url_for('main.release_notes_pdf')",
    }
    for template, route_call in checks.items():
        html = _read_template(template)
        assert route_call in html
        assert "button secondary" in html
