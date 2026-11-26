"""RC70: instruction follows the learner journey, not the template catalog order."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ADDENDUM=ROOT/'docs/presentation/visual_rc69_addendum.json'


def test_incident_creation_teaching_order_and_content():
    slides=json.loads(ADDENDUM.read_text(encoding='utf8'))['slides']
    assert [s['training_flow'] for s in slides] == [
        'incident-entry', 'incident-blank', 'incident-model',
        'incident-admin', 'incident-from-existing', 'incident-template'
    ]
    assert slides[0]['title'].startswith('Aprire un incidente:')
    assert 'da zero' in slides[1]['title']
    assert 'cosa sono' in slides[2]['title']
    assert 'creazione, modifica e cancellazione' in slides[3]['title']
    assert 'già registrato' in slides[4]['title']
    assert 'usando un modello' in slides[5]['title']
    assert all(len(s['bullets'])==4 for s in slides)
    assert 'nuovo incidente' in ' '.join(slides[0]['bullets']).lower()
    assert 'modello predefinito' not in ' '.join(slides[:1][0]['bullets']).lower()
    assert 'writer' in ' '.join(slides[2]['bullets']).lower()
    assert 'superuser' in ' '.join(slides[2]['bullets'])
    assert 'premere «crea»' in ' '.join(slides[-1]['bullets']).lower()


def test_generator_guards_sequence_and_verifier_references_it():
    js=(ROOT/'scripts/build_training_visual_rc64.js').read_text(encoding='utf8')
    py=(ROOT/'scripts/verify_visual_training_rc64.py').read_text(encoding='utf8')
    assert "const expectedTeachingSequence = ['incident-entry', 'incident-blank', 'incident-model'" in js
    from scripts.verify_visual_training_rc64 import REQUIRED_NEW_SLIDE_TITLES
    for number,title in [(21,'Modelli incidente: cosa sono'), (22,'Amministrare i modelli'),
                         (23,'Creare un modello'), (24,'Aprire un incidente usando un modello')]:
        assert REQUIRED_NEW_SLIDE_TITLES[number].startswith(title)
        assert f"{number}: '{title}" in py
