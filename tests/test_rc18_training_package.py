"""Release-contract checks for the training material and its editable sources."""
import json
import hashlib
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}


class TrainingPackageTests(unittest.TestCase):
    def test_powerpoint_contains_every_authored_slide_and_speaker_note(self):
        content = json.loads((DOCS / 'presentation/content_it.json').read_text())
        with ZipFile(DOCS / 'presentation/CIR_Operational_Training_IT.pptx') as archive:
            self.assertIsNone(archive.testzip())
            slides = [name for name in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', name)]
            notes = [name for name in archive.namelist() if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', name)]
            self.assertEqual(len(slides), len(content['slides']))
            self.assertEqual(len(notes), len(content['slides']))
            for index, authored in enumerate(content['slides'], 1):
                slide = ET.fromstring(archive.read(f'ppt/slides/slide{index}.xml'))
                text = ' '.join(node.text or '' for node in slide.findall('.//a:t', NS))
                title = ' '.join(authored['title'].split())
                self.assertIn(title, ' '.join(text.split()))
                note = ET.fromstring(archive.read(f'ppt/notesSlides/notesSlide{index}.xml'))
                note_text = ' '.join(node.text or '' for node in note.findall('.//a:t', NS))
                self.assertIn(' '.join(authored['notes'].split()), ' '.join(note_text.split()))

    def test_photographic_assets_are_declared_and_rebuild_inputs_are_portable(self):
        assets = DOCS / 'presentation/assets'
        sources = json.loads((assets / 'sources.json').read_text())
        self.assertEqual(sources['schema_version'], 2)
        for record in sources['images']:
            path = ROOT / record['file']
            self.assertTrue(path.resolve().is_relative_to(ROOT.resolve()))
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record['sha256'])
            self.assertIn('fictitious', record['origin'])
            self.assertIn('no people', record['origin'])
        generator = (DOCS / 'presentation/build.mjs').read_text()
        self.assertNotIn('/workspace/', generator)
        self.assertNotIn('/home/agent/', generator)
        self.assertIn('scripts/build_training_presentation.py', generator)
        self.assertNotIn('@oai/artifact-tool', generator)
        self.assertNotIn('CIR_PRESENTATIONS_SKILL_DIR', generator)

    def test_source_presentation_receipt_binds_real_manual_first_pages(self):
        directory = DOCS / 'presentation'
        receipt = json.loads((directory / 'presentation-receipt.json').read_text())
        deck = directory / 'CIR_Operational_Training_IT.pptx'
        self.assertEqual(receipt['functional_version'], (ROOT / 'VERSION').read_text().strip())
        self.assertEqual(receipt['sha256'], hashlib.sha256(deck.read_bytes()).hexdigest())
        self.assertEqual(len(receipt['manual_first_pages']), 5)
        # A checkout can contain the previous frozen documentation batch while
        # CI stamps a new BUILD. Verify its own evidence instead of relabeling it.
        footer = receipt['functional_version'] + ' · Build ' + receipt['build']
        with ZipFile(deck) as archive:
            slide = ET.fromstring(archive.read('ppt/slides/slide1.xml'))
            text = ' '.join(node.text or '' for node in slide.findall('.//a:t', NS))
            self.assertIn(footer, text)
            for row in receipt['manual_first_pages']:
                pdf, png = DOCS / row['pdf'], directory / row['png']
                self.assertEqual(row['page'], 1)
                self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), row['pdf_sha256'])
                self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), row['png_sha256'])
                self.assertEqual(hashlib.sha256(archive.read(row['media_file'])).hexdigest(), row['png_sha256'])

    def test_new_online_chapters_are_inside_rendered_content_and_navigation(self):
        for name in ('help.html', 'help_en.html', 'admin_help.html', 'admin_help_en.html'):
            text = (ROOT / 'app/templates' / name).read_text()
            start = text.index('{% block content %}')
            end = text.index('{% endblock %}')
            for anchor in ('rc18-tenants-default', 'rc18-export-portable'):
                self.assertLess(start, text.index(f'id="{anchor}"'))
                self.assertLess(text.index(f'id="{anchor}"'), end)
                self.assertIn(f'href="#{anchor}"', text[start:end])
            self.assertFalse(text[end + len('{% endblock %}'):].strip(), name)
            self.assertNotIn('workflows are merged and duplicates removed', text)

    def test_pdf_manuals_include_current_release_and_new_chapters(self):
        from pypdf import PdfReader
        for name in ('documentazione_utente', 'documentazione_amministrativa',
                     'user_documentation_en', 'administrator_documentation_en'):
            reader = PdfReader(DOCS / (name + '.pdf'))
            text = '\n'.join(page.extract_text() for page in reader.pages)
            self.assertIn((ROOT / 'VERSION').read_text().strip(), text)
            self.assertIn('Tenants Default', text)
            self.assertNotIn('0.7.0-7', text)
            if name in ('documentazione_amministrativa', 'administrator_documentation_en'):
                self.assertIn('OpenShift', text)

    def test_packaging_requires_training_and_its_editable_sources(self):
        package = (ROOT / 'scripts/package_release.sh').read_text()
        verifier = (ROOT / 'scripts/verify_release_candidate.py').read_text()
        for name in ('docs/TRAINING.md', 'docs/presentation/CIR_Operational_Training_IT.pptx',
                     'docs/presentation/content_it.json', 'docs/presentation/build.mjs',
                     'docs/presentation/assets/sources.json', 'scripts/build_brochures.py'):
            self.assertTrue((ROOT / name).is_file(), name)
            self.assertIn(name, package)
            self.assertIn(name, verifier)


if __name__ == '__main__':
    unittest.main()
