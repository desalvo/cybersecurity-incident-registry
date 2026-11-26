#!/usr/bin/env python3
"""Check PDF appendix pages against same-run screenshots, pixel by pixel.

The PPTX verifier separately proves SHA-256-identical source image bytes are
linked by each slide. This verifier checks that the PDF *renders* those same
images on its corresponding pages, not merely that pages exist.
"""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path


def verify(pdf: Path, screenshot_paths: list[Path], *, base_slides: int = 88) -> int:
    from PIL import Image, ImageChops, ImageStat
    if not screenshot_paths:
        raise ValueError('No screenshots to verify in PDF')
    # Slide coordinates (PptxGenJS wide 13.33333 x 7.5 inches).
    # The gallery uses imageSizingContain at x=.76, y=1.48, w=11.81, h=4.98.
    scale = 960 / 13.33333
    x, y, w, h = [round(v * scale) for v in (.76, 1.48, 11.81, 4.98)]
    with tempfile.TemporaryDirectory(prefix='cir-pdf-gallery-') as tmp:
        for offset, source in enumerate(screenshot_paths):
            page = base_slides + offset + 1
            prefix = Path(tmp) / 'page'
            command = ['pdftoppm', '-f', str(page), '-l', str(page),
                       '-scale-to-x', '960', '-scale-to-y', '540',
                       '-singlefile', '-png', str(pdf), str(prefix)]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=35)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise ValueError(f'PDF screenshot page {page} could not be rendered') from error
            with Image.open(source) as original, Image.open(prefix.with_suffix('.png')) as rendered:
                original = original.convert('RGB')
                rendered = rendered.convert('RGB')
                ratio = min(w / original.width, h / original.height)
                tw, th = round(original.width * ratio), round(original.height * ratio)
                rx = x + (w - tw) // 2
                ry = y + (h - th) // 2
                if rx < 0 or ry < 0 or rx + tw > rendered.width or ry + th > rendered.height:
                    raise ValueError(f'PDF screenshot {page}: invalid image placement')
                actual = rendered.crop((rx, ry, rx + tw, ry + th))
                expected = original.resize((tw, th), Image.Resampling.LANCZOS)
                # Minor LibreOffice PDF resampling and antialiasing is allowed,
                # but replacing the image, removing it or showing a different
                # screenshot makes the mean error significantly larger.
                mae = sum(ImageStat.Stat(ImageChops.difference(actual, expected)).mean) / 3
                if mae > 43:
                    raise ValueError(f'PDF screenshot {page} does not match {source.name} (MAE {mae:.1f})')
            prefix.with_suffix('.png').unlink()
    return len(screenshot_paths)
