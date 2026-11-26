"""Actual metadata/date/staging behavior independent of Flask and pytest."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from zoneinfo import ZoneInfoNotFoundError

from release_metadata import read_release_metadata, resolve_build, validate_build, write_build

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/prepare_release_metadata.py"


class AutomaticBuildMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "VERSION").write_text("0.10.0-1\n", encoding="utf-8")
        (self.root / "BUILD").write_text("20260902\n", encoding="utf-8")
        self.env = dict(os.environ)
        for key in ("CIR_RELEASE_BUILD", "SOURCE_DATE_EPOCH"):
            self.env.pop(key, None)

    def cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              env=self.env if env is None else env, text=True, capture_output=True)

    def source_fixture(self):
        """Isolated source without installed browser evidence for packaging tests.

        The suite also runs from cumulative archives with real CI evidence. Do
        not relabel that evidence or modify any file in the user's checkout.
        """
        source = self.root / "source"
        r = subprocess.run([sys.executable, str(ROOT / "scripts/copy_release_tree.py"), str(ROOT), str(source)],
                           env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for relative in ("docs/UI_SCREENSHOTS_SOURCE.json", "docs/UI_SCREENSHOTS_BUILD.json"):
            (source / relative).unlink(missing_ok=True)
        screenshots = source / "app/static/help/ui-runtime"
        if screenshots.exists():
            shutil.rmtree(screenshots)
        return source

    def test_rome_date_uses_next_day_after_utc_2300_in_winter(self):
        result = resolve_build(now=datetime(2026, 11, 22, 23, 30, tzinfo=timezone.utc))
        self.assertEqual(result, "20261123")

    def test_summer_dst_boundary_is_not_a_fixed_one_hour_offset(self):
        result = resolve_build(now=datetime(2026, 7, 10, 22, 30, tzinfo=timezone.utc))
        self.assertEqual(result, "20260711")

    def test_source_date_epoch_is_reproducible(self):
        instant = datetime(2026, 11, 22, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(resolve_build(source_date_epoch=str(int(instant.timestamp()))), "20261123")

    def test_explicit_build_wins_at_midnight_and_ignores_a_different_epoch(self):
        self.assertEqual(resolve_build("20261122", "0", datetime(2030, 1, 1, tzinfo=timezone.utc)), "20261122")

    def test_invalid_calendar_and_output_injection_rejected(self):
        for value in ("20260230", "20261301", "2026112", "20261122\nversion=9.9.9", "0", "latest"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_build(value)

    def test_invalid_epochs_and_naive_time_rejected(self):
        for value in ("-1", "1.5", "yesterday", "9" * 80, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_build(source_date_epoch=value)
        with self.assertRaises(ValueError):
            resolve_build(now=datetime(2026, 11, 22))

    def test_missing_timezone_fails_instead_of_silently_changing_date(self):
        with patch("release_metadata.ZoneInfo", side_effect=ZoneInfoNotFoundError("Europe/Rome")):
            with self.assertRaises(ZoneInfoNotFoundError):
                resolve_build(now=datetime(2026, 11, 22, tzinfo=timezone.utc))
            self.assertEqual(resolve_build("20261122"), "20261122")

    def test_metadata_job_outputs_without_modifying_source(self):
        output = self.root / "github-output"
        before = (self.root / "BUILD").read_bytes()
        r = self.cli("--build", "20261122", "--github-output", str(output))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"version": "0.10.0-1", "build": "20261122"})
        self.assertEqual(output.read_text(), "version=0.10.0-1\nbuild=20261122\n")
        self.assertEqual((self.root / "BUILD").read_bytes(), before)

    def test_downstream_jobs_reuse_exact_resolved_build_even_if_epoch_changes(self):
        for epoch in ("0", "946684800", "2000000000"):
            r = self.cli("--write", env={**self.env, "CIR_RELEASE_BUILD": "20261122", "SOURCE_DATE_EPOCH": epoch})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(read_release_metadata(self.root).build, "20261122")

    def test_cli_reproducible_epoch_stamps_build_and_leaves_version(self):
        version_before = (self.root / "VERSION").read_bytes()
        r = self.cli("--write", env={**self.env, "SOURCE_DATE_EPOCH": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / "BUILD").read_text(), "19700101\n")
        self.assertEqual((self.root / "VERSION").read_bytes(), version_before)

    def test_invalid_build_or_checkout_version_never_changes_files_or_outputs(self):
        before = (self.root / "BUILD").read_bytes()
        output = self.root / "github-output"
        for args in (("--build", "20260230"), ("--build", "20261122", "--expected-version", "0.9.0-1")):
            with self.subTest(args=args):
                r = self.cli(*args, "--write", "--github-output", str(output))
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual((self.root / "BUILD").read_bytes(), before)
                self.assertFalse(output.exists())

    def test_atomic_writer_does_not_follow_a_build_symlink(self):
        victim = self.root / "other"
        victim.write_text("retain", encoding="utf-8")
        (self.root / "BUILD").unlink()
        (self.root / "BUILD").symlink_to(victim)
        with self.assertRaises(ValueError):
            write_build(self.root, "20261122")
        self.assertEqual(victim.read_text(), "retain")

    def test_atomic_writer_respects_existing_temporary_update(self):
        before = (self.root / "BUILD").read_bytes()
        temporary = self.root / ".BUILD.cir-tmp"
        temporary.write_text("other operation", encoding="utf-8")
        with self.assertRaises(ValueError):
            write_build(self.root, "20261122")
        self.assertEqual(temporary.read_text(), "other operation")
        self.assertEqual((self.root / "BUILD").read_bytes(), before)

    def test_atomic_writer_does_not_delete_a_racing_writers_temporary_file(self):
        temporary = self.root / ".BUILD.cir-tmp"
        before = (self.root / "BUILD").read_bytes()
        real_open = Path.open

        def open_after_competing_writer(path, mode="r", *args, **kwargs):
            if path == temporary and mode == "x":
                with real_open(temporary, "w", encoding="utf-8") as stream:
                    stream.write("other operation")
                raise FileExistsError(str(temporary))
            return real_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", open_after_competing_writer):
            with self.assertRaises(FileExistsError):
                write_build(self.root, "20261122")
        self.assertEqual(temporary.read_text(), "other operation")
        self.assertEqual((self.root / "BUILD").read_bytes(), before)

    def test_package_generates_build_only_in_staging(self):
        source = self.source_fixture()
        source_build = (source / "BUILD").read_bytes()
        package = self.root / "source.zip"
        result = subprocess.run(["bash", str(source / "scripts/package_release.sh"), str(package)],
                                cwd=source, env={**self.env, "CIR_RELEASE_BUILD": "20301224"},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(package) as archive:
            base = "cybersecurity-incident-registry-" + (ROOT / "VERSION").read_text().strip()
            self.assertEqual(archive.read(base + "/BUILD"), b"20301224\n")
            self.assertIn(base + "/release_metadata.py", archive.namelist())
            from scripts.presentation_evidence import PRESENTATION_ARTIFACTS
            for name in PRESENTATION_ARTIFACTS:
                if name == 'CIR_Operational_Training_IT.pptx':
                    self.assertNotIn(base + "/docs/presentation/" + name, archive.namelist())
                else:
                    self.assertIn(base + "/docs/presentation/" + name, archive.namelist())
        self.assertEqual((source / "BUILD").read_bytes(), source_build)

    def test_package_rejects_partial_installed_evidence_before_creating_archive(self):
        source = self.source_fixture()
        source_build = (source / "BUILD").read_bytes()
        (source / "docs/UI_SCREENSHOTS_BUILD.json").write_text("{}\n", encoding="utf-8")
        package = self.root / "invalid.zip"
        result = subprocess.run(["bash", str(source / "scripts/package_release.sh"), str(package)],
                                cwd=source, env={**self.env, "CIR_RELEASE_BUILD": "20301224"},
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Release metadata: FAIL", result.stderr)
        self.assertIn("manifest", result.stderr.lower())
        self.assertFalse(package.exists())
        self.assertEqual((source / "BUILD").read_bytes(), source_build)

    def test_ci_resolves_once_and_reuses_build_in_all_release_consumers(self):
        # YAML is parsed by the existing pipeline suite; this dataflow contract
        # covers the known cross-job midnight/image-evidence mismatch regression.
        text = (ROOT / ".github/workflows/ci-release.yml").read_text()
        self.assertEqual(text.count("--github-output \"$GITHUB_OUTPUT\""), 1)
        self.assertEqual(text.count('CIR_RELEASE_BUILD: ${{ needs.release-metadata.outputs.build }}'), 3)
        self.assertEqual(text.count('--expected-version "$CIR_RELEASE_VERSION" --write'), 3)
        self.assertIn('CIR_RELEASE_BUILD=${{ needs.release-metadata.outputs.build }}', text)
        self.assertIn('needs: [release-metadata, quality-gates, ui-documentation, release-scope]', text)
        self.assertIn('io.cir.build=${{ needs.release-metadata.outputs.build }}', text)

    def test_docker_and_manual_multiarch_share_automatic_stamp(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        script = (ROOT / "scripts/build_multiarch_image.sh").read_text()
        self.assertIn('tzdata', dockerfile)
        self.assertIn('ARG CIR_RELEASE_BUILD', dockerfile)
        self.assertIn('ARG SOURCE_DATE_EPOCH', dockerfile)
        self.assertIn('scripts/prepare_release_metadata.py --build "${CIR_RELEASE_BUILD}" --write', dockerfile)
        self.assertIn('--write --verify-installed-documentation', dockerfile)
        self.assertIn('--build-arg "CIR_RELEASE_BUILD=$CIR_RESOLVED_BUILD"', script)
        self.assertIn('scripts/prepare_release_metadata.py" --field build', script)


if __name__ == "__main__":
    unittest.main()
