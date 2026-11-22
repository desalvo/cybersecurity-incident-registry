"""Printed manuals must identify the exact staged source build used by CI."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentReleaseMetadataTests(unittest.TestCase):
    def test_long_configured_about_identity_keeps_complete_click_targets(self):
        from pypdf import PdfReader
        from application_identity import read_application_identity
        from scripts.documentation_cover import build_documentation_cover

        identity = read_application_identity(ROOT, environ={
            "APP_NAME": "Configured Cybersecurity Registry " * 4,
            "APP_AUTHOR": "Configured Author Name " * 6,
            "APP_AUTHOR_EMAIL": "person+" + "x" * 180 + "@example.org",
            "APP_PROJECT_URL": "https://example.org/project/" + "long-path-segment/" * 30,
        })
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "custom-cover.pdf"
            build_documentation_cover(output, root=ROOT, title="Manuale utente",
                                      subtitle="Gestione degli incidenti", identity=identity)
            reader = PdfReader(str(output))
            self.assertEqual(len(reader.pages), 1)
            text = reader.pages[0].extract_text() or ""
            self.assertIn("https://example.org/project/", text)
            self.assertIn("...", text)
            urls = {a.get_object().get("/A", {}).get("/URI")
                    for a in reader.pages[0].get("/Annots", [])}
            self.assertIn(identity["project_url"], urls)
            self.assertIn("mailto:" + identity["author_email"], urls)
            self.assertEqual(reader.metadata.author, identity["author"])
            self.assertIn(identity["name"], reader.metadata.title)

    def _copy_cover_inputs(self, project):
        for name in ("release_metadata.py", "application_identity.py"):
            shutil.copy2(ROOT / name, project)
        shutil.copy2(ROOT / "scripts/documentation_cover.py", project / "scripts")
        for name in ("help/app-logo.png", "ui/cybersecurity-hero-v2.png"):
            source = ROOT / "app/static" / name
            target = project / "app/static" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copytree(ROOT / "app/static/branding", project / "app/static/branding")

    def test_alfresco_manual_uses_staged_metadata_and_preserves_operational_chapters(self):
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "scripts").mkdir()
            (project / "docs").mkdir()
            (project / "VERSION").write_text("1.2.3-4\n", encoding="utf-8")
            (project / "BUILD").write_text("20301231\n", encoding="utf-8")
            self._copy_cover_inputs(project)
            shutil.copy2(ROOT / "scripts" / "build_alfresco_pdf.py", project / "scripts")
            shutil.copy2(ROOT / "docs" / "ADMIN_ALFRESCO.md", project / "docs")
            completed = subprocess.run(
                [sys.executable, str(project / "scripts" / "build_alfresco_pdf.py")],
                cwd=project, text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            reader = PdfReader(str(project / "docs" / "ADMIN_ALFRESCO.pdf"))
            cover = reader.pages[0].extract_text() or ""
            body = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("1.2.3-4", cover)
            self.assertIn("20301231", cover)
            for chapter in ("1. Ambito", "6. Sync Alfresco", "8. Diagnostica", "Nomi delle cartelle"):
                self.assertIn(chapter, body)
            self.assertNotIn("0.9.0-1", body)
            self.assertNotIn("Hotfix 6", body)

    def test_manuals_follow_staged_version_and_build_without_legacy_overrides(self):
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "scripts").mkdir()
            templates = project / "app" / "templates"
            templates.mkdir(parents=True)
            (project / "VERSION").write_text("1.2.3-4\n", encoding="utf-8")
            (project / "BUILD").write_text("20301231\n", encoding="utf-8")
            self._copy_cover_inputs(project)
            (project / "docs").mkdir()
            shutil.copy2(ROOT / "docs/ADMIN_ALFRESCO.md", project / "docs")
            (project / "app/static/help").mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "app/static/help/cybersecurity-brochure-strip.png", project / "app/static/help")
            for name in ("build_documentation_pdfs.py", "build_alfresco_pdf.py", "build_brochures.py", "build_incident_lab_pdf.py"):
                shutil.copy2(ROOT / "scripts" / name, project / "scripts")
            for name in ("help.html", "admin_help.html", "help_en.html", "admin_help_en.html"):
                (templates / name).write_text(
                    "{% block content %}<p>{{ app_info.version }} / {{ app_info.build }}</p>"
                    "<h2>1. Overview</h2><p>Example operating instructions.</p>{% endblock %}",
                    encoding="utf-8",
                )
            env = dict(os.environ, APP_VERSION="0.9.0-1", APP_BUILD="20260902")
            completed = subprocess.run(
                [sys.executable, str(project / "scripts" / "build_documentation_pdfs.py"),
                 "--include-brochures"],
                cwd=project, env=env, text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            manuals = sorted((project / "docs").glob("*.pdf"))
            self.assertEqual(len(manuals), 8)
            for path in manuals:
                with self.subTest(manual=path.name):
                    reader = PdfReader(str(path))
                    cover = reader.pages[0].extract_text() or ""
                    body = "\n".join(page.extract_text() or "" for page in reader.pages)
                    # Native cover embeds the application logo, the approved
                    # photograph and all six platform marks as separate assets.
                    self.assertGreaterEqual(len(reader.pages[0].images), 8)
                    self.assertIn("1.2.3-4", cover)
                    self.assertIn("20301231", cover)
                    if path.name in ("documentazione_utente.pdf", "documentazione_amministrativa.pdf",
                                     "user_documentation_en.pdf", "administrator_documentation_en.pdf"):
                        self.assertIn("1.2.3-4 / 20301231", body)
                    if path.name.startswith("brochure"):
                        for page in reader.pages[1:]:
                            self.assertIn("1.2.3-4", page.extract_text())
                            self.assertIn("20301231", page.extract_text())
                    for label in ("Alessandro De Salvo", "Alessandro.DeSalvo@roma1.infn.it",
                                  "https://github.com/desalvo/cybersecurity-incident-registry",
                                  "Docker", "Podman", "Kubernetes", "Helm", "OpenShift", "PostgreSQL",
                                  "linux/amd64", "linux/arm64"):
                        self.assertIn(label, cover)
                    cover_marker = "Supported platforms and technologies" if "_en" in path.stem else "Piattaforme e tecnologie supportate"
                    self.assertEqual(body.count(cover_marker), 1)
                    urls = {a.get_object().get("/A", {}).get("/URI")
                            for a in reader.pages[0].get("/Annots", [])}
                    self.assertIn("https://github.com/desalvo/cybersecurity-incident-registry", urls)
                    self.assertIn("mailto:Alessandro.DeSalvo@roma1.infn.it", urls)
                    self.assertNotIn("0.9.0-1", body)
                    self.assertNotIn("20260902", body)


if __name__ == "__main__":
    unittest.main()
