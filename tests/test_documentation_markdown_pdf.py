"""Standalone Markdown guides retain content without interpreting unsafe markup."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from scripts.documentation_markdown_pdf import build_markdown_pdf
from release_metadata import read_release_metadata


ROOT = Path(__file__).resolve().parents[1]


class MarkdownDocumentationPdfTests(unittest.TestCase):
    def test_stream_output_preserves_text_code_tables_and_safe_links(self):
        long_token = '0123456789ABCDEF' * 55
        raw_html = '<b>RawLiteral</b><script>alert("never-run")</script>'
        source = f'''# Operational guide

{raw_html}

## Procedure

1. First task with **emphasis**.
   - Nested task with `inline_code`.

> Quoted instruction with accented text: gravità → sicurezza.

| Setting | Value |
| --- | --- |
| safe | value\\|literal |
| quoted | <i>Must remain literal</i> |

```text
{long_token}
<img src="file:///never-read-private-data">
```

[Safe documentation](https://example.org/guide)
[Unsafe target](javascript:alert(1))
[Local reference](MIGRATION.md)
![Remote illustration](https://example.invalid/never-fetch.png)

EndOfGuideSentinel
'''
        output = BytesIO()
        with patch('urllib.request.urlopen', side_effect=AssertionError('Remote fetching is forbidden')):
            build_markdown_pdf(output, source, root=ROOT, title='Guida operativa',
                               subtitle='Procedure e configurazione')
        reader = PdfReader(output)
        metadata = read_release_metadata(ROOT)
        cover = reader.pages[0].extract_text() or ''
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        self.assertIn(metadata.version, cover)
        self.assertIn(metadata.build, cover)
        self.assertIn(raw_html, text)
        self.assertIn('<i>Must remain literal</i>', text)
        self.assertIn('value|literal', text)
        self.assertIn('gravità', text)
        self.assertIn('→', text)
        self.assertIn(long_token, ''.join(text.split()))
        self.assertIn('<img src="file:///never-read-private-data">', text)
        self.assertIn('MIGRATION.md', text)
        self.assertIn('https://example.invalid/never-fetch.png', text)
        self.assertIn('EndOfGuideSentinel', text)
        urls = [a.get_object().get('/A', {}).get('/URI', '')
                for page in reader.pages for a in page.get('/Annots', [])]
        self.assertIn('https://example.org/guide', urls)
        self.assertFalse(any(url.startswith(('javascript:', 'file:', 'data:')) for url in urls))
        self.assertEqual(text.count('Piattaforme e tecnologie supportate'), 1)

    def test_very_tall_table_cell_splits_without_losing_content(self):
        repetitions = 900
        source = '# Large table\n\n| Key | Content |\n| --- | --- |\n| one | ' + 'RowSentinel ' * repetitions + '|\n\nLastParagraphSentinel\n'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'table.pdf'
            build_markdown_pdf(output, source, root=ROOT, title='Reference guide',
                               subtitle='Configuration reference', language='en')
            reader = PdfReader(str(output))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            self.assertGreater(len(reader.pages), 3)
            self.assertEqual(text.count('RowSentinel'), repetitions)
            self.assertIn('LastParagraphSentinel', text)
            self.assertEqual(text.count('Supported platforms and technologies'), 1)


if __name__ == '__main__':
    unittest.main()
