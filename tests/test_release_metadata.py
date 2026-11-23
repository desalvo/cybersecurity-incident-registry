"""Runtime identity must come from the packaged files, not stale deployment env."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release_metadata import read_release_metadata, read_runtime_metadata

ROOT = Path(__file__).resolve().parents[1]


class RuntimeReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "VERSION").write_text("0.10.0-1\n", encoding="utf-8")
        (self.root / "BUILD").write_text("20261122\n", encoding="utf-8")

    def test_existing_metadata_ignores_legacy_version_and_build_overrides(self):
        metadata = read_runtime_metadata(self.root, {"APP_VERSION": "0.9.0-1", "APP_BUILD": "20260902"})
        self.assertEqual((metadata.version, metadata.build), ("0.10.0-1", "20261122"))

    def test_actual_application_version_module_uses_packaged_files(self):
        spec = spec_from_file_location("cir_version_metadata_test", ROOT / "app/version.py")
        module = module_from_spec(spec)
        with patch.dict(os.environ, {"APP_VERSION": "0.9.0-1", "APP_BUILD": "20260902"}):
            spec.loader.exec_module(module)
        expected = read_release_metadata(ROOT)
        self.assertEqual(module.APP_RELEASE_VERSION, expected.version)
        self.assertEqual(module.APP_RELEASE_BUILD, expected.build)

    def test_legacy_unpacked_environment_fallback_requires_missing_files(self):
        (self.root / "VERSION").unlink()
        (self.root / "BUILD").unlink()
        metadata = read_runtime_metadata(self.root, {"APP_VERSION": "1.2.3-test", "APP_BUILD": "20261230"})
        self.assertEqual((metadata.version, metadata.build), ("1.2.3-test", "20261230"))

    def test_absent_build_does_not_allow_version_override(self):
        (self.root / "BUILD").unlink()
        metadata = read_runtime_metadata(self.root, {"APP_VERSION": "0.9.0-1", "APP_BUILD": "20261230"})
        self.assertEqual((metadata.version, metadata.build), ("0.10.0-1", "20261230"))

    def test_present_empty_or_invalid_file_fails_without_environment_rescue(self):
        for value in ("", "20260230", "unknown"):
            with self.subTest(value=value):
                (self.root / "BUILD").write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_runtime_metadata(self.root, {"APP_BUILD": "20261122"})

    def test_no_metadata_has_development_fallback_only(self):
        (self.root / "VERSION").unlink()
        (self.root / "BUILD").unlink()
        metadata = read_runtime_metadata(self.root, {})
        self.assertEqual((metadata.version, metadata.build), ("0.0.0", "unknown"))

    def test_broken_metadata_symlink_does_not_allow_legacy_override(self):
        (self.root / "BUILD").unlink()
        (self.root / "BUILD").symlink_to(self.root / "missing-build")
        with self.assertRaisesRegex(ValueError, "broken symlink"):
            read_runtime_metadata(self.root, {"APP_BUILD": "20261122"})

    def test_restarting_runtime_does_not_consult_build_clock(self):
        with patch("release_metadata.resolve_build", side_effect=AssertionError("runtime clock used")):
            self.assertEqual(read_runtime_metadata(self.root), read_runtime_metadata(self.root))


if __name__ == "__main__":
    unittest.main()
