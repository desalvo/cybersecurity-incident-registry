"""Regression: the original Support Tickets browser screenshot remains pixel-auditable.

The appendix renders ticket captures as full screenshots in a narrower LEFT
panel with a native zoom on the right. A gallery verifier must not assume that
the screenshot occupies the usual wide image frame. It must also reject an
image replacement rather than raising the allowed pixel-error threshold.
"""
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from scripts.verify_pdf_screenshot_gallery import verify


@pytest.mark.parametrize('capture_id', [
    'support-ticket-new-tenant-admin',
    'support-ticket-submitted-tenant-admin',
    'registry-desktop',
])
def test_gallery_checks_original_capture_in_its_actual_frame(monkeypatch, tmp_path, capture_id):
    Image = pytest.importorskip('PIL.Image')
    ImageDraw = pytest.importorskip('PIL.ImageDraw')
    source = tmp_path / (capture_id + '.png')
    original = Image.new('RGB', (1320, 920), '#205580')
    draw = ImageDraw.Draw(original)
    for n in range(10):
        draw.rectangle((40 + 23*n, 36 + 68*n, 1230 - 18*n, 66 + 68*n),
                       fill=(30 + n*14, 170 - n*10, 90 + n*12))
    original.save(source)
    frame = ((.85, 1.83, 5.14, 4.51) if capture_id.startswith('support-ticket-')
             else (.76, 1.48, 11.81, 4.98))
    scale = 960 / 13.33333
    x, y, w, h = [round(value * scale) for value in frame]
    ratio = min(w / original.width, h / original.height)
    tw, th = round(original.width * ratio), round(original.height * ratio)
    expected = original.resize((tw, th), Image.Resampling.LANCZOS)

    def render(command, **kwargs):
        destination = Path(command[command.index('-png') + 2]).with_suffix('.png')
        page = Image.new('RGB', (960, 540), '#f8fafc')
        page.paste(expected, (x + (w - tw)//2, y + (h - th)//2))
        page.save(destination)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr('scripts.verify_pdf_screenshot_gallery.subprocess.run', render)
    assert verify(tmp_path / 'fixture.pdf', [source], base_slides=129,
                  screenshot_ids=[capture_id]) == 1

    # With the right source but no original image on the page, the audit must
    # fail closed. This catches a PDF that merely shows a zoom or an illustration.
    def blank(command, **kwargs):
        destination = Path(command[command.index('-png') + 2]).with_suffix('.png')
        Image.new('RGB', (960, 540), '#f8fafc').save(destination)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr('scripts.verify_pdf_screenshot_gallery.subprocess.run', blank)
    with pytest.raises(ValueError, match='does not match'):
        verify(tmp_path / 'fixture.pdf', [source], base_slides=129,
               screenshot_ids=[capture_id])


def test_gallery_requires_one_id_per_screenshot(tmp_path):
    with pytest.raises(ValueError, match='IDs do not match'):
        verify(tmp_path / 'unused.pdf', [tmp_path/'one.png'], screenshot_ids=[])
