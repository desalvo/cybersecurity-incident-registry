#!/usr/bin/env python3
"""CI preflight of CIR training images and their non-stock origin.

A provenance hash is a supply-chain check, not an automated face detector
or a guarantee that an asset can never implicate third-party rights.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PRES=ROOT/'docs/presentation'


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    spec=json.loads((PRES/'visual_rc62_spec.json').read_text(encoding='utf8'))
    provenance=json.loads((PRES/'visual_rc62_provenance.json').read_text(encoding='utf8'))
    assert len(spec)==79
    assert set(provenance['replaced_illustrations']) == {28,33,35,42,43}
    background=ROOT/provenance['background']['path']
    assert background.is_file() and digest(background)==provenance['background']['sha256']
    assert provenance['background']['contains_real_people'] is False
    assert provenance['background']['contains_human_silhouettes'] is False
    historical=json.loads((PRES/'visual_rc61_art/provenance.json').read_text(encoding='utf8'))['slides']
    historical_paths={v['path']:v['sha256'] for v in historical.values()}
    seen=set()
    for row in spec:
        num=row['index']; seen.add(num)
        if num in provenance['replaced_illustrations']:
            assert row.get('synthetic_diagram') and not row.get('conceptual_art'),num
        if row.get('synthetic_diagram'):
            assert num in provenance['replaced_illustrations'],num
        if row.get('conceptual_art'):
            ref=row['conceptual_art']
            assert ref in historical_paths and num not in provenance['replaced_illustrations']
            assert digest(ROOT/ref)==historical_paths[ref], (num,ref)
        for media in row.get('images',[]):
            ref=media['file']
            assert ref.startswith('docs/presentation/visual_rc57_media/') and '..' not in ref
            assert (ROOT/ref).is_file(),ref
        for report in row.get('report_pages',[]):
            assert str(report).startswith('docs/presentation/visual_rc61_art/example_report_page_')
            assert (ROOT/report).is_file(),report
    assert seen==set(range(1,80)),seen
    print(json.dumps({'slides':len(spec),'synthetic_replacements':sorted(provenance['replaced_illustrations']),
                      'replaced_chapter_backgrounds':provenance['replaced_chapter_backgrounds'],
                      'new_background_sha256':provenance['background']['sha256'],
                      'status':'PASS'},ensure_ascii=False,indent=2))

if __name__=='__main__':
 try:verify()
 except (AssertionError, OSError, KeyError, ValueError) as exc:
  print('CIR image provenance FAILED:',repr(exc),file=sys.stderr)
  raise SystemExit(1)
