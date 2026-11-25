"""RC76: incident workflow choice is documented at entry and in the SPAM lab.

Checks correspond to the real CIR first-category scope implementation; never
promote test-only image fixtures into published screenshot evidence.
"""
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from scripts.verify_visual_training_rc64 import (
    LAB_SPAM_OPENING_SLIDE, PALETTE_SLIDE, linked_slide_image_digests,
)

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'docs/presentation'
NS='{http://schemas.openxmlformats.org/drawingml/2006/main}'


def test_first_category_is_actual_runtime_workflow_scope():
    scope=(ROOT/'app/workflow_lifecycle.py').read_text(encoding='utf8')
    impl=(ROOT/'app/routes.py').read_text(encoding='utf8')
    assert 'ids[0]' in scope
    assert '_steps_query(tenant_id, ids[0])' in scope
    assert 'return None' in scope
    assert 'workflow_step_scope_query(category_ids[0]' in impl
    assert 'workflow_step_scope_query(None' in impl


def test_manual_and_template_entry_both_explain_category_priority_and_fallback():
    src=json.loads((P/'visual_rc69_addendum.json').read_text(encoding='utf8'))
    slides={row['training_flow']:row for row in src['slides']}
    for flow in ('incident-entry','incident-blank','incident-template'):
        joined=' '.join(slides[flow]['bullets']).lower()
        assert 'categoria' in joined
        assert 'prima' in joined or 'primo' in joined
        assert 'workflow' in joined
        assert 'crea' in joined
    assert 'default' in ' '.join(slides['incident-blank']['bullets']).lower()
    assert 'default' in ' '.join(slides['incident-template']['bullets']).lower()
    assert 'non si combinano workflow' in ' '.join(slides['incident-template']['bullets']).lower()
    assert 'modello predefinito' not in ' '.join(slides['incident-entry']['bullets']).lower()
    assert all(len(row['bullets']) == 4 for row in src['slides'])
    assert 'non contiene un workflow indipendente' in ' '.join(slides['incident-model']['bullets']).lower()


def test_tutorial_spam_lab_has_practical_start_to_finish_procedure():
    src=json.loads((P/'visual_rc64_spec.json').read_text(encoding='utf8'))
    slide=next(row for row in src if row['index']==62)
    assert 'Laboratorio Tutorial' in slide['title']
    text=' '.join(slide['bullets']).lower()
    for expected in ('tutorial','tenants default','spam','categorie disponibili',
                     'categorie selezionate','prima','nessun modello','crea', 'corrente'):
        assert expected in text
    assert len(slide['bullets']) == 4
    assert 'rischi per diritti e libertà' in text


def test_category_diagrams_and_same_run_lab_capture_are_hard_gates():
    js=(ROOT/'scripts/build_training_visual_rc64.js').read_text(encoding='utf8')
    py=(ROOT/'scripts/verify_visual_training_rc64.py').read_text(encoding='utf8')
    assert "if(d.index===62)" in js
    assert "ciById.get('spam-incident-config-labels')" in js
    assert "'1ª CATEGORIA\\nSPAM'" in js
    assert "'WORKFLOW\\nSPAM'" in js
    assert "'1ª SPAM  →  workflow SPAM  →  Crea'" in js
    assert 'SPAM prima tra le categorie' in js
    assert LAB_SPAM_OPENING_SLIDE == 71
    assert PALETTE_SLIDE == 79
    assert 'checksum not in lab_opening_digests' in py


def test_generated_editorial_deck_includes_workflow_instructions():
    pptx=P/'CIR_Operational_Training_Visual.pptx'
    if not pptx.exists():
        # The GitHub test checkout generates the current deck in the document job;
        # source checks above always run in the general Python job.
        return
    with ZipFile(pptx) as archive:
        for no,needles in {19:('prima categoria','workflow'),
                           23:('prima categoria','workflow'),
                           71:('Laboratorio Tutorial','WORKFLOW','SPAM')}.items():
            page=ET.fromstring(archive.read(f'ppt/slides/slide{no}.xml'))
            contents=' '.join((x.text or '') for x in page.iter(NS+'t')).lower()
            assert all(n.lower() in contents for n in needles), (no, contents[:200])
        assert linked_slide_image_digests(archive,71)
