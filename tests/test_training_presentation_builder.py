"""Portable authoring and same-build media contracts; no browser or network.

PNG/PDF inputs in this test are artificial fixtures. They never become the
distributed presentation or evidence of a completed application capture.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from release_metadata import read_release_metadata
from scripts.build_training_presentation import build_presentation, load_content, preflight
from scripts.presentation_evidence import (MANUAL_PDFS, MANUAL_PREVIEWS, PRESENTATION_FILE,
                                           PRESENTATION_RECEIPT, validate_presentation)
from scripts.ui_documentation_evidence import (DOCUMENTATION_CAPTURE_CHECKS, DOCUMENTATION_CAPTURE_ROUTES,
                                              EvidenceError, REQUIRED_MANUALS, REQUIRED_SCREENSHOTS,
                                              load_evidence, sha256)

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


class PresentationBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cir-pptx-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.docs = self.directory / "documentation"
        self.docs.mkdir()
        self.captures = self.directory / "captures"
        self.captures.mkdir()
        self.output = self.directory / "result" / PRESENTATION_FILE
        self.metadata = read_release_metadata(ROOT)
        for name in REQUIRED_MANUALS:
            self.write_pdf(name)

    def write_pdf(self, name, *, version=None, build=None):
        path = self.docs / name
        pdf = canvas.Canvas(str(path), pagesize=A4)
        pdf.setTitle("Artificial documentation fixture")
        pdf.drawString(30, 800, "Artificial test input: " + name)
        pdf.drawString(30, 775, "Version " + (version or self.metadata.version))
        pdf.drawString(30, 750, "Build " + (build or self.metadata.build))
        pdf.showPage()
        pdf.save()

    def write_evidence(self):
        rows = []
        for index, sid in enumerate(sorted(REQUIRED_SCREENSHOTS)):
            width, height = (400, 700) if "mobile" in sid else (640, 480)
            path = self.captures / (sid + ".png")
            # Test-only colored inputs keep different capture hashes distinct.
            Image.new("RGB", (width, height), (index*11 % 255, 55, 140)).save(path)
            rows.append({"id": sid, "file": path.name, "sha256": sha256(path),
                         "viewport": {"width": width, "height": height},
                         "ui_mode": "classic" if sid.startswith("classic-") else "modern",
                         "authenticated": not sid.startswith("login-"),
                         "route": DOCUMENTATION_CAPTURE_ROUTES.get(sid, "/test-fixture"),
                         "capture_area": "viewport",
                         "caption_it": "Fixture artificiale: " + sid,
                         "caption_en": "Artificial fixture: " + sid})
        data = {"schema_version": 1, "source_kind": "real-application-browser",
                "data_provenance": "isolated-synthetic-fixture", "source_commit": COMMIT,
                "functional_version": self.metadata.version, "build": self.metadata.build,
                "browser": {"name": "unit-test-fixture", "version": "test", "playwright": "test"},
                "checks": {"fixture_only": True, **{name: True for name in DOCUMENTATION_CAPTURE_CHECKS}},
                "screenshots": rows}
        manifest = self.captures / "manifest.json"
        manifest.write_text(json.dumps(data))
        self.write_pdf_receipt(manifest)
        return manifest

    def write_pdf_receipt(self, manifest):
        receipt = {"schema_version": 1, "source_commit": COMMIT,
                   "functional_version": self.metadata.version, "build": self.metadata.build,
                   "screenshot_manifest_sha256": sha256(manifest), "real_screenshots": True,
                   "files": [{"file": name, "sha256": sha256(self.docs / name)}
                             for name in sorted(REQUIRED_MANUALS)]}
        (self.docs / "build-manifest.json").write_text(json.dumps(receipt))

    def test_source_edition_has_editable_training_and_explicit_pending_screenshots(self):
        metadata_before = (ROOT / "BUILD").read_bytes()
        receipt = build_presentation(root=ROOT, output=self.output, documentation_dir=self.docs)
        self.assertFalse(receipt["real_screenshots"])
        self.assertEqual(receipt["screenshots"], [])
        self.assertIsNone(receipt["screenshot_manifest_sha256"])
        self.assertEqual(receipt["status"], "source-edition-awaiting-verified-ci-screenshots")
        self.assertEqual(len(receipt["manual_first_pages"]), 5)
        self.assertEqual((ROOT / "BUILD").read_bytes(), metadata_before)
        authored = load_content(ROOT, self.metadata)["slides"]
        self.assertEqual(receipt["slides"], len(authored))
        with ZipFile(self.output) as archive:
            texts = []
            for index, item in enumerate(authored, 1):
                slide = ET.fromstring(archive.read(f"ppt/slides/slide{index}.xml"))
                text = " ".join(node.text or "" for node in slide.findall(".//a:t", NS))
                text = " ".join(text.split())
                self.assertIn(" ".join(item["title"].split()), text)
                self.assertIn(f"{self.metadata.version} · Build {self.metadata.build}", text)
                texts.append(text)
                note = ET.fromstring(archive.read(f"ppt/notesSlides/notesSlide{index}.xml"))
                note_text = " ".join(node.text or "" for node in note.findall(".//a:t", NS))
                self.assertIn(" ".join(item["notes"].split()), " ".join(note_text.split()))
            self.assertIn("Acquisizione CI in attesa", " ".join(texts))
            for row in receipt["manual_first_pages"]:
                import hashlib
                self.assertEqual(hashlib.sha256(archive.read(row["media_file"])).hexdigest(), row["png_sha256"])

    def test_verified_mode_embeds_every_capture_and_actual_first_page_byte_for_byte(self):
        manifest = self.write_evidence()
        # The actual CI CLI writes the presentation alongside the PDF batch.
        output = self.docs / PRESENTATION_FILE
        receipt = build_presentation(root=ROOT, output=output, documentation_dir=self.docs,
                                     screenshot_manifest=manifest, source_commit=COMMIT,
                                     require_real_screenshots=True)
        self.assertTrue(receipt["real_screenshots"])
        self.assertEqual({row["id"] for row in receipt["screenshots"]}, REQUIRED_SCREENSHOTS)
        self.assertEqual({row["pdf"] for row in receipt["manual_first_pages"]}, MANUAL_PDFS)
        paths = {PRESENTATION_FILE: output,
                 PRESENTATION_RECEIPT: self.docs / PRESENTATION_RECEIPT}
        paths.update({name: self.docs / name for name in MANUAL_PDFS})
        paths.update({name: self.docs / name for name in MANUAL_PREVIEWS.values()})
        checked = validate_presentation(paths, COMMIT, sha256(manifest),
                                        load_evidence(manifest, COMMIT, metadata_root=ROOT), metadata_root=ROOT)
        self.assertEqual(checked["sha256"], sha256(output))
        # A forged receipt cannot reclassify the source edition as reviewed.
        self.assertNotIn("source-edition", json.dumps(checked))
        from scripts.finalize_documentation_bundle import finalize
        batch = finalize(manifest, self.docs, COMMIT, metadata_root=ROOT)
        self.assertEqual(batch["schema_version"], 2)
        self.assertEqual(batch["presentation_receipt_file"], PRESENTATION_RECEIPT)
        self.assertIn(PRESENTATION_FILE, {row["file"] for row in batch["files"]})

    def test_real_mode_without_complete_provenance_fails_before_output(self):
        with self.assertRaisesRegex(EvidenceError, "requires"):
            build_presentation(root=ROOT, output=self.output, documentation_dir=self.docs,
                               require_real_screenshots=True)
        self.assertFalse(self.output.exists())

    def test_source_commit_mismatch_fails_before_output(self):
        manifest = self.write_evidence()
        with self.assertRaisesRegex(EvidenceError, "commit differs"):
            build_presentation(root=ROOT, output=self.output, documentation_dir=self.docs,
                               screenshot_manifest=manifest, source_commit="b"*40,
                               require_real_screenshots=True)
        self.assertFalse(self.output.exists())

    def test_changed_browser_image_fails_before_output(self):
        manifest = self.write_evidence()
        path = self.captures / (sorted(REQUIRED_SCREENSHOTS)[0] + ".png")
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(EvidenceError, "checksum mismatch"):
            build_presentation(root=ROOT, output=self.output, documentation_dir=self.docs,
                               screenshot_manifest=manifest, source_commit=COMMIT,
                               require_real_screenshots=True)
        self.assertFalse(self.output.exists())

    def test_old_manual_build_is_rejected_even_with_updated_file_hash(self):
        manifest = self.write_evidence()
        self.write_pdf("documentazione_utente.pdf", build="20000101")
        self.write_pdf_receipt(manifest)
        with self.assertRaisesRegex(EvidenceError, "first page does not match"):
            build_presentation(root=ROOT, output=self.output, documentation_dir=self.docs,
                               screenshot_manifest=manifest, source_commit=COMMIT,
                               require_real_screenshots=True)
        self.assertFalse(self.output.exists())

    def test_manual_batch_must_reference_exact_screenshot_manifest(self):
        manifest = self.write_evidence()
        path = self.docs / "build-manifest.json"
        receipt = json.loads(path.read_text())
        receipt["screenshot_manifest_sha256"] = "0" * 64
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(EvidenceError, "not built from these screenshots"):
            preflight(ROOT, self.docs, manifest, COMMIT, True)

    def test_illustration_manifest_cannot_be_used_as_real_capture(self):
        manifest = self.write_evidence()
        data = json.loads(manifest.read_text())
        data["source_kind"] = "illustration"
        manifest.write_text(json.dumps(data))
        self.write_pdf_receipt(manifest)
        with self.assertRaisesRegex(EvidenceError, "real application screenshots"):
            preflight(ROOT, self.docs, manifest, COMMIT, True)

    def test_source_metadata_and_exact_view_coverage_are_enforced(self):
        root = self.directory / "fake-source"
        (root / "docs/presentation").mkdir(parents=True)
        content = json.loads((ROOT / "docs/presentation/content_it.json").read_text())
        path = root / "docs/presentation/content_it.json"
        content["version"] = "0.9.0-1"
        path.write_text(json.dumps(content))
        with self.assertRaisesRegex(EvidenceError, "source version"):
            load_content(root, self.metadata)
        content["version"] = self.metadata.version
        next(item for item in content["slides"] if "screenshots" in item)["screenshots"].pop()
        path.write_text(json.dumps(content))
        with self.assertRaisesRegex(EvidenceError, "every required UI view"):
            load_content(root, self.metadata)

    def test_citations_and_lifecycle_are_references_not_certification_claims(self):
        content = load_content(ROOT, self.metadata)
        urls = content["references"]
        for key in ("nis2", "gdpr", "agid_design", "agid_accessibility", "wcag", "nist_ssdf"):
            self.assertTrue(urls[key].startswith("https://"))
        references = [item for item in content["slides"] if item["type"] == "references"]
        self.assertEqual(len(references), 2)
        for item in references:
            self.assertIn("non", item["bottom"].lower())
            self.assertIn("https://", item["notes"])
        lifecycle = next(item for item in content["slides"] if item.get("kicker") == "MANUTENZIONE DELLA SICUREZZA")
        self.assertIn("FixedVersion", lifecycle["notes"])
        self.assertIn("expiry", lifecycle["notes"])
        self.assertIn("non presumere", lifecycle["notes"])


if __name__ == "__main__":
    unittest.main()
