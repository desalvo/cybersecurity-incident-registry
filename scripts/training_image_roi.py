#!/usr/bin/env python3
"""Deterministic, lossless region extraction for CIR teaching callouts.

Input must be a trusted original screenshot.  Fractional bounds are checked,
then only pixel content from the original region is copied to a PNG.
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image

def crop_region(source: Path, destination: Path, roi: tuple[float,float,float,float]) -> None:
    x,y,w,h = roi
    if any(not (0 <= v <= 1) for v in roi) or not w or not h or x+w>1.0000001 or y+h>1.0000001:
        raise ValueError('Invalid screenshot ROI')
    with Image.open(source) as im:
        left=round(x*im.width);top=round(y*im.height)
        right=round((x+w)*im.width);bottom=round((y+h)*im.height)
        if right<=left or bottom<=top:
            raise ValueError('Empty screenshot ROI')
        destination.parent.mkdir(parents=True,exist_ok=True)
        im.crop((left,top,right,bottom)).save(destination, format='PNG')

if __name__ == '__main__':
    if len(sys.argv)!=7:raise SystemExit('usage: crop_training_roi.py source destination x y w h')
    crop_region(Path(sys.argv[1]),Path(sys.argv[2]),tuple(map(float,sys.argv[3:])))
