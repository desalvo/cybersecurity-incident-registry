#!/usr/bin/env python3
"""Recreate RC63 photos from project-owned ImageGen sheets; no network required."""
from PIL import Image,ImageEnhance,ImageFilter
from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parents[1]
folder=root/'docs/presentation/visual_rc63_art'
provenance=json.loads((folder/'provenance.json').read_text(encoding='utf8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for key,record in provenance['sources'].items():
 path=root/record['path']
 assert digest(path)==record['sha256'],f'Original synthetic source mismatch {key}'
for slide,record in provenance['slides'].items():
 code=record['source'];img=Image.open(folder/f'original_{code[0]}.png').convert('RGB')
 cell=int(code[1]);column=cell%3;row=cell//3
 w=img.width/3;h=img.height/2
 crop=img.crop((round(column*w)+6,round(row*h)+6,round((column+1)*w)-6,round((row+1)*h)-6))
 crop=ImageEnhance.Color(crop).enhance(1.21)
 crop=ImageEnhance.Brightness(crop).enhance(1.095)
 crop=ImageEnhance.Contrast(crop).enhance(1.075)
 outw,outh=1600,1280
 s=max(outw/crop.width,outh/crop.height)
 bg=crop.resize((round(crop.width*s),round(crop.height*s)),Image.Resampling.LANCZOS)
 dx=(bg.width-outw)//2;dy=(bg.height-outh)//2
 bg=bg.crop((dx,dy,dx+outw,dy+outh)).filter(ImageFilter.GaussianBlur(28))
 bg=ImageEnhance.Brightness(bg).enhance(.84)
 f=min((outw-28)/crop.width,(outh-28)/crop.height)
 fg=crop.resize((int(crop.width*f),int(crop.height*f)),Image.Resampling.LANCZOS)
 bg.paste(fg,((outw-fg.width)//2,(outh-fg.height)//2))
 dest=root/record['file']
 bg.save(dest,quality=90,subsampling=0,optimize=True)
 assert digest(dest)==record['sha256'],f'Photo source mismatch slide {slide}'
print(f"Rebuilt {len(provenance['slides'])} synthetic photographic illustrations")
