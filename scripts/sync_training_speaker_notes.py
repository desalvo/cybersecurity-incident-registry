#!/usr/bin/env python3
"""Synchronize the frozen editable training deck's speaker notes with content_it.json.

Only notes-slide XML may change; all real UI screenshots, layouts, slide media,
manual previews and other presentation parts remain byte-identical.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'presentation'
DECK = DOCS / 'CIR_Operational_Training_IT.pptx'
NOTES = '{http://schemas.openxmlformats.org/drawingml/2006/main}t'


def synchronize() -> list[int]:
    notes = [s['notes'] for s in json.loads((DOCS / 'content_it.json').read_text(encoding='utf8'))['slides']]
    changed = []
    with NamedTemporaryFile(dir=DOCS, prefix='.notes-', suffix='.pptx', delete=False) as temp:
        target = Path(temp.name)
    try:
        with ZipFile(DECK) as original, ZipFile(target, 'w') as output:
            expected = {f'ppt/notesSlides/notesSlide{i}.xml' for i in range(1, len(notes) + 1)}
            available = set(original.namelist())
            if not expected <= available:
                raise ValueError('Presentation is missing one or more authoring notes')
            for item in original.infolist():
                content = original.read(item.filename)
                match = re.fullmatch(r'ppt/notesSlides/notesSlide([1-9][0-9]*)\.xml', item.filename)
                if match:
                    index = int(match.group(1))
                    if 1 <= index <= len(notes):
                        root = ET.fromstring(content)
                        text_nodes = list(root.iter(NOTES))
                        if not text_nodes:
                            raise ValueError(f'Slide {index}: missing notes text')
                        # Keep additional provenance/source annotations intact.
                        # Only the primary authoring notes run is synchronized.
                        if notes[index - 1] not in ' '.join(n.text or '' for n in text_nodes):
                            if not notes[index - 1].startswith((text_nodes[0].text or '')[:80]):
                                raise ValueError(f'Slide {index}: unexpected notes divergence')
                            text_nodes[0].text = notes[index - 1]
                            content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                            changed.append(index)
                output.writestr(item, content)
        with ZipFile(target) as verified:
            if verified.testzip() is not None:
                raise ValueError('Damaged training presentation')
        target.replace(DECK)
        receipt_file = DOCS / 'presentation-receipt.json'
        receipt = json.loads(receipt_file.read_text(encoding='utf8'))
        receipt['sha256'] = hashlib.sha256(DECK.read_bytes()).hexdigest()
        receipt_file.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
        return changed
    finally:
        target.unlink(missing_ok=True)


if __name__ == '__main__':
    print('Speaker notes synchronized on slides:', synchronize())
