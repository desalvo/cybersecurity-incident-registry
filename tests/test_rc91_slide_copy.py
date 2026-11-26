"""RC91: keep short user-approved captions on slide 15/16 after regeneration."""
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DECK=ROOT/'docs/presentation/CIR_Operational_Training_Visual.pptx'
SPEC=ROOT/'docs/presentation/visual_rc64_spec.json'
NS='{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def slide_text(number):
    with ZipFile(DECK) as archive:
        xml=ET.fromstring(archive.read(f'ppt/slides/slide{number}.xml'))
    return ' '.join(row.text or '' for row in xml.iter(NS))


def test_slide_15_and_16_approved_wording_is_persistent():
    content=json.loads(SPEC.read_text(encoding='utf8'))
    all_copy=json.dumps(content,ensure_ascii=False)
    assert 'La screenshot documenta due incidenti chiusi' in all_copy
    assert 'i casi chiusi non dovrebbero mai avere avvisi attivi.' in all_copy
    assert 'La cattura CI successiva documenta due incidenti chiusi' not in all_copy
    assert 'la nuova CI ne verificherà la correzione' not in all_copy
    for n,required in ((15,'La screenshot documenta due incidenti chiusi'),
                       (16,'i casi chiusi non dovrebbero mai avere avvisi attivi.')):
        assert required in slide_text(n)
