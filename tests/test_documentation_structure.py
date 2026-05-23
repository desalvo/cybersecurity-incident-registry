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
