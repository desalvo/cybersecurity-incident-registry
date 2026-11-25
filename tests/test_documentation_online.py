"""Exercise the shared documentation design through authenticated Flask HTTP."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class DocumentationOnlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='cir-doc-http-')
        base = Path(cls.directory.name)
        env = {
            'DATABASE_URL': 'sqlite:///' + str(base / 'app.db'),
            'SECRET_KEY': 'docs-test-' + 's' * 64,
            'ADMIN_INITIAL_PASSWORD': 'DocumentationTest123!',
            'CIR_DISABLE_BACKGROUND_SCHEDULERS': '1', 'CIR_DISABLE_CSRF': '0',
            'CIR_PRODUCTION': '0', 'FLASK_ENV': 'testing',
        }
        for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
                    'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR'):
            env[key] = str(base / key.lower())
        cls.environment = patch.dict(os.environ, env)
        cls.environment.start()
        from app import create_app
        cls.app = create_app()
        cls.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        from app import db
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        cls.environment.stop()
        cls.directory.cleanup()

    def setUp(self):
        from app import db
        from app.models import Setting
        with self.app.app_context():
            db.session.merge(Setting(key='global_ui_mode', value='modern'))
            db.session.commit()
        self.client = self.app.test_client()
        page = self.client.get('/login').get_data(as_text=True)
        match = (re.search(r'name="_csrf_token" value="([^"]+)"', page)
                 or re.search(r'name="csrf-token" content="([^"]+)"', page))
        self.assertIsNotNone(match)
        result = self.client.post('/login', data={'username': 'admin',
            'password': 'DocumentationTest123!', '_csrf_token': match[1]})
        self.assertIn(result.status_code, (302, 303))

    def test_every_online_manual_has_one_shared_cover_and_valid_navigation(self):
        from app.documentation import GUIDES
        urls = ['/aiuto', '/aiuto/amministrazione', '/aiuto/note-rilascio']
        urls += ['/aiuto/guide/' + slug for slug in GUIDES]
        for language in ('it', 'en'):
            for url in urls:
                with self.subTest(language=language, url=url):
                    response = self.client.get(url, headers={'Accept-Language': language})
                    self.assertEqual(response.status_code, 200)
                    html = response.get_data(as_text=True)
                    self.assertEqual(html.count('data-documentation-cover'), 1)
                    cover = re.search(r'<header[^>]*data-documentation-cover[^>]*>(.*?)</header>', html, re.S)[1]
                    info = self.app.config['APP_INFO']
                    for key in ('version', 'build', 'author', 'author_email', 'project_url'):
                        self.assertIn(info[key], cover)
                    for platform in info['platforms']:
                        self.assertIn('/static/' + platform['logo'], cover)
                        self.assertIn(platform['name'], cover)
                    self.assertIn('ui/documentation.css', html)
                    self.assertIn('cybersecurity-hero-v2.png', cover)
                    self.assertIn('data-cir-nav-link', html)
                    self.assertIn('/admin/interface', html)  # existing application menu retained
                    for anchor in re.findall(r'href="#([^"]+)"', cover):
                        self.assertIn('id="' + anchor + '"', html)
                    self.assertIn('Download PDF' if language == 'en' else 'Scarica PDF', cover)

    def test_classic_ui_preserves_cover_and_family_navigation(self):
        from app import db
        from app.models import Setting
        with self.app.app_context():
            db.session.merge(Setting(key='global_ui_mode', value='classic'))
            db.session.commit()
        html = self.client.get('/aiuto').get_data(as_text=True)
        self.assertIn('cir-classic', html)
        self.assertIn('ui/documentation.css', html)
        self.assertIn('cir-doc-inline-nav', html)
        self.assertIn('/aiuto/guide/installation', html)

    def test_local_platform_assets_match_the_shipped_manifest(self):
        data = json.loads((ROOT / 'app/static/branding/platforms/manifest.json').read_text())
        self.assertEqual(len(data['platforms']), 6)
        for platform in data['platforms']:
            result = self.client.get('/static/' + platform['logo'])
            self.assertEqual(result.status_code, 200)
            self.assertEqual(hashlib.sha256(result.data).hexdigest(), platform['sha256'])
            result.close()

    def test_runtime_user_admin_and_release_pdf_covers_use_about_identity(self):
        from pypdf import PdfReader
        for language in ('it', 'en'):
            for url in ('/aiuto/pdf', '/aiuto/amministrazione/pdf', '/aiuto/note-rilascio/pdf'):
                with self.subTest(language=language, url=url):
                    response = self.client.get(url, headers={'Accept-Language': language})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'application/pdf')
                    pdf = PdfReader(io.BytesIO(response.data))
                    self.assertGreater(len(pdf.pages), 1)
                    text = pdf.pages[0].extract_text()
                    for key in ('version', 'build', 'author', 'author_email', 'project_url'):
                        self.assertIn(self.app.config['APP_INFO'][key], text)
                    self.assertGreaterEqual(len(pdf.pages[0].images), 8)
                    urls = {entry.get_object().get('/A', {}).get('/URI')
                            for entry in pdf.pages[0].get('/Annots', [])}
                    self.assertIn(self.app.config['APP_INFO']['project_url'], urls)

    def test_new_guides_retain_authentication_mfa_and_expiry_policy(self):
        for path in ('/aiuto/guide/security', '/aiuto/guide/security/pdf'):
            anonymous = self.app.test_client().get(path)
            self.assertEqual(anonymous.status_code, 302)
            self.assertIn('/login', anonymous.location)
        with self.client.session_transaction() as session:
            session['mfa_user_id'] = 1
        result = self.client.get('/aiuto/guide/installation')
        self.assertEqual(result.status_code, 302)
        self.assertIn('mfa', result.location)
        with self.client.session_transaction() as session:
            session.pop('mfa_user_id', None)
            session['last_activity'] = 1
        result = self.client.get('/aiuto/guide/installation')
        self.assertEqual(result.status_code, 302)
        self.assertIn('/login', result.location)

    def test_guide_pdf_is_allowlisted_and_has_native_cover_and_source_content(self):
        from pypdf import PdfReader
        self.assertEqual(self.client.get('/aiuto/guide/not-a-guide').status_code, 404)
        self.assertEqual(self.client.get('/aiuto/guide/not-a-guide/pdf').status_code, 404)
        self.assertEqual(self.client.get('/aiuto/guide/../../.env').status_code, 404)
        response = self.client.get('/aiuto/guide/alfresco/pdf', headers={'Accept-Language': 'it'})
        self.assertEqual(response.status_code, 200)
        reader = PdfReader(io.BytesIO(response.data))
        self.assertIn('Guida Alfresco', reader.pages[0].extract_text())
        text = '\n'.join(page.extract_text() or '' for page in reader.pages[1:])
        for term in ('Parent Node ID', 'Hotfix', 'Sync', 'documentLibrary'):
            self.assertIn(term, text)

    def test_markdown_escapes_html_and_maps_internal_guide_links(self):
        from app.documentation import render_source_markdown
        with self.app.test_request_context('/aiuto/guide/security'):
            html = str(render_source_markdown('''# A title
<script>alert(1)</script>
[unsafe](javascript:alert)
[guide](MIGRATION.md)
[anchor](#conformità)

## Conformità

| Key | Value |
| --- | --- |
| Demo | **Safe** |

```html
<img src=x onerror=alert(1)>
```
'''))
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn('href="/aiuto/guide/migration"', html)
        self.assertIn('<table', html)
        self.assertIn('<strong>Safe</strong>', html)
        self.assertIn('id="conformità"', html)
        self.assertIn('href="#conformità"', html)

    def test_identity_rejects_active_urls_and_keeps_custom_public_about_values(self):
        from application_identity import read_application_identity
        for url in ('javascript:alert(1)', 'file:///etc/passwd', 'https://u:p@example.org', '//example.org'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                read_application_identity(ROOT, {'APP_PROJECT_URL': url})
        identity = read_application_identity(ROOT, {'APP_NAME': 'Test registry',
            'APP_AUTHOR': 'Example author', 'APP_AUTHOR_EMAIL': 'author@example.org',
            'APP_PROJECT_URL': 'https://example.org/project'})
        self.assertEqual(identity['name'], 'Test registry')
        self.assertEqual(identity['project_url'], 'https://example.org/project')

    def test_runtime_pdf_retains_each_verified_figure_and_omits_unverified_ones(self):
        from app.documentation import runtime_pdf_visuals
        static = ROOT / 'app/static/help'
        originals = {
            '3': [('Registry', static / 'screenshot-dashboard.png')],
            '5': [('Incident', static / 'screenshot-incident-detail.png')],
            '10': [('Modules', static / 'screenshot-modules.png')],
        }
        # Mock only the evidence lookup: these are explicit test fixtures and
        # are never written into a screenshot manifest or released as captures.
        with self.app.test_request_context('/aiuto/pdf'):
            with patch('app.ui_documentation.documentation_screenshot', side_effect=lambda sid: '/static/help/ui-runtime/' + sid + '.jpg'):
                converted = runtime_pdf_visuals(originals)
            seen = set()
            rendered = []
            # The runtime generators deduplicate figures by their caption.
            for rows in converted.values():
                for caption, path in rows:
                    if caption not in seen:
                        rendered.append(path.name)
                        seen.add(caption)
            self.assertEqual(rendered, ['registry-desktop.jpg', 'incident-desktop.jpg', 'admin-modules-desktop.jpg'])
            with patch('app.ui_documentation.documentation_screenshot', return_value=None):
                self.assertTrue(all(not rows for rows in runtime_pdf_visuals(originals).values()))


if __name__ == '__main__':
    unittest.main()
