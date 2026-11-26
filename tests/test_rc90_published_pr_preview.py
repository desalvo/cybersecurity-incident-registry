"""RC90: a documentation PR audits published bytes, not unavailable CI scratch files."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import pytest

from scripts.published_visual_training import validate_published_pdf_preview


def preview_record():
    return {
        'source_kind': 'cir-generated-mapped-acroform',
        'pdf_file': 'screenshots/generated-mapped-example.pdf',
        'pdf_sha256': 'a' * 64,
        'png_file': 'screenshots/generated-mapped-example.png',
        'png_sha256': 'b' * 64,
    }


def test_published_preview_does_not_require_ci_temporary_files(tmp_path):
    # The screenshot hashes originate from the already verified original
    # manifest; the same-run CI independently checked the source PDF/PNG bytes.
    assert list(tmp_path.iterdir()) == []
    original = {'generated_pdf_preview': preview_record()}
    installed = deepcopy(original)
    assert validate_published_pdf_preview(original, installed) == preview_record()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('mutation', [
    ('pdf_sha256', 'f' * 64), ('png_sha256', '0' * 64),
    ('pdf_file', '../other.pdf'), ('png_file', '/tmp/untrusted.png'),
    ('pdf_file', 'screenshots\\other.pdf'), ('png_file', 'C:other.png'),
    ('png_sha256', None), ('pdf_sha256', 12),
    ('source_kind', 'arbitrary-file'),
])
def test_published_preview_rejects_metadata_tampering(mutation):
    original = {'generated_pdf_preview': preview_record()}
    installed = deepcopy(original)
    installed['generated_pdf_preview'][mutation[0]] = mutation[1]
    with pytest.raises(ValueError, match='preview'):
        validate_published_pdf_preview(original, installed)


def test_published_preview_rejects_invalid_but_matching_untrusted_source():
    original = {'generated_pdf_preview': preview_record()}
    original['generated_pdf_preview']['pdf_file'] = '../untrusted.pdf'
    installed = deepcopy(original)
    with pytest.raises(ValueError, match='preview'):
        validate_published_pdf_preview(original, installed)


def test_published_and_same_run_visual_verification_keep_distinct_pdf_rules():
    source = (Path(__file__).resolve().parents[1] /
              'scripts/verify_visual_training_rc64.py').read_text(encoding='utf-8')
    assert 'if not published_ci_images:' in source
    assert 'validate_published_pdf_preview(data, data)' in source
    assert "if preview['png_sha256'] not in linked_slide_image_digests" in source
    assert 'Generated PDF preview SHA-256 mismatch' in source
    # Do not change the same-run verifier to a manifest-only check.
    assert "not (manifest_path.parent / preview['pdf_file']).read_bytes().startswith(b'%PDF-')" in source


def test_gallery_regressions_use_published_manifest_and_not_obsolete_images():
    source = (Path(__file__).resolve().parents[1] /
              'tests/test_rc88_workflow_gallery.py').read_text(encoding='utf-8')
    assert "if published:" in source
    assert "check_published_receipt(ROOT,DECK,PDF,manifest,receipt)" in source
    assert "step_id='spam-workflow-steps' if 'spam-workflow-steps' in rows else 'workflow-steps-focused'" in source
    assert "categories=ARCHIVE/rows['spam-incident-config-labels']['file']" in source
