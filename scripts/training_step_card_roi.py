#!/usr/bin/env python3
"""Validated, lossless crops of the first six workflow step cards.

Current CI captures Playwright element-relative ROIs, making the callouts
independent of CSS grid wrapping, viewport width and card order. Older archived
screenshots predate ROI metadata, so their six known card boundaries are used.
No resampling or generated replacement UI is involved.
"""
from __future__ import annotations
import json
import math
import sys
from pathlib import Path
# Evidence validation also runs in the minimal Docker-release job, before
# Python application dependencies are installed. Reuse the existing strict,
# standard-library PNG/JPEG parser instead of importing Pillow here.
# The executable is also invoked directly by the PowerPoint generator.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ui_documentation_evidence import _image_size

# Pixel-exact bounds for the checked-in 1920 px archival capture, with a small
# safety margin around each card (top of all cards = 504 px, bottom = 919 px).
_ARCHIVED_X = (294, 553, 812, 1071, 1330, 1589)
_ARCHIVED_Y = 497
_ARCHIVED_WIDTH = 246
_ARCHIVED_HEIGHT = 433


def step_card_regions(source: Path, screenshot: dict | None = None) -> list[tuple[float, float, float, float]]:
    width, height = _image_size(Path(source))
    # These coordinates are measured from the same DOM element in the actual
    # authenticated Chromium run which produced the sealed screenshot.
    measured = screenshot.get("step_card_rois") if screenshot else None
    if measured is not None:
        if not isinstance(measured, list) or len(measured) != 6:
            raise ValueError("Expected six measured workflow card regions")
        result = []
        for item in measured:
            if (not isinstance(item, list) or len(item) != 4
                    or any(type(value) not in (float, int) or not math.isfinite(value) for value in item)):
                raise ValueError("Invalid workflow card region")
            x, y, w, h = map(float, item)
            if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0
                    and x + w <= 1.00001 and y + h <= 1.00001
                    and width * w >= 145 and height * h >= 180):
                raise ValueError("Workflow card region clipped or implausibly small")
            result.append((x, y, w, h))
        for i, (x, y, w, h) in enumerate(result):
            for xx, yy, ww, hh in result[:i]:
                overlap = max(0, min(x+w,xx+ww)-max(x,xx))*max(0, min(y+h,yy+hh)-max(y,yy))
                if overlap > 0.03 * min(w*h,ww*hh):
                    raise ValueError("Workflow card regions overlap")
        return result
    # Historical captured full-page screenshot. Anchor Y and height to SOURCE
    # WIDTH, never to page height (which may include unrelated form sections).
    if height > width * 1.28 and width >= 1200:
        scale = width / 1920.0
        top = _ARCHIVED_Y * scale / height
        h = _ARCHIVED_HEIGHT * scale / height
        return [(x/1920.0,top,_ARCHIVED_WIDTH/1920.0,h) for x in _ARCHIVED_X]
    # Compatibility for existing pre-RC94 fixture manifests that lack DOM
    # geometry. All new CI builds record measured element regions instead.
    return [(x, 0.015, 0.163, 0.95) for x in (.02,.183,.346,.509,.672,.835)]


if __name__ == '__main__':
    if not 2 <= len(sys.argv) <= 3:
        raise SystemExit("usage: training_step_card_roi.py IMAGE [SCREENSHOT_ROW_JSON]")
    row=json.loads(Path(sys.argv[2]).read_text(encoding='utf8')) if len(sys.argv)==3 else None
    print(json.dumps(step_card_regions(Path(sys.argv[1]),row),separators=(',',':')))
