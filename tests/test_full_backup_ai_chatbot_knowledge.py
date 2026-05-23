"""Regression tests for full backups including AI Chatbot knowledge-base files."""
from __future__ import annotations

import tarfile

import pytest


@pytest.fixture()
def isolated_app(monkeypatch, tmp_path):
    base = tmp_path
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(base / "backup.db"))
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
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app

def test_full_backup_includes_ai_chatbot_knowledge_base_files(isolated_app):
    """Full backup/export must include physical AI Chatbot KB documents."""
    with isolated_app.app_context():
        from app.models import AIChatbotDocument, db
        from app.routes import BACKUP_CATEGORY_KEYS, build_backup_archive

        docs_dir = isolated_app.config["AI_CHATBOT_DOC_DIR"]
        docs_dir_path = __import__("pathlib").Path(docs_dir)
        docs_dir_path.mkdir(parents=True, exist_ok=True)
        stored_name = "kb-procedure.md"
        (docs_dir_path / stored_name).write_text("# Procedura chatbot\nContenuto operativo.", encoding="utf-8")

        db.session.add(
            AIChatbotDocument(
                title="Procedura chatbot",
                filename=stored_name,
                original_filename="procedura.md",
                content_type="text/markdown",
                size_bytes=(docs_dir_path / stored_name).stat().st_size,
                extracted_text="Procedura chatbot\nContenuto operativo.",
            )
        )
        db.session.commit()

        archive_path = build_backup_archive(BACKUP_CATEGORY_KEYS, prefix="test-full-backup")

    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
        assert "export.json" in names
        assert "files/persistent/ai_chatbot_docs/kb-procedure.md" in names
        member = archive.extractfile("files/persistent/ai_chatbot_docs/kb-procedure.md")
        assert member is not None
        assert "Contenuto operativo" in member.read().decode("utf-8")
