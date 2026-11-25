#!/usr/bin/env python3
"""Ensure every right-panel photographic illustration is synthetic and full-width safe."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
p=root/'docs/presentation'
spec=json.loads((p/'visual_rc63_spec.json').read_text(encoding='utf8'))
prov=json.loads((p/'visual_rc63_art/provenance.json').read_text(encoding='utf8'))
assert len(spec)==79
assert len(prov['slides'])==26
for source in prov['sources'].values():
    src=root/source['path']
    assert src.is_file() and hashlib.sha256(src.read_bytes()).hexdigest()==source['sha256']
for ix,slide in enumerate(spec,1):
    image=slide.get('photo_art')
    assert not slide.get('conceptual_art') and not slide.get('synthetic_diagram'),ix
    if not image:continue
    item=prov['slides'][str(ix)]
    assert image==item['file'] and item['real_people'] is False,ix
    assert image.startswith('docs/presentation/visual_rc63_art/'),ix
    f=root/image
    assert f.is_file(),ix
    assert hashlib.sha256(f.read_bytes()).hexdigest()==item['sha256'],ix
    from PIL import Image
    with Image.open(f) as im:
        w,h=im.size
        assert w/h>1.20 and w/h<1.30,(ix,w,h)
print('RC63 photo provenance OK: 26 original synthetic illustrations, no cropped margins')
