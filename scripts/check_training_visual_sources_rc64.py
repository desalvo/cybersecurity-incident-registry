#!/usr/bin/env python3
"""Ensure every right-panel photographic illustration is synthetic and full-width safe."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
p=root/'docs/presentation'
spec=json.loads((p/'visual_rc64_spec.json').read_text(encoding='utf8'))
prov=json.loads((p/'visual_rc63_art/provenance.json').read_text(encoding='utf8'))
assert len(spec)==79
prov64=json.loads((p/'visual_rc64_art/provenance.json').read_text(encoding='utf8'))
required={3,4,5,6,7,28,29,30,31,32,33,34,35,39,40,41,42,43,44,70,73,75,76,77,78,79}
for record in list(prov['sources'].values())+list(prov64['sources'].values()):
    src=root/record['path']
    assert src.is_file() and hashlib.sha256(src.read_bytes()).hexdigest()==record['sha256'],str(src)
assert {int(k) for k in prov64['slides']}=={31,33,41,42,79}
assert {n for n,s in enumerate(spec,1) if s.get('photo_art')}==required
assert spec[30].get('right_diagram')=='tenant_inheritance'
assert 'duplicat' not in ' '.join(spec[30]['bullets']).lower()
assert 'remapp' not in ' '.join(spec[30]['bullets']).lower()
assert not any('L’eredità deve essere visibile' in v for v in spec[29]['bullets'])
seen={}
for ix,slide in enumerate(spec,1):
    image=slide.get('photo_art')
    assert not slide.get('conceptual_art') and not slide.get('synthetic_diagram'),ix
    if not image: continue
    origin=prov64 if str(ix) in prov64['slides'] else prov
    item=origin['slides'][str(ix)]
    assert image==item['file'] and item['real_people'] is False,ix
    assert image.startswith(('docs/presentation/visual_rc63_art/','docs/presentation/visual_rc64_art/')),ix
    f=root/image
    assert f.is_file(),ix
    digest=hashlib.sha256(f.read_bytes()).hexdigest()
    assert digest==item['sha256'],ix
    # Existing RC63 images may still be reused on unaffected slides. The five
    # revised panels must each have their own distinct image.
    if ix in (31,33,41,42,79):
        assert digest not in seen,(ix,seen.get(digest))
        seen[digest]=ix
    from PIL import Image
    with Image.open(f) as im:
        w,h=im.size
        if ix==31:
            assert w/h>2.5,(ix,w,h)
        else:
            assert 1.20<w/h<1.30,(ix,w,h)
print('RC64 photo provenance OK: 26 people-free synthetic illustrations, five new visuals and editable inheritance diagram')
