"""RC89: keep browser capture contract and visual teaching layout synchronized."""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from scripts import capture_ui_screenshots as capture
from scripts import ui_documentation_evidence as evidence
from scripts.verify_visual_training_rc64 import (
    ADDED_SLIDES, ARCH_AFTER, ARCH_SLIDES, INSERT_AFTER,
    WORKFLOW_AFTER, WORKFLOW_INTRO_SLIDES, ALBOT_AFTER, ALBOT_ADDED_SLIDES, REQUIRED_CI,
)

ROOT = Path(__file__).resolve().parents[1]
DRAW_TEXT = '{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def deck_number(original_index: int) -> int:
    return (original_index + (ARCH_SLIDES if original_index > ARCH_AFTER else 0)
            + (ADDED_SLIDES if original_index > INSERT_AFTER else 0)
            + (WORKFLOW_INTRO_SLIDES if original_index > WORKFLOW_AFTER else 0)
            + (ALBOT_ADDED_SLIDES if original_index > ALBOT_AFTER else 0))


def test_browser_evidence_and_capturer_have_identical_mandatory_sets():
    assert capture.REQUIRED_CAPTURES == evidence.REQUIRED_SCREENSHOTS
    assert len(capture.REQUIRED_CAPTURES) == 32
    for ident in ('pdf-generated-preview', 'notification-preview', 'tenant-wizard-next-step'):
        assert ident in evidence.REQUIRED_SCREENSHOTS
        assert ident in REQUIRED_CI or ident == 'pdf-generated-preview'


def test_tenant_wizard_second_step_is_authorized_with_exact_dom_provenance():
    assert evidence.ELEMENT_CAPTURE_SELECTORS['tenant-wizard-next-step'] == '.setup-wizard-shell'
    assert evidence.DOCUMENTATION_CAPTURE_ROUTES['tenant-wizard-next-step'] == '/admin/setup-wizard'
    source = (ROOT / 'scripts/capture_ui_screenshots.py').read_text(encoding='utf-8')
    assert 'snap(limited_page, "tenant-wizard-next-step"' in source
    assert 'element_selector=".setup-wizard-shell"' in source
    assert 'expect(limited_page.locator(".setup-step-item.skipped")).to_have_count(1)' in source


def test_training_insertion_offsets_keep_catalog_and_spam_in_order():
    assert (deck_number(33), deck_number(40), deck_number(62)) == (43, 55, 78)
    assert deck_number(48) == 63
    assert deck_number(70) == 86
    deck = ROOT / 'docs/presentation/CIR_Operational_Training_Visual.pptx'
    if not deck.is_file():
        pytest.skip('Editorial deck is not committed in this checkout')
    with ZipFile(deck) as archive:
        for number, phrase in ((43, 'Catalogo workflow'), (55, 'Catalogo workflow'),
                               (78, 'Laboratorio Tutorial'), (86, 'categorie')):
            xml = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            text = ' '.join(node.text or '' for node in xml.iter(DRAW_TEXT))
            assert phrase.casefold() in text.casefold(), (number, phrase)


def test_secondary_training_deck_renders_every_new_required_capture():
    from scripts.build_training_presentation import load_content
    from release_metadata import read_release_metadata
    import json
    content = load_content(ROOT, read_release_metadata(ROOT))
    screenshot_items = [item for item in content['slides'] if item.get('screenshots')]
    assert all(item['type'] == 'screenshots' for item in screenshot_items)
    shots = [sid for item in screenshot_items for sid in item['screenshots']]
    assert len(shots) == len(set(shots)) == 32
    assert set(shots) == evidence.REQUIRED_SCREENSHOTS
    assert any('notification-preview' in item['screenshots'] for item in screenshot_items)
    assert any('tenant-wizard-next-step' in item['screenshots'] for item in screenshot_items)


def test_secondary_training_rejects_invisible_screenshot_declaration(tmp_path):
    import json
    from scripts.build_training_presentation import load_content
    from scripts.ui_documentation_evidence import EvidenceError
    from release_metadata import read_release_metadata
    data = json.loads((ROOT / 'docs/presentation/content_it.json').read_text(encoding='utf8'))
    wizard = next(item for item in data['slides']
                  if 'tenant-wizard-next-step' in item.get('screenshots', []))
    wizard['type'] = 'columns'  # JSON declaration must not count as actual embedding
    docs = tmp_path / 'docs/presentation'
    docs.mkdir(parents=True)
    (docs / 'content_it.json').write_text(json.dumps(data), encoding='utf8')
    with pytest.raises(EvidenceError, match='rendered screenshot slide'):
        load_content(tmp_path, read_release_metadata(ROOT))
