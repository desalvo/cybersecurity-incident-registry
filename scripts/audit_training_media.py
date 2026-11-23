#!/usr/bin/env python3
"""Fail closed on unapproved media in the CIR training presentation.

All embedded raster assets must be byte-identical to an approved local CIR
application graphic, locally generated first page of a manual, or an explicitly
validated real-app synthetic-fixture screenshot. This is a provenance check,
not a computer-vision assertion that no people exist in arbitrary pixels.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ALLOWED_SUFFIXES={'.png','.jpg','.jpeg'}

def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def approved_hashes(root:Path,manual_previews:dict|None=None,evidence:dict|None=None)->set[str]:
    approved={}
    # Explicit approved app graphic / logos, never arbitrary assets elsewhere.
    approved_paths=[root/'app/static/help/app-logo.png',root/'app/static/ui/cybersecurity-hero-v2.png']
    from application_identity import read_application_identity
    approved_paths += [root/'app/static'/p['logo'] for p in read_application_identity(root)['platforms']]
    if manual_previews:
        approved_paths.extend(manual_previews.values())
    else:
        approved_paths.extend((root/'docs/presentation').glob('manual-first-page-*.png'))
    if evidence:
        approved_paths.extend(evidence['_paths'].values())
    for path in approved_paths:
        path=Path(path)
        if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError('Missing/unsupported approved asset: '+str(path))
        approved[sha(path.read_bytes())]=path.name
    return set(approved)

def audit(pptx:Path,root:Path,manual_previews:dict|None=None,evidence:dict|None=None)->int:
    approved=approved_hashes(root,manual_previews,evidence)
    with ZipFile(pptx) as deck:
        media=[n for n in deck.namelist() if n.startswith('ppt/media/') and not n.endswith('/')]
        if len(media)!=len(set(media)) or not media:
            raise ValueError('Unexpected presentation media collection')
        for name in media:
            if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
                raise ValueError('Non-raster or unexpected embedded media: '+name)
            if sha(deck.read(name)) not in approved:
                raise ValueError('Embedded media lacks CIR provenance: '+name)
    return len(media)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('presentation',type=Path);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args()
    print('CIR training media provenance: PASS (%d approved images)'%audit(a.presentation,a.root))
