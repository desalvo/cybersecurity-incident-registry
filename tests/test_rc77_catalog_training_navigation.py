"""RC77: the catalog import route in tenant onboarding must match the UI."""
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DRAW_TEXT = '{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def test_catalog_import_navigation_is_documented_in_affected_slides():
    spec = json.loads((ROOT / 'docs/presentation/visual_rc64_spec.json').read_text(encoding='utf-8'))
    for original in (35, 42, 63):
        slide = next(row for row in spec if row.get('original') == original)
        all_text = ' '.join(slide.get('bullets', [])) + '\n' + slide.get('notes', '')
        for phrase in ('Amministrazione', 'Workflow e catalogo', 'Catalogo workflow',
                       'Admin', 'Anagrafiche e workflow'):
            assert phrase in all_text, (original, phrase)
    assert 'Crea una nuova copia nel tenant' in ' '.join(next(row for row in spec if row.get('original') == 42)['bullets'])


def test_catalog_route_matches_real_ui_templates():
    nav = (ROOT / 'app/templates/ui/navigation.html').read_text(encoding='utf-8')
    legacy = (ROOT / 'app/templates/base.html').read_text(encoding='utf-8')
    catalog = (ROOT / 'app/templates/admin_workflow_catalog.html').read_text(encoding='utf-8')
    assert 'Workflow e catalogo' in nav and 'main.admin_workflow_catalog' in nav
    assert 'Anagrafiche e workflow' in legacy and 'main.admin_workflow_catalog' in legacy
    assert 'Crea una nuova copia nel tenant' in catalog


def test_generated_deck_has_catalog_import_navigation_when_available():
    deck = ROOT / 'docs/presentation/CIR_Operational_Training_Visual.pptx'
    if not deck.exists():
        return
    # 88-slide editorial presentation: originals 35,42,63 map to slides 42,49,71.
    with ZipFile(deck) as archive:
        for number in (42, 49, 71):
            page = ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
            text = ' '.join(node.text or '' for node in page.iter(DRAW_TEXT))
            assert 'Catalogo workflow' in text, (number, text[:150])
