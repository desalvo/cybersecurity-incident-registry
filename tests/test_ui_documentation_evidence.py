"""Exercise artifact validation and installation without a browser or app.

The PNG/PDF bytes below are deliberately synthetic UNIT TEST PLACEHOLDERS,
created only in TemporaryDirectory. They are not application screenshots,
manuals, release evidence, or a substitute for the required browser CI job.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import zlib

from scripts import ui_documentation_evidence as evidence
from scripts.presentation_evidence import MANUAL_PREVIEWS, PRESENTATION_FILE, PRESENTATION_RECEIPT
from release_metadata import read_release_metadata

ROOT = Path(__file__).resolve().parents[1]
RELEASE = read_release_metadata(ROOT)
COMMIT = "0123456789abcdef0123456789abcdef01234567"
OTHER_COMMIT = "fedcba9876543210fedcba9876543210fedcba98"

# The installer is also an executable script; resolve its standard-library
# helper exactly as its CLI does, without importing the Flask application.
_spec = importlib.util.spec_from_file_location(
    "cir_ui_documentation_installer_test", ROOT / "scripts/install_ui_documentation.py"
)
installer = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"ui_documentation_evidence": evidence}):
    _spec.loader.exec_module(installer)


def placeholder_png(width=300, height=400):
    """A valid, uniformly gray PNG solely for testing headers/checksums."""
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    pixels = (b"\x00" + b"\xb0\xb0\xb0" * width) * height
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"tEXt", b"Comment\x00UNIT TEST ONLY - NOT AN APPLICATION SCREENSHOT")
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def placeholder_presentation(directory, screenshots, images):
    """Minimal ZIP/XML validation fixture; never a deliverable or browser proof."""
    ns = ('xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
          'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    rel_ns = 'http://schemas.openxmlformats.org/package/2006/relationships'
    rel_type = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
    embedded = []
    screenshot_rows = []
    for index, row in enumerate(screenshots, 1):
        media = f'ppt/media/screenshot{index}.png'
        embedded.append((media, (images / (row['id'] + '.png')).read_bytes()))
        screenshot_rows.append({'id': row['id'], 'sha256': row['sha256'], 'media_file': media})
    previews = []
    for index, (pdf, png) in enumerate(sorted(MANUAL_PREVIEWS.items()), 1):
        (directory / png).write_bytes(placeholder_png(595, 842))
        media = f'ppt/media/manual{index}.png'
        embedded.append((media, (directory / png).read_bytes()))
        previews.append({'pdf': pdf, 'pdf_sha256': evidence.sha256(directory / pdf),
                         'png': png, 'png_sha256': evidence.sha256(directory / png),
                         'media_file': media, 'page': 1})
    output = directory / PRESENTATION_FILE
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr('docProps/core.xml', '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"/>')
        slide_ids = ''.join(f'<p:sldId id="{255+i}" r:id="slide{i}"/>' for i in range(1, 6))
        archive.writestr('ppt/presentation.xml', f'<p:presentation {ns}><p:sldIdLst>{slide_ids}</p:sldIdLst></p:presentation>')
        archive.writestr('ppt/_rels/presentation.xml.rels', f'<Relationships xmlns="{rel_ns}">' +
                         ''.join(f'<Relationship Id="slide{i}" Type="{rel_type}slide" Target="slides/slide{i}.xml"/>' for i in range(1, 6)) + '</Relationships>')
        for media, data in embedded:
            archive.writestr(media, data)
        for number in range(1, 6):
            pictures = ''
            relations = f'<Relationship Id="notes" Type="{rel_type}notesSlide" Target="../notesSlides/notesSlide{number}.xml"/>'
            if number == 1:
                for index, (media, _) in enumerate(embedded):
                    rid = f'image{index}'
                    pictures += f'<p:pic><p:blipFill><a:blip r:embed="{rid}"/></p:blipFill></p:pic>'
                    relations += f'<Relationship Id="{rid}" Type="{rel_type}image" Target="../media/{Path(media).name}"/>'
            text = escape('UNIT TEST PLACEHOLDER: editable native body, never a training deliverable')
            footer = escape(RELEASE.version + ' · Build ' + RELEASE.build)
            shapes = f'<p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r><a:r><a:t>{footer}</a:t></a:r></a:p></p:txBody></p:sp>'
            archive.writestr(f'ppt/slides/slide{number}.xml', f'<p:sld {ns}><p:cSld><p:spTree>{shapes}{pictures}</p:spTree></p:cSld></p:sld>')
            archive.writestr(f'ppt/slides/_rels/slide{number}.xml.rels', f'<Relationships xmlns="{rel_ns}">{relations}</Relationships>')
            archive.writestr(f'ppt/notesSlides/notesSlide{number}.xml', f'<p:notes {ns}><a:t>UNIT TEST ONLY: native notes exercise validation, not real operational instruction.</a:t></p:notes>')
    return {'schema_version': 1, 'source_commit': COMMIT,
            'functional_version': RELEASE.version, 'build': RELEASE.build,
            'real_screenshots': True, 'editable_text': True, 'speaker_notes': True,
            'file': PRESENTATION_FILE, 'sha256': evidence.sha256(output), 'slides': 5,
            'screenshots': screenshot_rows, 'manual_first_pages': previews}


def tree_bytes(root):
    """Capture every destination file, allowing assertions of zero writes."""
    if not root.exists():
        return None
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


class EvidenceFixtureTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cir-unit-test-evidence-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.artifact = self.root / "artifact"
        self.images = self.artifact / "screenshots"
        self.images.mkdir(parents=True)
        self.documentation = self.artifact / "documentation"
        self.documentation.mkdir()
        self.manifest_path = self.artifact / "manifest.json"
        rows = []
        image_bytes = placeholder_png()
        for sid in sorted(evidence.REQUIRED_SCREENSHOTS):
            relative = "screenshots/" + sid + ".png"
            (self.artifact / relative).write_bytes(image_bytes)
            rows.append({
                "id": sid, "file": relative,
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
                "viewport": {"width": 300, "height": 400},
                "ui_mode": "classic" if sid.startswith("classic-") else "modern",
                "authenticated": not sid.startswith("login-"),
                "route": evidence.DOCUMENTATION_CAPTURE_ROUTES.get(sid, "/login" if sid.startswith("login-") else "/"),
                "capture_area": "viewport",
                "caption_it": "Segnaposto di test, non una schermata del browser.",
                "caption_en": "Unit-test placeholder, not a browser screenshot.",
            })
        self.manifest = {
            "schema_version": 1, "source_kind": "real-application-browser",
            "source_commit": COMMIT, "functional_version": RELEASE.version,
            "build": RELEASE.build, "data_provenance": "isolated-synthetic-fixture",
            "browser": {"name": "chromium", "version": "unit-test", "playwright": "unit-test"},
            "fixture_purpose": "UNIT TEST ONLY - NOT REAL BROWSER EVIDENCE",
            "checks": {"unit_test_fixture_contract": True,
                       **{name: True for name in evidence.DOCUMENTATION_CAPTURE_CHECKS}}, "screenshots": rows,
        }
        self.save_manifest()
        files = []
        for name in sorted(evidence.REQUIRED_MANUALS):
            path = self.documentation / name
            path.write_bytes(b"%PDF-1.4\n% UNIT TEST PLACEHOLDER - NOT A MANUAL\n%%EOF\n")
            files.append({"file": name, "sha256": evidence.sha256(path)})
        self.presentation_receipt = placeholder_presentation(self.documentation, rows, self.images)
        self.presentation_receipt['screenshot_manifest_sha256'] = evidence.sha256(self.manifest_path)
        write_json(self.documentation / PRESENTATION_RECEIPT, self.presentation_receipt)
        for name in sorted([PRESENTATION_FILE, PRESENTATION_RECEIPT, *MANUAL_PREVIEWS.values()]):
            files.append({'file': name, 'sha256': evidence.sha256(self.documentation / name)})
        self.receipt = {
            "schema_version": 2, "source_commit": COMMIT, "real_screenshots": True,
            "functional_version": RELEASE.version, "build": RELEASE.build,
            "screenshot_manifest_sha256": evidence.sha256(self.manifest_path),
            "fixture_purpose": "UNIT TEST ONLY - NOT A DOCUMENTATION BUILD",
            "presentation_receipt_file": PRESENTATION_RECEIPT,
            "files": files,
        }
        self.save_receipt()
        self.destination = self.root / "candidate"
        self.destination.mkdir()
        (self.destination / "VERSION").write_text(RELEASE.version + "\n")
        (self.destination / "BUILD").write_text(RELEASE.build + "\n")
        self.initial_destination = tree_bytes(self.destination)

    def save_manifest(self):
        write_json(self.manifest_path, self.manifest)

    def save_receipt(self):
        write_json(self.documentation / "build-manifest.json", self.receipt)

    def load(self):
        return evidence.load_evidence(self.manifest_path, COMMIT)

    def manuals(self):
        return evidence.validate_manuals(self.documentation, COMMIT, evidence.sha256(self.manifest_path),
                                         screenshot_evidence=self.load())

    def install(self):
        with redirect_stdout(io.StringIO()):
            installer.install(self.manifest_path, self.documentation, COMMIT, root=self.destination)


class ScreenshotArtifactValidationTests(EvidenceFixtureTestCase):
    def test_old_release_and_different_build_are_rejected(self):
        for key, value in (("functional_version", "0.9.0-1"), ("build", "20000101")):
            with self.subTest(key=key):
                original = self.manifest[key]
                self.manifest[key] = value
                self.save_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, "release metadata"):
                    self.load()
                self.manifest[key] = original

    def test_complete_batch_resolves_all_required_distinct_artifacts(self):
        loaded = self.load()
        self.assertEqual(len(loaded["_paths"]), len(evidence.REQUIRED_SCREENSHOTS))
        self.assertEqual(set(loaded["_paths"]), evidence.REQUIRED_SCREENSHOTS)
        self.assertEqual(len(set(loaded["_paths"].values())), len(evidence.REQUIRED_SCREENSHOTS))
        for sid, path in loaded["_paths"].items():
            self.assertEqual(path, self.images / (sid + ".png"))

    def test_jpeg_browser_artifact_uses_image_header_dimensions_and_sha256(self):
        """Test one JPEG alongside legacy PNGs; the historic archive still loads."""
        from PIL import Image
        row = self.manifest["screenshots"][0]
        old = self.artifact / row['file']
        name = row['id'] + '.jpg'
        new = self.images / name
        Image.new('RGB', (300, 400), (35, 91, 142)).save(new, format='JPEG', quality=90)
        old.unlink()
        row.update({'file': 'screenshots/' + name, 'image_format': 'jpeg', 'jpeg_quality': 90,
                    'sha256': evidence.sha256(new)})
        self.save_manifest()
        loaded = self.load()
        self.assertEqual(loaded['_paths'][row['id']], new)
        # An attacker cannot assert that arbitrary content was a JPEG, even
        # after regenerating the manifest hash.
        new.write_bytes(b'not really a jpeg')
        row['sha256'] = evidence.sha256(new)
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, 'JPEG'):
            self.load()

    def test_jpeg_cannot_fake_a_png_extension_or_viewport(self):
        from PIL import Image
        row = self.manifest['screenshots'][0]
        new = self.images / (row['id'] + '.jpg')
        Image.new('RGB', (300, 400), (90, 115, 140)).save(new, format='JPEG', quality=90)
        row.update({'file': 'screenshots/' + new.name, 'image_format': 'png',
                    'sha256': evidence.sha256(new)})
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, 'format/extension mismatch'):
            self.load()
        row['image_format'] = 'jpeg'
        row['viewport'] = {'width': 301, 'height': 400}
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, 'dimensions'):
            self.load()

    def test_real_element_capture_uses_its_own_bounded_dimensions(self):
        # The actual browser captures the narrower category/data-type palette,
        # not a 1920-pixel page screenshot. That geometry must be acceptable.
        from PIL import Image
        row = next(item for item in self.manifest['screenshots']
                   if item['id'] == 'spam-incident-config-labels')
        target = self.artifact / row['file']
        Image.new('RGB', (260, 530), (90, 115, 140)).save(target, format='PNG')
        row['sha256'] = evidence.sha256(target)
        row['viewport'] = {'width': 1920, 'height': 1140}
        row['capture_area'] = 'element'
        row['element_selector'] = '#incident-main .dnd-layout'
        row['element_size'] = {'width': 260, 'height': 530}
        self.save_manifest()
        self.assertIn(row['id'], self.load()['_paths'])

        for key, invalid in (
            ('element_size', None),
            ('element_size', {'width': 261, 'height': 530}),
            ('element_size', {'width': True, 'height': 530}),
            ('element_selector', '#incident-workflow'),
        ):
            with self.subTest(key=key, invalid=invalid):
                original = row[key]
                row[key] = invalid
                self.save_manifest()
                with self.assertRaises(evidence.EvidenceError):
                    self.load()
                row[key] = original

        # An element larger than the viewport is not a valid cropped palette.
        Image.new('RGB', (2000, 530), (90, 115, 140)).save(target, format='PNG')
        row['element_size'] = {'width': 2000, 'height': 530}
        row['sha256'] = evidence.sha256(target)
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, 'Element screenshot dimensions'):
            self.load()

    def test_element_capture_cannot_use_unapproved_id(self):
        row = next(item for item in self.manifest['screenshots']
                   if item['id'] == 'spam-incident-config-labels')
        row['capture_area'] = 'element'
        row['element_selector'] = '#incident-main .dnd-layout'
        row['element_size'] = {'width': 300, 'height': 400}
        self.save_manifest()
        self.assertIn(row['id'], self.load()['_paths'])
        row['id'] = 'unapproved-crop'
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, 'Unapproved screenshot element selector'):
            self.load()

    def test_jpeg_element_capture_accepts_real_dimensions_without_viewport_width(self):
        from PIL import Image
        row = next(item for item in self.manifest['screenshots']
                   if item['id'] == 'spam-incident-config-labels')
        target = self.artifact / 'screenshots' / (row['id'] + '.jpg')
        Image.new('RGB', (650, 720), (19, 63, 92)).save(target, 'JPEG', quality=90)
        row.update({'file': 'screenshots/' + target.name, 'image_format': 'jpeg',
                    'jpeg_quality': 90, 'sha256': evidence.sha256(target),
                    'capture_area': 'element', 'viewport': {'width': 1920, 'height': 1140},
                    'element_selector': '#incident-main .dnd-layout',
                    'element_size': {'width': 650, 'height': 720}})
        self.save_manifest()
        self.assertIn(row['id'], self.load()['_paths'])

    def test_viewport_capture_must_still_use_exact_viewport_height(self):
        from PIL import Image
        row = self.manifest['screenshots'][0]
        target = self.artifact / row['file']
        Image.new('RGB', (300, 600), (90, 115, 140)).save(target, format='PNG')
        row['sha256'] = evidence.sha256(target)
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, 'dimensions do not match viewport'):
            self.load()
        row['capture_area'] = 'full-page'
        self.save_manifest()
        # Full-page still permits a real scrollable capture of the document.
        if row['id'] not in evidence.DOCUMENTATION_CAPTURE_ROUTES:
            self.assertIn(row['id'], self.load()['_paths'])

    def test_other_commit_is_rejected(self):
        with self.assertRaisesRegex(evidence.EvidenceError, "commit differs"):
            evidence.load_evidence(self.manifest_path, OTHER_COMMIT)

    def test_hash_tampering_is_rejected(self):
        path = self.artifact / self.manifest["screenshots"][-1]["file"]
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(evidence.EvidenceError, "checksum"):
            self.load()

    def test_missing_required_capture_is_rejected(self):
        self.manifest["screenshots"].pop()
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "Missing required"):
            self.load()

    def test_duplicate_capture_id_is_rejected(self):
        self.manifest["screenshots"].append(copy.deepcopy(self.manifest["screenshots"][0]))
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate screenshot ID"):
            self.load()

    def test_distinct_ids_cannot_reuse_the_same_artifact_path(self):
        self.manifest["screenshots"][1]["file"] = self.manifest["screenshots"][0]["file"]
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "own file"):
            self.load()

    def test_missing_capture_file_is_rejected(self):
        (self.artifact / self.manifest["screenshots"][0]["file"]).unlink()
        with self.assertRaisesRegex(evidence.EvidenceError, "missing"):
            self.load()

    def test_traversal_absolute_windows_and_protocol_paths_are_rejected(self):
        for invalid in ("../outside.png", "/tmp/outside.png", "screenshots/../../outside.png",
                        "C:/outside.png", "screenshots\\outside.png", "https://example.invalid/a.png"):
            with self.subTest(path=invalid):
                self.manifest["screenshots"][0]["file"] = invalid
                self.save_manifest()
                with self.assertRaises(evidence.EvidenceError):
                    self.load()

    def test_symlink_image_is_rejected_even_with_matching_contents(self):
        path = self.artifact / self.manifest["screenshots"][0]["file"]
        outside = self.root / "outside.png"
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaisesRegex(evidence.EvidenceError, "Symlink"):
            self.load()

    def test_symlink_image_directory_is_rejected(self):
        outside = self.root / "outside-images"
        self.images.rename(outside)
        self.images.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(evidence.EvidenceError, "Symlink"):
            self.load()

    def test_incorrect_ui_mode_is_rejected(self):
        for sid, invalid_mode in (("incident-mobile", "classic"), ("classic-registry-desktop", "modern")):
            with self.subTest(sid=sid):
                row = next(row for row in self.manifest["screenshots"] if row["id"] == sid)
                original = row["ui_mode"]
                row["ui_mode"] = invalid_mode
                self.save_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, "Wrong UI mode"):
                    self.load()
                row["ui_mode"] = original

    def test_failed_empty_and_truthy_nonboolean_checks_are_rejected(self):
        for invalid in ({}, {"passed": False}, {"passed": "true"}, {"passed": 1}, None):
            with self.subTest(checks=invalid):
                self.manifest["checks"] = invalid
                self.save_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, "checks"):
                    self.load()

    def test_online_cover_checks_cannot_be_omitted_from_a_passing_manifest(self):
        for name in evidence.DOCUMENTATION_CAPTURE_CHECKS:
            with self.subTest(check=name):
                del self.manifest['checks'][name]
                self.save_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, 'documentation checks'):
                    self.load()
                self.manifest['checks'][name] = True

    def test_online_manual_openings_require_the_actual_route_and_viewport_capture(self):
        for sid in evidence.DOCUMENTATION_CAPTURE_ROUTES:
            row = next(item for item in self.manifest['screenshots'] if item['id'] == sid)
            for key, invalid in (('route', '/login'), ('capture_area', 'full-page'), ('capture_area', None)):
                with self.subTest(id=sid, key=key, invalid=invalid):
                    original = row[key]
                    row[key] = invalid
                    self.save_manifest()
                    with self.assertRaisesRegex(evidence.EvidenceError, 'first viewport'):
                        self.load()
                    row[key] = original

    def test_tall_png_cannot_claim_a_normal_online_manual_viewport(self):
        row = next(item for item in self.manifest['screenshots'] if item['id'] == 'documentation-user-mobile')
        path = self.artifact / row['file']
        path.write_bytes(placeholder_png(width=300, height=1600))
        row['sha256'] = evidence.sha256(path)
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, 'first viewport'):
            self.load()

    def test_provenance_must_identify_real_app_and_isolated_synthetic_data(self):
        for key, invalid in (("source_kind", "mock-html"), ("data_provenance", "production-backup")):
            with self.subTest(key=key):
                original = self.manifest[key]
                self.manifest[key] = invalid
                self.save_manifest()
                with self.assertRaises(evidence.EvidenceError):
                    self.load()
                self.manifest[key] = original

    def test_authentication_state_cannot_be_swapped(self):
        row = next(row for row in self.manifest["screenshots"] if row["id"] == "login-desktop")
        row["authenticated"] = True
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "authentication state"):
            self.load()

    def test_png_dimensions_must_match_the_reported_viewport(self):
        self.manifest["screenshots"][0]["viewport"]["width"] = 301
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "dimensions"):
            self.load()

    def test_invalid_png_is_rejected_even_if_checksum_matches(self):
        row = self.manifest["screenshots"][0]
        path = self.artifact / row["file"]
        path.write_bytes(b"this is not a PNG")
        row["sha256"] = evidence.sha256(path)
        self.save_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "PNG header"):
            self.load()

    def test_remote_or_protocol_relative_page_route_is_rejected(self):
        for route in ("https://example.invalid/login", "//example.invalid/login"):
            with self.subTest(route=route):
                self.manifest["screenshots"][0]["route"] = route
                self.save_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, "route must be local"):
                    self.load()


class ManualReceiptValidationTests(EvidenceFixtureTestCase):
    def test_manual_receipt_requires_current_release_and_same_build(self):
        for key, value in (("functional_version", "0.9.0-1"), ("build", "20000101")):
            with self.subTest(key=key):
                original = self.receipt[key]
                self.receipt[key] = value
                self.save_receipt()
                with self.assertRaisesRegex(evidence.EvidenceError, "release metadata"):
                    self.manuals()
                self.receipt[key] = original

    def test_complete_pdf_batch_matches_original_artifact_manifest(self):
        receipt = self.manuals()
        self.assertEqual(set(receipt["_paths"]), set(evidence.REQUIRED_MANUALS) |
                         {PRESENTATION_FILE, PRESENTATION_RECEIPT, *MANUAL_PREVIEWS.values()})
        self.assertEqual(receipt["screenshot_manifest_sha256"], evidence.sha256(self.manifest_path))

    def test_manuals_for_other_commit_are_rejected(self):
        self.receipt["source_commit"] = OTHER_COMMIT
        self.save_receipt()
        with self.assertRaisesRegex(evidence.EvidenceError, "different source commit"):
            self.manuals()

    def test_manuals_built_from_different_manifest_are_rejected(self):
        self.receipt["screenshot_manifest_sha256"] = "f" * 64
        self.save_receipt()
        with self.assertRaisesRegex(evidence.EvidenceError, "not built from these screenshots"):
            self.manuals()

    def test_non_real_screenshot_receipt_is_rejected(self):
        self.receipt["real_screenshots"] = False
        self.save_receipt()
        with self.assertRaisesRegex(evidence.EvidenceError, "real screenshot evidence"):
            self.manuals()

    def test_missing_required_manual_is_rejected(self):
        self.receipt["files"].pop()
        self.save_receipt()
        with self.assertRaisesRegex(evidence.EvidenceError, "Required current manuals"):
            self.manuals()

    def test_pdf_bytes_cannot_change_after_receipt_generation(self):
        path = self.documentation / self.receipt["files"][-1]["file"]
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(evidence.EvidenceError, "checksum mismatch"):
            self.manuals()

    def test_non_pdf_is_rejected_even_with_matching_hash(self):
        row = self.receipt["files"][0]
        path = self.documentation / row["file"]
        path.write_bytes(b"<html>not a PDF</html>")
        row["sha256"] = evidence.sha256(path)
        self.save_receipt()
        with self.assertRaisesRegex(evidence.EvidenceError, "format or checksum"):
            self.manuals()

    def test_pdf_symlink_is_rejected(self):
        path = self.documentation / self.receipt["files"][0]["file"]
        outside = self.root / "outside.pdf"
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaisesRegex(evidence.EvidenceError, "Symlink"):
            self.manuals()

    def test_manual_filenames_cannot_traverse_or_collide_when_flattened(self):
        original = copy.deepcopy(self.receipt["files"])
        for name in ("../outside.pdf", "nested/documentazione_utente.pdf", "/tmp/outside.pdf"):
            with self.subTest(filename=name):
                self.receipt["files"] = copy.deepcopy(original)
                self.receipt["files"].append({"file": name, "sha256": "a" * 64})
                self.save_receipt()
                with self.assertRaisesRegex(evidence.EvidenceError, "basenames"):
                    self.manuals()

    def test_duplicate_manual_receipt_entry_is_rejected(self):
        self.receipt["files"].append(copy.deepcopy(self.receipt["files"][0]))
        self.save_receipt()
        with self.assertRaisesRegex(evidence.EvidenceError, "Duplicate manual"):
            self.manuals()


class PresentationBundleValidationTests(EvidenceFixtureTestCase):
    def refresh_receipt_hashes(self):
        self.presentation_receipt['sha256'] = evidence.sha256(self.documentation / PRESENTATION_FILE)
        write_json(self.documentation / PRESENTATION_RECEIPT, self.presentation_receipt)
        for row in self.receipt['files']:
            row['sha256'] = evidence.sha256(self.documentation / row['file'])
        self.save_receipt()

    def rewrite_deck(self, transform):
        output = io.BytesIO()
        with ZipFile(self.documentation / PRESENTATION_FILE) as original, ZipFile(output, 'w', ZIP_DEFLATED) as changed:
            for name in original.namelist():
                value = transform(name, original.read(name))
                if value is not None:
                    changed.writestr(name, value)
        (self.documentation / PRESENTATION_FILE).write_bytes(output.getvalue())
        self.refresh_receipt_hashes()

    def use_pdf_phase_receipt(self):
        self.receipt['schema_version'] = 1
        self.receipt.pop('presentation_receipt_file', None)
        self.receipt['files'] = [row for row in self.receipt['files'] if row['file'] in evidence.REQUIRED_MANUALS]
        self.save_receipt()

    def test_pdf_phase_cannot_be_installed_as_a_complete_release(self):
        self.use_pdf_phase_receipt()
        self.assertEqual(len(evidence.validate_manuals(self.documentation, COMMIT, evidence.sha256(self.manifest_path),
                                                       require_presentation=False)['_paths']), 9)
        with self.assertRaisesRegex(evidence.EvidenceError, 'complete required batch'):
            self.install()
        self.assertEqual(tree_bytes(self.destination), self.initial_destination)

    def test_presentation_commit_version_and_build_are_checked_independently(self):
        for field, value in (('source_commit', OTHER_COMMIT), ('functional_version', '0.9.0-1'), ('build', '20000101')):
            with self.subTest(field=field):
                original = self.presentation_receipt[field]
                self.presentation_receipt[field] = value
                self.refresh_receipt_hashes()
                with self.assertRaises(evidence.EvidenceError):
                    self.manuals()
                self.presentation_receipt[field] = original

    def test_source_only_or_noneditable_deck_cannot_enter_real_ci_batch(self):
        for field in ('real_screenshots', 'editable_text', 'speaker_notes'):
            with self.subTest(field=field):
                self.presentation_receipt[field] = False
                self.refresh_receipt_hashes()
                with self.assertRaisesRegex(evidence.EvidenceError, 'real screenshots, editable text'):
                    self.manuals()
                self.presentation_receipt[field] = True

    def test_presentation_requires_every_verified_desktop_and_mobile_view(self):
        self.presentation_receipt['screenshots'].pop()
        self.refresh_receipt_hashes()
        with self.assertRaisesRegex(evidence.EvidenceError, 'every required real UI view'):
            self.manuals()

    def test_presentation_cannot_reuse_one_capture_id_for_multiple_required_views(self):
        self.presentation_receipt['screenshots'][-1] = dict(self.presentation_receipt['screenshots'][0])
        self.refresh_receipt_hashes()
        with self.assertRaisesRegex(evidence.EvidenceError, 'IDs are missing, duplicated'):
            self.manuals()

    def test_pptx_media_bytes_must_match_verified_capture_even_after_outer_hash_updated(self):
        target = self.presentation_receipt['screenshots'][0]['media_file']
        self.rewrite_deck(lambda name, data: data + b'changed' if name == target else data)
        with self.assertRaisesRegex(evidence.EvidenceError, 'embedded media checksum'):
            self.manuals()

    def test_stale_native_footer_is_rejected_even_with_current_receipt_and_hashes(self):
        self.rewrite_deck(lambda name, data: data.replace(RELEASE.build.encode(), b'20000101')
                          if name == 'ppt/slides/slide1.xml' else data)
        with self.assertRaisesRegex(evidence.EvidenceError, 'current version/build footer'):
            self.manuals()

    def test_deck_requires_native_speaker_notes_for_every_slide(self):
        self.rewrite_deck(lambda name, data: None if name == 'ppt/notesSlides/notesSlide1.xml' else data)
        with self.assertRaisesRegex(evidence.EvidenceError, 'speaker-note count'):
            self.manuals()

    def test_presentation_manual_preview_is_bound_to_actual_generated_pdf(self):
        pdf = self.presentation_receipt['manual_first_pages'][0]['pdf']
        (self.documentation / pdf).write_bytes(b'%PDF-1.4\n% changed manual after preview generation\n%%EOF\n')
        self.refresh_receipt_hashes()
        with self.assertRaisesRegex(evidence.EvidenceError, 'manual/preview checksum'):
            self.manuals()

    def test_presentation_cannot_claim_a_different_manual_page_is_the_cover(self):
        self.presentation_receipt['manual_first_pages'][0]['page'] = 2
        self.refresh_receipt_hashes()
        with self.assertRaisesRegex(evidence.EvidenceError, 'actual first page'):
            self.manuals()

    def test_finalizer_produces_complete_receipt_after_validating_every_artifact(self):
        from scripts.finalize_documentation_bundle import finalize
        self.use_pdf_phase_receipt()
        result = finalize(self.manifest_path, self.documentation, COMMIT, metadata_root=self.destination)
        self.assertEqual(result['schema_version'], 2)
        self.assertEqual(len(result['files']), 16)
        self.assertEqual(len(self.manuals()['_paths']), 16)

    def test_failed_finalization_preserves_pdf_receipt_and_removes_temporary_output(self):
        from scripts.finalize_documentation_bundle import finalize
        self.presentation_receipt['build'] = '20000101'
        self.refresh_receipt_hashes()
        self.use_pdf_phase_receipt()
        before = (self.documentation / 'build-manifest.json').read_bytes()
        with self.assertRaisesRegex(evidence.EvidenceError, 'Presentation release metadata'):
            finalize(self.manifest_path, self.documentation, COMMIT, metadata_root=self.destination)
        self.assertEqual((self.documentation / 'build-manifest.json').read_bytes(), before)
        self.assertEqual(list(self.documentation.glob('.cir-documentation-*')), [])

    def test_late_invalid_presentation_prevents_all_destination_writes(self):
        self.presentation_receipt['build'] = '20000101'
        self.refresh_receipt_hashes()
        with self.assertRaises(evidence.EvidenceError):
            self.install()
        self.assertEqual(tree_bytes(self.destination), self.initial_destination)


class InstallationValidationTests(EvidenceFixtureTestCase):
    def test_same_commit_artifact_from_another_candidate_build_is_rejected_without_writes(self):
        (self.destination / "BUILD").write_text("20000101\n")
        before = tree_bytes(self.destination)
        with self.assertRaisesRegex(evidence.EvidenceError, "release metadata"):
            self.install()
        self.assertEqual(tree_bytes(self.destination), before)

    def test_valid_batch_installs_all_images_manuals_and_traceable_receipt(self):
        self.install()
        static = self.destination / "app/static/help/ui-runtime"
        installed_manifest_path = static / "manifest.json"
        loaded = evidence.load_evidence(installed_manifest_path, COMMIT)
        self.assertEqual(set(loaded["_paths"]), evidence.REQUIRED_SCREENSHOTS)
        for row in loaded["screenshots"]:
            self.assertEqual(row["file"], row["id"] + ".png")
            self.assertEqual(evidence.sha256(static / row["file"]), row["sha256"])
        for name in evidence.REQUIRED_MANUALS:
            self.assertEqual((self.destination / "docs" / name).read_bytes(),
                             (self.documentation / name).read_bytes())
        self.assertEqual((self.destination / 'docs/presentation' / PRESENTATION_FILE).read_bytes(),
                         (self.documentation / PRESENTATION_FILE).read_bytes())
        for name in [PRESENTATION_RECEIPT, *MANUAL_PREVIEWS.values()]:
            self.assertEqual((self.destination / 'docs/presentation' / name).read_bytes(),
                             (self.documentation / name).read_bytes())
            self.assertFalse((self.destination / 'docs' / name).exists())
        receipt = json.loads((self.destination / "docs/UI_SCREENSHOTS_BUILD.json").read_text())
        for key, value in self.receipt.items():
            self.assertEqual(receipt[key], value)
        # The receipt binds to the original artifact manifest. The installed
        # manifest rewrites paths for online-help static URLs; both exact
        # manifests remain independently hash-bound in the installed receipt.
        self.assertEqual(receipt["source_manifest_file"], "UI_SCREENSHOTS_SOURCE.json")
        preserved = self.destination / "docs" / receipt["source_manifest_file"]
        self.assertEqual(preserved.read_bytes(), self.manifest_path.read_bytes())
        self.assertEqual(receipt["screenshot_manifest_sha256"], evidence.sha256(self.manifest_path))
        self.assertEqual(receipt["screenshot_manifest_sha256"], evidence.sha256(preserved))
        self.assertEqual(receipt["installed_manifest_sha256"], evidence.sha256(installed_manifest_path))
        self.assertNotEqual(evidence.sha256(installed_manifest_path), evidence.sha256(self.manifest_path))
        validated = evidence.validate_installed_documentation(self.destination)
        self.assertEqual(validated["source_commit"], COMMIT)
        self.assertEqual(validated["build"], RELEASE.build)

    def test_ci_install_replaces_source_presentation_receipt_and_previews_together(self):
        # Source packages carry an honest pending deck. A verified CI batch must
        # replace every presentation artifact at the same documented location.
        source_deck = self.destination / 'docs/presentation'
        source_deck.mkdir(parents=True, exist_ok=True)
        for name in [PRESENTATION_FILE, PRESENTATION_RECEIPT, *MANUAL_PREVIEWS.values()]:
            (source_deck / name).write_bytes(b'UNIT TEST: old source presentation')
        self.install()
        for name in [PRESENTATION_FILE, PRESENTATION_RECEIPT, *MANUAL_PREVIEWS.values()]:
            self.assertEqual((source_deck / name).read_bytes(), (self.documentation / name).read_bytes())
        evidence.validate_installed_documentation(self.destination)

    def test_installed_documentation_cannot_be_reused_after_build_date_changes(self):
        self.install()
        (self.destination / "BUILD").write_text("20000101\n")
        with self.assertRaisesRegex(evidence.EvidenceError, "release metadata"):
            evidence.validate_installed_documentation(self.destination)

    def test_installed_documentation_rejects_changed_source_manifest_and_partial_receipt(self):
        self.install()
        source = self.destination / 'docs/UI_SCREENSHOTS_SOURCE.json'
        original = source.read_bytes()
        source_data = json.loads(original)
        source_data['browser']['version'] = 'different-browser'
        write_json(source, source_data)
        with self.assertRaisesRegex(evidence.EvidenceError, "original artifact"):
            evidence.validate_installed_documentation(self.destination)
        source.write_bytes(original)
        (self.destination / 'docs/UI_SCREENSHOTS_BUILD.json').unlink()
        with self.assertRaisesRegex(evidence.EvidenceError, "Manifest missing"):
            evidence.validate_installed_documentation(self.destination)

    def test_late_invalid_image_prevents_any_destination_change(self):
        path = self.artifact / self.manifest["screenshots"][-1]["file"]
        path.write_bytes(b"tampered")
        with self.assertRaises(evidence.EvidenceError):
            self.install()
        self.assertEqual(tree_bytes(self.destination), self.initial_destination)

    def test_late_invalid_pdf_prevents_even_valid_screenshots_being_installed(self):
        path = self.documentation / self.receipt["files"][-1]["file"]
        path.write_bytes(b"tampered")
        with self.assertRaises(evidence.EvidenceError):
            self.install()
        self.assertEqual(tree_bytes(self.destination), self.initial_destination)

    def test_invalid_receipt_keeps_existing_candidate_files_byte_identical(self):
        previous_static = self.destination / "app/static/help/ui-runtime"
        previous_static.mkdir(parents=True)
        (previous_static / "manifest.json").write_bytes(b"existing manifest")
        previous_docs = self.destination / "docs"
        previous_docs.mkdir()
        (previous_docs / "documentazione_utente.pdf").write_bytes(b"existing manual")
        before = tree_bytes(self.destination)
        self.receipt["source_commit"] = OTHER_COMMIT
        self.save_receipt()
        with self.assertRaises(evidence.EvidenceError):
            self.install()
        self.assertEqual(tree_bytes(self.destination), before)

    def test_unlisted_artifact_files_are_not_copied_into_application(self):
        (self.artifact / "private-credentials.json").write_text("UNIT TEST DO NOT COPY")
        (self.documentation / "unlisted.pdf").write_bytes(b"%PDF-1.4 UNLISTED")
        self.install()
        names = set(tree_bytes(self.destination))
        self.assertNotIn("docs/unlisted.pdf", names)
        self.assertFalse(any("private-credentials" in name for name in names))


if __name__ == "__main__":
    unittest.main()
