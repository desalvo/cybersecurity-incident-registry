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
    assert "17. Rendering Markdown sicuro" in html
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


def test_release_notes_are_rendered_inside_single_main_card():
    html = _read_template("release_notes.html")
    assert html.startswith("{% extends 'base.html' %}")
    assert html.count("release-notes-page") == 1
    assert '<section class="doc-section">' not in html
    assert html.rstrip().endswith("{% endblock %}")


def test_user_pdf_callout_excludes_admin_configurations_and_chat_widget():
    routes = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")
    assert "moduli PDF, report ed export/import" in routes
    assert "moduli PDF, report, export/import e configurazioni amministrative" not in routes
    for fragment in ("AlBot anche Alex", "Helpdesk applicativo", "Domanda per AlBot"):
        assert fragment in routes


def test_static_pdf_builder_brochure_mentions_accessibility_localization():
    script = (ROOT / "scripts" / "build_documentation_pdfs.py").read_text(encoding="utf-8")
    assert "Interfaccia desktop e mobile accessibile" in script
    assert "Localizzazione ITA + ENG" in script
    assert "Le figure sono mantenute vicino al capitolo" not in script


def test_admin_static_pdf_has_no_orphan_chapter_titles():
    from pypdf import PdfReader
    import re

    pdf = ROOT / "docs" / "documentazione_amministrativa.pdf"
    reader = PdfReader(str(pdf))
    chapter_title_re = re.compile(r"^\d+[a-z]?\.\s+\S+", re.I)
    for page in reader.pages:
        lines = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
        if "Indice" in lines[:3]:
            continue
        content_lines = [
            line for line in lines
            if not line.startswith("Cybersecurity Incident Registry -") and not line.startswith("Pagina ")
        ]
        assert not content_lines or not chapter_title_re.match(content_lines[-1])


def test_static_pdf_builder_keeps_chapter_titles_with_initial_content():
    script = (ROOT / "scripts" / "build_documentation_pdfs.py").read_text(encoding="utf-8")
    assert "chapter heading is left orphaned" in script
    assert "story.append(KeepTogether(keep_block))" in script
    assert "is_subheading" in script


def test_downloadable_admin_pdf_has_no_orphan_chapter_titles(monkeypatch, tmp_path):
    from pypdf import PdfReader
    import io
    import re

    base = tmp_path
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(base / "docs.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(base / "uploads"))
    monkeypatch.setenv("LOGO_DIR", str(base / "logos"))
    monkeypatch.setenv("SSO_LOGO_DIR", str(base / "sso"))
    monkeypatch.setenv("FORM_TEMPLATE_DIR", str(base / "forms"))
    monkeypatch.setenv("BACKUP_DIR", str(base / "backups"))
    monkeypatch.setenv("AI_CHATBOT_DOC_DIR", str(base / "ai_docs"))
    monkeypatch.setenv("SECRET_KEY", "T" * 64)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "AdminPassword123!")
    monkeypatch.delenv("CIR_PRODUCTION", raising=False)

    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        client.get("/login")
        with client.session_transaction() as sess:
            token = sess["_csrf_token"]
        login = client.post(
            "/login",
            data={"username": "admin", "password": "AdminPassword123!", "_csrf_token": token},
            follow_redirects=False,
        )
        assert login.status_code in {302, 200}
        response = client.get("/aiuto/amministrazione/pdf")

    assert response.status_code == 200
    reader = PdfReader(io.BytesIO(response.data))
    chapter_title_re = re.compile(r"^\d+[a-z]?\.\s+\S+", re.I)
    for page in reader.pages:
        lines = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
        if "Indice" in lines[:3]:
            continue
        content_lines = [
            line for line in lines
            if not line.startswith("Cybersecurity Incident Registry -") and not line.startswith("Pagina ")
        ]
        assert not content_lines or not chapter_title_re.match(content_lines[-1])


def test_static_english_documentation_pdfs_are_packaged():
    for name in (
        "user_documentation_en.pdf",
        "administrator_documentation_en.pdf",
        "brochure_cybersecurity_incident_registry_en.pdf",
    ):
        pdf = ROOT / "docs" / name
        assert pdf.exists(), f"missing English PDF artifact: {name}"
        assert pdf.stat().st_size > 50_000


def test_static_english_brochure_is_portrait_two_pages():
    from pypdf import PdfReader

    brochure = ROOT / "docs" / "brochure_cybersecurity_incident_registry_en.pdf"
    reader = PdfReader(str(brochure))
    assert len(reader.pages) <= 2
    for page in reader.pages:
        box = page.mediabox
        assert float(box.height) > float(box.width)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for fragment in (
        "Docker Hub",
        "Docker Compose",
        "Kubernetes",
        "Italian + English localization",
        "European Union Public Licence",
        "https://github.com/desalvo/cybersecurity-incident-registry",
    ):
        assert fragment in text


def test_brochures_use_infn_creator_email():
    from pypdf import PdfReader

    for name in (
        'brochure_cybersecurity_incident_registry.pdf',
        'brochure_cybersecurity_incident_registry_en.pdf',
    ):
        pdf = ROOT / 'docs' / name
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(str(pdf)).pages)
        assert 'Alessandro.DeSalvo@roma1.infn.it' in text
        assert 'braket71@gmail.com' not in text
