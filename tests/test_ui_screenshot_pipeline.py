"""Security and release contracts for real UI documentation evidence.

Browser flows themselves run in the required ui-documentation CI job. These
tests exercise preflight/isolation and workflow fail-closed semantics without
starting a browser or requiring a downloaded browser binary during pytest.
"""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts import capture_ui_screenshots as capture
from scripts import ui_documentation_evidence as evidence
from scripts.seed_ui_documentation import STORAGE_ENV, isolated_environment, seed_documentation_app

ROOT = Path(__file__).resolve().parents[1]


def capture_entries():
    return [{"id": name, "ui_mode": "classic" if name.startswith("classic-") else "modern",
             "sha256": "a" * 64} for name in sorted(capture.REQUIRED_CAPTURES)]


class ScreenshotIsolationTests(unittest.TestCase):
    def test_inherited_production_database_and_secret_files_are_not_used(self):
        original = {"DATABASE_URL": "postgresql://private.invalid/production",
                    "DATABASE_URL_FILE": "/private/database-secret",
                    "SECRET_KEY_FILE": "/private/session-secret",
                    "SETTING_ENCRYPTION_KEY_FILE": "/private/encryption-secret",
                    "CIR_PRODUCTION": "1", "FLASK_ENV": "production", "CIR_DISABLE_CSRF": "1"}
        with patch.dict(os.environ, original), tempfile.TemporaryDirectory() as directory:
            with isolated_environment(Path(directory)) as private:
                self.assertEqual(os.environ["DATABASE_URL"], "sqlite:///" + str(Path(directory).resolve() / "documentation.sqlite"))
                for key in ("DATABASE_URL_FILE", "SECRET_KEY_FILE", "SETTING_ENCRYPTION_KEY_FILE"):
                    self.assertNotIn(key, os.environ)
                self.assertEqual(os.environ["CIR_DISABLE_CSRF"], "0")
                self.assertEqual(os.environ["CIR_PRODUCTION"], "0")
                self.assertEqual(os.environ["CIR_DISABLE_BACKGROUND_SCHEDULERS"], "1")
                self.assertGreaterEqual(len(private["password"]), 32)
                self.assertNotEqual(os.environ["SECRET_KEY"], os.environ["SETTING_ENCRYPTION_KEY"])
                for key in STORAGE_ENV:
                    self.assertTrue(Path(os.environ[key]).is_relative_to(Path(directory).resolve()))
            for key, value in original.items():
                self.assertEqual(os.environ[key], value)

    def test_fixture_rejects_nonempty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "keep.txt"
            existing.write_text("keep")
            with self.assertRaises(ValueError):
                with isolated_environment(Path(directory)):
                    self.fail("Existing directory was accepted")
            self.assertEqual(existing.read_text(), "keep")

    def test_seed_rejects_existing_database_before_importing_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with isolated_environment(root):
                database = root / "documentation.sqlite"
                database.write_bytes(b"existing")
                with self.assertRaisesRegex(ValueError, "existing"):
                    seed_documentation_app(root, "unused", "http://127.0.0.1:1/api/chat")
                self.assertEqual(database.read_bytes(), b"existing")

    def test_seed_rejects_remote_ai_endpoint_before_importing_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with isolated_environment(root):
                with self.assertRaisesRegex(ValueError, "loopback"):
                    seed_documentation_app(root, "unused", "https://provider.example.org/api/chat")
                self.assertFalse((root / "documentation.sqlite").exists())

    def test_output_rejects_existing_files_without_deleting_them(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "keep.txt"
            existing.write_text("keep")
            with self.assertRaises(ValueError):
                capture.prepare_output(Path(directory))
            self.assertEqual(existing.read_text(), "keep")

    def test_output_cannot_replace_application_sources(self):
        with self.assertRaises(ValueError):
            capture.prepare_output(ROOT / "app" / "ui-documentation")

    def test_fresh_output_has_screenshot_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = capture.prepare_output(Path(directory) / "evidence")
            self.assertTrue((output / "screenshots").is_dir())
            self.assertEqual(list(output.iterdir()), [output / "screenshots"])


class ScreenshotEvidenceTests(unittest.TestCase):
    def test_capture_and_manual_builder_require_the_same_views(self):
        self.assertEqual(capture.REQUIRED_CAPTURES, evidence.REQUIRED_SCREENSHOTS)

    def test_complete_capture_set_accepted(self):
        capture.validate_capture_set(capture_entries())

    def test_missing_capture_is_rejected(self):
        with self.assertRaises(ValueError):
            capture.validate_capture_set(capture_entries()[:-1])

    def test_duplicate_capture_is_rejected(self):
        entries = capture_entries()
        entries[-1] = entries[0]
        with self.assertRaises(ValueError):
            capture.validate_capture_set(entries)

    def test_unhashed_capture_is_rejected(self):
        entries = capture_entries()
        entries[0]["sha256"] = "pending"
        with self.assertRaises(ValueError):
            capture.validate_capture_set(entries)

    def test_invalid_ui_mode_is_rejected(self):
        entries = capture_entries()
        entries[0]["ui_mode"] = "mock"
        with self.assertRaises(ValueError):
            capture.validate_capture_set(entries)

    def test_commit_must_match_checkout(self):
        with patch.object(capture.subprocess, "check_output", return_value="b" * 40 + "\n"):
            with self.assertRaisesRegex(ValueError, "does not match"):
                capture.source_commit("a" * 40)

    def test_dirty_checkout_cannot_claim_exact_commit(self):
        with patch.object(capture.subprocess, "check_output", side_effect=["a" * 40 + "\n", " M app/templates/index.html\n"]):
            with self.assertRaisesRegex(ValueError, "clean"):
                capture.source_commit("a" * 40)

    def test_untracked_application_code_cannot_claim_exact_commit(self):
        with patch.object(capture.subprocess, "check_output", side_effect=["a" * 40 + "\n", "", "app/ui.py\n"]):
            with self.assertRaisesRegex(ValueError, "Untracked"):
                capture.source_commit("a" * 40)

    def test_clean_matching_checkout_is_accepted(self):
        with patch.object(capture.subprocess, "check_output", side_effect=["a" * 40 + "\n", "", ""]):
            self.assertEqual(capture.source_commit("a" * 40), "a" * 40)

    def test_exact_ci_generated_build_overlay_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "BUILD").write_text("20270115\n")
            with patch.object(capture, "ROOT", root), patch.dict(os.environ, {"CIR_RELEASE_BUILD": "20270115"}):
                with patch.object(capture.subprocess, "check_output", side_effect=["a" * 40 + "\n", " M BUILD\n", ""]):
                    self.assertEqual(capture.source_commit("a" * 40), "a" * 40)

    def test_ci_build_overlay_does_not_authorize_other_source_or_metadata_changes(self):
        cases = ((" M BUILD\n M VERSION\n", "20270115\n", "20270115"),
                 (" M BUILD\n M app/routes.py\n", "20270115\n", "20270115"),
                 ("M  BUILD\n", "20270115\n", "20270115"),
                 (" M BUILD\n", "20270115\n", ""),
                 ("", "20270114\n", "20270115"),
                 (" M BUILD\n", "20270114\n", "20270115"),
                 (" M BUILD\n", "20270115\nextra\n", "20270115"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for status, contents, authorized in cases:
                with self.subTest(status=status, contents=contents, authorized=authorized):
                    (root / "BUILD").write_text(contents)
                    with patch.object(capture, "ROOT", root), patch.dict(os.environ, {"CIR_RELEASE_BUILD": authorized}):
                        with patch.object(capture.subprocess, "check_output", side_effect=["a" * 40 + "\n", status]):
                            with self.assertRaisesRegex(ValueError, "clean"):
                                capture.source_commit("a" * 40)

    def test_untracked_release_metadata_code_is_in_the_protected_source_set(self):
        with patch.object(capture.subprocess, "check_output", side_effect=["a" * 40 + "\n", "", "release_metadata.py\n"]) as command:
            with self.assertRaisesRegex(ValueError, "Untracked"):
                capture.source_commit("a" * 40)
            self.assertIn("release_metadata.py", command.call_args.args[0])
            self.assertIn("application_identity.py", command.call_args.args[0])
            self.assertIn("requirements-docs.txt", command.call_args.args[0])

    def test_real_documentation_cover_captures_are_required_for_both_viewports(self):
        for name in ('documentation-user-desktop', 'documentation-user-mobile',
                     'documentation-admin-desktop', 'documentation-admin-mobile'):
            self.assertIn(name, capture.REQUIRED_CAPTURES)
            self.assertIn(name, evidence.REQUIRED_SCREENSHOTS)
        source = (ROOT / 'scripts/capture_ui_screenshots.py').read_text()
        self.assertIn("('user', '/aiuto', 'doc-title')", source)
        self.assertIn("('admin', '/aiuto/amministrazione', 'admin-doc-title')", source)
        self.assertIn("check_documentation_cover(guide_page, title_id)", source)
        self.assertIn("documentation_mobile_first_fold_has_no_horizontal_overflow", source)


class ScreenshotWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load((ROOT / ".github/workflows/ci-release.yml").read_text())

    def test_release_requires_successful_ui_documentation_job(self):
        jobs = self.workflow["jobs"]
        self.assertIn("ui-documentation", jobs["docker-release"]["needs"])
        self.assertEqual(jobs["ui-documentation"]["if"], "needs.ci-mode.outputs.security_only != 'true'")
        self.assertIn('ci-mode', jobs['ui-documentation']['needs'])
        self.assertEqual(jobs["ui-documentation"]["permissions"], {"contents": "read"})
        for step in jobs["ui-documentation"]["steps"]:
            self.assertFalse(step.get("continue-on-error", False))

    def test_capture_precedes_manual_generation_and_packaging(self):
        steps = self.workflow["jobs"]["ui-documentation"]["steps"]
        commands = [step.get("run", "") for step in steps]
        capture_index = next(i for i, command in enumerate(commands) if "scripts/capture_ui_screenshots.py" in command)
        manuals_index = next(i for i, command in enumerate(commands) if "scripts/build_documentation_pdfs.py" in command)
        package_index = next(i for i, command in enumerate(commands) if "scripts/package_release.sh" in command)
        self.assertLess(capture_index, manuals_index)
        self.assertLess(manuals_index, package_index)
        self.assertIn('--source-commit "${GITHUB_SHA}"', commands[capture_index])
        self.assertIn("--require-real-screenshots", commands[manuals_index])
        self.assertIn("--screenshot-manifest", commands[manuals_index])
        self.assertIn("--include-brochures", commands[manuals_index])

    def test_editable_presentation_and_bundle_validation_precede_installation(self):
        steps = self.workflow['jobs']['ui-documentation']['steps']
        commands = [step.get('run', '') for step in steps]
        manual = next(i for i, command in enumerate(commands) if 'scripts/build_documentation_pdfs.py' in command)
        pptx = next(i for i, command in enumerate(commands) if 'scripts/build_training_presentation.py' in command)
        seal = next(i for i, command in enumerate(commands) if 'scripts/finalize_documentation_bundle.py' in command)
        install = next(i for i, command in enumerate(commands) if 'scripts/install_ui_documentation.py' in command)
        self.assertLess(manual, pptx)
        self.assertLess(pptx, seal)
        self.assertLess(seal, install)
        self.assertIn('--require-real-screenshots', commands[pptx])
        for i in (manual, pptx, seal, install):
            self.assertIn('"${GITHUB_SHA}"', commands[i])
            self.assertIn('${RUNNER_TEMP}/cir-ui-evidence', commands[i])
        self.assertNotIn('artifact_tool', '\n'.join(commands))
        self.assertIn('poppler-utils', '\n'.join(commands))

    def test_public_presentation_tooling_is_installed_and_audited_only_as_tooling(self):
        self.assertIn('-r requirements-docs.txt', (ROOT / 'requirements-dev.txt').read_text())
        self.assertIn('python-pptx==1.0.2', (ROOT / 'requirements-docs.txt').read_text())
        self.assertNotIn('python-pptx', (ROOT / 'requirements.txt').read_text())
        for job in ('quality-gates', 'ui-documentation'):
            commands = '\n'.join(step.get('run', '') for step in self.workflow['jobs'][job]['steps'])
            self.assertIn('requirements-docs.txt --strict', commands)
            self.assertIn('poppler-utils', commands)

    def test_release_downloads_verified_same_run_artifact_before_build(self):
        steps = self.workflow["jobs"]["docker-release"]["steps"]
        download_index = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("actions/download-artifact@"))
        download = steps[download_index]
        self.assertEqual(download["with"]["name"], "ui-documentation-${{ github.sha }}")
        self.assertEqual(download["with"]["digest-mismatch"], "error")
        self.assertNotIn("run-id", download["with"])
        install_index = next(i for i, step in enumerate(steps) if "scripts/install_ui_documentation.py" in step.get("run", ""))
        build_index = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("docker/build-push-action@"))
        self.assertLess(download_index, install_index)
        self.assertLess(install_index, build_index)

    def test_playwright_matches_pinned_browser_install(self):
        requirements = (ROOT / "requirements-ui.txt").read_text().splitlines()
        self.assertIn("playwright==" + capture.PLAYWRIGHT_VERSION, requirements)
        commands = "\n".join(step.get("run", "") for step in self.workflow["jobs"]["ui-documentation"]["steps"])
        self.assertIn("python -m playwright install --with-deps chromium", commands)
        self.assertNotIn("--no-sandbox", commands)


if __name__ == "__main__":
    unittest.main()


def test_spam_training_fixture_enables_conditional_personal_data_steps():
    """A 13-step screenshot requires the two conditional steps to be applicable."""
    import ast
    import json
    source = (ROOT / "scripts" / "seed_ui_documentation.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    incident_calls = [node for node in ast.walk(tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                      and node.func.id == "Incident" and any(
                          kw.arg == "reference" and isinstance(kw.value, ast.Constant)
                          and kw.value.value == "DEMO-SPAM-2026-0001"
                          for kw in node.keywords)]
    assert len(incident_calls) == 1
    assert any(kw.arg == "personal_data" and isinstance(kw.value, ast.Constant)
               and kw.value.value is True for kw in incident_calls[0].keywords)
    fixture = json.loads((ROOT / "tests" / "fixtures" / "spam_training_workflow.json").read_text())
    assert len(fixture["steps"]) == 13
    assert sum("personal_data" in step["conditions"] for step in fixture["steps"]) == 2
    assert 'to_have_count(13)' in (ROOT / "scripts" / "capture_ui_screenshots.py").read_text()
